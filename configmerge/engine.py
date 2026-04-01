"""
configmerge.engine
~~~~~~~~~~~~~~~~~~
MergeEngine — top-level orchestrator.

Single-base usage (backward compat):
    from configmerge import MergeEngine, MergeConfig
    config = MergeConfig(base_dir="base", release_dirs=["release"], output_dir="output")
    results = MergeEngine(config).run()   # returns List[MergeResult]

Multi-base usage (one pass per production node):
    config = MergeConfig(
        release_dirs=["release"], output_dir="output",
        base_configs=[
            BaseDirConfig("node1", mapping_file="map1.txt"),
            BaseDirConfig("node2"),
        ],
    )
    results = MergeEngine(config).run()
"""

from __future__ import annotations

import os
import logging
import shutil
from typing import List, Optional

from .models import BaseDirConfig, MergeConfig, MergeResult, EntryType, FileProcessResult
from .logger import setup_logging, important, log_structured
from .utils import copy_file, ensure_dir
from .matcher import FileMatcher
from .processors import PROCESSOR_REGISTRY, BaseProcessor
from .processors.generic import GenericProcessor
from .reporter.excel import write_excel
from .reporter.html_reporter import write_html


class MergeEngine:
    """
    Orchestrates the full merge pipeline.  Iterates over every BaseDirConfig
    in config.base_configs (synthesised from base_dir for single-base runs).

    run() returns List[MergeResult] — one result per base directory.
    """

    def __init__(
        self,
        config: MergeConfig,
        logger: Optional[logging.Logger] = None,
        log_dir: str = "logs",
        report_dir: str = "reports",
    ):
        from datetime import datetime
        self.config  = config
        run_ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Single run directory: all logs, Excel files, and HTML land here.
        # log_dir is accepted for backward compat but ignored — everything
        # goes into run_dir so the user can zip one folder per run.
        self.run_dir    = os.path.join(report_dir, f"run_{run_ts}")
        self.report_dir = report_dir   # kept for reference; not used for sub-dirs
        os.makedirs(self.run_dir, exist_ok=True)
        self.logger  = logger or setup_logging(config.verbose, self.run_dir)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> List[MergeResult]:
        config = self.config
        logger = self.logger
        multi  = len(config.base_configs) > 1

        important(
            f"[RELEASE DIRS]: {', '.join(config.release_dirs)}  "
            f"[OUTPUT DIR]: {config.output_dir}  "
            f"[BASES]: {len(config.base_configs)}",
            logger,
        )
        if config.dry_run:
            logger.info("[DRY-RUN] No files will be written")

        all_results: List[MergeResult] = []

        for bdc in config.base_configs:
            result = self._run_one_base(bdc, multi)
            all_results.append(result)

        # ── Combined HTML report ─────────────────────────────────────────
        html_path = write_html(all_results, config, self.run_dir)
        important(f"[REPORT HTML] {html_path}", logger)

        total = sum(len(r.report) for r in all_results)
        important(f"[SUMMARY] Total changes across all bases: {total}", logger)

        return all_results

    # ------------------------------------------------------------------
    # Per-base pipeline
    # ------------------------------------------------------------------

    def _run_one_base(self, bdc: BaseDirConfig, multi: bool) -> MergeResult:
        config = self.config
        logger = self.logger

        # Output config files go into per-base subdirs (multi) or root (single)
        if multi:
            base_output_dir = os.path.join(config.output_dir, bdc.name)
        else:
            base_output_dir = config.output_dir
        # All report/log artifacts always go into the shared run_dir
        base_report_dir = self.run_dir

        important(
            f"[BASE] {bdc.name}  dir={bdc.base_dir}  output={base_output_dir}",
            logger,
        )

        if not config.dry_run:
            self._clean_dir(base_output_dir)

        # Build a single-base MergeConfig for FileMatcher
        base_config = MergeConfig(
            release_dirs   = config.release_dirs,
            output_dir     = base_output_dir,
            base_dir       = bdc.base_dir,
            mapping_file   = bdc.mapping_file,
            copy_only_file = bdc.copy_only_file,
            exclude_base_only = config.exclude_base_only,
            dry_run        = config.dry_run,
            verbose        = config.verbose,
        )

        result = MergeResult(base_name=bdc.name, base_dir=bdc.base_dir)

        # ── File matching ────────────────────────────────────────────────
        matcher = FileMatcher(base_config, logger)
        result.base_only_files    = matcher.base_files - {
            m.base_paths[0] for m in matcher.matches if m.base_paths
        }
        result.release_only_files = {
            m.rel_path for m in matcher.matches if not m.base_paths and not m.ambiguous
        }
        result.multi_base_mappings = matcher.multi_base_mappings

        for m in matcher.matches:
            if m.mapped and m.base_paths:
                for bp in m.base_paths:
                    result.file_mappings.append((bp, m.rel_path))

        # ── Copy-only files ──────────────────────────────────────────────
        for rel_path in matcher.copy_only:
            base_candidate = os.path.join(matcher.base_dir, rel_path)
            if not os.path.exists(base_candidate):
                log_structured(logger, "WARNING", "COPY_ONLY", "MISSING",
                               rel_path, "", "base file not found — skipped")
                continue
            out_file = os.path.join(base_output_dir, rel_path)
            if not config.dry_run:
                copy_file(base_candidate, out_file, logger)
            result.copy_only_files.append(rel_path)
            result.base_only_files.discard(rel_path)

        # ── Process matched files ────────────────────────────────────────
        for file_match in matcher.matches:
            if not file_match.base_paths or file_match.ambiguous:
                continue

            rel_file = self._resolve_rel_abs(file_match.rel_path, config.release_dirs)
            if not rel_file:
                continue

            base_files = [
                os.path.join(matcher.base_dir, bp)
                for bp in file_match.base_paths
                if os.path.exists(os.path.join(matcher.base_dir, bp))
            ]
            if not base_files:
                continue

            out_rel  = file_match.rel_path if file_match.mapped else file_match.base_paths[0]
            out_file = os.path.join(base_output_dir, out_rel)

            ext = os.path.splitext(file_match.rel_path)[1].lower()
            processor_cls = PROCESSOR_REGISTRY.get(ext)
            processor: BaseProcessor = (
                processor_cls() if processor_cls else GenericProcessor()
            )

            try:
                entries = processor.process(
                    base_files, rel_file, out_file, base_config, logger
                )
            except Exception as e:
                log_structured(logger, "ERROR", "ENGINE", "PROCESSOR_FAILED",
                               file_match.rel_path, "", str(e))
                important(
                    f"[ERROR] Processor failed for {file_match.rel_path}: {e}", logger
                )
                result.failed_files.append(FileProcessResult(
                    rel_path=file_match.rel_path,
                    success=False,
                    error=str(e),
                ))
                entries = []

            for entry in entries:
                if entry.type == EntryType.EXCLUDED_BASE_ONLY_PARAMETER:
                    result.excluded_params.append(entry)
                else:
                    result.report.append(entry)

            for bp in file_match.base_paths:
                result.base_only_files.discard(bp)

            # Store release + merged output content for HTML "Show Full Config" diff view.
            # Diff direction: release (before merge) → output (after merge).
            # Key = rel_file (must match entry.file set by processors).
            # On dry-run, use the release file as the output proxy (nothing was written).
            content_source = out_file if (not config.dry_run and os.path.exists(out_file)) else rel_file
            try:
                with open(content_source, encoding="utf-8-sig") as f:
                    result.output_contents[rel_file] = f.read()
            except Exception:
                pass
            try:
                with open(rel_file, encoding="utf-8-sig") as f:
                    result.release_contents[rel_file] = f.read()
            except Exception:
                pass

        # ── Per-base Excel report ────────────────────────────────────────
        xlsx_path = write_excel(result, base_config, base_report_dir, bdc.name)
        important(f"[REPORT XLSX] {xlsx_path}", logger)
        important(
            f"[SUMMARY:{bdc.name}] changes={len(result.report)} "
            f"errors={len(result.failed_files)}",
            logger,
        )

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clean_dir(self, path: str) -> None:
        if os.path.exists(path):
            self.logger.info(f"[CLEANUP] Removing: {path}")
            shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)
        self.logger.info(f"[CLEANUP] Ready: {path}")

    def _resolve_rel_abs(self, rel_path: str, release_dirs: list) -> str | None:
        for d in release_dirs:
            candidate = os.path.join(os.path.normpath(d), rel_path)
            if os.path.exists(candidate):
                return candidate
        return None
