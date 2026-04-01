"""
configmerge.processors.generic
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Fallback processor for unrecognised file types — copies release file as-is.
"""

from __future__ import annotations

import logging
from typing import List

from . import BaseProcessor
from ..models import MergeConfig, ReportEntry
from ..utils import copy_file


class GenericProcessor(BaseProcessor):

    def process(
        self,
        base_files: List[str],
        rel_file: str,
        out_file: str,
        config: MergeConfig,
        logger: logging.Logger,
    ) -> List[ReportEntry]:
        logger.info(f"[GENERIC] copy {rel_file}")
        if not config.dry_run:
            copy_file(rel_file, out_file, logger)
        return []
