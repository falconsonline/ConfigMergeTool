"""
configmerge.processors.logrotate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Logrotate processor (.logrotate) — whole-file replacement from base.
"""

from __future__ import annotations

import logging
from typing import List

from . import register, BaseProcessor
from ..models import MergeConfig, ReportEntry, EntryType
from ..logger import log_structured
from ..utils import ensure_dir


@register(".logrotate")
class LogrotateProcessor(BaseProcessor):

    def process(
        self,
        base_files: List[str],
        rel_file: str,
        out_file: str,
        config: MergeConfig,
        logger: logging.Logger,
    ) -> List[ReportEntry]:
        logger.info(f"[LOGROTATE] {rel_file}")
        report: List[ReportEntry] = []

        with open(base_files[0], encoding="utf-8") as f:
            base_content = f.read()

        if not base_content.strip():
            log_structured(logger, "ERROR", "LOGROTATE", "EMPTY_BASE",
                           rel_file, "", "base is empty — output forced empty")
            report.append(ReportEntry(
                type=EntryType.LOGROTATE_EMPTY_BASE_OVERRIDE,
                file=rel_file,
                element="",
                old="FULL_FILE",
                new="",
                recommended="FROM_RELEASE",
            ))
            if not config.dry_run:
                ensure_dir(out_file)
                with open(out_file, "w", encoding="utf-8"):
                    pass   # write empty file
            return report

        report.append(ReportEntry(
            type=EntryType.LOGROTATE_BASE_TO_RELEASE_REPLACED,
            file=rel_file,
            element="",
            old="FULL_FILE",
            new="FROM_BASE",
        ))
        if not config.dry_run:
            ensure_dir(out_file)
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(base_content)

        return report
