"""
configmerge.processors.json_proc
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
JSON processor (.json)

Merge: base values overwrite release values recursively.
Release-only keys are preserved.  Empty-base override applied.
Duplicate key detection via custom object_pairs_hook.
Output validated before writing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from . import register, BaseProcessor
from ..models import MergeConfig, ReportEntry, EntryType
from ..logger import log_structured
from ..utils import ensure_dir, open_text, detect_api_version_upgrade, is_java_fqcn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_load_json(
    file_path: str, role: str, rel_file: str, logger: logging.Logger
) -> Optional[Any]:
    try:
        content = open_text(file_path).strip()  # BUG-B: encoding-aware read
        if not content:
            log_structured(logger, "ERROR", "JSON", "EMPTY_FILE",
                           file_path, "", f"{role} file is empty")
            return None
        return json.loads(content)
    except json.JSONDecodeError as e:
        log_structured(logger, "ERROR", "JSON", "INVALID_JSON",
                       file_path, "", f"{role} invalid JSON: {e}")
        return None
    except Exception as e:
        log_structured(logger, "ERROR", "JSON", "READ_ERROR", file_path, "", str(e))
        return None


def _collapse_primitive_arrays(text: str) -> str:
    """Collapse expanded JSON arrays that contain only primitive values back to
    a single line.

    json.dump() with any indent setting always expands arrays to multi-line,
    but config files typically write simple arrays inline, e.g.::

        "auth.modes": ["oauth2"]

    This function finds every array whose body contains no nested ``[`` or
    ``{`` characters (i.e. no nested arrays or objects — only strings, numbers,
    booleans, and null) and collapses whitespace so it reads on one line.

    Arrays that contain nested structures are left untouched.  String literals are
    copied as-is: brackets or commas inside a string are never treated as structure.
    """
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            end = _string_end(text, i)
            out.append(text[i:end])
            i = end
            continue
        if ch == "[":
            items, current, j, primitive = [], [], i + 1, True
            while j < n and text[j] != "]":
                c = text[j]
                if c == '"':
                    end = _string_end(text, j)
                    current.append(text[j:end])
                    j = end
                    continue
                if c in "[{":
                    primitive = False
                    break
                if c == ",":
                    items.append("".join(current).strip())
                    current = []
                else:
                    current.append(c)
                j += 1
            if primitive and j < n:
                items.append("".join(current).strip())
                out.append("[" + ", ".join(item for item in items if item) + "]")
                i = j + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _string_end(text: str, start: int) -> int:
    """Index just past the JSON string literal that opens at *start*."""
    j = start + 1
    while j < len(text):
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == '"':
            return j + 1
        j += 1
    return len(text)


def _same_json(a: Any, b: Any) -> bool:
    """JSON equality: unlike Python ==, true != 1 and false != 0."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _detect_indent(text: str):
    """Detect the indentation used in a JSON file.

    Returns '\t' for tab-indented files, or an int (2, 4, or 8) for
    space-indented files.  Defaults to 2 when no indentation is detected.
    """
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped and line != stripped:
            if line[0] == "\t":
                return "\t"
            indent = len(line) - len(stripped)
            if indent in (2, 4, 8):
                return indent
    return 2


def _detect_duplicates(
    file_path: str, rel_file: str, logger: logging.Logger
) -> List[ReportEntry]:
    report: List[ReportEntry] = []
    duplicates: List = []

    def hook(pairs):
        seen: Dict = {}
        local_dups: Dict = {}
        for k, v in pairs:
            if k in seen:
                local_dups[k] = local_dups.get(k, 1) + 1
            else:
                seen[k] = v
        for key, count in local_dups.items():
            duplicates.append((key, count))
        return dict(pairs)

    try:
        content = open_text(file_path).strip()  # BUG-B: encoding-aware read
        if content:
            json.loads(content, object_pairs_hook=hook)
    except Exception:
        pass

    for key, count in duplicates:
        report.append(ReportEntry(
            type=EntryType.DUPLICATE_KEY,
            file=rel_file,
            element=key,
            old=f"{count} duplicates",
            new="LAST_VALUE_USED",
        ))
    return report


def _add_missing_keys(target: Any, extra: Any) -> None:
    """Recursively copy keys from *extra* that *target* lacks (existing values are kept)."""
    if not isinstance(target, dict) or not isinstance(extra, dict):
        return
    for k, v in extra.items():
        if k not in target:
            target[k] = v
        else:
            _add_missing_keys(target[k], v)


def _merge(
    base: Any, rel: Any, path: str, rel_file: str, report: List[ReportEntry]
) -> None:
    if not isinstance(base, dict) or not isinstance(rel, dict):
        return
    for k in base:
        current = f"{path}.{k}" if path else k
        # Empty object/array in base but populated in release — flagged for review.
        # {} : base predates the release keys → release keys taken.
        # [] : base list intentionally empty → base (empty) kept.
        if (isinstance(base[k], (dict, list)) and not base[k]
                and type(rel.get(k)) is type(base[k]) and rel.get(k)):
            keep_release = isinstance(base[k], dict)
            report.append(ReportEntry(
                type=EntryType.REVIEW_EMPTY_IN_BASE,
                file=rel_file,
                element=current,
                old=json.dumps(rel[k]),
                new=json.dumps(rel[k] if keep_release else base[k]),
            ))
            if not keep_release:
                rel[k] = []
            continue
        if isinstance(base[k], dict) and isinstance(rel.get(k), dict):
            _merge(base[k], rel[k], current, rel_file, report)
        else:
            old_val = rel.get(k)
            new_val = base[k]

            if new_val == "" or new_val is None:
                report.append(ReportEntry(
                    type=EntryType.JSON_EMPTY_BASE_OVERRIDE,
                    file=rel_file,
                    element=current,
                    old=json.dumps(old_val),
                    new="",
                    recommended=json.dumps(old_val),
                ))
                rel[k] = new_val
            elif not _same_json(old_val, new_val):
                old_s = json.dumps(old_val)
                new_s = json.dumps(new_val)
                if isinstance(old_val, str) and isinstance(new_val, str) and \
                        detect_api_version_upgrade(new_val, old_val):
                    # Release has a newer API version — keep release value
                    report.append(ReportEntry(
                        type=EntryType.API_VERSION_UPGRADED,
                        file=rel_file,
                        element=current,
                        old=new_s,   # old = base value
                        new=old_s,   # new = release (newer) value kept
                    ))
                    # rel[k] already holds old_val (release); leave it unchanged
                elif isinstance(old_val, str) and isinstance(new_val, str) and \
                        is_java_fqcn(old_val) and is_java_fqcn(new_val):
                    # Both values are Java FQCNs — class names are deployment-specific;
                    # use the release value and flag for reviewer attention.
                    report.append(ReportEntry(
                        type=EntryType.JAVA_CLASS_NAME_FROM_RELEASE,
                        file=rel_file,
                        element=current,
                        old=new_s,   # old = base value
                        new=old_s,   # new = release value used
                    ))
                    # rel[k] already holds old_val (release); leave it unchanged
                else:
                    report.append(ReportEntry(
                        type=EntryType.JSON_BASE_TO_RELEASE_REPLACED,
                        file=rel_file,
                        element=current,
                        old=old_s,
                        new=new_s,
                    ))
                    rel[k] = new_val


def _find_release_only(
    base: Any, rel: Any, path: str, rel_file: str, report: List[ReportEntry]
) -> None:
    if not isinstance(base, dict) or not isinstance(rel, dict):
        return
    for k in rel:
        current = f"{path}.{k}" if path else k
        if k not in base:
            report.append(ReportEntry(
                type=EntryType.RELEASE_ONLY_PARAMETER_ADDED,
                file=rel_file,
                element=current,
                old=json.dumps(rel[k]),
                new=json.dumps(rel[k]),
            ))
        elif isinstance(rel[k], dict) and isinstance(base.get(k), dict):
            _find_release_only(base[k], rel[k], current, rel_file, report)


# ---------------------------------------------------------------------------
# Processor class
# ---------------------------------------------------------------------------

@register(".json")
class JSONProcessor(BaseProcessor):

    def process(
        self,
        base_files: List[str],
        rel_file: str,
        out_file: str,
        config: MergeConfig,
        logger: logging.Logger,
    ) -> List[ReportEntry]:
        logger.info(f"[JSON] {rel_file}")
        report: List[ReportEntry] = []

        # BUG-G: detect original indent width for fidelity-preserving output
        rel_raw  = open_text(rel_file)
        rel_indent = _detect_indent(rel_raw)

        # Many-to-One: the first base (mapping-file order) wins; later bases only add
        # keys the earlier ones lack — same rule as the KV processor.
        bases = [_safe_load_json(bf, "BASE", rel_file, logger) for bf in base_files]
        rel   = _safe_load_json(rel_file, "RELEASE", rel_file, logger)

        if rel is None or any(b is None for b in bases):
            bad = [f for f, b in zip(base_files, bases) if b is None] + ([rel_file] if rel is None else [])
            report.append(ReportEntry(
                type=EntryType.INVALID_JSON,
                file=rel_file,
                element="",
                old=", ".join(bad),
                new="SKIPPED",
            ))
            return report

        base = bases[0]
        for extra in bases[1:]:
            _add_missing_keys(base, extra)

        for bf in base_files:
            report.extend(_detect_duplicates(bf, rel_file, logger))

        _merge(base, rel, "", rel_file, report)
        for entry in report:
            if entry.type == EntryType.REVIEW_EMPTY_IN_BASE:
                log_structured(logger, "WARNING", "JSON", "REVIEW_EMPTY_IN_BASE", rel_file, entry.element,
                               f"empty in base but populated in release; output {entry.new} — confirm")
            if entry.type == EntryType.JSON_EMPTY_BASE_OVERRIDE:
                log_structured(logger, "ERROR", "JSON", "EMPTY_BASE_OVERRIDE", rel_file, entry.element,
                               "base value empty — release value forced empty; review required")
        _find_release_only(base, rel, "", rel_file, report)

        # Output validation
        try:
            json_text = json.dumps(rel)
            json.loads(json_text)
        except Exception as e:
            report.append(ReportEntry(
                type=EntryType.INVALID_OUTPUT_JSON,
                file=rel_file,
                element="",
                old="INVALID_JSON_GENERATED",
                new="",
            ))
            log_structured(logger, "ERROR", "JSON", "INVALID_OUTPUT_JSON",
                           rel_file, "", str(e))
            return report

        if not config.dry_run:
            ensure_dir(out_file)
            out_text = json.dumps(rel, indent=rel_indent, ensure_ascii=False)
            # Collapse primitive-only arrays back to single line so that simple
            # arrays like ["oauth2"] are not expanded to multi-line by json.dumps.
            out_text = _collapse_primitive_arrays(out_text)
            with open(out_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(out_text)
                f.write("\n")

        return report
