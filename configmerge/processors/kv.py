"""
configmerge.processors.kv
~~~~~~~~~~~~~~~~~~~~~~~~~
Key-Value processor (.cfg, .ini, .conf, .properties, .sh)

Merge strategy (per section):
  1. Walk release spine in order.  Group entries are emitted per-index,
     on-demand, when the release spine first encounters an entry for that
     index.  This preserves the exact interleaved ordering found in the
     release file.
  2. For each regular param on the release spine:
     - If also in base (active) → take base value, base comment-state,
       release comments if present else base comments.
     - If only in release → emit as-is (RELEASE_ONLY_PARAMETER_ADDED).
  3. Base-only params are anchored to appear just before the release entry
     that follows them in the base file.
  4. Base annotations (commented base entry whose key is also active in base)
     are emitted verbatim just before the corresponding active merged entry,
     but ONLY if the release does not already supply an annotation for that key.
  5. Release annotations (commented release entry whose key is also active in
     release) are emitted verbatim before the active entry.
  6. Indexed groups: base groups retained; release-only groups appended
     (renumbered) at their natural release-file position.
  7. Group header params (schedule.count, schedule.registry etc.) are emitted
     at their natural release-file position without triggering early group emission.
  8. Duplicate tracking: last active value wins; all active duplicates reported.
     Commented entries are never counted as duplicates (they are annotations).
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from . import register, BaseProcessor
from ..models import MergeConfig, ReportEntry, EntryType
from ..logger import log_structured
from ..utils import ensure_dir, open_text, detect_api_version_upgrade, is_java_fqcn

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

    # BUG-I: section → original raw header line (e.g. "[App]  # main\n")
    # so it can be emitted verbatim instead of reconstructed as f"{section}\n"
    section_raw_lines: Dict[str, str] = field(default_factory=dict)

    # Comments (blank/comment lines) that appear BEFORE a section header.
    # These would otherwise be lost when comment_buffer is cleared on section entry.
    section_preamble: Dict[str, List[str]] = field(default_factory=dict)

    # Comments / unrecognised lines that appear after the last KV entry of a section
    # (or the entire file when no KV entries exist at all).  Emitted verbatim after
    # all entries of that section have been output.
    section_trailing: Dict[str, List[str]] = field(default_factory=dict)

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
    # compound_key → KVEntry  (fast lookup — prefers active over commented)
    lookup: Dict[str, KVEntry] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_GROUP_KEY_RE = re.compile(r'^([\w.]+)\.(\d+)\.(.+)$')

# Review annotations written by this tool into merged output — never read back as content.
_REVIEW_ANNOTATION_RE = re.compile(r'^\s*#\s*\[CMT-[A-Z]{3}-[EWI]\d{3}\] REVIEW:')


def parse_kv_doc(file_path: str, known_keys: Optional[Set[str]] = None) -> KVDocument:
    """Parse a KV file.  *known_keys* (active keys of the files being merged) lets a commented
    line with spaces around its key (``#key = value``) be recognised as a commented parameter;
    without it only ``#key=value``-style commented keys are recognised."""
    doc = KVDocument()
    current_section = "DEFAULT"
    doc.sections[current_section] = []
    doc.section_order.append(current_section)

    comment_buffer: List[str] = []
    lineno = 0

    # BUG-B: use encoding-aware reader (utf-8-sig → chardet → latin-1 fallback)
    _raw_text = open_text(file_path)
    for line in _raw_text.splitlines(keepends=True):
            lineno += 1
            stripped = line.rstrip("\n")

            # ── Section header ──────────────────────────────────────────
            m_sec = re.match(r'^\s*\[(.+)\]\s*(?:#.*)?$', stripped)
            if m_sec and stripped.lstrip().startswith('['):
                current_section = f"[{m_sec.group(1).strip()}]"
                if current_section not in doc.sections:
                    doc.sections[current_section] = []
                    doc.section_order.append(current_section)
                    # BUG-I: store original raw line for verbatim emission
                    doc.section_raw_lines[current_section] = line
                    # Preserve comments that appeared before this section header;
                    # they would be lost when comment_buffer is cleared below.
                    if comment_buffer:
                        doc.section_preamble[current_section] = comment_buffer[:]
                comment_buffer = []
                continue

            # ── Comment / blank ─────────────────────────────────────────
            if stripped.strip() == "" or stripped.strip().startswith("#") or stripped.strip().startswith("!"):
                if _REVIEW_ANNOTATION_RE.match(stripped):
                    continue
                # Could be a commented-out key — check
                stripped_inner = stripped.strip().lstrip("#!").strip()

                # Check for commented-out section header: #[SectionName]
                m_csec = re.match(r'^\[(.+)\]\s*$', stripped_inner)
                if m_csec:
                    current_section = f"#[{m_csec.group(1)}]"
                    if current_section not in doc.sections:
                        doc.sections[current_section] = []
                        doc.section_order.append(current_section)
                    comment_buffer = []
                    continue

                if _is_kv_line(stripped_inner) and (
                        _has_valid_kv_key(stripped_inner)
                        or (known_keys and _split_kv(stripped_inner)[0] in known_keys)):
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
                        # Commented entries are NOT tracked as duplicates — a commented
                        # key alongside an active key is an annotation, not a conflict.
                        # Only update lookup with commented entry if no active entry
                        # exists yet for this compound (active entries always win).
                        if compound not in doc.lookup or doc.lookup[compound].is_commented:
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
                    # Active entry always overwrites lookup (active beats commented).
                    doc.lookup[compound] = entry
                    comment_buffer = []
                    continue

            # ── Unrecognised ────────────────────────────────────────────
            # Preserve the line verbatim — it will attach to the next KV entry
            # as a comment, or be stored as section trailing content if no
            # further KV entry appears (e.g. comma-delimited data lines).
            comment_buffer.append(line)

    # Any comment/unrecognised lines remaining after the last KV entry are
    # stored as trailing content for the current section so they can be emitted.
    if comment_buffer:
        doc.section_trailing[current_section] = comment_buffer[:]

    _detect_groups(doc)
    return doc


def _is_kv_line(s: str) -> bool:
    return "=" in s or ":" in s


def _comma_union(base_val: str, rel_val: str) -> str:
    """Base items in base order, then release items the base lacks.  Keeps the release separator."""
    sep = ", " if ", " in rel_val else ","
    items = [i.strip() for i in base_val.split(",")]
    items += [i for i in (r.strip() for r in rel_val.split(",")) if i not in items]
    return sep.join(items)


def _match_groups(
    prefix: str,
    b_grps: Dict[int, List["KVEntry"]],
    r_grps: Dict[int, List["KVEntry"]],
) -> Dict[int, int]:
    """Map release group index → base group index.

    Groups are identified by their active ``<prefix>.<N>.name`` value when every base and
    release group has one and names are unique on each side; otherwise by index.
    """
    def names(grps: Dict[int, List["KVEntry"]]) -> Optional[Dict[str, int]]:
        found: Dict[str, int] = {}
        for idx, entries in grps.items():
            name = next((e.value.strip() for e in entries
                         if not e.is_commented and e.key == f"{prefix}.{idx}.name"), None)
            if not name or name in found:
                return None
            found[name] = idx
        return found

    b_names, r_names = names(b_grps), names(r_grps)
    if b_grps and r_grps and b_names is not None and r_names is not None:
        return {r_idx: b_names[name] for name, r_idx in r_names.items() if name in b_names}
    return {r_idx: r_idx for r_idx in r_grps if r_idx in b_grps}


def _is_comma_list_value(v: str) -> bool:
    """Return True if *v* looks like a comma-separated name/class list
    (at least two items, no whitespace within individual items).

    Used to identify group-header "registry" parameters such as
    ``schedule.registry=ClassA,ClassB,ClassC`` whose correct merged value
    is the release list (release adds new registrations) rather than the
    base list.  Simple scalars (``3``, ``yes``, ``INFO``) return False.
    """
    parts = v.split(",")
    if len(parts) < 2:
        return False
    return all(p.strip() and " " not in p.strip() for p in parts)


def _has_valid_kv_key(s: str) -> bool:
    """Return True only if the key portion of s (before the first = or :) contains
    no whitespace.  Prevents comment lines like '# Description   : some text' from
    being misidentified as commented KV entries.  Real keys such as 'trap.version'
    or 'log.max.size' never have spaces before the delimiter."""
    # Deliberately checks '=' before ':' (not the first delimiter): prose such as
    # '# Format: "SEC or sec" ... = ...' must not become a commented key, while
    # '#jdbc.url: jdbc:...?opt=val' (no spaces before '=') still qualifies.
    for delim in ("=", ":"):
        if delim in s:
            key_part = s.split(delim, 1)[0]
            return bool(key_part) and " " not in key_part and "\t" not in key_part
    return False


def _split_kv(s: str) -> Tuple[str, str, str]:
    """Split 'key = value' or 'key: value' at the FIRST delimiter, so a value may contain the
    other one (e.g. 'jdbc.url: jdbc:...?opt=val'). Returns (key, value, delimiter)."""
    delim = _first_delimiter(s)
    if delim:
        k, v = s.split(delim, 1)
        return k.strip(), v.strip(), delim
    return "", "", "="


def _first_delimiter(s: str) -> str:
    """'=' or ':' — whichever occurs first in *s*; '' when neither does."""
    positions = [(s.find(d), d) for d in ("=", ":") if d in s]
    return min(positions)[1] if positions else ""


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

    Single combined pass over the release spine preserves the release file's
    positional ordering for all entries.  Each base group index is emitted
    on-demand when the release spine first visits an entry for that index.
    Group headers are emitted at their natural release position — they do NOT
    trigger eager group emission.
    """
    report: List[ReportEntry] = []
    out_lines: List[str] = []

    # ── Section ordering ─────────────────────────────────────────────────
    # Use release spine as primary order.  Base-only sections are interleaved
    # just before the first release section that follows them in the base file.
    # Shadow base sections (#[X]) whose active counterpart ([X]) exists in
    # release are suppressed from direct emission — they are merged in-place
    # when [X] is processed.
    rel_section_set = set(rel_doc.section_order)
    # Shadow sections that have an active release counterpart
    suppressed_shadows = {
        s for s in base_doc.section_order
        if s.startswith("#[") and s[1:] in rel_section_set
    }
    # Interleave: base-only sections appear before the release section that
    # follows them in the base file
    _pending: List[str] = []
    _before: Dict[str, List[str]] = defaultdict(list)
    for _sec in base_doc.section_order:
        if _sec in suppressed_shadows:
            continue  # handled as shadow when active section is processed
        if _sec in rel_section_set:
            _before[_sec].extend(_pending)
            _pending = []
        else:
            _pending.append(_sec)
    _trailing_base_only_secs = _pending

    all_sections: List[str] = []
    for _sec in rel_doc.section_order:
        all_sections.extend(_before.get(_sec, []))
        all_sections.append(_sec)
    all_sections.extend(_trailing_base_only_secs)

    for section in all_sections:
        _sec_start_pos = len(out_lines)   # track whether this section emits anything

        # BUG-I: emit section header verbatim if raw line was stored, else reconstruct
        if section != "DEFAULT":
            # Emit comments that appeared before this section header in either file.
            # Prefer release preamble (more up-to-date); fall back to base preamble.
            preamble = (rel_doc.section_preamble.get(section)
                        or base_doc.section_preamble.get(section)
                        or [])
            _preamble_first_blank_skipped = False
            for _pc in preamble:
                # Deduplicate: skip only the FIRST blank preamble line when the
                # previous section's separator already provided a blank.  Allow
                # additional blank lines through so triple-blank separators in the
                # source file are faithfully reproduced.
                if (not _preamble_first_blank_skipped and not _pc.strip()
                        and out_lines and not out_lines[-1].strip()):
                    _preamble_first_blank_skipped = True
                    continue
                out_lines.append(_pc if _pc.endswith("\n") else _pc + "\n")

            # Prefer base doc's raw line (base is canonical); fall back to release or reconstruct
            raw_hdr = (base_doc.section_raw_lines.get(section)
                       or rel_doc.section_raw_lines.get(section))
            if raw_hdr:
                out_lines.append(raw_hdr if raw_hdr.endswith("\n") else raw_hdr + "\n")
            else:
                out_lines.append(f"{section}\n")

        # Check for shadow base section: if base has #[SectionName] and
        # release has [SectionName], use shadow entries as the effective base.
        # The shadow entries were stored with section="#[X]"; remap to "[X]"
        # so compound-key lookups match.
        _shadow_key = "#" + section  # e.g. "#[DBHandler]"
        _shadow_entries_raw = base_doc.sections.get(_shadow_key, [])
        _direct_base = base_doc.sections.get(section, [])

        _shadow_merge = False
        if _shadow_entries_raw and not _direct_base:
            # Remap shadow entries to the active section name.
            # _shadow_merge=True tells the merge logic to keep these commented
            # entries (not treat them as "absent") and to emit them commented.
            _shadow_merge = True
            out_lines.append(
                f"# [CMT-MRG-W015] REVIEW: section {section} is commented out in base but active "
                f"in release — its entries are kept commented (base); confirm this is correct\n")
            report.append(ReportEntry(
                type=EntryType.REVIEW_COMMENTED_SECTION_IN_BASE,
                file=rel_file, element=section, old="active in release",
                new="commented (base kept)", section=section,
            ))
            log_structured(logger, "WARNING", "KV", "REVIEW_COMMENTED_SECTION", rel_file, section,
                           "section commented out in base but active in release; base kept — confirm")
            base_entries: List[KVEntry] = []
            for _e in _shadow_entries_raw:
                _re = KVEntry(
                    section=section, key=_e.key, value=_e.value,
                    is_commented=_e.is_commented, comments=_e.comments,
                    delimiter=_e.delimiter, line_number=_e.line_number,
                    raw_line=_e.raw_line,
                )
                base_entries.append(_re)
                _c = f"{section}|{_re.key}"
                # Always register remapped shadow entries in lookup
                base_doc.lookup[_c] = _re
        else:
            base_entries = _direct_base

        rel_entries   = rel_doc.sections.get(section, [])
        base_groups   = (base_doc.indexed_groups or {}).get(section, {})
        rel_groups    = (rel_doc.indexed_groups  or {}).get(section, {})
        base_headers  = (base_doc.group_headers  or {}).get(section, {})
        rel_headers   = (rel_doc.group_headers   or {}).get(section, {})

        emitted_keys: set = set()

        # ── Pre-computations ─────────────────────────────────────────────

        # Keys that have at least one ACTIVE entry in base / release
        base_active_compounds = {
            f"{section}|{e.key}" for e in base_entries if not e.is_commented
        }
        rel_active_keys = {
            f"{section}|{e.key}" for e in rel_entries if not e.is_commented
        }
        # Keys that appear as annotations in release: a commented release entry
        # whose key is also active in release AND the commented entry appears
        # BEFORE the first active entry for that key.
        # (A commented entry appearing AFTER the active key is a "reverse annotation"
        # — the file shows the alternative value; it is not emitted on the spine.)
        _rel_first_active_pos: Dict[str, int] = {}
        _rel_first_commented_pos: Dict[str, int] = {}
        for _i, _e in enumerate(rel_entries):
            _c = f"{section}|{_e.key}"
            if not _e.is_commented and _c not in _rel_first_active_pos:
                _rel_first_active_pos[_c] = _i
            elif _e.is_commented and _c not in _rel_first_commented_pos:
                _rel_first_commented_pos[_c] = _i
        rel_annotation_compounds = {
            c for c in _rel_first_commented_pos
            if c in _rel_first_active_pos
            and _rel_first_commented_pos[c] < _rel_first_active_pos[c]
        }
        rel_compound_set = {f"{section}|{e.key}" for e in rel_entries}

        all_prefixes = set(base_groups) | set(rel_groups)

        # Group header compounds — any key whose stripped-prefix matches an
        # indexed-group prefix.  Used only to identify them; we do NOT emit
        # base groups eagerly at headers any more.
        group_header_compounds: set = set()
        for prefix in all_prefixes:
            for hdr in base_headers.get(prefix, []) + rel_headers.get(prefix, []):
                group_header_compounds.add(f"{section}|{hdr.key}")

        # Group identity: release index → base index.  Groups are matched by their
        # `name` subkey when every group of the prefix has a unique one, otherwise by index.
        r_to_b: Dict[str, Dict[int, int]] = {
            prefix: _match_groups(prefix, base_groups.get(prefix, {}), rel_groups.get(prefix, {}))
            for prefix in all_prefixes
        }
        b_to_r: Dict[str, Dict[int, int]] = {
            prefix: {b: r for r, b in m.items()} for prefix, m in r_to_b.items()
        }

        # Renumber map for release-only groups → merged indices
        renumber_map: Dict[str, Dict[int, int]] = {}
        group_totals: Dict[str, int] = {}
        for prefix in all_prefixes:
            b_grps = base_groups.get(prefix, {})
            r_grps = rel_groups.get(prefix, {})
            max_b  = max(b_grps.keys(), default=0)
            rel_only_sorted = sorted(k for k in r_grps if k not in r_to_b[prefix])
            renumber_map[prefix] = {
                r_idx: max_b + 1 + i for i, r_idx in enumerate(rel_only_sorted)
            }
            group_totals[prefix] = len(b_grps) + len(rel_only_sorted)

        # Track which base / release group indices have been emitted
        emitted_b_groups: Dict[str, set] = defaultdict(set)
        emitted_r_groups: Dict[str, set] = defaultdict(set)

        # Base annotations: compound → [commented base KVEntry]
        # A PRE-annotation is a commented base entry whose key is also ACTIVE in base
        # AND whose first commented occurrence comes BEFORE the first active occurrence.
        # POST-annotations (commented after the active key) must NOT be emitted as
        # pre-annotations or they appear in the wrong position.
        _base_first_active_pos: Dict[str, int] = {}
        _base_first_commented_pos: Dict[str, int] = {}
        for _bi, _be in enumerate(base_entries):
            _bc = f"{section}|{_be.key}"
            if not _be.is_commented and _bc not in _base_first_active_pos:
                _base_first_active_pos[_bc] = _bi
            elif _be.is_commented and _bc not in _base_first_commented_pos:
                _base_first_commented_pos[_bc] = _bi
        base_pre_annotation_keys = {
            c for c in _base_first_commented_pos
            if c in _base_first_active_pos
            and _base_first_commented_pos[c] < _base_first_active_pos[c]
        }

        base_annotations: Dict[str, List[KVEntry]] = defaultdict(list)
        base_post_annotations: Dict[str, List[KVEntry]] = defaultdict(list)
        base_commented_only: Dict[str, List[KVEntry]] = defaultdict(list)
        for _bi, entry in enumerate(base_entries):
            compound = f"{section}|{entry.key}"
            if not entry.is_commented:
                continue
            if compound in base_pre_annotation_keys:
                base_annotations[compound].append(entry)
            elif compound in _base_first_active_pos and _bi > _base_first_active_pos[compound]:
                base_post_annotations[compound].append(entry)
            elif compound not in base_active_compounds:
                base_commented_only[compound].append(entry)

        # Every line of the release section — base comment lines already present there
        # are not copied a second time.
        rel_lines = {e.raw_line.strip() for e in rel_entries}
        rel_lines |= {c.strip() for e in rel_entries for c in e.comments}

        # ── Anchor map: base-only regular params ─────────────────────────
        anchors: Dict[str, List[KVEntry]] = defaultdict(list)
        trailing_base_only: List[KVEntry] = []
        pending: List[KVEntry] = []

        for entry in base_entries:
            compound = f"{section}|{entry.key}"
            # Skip base annotations (emitted alongside the active entry)
            if entry.is_commented and compound in base_active_compounds:
                continue
            # Skip indexed group entries and group headers
            if _GROUP_KEY_RE.match(entry.key) or compound in group_header_compounds:
                continue
            # Skip commented-only base entries whose key appears in release
            # (release-only handling takes over).  In shadow-merge mode, keep
            # these entries so they can be emitted commented at the right position.
            if (entry.is_commented and compound not in base_active_compounds
                    and compound in rel_compound_set and not _shadow_merge):
                continue

            if compound not in rel_compound_set:
                pending.append(entry)
            else:
                anchors[compound].extend(pending)
                pending = []

        trailing_base_only = pending

        # ── Helpers ──────────────────────────────────────────────────────

        def _emit_verbatim(raw_line: str, comments: List[str]) -> None:
            for c in comments:
                out_lines.append(c if c.endswith("\n") else c + "\n")
            out_lines.append(raw_line if raw_line.endswith("\n") else raw_line + "\n")

        def _emit_base_annotations(compound: str) -> None:
            """Emit base annotations only if release doesn't supply its own."""
            if compound in rel_annotation_compounds:
                return  # release annotation already emitted via release spine walk
            for ann in base_annotations.get(compound, []):
                _emit_verbatim(ann.raw_line, ann.comments)

        def emit_base_only(bo: KVEntry) -> None:
            """Emit a base-only regular param (with its base annotations)."""
            bo_compound = f"{section}|{bo.key}"
            if bo_compound in emitted_keys:
                return
            _emit_base_annotations(bo_compound)
            merged_val, merged_comments, rpt = _merge_single_entry(
                bo, None, rel_file, config, section
            )
            if rpt:
                report.append(rpt)
            _emit_entry(out_lines, bo, merged_val, merged_comments)
            emitted_keys.add(bo_compound)

        def dedup_group_entries(entries: List[KVEntry]) -> List[KVEntry]:
            """
            Deduplicate group entries: for each compound keep the last ACTIVE
            occurrence (active beats commented).  If only commented occurrences
            exist for a compound, keep the last one.
            """
            last_active: Dict[str, int] = {}
            last_any: Dict[str, int] = {}
            for i, e in enumerate(entries):
                c = f"{section}|{e.key}"
                last_any[c] = i
                if not e.is_commented:
                    last_active[c] = i
            result: List[KVEntry] = []
            for i, e in enumerate(entries):
                c = f"{section}|{e.key}"
                if c in last_active:
                    if last_active[c] == i:
                        result.append(e)
                else:
                    if last_any[c] == i:
                        result.append(e)
            return result

        def emit_base_group(prefix: str, b_idx: int) -> None:
            """
            Emit all entries of base group b_idx for the given prefix.
            Uses the canonical (last-wins) entry from base_doc.lookup for the value.
            Emits release annotations before each group entry when present.
            """
            b_grps = base_groups.get(prefix, {})
            raw_entries = dedup_group_entries(b_grps.get(b_idx, []))

            for ge in raw_entries:
                ge_compound = f"{section}|{ge.key}"
                if ge_compound in emitted_keys:
                    continue
                # Base annotations within group entries — skip (group annotations
                # handled separately via base_annotations / rel_annotation_compounds)
                if ge.is_commented and ge_compound in base_active_compounds:
                    continue

                # If only a commented stub in base but active in release → release-only
                if ge.is_commented and ge_compound not in base_active_compounds:
                    rel_ge = rel_doc.lookup.get(ge_compound)
                    if rel_ge and not rel_ge.is_commented:
                        _emit_entry(out_lines, rel_ge, rel_ge.value, rel_ge.comments)
                        report.append(ReportEntry(
                            type=EntryType.RELEASE_ONLY_PARAMETER_ADDED,
                            file=rel_file, element=ge_compound,
                            old=rel_ge.value, new=rel_ge.value, section=section,
                        ))
                    else:
                        # Commented-only in both base and release — no active counterpart.
                        # Emit verbatim to preserve commented-out alternative configs /
                        # documentation.  Prefer release entry so release comments are used.
                        src = rel_doc.lookup.get(ge_compound) or ge
                        _emit_verbatim(src.raw_line, src.comments)
                    emitted_keys.add(ge_compound)
                    continue

                # Emit release annotation for this group entry if present
                if ge_compound in rel_annotation_compounds:
                    for rann in rel_entries:
                        rann_compound = f"{section}|{rann.key}"
                        if rann_compound == ge_compound and rann.is_commented:
                            _emit_verbatim(rann.raw_line, rann.comments)
                            break
                else:
                    # Emit base annotation if no release annotation
                    for bann in base_annotations.get(ge_compound, []):
                        _emit_verbatim(bann.raw_line, bann.comments)

                # Use canonical (last-wins) base entry for value; the matching release
                # entry lives under the release index of the matched group.
                canonical_base = base_doc.lookup.get(ge_compound, ge)
                r_idx_match = b_to_r.get(prefix, {}).get(b_idx)
                rel_ge = None
                if r_idx_match is not None:
                    rel_key = re.sub(rf'^({re.escape(prefix)}\.)\d+(\.)',
                                     lambda m: f"{m.group(1)}{r_idx_match}{m.group(2)}", ge.key)
                    rel_ge = rel_doc.lookup.get(f"{section}|{rel_key}")
                if rel_ge and rel_ge.is_commented and \
                        f"{section}|{rel_ge.key}" not in rel_active_keys:
                    rel_ge = None

                merged_val, merged_comments, rpt = _merge_single_entry(
                    canonical_base, rel_ge, rel_file, config, section
                )
                if rpt:
                    report.append(rpt)
                _emit_entry(out_lines, canonical_base, merged_val, merged_comments)
                if rpt and rpt.type == EntryType.JAVA_CLASS_NAME_FROM_RELEASE:
                    _annotate_class_from_release(ge.key, ge_compound, rpt.old)
                emitted_keys.add(ge_compound)

            emitted_b_groups[prefix].add(b_idx)

        def emit_release_only_group(prefix: str, r_idx: int) -> None:
            """Emit a release-only group with renumbered index."""
            r_grps = rel_groups.get(prefix, {})
            merged_idx = renumber_map[prefix][r_idx]
            for ge in r_grps.get(r_idx, []):
                if ge.is_commented:
                    # Emit commented-only release group entries verbatim (no renumbering)
                    _emit_verbatim(ge.raw_line, ge.comments)
                    emitted_keys.add(f"{section}|{ge.key}")
                    continue
                new_key = re.sub(
                    rf'^({re.escape(prefix)}\.)(\d+)(\.)',
                    lambda m, ni=merged_idx: f"{m.group(1)}{ni}{m.group(3)}",
                    ge.key,
                )
                new_compound = f"{section}|{new_key}"
                _emit_raw_entry(
                    out_lines, new_key, ge.value,
                    ge.delimiter, ge.is_commented, ge.comments[:]
                )
                emitted_keys.add(new_compound)
                report.append(ReportEntry(
                    type=EntryType.INDEXED_GROUP_APPENDED,
                    file=rel_file,
                    element=f"{section}|{new_key}",
                    old=f"release index {r_idx}",
                    new=f"merged index {merged_idx}",
                    section=section,
                ))
            emitted_r_groups[prefix].add(r_idx)

        def _annotate_class_from_release(key: str, compound: str, production_value: str) -> None:
            """Release Java class name replaced the production one: show the production value
            directly above the active line so the user can confirm."""
            out_lines.insert(len(out_lines) - 1,
                f"# [CMT-MRG-W017] REVIEW: '{key}' production value was {production_value} — "
                f"release class name kept; confirm the correct class\n")
            log_structured(logger, "WARNING", "KV", "REVIEW_CLASS_NAME_FROM_RELEASE", rel_file, compound,
                           f"production class {production_value} replaced by release class — confirm")

        def _flag_group_count(compound: str, key: str, value: str) -> None:
            """Base count wins, but a count that differs from the merged group total is flagged."""
            if not key.endswith(".count"):
                return
            prefix = key[: -len(".count")]
            total = group_totals.get(prefix)
            if total is None or not value.strip().isdigit() or int(value) == total:
                return
            report.append(ReportEntry(
                type=EntryType.GROUP_COUNT_MISMATCH,
                file=rel_file, element=compound,
                old=value.strip(), new=str(total), section=section,
            ))
            log_structured(logger, "WARNING", "KV", "GROUP_COUNT_MISMATCH", rel_file, compound,
                           f"{key}={value.strip()} kept from base, but the merged output has "
                           f"{total} '{prefix}' groups — verify the count")

        # ── Combined single pass over release spine ───────────────────────
        for entry in rel_entries:
            compound = f"{section}|{entry.key}"

            # ── Active indexed group entry ───────────────────────────────
            # Tracked per group (not per key): with name matching a release
            # index can differ from the base index it maps to, so release and
            # base group keys must not share the emitted_keys namespace.
            grp_active = None if entry.is_commented else _GROUP_KEY_RE.match(entry.key)
            if grp_active and grp_active.group(1) in all_prefixes:
                prefix = grp_active.group(1)
                r_idx  = int(grp_active.group(2))
                b_idx_match = r_to_b.get(prefix, {}).get(r_idx)
                if b_idx_match is not None:
                    if b_idx_match not in emitted_b_groups[prefix]:
                        emit_base_group(prefix, b_idx_match)
                elif (r_idx in renumber_map.get(prefix, {})
                        and r_idx not in emitted_r_groups[prefix]):
                    emit_release_only_group(prefix, r_idx)
                continue

            if compound in emitted_keys:
                # Post-annotation: a commented release entry for an already-emitted
                # key (appears AFTER the active key).  These are "alternative value"
                # comments (e.g. #event.list=UCGDMLS after event.list=UCM) and must
                # be emitted verbatim so the user sees all the options.
                if entry.is_commented:
                    _emit_verbatim(entry.raw_line, entry.comments)
                continue

            # ── Release annotation BEFORE its active key ────────────────
            # Commented release entry whose key also appears active in release.
            if entry.is_commented and compound in rel_active_keys:
                _emit_verbatim(entry.raw_line, entry.comments)
                continue  # no emitted_keys.add — annotation does not consume slot

            # ── Indexed group entry ──────────────────────────────────────
            grp_match = _GROUP_KEY_RE.match(entry.key)
            if grp_match:
                prefix = grp_match.group(1)
                r_idx  = int(grp_match.group(2))
                b_grps = base_groups.get(prefix, {})

                b_idx_match = r_to_b.get(prefix, {}).get(r_idx)
                if b_idx_match is not None:
                    # Matched base group: emit all entries of the base group
                    # the first time any entry of the release group is encountered.
                    if b_idx_match not in emitted_b_groups[prefix]:
                        emit_base_group(prefix, b_idx_match)
                    emitted_keys.add(compound)
                elif r_idx in emitted_r_groups.get(prefix, set()):
                    emitted_keys.add(compound)
                elif prefix in renumber_map and r_idx in renumber_map[prefix]:
                    if r_idx not in emitted_r_groups.get(prefix, set()):
                        emit_release_only_group(prefix, r_idx)
                else:
                    emitted_keys.add(compound)
                continue

            # ── Group header ─────────────────────────────────────────────
            if compound in group_header_compounds:
                # Emit base-only anchors
                for bo in anchors.get(compound, []):
                    emit_base_only(bo)
                anchors[compound] = []

                # Emit base annotations (if release doesn't have its own)
                _emit_base_annotations(compound)

                # Determine effective base entry
                base_hdr = base_doc.lookup.get(compound)
                if base_hdr and base_hdr.is_commented and compound not in base_active_compounds:
                    base_hdr = None

                if base_hdr is None:
                    _emit_entry(out_lines, entry, entry.value, entry.comments)
                    report.append(ReportEntry(
                        type=EntryType.RELEASE_ONLY_PARAMETER_ADDED,
                        file=rel_file, element=compound,
                        old=entry.value, new=entry.value, section=section,
                    ))
                else:
                    rel_hdr = entry if not entry.is_commented else None
                    # Comma-separated registry headers (e.g. schedule.registry):
                    # union of base items then release-only items, so base
                    # registrations are kept and release registrations are added.
                    # All other group headers (e.g. schedule.count) follow the
                    # standard base-wins strategy.
                    if (rel_hdr is not None
                            and base_hdr.value != rel_hdr.value
                            and _is_comma_list_value(base_hdr.value)
                            and _is_comma_list_value(rel_hdr.value)):
                        merged_comments = rel_hdr.comments or base_hdr.comments
                        union_val = _comma_union(base_hdr.value, rel_hdr.value)
                        if union_val != base_hdr.value:
                            report.append(ReportEntry(
                                type=EntryType.COMMA_VALUE_UNION,
                                file=rel_file, element=compound,
                                old=rel_hdr.value, new=union_val,
                                base_comment="\n".join(base_hdr.comments),
                                release_comment="\n".join(rel_hdr.comments),
                                section=section,
                            ))
                        _emit_entry(out_lines, rel_hdr, union_val, merged_comments)
                        emitted_value = union_val
                    else:
                        merged_val, merged_comments, rpt = _merge_single_entry(
                            base_hdr, rel_hdr, rel_file, config, section
                        )
                        if rpt:
                            report.append(rpt)
                        _emit_entry(out_lines, base_hdr, merged_val, merged_comments)
                        emitted_value = merged_val
                    _flag_group_count(compound, entry.key, emitted_value)
                emitted_keys.add(compound)
                # NOTE: we do NOT eagerly emit base groups here.
                # Base groups are emitted on-demand when the release spine
                # visits their entries, preserving the exact release ordering.
                continue

            # ── Regular param ────────────────────────────────────────────

            # Emit base-only entries anchored just before this release entry
            for bo in anchors.get(compound, []):
                emit_base_only(bo)
            anchors[compound] = []

            # Emit release annotation was already handled above (continue skipped it).
            # Now emit base annotation if release doesn't have one.
            _emit_base_annotations(compound)

            # Determine effective base entry.
            # Commented-only (no active counterpart) → treat as absent, UNLESS
            # this is a shadow-merge section (entire section was commented in base).
            # In that case keep the commented entry so base comment state is used.
            base_entry = base_doc.lookup.get(compound)
            if (base_entry and base_entry.is_commented
                    and compound not in base_active_compounds
                    and not _shadow_merge):
                base_entry = None

            if base_entry:
                merged_val, merged_comments, rpt = _merge_single_entry(
                    base_entry,
                    entry if not entry.is_commented else None,
                    rel_file, config, section,
                )
                if rpt:
                    report.append(rpt)
                _emit_entry(out_lines, base_entry, merged_val, merged_comments)
                if rpt and rpt.type == EntryType.JAVA_CLASS_NAME_FROM_RELEASE:
                    _annotate_class_from_release(entry.key, compound, rpt.old)
                # Base alternative-value comments (`#key=alt` after the active key) give context;
                # one that equals the value now active adds nothing and is not copied.
                for alt in base_post_annotations.get(compound, []):
                    if alt.raw_line.strip() not in rel_lines and alt.value.strip() != merged_val.strip():
                        _emit_verbatim(alt.raw_line, [])
            else:
                # Commented out in base, active in release: keep the base comment for context
                # and ask the user to confirm the release value.
                if not entry.is_commented and base_commented_only.get(compound):
                    for bc in base_commented_only[compound]:
                        if bc.raw_line.strip() not in rel_lines and bc.value.strip() != entry.value.strip():
                            _emit_verbatim(bc.raw_line, [])
                    out_lines.append(
                        f"# [CMT-MRG-W014] REVIEW: '{entry.key}' is commented out in base but active "
                        f"in release — release value kept; confirm the correct value\n")
                    report.append(ReportEntry(
                        type=EntryType.REVIEW_COMMENTED_IN_BASE,
                        file=rel_file, element=compound,
                        old=base_commented_only[compound][-1].raw_line.strip(), new=entry.value,
                        section=section,
                    ))
                    log_structured(logger, "WARNING", "KV", "REVIEW_COMMENTED_IN_BASE", rel_file,
                                   compound, "commented out in base, active in release; release value "
                                   "kept — confirm the correct value")
                # Release-only
                _emit_entry(out_lines, entry, entry.value, entry.comments)
                report.append(ReportEntry(
                    type=EntryType.RELEASE_ONLY_PARAMETER_ADDED,
                    file=rel_file, element=compound,
                    old=entry.value, new=entry.value, section=section,
                ))
            emitted_keys.add(compound)

        # ── Post-walk: unemitted base groups ─────────────────────────────
        # Base groups whose indices never appeared on the release spine
        # (base has more groups than release), appended in sorted order.
        for prefix in sorted(all_prefixes):
            for b_idx in sorted(base_groups.get(prefix, {}).keys()):
                if b_idx not in emitted_b_groups[prefix]:
                    emit_base_group(prefix, b_idx)

        # ── Trailing base-only regular params ─────────────────────────────
        for bo in trailing_base_only:
            emit_base_only(bo)

        # ── Safety net: any remaining unemitted base entries ──────────────
        for entry in base_entries:
            compound = f"{section}|{entry.key}"
            if compound in emitted_keys:
                continue
            if entry.is_commented and compound in base_active_compounds:
                continue  # annotation — already emitted alongside active entry
            if _GROUP_KEY_RE.match(entry.key) or compound in group_header_compounds:
                continue
            if entry.is_commented and compound not in base_active_compounds and not _shadow_merge:
                continue  # commented-only base entry not in release
            merged_val, merged_comments, rpt = _merge_single_entry(
                entry, rel_doc.lookup.get(compound), rel_file, config, section
            )
            if rpt:
                report.append(rpt)
            _emit_entry(out_lines, entry, merged_val, merged_comments)
            emitted_keys.add(compound)

        # ── Section trailing content ──────────────────────────────────────
        # Emit comment/unrecognised lines that appeared after the last KV
        # entry in this section (or form the entire section when no KV
        # entries exist — e.g. comma-delimited files).
        # Prefer release trailing content; fall back to base.
        _sec_trailing = (rel_doc.section_trailing.get(section)
                         or base_doc.section_trailing.get(section)
                         or [])
        for _tl in _sec_trailing:
            out_lines.append(_tl if _tl.endswith("\n") else _tl + "\n")

        # Only add blank separator between sections if this section emitted content.
        # Skipping it for empty sections (e.g. an empty DEFAULT when the file starts
        # with a named section like [Defaults]) prevents spurious leading blank lines.
        if len(out_lines) > _sec_start_pos:
            out_lines.append("\n")

    # Remove any trailing blank lines generated by the last section's separator.
    # All content lines are already newline-terminated, so no extra newline is needed.
    while out_lines and not out_lines[-1].strip():
        out_lines.pop()

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

    release_val = rel_entry.value

    # Uncomment case: release has the key commented out, base has it active
    uncomment_case = rel_entry.is_commented and not base_entry.is_commented

    # Determine whether the value is actually changing
    value_changing = uncomment_case or base_entry.value != release_val

    # Prefer release comments when present — release config is the authoritative
    # source for documentation/intent.  Fall back to base comments only when
    # the release entry carries no comments of its own.
    if rel_entry.comments:
        merged_comments = rel_entry.comments
    else:
        merged_comments = base_entry.comments

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

    # Values differ or comment state changes
    if value_changing:
        # API version upgrade: release has a newer version of a third-party
        # library — use the release (newer) value rather than the base value.
        if not uncomment_case and detect_api_version_upgrade(base_entry.value, release_val):
            rpt = ReportEntry(
                type=EntryType.API_VERSION_UPGRADED,
                file=rel_file,
                element=compound,
                old=base_entry.value,    # old = base (what was there before)
                new=release_val,         # new = release (newer API version used)
                base_comment="\n".join(base_entry.comments),
                release_comment="\n".join(rel_entry.comments),
                section=section,
            )
            return release_val, merged_comments, rpt

        # Java FQCN: when the release value looks like a Java fully-qualified class
        # name, defer to the release value.  Class names are deployment-specific and
        # may legitimately differ between environments (different vendor jars, renamed
        # packages, etc.).  Flag with a dedicated indicator so reviewers can verify.
        if not uncomment_case and is_java_fqcn(release_val) and is_java_fqcn(base_entry.value):
            rpt = ReportEntry(
                type=EntryType.JAVA_CLASS_NAME_FROM_RELEASE,
                file=rel_file,
                element=compound,
                old=base_entry.value,   # what base had
                new=release_val,        # release value used in output
                base_comment="\n".join(base_entry.comments),
                release_comment="\n".join(rel_entry.comments),
                section=section,
            )
            return release_val, merged_comments, rpt

        rpt = ReportEntry(
            type=(EntryType.UNCOMMENT_REPLACE
                  if uncomment_case else EntryType.BASE_TO_RELEASE_REPLACED),
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


def _emit_entry(
    out_lines: List[str],
    entry: KVEntry,
    value: str,
    comments: List[str],
) -> None:
    """Emit comments then the key line.

    BUG-D fix: preserve original line formatting.
    - Pass-through (value unchanged, comment state unchanged): emit raw_line verbatim.
    - Changed value: use raw_line as a template — locate the delimiter in the raw
      line, keep everything up to and including it, append the new value.
      This preserves indentation, spaces around '=', and any inline comment
      after the value that was present in the original line.
    """
    for c in comments:
        out_lines.append(c if c.endswith("\n") else c + "\n")

    raw = entry.raw_line.rstrip("\n")

    # Determine whether this is a pass-through or a changed-value emit
    # by comparing the target value with what the raw line would produce.
    # NOTE: commented entries are included here — their raw_line already starts
    # with '#', so verbatim emit is always correct for unchanged values.
    if entry.value == value:
        # Pass-through: commented lines are context and stay byte-for-byte;
        # active lines have trailing spaces/tabs stripped from the value (K-20).
        out_lines.append((raw if entry.is_commented else raw.rstrip(" \t")) + "\n")
        return

    # Changed value: use raw_line as template.
    # For commented entries, raw_line already starts with '#', so prefix already
    # contains the '#'.  Do NOT prepend an extra '#' or the output gets '##'.
    delim_pos = raw.find(entry.delimiter)
    if delim_pos >= 0:
        prefix = raw[:delim_pos + len(entry.delimiter)]
        # Detect any trailing inline comment after the original value.
        # Strip trailing spaces/tabs first so they are never treated as part of
        # the inline comment or the value.
        # Heuristic: first occurrence of ' #' or ' ;' after the delimiter.
        orig_after_delim = raw[delim_pos + len(entry.delimiter):].rstrip(" \t")
        inline_comment = ""
        for marker in (" #", " ;"):
            idx = orig_after_delim.find(marker)
            if idx >= 0:
                inline_comment = orig_after_delim[idx:]
                break
        # prefix already encodes whether the line is commented (raw_line has '#')
        out_lines.append(f"{prefix}{value}{inline_comment}\n")
    else:
        # Fallback: reconstruct (should not happen for valid KV)
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
    raw_line: str = "",
) -> None:
    """Emit comments then the key line.

    BUG-H fix: same raw_line template approach as _emit_entry.
    """
    for c in comments:
        out_lines.append(c if c.endswith("\n") else c + "\n")

    if raw_line:
        raw = raw_line.rstrip("\n")
        delim_pos = raw.find(delimiter)
        if delim_pos >= 0:
            prefix = raw[:delim_pos + len(delimiter)]
            # Strip trailing spaces/tabs before inline-comment detection
            orig_after_delim = raw[delim_pos + len(delimiter):].rstrip(" \t")
            inline_comment = ""
            for marker in (" #", " ;"):
                idx = orig_after_delim.find(marker)
                if idx >= 0:
                    inline_comment = orig_after_delim[idx:]
                    break
            if is_commented:
                out_lines.append(f"#{prefix}{value}{inline_comment}\n")
            else:
                out_lines.append(f"{prefix}{value}{inline_comment}\n")
            return

    # Fallback when no raw_line available
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

@register(".cfg", ".ini", ".conf", ".properties", ".sh", ".acl")
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
        # Active keys of every file in this merge: lets `#key = value` (spaces around the
        # key) be recognised as a commented parameter without turning prose into keys.
        known_keys: Set[str] = set()
        for path in [*base_files, rel_file]:
            known_keys |= {e.key for entries in parse_kv_doc(path).sections.values()
                           for e in entries if not e.is_commented}

        base_doc = parse_kv_doc(base_files[0], known_keys)
        for extra_base in base_files[1:]:
            extra_doc = parse_kv_doc(extra_base, known_keys)
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

        rel_raw = open_text(rel_file)
        rel_doc = parse_kv_doc(rel_file, known_keys)

        # Only report duplicates found in the RELEASE file — those indicate the
        # release config has conflicting entries the user should review.
        # Base duplicates are resolved silently (last-wins) and don't surface.
        report.extend(_report_duplicates(rel_doc, rel_file))

        out_lines, merge_report = merge_kv(base_doc, rel_doc, rel_file, config, logger)
        report.extend(merge_report)
        for entry in merge_report:
            if entry.type == EntryType.EMPTY_BASE_OVERRIDE:
                log_structured(logger, "ERROR", "KV", "EMPTY_BASE_OVERRIDE", rel_file, entry.element,
                               "base value empty — release value forced empty; review required")

        # Preserve trailing blank line: if the release file ends with a blank line
        # (i.e. \n\n at EOF), the merged output must too.  merge_kv strips all
        # trailing blanks to avoid spurious separators, so re-add exactly one
        # blank line when the release file had one.
        if rel_raw.endswith("\n\n"):
            out_lines.append("\n")

        # Separate excluded params from the main report
        excluded = [r for r in report if r.type == EntryType.EXCLUDED_BASE_ONLY_PARAMETER]
        report   = [r for r in report if r.type != EntryType.EXCLUDED_BASE_ONLY_PARAMETER]

        if not config.dry_run:
            ensure_dir(out_file)
            with open(out_file, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(out_lines)

        # Attach excluded back so engine can route them to MergeResult.excluded_params
        report.extend(excluded)
        return report
