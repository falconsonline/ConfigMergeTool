"""
configmerge.processors.sstp
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Merge-mode processor for Roamware Smart-STP (``.sstp``) routing rule files
(Phase 8 / MOD-5).

SSTP files are auto-generated routing rule scripts — they are NOT hand-edited
config files.  In merge mode, the release copy is always authoritative and is
copied as-is to the output directory.  No line-by-line merge is attempted.

Semantic diff (audit mode) is handled by
``configmerge.auditor.sstp_parser`` and ``AuditEngine._compare_sstp()``.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import List

from ..models import MergeConfig, ReportEntry, EntryType
from ..logger import log_structured
from . import register, BaseProcessor


@register(".sstp")
class SstpProcessor(BaseProcessor):
    """Copy-only processor for ``.sstp`` routing rule files.

    Release file always wins (routing rules are auto-generated, so the
    release version supersedes any production copy).
    """

    def process(
        self,
        base_files: List[str],
        rel_file: str,
        out_file: str,
        config: MergeConfig,
        logger: logging.Logger,
    ) -> List[ReportEntry]:
        if not os.path.isfile(rel_file):
            log_structured(logger, "ERROR", "SSTP", "RELEASE_MISSING",
                           rel_file, "", "release file missing — skipped")
            return [ReportEntry(
                type=EntryType.PROCESSOR_ERROR,
                file=rel_file,
                element="",
                old="FULL_FILE",
                new="",
            )]

        if not config.dry_run:
            os.makedirs(os.path.dirname(out_file), exist_ok=True)
            shutil.copy2(rel_file, out_file)
            logger.info("[SSTP] copied release → %s", out_file)

        return [ReportEntry(
            type=EntryType.SSTP_RELEASE_COPIED,
            file=rel_file,
            element="",
            old="FULL_FILE",
            new="FROM_RELEASE",
        )]
