"""
Mapping-file merges and critical-entry traceability (QE F-009/F-010, agreed with user 2026-09-17).

  1. One base file may map to several release files — each release output is merged from it (no warning).
  2. Several base files may map to one release file, for every processor (KV, XML, JSON) with the KV rule:
     the first base listed in the mapping file wins; later bases only add what earlier bases lack.
  3. Every critical report entry is also logged with a stable [CMT-*] identifier and exits 1.
  4. A JSON/XML input that cannot be parsed is reported as critical (exit 1), never silently dropped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from configmerge.cli import main


def _tree(root: Path, files: Dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _merge(tmp_path: Path, base: Dict[str, str], release: Dict[str, str],
           mapping: List[str] = ()) -> int:
    _tree(tmp_path / "base", base)
    _tree(tmp_path / "release", release)
    argv = ["--base-dir", str(tmp_path / "base"), "--release-dirs", str(tmp_path / "release"),
            "--output-dir", str(tmp_path / "out"), "--report-dir", str(tmp_path / "reports")]
    if mapping:
        (tmp_path / "map.txt").write_text("\n".join(mapping) + "\n", encoding="utf-8")
        argv += ["--mapping-file", str(tmp_path / "map.txt")]
    return main(argv)


def _out(tmp_path: Path, rel: str) -> str:
    return (tmp_path / "out" / rel).read_text(encoding="utf-8")


def test_one_base_mapped_to_several_release_files_merges_each(tmp_path, capsys):
    rc = _merge(tmp_path,
                {"conf/common.properties": "a=BASE\n"},
                {"conf/app1.properties": "a=R1\n", "conf/app2.properties": "a=R2\n"},
                ["conf/common.properties = conf/app1.properties",
                 "conf/common.properties = conf/app2.properties"])
    assert "a=BASE" in _out(tmp_path, "conf/app1.properties")
    assert "a=BASE" in _out(tmp_path, "conf/app2.properties")
    assert "CMT-MRG-W006" not in capsys.readouterr().out
    assert rc == 0


def test_many_kv_bases_first_listed_wins_later_add_missing(tmp_path):
    rc = _merge(tmp_path,
                {"conf/b0.properties": "a=B0\n", "conf/b1.properties": "a=B1\nb=B1\n"},
                {"conf/app.properties": "a=REL\n"},
                ["conf/b0.properties = conf/app.properties",
                 "conf/b1.properties = conf/app.properties"])
    lines = set(_out(tmp_path, "conf/app.properties").splitlines())
    assert {"a=B0", "b=B1"} <= lines and "a=B1" not in lines
    assert rc == 0


def test_many_json_bases_first_listed_wins_later_add_missing(tmp_path, capsys):
    rc = _merge(tmp_path,
                {"conf/b0.json": json.dumps({"a": "B0", "n": {"x": 1}}),
                 "conf/b1.json": json.dumps({"a": "B1", "n": {"x": 2, "y": 3}, "z": 4})},
                {"conf/app.json": json.dumps({"a": "REL", "n": {"x": 0}})},
                ["conf/b0.json = conf/app.json", "conf/b1.json = conf/app.json"])
    assert json.loads(_out(tmp_path, "conf/app.json")) == {"a": "B0", "n": {"x": 1, "y": 3}, "z": 4}
    assert "MULTI_BASE_IGNORED" not in capsys.readouterr().out
    assert rc == 0


def test_many_xml_bases_first_listed_wins_later_add_missing(tmp_path, capsys):
    rc = _merge(tmp_path,
                {"conf/b0.xml": '<config><param name="a">B0</param></config>\n',
                 "conf/b1.xml": '<config><param name="a">B1</param><param name="c">B1</param>'
                                '<extra>E1</extra></config>\n'},
                {"conf/app.xml": '<config><param name="a">REL</param><param name="c">REL</param>'
                                 '</config>\n'},
                ["conf/b0.xml = conf/app.xml", "conf/b1.xml = conf/app.xml"])
    out = _out(tmp_path, "conf/app.xml")
    assert '<param name="a">B0</param>' in out
    assert '<param name="c">B1</param>' in out
    assert "<extra>E1</extra>" in out
    assert "MULTI_BASE_IGNORED" not in capsys.readouterr().out
    assert rc == 0


def test_kv_empty_base_override_is_logged_with_id(tmp_path, capsys):
    rc = _merge(tmp_path, {"c/app.properties": "a=\n"}, {"c/app.properties": "a=x\n"})
    assert "[CMT-MRG-E012]" in capsys.readouterr().out
    assert rc == 1


def test_xml_empty_base_override_is_logged_with_id(tmp_path, capsys):
    rc = _merge(tmp_path,
                {"c/app.xml": '<config><param name="a"></param></config>\n'},
                {"c/app.xml": '<config><param name="a">x</param></config>\n'})
    assert "[CMT-MRG-E013]" in capsys.readouterr().out
    assert rc == 1


def test_json_empty_base_override_is_logged_with_id(tmp_path, capsys):
    rc = _merge(tmp_path, {"c/app.json": '{"a": ""}'}, {"c/app.json": '{"a": "x"}'})
    assert "[CMT-MRG-E014]" in capsys.readouterr().out
    assert rc == 1


def test_invalid_json_input_is_critical_not_silently_dropped(tmp_path, capsys):
    rc = _merge(tmp_path, {"c/app.json": '{"a": 1}'}, {"c/app.json": '{bad'})
    assert "[CMT-MRG-E003]" in capsys.readouterr().out
    assert rc == 1


def test_invalid_xml_input_is_critical_not_silently_dropped(tmp_path, capsys):
    rc = _merge(tmp_path, {"c/app.xml": "<config><a>1</a></config>"}, {"c/app.xml": "<config><a>"})
    assert "[CMT-MRG-E007]" in capsys.readouterr().out
    assert rc == 1
