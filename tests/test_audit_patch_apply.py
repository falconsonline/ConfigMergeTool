"""
--apply-audit-patch safety and exit codes (QE findings F-005..F-007, agreed 2026-09-17).

Exit codes: 0 = every change written, 1 = some changes skipped/failed,
2 = patch file invalid or nothing to apply.  Every error carries a stable [CMT-PAT-*] code.
"""

from __future__ import annotations

import json
from pathlib import Path

from configmerge.cli import main


def _change(node: str = "n1", **over) -> dict:
    change = {"node": node, "file": "a.properties", "file_type": "kv", "compound": "|k",
              "key": "k", "section": "", "action": "modified", "original": "1", "corrected": "2"}
    change.update(over)
    return change


def _apply(tmp_path: Path, patch: dict) -> int:
    (tmp_path / "n1").mkdir(exist_ok=True)
    (tmp_path / "n1" / "a.properties").write_text("k=1\n", encoding="utf-8")
    patch_file = tmp_path / "patch.json"
    patch_file.write_text(json.dumps(patch), encoding="utf-8")
    return main(["--apply-audit-patch", str(patch_file), "--output-dir", str(tmp_path / "corr")])


def test_valid_patch_writes_correction_and_exits_0(tmp_path):
    rc = _apply(tmp_path, {"node_dirs": {"n1": str(tmp_path / "n1")}, "changes": [_change()]})
    assert (tmp_path / "corr/n1/a.properties").read_text() == "k=2\n"
    assert rc == 0


def test_node_name_traversal_is_rejected_nothing_written_outside_output(tmp_path, capsys):
    rc = _apply(tmp_path, {"node_dirs": {"../ESCAPED": str(tmp_path / "n1")},
                           "changes": [_change("../ESCAPED")]})
    assert not (tmp_path / "ESCAPED").exists()
    assert "[CMT-PAT-E008]" in capsys.readouterr().out
    assert rc == 1


def test_patch_with_no_changes_exits_2(tmp_path, capsys):
    rc = _apply(tmp_path, {"node_dirs": {}, "changes": []})
    assert "[CMT-PAT-E004]" in capsys.readouterr().err
    assert rc == 2


def test_malformed_change_entry_exits_2_without_traceback(tmp_path, capsys):
    rc = _apply(tmp_path, {"node_dirs": {}, "changes": [{"node": "n1"}]})
    err = capsys.readouterr().err
    assert "[CMT-PAT-E003]" in err and "Traceback" not in err
    assert rc == 2


def test_patch_missing_required_field_exits_2(tmp_path, capsys):
    rc = _apply(tmp_path, {"changes": [_change()]})
    assert "[CMT-PAT-E002]" in capsys.readouterr().err
    assert rc == 2
