"""
Merge-mode engine behaviour (QE findings F-001..F-004, decisions agreed with user 2026-09-17).

  1. Base values win; base-only keys are added; release-only keys are preserved.
  2. A release file with no base counterpart is copied to the output as-is (F-001).
  3. Hidden files (name starts with '.') are never matched, merged or copied.
  4. A filename-only match with several base candidates is skipped, reported and exits 1 (F-002).
  5. .sstp files are copied from release without a processor error (F-003).
  6. A processor failure is critical and exits 1 (F-003).
  7. --output-dir equal to, containing, or inside a base/release dir is refused with exit 2
     and nothing is deleted (F-004).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from configmerge.cli import main
from configmerge.processors import PROCESSOR_REGISTRY


def _tree(root: Path, files: Dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _merge(tmp_path: Path, base: Dict[str, str], release: Dict[str, str], out: str = "out") -> int:
    _tree(tmp_path / "base", base)
    _tree(tmp_path / "release", release)
    return main([
        "--base-dir", str(tmp_path / "base"),
        "--release-dirs", str(tmp_path / "release"),
        "--output-dir", str(tmp_path / out),
        "--report-dir", str(tmp_path / "reports"),
    ])


def _out_files(tmp_path: Path) -> Dict[str, str]:
    out = tmp_path / "out"
    return {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8")
            for p in out.rglob("*") if p.is_file()}


def test_base_wins_base_only_added_release_only_preserved(tmp_path):
    rc = _merge(tmp_path,
                {"conf/app.properties": "a=BASE\nbase_only=1\n"},
                {"conf/app.properties": "a=REL\nrel_only=2\n"})
    lines = set(_out_files(tmp_path)["conf/app.properties"].splitlines())
    assert {"a=BASE", "base_only=1", "rel_only=2"} <= lines
    assert "a=REL" not in lines
    assert rc == 0


def test_release_only_file_is_copied_to_output(tmp_path):
    rc = _merge(tmp_path,
                {"conf/app.properties": "a=1\n"},
                {"conf/app.properties": "a=2\n", "conf/request/new.json": '{"x": 1}\n'})
    assert _out_files(tmp_path)["conf/request/new.json"] == '{"x": 1}\n'
    assert rc == 0


def test_hidden_files_are_not_copied_or_merged(tmp_path):
    rc = _merge(tmp_path,
                {"conf/app.properties": "a=1\n", ".DS_Store": "base-junk"},
                {"conf/app.properties": "a=2\n", ".DS_Store": "rel-junk", "conf/.hidden": "x"})
    assert set(_out_files(tmp_path)) == {"conf/app.properties"}
    assert rc == 0


def test_ambiguous_filename_match_is_skipped_reported_and_exits_1(tmp_path, capsys):
    rc = _merge(tmp_path,
                {"old/dup.properties": "x=OLD\n", "other/dup.properties": "x=OTHER\n"},
                {"new/dup.properties": "x=REL\n"})
    assert _out_files(tmp_path) == {}
    assert "[CMT-MRG-E002]" in capsys.readouterr().out
    assert rc == 1


def test_sstp_file_copied_from_release_without_processor_error(tmp_path, capsys):
    rc = _merge(tmp_path,
                {"conf/r.sstp": "rule R1 {}\n"},
                {"conf/r.sstp": "rule R1 {x}\n"})
    assert _out_files(tmp_path)["conf/r.sstp"] == "rule R1 {x}\n"
    assert "PROCESSOR_FAILED" not in capsys.readouterr().out
    assert rc == 0


def test_processor_failure_is_critical_and_exits_1(tmp_path, monkeypatch, capsys):
    class Boom:
        def process(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setitem(PROCESSOR_REGISTRY, ".boom", Boom)
    rc = _merge(tmp_path, {"f.boom": "a"}, {"f.boom": "b"})
    assert "[CMT-MRG-E001]" in capsys.readouterr().out
    assert rc == 1


@pytest.mark.parametrize("out_rel", ["release", ".", "release/out", "base", "base/out"])
def test_output_dir_overlapping_input_is_refused_and_nothing_deleted(tmp_path, capsys, out_rel):
    rc = _merge(tmp_path,
                {"conf/app.properties": "a=1\n"},
                {"conf/app.properties": "a=2\n"},
                out=out_rel)
    assert rc == 2
    assert "[CMT-MRG-E010]" in capsys.readouterr().err
    assert (tmp_path / "release/conf/app.properties").read_text() == "a=2\n"
    assert (tmp_path / "base/conf/app.properties").read_text() == "a=1\n"
