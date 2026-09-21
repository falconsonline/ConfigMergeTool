"""
configmerge.auditor.fetcher
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
NodeFetcher abstraction — translates a BaseDirConfig into a local directory
path that AuditEngine can scan with os.walk.

For local nodes (the default), files are already on disk and no transfer
is needed.  For remote nodes (Phase 11), an SSHNodeFetcher implementation
copies files to a temporary directory and returns that path.

Usage in AuditEngine::

    fetcher = LocalNodeFetcher()   # default
    for node in self.nodes:
        node.local_path = fetcher.fetch(node)
    try:
        ...  # run audit
    finally:
        fetcher.cleanup()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..models import BaseDirConfig


class NodeFetcher(ABC):
    """Translates a BaseDirConfig into a local directory path the engine can scan."""

    @abstractmethod
    def fetch(self, node: "BaseDirConfig") -> str:
        """Ensure all files for *node* are accessible at a local path.

        Returns the local directory path.
        - Local nodes: returns ``node.local_path`` (resolved base_dir).
        - Remote nodes: copies files to a temp dir and returns that.
        """

    @abstractmethod
    def cleanup(self) -> None:
        """Remove any temp directories created during fetch.  Called by engine on exit."""


class LocalNodeFetcher(NodeFetcher):
    """Default fetcher — node files are already on the local filesystem."""

    def fetch(self, node: "BaseDirConfig") -> str:
        return node.local_path

    def cleanup(self) -> None:
        pass  # nothing to clean up for local nodes
