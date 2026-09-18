"""
configmerge.workflows.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~
WorkflowBase — abstract contract for all audit workflow implementations.

A workflow is responsible for:
  1. Obtaining config files (local, SSH, email attachment)
  2. Running AuditEngine
  3. Delivering the report (save to disk, send email, etc.)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..auditor.engine import AuditResult


class WorkflowBase(ABC):
    """Base class for all audit workflows."""

    @abstractmethod
    def run(self) -> "AuditResult":
        """Execute the full workflow: fetch → audit → return result."""

    @abstractmethod
    def deliver(self, result: "AuditResult", report_path: str) -> None:
        """Deliver the completed report (write to disk, send email, etc.)."""
