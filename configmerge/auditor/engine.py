"""
configmerge.auditor.engine
~~~~~~~~~~~~~~~~~~~~~~~~~~
Data models and AuditEngine for comparing configurations across multiple
site nodes (base directories) to detect configuration drift.

Key concepts
------------
has_mismatch (bool)
    True when active values differ across present nodes AND the parameter is
    not classified as a logical difference.  These are actionable items the
    user should investigate and fix.

is_logical_diff (bool)
    True when the parameter key/compound matches a user-supplied
    ``logical_diff_patterns`` regex list.  Such parameters are *expected* to
    differ between nodes (e.g. hostname, log file name, instance ID).  They
    are tracked and visible in the report but are not counted as mismatches.

KV files are compared section by section against the base node (the first node in
the audit config that has the file); see MEMORY.md (2026-09-15) for the rules.

Reuses:
  - KV line helpers (_is_kv_line, _has_valid_kv_key, _split_kv) from configmerge.processors.kv
  - BaseDirConfig from configmerge.models
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Backup-file detection patterns (Phase 3.2)
# ---------------------------------------------------------------------------
# Matches common backup suffixes appended to config filenames in production.
# Examples detected:
#   GTPProxy.cfg_bkp_27072024  →  stem: GTPProxy.cfg
#   fsmapp.properties_bkp      →  stem: fsmapp.properties
#   server.xml_20240705        →  stem: server.xml
#   server.xml.bak             →  stem: server.xml
#   server.xml_backup          →  stem: server.xml
_BACKUP_SUFFIX_RE = re.compile(
    r"""
    (?:
        [_.](?:bkp|backup|orig|org|bak|old|save).*   # _bkp  _bkp_27072024  _bkp200821  _bak17062026  .old
      | _\d{14}(?:[_.\-].+)?      # _20240727153000  (YYYYMMDDHHmmss)
      | _\d{8}(?:[_.\-].+)?       # _20240705  _20240705_v2  _27072024
      | _\d{6}(?:[_.\-].+)?       # _240705  (DDMMYY)
    )$
    """,
    re.VERBOSE | re.IGNORECASE,
)

from ..errors import tag
from ..models import BaseDirConfig
from ..processors.kv import _has_valid_kv_key, _is_kv_line, _split_kv
from ..utils import open_text, file_sha256
from .file_filter import FileFilter
from .html_report import write_audit_html
from .sstp_parser import SstpParser, categorise_block_diff


# Maximum raw-content bytes embedded in HTML per file (512 KB).
_MAX_RAW_BYTES = 524_288


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AuditParam:
    """One parameter row in the audit comparison table."""
    compound: str               # "SECTION|key" for KV, dot-path for JSON, "__md5__" for text
    section: str                # section name or "" for top-level / text files
    key: str                    # display key name
    values: Dict[str, Optional[str]]   # node_name -> value (None = key absent)
    commented: Dict[str, bool]         # node_name -> is_commented
    has_mismatch: bool          # True if active values differ and NOT a logical diff
    is_logical_diff: bool = False      # True if matched by logical_diff_patterns
    lines: Dict[str, List[int]] = field(default_factory=dict)       # KV: node -> source line numbers
    dup_values: Dict[str, List[str]] = field(default_factory=dict)  # KV: node -> all active values when duplicated in section


@dataclass
class BinaryInfo:
    """SHA-256 and size info for one node's copy of a binary file."""
    md5: str        # kept as 'md5' for patch JSON backward compat; now holds SHA-256
    size_bytes: int
    present: bool


@dataclass
class AuditFile:
    """Comparison result for one file across all nodes."""
    rel_path: str
    file_type: str              # "kv" | "json" | "binary" | "xml" | "text"
    present_in: List[str]       # node names that have this file
    params: List[AuditParam]
    binary: Dict[str, BinaryInfo]      # populated only when file_type == "binary"
    raw_content: Dict[str, str]        # node_name -> raw text (for KV reconstruction + display)
    mismatch_count: int                # content mismatches among present nodes (excludes absence & logical diffs)
    warnings: List[str] = field(default_factory=list)
    logical_diff_count: int = 0        # parameters expected to differ (node-specific)
    absent_count: int = 0              # number of nodes where the file is entirely absent
    # Large-file optimisation: when a file is > _MAX_RAW_BYTES on any node AND has
    # no mismatches AND no absent nodes, raw_content and params are cleared.
    content_skipped: bool = False      # True when diff display was skipped
    param_count: int = 0               # original param count (before clearing on skip)
    file_sizes: "Dict[str, int]" = field(default_factory=dict)  # node -> bytes
    # KV section check, in merged section order. Each entry:
    #   name, base (node checked against), present {node: bool}, base_count (None when base lacks
    #   the section), counts {node: {match, differ, missing, extra}}, param_counts {node: int}
    sections: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# KV section walker (audit only — merge keeps processors.kv.parse_kv_doc)
# ---------------------------------------------------------------------------

KV_DEFAULT_SECTION = "DEFAULT"
# Same header rule as parse_kv_doc: "[Name]" optionally followed by an inline "# comment".
_KV_SECTION_RE = re.compile(r'^\s*\[(.+)\]\s*(?:#.*)?$')
_KV_COMMENTED_SECTION_RE = re.compile(r'^\[(.+)\]\s*$')


@dataclass
class _KVSections:
    """One node's KV file grouped by real section. A commented header "#[X]" is a comment."""
    section_order: List[str]
    key_order: Dict[str, List[str]]                         # section -> keys in file order
    active: Dict[Tuple[str, str], List[Tuple[str, int]]]    # (section, key) -> [(value, line)]
    commented: Dict[Tuple[str, str], Tuple[str, int]]       # (section, key) -> last (value, line)


