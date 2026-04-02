"""
configmerge.models
~~~~~~~~~~~~~~~~~~
Shared dataclasses used across the entire package.
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Per-base-directory configuration
# ---------------------------------------------------------------------------

@dataclass
class BaseDirConfig:
    """
    Configuration for a single base (production/node) directory.

    Multiple BaseDirConfig entries can be supplied to MergeConfig.base_configs
    to run an independent merge pass per node/environment, with each base
    having its own optional mapping file and copy-only list.
    """
    base_dir: str
    mapping_file: Optional[str] = None
    copy_only_file: Optional[str] = None
    name: str = ""   # display name; auto-derived from base_dir basename if empty

    def __post_init__(self) -> None:
        if not self.name:
            self.name = os.path.basename(os.path.normpath(self.base_dir))
        errors: List[str] = []
        if not self.base_dir or not self.base_dir.strip():
            errors.append("base_dir must not be empty")
        elif not os.path.isdir(self.base_dir):
            errors.append(
                f"base_dir does not exist or is not a directory: {self.base_dir!r}"
            )
        if self.mapping_file and not os.path.isfile(self.mapping_file):
            errors.append(f"mapping_file does not exist: {self.mapping_file!r}")
        if self.copy_only_file and not os.path.isfile(self.copy_only_file):
            errors.append(f"copy_only_file does not exist: {self.copy_only_file!r}")
        if errors:
            raise ValueError(
                "BaseDirConfig validation failed:\n  " + "\n  ".join(errors)
            )


# ---------------------------------------------------------------------------
# Configuration (input to MergeEngine)
# ---------------------------------------------------------------------------

@dataclass
class MergeConfig:
    """
    Top-level merge configuration.

    Single-base mode (backward compat):
        MergeConfig(base_dir="base", release_dirs=["rel"], output_dir="out")

    Multi-base mode (one pass per node/environment):
        MergeConfig(
            release_dirs=["rel"], output_dir="out",
            base_configs=[
                BaseDirConfig(base_dir="node1", mapping_file="map1.txt"),
                BaseDirConfig(base_dir="node2"),
            ],
        )
    """
    release_dirs: List[str]
    output_dir: str
    # -- single-base convenience fields (used when base_configs is empty) --
    base_dir: str = ""
    mapping_file: Optional[str] = None
    copy_only_file: Optional[str] = None
    # -- multi-base --
    base_configs: List[BaseDirConfig] = field(default_factory=list)
    # -- common --
    exclude_base_only: bool = False
    dry_run: bool = False
    verbose: bool = False
    three_way_diff: bool = True    # always-on: 3-way Base|Release|Output diff in HTML

    def __post_init__(self) -> None:
        errors: List[str] = []

        # Validate release dirs
        if not self.release_dirs:
            errors.append("release_dirs must contain at least one directory")
        else:
            for d in self.release_dirs:
                if not os.path.isdir(d):
                    errors.append(
                        f"release_dir does not exist or is not a directory: {d!r}"
                    )

        if not self.output_dir or not self.output_dir.strip():
            errors.append("output_dir must not be empty")

        # If base_configs supplied directly, skip single-base validation
        if self.base_configs:
            if errors:
                raise ValueError(
                    "MergeConfig validation failed:\n  " + "\n  ".join(errors)
                )
            return

        # Single-base path: validate and synthesize base_configs
        if not self.base_dir or not self.base_dir.strip():
            errors.append("either base_dir or base_configs must be provided")
        elif not os.path.isdir(self.base_dir):
            errors.append(
                f"base_dir does not exist or is not a directory: {self.base_dir!r}"
            )
        else:
            if self.mapping_file and not os.path.isfile(self.mapping_file):
                errors.append(f"mapping_file does not exist: {self.mapping_file!r}")
            if self.copy_only_file and not os.path.isfile(self.copy_only_file):
                errors.append(
                    f"copy_only_file does not exist: {self.copy_only_file!r}"
                )

        if errors:
            raise ValueError(
                "MergeConfig validation failed:\n  " + "\n  ".join(errors)
            )

        # Synthesize a single BaseDirConfig for uniform engine handling
        self.base_configs = [
            BaseDirConfig(
                base_dir=self.base_dir,
                mapping_file=self.mapping_file,
                copy_only_file=self.copy_only_file,
            )
        ]


# ---------------------------------------------------------------------------
# Report entry (one per parameter/element change)
# ---------------------------------------------------------------------------

@dataclass
class ReportEntry:
    type: str           # EntryType constant
    file: str           # relative output path
    element: str        # parameter name / XPath / JSON key path
    old: str            # release value (what was there before merge)
    new: str            # merged value (what ended up in output)
    recommended: str = ""        # for EMPTY_BASE_OVERRIDE: original release value is recommended
    base_comment: str = ""       # comment from base file for this element
    release_comment: str = ""    # comment from release file for this element
    section: str = ""            # KV section, if applicable


# ---------------------------------------------------------------------------
# File match (one per release file processed)
# ---------------------------------------------------------------------------

@dataclass
class FileMatch:
    rel_path: str                    # relative path within release dir
    base_paths: List[str]            # one or more matched base file rel-paths
    mapped: bool = False             # True if resolved via --mapping-file
    ambiguous: bool = False          # True if multiple base candidates (no mapping)
    release_dir: str = ""            # which release dir this file came from


# ---------------------------------------------------------------------------
# Per-file processing result (used inside engine before aggregating)
# ---------------------------------------------------------------------------

@dataclass
class FileProcessResult:
    rel_path: str
    success: bool
    entries: List[ReportEntry] = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------------------
# Per-base-run result
# ---------------------------------------------------------------------------

@dataclass
class MergeResult:
    """Result for a single base-directory merge pass."""
    report: List[ReportEntry] = field(default_factory=list)
    base_only_files: Set[str] = field(default_factory=set)
    release_only_files: Set[str] = field(default_factory=set)
    copy_only_files: List[str] = field(default_factory=list)
    file_mappings: List[Tuple[str, str]] = field(default_factory=list)   # (base, release)
    multi_base_mappings: List[Tuple[str, List[str]]] = field(default_factory=list)
    excluded_params: List[ReportEntry] = field(default_factory=list)
    failed_files: List[FileProcessResult] = field(default_factory=list)
    # Full file contents for HTML diff views
    # 2-way diff:  release (before merge) → output (after merge)
    # 3-way diff:  base | release | output
    output_contents:  Dict[str, str] = field(default_factory=dict)  # rel_file → merged output text
    release_contents: Dict[str, str] = field(default_factory=dict)  # rel_file → original release text
    base_contents:    Dict[str, str] = field(default_factory=dict)  # rel_file → original base text
    # Which BaseDirConfig produced this result
    base_name: str = ""
    base_dir: str = ""

    def summary(self) -> Dict[str, int]:
        """Return a count dict of each entry type for display."""
        counts: Dict[str, int] = {}
        for e in self.report:
            counts[e.type] = counts.get(e.type, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Report entry type constants
# ---------------------------------------------------------------------------

class EntryType:
    BASE_TO_RELEASE_REPLACED            = "BASE_TO_RELEASE_REPLACED"
    XML_BASE_TO_RELEASE_REPLACED        = "XML_BASE_TO_RELEASE_REPLACED"
    JSON_BASE_TO_RELEASE_REPLACED       = "JSON_BASE_TO_RELEASE_REPLACED"
    LOGROTATE_BASE_TO_RELEASE_REPLACED  = "LOGROTATE_BASE_TO_RELEASE_REPLACED"
    BASE_ONLY_PARAMETER_ADDED           = "BASE_ONLY_PARAMETER_ADDED"
    RELEASE_ONLY_PARAMETER_ADDED        = "RELEASE_ONLY_PARAMETER_ADDED"
    EXCLUDED_BASE_ONLY_PARAMETER        = "EXCLUDED_BASE_ONLY_PARAMETER"
    EMPTY_BASE_OVERRIDE                 = "EMPTY_BASE_OVERRIDE"
    EMPTY_BASE_OVERRIDE_XML             = "EMPTY_BASE_OVERRIDE_XML"
    JSON_EMPTY_BASE_OVERRIDE            = "JSON_EMPTY_BASE_OVERRIDE"
    LOGROTATE_EMPTY_BASE_OVERRIDE       = "LOGROTATE_EMPTY_BASE_OVERRIDE"
    DUPLICATE_KEY                       = "DUPLICATE_KEY"
    INVALID_JSON                        = "INVALID_JSON"
    INVALID_OUTPUT_JSON                 = "INVALID_OUTPUT_JSON"
    FILE_MAPPING                        = "FILE_MAPPING"
    BASE_ONLY_FILE_COPIED               = "BASE_ONLY_FILE_COPIED"
    UNCOMMENT_REPLACE                   = "UNCOMMENT_REPLACE"
    INDEXED_GROUP_RENUMBERED            = "INDEXED_GROUP_RENUMBERED"
    INDEXED_GROUP_APPENDED              = "INDEXED_GROUP_APPENDED"
    COMMA_VALUE_UNION                   = "COMMA_VALUE_UNION"
    NAMESPACE_ADAPTED                   = "NAMESPACE_ADAPTED"
    PROCESSOR_ERROR                     = "PROCESSOR_ERROR"

    # All types that should trigger a non-zero exit code in CI
    CRITICAL_TYPES: Set[str] = {
        EMPTY_BASE_OVERRIDE, EMPTY_BASE_OVERRIDE_XML, JSON_EMPTY_BASE_OVERRIDE,
        LOGROTATE_EMPTY_BASE_OVERRIDE, INVALID_JSON, INVALID_OUTPUT_JSON,
        PROCESSOR_ERROR,
    }
