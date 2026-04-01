"""
configmerge
~~~~~~~~~~~
Public API.

Single-base:
    from configmerge import MergeEngine, MergeConfig
    config  = MergeConfig(base_dir="base", release_dirs=["release"], output_dir="output")
    results = MergeEngine(config).run()   # List[MergeResult]

Multi-base:
    from configmerge import MergeEngine, MergeConfig, BaseDirConfig
    config  = MergeConfig(
        release_dirs=["release"], output_dir="output",
        base_configs=[BaseDirConfig("node1"), BaseDirConfig("node2")],
    )
    results = MergeEngine(config).run()
"""

from .models import BaseDirConfig, MergeConfig, MergeResult, ReportEntry, EntryType
from .engine import MergeEngine

__all__ = [
    "MergeEngine", "MergeConfig", "BaseDirConfig",
    "MergeResult", "ReportEntry", "EntryType",
]