def _walk_kv_sections(text: str) -> _KVSections:
    doc = _KVSections([KV_DEFAULT_SECTION], {KV_DEFAULT_SECTION: []}, {}, {})
    section = KV_DEFAULT_SECTION

    def note(key: str) -> None:
        if key not in doc.key_order[section]:
            doc.key_order[section].append(key)

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        m_sec = _KV_SECTION_RE.match(line) if stripped.startswith("[") else None
        if m_sec:
            section = f"[{m_sec.group(1).strip()}]"
            if section not in doc.key_order:
                doc.section_order.append(section)
                doc.key_order[section] = []
            continue
        if stripped[0] in "#!":
            inner = stripped.lstrip("#!").strip()
            if _KV_COMMENTED_SECTION_RE.match(inner):
                continue
            if _is_kv_line(inner) and _has_valid_kv_key(inner):
                key, value, _ = _split_kv(inner)
                if key:
                    doc.commented[(section, key)] = (value, lineno)
                    note(key)
            continue
        if _is_kv_line(stripped):
            key, value, _ = _split_kv(stripped)
            if key:
                doc.active.setdefault((section, key), []).append((value, lineno))
                note(key)
    return doc


def _merge_order(sequences: List[List[str]]) -> List[str]:
    """Merge ordered sequences: the first sets the order, later items are placed after their predecessor."""
    merged: List[str] = []
    seen: Set[str] = set()
    for seq in sequences:
        inserts: Dict[Optional[str], List[str]] = {}
        anchor: Optional[str] = None
        for item in seq:
            if item in seen:
                anchor = item
            else:
                inserts.setdefault(anchor, []).append(item)
                seen.add(item)
        rebuilt = list(inserts.get(None, []))
        for item in merged:
            rebuilt.append(item)
            rebuilt.extend(inserts.get(item, []))
        merged = rebuilt
    return merged


def _section_check_kind(values: Dict[str, Optional[str]], commented: Dict[str, bool],
                        dup_values: Dict[str, List[str]], base: str, node: str) -> Optional[str]:
    base_val, node_val = values.get(base), values.get(node)
    if base_val is None and node_val is None:
        return None
    if node_val is None:
        return "missing"
    if base_val is None:
        return "extra"
    if not commented.get(base) and not commented.get(node) and base_val != node_val:
        return "differ"
    return "match"


@dataclass
class AuditResult:
    """Top-level result returned by AuditEngine.run()."""
    nodes: List[str]
    node_dirs: Dict[str, str]   # node_name -> base_dir path
    files: List[AuditFile]
    total_mismatches: int
    total_logical_diffs: int            # across all files
    run_timestamp: str          # "YYYYMMDD_HHMMSS"
    run_dir: str                # path to the audit_YYYYMMDD_HHMMSS/ output directory
    output_dir: str = ""        # patch output base dir (from audit config {"output_dir": "..."})
    skipped_backups: List[dict] = field(default_factory=list)
    filtered_files: List[dict] = field(default_factory=list)
    render_errors: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AuditEngine
# ---------------------------------------------------------------------------

