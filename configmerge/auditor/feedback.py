"""
configmerge.auditor.feedback
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Cross-run feedback accumulator (Phase 5.3).

Each audit run appends a summary record to
``~/.configmergetool/feedback_history.json``.  This module provides helpers
to read and display that history.

CLI usage::

    configmergetool feedback --summary
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List


_HISTORY_PATH = pathlib.Path.home() / ".configmergetool" / "feedback_history.json"


def load_history() -> Dict[str, Any]:
    """Return the full feedback history dict, or an empty skeleton."""
    if not _HISTORY_PATH.exists():
        return {"runs": []}
    try:
        with open(str(_HISTORY_PATH), encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "runs" not in data:
            return {"runs": []}
        return data
    except Exception:
        return {"runs": []}


def print_summary() -> None:
    """Print a human-readable summary of all recorded runs."""
    history = load_history()
    runs: List[dict] = history.get("runs", [])

    if not runs:
        print("No feedback history found. Run an audit first.")
        return

    total_runs      = len(runs)
    total_backups   = sum(len(r.get("skipped_backups", [])) for r in runs)
    total_logical   = sum(len(r.get("logical_diffs",   [])) for r in runs)
    total_log_warns = sum(len(r.get("log_warnings",    [])) for r in runs)
    total_filtered  = sum(len(r.get("filtered_files",  [])) for r in runs)

    print(f"ConfigMergeTool Feedback History — {str(_HISTORY_PATH)}")
    print(f"{'─' * 60}")
    print(f"Total audit runs recorded : {total_runs}")
    print(f"Backup files skipped      : {total_backups}")
    print(f"Logical diffs seen        : {total_logical}")
    print(f"Log name warnings         : {total_log_warns}")
    print(f"Files excluded by filter  : {total_filtered}")
    print(f"{'─' * 60}")
    print(f"\nLast {min(5, total_runs)} run(s):")
    for run in runs[-5:]:
        ts       = run.get("timestamp", "unknown")
        nodes    = ", ".join(run.get("nodes", []))
        nb       = len(run.get("skipped_backups", []))
        nl       = len(run.get("logical_diffs",   []))
        nw       = len(run.get("log_warnings",    []))
        nf       = len(run.get("filtered_files",  []))
        print(f"  {ts}  nodes={nodes}")
        print(f"    backups_skipped={nb}  logical_diffs={nl}  log_warnings={nw}  filtered={nf}")
