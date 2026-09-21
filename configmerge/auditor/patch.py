"""
configmerge.auditor.patch
~~~~~~~~~~~~~~~~~~~~~~~~~~
Apply an audit patch (exported from the HTML report) to write corrected
configuration files into an output directory and produce a corrections.log.

Workflow:
  1. User opens audit_report.html and makes corrections.
  2. User clicks "Export Patch" → downloads audit_patch_YYYYMMDD.json.
  3. User runs:
       python3 ConfigMergeTool.py \\
           --apply-audit-patch audit_patch_20260403.json \\
           --output-dir corrections/

  Output structure:
       corrections/
         APP-01/
           config/
             fsmapp.properties   ← corrected file
         APP-02/
           config/
             fsmapp.properties
         corrections.log         ← full change record
         audit_patch.json        ← copy of input patch (for traceability)
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from ..errors import ConfigMergeError, tag
from ..utils import safe_realpath


# ---------------------------------------------------------------------------
# Patch data model (mirrors the JSON exported by the JS)
# ---------------------------------------------------------------------------

class PatchChange:
    __slots__ = ('file', 'file_type', 'node', 'compound', 'key',
                 'section', 'original', 'corrected', 'action')

    def __init__(self, d: dict):
        self.file      = d['file']
        self.file_type = d.get('file_type', 'kv')
        self.node      = d['node']
        self.compound  = d['compound']
        self.key       = d['key']
        self.section   = d.get('section', '')
        self.original  = d.get('original')    # None if key was added
        self.corrected = d['corrected']
        self.action    = d.get('action', 'modified')


# ---------------------------------------------------------------------------
# AuditPatcher
# ---------------------------------------------------------------------------

class AuditPatcher:
    """
    Read an audit patch JSON, apply changes to original source files,
    write corrected copies to output_dir, and produce corrections.log.
    """

    def __init__(self, patch_file: str, output_dir: str = ""):
        self.patch_file = patch_file
        self.output_dir = output_dir  # may be empty; resolved in apply() from patch JSON
        self.issues     = 0           # changes skipped or failed during apply()

    # ------------------------------------------------------------------

    def apply(self) -> int:
        """Apply patch. Returns number of files written; skipped/failed files are counted
        in ``self.issues``.  Raises ConfigMergeError when the patch is invalid or empty."""
        patch      = self._load_patch()
        node_dirs  = patch['node_dirs']
        changes    = []
        for i, raw in enumerate(patch['changes']):
            try:
                changes.append(PatchChange(raw))
            except (KeyError, TypeError, AttributeError) as exc:
                raise ConfigMergeError(
                    "CMT-PAT-E003", f"Patch change #{i} is malformed (missing/invalid {exc})")
        audit_run  = patch.get('audit_run', 'unknown')

        # Resolve output_dir: CLI arg wins → config/patch field → default to run_dir/corrections
        output_dir = self.output_dir or patch.get('output_dir', '').strip()
        if not output_dir:
            run_dir = patch.get('run_dir', '').strip()
            output_dir = os.path.join(run_dir, "corrections") if run_dir else "corrections"
            print(f"[PATCH] No output_dir specified — defaulting to: {output_dir}")

        if not changes:
            raise ConfigMergeError("CMT-PAT-E004", "No changes in patch file — nothing to apply.")

        os.makedirs(output_dir, exist_ok=True)

        # Group changes by (node, file)
        by_node_file: Dict[tuple, List[PatchChange]] = {}
        for c in changes:
            key = (c.node, c.file)
            by_node_file.setdefault(key, []).append(c)

        log_lines = self._log_header(audit_run, len(changes), len(by_node_file), output_dir)
        files_written = 0

        for (node, rel_path), file_changes in sorted(by_node_file.items()):
            file_type = file_changes[0].file_type

            # The node name becomes a directory under output_dir — it must be a plain name
            if not _is_plain_dir_name(node):
                self._issue(log_lines, tag("CMT-PAT-E008",
                    f"[ERROR] Skipping {node!r}/{rel_path}: node name must be a plain directory name"))
                continue

            # Source file path from patch node_dirs
            src_dir = node_dirs.get(node)
            if not src_dir:
                self._issue(log_lines, tag("CMT-PAT-E005",
                    f"[ERROR] Node '{node}' not found in patch node_dirs — skipping"))
                continue

            # Guard against path traversal (e.g. rel_path containing "../")
            if os.path.isabs(rel_path):
                self._issue(log_lines, tag("CMT-PAT-E006",
                    f"[ERROR] Skipping {node}/{rel_path}: rel_path must be relative"))
                continue
            src_path = safe_realpath(src_dir, rel_path)
            dst_path = safe_realpath(os.path.join(output_dir, node), rel_path)
            if src_path is None or dst_path is None:
                self._issue(log_lines, tag("CMT-PAT-E007",
                    f"[ERROR] Skipping {node}/{rel_path}: path traversal detected"))
                continue
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)

            try:
                corrected_text = self._apply_to_file(
                    src_path, rel_path, file_type, node, file_changes
                )
            except Exception as exc:
                self._issue(log_lines, tag("CMT-PAT-E009", f"[ERROR] {node}/{rel_path}: {exc}"))
                continue

            with open(dst_path, "w", encoding="utf-8", newline="") as f:
                f.write(corrected_text)

            files_written += 1
            log_lines.append(f"\n{'─'*80}")
            log_lines.append(f"  Node  : {node}")
            log_lines.append(f"  File  : {rel_path}")
            log_lines.append(f"  Source: {src_path}")
            log_lines.append(f"  Output: {dst_path}")
            log_lines.append(f"  Changes ({len(file_changes)}):")

            for c in file_changes:
                key_label = (f"[{c.section}]|" if c.section else "") + c.key
                orig_str  = c.original if c.original is not None else "<missing>"
                log_lines.append(f"    [{c.action.upper():<8}]  {key_label}")
                log_lines.append(f"             Original : {orig_str}")
                log_lines.append(f"             Corrected: {c.corrected}")

            print(f"[PATCH] Written: {dst_path}  ({len(file_changes)} change(s))")

        # Write corrections.log alongside the audit report (run_dir), not inside output_dir.
        # output_dir contains only corrected config files — nothing else.
        run_dir = patch.get('run_dir', '').strip()
        log_dir = run_dir if run_dir and os.path.isdir(run_dir) else output_dir
        log_path = os.path.join(log_dir, "corrections.log")
        log_lines.append(f"\n{'─'*80}")
        log_lines.append(f"TOTAL: {files_written} file(s) written to {output_dir}")
        with open(log_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(log_lines) + "\n")

        print(f"[PATCH] corrections.log → {log_path}")
        print(f"[PATCH] {files_written} file(s) written to {output_dir}")
        return files_written

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_patch(self) -> dict:
        try:
            with open(self.patch_file, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigMergeError("CMT-PAT-E001", f"Cannot read patch file {self.patch_file!r}: {exc}")
        if not isinstance(data, dict):
            raise ConfigMergeError("CMT-PAT-E002", "Patch JSON must be an object")
        for field in ('node_dirs', 'changes'):
            if field not in data:
                raise ConfigMergeError("CMT-PAT-E002", f"Patch JSON missing field '{field}'")
        return data

    def _issue(self, log_lines: List[str], msg: str) -> None:
        self.issues += 1
        print(msg)
        log_lines.append(msg)

    def _log_header(self, audit_run: str, n_changes: int, n_files: int,
                    output_dir: str) -> List[str]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return [
            "ConfigMergeTool — Audit Correction Log",
            f"{'─'*80}",
            f"  Audit run    : {audit_run}",
            f"  Applied at   : {now}",
            f"  Patch file   : {self.patch_file}",
            f"  Output dir   : {output_dir}",
            f"  Total changes: {n_changes} across {n_files} node/file pair(s)",
            f"{'─'*80}",
        ]

    def _apply_to_file(self, src_path: str, rel_path: str, file_type: str,
                       node: str, changes: List[PatchChange]) -> str:
        """Read the source file and apply the given changes, returning corrected text."""
        if not os.path.exists(src_path):
            # File absent on this node — build from scratch using 'added' changes
            if file_type == 'kv':
                return self._build_kv_from_scratch(changes)
            raise FileNotFoundError(f"Source file not found: {src_path}")

        with open(src_path, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()

        if file_type == 'kv':
            return self._apply_kv(text, changes)
        elif file_type == 'json':
            return self._apply_json(text, changes)
        else:
            # xml / text — return as-is with a comment header (binary handled by caller)
            return text

    # ── KV application ─────────────────────────────────────────────────

    def _apply_kv(self, raw: str, changes: List[PatchChange]) -> str:
        # Build a lookup: compound -> corrected_value
        change_map: Dict[str, str] = {c.compound: c.corrected for c in changes}
        # Track which compound keys have been applied
        modified: set = set()

        lines          = raw.split('\n')
        currentSection = 'DEFAULT'

        for i, line in enumerate(lines):
            stripped = line.strip()
            sm = re.match(r'^\[([^\]]+)\]$', stripped)
            if sm:
                currentSection = f"[{sm.group(1)}]"
                continue
            if stripped.startswith('#') or stripped.startswith('!') or not stripped:
                continue

            # Detect delimiter
            ei = stripped.find('=')
            ci = stripped.find(':')
            if ei >= 0 and (ci < 0 or ei <= ci):
                di, delim = ei, '='
            elif ci >= 0:
                di, delim = ci, ':'
            else:
                continue

            key = stripped[:di].strip()
            if not key:
                continue
            # NOTE: keys with embedded whitespace (e.g. shell-script lines like
            #   "nohup java -Dapp=value") are valid KV compounds in the audit
            #   engine — do NOT skip them; replace the value in-place.

            compound = f"{currentSection}|{key}"
            if compound in change_map:
                line_delim_pos = line.find(delim)
                new_value = change_map[compound]
                # BUG-F: detect and preserve any trailing inline comment
                # Heuristic: first ' #' or ' ;' occurrence after the delimiter
                after_delim = line[line_delim_pos + 1:]
                inline_comment = ""
                for marker in (" #", " ;"):
                    idx = after_delim.find(marker)
                    if idx >= 0:
                        inline_comment = after_delim[idx:]
                        break
                lines[i] = line[:line_delim_pos + 1] + new_value + inline_comment
                modified.add(compound)

        # Fallback for 'modified' changes whose compound wasn't matched above
        # (can happen when the line's key structure doesn't survive the delimiter
        # scan — e.g. the line was commented out).  Try a direct value-match
        # substitution using the known original value.
        for c in changes:
            if c.action != 'modified' or c.compound in modified:
                continue
            if not c.original:
                continue
            orig_stripped = c.original.strip()
            for i, line in enumerate(lines):
                s = line.strip()
                if s.startswith('#') or s.startswith('!') or not s:
                    continue
                for delim in ('=', ':'):
                    if delim in s:
                        _, _, val_part = s.partition(delim)
                        if val_part.strip() == orig_stripped:
                            dpos = line.find(delim)
                            lines[i] = line[:dpos + 1] + c.corrected
                            modified.add(c.compound)
                        break

        # Append genuinely new keys (file is absent on this node — action='added').
        # Do NOT append 'modified' changes that were not matched; the line exists
        # in the file but could not be located — appending would duplicate it.
        adds_by_sec: Dict[str, List[PatchChange]] = {}
        for c in changes:
            if c.action == 'added' and c.compound not in modified:
                sec = c.section or 'DEFAULT'
                adds_by_sec.setdefault(sec, []).append(c)

        if adds_by_sec:
            lines.append('')
            for sec, entries in adds_by_sec.items():
                if sec != 'DEFAULT':
                    lines.append(sec)
                for c in entries:
                    lines.append(f"{c.key}={c.corrected}")

        return '\n'.join(lines)

    def _build_kv_from_scratch(self, changes: List[PatchChange]) -> str:
        """Build a KV file from scratch when the original doesn't exist."""
        by_sec: Dict[str, List[PatchChange]] = {}
        for c in changes:
            sec = c.section or 'DEFAULT'
            by_sec.setdefault(sec, []).append(c)

        lines = []
        for sec, entries in by_sec.items():
            lines.append('')
            if sec != 'DEFAULT':
                lines.append(sec)
            for c in entries:
                lines.append(f"{c.key}={c.corrected}")
        return '\n'.join(lines) + '\n'

    # ── JSON application ────────────────────────────────────────────────

    def _apply_json(self, raw: str, changes: List[PatchChange]) -> str:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return raw

        for c in changes:
            parts = c.compound.split('.')
            cur   = obj
            for part in parts[:-1]:
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    cur = None
                    break
            if cur is None:
                continue
            last = parts[-1]
            if isinstance(cur, dict):
                # Attempt to preserve original type
                orig_val = cur.get(last)
                if isinstance(orig_val, bool):
                    cur[last] = c.corrected.lower() in ('true', '1', 'yes')
                elif isinstance(orig_val, int):
                    try:
                        cur[last] = int(c.corrected)
                    except ValueError:
                        cur[last] = c.corrected
                elif isinstance(orig_val, float):
                    try:
                        cur[last] = float(c.corrected)
                    except ValueError:
                        cur[last] = c.corrected
                else:
                    cur[last] = c.corrected

        return json.dumps(obj, indent=2, ensure_ascii=False) + '\n'


def _is_plain_dir_name(name: str) -> bool:
    """True for a single path component such as ``APP-01`` (no separators, not ``.``/``..``)."""
    seps = {"/", "\\", os.sep} | ({os.altsep} if os.altsep else set())
    return bool(name) and name not in (".", "..") and not any(sep in name for sep in seps)