class AuditEngine:
    """Compare configuration files across multiple site nodes."""

    # .sh is compared as text: shell scripts are not key/value files (agreed 2026-09-18)
    KV_EXTS   = {'.properties', '.cfg', '.ini', '.conf'}
    JSON_EXTS = {'.json'}
    SSTP_EXTS = {'.sstp'}

    def __init__(self, nodes: List[BaseDirConfig], report_dir: str = "reports",
                 logical_diff_patterns: Optional[List[str]] = None,
                 quiet: bool = False,
                 no_skip_files: Optional[List[str]] = None,
                 filter_file: Optional[str] = None,
                 output_dir: str = ""):
        self.nodes      = nodes
        self.report_dir = report_dir
        self._output_dir = output_dir
        self._quiet     = quiet
        ts              = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir    = os.path.join(report_dir, f"audit_{ts}")
        self._ts        = ts
        self._log_lines: List[str] = []
        # Phase 3.2: filenames exempt from backup-detection skipping
        self._no_skip_files: Set[str] = set(no_skip_files or [])
        self._skipped_backups: List[dict] = []
        # Phase 3.3: file/directory filter
        self._file_filter = FileFilter(filter_file)
        self._filtered_files: List[dict] = []

        # Compile logical-diff patterns for fast matching
        self._logical_patterns: List[re.Pattern] = []
        for pat in (logical_diff_patterns or []):
            try:
                self._logical_patterns.append(re.compile(pat, re.IGNORECASE))
            except re.error as exc:
                print(tag("CMT-AUD-W001", f"[WARN] Invalid logical_diff_pattern {pat!r}: {exc}"))

    # ------------------------------------------------------------------
    # Structured logger (writes to audit.log in run_dir)
    # ------------------------------------------------------------------

    def _log(self, level: str, msg: str) -> None:
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} [{level:<5}] {msg}"
        self._log_lines.append(line)
        if level in ("ERROR", "WARN "):
            print(line)
        elif not self._quiet:
            # In non-quiet mode also print INFO lines to console
            # (MATCH lines are suppressed in quiet mode via the caller)
            pass

    def _flush_log(self) -> str:
        log_path = os.path.join(self.run_dir, "audit.log")
        with open(log_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(self._log_lines) + "\n")
        return log_path

    # ------------------------------------------------------------------
    # Logical-diff classification
    # ------------------------------------------------------------------

    def _is_logical_diff(self, key: str, compound: str) -> bool:
        """Return True if key or compound matches any logical_diff_pattern."""
        for pat in self._logical_patterns:
            if pat.search(key) or pat.search(compound):
                return True
        return False

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> AuditResult:
        os.makedirs(self.run_dir, exist_ok=True)

        node_names = [n.name for n in self.nodes]
        node_dirs  = {n.name: os.path.abspath(n.base_dir) for n in self.nodes}

        # 7.3: Pre-run node directory validation
        for node in self.nodes:
            if not os.path.isdir(node.base_dir):
                msg = tag("CMT-AUD-E001",
                          f"[ERROR] Node '{node.name}': directory {node.base_dir!r} not found. "
                          "Aborting.")
                print(msg, flush=True)
                self._log("ERROR", msg)
                self._flush_log()
                raise SystemExit(2)

        self._log("INFO ", f"Audit started — nodes: {', '.join(node_names)}")
        self._log("INFO ", f"Report dir: {self.run_dir}")
        if self._quiet:
            print("[INFO ] Quiet mode: MATCH lines suppressed — only DIFF/WARN/ERROR shown")
        if self._logical_patterns:
            pats = [p.pattern for p in self._logical_patterns]
            self._log("INFO ", f"Logical-diff patterns ({len(pats)}): {', '.join(pats)}")

        # 1. Scan each node's base_dir -> set of rel_paths
        node_files: Dict[str, Set[str]] = {}
        for node in self.nodes:
            self._log("INFO ", f"Scanning {node.name}: {node.base_dir}")
            node_files[node.name] = self._scan_dir(node.base_dir)
            self._log("INFO ", f"  {len(node_files[node.name])} files found in {node.name}")

        # 2. Union of all rel_paths -> sorted
        all_paths = sorted(set().union(*node_files.values()))
        self._log("INFO ", f"Total unique files to compare: {len(all_paths)}")

        # 3. Compare each file across nodes
        audit_files: List[AuditFile] = []
        render_errors: List[dict] = []
        total_files   = len(all_paths)
        diffs_so_far  = 0
        _progress_interval = 25

        for file_idx, rel_path in enumerate(all_paths):
            present_in = [n for n in node_names if rel_path in node_files[n]]
            abs_paths  = {n: os.path.join(node_dirs[n], rel_path)
                          for n in present_in}

            try:
                af = self._compare_file(rel_path, present_in, abs_paths, node_names)
            except Exception as exc:
                tb = traceback.format_exc()
                self._log("ERROR", tag("CMT-AUD-E002", f"Processing error for {rel_path}: {exc}"))
                render_errors.append({
                    "rel_path":  rel_path,
                    "present_in": present_in,
                    "error":     tag("CMT-AUD-E002", str(exc)),
                    "traceback": tb,
                })
                af = AuditFile(
                    rel_path       = rel_path,
                    file_type      = "error",
                    present_in     = present_in,
                    params         = [],
                    binary         = {},
                    raw_content    = {},
                    mismatch_count = 0,
                    warnings       = [f"Processing error: {exc}"],
                )
            audit_files.append(af)
            if af.mismatch_count:
                diffs_so_far += 1

            for w in af.warnings:
                self._log("WARN ", f"{rel_path}: {w}")

            if af.mismatch_count and af.logical_diff_count:
                line = f"  DIFF({af.mismatch_count:3d}) LDIFF({af.logical_diff_count:3d})  {rel_path}"
                self._log("INFO ", line)
                if self._quiet:
                    print(line, flush=True)
            elif af.mismatch_count:
                line = f"  DIFF({af.mismatch_count:3d})             {rel_path}"
                self._log("INFO ", line)
                if self._quiet:
                    print(line, flush=True)
            elif af.logical_diff_count:
                line = f"  LDIFF({af.logical_diff_count:3d})            {rel_path}  [expected node-specific differences]"
                self._log("INFO ", line)
                if self._quiet:
                    print(line, flush=True)
            else:
                self._log("INFO ", f"  MATCH                    {rel_path}")
                # In quiet mode, MATCH lines are NOT printed to console

            # 7.4: Progress indicator (only when total > 50 and not quiet)
            processed = file_idx + 1
            if (total_files > 50 and not self._quiet
                    and processed % _progress_interval == 0
                    and processed < total_files):
                pct = int(100 * processed / total_files)
                print(f"[PROGRESS] {processed}/{total_files} files processed ({pct}%) "
                      f"— {diffs_so_far} diffs found so far", flush=True)

        total_mismatches     = sum(af.mismatch_count      for af in audit_files)
        total_logical_diffs  = sum(af.logical_diff_count  for af in audit_files)

        result = AuditResult(
            nodes               = node_names,
            node_dirs           = {n.name: n.base_dir for n in self.nodes},
            files               = audit_files,
            total_mismatches    = total_mismatches,
            total_logical_diffs = total_logical_diffs,
            run_timestamp       = self._ts,
            run_dir             = self.run_dir,
            output_dir          = self._output_dir,
            skipped_backups     = list(self._skipped_backups),
            filtered_files      = list(self._filtered_files),
            render_errors       = render_errors,
        )

        # 3b. Phase 5 post-processing
        feedback_dir = os.path.join(self.run_dir, "feedback")
        os.makedirs(feedback_dir, exist_ok=True)

        # 5.2: Logical diff parameter summary
        logical_diff_summary = self._build_logical_diff_summary(audit_files)
        if logical_diff_summary:
            ld_path = os.path.join(feedback_dir, "logical_diff_summary.json")
            with open(ld_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(logical_diff_summary, f, indent=2)
            self._log("INFO ",
                      f"[LOGICAL DIFFS] {len(logical_diff_summary)} parameters skipped "
                      f"— see feedback/logical_diff_summary.json")
            print(f"[LOGICAL DIFFS]  {len(logical_diff_summary)} parameter(s) skipped "
                  f"— {ld_path}", flush=True)

        # 5.1: Log file/prefix uniqueness detection
        log_warnings = self._detect_log_name_duplicates(audit_files, node_names)
        if log_warnings:
            lw_path = os.path.join(feedback_dir, "log_name_warnings.json")
            with open(lw_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(log_warnings, f, indent=2)
            self._log("WARN ",
                      f"[CMT-AUD-W008] [LOG NAMES] {len(log_warnings)} duplicate log prefix(es) "
                      f"detected — see feedback/log_name_warnings.json")
            print(f"[CMT-AUD-W008] [LOG NAMES] {len(log_warnings)} duplicate log prefix(es) "
                  f"— {lw_path}", flush=True)

        # 3c. Write skipped-backups feedback (Phase 3.2)
        # 5.3: Feedback accumulator
        self._append_feedback_history(
            node_names=node_names,
            skipped_backups=self._skipped_backups,
            logical_diffs=logical_diff_summary,
            log_warnings=log_warnings,
            filtered_files=self._filtered_files,
        )

        if self._skipped_backups:
            skipped_path = os.path.join(feedback_dir, "skipped_backups.json")
            with open(skipped_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(self._skipped_backups, f, indent=2)
            self._log("INFO ",
                      f"Backup files skipped: {len(self._skipped_backups)} "
                      f"— see feedback/skipped_backups.json")
            print(f"[BACKUP SKIP]    {len(self._skipped_backups)} backup file(s) skipped "
                  f"— {skipped_path}")

        if self._filtered_files:
            filtered_path = os.path.join(feedback_dir, "filtered_files.json")
            with open(filtered_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(self._filtered_files, f, indent=2)
            self._log("INFO ",
                      f"Files excluded by filter: {len(self._filtered_files)} "
                      f"— see feedback/filtered_files.json")
            print(f"[FILTER]         {len(self._filtered_files)} file(s) excluded by filter "
                  f"— {filtered_path}")

        # 4. Write HTML report
        report_path = write_audit_html(result, self.run_dir)
        self._log("INFO ", f"HTML report: {report_path}")

        # 5. Summary
        files_with_diff    = sum(1 for af in audit_files if af.mismatch_count > 0)
        files_matched      = sum(1 for af in audit_files
                                 if af.mismatch_count == 0 and af.logical_diff_count == 0)
        files_logical_only = sum(1 for af in audit_files
                                 if af.mismatch_count == 0 and af.logical_diff_count > 0)

        self._log("INFO ", (
            f"SUMMARY — nodes:{len(node_names)}"
            f"  files:{len(audit_files)}"
            f"  matched:{files_matched}"
            f"  logical_only:{files_logical_only}"
            f"  with_diffs:{files_with_diff}"
            f"  mismatches:{total_mismatches}"
            f"  logical_diffs:{total_logical_diffs}"
        ))

        log_path = self._flush_log()

        print(f"[AUDIT REPORT]   {report_path}")
        print(f"[AUDIT LOG]      {log_path}")
        print(f"[AUDIT SUMMARY]  "
              f"Nodes:{len(node_names)}  "
              f"Files:{len(audit_files)}  "
              f"Matched:{files_matched}  "
              f"LogicalDiffs:{total_logical_diffs}  "
              f"Mismatches:{total_mismatches}")

        return result

    # ------------------------------------------------------------------
    # Directory scanning — hidden files excluded (BUG-03)
    # ------------------------------------------------------------------

    def _scan_dir(self, base_dir: str) -> Set[str]:
        """Walk base_dir and return a set of forward-slash relative paths.

        Phase 3.2: files matching backup-suffix patterns are silently skipped
        when their canonical stem (the filename without the backup suffix)
        exists in the same directory.  Exempt filenames listed in
        ``self._no_skip_files`` are never classified as backups.
        """
        # Pass 1 — collect everything; group by directory for stem lookup
        # dir_rel_path -> set of filenames in that directory
        dir_files: Dict[str, Set[str]] = {}
        raw_entries: List[Tuple[str, str, str]] = []  # (abs_path, rel_slash, fname)

        base_real = os.path.realpath(base_dir)
        for root, dirs, files in os.walk(base_dir, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            dir_rel = os.path.relpath(root, base_dir).replace(os.sep, '/')
            if dir_rel == '.':
                dir_rel = ''
            dir_files.setdefault(dir_rel, set())
            for fname in files:
                if fname.startswith('.'):
                    continue
                abs_path = os.path.join(root, fname)
                real_abs = os.path.realpath(abs_path)
                # MOD-4: path-traversal guard — skip symlinks escaping base_dir
                if (not real_abs.startswith(base_real + os.sep)
                        and real_abs != base_real):
                    continue
                dir_files[dir_rel].add(fname)
                rel = (dir_rel + '/' + fname) if dir_rel else fname
                raw_entries.append((abs_path, rel, fname))

        # Pass 2 — filter out backup files and apply file filter
        result: Set[str] = set()
        for abs_path, rel, fname in raw_entries:
            dir_rel = '/'.join(rel.split('/')[:-1])
            siblings = dir_files.get(dir_rel, set())

            if self._is_backup_file(fname, siblings):
                self._skipped_backups.append({
                    "rel_path":  rel,
                    "abs_path":  abs_path,
                    "reason":    "backup_suffix",
                    "base_dir":  base_dir,
                })
                continue

            fr = self._file_filter.should_include(rel)
            if not fr.included:
                self._filtered_files.append({
                    "rel_path":  rel,
                    "abs_path":  abs_path,
                    "reason":    fr.reason,
                    "base_dir":  base_dir,
                })
                continue

            result.add(rel)
        return result

    # ------------------------------------------------------------------
    # Phase 5.2: Logical diff parameter summary
    # ------------------------------------------------------------------

    def _build_logical_diff_summary(self, audit_files: List["AuditFile"]) -> List[dict]:
        """Collect all parameters classified as logical diffs across all files."""
        summary = []
        for af in audit_files:
            for p in af.params:
                if p.is_logical_diff:
                    summary.append({
                        "file":     af.rel_path,
                        "section":  p.section,
                        "key":      p.key,
                        "compound": p.compound,
                        "values":   p.values,
                    })
        return summary

    # ------------------------------------------------------------------
    # Phase 5.1: Log file/prefix uniqueness detection
    # ------------------------------------------------------------------

    # Patterns for keys that typically hold log file prefixes or filenames
    _LOG_KEY_RE = re.compile(
        r"(?:log[._\-]?(?:file|prefix|dir|path|name)|"
        r"(?:kpi|stats|snmp)[._\-].*prefix|"
        r"logfile|logprefix)",
        re.IGNORECASE,
    )

    def _detect_log_name_duplicates(self, audit_files: List["AuditFile"],
                                    node_names: List[str]) -> List[dict]:
        """Find KV parameters whose key looks like a log prefix/file name AND whose
        value is the same across two or more nodes — a likely misconfiguration that
        causes two nodes to write to the same log file.

        Returns a list of warning dicts.
        """
        warnings_list: List[dict] = []
        for af in audit_files:
            if af.file_type != "kv":
                continue
            for p in af.params:
                if not self._LOG_KEY_RE.search(p.key):
                    continue
                # Collect non-empty, non-null values from present nodes
                val_to_nodes: Dict[str, List[str]] = {}
                for node in node_names:
                    v = p.values.get(node)
                    if v and str(v).strip():
                        val_to_nodes.setdefault(str(v).strip(), []).append(node)
                for val, nodes in val_to_nodes.items():
                    if len(nodes) >= 2:
                        warnings_list.append({
                            "file":     af.rel_path,
                            "compound": p.compound,
                            "key":      p.key,
                            "value":    val,
                            "nodes":    nodes,
                            "reason":   "duplicate_log_prefix",
                        })
        return warnings_list

    # ------------------------------------------------------------------
    # Phase 5.3: Cross-run feedback accumulator
    # ------------------------------------------------------------------

    def _append_feedback_history(self, node_names: List[str],
                                  skipped_backups: List[dict],
                                  logical_diffs: List[dict],
                                  log_warnings: List[dict],
                                  filtered_files: List[dict]) -> None:
        """Append this run's summary to ~/.configmergetool/feedback_history.json."""
        import pathlib
        history_dir  = pathlib.Path.home() / ".configmergetool"
        history_path = history_dir / "feedback_history.json"
        try:
            history_dir.mkdir(parents=True, exist_ok=True)
            history: dict = {}
            if history_path.exists():
                try:
                    with open(str(history_path), encoding="utf-8") as hf:
                        history = json.load(hf)
                except Exception:
                    history = {}
            if not isinstance(history, dict) or "runs" not in history:
                history = {"runs": []}

            history["runs"].append({
                "timestamp":       self._ts,
                "nodes":           node_names,
                "run_dir":         self.run_dir,
                "skipped_backups": [e.get("rel_path") for e in skipped_backups],
                "logical_diffs":   [e.get("compound") for e in logical_diffs],
                "log_warnings":    log_warnings,
                "filtered_files":  [e.get("rel_path") for e in filtered_files],
            })

            with open(str(history_path), "w", encoding="utf-8", newline="\n") as hf:
                json.dump(history, hf, indent=2)
        except Exception as _fh_exc:
            # Feedback history is advisory — never abort the run, but do warn
            self._log("WARN ", tag("CMT-AUD-W002", f"Could not write feedback history: {_fh_exc}"))

    # ------------------------------------------------------------------
    # Backup-file detection helpers
    # ------------------------------------------------------------------

    def _is_backup_file(self, fname: str, siblings: Set[str]) -> bool:
        """Return True when *fname* looks like a backup of another file in *siblings*.

        Skipping is suppressed when the filename is in ``self._no_skip_files``.
        """
        if fname in self._no_skip_files:
            return False
        # Marker after the full name: fsmapp.properties_bkp200821 → fsmapp.properties
        m = _BACKUP_SUFFIX_RE.search(fname)
        if m and fname[: m.start()] and fname[: m.start()] in siblings:
            return True
        # Marker before the extension (F-025): fsmapp_240226.properties → fsmapp.properties
        root, ext = os.path.splitext(fname)
        m = _BACKUP_SUFFIX_RE.search(root) if ext else None
        if m and root[: m.start()] and root[: m.start()] + ext in siblings:
            return True
        # Only ever a backup when the original actually exists next to it
        return False

    # ------------------------------------------------------------------
    # Per-file comparison dispatch
    # ------------------------------------------------------------------

    def _compare_file(self, rel_path: str, present_in: List[str],
                      abs_paths: Dict[str, str],
                      all_nodes: List[str]) -> AuditFile:
        ext = os.path.splitext(rel_path)[1].lower()

        # Binary routing: check ALL present nodes, not just the first.
        # A file is treated as binary if:
        #   (a) its extension is in the hard-coded BINARY_EXCLUDES set, OR
        #   (b) ANY node's copy of the file contains a null byte in the first
        #       8 KB (null-byte heuristic).
        # Checking all nodes catches cases where one node has an old text version
        # and another node has already been replaced with a binary, and avoids
        # misrouting noext binary executables that happen to be absent on the
        # first node.
        from .file_filter import BINARY_EXCLUDES as _BIN_EX
        if ext in _BIN_EX or any(
            self._is_binary(abs_paths[n]) for n in present_in if n in abs_paths
        ):
            return self._compare_binary(rel_path, present_in, abs_paths, all_nodes)
        elif ext in self.SSTP_EXTS:
            return self._compare_sstp(rel_path, present_in, abs_paths, all_nodes)
        elif ext in self.KV_EXTS:
            return self._compare_kv(rel_path, present_in, abs_paths, all_nodes)
        elif ext in self.JSON_EXTS:
            return self._compare_json(rel_path, present_in, abs_paths, all_nodes)
        else:
            file_type = "xml" if ext == ".xml" else "text"
            return self._compare_text(rel_path, file_type, present_in, abs_paths, all_nodes)

    # ------------------------------------------------------------------
    # Logical-diff reclassification (applied after each comparison method)
    # ------------------------------------------------------------------

    def _classify_logical_diffs(self, params: List[AuditParam]) -> int:
        """
        Walk params: if a param has_mismatch and its key/compound matches a
        logical_diff_pattern, mark it as is_logical_diff=True, has_mismatch=False.
        Returns the count of logical diffs found.
        """
        count = 0
        for p in params:
            if p.has_mismatch and self._is_logical_diff(p.key, p.compound):
                p.is_logical_diff = True
                p.has_mismatch    = False
                count            += 1
        return count

    # ------------------------------------------------------------------
    # Binary comparison
    # ------------------------------------------------------------------

    def _is_binary(self, path: str) -> bool:
        try:
            with open(path, 'rb') as f:
                chunk = f.read(8192)
            return b'\x00' in chunk
        except OSError:
            return False

    def _compare_binary(self, rel_path: str, present_in: List[str],
                        abs_paths: Dict[str, str],
                        all_nodes: List[str]) -> AuditFile:
        binary: Dict[str, BinaryInfo] = {}
        for node in all_nodes:
            if node in abs_paths:
                sha256, size = self._sha256_size(abs_paths[node])
                binary[node] = BinaryInfo(md5=sha256, size_bytes=size, present=True)
            else:
                binary[node] = BinaryInfo(md5="", size_bytes=0, present=False)

        present_hashes    = {binary[n].md5 for n in present_in}
        has_content_diff  = len(present_hashes) > 1
        mismatch          = 1 if has_content_diff else 0
        absent_count      = len(all_nodes) - len(present_in)

        return AuditFile(
            rel_path       = rel_path,
            file_type      = "binary",
            present_in     = present_in,
            params         = [],
            binary         = binary,
            raw_content    = {},
            mismatch_count = mismatch,
            absent_count   = absent_count,
        )

    def _sha256_size(self, path: str) -> Tuple[str, int]:
        """Return (sha256_hex, size_bytes) for a binary file."""
        h    = hashlib.sha256()
        size = 0
        try:
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    h.update(chunk)
                    size += len(chunk)
        except OSError:
            return "", 0
        return h.hexdigest(), size

    @staticmethod
    def _get_file_sizes(abs_paths: Dict[str, int]) -> Dict[str, int]:
        """Return node → file size in bytes for each path in abs_paths."""
        sizes: Dict[str, int] = {}
        for node, path in abs_paths.items():
            try:
                sizes[node] = os.path.getsize(path)
            except OSError:
                sizes[node] = 0
        return sizes

    @staticmethod
    def _should_skip_content(file_sizes: Dict[str, int], mismatch_count: int,
                              absent_count: int = 0) -> bool:
        """Return True when large identical files should have their diff display skipped.

        Criteria: no content mismatches AND no absent nodes AND at least one node's
        file exceeds _MAX_RAW_BYTES.  Files with absent nodes are never skipped so
        the user can still see which nodes are missing.
        """
        if mismatch_count != 0 or absent_count != 0:
            return False
        return any(sz > _MAX_RAW_BYTES for sz in file_sizes.values())

    # ------------------------------------------------------------------
    # KV comparison
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # SSTP comparison (Phase 8)
    # ------------------------------------------------------------------

    def _compare_sstp(self, rel_path: str, present_in: List[str],
                      abs_paths: Dict[str, str],
                      all_nodes: List[str]) -> "AuditFile":
        """Semantic diff for .sstp routing rule files.

        Each top-level block becomes one AuditParam.  The compound key is
        "BLOCK|NAME(params)".  Diff categories: VALUE_DIFF, ORDER_DIFF,
        STRUCT_EQUIV (treated as logical diff), MATCH.
        """
        docs: Dict[str, Any] = {}
        warnings: List[str] = []

        for node in present_in:
            path = abs_paths[node]
            try:
                text    = open_text(path)
                docs[node] = SstpParser.parse(text)
            except Exception as exc:
                warnings.append(f"{node}: [CMT-AUD-W003] SSTP parse error — {exc}")
                docs[node] = None

        # Safety net (F-030): a node whose file yields no SSTP blocks cannot be compared
        # semantically — compare as text so a real difference is never reported as a match.
        unparsed = [n for n in present_in if docs.get(n) is None or not docs[n].blocks]
        if unparsed:
            af = self._compare_text(rel_path, "text", present_in, abs_paths, all_nodes)
            af.warnings = warnings + [f"{n}: [CMT-AUD-W010] no SSTP blocks recognised — compared as text"
                                      for n in unparsed] + af.warnings
            return af

        # Build union of all block compounds
        seen_compounds: Dict[str, None] = {}
        for node in present_in:
            doc = docs.get(node)
            if doc is None:
                continue
            for blk in doc.blocks:
                if blk.compound not in seen_compounds:
                    seen_compounds[blk.compound] = None

        params: List[AuditParam] = []
        for compound in seen_compounds:
            # Collect per-node normalised body (used as "value" for comparison)
            values: Dict[str, Optional[str]] = {}
            commented: Dict[str, bool] = {}
            for node in all_nodes:
                if node not in present_in:
                    values[node] = None
                    commented[node] = False
                    continue
                doc = docs.get(node)
                if doc is None:
                    values[node] = None
                    commented[node] = False
                    continue
                blk_map = {b.compound: b for b in doc.blocks}
                b = blk_map.get(compound)
                values[node]   = b.body_norm if b else None
                commented[node] = False

            # Determine mismatch / diff category (absence is tracked separately)
            present_vals = [values[n] for n in present_in if values.get(n) is not None]
            has_mismatch = len(set(present_vals)) > 1

            # Categorise (use first two present nodes)
            diff_category = "MATCH"
            if has_mismatch and len(present_in) >= 2:
                doc_a = docs.get(present_in[0])
                doc_b = docs.get(present_in[1])
                if doc_a and doc_b:
                    map_a = {b.compound: b for b in doc_a.blocks}
                    map_b = {b.compound: b for b in doc_b.blocks}
                    ba    = map_a.get(compound)
                    bb    = map_b.get(compound)
                    if ba and bb:
                        diff_category = categorise_block_diff(ba, bb)
                    elif ba or bb:
                        diff_category = "VALUE_DIFF"

            # STRUCT_EQUIV → logical diff (expected, informational)
            is_logical = (diff_category == "STRUCT_EQUIV")
            if is_logical:
                has_mismatch = False

            # Encode diff category into compound for display
            display_compound = f"{compound}|{diff_category}"
            name = compound.replace("BLOCK|", "")

            params.append(AuditParam(
                compound       = display_compound,
                section        = "SSTP",
                key            = name,
                values         = values,
                commented      = commented,
                has_mismatch   = has_mismatch,
                is_logical_diff = is_logical,
            ))

        mismatch_count     = sum(1 for p in params if p.has_mismatch)
        logical_diff_count = sum(1 for p in params if p.is_logical_diff)
        absent_count       = len(all_nodes) - len(present_in)

        return AuditFile(
            rel_path           = rel_path,
            file_type          = "sstp",
            present_in         = present_in,
            params             = params,
            binary             = {},
            raw_content        = {},
            mismatch_count     = mismatch_count,
            warnings           = warnings,
            logical_diff_count = logical_diff_count,
            absent_count       = absent_count,
        )

    def _compare_kv(self, rel_path: str, present_in: List[str],
                    abs_paths: Dict[str, str],
                    all_nodes: List[str]) -> AuditFile:
        """Section-by-section comparison against the base node (rules: MEMORY.md, 2026-09-15)."""
        docs        : Dict[str, _KVSections] = {}
        raw_content : Dict[str, str]         = {}
        warnings    : List[str]              = []

        for node in present_in:
            try:
                text = open_text(abs_paths[node])  # BUG-B: encoding-aware read
            except OSError as exc:
                warnings.append(f"{node}: [CMT-AUD-W005] read error — {exc}")
                raw_content[node] = ""
                continue
            if len(text.encode("utf-8", errors="replace")) > _MAX_RAW_BYTES:
                raw_content[node] = text[:_MAX_RAW_BYTES]
                warnings.append(
                    f"{node}: [CMT-AUD-W006] raw content truncated at {_MAX_RAW_BYTES // 1024} KB"
                )
            else:
                raw_content[node] = text
            docs[node] = _walk_kv_sections(text)

        # Base node for this file: first node in config order that has (and could read) it
        parsed = [n for n in present_in if n in docs]
        base   = parsed[0] if parsed else ""

        params  : List[AuditParam] = []
        sections: List[dict]       = []

        for sec in _merge_order([docs[n].section_order for n in parsed]):
            holders = [n for n in parsed if sec in docs[n].key_order]
            # A row needs the key active on at least one node
            keys = [
                k for k in _merge_order([docs[n].key_order[sec] for n in holders])
                if any((sec, k) in docs[n].active for n in holders)
            ]
            if sec == KV_DEFAULT_SECTION and not keys:
                continue

            base_has     = base in holders
            counts       = ({n: {"match": 0, "differ": 0, "missing": 0, "extra": 0}
                             for n in holders if n != base} if base_has else {})
            param_counts = {n: 0 for n in holders}
            base_count   = 0

            for key in keys:
                values    : Dict[str, Optional[str]] = {}
                commented : Dict[str, bool]          = {}
                lines     : Dict[str, List[int]]     = {}
                dup_values: Dict[str, List[str]]     = {}
                for node in present_in:
                    doc    = docs.get(node)
                    active = doc.active.get((sec, key)) if doc else None
                    com    = doc.commented.get((sec, key)) if doc else None
                    if active:
                        values[node]    = active[-1][0]
                        commented[node] = False
                        lines[node]     = [ln for _, ln in active]
                        if len(active) > 1:
                            dup_values[node] = [v for v, _ in active]
                    elif com:
                        values[node]    = com[0]
                        commented[node] = True
                        lines[node]     = [com[1]]
                    else:
                        values[node]    = None
                        commented[node] = False

                # A key repeated in one section: the last (second) value is the effective one and
                # is what gets compared; the duplicate itself is only a warning (agreed 2026-09-18).
                for node in dup_values:
                    where = ", ".join(f"L{ln}" for ln in lines[node])
                    warnings.append(f"{node}: '{key}' duplicated in {sec} ({where}) — last value "
                                    f"'{values[node]}' (L{lines[node][-1]}) is used [CMT-AUD-W007]")

                active_vals = {v for n, v in values.items()
                               if not commented[n] and v is not None}
                any_missing = any(v is None for v in values.values())

                params.append(AuditParam(
                    compound     = f"{sec}|{key}",
                    section      = sec,
                    key          = key,
                    values       = values,
                    commented    = commented,
                    has_mismatch = len(active_vals) > 1 or any_missing,
                    lines        = lines,
                    dup_values   = dup_values,
                ))

                for node in holders:
                    if values.get(node) is not None:
                        param_counts[node] += 1
                if base_has:
                    if values.get(base) is not None:
                        base_count += 1
                    for node in counts:
                        kind = _section_check_kind(values, commented, dup_values, base, node)
                        if kind:
                            counts[node][kind] += 1

            sections.append({
                "name":         sec,
                "base":         base,
                "present":      {n: n in holders for n in present_in},
                "base_count":   base_count if base_has else None,
                "counts":       counts,
                "param_counts": param_counts,
            })

        logical_diff_count = self._classify_logical_diffs(params)
        mismatch_count     = sum(1 for p in params if p.has_mismatch)
        absent_count       = len(all_nodes) - len(present_in)

        file_sizes   = self._get_file_sizes(abs_paths)
        skip_content = self._should_skip_content(file_sizes, mismatch_count, absent_count)
        param_count  = len(params)
        if skip_content:
            params      = []
            raw_content = {}

        return AuditFile(
            rel_path           = rel_path,
            file_type          = "kv",
            present_in         = present_in,
            params             = params,
            binary             = {},
            raw_content        = raw_content,
            mismatch_count     = mismatch_count,
            warnings           = warnings,
            logical_diff_count = logical_diff_count,
            absent_count       = absent_count,
            content_skipped    = skip_content,
            param_count        = param_count,
            file_sizes         = file_sizes,
            sections           = sections,
        )

    # ------------------------------------------------------------------
    # JSON comparison
    # ------------------------------------------------------------------

    def _compare_json(self, rel_path: str, present_in: List[str],
                      abs_paths: Dict[str, str],
                      all_nodes: List[str]) -> AuditFile:
        flat       : Dict[str, Dict[str, Optional[str]]] = {}
        key_order  : List[str]      = []
        raw_content: Dict[str, str] = {}
        warnings   : List[str]      = []

        for node in present_in:
            try:
                text = open_text(abs_paths[node])  # BUG-B: encoding-aware read
                raw_content[node] = text
                obj      = json.loads(text)
                flat_map = self._flatten_json(obj)
                for k, v in flat_map.items():
                    if k not in flat:
                        flat[k] = {}
                        key_order.append(k)
                    flat[k][node] = v
            except json.JSONDecodeError as exc:
                warnings.append(f"{node}: [CMT-AUD-W004] invalid JSON — {exc}")
                raw_content.setdefault(node, "")
            except Exception as exc:
                warnings.append(f"{node}: [CMT-AUD-W005] read error — {exc}")
                raw_content.setdefault(node, "")

        params: List[AuditParam] = []
        for dotpath in key_order:
            node_vals = flat[dotpath]
            values: Dict[str, Optional[str]] = {}
            for node in all_nodes:
                if node not in present_in:
                    continue
                values[node] = node_vals.get(node)

            active_vals  = {v for v in values.values() if v is not None}
            any_missing  = any(v is None for v in values.values())
            has_mismatch = len(active_vals) > 1 or any_missing

            params.append(AuditParam(
                compound     = dotpath,
                section      = "",
                key          = dotpath,
                values       = values,
                commented    = {n: False for n in values},
                has_mismatch = has_mismatch,
            ))

        logical_diff_count = self._classify_logical_diffs(params)
        mismatch_count     = sum(1 for p in params if p.has_mismatch)
        absent_count       = len(all_nodes) - len(present_in)

        file_sizes   = self._get_file_sizes(abs_paths)
        skip_content = self._should_skip_content(file_sizes, mismatch_count, absent_count)
        param_count  = len(params)
        if skip_content:
            params      = []
            raw_content = {}

        return AuditFile(
            rel_path           = rel_path,
            file_type          = "json",
            present_in         = present_in,
            params             = params,
            binary             = {},
            raw_content        = raw_content,
            mismatch_count     = mismatch_count,
            warnings           = warnings,
            logical_diff_count = logical_diff_count,
            absent_count       = absent_count,
            content_skipped    = skip_content,
            param_count        = param_count,
            file_sizes         = file_sizes,
        )

    def _flatten_json(self, obj, prefix: str = "") -> Dict[str, str]:
        result: Dict[str, str] = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                full_key = f"{prefix}.{k}" if prefix else k
                result.update(self._flatten_json(v, full_key))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                result.update(self._flatten_json(v, f"{prefix}[{i}]"))
        else:
            result[prefix] = json.dumps(obj)   # BUG-04: canonical bool/null
        return result

    # ------------------------------------------------------------------
    # Text / XML comparison — BUG-01: binary MD5
    # ------------------------------------------------------------------

    def _compare_text(self, rel_path: str, file_type: str,
                      present_in: List[str],
                      abs_paths: Dict[str, str],
                      all_nodes: List[str]) -> AuditFile:
        raw_content: Dict[str, str]          = {}
        md5_vals   : Dict[str, Optional[str]] = {}
        exact_md5  : Dict[str, str]           = {}
        warnings   : List[str]               = []

        for node in all_nodes:
            if node not in abs_paths:
                md5_vals[node] = None
                continue
            try:
                # Use normalised text content for comparison (BUG-B + strip encoding noise)
                text = open_text(abs_paths[node])
                # Normalise: strip BOM artefacts, CRLF→LF, trailing whitespace per line
                norm = "\n".join(ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").splitlines())
                import hashlib as _hl
                exact_md5[node] = _hl.md5(norm.encode("utf-8", errors="replace")).hexdigest()
                # Compared with all whitespace removed: indentation / blank-line differences are
                # not drift (agreed 2026-09-18, same rule as merge whitespace-only files).
                squeezed = "".join(text.split())
                md5_vals[node] = _hl.md5(squeezed.encode("utf-8", errors="replace")).hexdigest()

                if len(text.encode("utf-8", errors="replace")) > _MAX_RAW_BYTES:
                    raw_content[node] = text[:_MAX_RAW_BYTES] + "\n[...truncated...]"
                    warnings.append(f"{node}: [CMT-AUD-W006] display truncated at {_MAX_RAW_BYTES // 1024} KB")
                else:
                    raw_content[node] = text

            except OSError as exc:
                md5_vals[node] = None
                warnings.append(f"{node}: [CMT-AUD-W005] read error — {exc}")

        present_md5s = {v for n, v in md5_vals.items()
                        if n in present_in and v is not None}
        absent_count = len(all_nodes) - len(present_in)
        has_mismatch = len(present_md5s) > 1      # content diff among present nodes only
        mismatch     = 1 if has_mismatch else 0
        if not has_mismatch and len({v for n, v in exact_md5.items() if n in present_in}) > 1:
            warnings.append("whitespace-only differences between nodes ignored [CMT-AUD-I001]")

        param = AuditParam(
            compound     = "__md5__",
            section      = "",
            key          = "File checksum",
            values       = {n: v for n, v in md5_vals.items() if n in all_nodes},
            commented    = {n: False for n in all_nodes},
            has_mismatch = has_mismatch,
        )

        file_sizes   = self._get_file_sizes(abs_paths)
        skip_content = self._should_skip_content(file_sizes, mismatch, absent_count)
        if skip_content:
            raw_content = {}

        return AuditFile(
            rel_path        = rel_path,
            file_type       = file_type,
            present_in      = present_in,
            params          = [] if skip_content else [param],
            binary          = {},
            raw_content     = raw_content,
            mismatch_count  = mismatch,
            warnings        = warnings,
            absent_count    = absent_count,
            content_skipped = skip_content,
            param_count     = 1,
            file_sizes      = file_sizes,
        )
