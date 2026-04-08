"""
configmerge.workflows.email_workflow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
EmailAuditWorkflow — email-triggered audit workflow.

STATUS: STUB — not yet implemented.  Will be implemented in Phase 12.

To use once implemented::

    pip install "configmergetool[email]"

Trigger
-------
An unread email whose subject contains the configured filter string arrives
in the monitored IMAP mailbox.

Input
-----
Email attachment: a zip file structured as::

    audit_configs.zip
    ├── APP-01/
    │   ├── fsmapp.properties
    │   └── GTPProxy.cfg
    └── APP-02/
        ├── fsmapp.properties
        └── GTPProxy.cfg

Each top-level directory inside the zip becomes one audit node.  The node
name is taken from the directory name.

Output
------
A reply email is sent via SMTP to the original sender (subject must be in the
``from_whitelist``).  The body contains a plain-text summary table; the
``audit_report.html`` is attached.

Email config JSON (separate from the per-run audit config)::

    {
      "imap": {
        "host": "mail.company.com",
        "port": 993,
        "username": "audit@company.com",
        "password_env": "AUDIT_EMAIL_PASS"
      },
      "smtp": {
        "host": "mail.company.com",
        "port": 587
      },
      "filter": {
        "subject_contains": "[AUDIT REQUEST]",
        "from_whitelist": ["ops@company.com", "noc@company.com"]
      },
      "audit_config_template": "audit-template.json"
    }

Security
--------
* Sender whitelist is enforced — emails from unlisted senders are ignored.
* No code is executed from email content.
* Passwords are never stored in config files — use ``password_env`` to name
  the environment variable that holds the password.
* Processed emails are marked as read and moved to an ``[Processed]`` IMAP
  folder to prevent re-processing.

CLI usage (once implemented)::

    configmergetool --email-config email.json
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import WorkflowBase

if TYPE_CHECKING:
    from ..auditor.engine import AuditResult


class EmailAuditWorkflow(WorkflowBase):
    """
    Email-triggered audit workflow.

    Requires: pip install imapclient  (declared as [email] optional extra)

    This class is a STUB.  The interface is finalised; the implementation
    will be added in Phase 12 once imapclient/SMTP integration is tested
    against a live mail server.
    """

    def __init__(self, email_config_path: str) -> None:
        """
        Parameters
        ----------
        email_config_path:
            Path to the email config JSON file (see module docstring for format).
        """
        # Verify imapclient is available before attempting anything
        try:
            import imapclient  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "EmailAuditWorkflow requires imapclient: "
                "pip install \"configmergetool[email]\""
            )
        self._email_config_path = email_config_path

    def run(self) -> "AuditResult":
        """
        Poll the IMAP mailbox, extract the attached zip, run AuditEngine,
        and return the result.

        Implementation steps (Phase 12):
          1. Connect to IMAP server using credentials from env var.
          2. Search for unread emails matching subject filter and from_whitelist.
          3. For each matching email:
             a. Download zip attachment.
             b. Extract to a per-run temp directory;
                each top-level subdirectory becomes a BaseDirConfig node.
             c. Build AuditEngine with LocalNodeFetcher (files are already local
                after extraction — no SSH needed).
             d. Run engine; collect AuditResult.
             e. Mark email as read; move to [Processed] IMAP folder.
             f. Call deliver() to send reply with report attached.
          4. Return last AuditResult (or combined result if multiple emails).
        """
        raise NotImplementedError(
            "EmailAuditWorkflow.run() — Phase 12: implement IMAP polling and "
            "attachment extraction"
        )

    def deliver(self, result: "AuditResult", report_path: str) -> None:
        """
        Send a reply email with the audit report attached.

        Implementation steps (Phase 12):
          1. Connect to SMTP server.
          2. Build reply:
             - Subject: "Re: [AUDIT REQUEST] <original subject>"
             - Body (plain text): summary table from result.to_dict()
               including total_mismatches, files_compared, files_with_diffs.
             - Attachment: report_path (audit_report.html).
          3. Send to original sender (already verified in from_whitelist).
        """
        raise NotImplementedError(
            "EmailAuditWorkflow.deliver() — Phase 12: implement SMTP reply"
        )
