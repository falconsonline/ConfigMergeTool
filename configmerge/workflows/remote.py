"""
configmerge.workflows.remote
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
SSHNodeFetcher — fetch config files from a remote node over SSH/SFTP.

STATUS: STUB — not yet implemented.  Will be implemented in Phase 11.

To use once implemented::

    pip install "configmergetool[ssh]"

Then in your audit config JSON::

    {
      "base_dir": "/opt/Roamware/binaries/gtpproxy/config",
      "name": "GTPProxy-APP01",
      "remote": {
        "host": "10.253.47.147",
        "port": 22,
        "username": "roamware",
        "key_file": "~/.ssh/prod_key"
      }
    }

And run::

    configmergetool --audit-config-file audit.json --remote-audit
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import List, TYPE_CHECKING

from ..auditor.fetcher import NodeFetcher

if TYPE_CHECKING:
    from ..models import BaseDirConfig


class SSHNodeFetcher(NodeFetcher):
    """
    Fetch config files from a remote node over SSH/SFTP.

    Requires: pip install paramiko  (declared as [ssh] optional extra)

    This class is a STUB.  The interface is finalised; the implementation
    will be added in Phase 11 once paramiko integration is tested against
    a live environment.
    """

    def __init__(self) -> None:
        self._temp_dirs: List[str] = []

    def fetch(self, node: "BaseDirConfig") -> str:
        """Copy remote files to a temp directory and return the local path."""
        # Verify paramiko is available before attempting anything
        try:
            import paramiko  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "SSHNodeFetcher requires paramiko: "
                "pip install \"configmergetool[ssh]\""
            )
        raise NotImplementedError(
            "SSHNodeFetcher.fetch() — Phase 11: implement SSH/SFTP file transfer"
        )

    def cleanup(self) -> None:
        """Remove all temporary directories created during this session."""
        for tmpdir in self._temp_dirs:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
        self._temp_dirs.clear()
