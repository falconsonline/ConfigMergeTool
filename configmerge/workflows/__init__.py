"""
configmerge.workflows
~~~~~~~~~~~~~~~~~~~~~
Workflow layer — responsible for obtaining config files (local disk, SSH,
email attachment) and delivering the audit report (disk, email, etc.).

Current implementations:
  - LocalNodeFetcher (default, no install required)

Future implementations (scaffolded as stubs):
  - SSHNodeFetcher   — pip install "configmergetool[ssh]"
  - EmailAuditWorkflow — pip install "configmergetool[email]"
"""

from .base import WorkflowBase

__all__ = ["WorkflowBase"]
