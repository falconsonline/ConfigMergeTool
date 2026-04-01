"""
configmerge.processors.kv
~~~~~~~~~~~~~~~~~~~~~~~~~
Key-Value processor (.cfg, .ini, .conf, .properties, .sh)

Merge strategy (per section):
  1. Walk base entries in definition order.
     - For each base entry check if release has same key:
       * YES → take base value, base comment-state (commented/uncommented),
               use release comments if present else base comments.
       * NO  → insert as BASE_ONLY_PARAMETER_ADDED (unless --exclude-base-only).
  2. Append release-only entries (not in base) as RELEASE_ONLY_PARAMETER_ADDED.
  3. Indexed groups (prefix.N.subkey): base groups retained; release-only groups
     appended with continuing sequence numbers.
  4. Comma-separated header params: union of base + release unique values.
  5. Duplicate tracking: last value wins; all duplicates reported.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from . import register, BaseProcessor
from ..models import MergeConfig, ReportEntry, EntryType
from ..logger import log_structured
from ..utils import ensure_dir

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class KVEntry:
    section: str
    key: str
    value: str
    is_commented: bool          # True if this line is commented out in source
    comments: List[str]         # comment/blank lines immediately above
    delimiter: str              # '=' or ':'
    line_number: int
    raw_line: str               # original line (used for no-change pass-through)


@dataclass
class KVDocument:
    # section → ordered list of entries (insertion-ordered dict, Python 3.7+)
    sections: "Dict[str, List[KVEntry]]" = field(default_factory=dict)
    section_order: List[str] = field(default_factory=list)

    # duplicate tracking: compound_key → [all values seen]
    duplicate_map: Dict[str, List[str]] = field(default_factory=dict)

    # indexed group detection (set after parse via detect_groups)
    # section → prefix → { N: [KVEntry] }
    indexed_groups: Dict[str, Dict[str, Dict[int, List[KVEntry]]]] = field(
        default_factory=dict
    )
    # section → prefix → [header KVEntry]  (e.g. schedule.count, schedule.registry)
    group_headers: Dict[str, Dict[str, List[KVEntry]]] = field(
        default_factory=dict
    )
    # compound_key → KVEntry  (fast lookup)
    lookup: Dict[str, KVEntry] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_GROUP_KEY_RE = re.compile(r'^([\w.]+)\.(\d+)\.(.+)$')


def parse_kv_doc(file_path: str) -> KVDocument:
    doc = KVDocument()
    current_section = "DEFAULT"
    doc.sections[current_section] = []
    doc.section_order.append(current_section)

    comment_buffer: List[str] = []
    lineno = 0

    with open(file_path, encoding="utf-8-sig") as f:  # utf-8-sig strips BOM if present
        for line in f:
            lineno += 1
            stripped = line.rstrip("\n")

            # ── Section header ──────────────────────────────────────────
            m_sec = re.match(r'^\s*\[(.+)\]\s*$', stripped)
            if m_sec:
                current_section = f"[{m_sec.group(1)}]"
                if current_section not in doc.sections:
                    doc.sections[current_section] = []
                    doc.section_order.append(current_section)
                comment_buffer = []
                continue

            # ── Comment / blank ─────────────────────────────────────────
            if stripped.strip() == "" or stripped.strip().startswith("#") or stripped.strip().startswith("!"):
                # Could be a commented-out key — check
                stripped_inner = stripped.strip().lstrip("#!").strip()
                if _is_kv_line(stripped_inner):
                    # This is a commented key — parse as entry with is_commented=True
                    key, value, delim = _split_kv(stripped_inner)
                    if key:
                        compound = f"{current_section}|{key}"
                        entry = KVEntry(
                            section=current_section,
                            key=key,
                            value=value,
                            is_commented=True,
                            comments=comment_buffer[:],
                            delimiter=delim,
                            line_number=lineno,
                            raw_line=line,
                        )
                        doc.sections[current_section].append(entry)
                        _track_duplicate(doc, compound, value)
                        doc.lookup[compound] = entry
                        comment_buffer = []
                        continue
                # plain comment or blank → buffer
                comment_buffer.append(line)
                continue

            # ── Real key-value ──────────────────────────────────────────
            if _is_kv_line(stripped):
                key, value, delim = _split_kv(stripped)
                if key:
                    compound = f"{current_section}|{key}"
                    entry = KVEntry(
                        section=current_section,
                        key=key,
                        value=value,
                        is_commented=False,
                        comments=comment_buffer[:],
                        delimiter=delim,
                        line_number=lineno,
                        raw_line=line,
                    )
                    doc.sections[current_section].append(entry)
                    _track_duplicate(doc, compound, value)
                    doc.lookup[compound] = entry
                    comment_buffer = []
                    continue

            # ── Unrecognised ────────────────────────────────────────────
            comment_buffer = []

    _detect_groups(doc)
    return doc


def _is_kv_line(s: str) -> bool:
    return "=" in s or ":" in s


def _split_kv(s: str) -> Tuple[str, str, str]:
    """Split 'key = value' or 'key: value'. Returns (key, value, delimiter)."""
    for delim in ("=", ":"):
        if delim in s:
            k, v = s.split(delim, 1)
            return k.strip(), v.strip(), delim
    return "", "", "="


def _track_duplicate(doc: KVDocument, compound: str, value: str) -> None:
    if compound not in doc.duplicate_map:
        doc.duplicate_map[compound] = []
    doc.duplicate_map[compound].append(value)


def _detect_groups(doc: KVDocument) -> None:
    """
    Identify indexed groups: keys matching prefix.N.subkey  (e.g. schedule.1.name).
    Group header params match prefix.word (no numeric middle), e.g. schedule.count.
    """
    for section, entries in doc.sections.items():
        groups: Dict[str, Dict[int, List[KVEntry]]] = defaultdict(lambda: defaultdict(list))
        headers: Dict[str, List[KVEntry]] = defaultdict(list)

        for entry in entries:
            m = _GROUP_KEY_RE.match(entry.key)
            if m:
                prefix, idx_str, _ = m.group(1), m.group(2), m.group(3)
                groups[prefix][int(idx_str)].append(entry)
            else:
                # Check if it looks like a group header  prefix.word
                parts = entry.key.split(".")
                if len(parts) >= 2:
                    # heuristic: if there are any numeric-indexed keys for this prefix in this section
                    prefix_candidate = ".".join(parts[:-1])
                    headers[prefix_candidate].append(entry)

        if groups:
            doc.indexed_groups[section] = {k: dict(v) for k, v in groups.items()}
            doc.group_headers[section] = dict(headers)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def merge_kv(
    base_doc: KVDocument,
    rel_doc: KVDocument,
    rel_file: str,
    config: MergeConfig,
    logger: logging.Logger,
) -> Tuple[List[str], List[ReportEntry]]:
    """
    Produce merged output lines and report entries.
    """
    report: List[ReportEntry] = []
    out_lines: List[str] = []

    all_sections = list(
        dict.fromkeys(base_doc.section_order + rel_doc.section_order)
    )

    for section in all_sections:
        # emit section header
        if section != "DEFAULT":
            out_lines.append(f"{section}\n")

        base_entries  = base_doc.sections.get(section, [])
        rel_entries   = rel_doc.sections.get(section, [])
        base_groups   = (base_doc.indexed_groups or {}).get(section, {})
        rel_groups    = (rel_doc.indexed_groups  or {}).get(section, {})
        base_headers  = (base_doc.group_headers  or {}).get(section, {})
        rel_headers   = (rel_doc.group_headers   or {}).get(section, {})

        emitted_keys = set()   # track compound keys already written

        # ── 1. Indexed group prefixes ────────────────────────────────
        all_prefixes = set(base_groups) | set(rel_groups)
        for prefix in sorted(all_prefixes):
            b_groups = base_groups.get(prefix, {})
            r_groups = rel_groups.get(prefix, {})

            # 1a. Group header params (e.g. schedule.count, schedule.registry)
            for hdr_entry in base_headers.get(prefix, []):
                compound = f"{section}|{hdr_entry.key}"
                rel_hdr  = rel_doc.lookup.get(compound)
                merged_value, merged_comments, rpt = _merge_single_entry(
                    hdr_entry, rel_hdr, rel_file, config, section
                )
                # Special: comma-separated union
                if rel_hdr and "," in (hdr_entry.value + rel_hdr.value):
                    merged_value, rpt_csv = _csv_union(
                        hdr_entry, rel_hdr, rel_file, section
                    )
                    if rpt_csv:
                        report.append(rpt_csv)
                        rpt = None
                if rpt:
                    report.append(rpt)
                _emit_entry(out_lines, hdr_entry, merged_value, merged_comments)
                emitted_keys.add(compound)

            # 1b. Base groups — retain in original order
            max_base_idx = max(b_groups.keys(), default=0)
            for idx in sorted(b_groups.keys()):
                for entry in b_groups[idx]:
                    compound = f"{section}|{entry.key}"
                    rel_entry = rel_doc.lookup.get(compound)
                    merged_value, merged_comments, rpt = _merge_single_entry(
                        entry, rel_entry, rel_file, config, section
                    )
                    if rpt:
                        report.append(rpt)
                    _emit_entry(out_lines, entry, merged_value, merged_comments)
                    emitted_keys.add(compound)

            # 1c. Release-only groups — append renumbered
            next_idx = max_base_idx + 1
            for r_idx in sorted(r_groups.keys()):
                # skip if this group index existed in base (already handled)
                if r_idx in b_groups:
                    continue
                for entry in r_groups[r_idx]:
                    # renumber the key
                    new_key = re.sub(
                        rf'^({re.escape(prefix)}\.)(\d+)(\.)',
                        lambda m, ni=next_idx: f"{m.group(1)}{ni}{m.group(3)}",
                        entry.key,
                    )
                    compound = f"{section}|{new_key}"
                    comments = entry.comments[:]
                    _emit_raw_entry(out_lines, new_key, entry.value,
                                    entry.delimiter, entry.is_commented, comments)
                    emitted_keys.add(f"{section}|{entry.key}")
                    emitted_keys.add(compound)
                    report.append(ReportEntry(
                        type=EntryType.INDEXED_GROUP_APPENDED,
                        file=rel_file,
                        element=f"{section}|{new_key}",
                        old=f"release index {r_idx}",
                        new=f"merged index {next_idx}",
                        section=section,
                    ))
                next_idx += 1

        # ── 2. Regular params (non-indexed) ──────────────────────────
        # Walk base entries first
        for entry in base_entries:
            compound = f"{section}|{entry.key}"
            if compound in emitted_keys:
                continue
            rel_entry = rel_doc.lookup.get(compound)
            merged_value, merged_comments, rpt = _merge_single_entry(
                entry, rel_entry, rel_file, config, section
            )
            if rpt:
                report.append(rpt)
            _emit_entry(out_lines, entry, merged_value, merged_comments)
            emitted_keys.add(compound)

        # Append release-only entries
        for entry in rel_entries:
            compound = f"{section}|{entry.key}"
            if compound in emitted_keys:
                continue
            if base_doc.lookup.get(compound):
                continue   # already handled above
            _emit_entry(out_lines, entry, entry.value, entry.comments)
            emitted_keys.add(compound)
            report.append(ReportEntry(
                type=EntryType.RELEASE_ONLY_PARAMETER_ADDED,
                file=rel_file,
                element=compound,
                old=entry.value,
                new=entry.value,
                section=section,
            ))

        out_lines.append("\n")   # blank line between sections

    return out_lines, report


def _merge_single_entry(
    base_entry: KVEntry,
    rel_entry: Optional[KVEntry],
    rel_file: str,
    config: MergeConfig,
    section: str,
) -> Tuple[str, List[str], Optional[ReportEntry]]:
    """
    Return (merged_value, merged_comments, optional_report_entry).
    Comment state (commented/uncommented) always follows base.
    Comments: prefer release comments if present, else base comments.
    """
    compound = f"{section}|{base_entry.key}"

    if rel_entry is None:
        # Base-only
        if config.exclude_base_only:
            return base_entry.value, base_entry.comments, ReportEntry(
                type=EntryType.EXCLUDED_BASE_ONLY_PARAMETER,
                file=rel_file,
                element=compound,
                old="",
                new=base_entry.value,
                section=section,
            )
        return base_entry.value, base_entry.comments, ReportEntry(
            type=EntryType.BASE_ONLY_PARAMETER_ADDED,
            file=rel_file,
            element=compound,
            old="",
            new=base_entry.value,
            base_comment="\n".join(base_entry.comments),
            section=section,
        )

    # Choose comments: release preferred if non-empty, else base
    if rel_entry.comments:
        merged_comments = rel_entry.comments
    else:
        merged_comments = base_entry.comments

    release_val = rel_entry.value

    # Empty base override
    if base_entry.value.strip() == "" and not base_entry.is_commented:
        rpt = ReportEntry(
            type=EntryType.EMPTY_BASE_OVERRIDE,
            file=rel_file,
            element=compound,
            old=release_val,
            new="",
            recommended=release_val,
            base_comment="\n".join(base_entry.comments),
            release_comment="\n".join(rel_entry.comments),
            section=section,
        )
        return "", merged_comments, rpt

    # Values differ
    if base_entry.value != release_val:
        rpt = ReportEntry(
            type=EntryType.BASE_TO_RELEASE_REPLACED,
            file=rel_file,
            element=compound,
            old=release_val,
            new=base_entry.value,
            base_comment="\n".join(base_entry.comments),
            release_comment="\n".join(rel_entry.comments),
            section=section,
        )
        return base_entry.value, merged_comments, rpt

    # No change
    return base_entry.value, merged_comments, None


def _csv_union(
    base_entry: KVEntry,
    rel_entry: KVEntry,
    rel_file: str,
    section: str,
) -> Tuple[str, Optional[ReportEntry]]:
    """Union comma-separated values: base first, then release-only additions."""
    base_vals = [v.strip() for v in base_entry.value.split(",") if v.strip()]
    rel_vals  = [v.strip() for v in rel_entry.value.split(",")  if v.strip()]
    added     = [v for v in rel_vals if v not in base_vals]
    merged    = base_vals + added
    merged_str = ",".join(merged)

    if added:
        rpt = ReportEntry(
            type=EntryType.COMMA_VALUE_UNION,
            file=rel_file,
            element=f"{section}|{base_entry.key}",
            old=rel_entry.value,
            new=merged_str,
            section=section,
        )
        return merged_str, rpt
    return base_entry.value, None


def _emit_entry(
    out_lines: List[str],
    entry: KVEntry,
    value: str,
    comments: List[str],
) -> None:
    for c in comments:
        out_lines.append(c if c.endswith("\n") else c + "\n")
    key_line = f"{entry.key}{entry.delimiter}{value}"
    if entry.is_commented:
        key_line = f"#{key_line}"
    out_lines.append(key_line + "\n")


def _emit_raw_entry(
    out_lines: List[str],
    key: str,
    value: str,
    delimiter: str,
    is_commented: bool,
    comments: List[str],
) -> None:
    for c in comments:
        out_lines.append(c if c.endswith("\n") else c + "\n")
    key_line = f"{key}{delimiter}{value}"
    if is_commented:
        key_line = f"#{key_line}"
    out_lines.append(key_line + "\n")


# ---------------------------------------------------------------------------
# Duplicate reporting helper
# ---------------------------------------------------------------------------

def _report_duplicates(
    doc: KVDocument, rel_file: str
) -> List[ReportEntry]:
    entries = []
    for compound, values in doc.duplicate_map.items():
        if len(values) > 1:
            entries.append(ReportEntry(
                type=EntryType.DUPLICATE_KEY,
                file=rel_file,
                element=compound,
                old=" | ".join(values[:-1]),
                new=values[-1],
            ))
    return entries


# ---------------------------------------------------------------------------
# Processor class
# ---------------------------------------------------------------------------

@register(".cfg", ".ini", ".conf", ".properties", ".sh")
class KVProcessor(BaseProcessor):

    def process(
        self,
        base_files: List[str],
        rel_file: str,
        out_file: str,
        config: MergeConfig,
        logger: logging.Logger,
    ) -> List[ReportEntry]:
        logger.info(f"[KV] {rel_file}")
        report: List[ReportEntry] = []

        # For Many-to-One: merge base files sequentially (first base is master,
        # subsequent bases add extra keys not already seen)
        base_doc = parse_kv_doc(base_files[0])
        for extra_base in base_files[1:]:
            extra_doc = parse_kv_doc(extra_base)
            for section, entries in extra_doc.sections.items():
                if section not in base_doc.sections:
                    base_doc.sections[section] = []
                    base_doc.section_order.append(section)
                for entry in entries:
                    compound = f"{section}|{entry.key}"
                    if compound not in base_doc.lookup:
                        base_doc.sections[section].append(entry)
                        base_doc.lookup[compound] = entry
        # Re-run group detection after merging all base files
        if len(base_files) > 1:
            base_doc.indexed_groups.clear()
            base_doc.group_headers.clear()
            _detect_groups(base_doc)

        rel_doc = parse_kv_doc(rel_file)

        # Duplicate reporting
        report.extend(_report_duplicates(base_doc, rel_file))
        report.extend(_report_duplicates(rel_doc, rel_file))

        out_lines, merge_report = merge_kv(base_doc, rel_doc, rel_file, config, logger)
        report.extend(merge_report)

        # Separate excluded params from the main report
        excluded = [r for r in report if r.type == EntryType.EXCLUDED_BASE_ONLY_PARAMETER]
        report   = [r for r in report if r.type != EntryType.EXCLUDED_BASE_ONLY_PARAMETER]

        if not config.dry_run:
            ensure_dir(out_file)
            with open(out_file, "w", encoding="utf-8") as f:
                f.writelines(out_lines)

        # Attach excluded back so engine can route them to MergeResult.excluded_params
        report.extend(excluded)
        return report
