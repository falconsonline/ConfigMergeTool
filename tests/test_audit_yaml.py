"""
Audit plain YAML (Helm values files) by structure, not by line order.

Rules (agreed with user, 2026-09-27):
  1. Maps are matched by key and list entries by name, at every depth; order never matters.
     A list entry's name is its first field (``opt=kpi.stats.rotate.interval``); plain value
     lists (``- 100``) are compared as sets.
  2. The same entry in two sections is two separate rows (compared within its own path).
  3. Instance blocks (first field ``inst`` / ``instance`` / ``instance_id`` …) pair by position,
     not by id; the id is its own row.
  4. Comment changes are flagged in one "(comments)" row.
  5. Files with template code ({{ }}) or invalid YAML keep the ordered line diff [CMT-AUD-I002].
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from configmerge.auditor.engine import AuditEngine, AuditFile
from configmerge.auditor.yaml_compare import flatten_yaml

REL = "app/values.yaml"

DR = """\
instprop:
  - inst: 1
    props:
      - { opt: 'pools', val: 'app' }
  - inst: 2
    props:
      - { opt: 'kpi.stats.rotate.interval', val: '5' }
appcfg:
  gmscspclist:
  - 100
  - 200
  props:
  - { opt: 'pools', val: 'app' }
  - { opt: 'kpi.stats.rotate.interval', val: '5' }
  - { opt: 'probe.1.host', val: '10.0.0.50' }
  - { opt: 'testparam', val: 'testval' }
"""

PROD = """\
instprop:
  - inst: 1
    props:
      - { opt: 'pools', val: 'app' }
  - inst: 2
    props: []
appcfg:
  gmscspclist:
  - 200
  - 100
  props:
  - { opt: 'probe.1.host', val: '10.0.0.52' }
  - { opt: 'kpi.stats.rotate.interval', val: '5' }
  - { opt: 'pools', val: 'app' }
"""


def _compare(tmp_path: Path, files: Dict[str, str], rel: str = REL) -> AuditFile:
    abs_paths = {}
    for node, text in files.items():
        path = tmp_path / node / rel
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        abs_paths[node] = str(path)
    engine = AuditEngine(nodes=[], report_dir=str(tmp_path / "reports"))
    return engine._compare_file(rel, list(files), abs_paths, list(files))


def _rows(af: AuditFile):
    return {p.key: p for p in af.params}


def _diffs(af: AuditFile):
    return {p.key: p.values for p in af.params if p.has_mismatch}


def test_moved_entries_match_and_only_real_differences_are_rows(tmp_path):
    af = _compare(tmp_path, {"dr": DR, "prod": PROD})
    assert af.file_type == "yaml"
    assert _diffs(af) == {
        "instprop[#2].props[opt=kpi.stats.rotate.interval].val": {"dr": "5", "prod": None},
        "instprop[#2].props": {"dr": None, "prod": "[]"},
        "appcfg.props[opt=probe.1.host].val": {"dr": "10.0.0.50", "prod": "10.0.0.52"},
        "appcfg.props[opt=testparam].val": {"dr": "testval", "prod": None},
    }
    rows = _rows(af)
    # same entry, different position and section: the appcfg copy matches on both nodes
    assert not rows["appcfg.props[opt=kpi.stats.rotate.interval].val"].has_mismatch
    assert not rows["appcfg.props[opt=pools].val"].has_mismatch
    # plain value list compared as a set
    assert not rows["appcfg.gmscspclist[=100]"].has_mismatch
    assert af.mismatch_count == 4


def test_rows_carry_section_and_line_numbers(tmp_path):
    af = _compare(tmp_path, {"dr": DR, "prod": PROD})
    row = _rows(af)["appcfg.props[opt=probe.1.host].val"]
    assert row.section == "appcfg"
    assert row.lines == {"dr": [15], "prod": [12]}
    assert af.raw_content == {"dr": DR, "prod": PROD}
    changed = {n: sorted(l for b in af.line_blocks for l in b["changed"][n]) for n in ("dr", "prod")}
    assert 15 in changed["dr"] and 12 in changed["prod"]
    assert 14 not in changed["dr"]          # kpi entry in appcfg matches — not highlighted


def test_instance_blocks_pair_by_position_not_by_id(tmp_path):
    a = "instprop:\n  - inst: 1\n    props:\n      - { opt: 'x', val: '1' }\n"
    b = "instprop:\n  - inst: 2\n    props:\n      - { opt: 'x', val: '1' }\n"
    af = _compare(tmp_path, {"a": a, "b": b})
    assert _diffs(af) == {"instprop[#1].inst": {"a": "1", "b": "2"}}


def test_nested_maps_and_lists_recurse(tmp_path):
    a = "svc:\n  ports:\n    - name: http\n      port: 80\n      extra: { tls: false }\n    - name: jmx\n      port: 9999\n"
    b = "svc:\n  ports:\n    - name: jmx\n      port: 9999\n    - name: http\n      port: 8080\n      extra: { tls: true }\n"
    af = _compare(tmp_path, {"a": a, "b": b})
    assert _diffs(af) == {
        "svc.ports[name=http].port": {"a": "80", "b": "8080"},
        "svc.ports[name=http].extra.tls": {"a": "false", "b": "true"},
    }


def test_duplicate_names_in_one_list_are_kept_apart():
    params, _ = flatten_yaml("l:\n  - { opt: 'x', val: '1' }\n  - { opt: 'x', val: '2' }\n")
    assert list(params) == ["l[opt=x].val", "l[opt=x#2].val"]


def test_comment_change_is_one_row(tmp_path):
    af = _compare(tmp_path, {"a": "a: 1  # port\n#old: 2\n", "b": "a: 1  # port\n"})
    assert _diffs(af) == {"(comments)": {"a": "#old: 2", "b": None}}


def test_whitespace_only_difference_matches(tmp_path):
    af = _compare(tmp_path, {"a": "a:\n  b: 1\n", "b": "a:\n    b:   1\n\n"})
    assert af.mismatch_count == 0


def test_template_and_invalid_yaml_fall_back_to_line_diff(tmp_path):
    tpl = _compare(tmp_path / "t", {"a": "x: {{ .Values.a }}\n", "b": "x: {{ .Values.b }}\n"})
    assert tpl.file_type == "text" and tpl.mismatch_count == 1
    assert any("CMT-AUD-I002" in w for w in tpl.warnings)
    bad = _compare(tmp_path / "b", {"a": "a: [1, 2\n", "b": "a: [1, 3\n"})
    assert bad.file_type == "text" and any("CMT-AUD-I002" in w for w in bad.warnings)


def test_missing_top_level_key_is_anchored_after_its_predecessor(tmp_path):
    # the side-by-side view must not place it "before L1" (2026-09-27)
    af = _compare(tmp_path, {"a": "name: x\nlogs: /opt\ntimezone: UTC\nport: 1\n",
                             "b": "name: x\nlogs: /opt\nport: 2\n"})
    blk = next(b for b in af.line_blocks if b["key"] == "timezone")
    assert blk["anchors"] == {"b": 2}
