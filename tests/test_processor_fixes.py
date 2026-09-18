"""
Processor defects found by the S1 review (verified 2026-09-17, fix approved by user).

  F-012 XML: a named element containing a same-tag child is replaced as a whole block.
  F-013 JSON: inline-array formatting never changes string contents.
  F-014 KV: a line is split at its first delimiter, so `key: value=x` keeps key `key`.
  F-015 JSON: `true` and `1` are different values — base wins.
  F-018 XML: elements inside <!-- comments --> are never matched or replaced.
"""

from __future__ import annotations

import json
from pathlib import Path

from configmerge.cli import main


def _merge(tmp_path: Path, name: str, base: str, release: str) -> str:
    for side, text in (("base", base), ("release", release)):
        path = tmp_path / side / "c" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    main(["--base-dir", str(tmp_path / "base"), "--release-dirs", str(tmp_path / "release"),
          "--output-dir", str(tmp_path / "out"), "--report-dir", str(tmp_path / "reports")])
    return (tmp_path / "out/c" / name).read_text(encoding="utf-8")


def test_xml_nested_same_tag_element_replaced_as_whole_block(tmp_path):
    out = _merge(tmp_path, "a.xml",
                 '<config><param name="outer"><param name="inner">B</param>baseouter</param></config>',
                 '<config><param name="outer"><param name="inner">R</param>relouter</param></config>')
    assert '<param name="outer"><param name="inner">B</param>baseouter</param>' in out
    assert "relouter" not in out


def test_json_string_that_looks_like_a_list_is_not_rewritten(tmp_path):
    out = _merge(tmp_path, "a.json", '{"pattern": "[a,b]", "x": 1}', '{"pattern": "[a,b]", "x": 2}')
    assert '"[a,b]"' in out
    assert json.loads(out) == {"pattern": "[a,b]", "x": 1}


def test_json_inline_array_keeps_commas_inside_strings(tmp_path):
    out = _merge(tmp_path, "a.json", '{"l": ["a,b", "c"]}', '{"l": ["x"]}')
    assert json.loads(out) == {"l": ["a,b", "c"]}
    assert '["a,b", "c"]' in out


def test_kv_colon_delimited_value_containing_equals_keeps_its_key(tmp_path):
    out = _merge(tmp_path, "a.cfg",
                 "jdbc.url: jdbc:oracle:thin:@host:1521/xe?opt=val\n",
                 "jdbc.url: jdbc:oracle:thin:@relhost:1521/xe?opt=relval\n")
    assert out.splitlines() == ["jdbc.url: jdbc:oracle:thin:@host:1521/xe?opt=val"]


def test_json_boolean_and_number_are_different_values(tmp_path):
    out = _merge(tmp_path, "a.json", '{"flag": true, "n": 0}', '{"flag": 1, "n": false}')
    # compare serialised form: in Python True == 1, so a dict comparison would hide the defect
    assert json.dumps(json.loads(out)) == '{"flag": true, "n": 0}'


def test_xml_commented_out_element_is_not_matched(tmp_path):
    out = _merge(tmp_path, "a.xml",
                 '<config><param name="a">B</param></config>',
                 '<config><!-- <param name="a">OLD</param> --><param name="a">R</param></config>')
    assert '<!-- <param name="a">OLD</param> -->' in out
    assert '<param name="a">B</param></config>' in out
