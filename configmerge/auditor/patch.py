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
import shutil
from datetime import datetime
from typing import Dict, List, Optional


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

    def __init__(self, patch_file: str, output_dir: str):
        self.patch_file = patch_file
        self.output_dir = output_dir

    # ------------------------------------------------------------------

    def apply(self) -> int:
        """Apply patch. Returns number of files written."""
        patch      = self._load_patch()
        node_dirs  = patch['node_dirs']
        changes    = [PatchChange(c) for c in patch['changes']]
        audit_run  = patch.get('audit_run', 'unknown')

        if not changes:
            print("[PATCH] No changes in patch file — nothing to do.")
            return 0

        os.makedirs(self.output_dir, exist_ok=True)

        # Group changes by (node, file)
        by_node_file: Dict[tuple, List[PatchChange]] = {}
        for c in changes:
            key = (c.node, c.file)
            by_node_file.setdefault(key, []).append(c)

        log_lines = self._log_header(audit_run, len(changes), len(by_node_file))
        files_written = 0

        for (node, rel_path), file_changes in sorted(by_node_file.items()):
            file_type = file_changes[0].file_type

            # Source file path from patch node_dirs
            src_dir = node_dirs.get(node)
            if not src_dir:
                warn = f"[WARN] Node '{node}' not found in patch node_dirs — skipping"
                print(warn)
                log_lines.append(warn)
                continue

            src_path = os.path.join(src_dir, rel_path)
            dst_path = os.path.join(self.output_dir, node, rel_path)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)

            try:
                corrected_text = self._apply_to_file(
                    src_path, rel_path, file_type, node, file_changes
                )
            except Exception as exc:
                warn = f"[ERROR] {node}/{rel_path}: {exc}"
                print(warn)
                log_lines.append(warn)
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

        # Write corrections.log
        log_path = os.path.join(self.output_dir, "corrections.log")
        log_lines.append(f"\n{'─'*80}")
        log_lines.append(f"TOTAL: {files_written} file(s) written to {self.output_dir}")
        with open(log_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(log_lines) + "\n")

        # Copy the patch JSON for traceability
        patch_copy = os.path.join(self.output_dir, "audit_patch.json")
        shutil.copy2(self.patch_file, patch_copy)

        print(f"[PATCH] corrections.log → {log_path}")
        print(f"[PATCH] {files_written} file(s) written")
        return files_written

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_patch(self) -> dict:
        try:
            with open(self.patch_file, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"[ERROR] Cannot read patch file {self.patch_file!r}: {exc}")
        required = ('node_dirs', 'changes')
        for r in required:
            if r not in data:
                raise SystemExit(f"[ERROR] Patch JSON missing field '{r}'")
        return data

    def _log_header(self, audit_run: str, n_changes: int, n_files: int) -> List[str]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return [
            "ConfigMergeTool — Audit Correction Log",
            f"{'─'*80}",
            f"  Audit run    : {audit_run}",
            f"  Applied at   : {now}",
            f"  Patch file   : {self.patch_file}",
            f"  Output dir   : {self.output_dir}",
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
        # Track which compound keys have been seen in existing lines
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
            if not key or re.search(r'\s', key):
                continue

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

        # Append newly added keys (not found in existing file)
        adds_by_sec: Dict[str, List[PatchChange]] = {}
        for c in changes:
            if c.action == 'added' and c.compound not in modified:
                sec = c.section or 'DEFAULT'
                adds_by_sec.setdefault(sec, []).append(c)

        if adds_by_sec:
            lines.append('')
            lines.append('# Added by ConfigMergeTool Audit')
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

        lines = ['# Generated by ConfigMergeTool Audit']
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
