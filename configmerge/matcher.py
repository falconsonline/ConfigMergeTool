"""
configmerge.matcher
~~~~~~~~~~~~~~~~~~~
Resolves which base file(s) correspond to each release file.

Matching priority (per release file):
  1. Explicit entry in --mapping-file  (Many-to-One: multiple bases → 1 release)
  2. Same relative path exists in base dir
  3. Filename-only match (skipped if ambiguous)

Path-traversal guard applied to all resolved paths.
"""

from __future__ import annotations
import os
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .models import FileMatch, MergeConfig
from .logger import log_structured
from .utils import safe_realpath


class FileMatcher:
    """
    Build the full file matching map given a MergeConfig.

    After construction:
        self.matches          — List[FileMatch] for all release files
        self.base_files       — Set[str] of all base rel-paths
        self.rel_files        — Set[str] of all release rel-paths
        self.copy_only        — Set[str] of base rel-paths to copy as-is
        self.multi_base_mappings  — List[(release_path, [base_paths])]
                                    entries where >1 base maps to same release
        self.ambiguous_base   — List[(base_path, [release_paths])]
                                    entries where 1 base maps to >1 release
    """

    def __init__(self, config: MergeConfig, logger: logging.Logger):
        self.config  = config
        self.logger  = logger
        self.base_dir = os.path.normpath(config.base_dir)

        self.base_files: Set[str]  = set()
        self.rel_files:  Set[str]  = set()
        self.copy_only:  Set[str]  = set()

        self.multi_base_mappings:  List[Tuple[str, List[str]]] = []
        self.ambiguous_base:       List[Tuple[str, List[str]]] = []

        self._base_name_index:   Dict[str, List[str]] = defaultdict(list)
        # release_rel → [base_rels]  (from mapping file)
        self._mapping_lookup:    Dict[str, List[str]] = defaultdict(list)

        self.matches: List[FileMatch] = []

        self._index_base()
        self._load_copy_only()
        self._load_mapping()
        self._resolve_matches()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _index_base(self) -> None:
        base_real = os.path.realpath(self.base_dir)
        for root, dirs, files in os.walk(self.base_dir, followlinks=False):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for f in files:
                abs_path = os.path.join(root, f)
                # Symlink guard
                if os.path.realpath(abs_path) == abs_path or \
                        os.path.realpath(abs_path).startswith(base_real + os.sep):
                    rel = os.path.normpath(os.path.relpath(abs_path, self.base_dir))
                    self.base_files.add(rel)
                    self._base_name_index[f].append(rel)

    def _load_copy_only(self) -> None:
        path = self.config.copy_only_file
        if not path:
            return
        base_name = os.path.basename(self.base_dir)
        base_dir_norm = os.path.normpath(self.base_dir)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                norm = os.path.normpath(line)
                if os.path.isabs(norm):
                    rel = os.path.relpath(norm, self.base_dir)
                elif norm.startswith(base_dir_norm + os.sep):
                    # full base_dir prefix: singtel/Singtel-APP-01/config/file.xml
                    rel = os.path.relpath(norm, base_dir_norm)
                elif norm.startswith(base_name + os.sep):
                    # base dir name prefix: Singtel-APP-01/config/file.xml
                    rel = norm.split(os.sep, 1)[1]
                else:
                    rel = norm
                rel = os.path.normpath(rel)
                # path-traversal guard
                if safe_realpath(self.base_dir, rel) is None:
                    log_structured(self.logger, "WARNING", "COPY_ONLY", "PATH_TRAVERSAL",
                                   rel, "", "skipped — path escapes base dir")
                    continue
                self.copy_only.add(rel)

    def _load_mapping(self) -> None:
        """
        Parse mapping file.  Format:  base_path = release_path
        Supports Many-to-One: multiple base lines may share the same release path.
        Detects one-base → many-release (ambiguous base) and flags it.
        """
        path = self.config.mapping_file
        if not path:
            return

        # raw pairs as parsed
        raw_pairs: List[Tuple[str, str]] = []

        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                base_raw, rel_raw = line.split("=", 1)
                raw_pairs.append((base_raw.strip(), rel_raw.strip()))

        base_dir_name = os.path.basename(self.base_dir)

        # normalize each pair
        for base_raw, rel_raw in raw_pairs:
            base_norm = self._normalise_base_path(base_raw, base_dir_name)
            rel_norm  = self._normalise_rel_path(rel_raw)

            if base_norm is None or rel_norm is None:
                continue

            # path-traversal guard on base side
            if safe_realpath(self.base_dir, base_norm) is None:
                log_structured(self.logger, "WARNING", "MAPPING", "PATH_TRAVERSAL",
                               base_norm, "", "skipped — path escapes base dir")
                continue

            self._mapping_lookup[rel_norm].append(base_norm)

        # detect ambiguous base (one base → many releases)
        base_to_releases: Dict[str, List[str]] = defaultdict(list)
        for rel_norm, base_list in self._mapping_lookup.items():
            for b in base_list:
                base_to_releases[b].append(rel_norm)

        for base, releases in base_to_releases.items():
            if len(releases) > 1:
                self.ambiguous_base.append((base, releases))
                log_structured(self.logger, "WARNING", "MAPPING", "AMBIGUOUS_BASE",
                               base, "", f"maps to multiple release files: {releases}")

        # detect multi-base (many bases → one release)
        for rel_norm, base_list in self._mapping_lookup.items():
            if len(base_list) > 1:
                self.multi_base_mappings.append((rel_norm, base_list))
                log_structured(self.logger, "INFO", "MAPPING", "MULTI_BASE",
                               rel_norm, "", f"has {len(base_list)} base files mapped")

    def _normalise_base_path(self, raw: str, base_dir_name: str) -> Optional[str]:
        norm = os.path.normpath(raw)
        if os.path.isabs(norm):
            return os.path.relpath(norm, self.base_dir)
        if norm.startswith(self.base_dir + os.sep):
            return os.path.relpath(norm, self.base_dir)
        if norm.startswith(base_dir_name + os.sep):
            return norm.split(os.sep, 1)[1]
        return norm

    def _normalise_rel_path(self, raw: str) -> Optional[str]:
        norm = os.path.normpath(raw)
        for rd in self.config.release_dirs:
            rd_norm = os.path.normpath(rd)
            rd_name = os.path.basename(rd_norm)
            if norm.startswith(rd_norm + os.sep):
                return os.path.relpath(norm, rd_norm)
            if norm.startswith(rd_name + os.sep):
                return norm.split(os.sep, 1)[1]
        # strip leading ./
        return norm.lstrip("." + os.sep)

    def _resolve_matches(self) -> None:
        for d in self.config.release_dirs:
            d = os.path.normpath(d)
            d_real = os.path.realpath(d)
            # followlinks=False prevents infinite loops from circular symlinks
            for root, dirs, files in os.walk(d, followlinks=False):
                # Skip hidden directories (e.g. .git, .svn)
                dirs[:] = [x for x in dirs if not x.startswith(".")]
                for f in files:
                    abs_path = os.path.join(root, f)

                    # Path-traversal guard on release side (handles symlinked files)
                    real_abs = os.path.realpath(abs_path)
                    if not real_abs.startswith(d_real + os.sep) and real_abs != d_real:
                        log_structured(self.logger, "WARNING", "FILE", "PATH_TRAVERSAL",
                                       abs_path, "", "skipped — resolves outside release dir")
                        continue

                    rel_path = os.path.normpath(os.path.relpath(abs_path, d))
                    self.rel_files.add(rel_path)

                    base_paths: List[str] = []
                    mapped = False
                    ambiguous = False

                    # 1. Explicit mapping
                    mapped_bases = (
                        self._mapping_lookup.get(rel_path) or
                        self._mapping_lookup.get(f)
                    )
                    if mapped_bases:
                        for bp in mapped_bases:
                            candidate = os.path.join(self.base_dir, bp)
                            if os.path.exists(candidate):
                                base_paths.append(bp)
                            else:
                                log_structured(self.logger, "WARNING", "MAPPING", "BASE_MISSING",
                                               bp, "", "mapped base file not found")
                        mapped = bool(base_paths)

                    # 2. Same relative path
                    if not base_paths:
                        candidate = os.path.join(self.base_dir, rel_path)
                        if os.path.exists(candidate):
                            base_paths.append(rel_path)

                    # 3. Filename-only fallback
                    if not base_paths:
                        candidates_by_name = self._base_name_index.get(f, [])
                        if len(candidates_by_name) == 1:
                            base_paths.append(candidates_by_name[0])
                        elif len(candidates_by_name) > 1:
                            log_structured(self.logger, "WARNING", "FILE", "AMBIGUOUS_MATCH",
                                           rel_path, f, f"candidates={candidates_by_name}")
                            ambiguous = True

                    if not base_paths and not ambiguous:
                        log_structured(self.logger, "WARNING", "FILE", "NO_MATCH",
                                       rel_path, f, "no matching file in base")

                    self.matches.append(FileMatch(
                        rel_path=rel_path,
                        base_paths=base_paths,
                        mapped=mapped,
                        ambiguous=ambiguous,
                        release_dir=d,
                    ))
