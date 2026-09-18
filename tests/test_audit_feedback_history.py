"""M-1: feedback history is appended in place, byte-identical to a full json.dump rewrite."""
import json
import pathlib

import pytest

from configmerge.auditor.engine import AuditEngine


def _engine(tmp_path, ts):
    eng = AuditEngine(nodes=[], report_dir=str(tmp_path / "reports"))
    eng._ts = ts
    return eng


def _append(eng, filtered):
    eng._append_feedback_history(
        node_names=["n1", "n2"],
        skipped_backups=[{"rel_path": "conf/a.properties.bak"}],
        logical_diffs=[{"compound": "[S]|host"}],
        log_warnings=[{"file": "f", "reason": "duplicate_log_prefix", "value": "é"}],
        filtered_files=[{"rel_path": p} for p in filtered],
    )


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return tmp_path / "home" / ".configmergetool" / "feedback_history.json"


def _expected(runs):
    return json.dumps({"runs": runs}, indent=2).encode("utf-8")


def test_repeated_appends_match_full_rewrite_bytes(tmp_path, home):
    for i in range(3):
        _append(_engine(tmp_path, f"2026010{i}_000000"), [f"lib/x{i}.jar", "lib/ü.jar"])
    runs = json.loads(home.read_text(encoding="utf-8"))["runs"]
    assert [r["timestamp"] for r in runs] == ["20260100_000000", "20260101_000000", "20260102_000000"]
    assert home.read_bytes() == _expected(runs)


def test_existing_file_is_not_loaded_when_layout_matches(tmp_path, home, monkeypatch):
    _append(_engine(tmp_path, "20260101_000000"), ["a"])
    monkeypatch.setattr(json, "load", lambda *a, **k: pytest.fail("history was fully loaded"))
    _append(_engine(tmp_path, "20260102_000000"), ["b"])
    monkeypatch.undo()
    assert len(json.loads(home.read_text(encoding="utf-8"))["runs"]) == 2


@pytest.mark.parametrize("content", [
    '{"runs": [{"timestamp": "old"}]}',                         # compact, hand-written
    '{\n  "runs": [\n    {\n      "timestamp": "old"\n    }\n  ]\n}\n',  # trailing newline
    '{\n  "runs": [],\n  "extra": 1\n}',                         # extra key kept
    '{\n  "runs": []\n}',                                        # empty list
])
def test_other_layouts_fall_back_to_rewrite(tmp_path, home, content):
    home.parent.mkdir(parents=True)
    home.write_text(content, encoding="utf-8")
    before = json.loads(content)
    _append(_engine(tmp_path, "20260101_000000"), ["a"])
    after = json.loads(home.read_text(encoding="utf-8"))
    assert after["runs"][:-1] == before["runs"]
    assert after["runs"][-1]["timestamp"] == "20260101_000000"
    assert {k: v for k, v in after.items() if k != "runs"} == {k: v for k, v in before.items() if k != "runs"}
    assert home.read_bytes() == json.dumps(after, indent=2).encode("utf-8")


def test_unparseable_history_is_reset_as_before(tmp_path, home):
    home.parent.mkdir(parents=True)
    home.write_text("not json", encoding="utf-8")
    _append(_engine(tmp_path, "20260101_000000"), ["a"])
    assert [r["timestamp"] for r in json.loads(home.read_text(encoding="utf-8"))["runs"]] == ["20260101_000000"]
