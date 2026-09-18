"""
Whitespace handling (decisions agreed with user 2026-09-18).

  F-019  Merged XML keeps the release file's trailing newline/whitespace.
  WS-1   When base and release differ only in whitespace (spaces, tabs, newlines — i.e. they are
         identical once all whitespace is removed), the release file is copied to the output
         byte-for-byte, logged [CMT-MRG-I003].  With a many-to-one mapping every base must qualify.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from configmerge.cli import main


def _merge(tmp_path: Path, base: Dict[str, str], release: Dict[str, str], mapping: List[str] = ()) -> int:
    for side, files in (("base", base), ("release", release)):
        for rel, text in files.items():
            path = tmp_path / side / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
    argv = ["--base-dir", str(tmp_path / "base"), "--release-dirs", str(tmp_path / "release"),
            "--output-dir", str(tmp_path / "out"), "--report-dir", str(tmp_path / "reports")]
    if mapping:
        (tmp_path / "map.txt").write_text("\n".join(mapping) + "\n", encoding="utf-8")
        argv += ["--mapping-file", str(tmp_path / "map.txt")]
    return main(argv)


def _out(tmp_path: Path, rel: str) -> bytes:
    return (tmp_path / "out" / rel).read_bytes()


def test_xml_merge_keeps_final_newline(tmp_path):
    _merge(tmp_path, {"c/a.xml": '<config><param name="a">B</param></config>\n'},
           {"c/a.xml": '<config><param name="a">R</param></config>\n'})
    assert _out(tmp_path, "c/a.xml") == b'<config><param name="a">B</param></config>\n'


def test_kv_whitespace_only_difference_copies_release_verbatim(tmp_path):
    release = "a=1\n\n\nb = two words\n"
    _merge(tmp_path, {"c/a.properties": "a = 1\nb=two  words  \n"}, {"c/a.properties": release})
    assert _out(tmp_path, "c/a.properties") == release.encode()
    log = next((tmp_path / "reports").glob("run_*/log_merge_config.log")).read_text(encoding="utf-8")
    assert "[CMT-MRG-I003]" in log


def test_xml_whitespace_only_difference_copies_release_verbatim(tmp_path):
    release = '<config>\n    <param name="a">1</param>\n</config>\n'
    _merge(tmp_path, {"c/a.xml": '<config><param name="a">1</param></config>'}, {"c/a.xml": release})
    assert _out(tmp_path, "c/a.xml") == release.encode()


def test_json_whitespace_only_difference_copies_release_verbatim(tmp_path):
    release = '{\n\t"a": [1, 2],\n\t"b": "x"\n}\n'
    _merge(tmp_path, {"c/a.json": '{"a":[1,2],"b":"x"}'}, {"c/a.json": release})
    assert _out(tmp_path, "c/a.json") == release.encode()


def test_real_difference_is_still_merged(tmp_path):
    _merge(tmp_path, {"c/a.properties": "a = 1\n"}, {"c/a.properties": "a=2\n"})
    assert _out(tmp_path, "c/a.properties") == b"a = 1\n"


def test_many_to_one_needs_every_base_whitespace_equal(tmp_path):
    _merge(tmp_path,
           {"c/b0.properties": "a = 1\n", "c/b1.properties": "a=1\nb=9\n"},
           {"c/app.properties": "a=1\n"},
           ["c/b0.properties = c/app.properties", "c/b1.properties = c/app.properties"])
    assert b"b=9" in _out(tmp_path, "c/app.properties")
