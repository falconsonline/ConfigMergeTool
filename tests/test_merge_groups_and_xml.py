"""
KV indexed groups and XML base-only elements (decisions agreed with user 2026-09-17).

  Q7  Comma-list group header (e.g. schedule.registry) = union: base items, then release-only items.
  Q8  Indexed groups are matched by their `name` subkey when every group has one; otherwise by index.
      Base values win inside a matched group; release-only groups are appended and renumbered.
  Q12 prefix.count keeps the base value, but a count that differs from the merged group total is
      flagged: report entry GROUP_COUNT_MISMATCH + [CMT-MRG-W013] (not critical).
  Q11 A named base-only XML element is inserted even when release has other elements with that tag,
      unless --exclude-params-in-baseonlyconfig is set.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from configmerge.cli import main


def _merge(tmp_path: Path, name: str, base: str, release: str, extra: List[str] = ()) -> int:
    for side, text in (("base", base), ("release", release)):
        path = tmp_path / side / "c" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return main(["--base-dir", str(tmp_path / "base"), "--release-dirs", str(tmp_path / "release"),
                 "--output-dir", str(tmp_path / "out"), "--report-dir", str(tmp_path / "reports"),
                 *extra])


def _kv(tmp_path: Path) -> Dict[str, str]:
    lines = (tmp_path / "out/c/app.properties").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def _groups_by_name(kv: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    idx_name = {m.group(1): v for k, v in kv.items() if (m := re.fullmatch(r"schedule\.(\d+)\.name", k))}
    return {name: {k.rsplit(".", 1)[1]: v for k, v in kv.items() if k.startswith(f"schedule.{i}.")}
            for i, name in idx_name.items()}


def test_registry_header_is_union_base_first(tmp_path):
    base = "schedule.registry=ClassA,ClassB\nschedule.count=1\nschedule.1.name=A\n"
    release = "schedule.registry=ClassB,ClassC\nschedule.count=1\nschedule.1.name=A\n"
    rc = _merge(tmp_path, "app.properties", base, release)
    assert _kv(tmp_path)["schedule.registry"] == "ClassA,ClassB,ClassC"
    assert rc == 0


def test_groups_matched_by_name_base_values_win_release_only_appended(tmp_path):
    base = ("schedule.count=2\n"
            "schedule.1.name=A\nschedule.1.interval=60\n"
            "schedule.2.name=B\nschedule.2.interval=5\n")
    release = ("schedule.count=2\n"
               "schedule.1.name=B\nschedule.1.interval=99\n"
               "schedule.2.name=C\nschedule.2.interval=1\n")
    _merge(tmp_path, "app.properties", base, release)
    kv = _kv(tmp_path)
    groups = _groups_by_name(kv)
    assert set(groups) == {"A", "B", "C"}
    assert groups["A"]["interval"] == "60"
    assert groups["B"]["interval"] == "5"
    assert groups["C"]["interval"] == "1"
    assert sorted(k for k in kv if k.endswith(".name")) == [f"schedule.{i}.name" for i in (1, 2, 3)]


def test_nameless_groups_still_matched_by_index(tmp_path):
    base = "server.count=2\nserver.1.uri=h1\nserver.2.uri=h2\n"
    release = "server.count=1\nserver.1.uri=r1\n"
    _merge(tmp_path, "app.properties", base, release)
    uris = sorted(v for k, v in _kv(tmp_path).items() if k.endswith(".uri"))
    assert uris == ["h1", "h2"]


def test_group_count_keeps_base_value_but_is_flagged(tmp_path, capsys):
    base = "schedule.count=1\nschedule.1.name=A\n"
    release = "schedule.count=2\nschedule.1.name=A\nschedule.2.name=B\n"
    rc = _merge(tmp_path, "app.properties", base, release)
    assert _kv(tmp_path)["schedule.count"] == "1"
    out = capsys.readouterr().out
    assert "[CMT-MRG-W013]" in out and "schedule.count" in out
    assert rc == 0


def test_named_base_only_xml_element_inserted(tmp_path):
    base = '<config><param name="a">1</param><param name="x">X</param></config>\n'
    release = '<config><param name="a">2</param></config>\n'
    rc = _merge(tmp_path, "app.xml", base, release)
    out = (tmp_path / "out/c/app.xml").read_text(encoding="utf-8")
    assert '<param name="a">1</param>' in out and '<param name="x">X</param>' in out
    assert rc == 0


def test_named_base_only_xml_element_not_inserted_when_excluded(tmp_path):
    base = '<config><param name="a">1</param><param name="x">X</param></config>\n'
    release = '<config><param name="a">2</param></config>\n'
    _merge(tmp_path, "app.xml", base, release, ["--exclude-params-in-baseonlyconfig"])
    assert 'name="x"' not in (tmp_path / "out/c/app.xml").read_text(encoding="utf-8")
