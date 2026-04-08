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
from typing import Any, Dict, List, Optional

from . import register, BaseProcessor
from ..models import MergeConfig, ReportEntry, EntryType
from ..logger import log_structured
from ..utils import ensure_dir, open_text


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


def _detect_indent(text: str) -> int:
    """Detect the indentation width used in a JSON file (2 or 4 spaces, default 2)."""
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped and line != stripped:
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


def _merge(
    base: Any, rel: Any, path: str, rel_file: str, report: List[ReportEntry]
) -> None:
    if not isinstance(base, dict) or not isinstance(rel, dict):
        return
    for k in base:
        current = f"{path}.{k}" if path else k
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
            elif old_val != new_val:
                report.append(ReportEntry(
                    type=EntryType.JSON_BASE_TO_RELEASE_REPLACED,
                    file=rel_file,
                    element=current,
                    old=json.dumps(old_val),
                    new=json.dumps(new_val),
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

        # MOD-2: warn if multiple base files supplied (not yet supported for JSON)
        if len(base_files) > 1:
            logger.warning(
                f"[JSON] {rel_file}: multi-base merge not fully supported for JSON — "
                f"using base_files[0] only; {len(base_files) - 1} additional base(s) ignored"
            )

        # BUG-G: detect original indent width for fidelity-preserving output
        rel_raw  = open_text(rel_file)
        rel_indent = _detect_indent(rel_raw)

        base = _safe_load_json(base_files[0], "BASE", rel_file, logger)
        rel  = json.loads(rel_raw) if rel_raw.strip() else None

        if base is None or rel is None:
            return report

        report.extend(_detect_duplicates(base_files[0], rel_file, logger))

        _merge(base, rel, "", rel_file, report)
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
            with open(out_file, "w", encoding="utf-8", newline="\n") as f:
                # BUG-G: preserve original indent width instead of hard-coding 2
                json.dump(rel, f, indent=rel_indent, ensure_ascii=False)
                f.write("\n")

        return report
