"""
configmerge.auditor
~~~~~~~~~~~~~~~~~~~
Audit mode: compare configurations across multiple site nodes (base dirs)
to detect configuration drift without needing a release directory.

Usage:
    from configmerge.auditor import AuditEngine, AuditResult
    from configmerge.models import BaseDirConfig

    nodes = [
        BaseDirConfig(base_dir="singtel/APP-01", name="App01"),
        BaseDirConfig(base_dir="singtel/APP-02", name="App02"),
    ]
    result = AuditEngine(nodes, report_dir="reports").run()
"""

from .engine      import AuditEngine, AuditResult
from .patch       import AuditPatcher
from .file_filter import FileFilter

__all__ = ["AuditEngine", "AuditResult", "AuditPatcher", "FileFilter"]
