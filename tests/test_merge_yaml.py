"""
Merge mode: YAML values files and backup copies (agreed with user, 2026-09-28).

  1. YAML is merged like KV/JSON: base (site) values win, base-only parameters are added
     in the same section, release-only parameters are kept. Maps are matched by key and
     list entries by name (first field), so order never matters.
  2. The output keeps the release file's layout and comments; only changed values are
     rewritten and base-only entries are inserted with the release's indentation.
  3. Files with template code ({{ }}) or invalid YAML keep the release copy; when the
     site copy differs this is reported (YAML_RELEASE_COPIED).
  4. Backup copies (backup markers, and values* files next to a values.yaml) are not
     copied to the output; they are reported (BACKUP_FILE_SKIPPED).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

import yaml

from configmerge.cli import main
from configmerge.models import EntryType, MergeConfig
from configmerge.processors import PROCESSOR_REGISTRY

REL = """\
# release defaults
name: app
appcfg:
  main_cfg: "/opt/app/TR.cfg"   # main config
  props:
  - { opt: 'probe.1.host', val: '10.0.0.1' }
  - { opt: 'kpi.stats.rotate.interval', val: '5' }
  - { opt: 'new.release.flag', val: 'true' }
  couchbase:
    default.cluster: "couchbase-default"
instprop:
  - inst: 1
    props:
      - { opt: 'x', val: '1' }
  - inst: 2
    props:
      - { opt: 'x', val: '1' }
"""

BASE = """\
name: app
appcfg:
  main_cfg: "/opt/app/TR.cfg"
  props:
  - { opt: 'kpi.stats.rotate.interval', val: '5' }
  - { opt: 'probe.1.host', val: '10.0.0.52' }
  - { opt: 'testparam', val: 'testval' }
  couchbase:
    default.cluster: "couchbase-site"
    pool.size: 16
instprop:
  - inst: 1
    props:
      - { opt: 'x', val: '1' }
  - inst: 2
    props:
      - { opt: 'x', val: '2' }
      - { opt: 'kpi.stats.rotate.interval', val: '5' }
timezone: Asia/Riyadh
"""


def _process(tmp_path: Path, bases: List[str], rel: str, exclude: bool = False):
    paths = []
    for i, text in enumerate(bases):
        p = tmp_path / f"base{i}" / "values.yaml"
        p.parent.mkdir(parents=True)
        p.write_text(text, encoding="utf-8")
        paths.append(str(p))
    r = tmp_path / "rel" / "values.yaml"
    r.parent.mkdir(parents=True)
    r.write_text(rel, encoding="utf-8")
    (tmp_path / "out").mkdir()
    cfg = MergeConfig(release_dirs=[str(r.parent)], output_dir=str(tmp_path / "out"),
                      base_dir=str(tmp_path / "base0"), exclude_base_only=exclude)
    out = tmp_path / "out" / "values.yaml"
    entries = PROCESSOR_REGISTRY[".yaml"]().process(paths, str(r), str(out), cfg, logging.getLogger("t"))
    return out.read_text(encoding="utf-8"), entries


def _types(entries):
    return {(e.type, e.element) for e in entries}


def test_base_values_win_release_layout_and_comments_kept(tmp_path):
    out, entries = _process(tmp_path, [BASE], REL)
    data = yaml.safe_load(out)
    props = {p["opt"]: p["val"] for p in data["appcfg"]["props"]}
    assert props["probe.1.host"] == "10.0.0.52"                  # base wins
    assert props["kpi.stats.rotate.interval"] == "5"             # same value, other position
    assert props["new.release.flag"] == "true"                   # release-only kept
    assert props["testparam"] == "testval"                       # base-only added
    assert data["appcfg"]["couchbase"] == {"default.cluster": "couchbase-site", "pool.size": 16}
    assert data["timezone"] == "Asia/Riyadh"
    # layout: release comments and entry order kept, only the value text changed
    assert out.startswith("# release defaults\nname: app\n")
    assert '  main_cfg: "/opt/app/TR.cfg"   # main config\n' in out
    assert "  - { opt: 'probe.1.host', val: '10.0.0.52' }\n" in out
    assert out.index("probe.1.host") < out.index("kpi.stats.rotate.interval")
    assert (EntryType.BASE_TO_RELEASE_REPLACED, "appcfg.props[opt=probe.1.host].val") in _types(entries)
    assert (EntryType.RELEASE_ONLY_PARAMETER_ADDED, "appcfg.props[opt=new.release.flag]") in _types(entries)


def test_base_only_entries_are_inserted_in_their_own_section(tmp_path):
    out, entries = _process(tmp_path, [BASE], REL)
    data = yaml.safe_load(out)
    inst2 = data["instprop"][1]["props"]
    assert inst2 == [{"opt": "x", "val": "2"}, {"opt": "kpi.stats.rotate.interval", "val": "5"}]
    assert data["instprop"][0]["props"] == [{"opt": "x", "val": "1"}]
    # inserted with the release list's indentation, right after that list
    assert "  - { opt: 'new.release.flag', val: 'true' }\n  - { opt: 'testparam', val: 'testval' }\n" in out
    added = {e.element for e in entries if e.type == EntryType.BASE_ONLY_PARAMETER_ADDED}
    assert added == {"appcfg.props[opt=testparam]", "appcfg.couchbase.pool.size",
                     "instprop[#2].props[opt=kpi.stats.rotate.interval]", "timezone"}


def test_exclude_base_only_parameters(tmp_path):
    out, entries = _process(tmp_path, [BASE], REL, exclude=True)
    data = yaml.safe_load(out)
    assert "timezone" not in data and "pool.size" not in data["appcfg"]["couchbase"]
    assert {e.element for e in entries if e.type == EntryType.EXCLUDED_BASE_ONLY_PARAMETER} == {
        "appcfg.props[opt=testparam]", "appcfg.couchbase.pool.size",
        "instprop[#2].props[opt=kpi.stats.rotate.interval]", "timezone"}
    assert data["appcfg"]["couchbase"]["default.cluster"] == "couchbase-site"


def test_first_base_wins_later_bases_only_add(tmp_path):
    second = "name: other\nextra: 1\nappcfg:\n  main_cfg: x\n"
    out, _ = _process(tmp_path, [BASE, second], REL)
    data = yaml.safe_load(out)
    assert data["name"] == "app" and data["extra"] == 1


def test_base_entry_into_flow_style_empty_list_is_reported_not_forced(tmp_path):
    rel = "props: []\nother: 1\n"
    base = "props:\n- { opt: 'a', val: '1' }\nother: 1\n"
    out, entries = _process(tmp_path, [base], rel)
    assert yaml.safe_load(out) == {"props": [], "other": 1}
    assert (EntryType.YAML_NOT_MERGED, "props[opt=a]") in _types(entries)


def test_template_keeps_release_copy_and_reports_when_site_differs(tmp_path):
    out, entries = _process(tmp_path, ["x: {{ .Values.a }}\n"], "x: {{ .Values.b }}\n")
    assert out == "x: {{ .Values.b }}\n"
    assert [e.type for e in entries] == [EntryType.YAML_RELEASE_COPIED]


# ── engine level: backups are not deployed ─────────────────────────────────

def _tree(root: Path, files: Dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_backup_copies_are_not_copied_to_output(tmp_path):
    _tree(tmp_path / "base", {"chart/values.yaml": "a: 1\n", "chart/values_DR.yaml": "a: 9\n",
                              "conf/app.properties": "k=1\n"})
    _tree(tmp_path / "release", {"chart/values.yaml": "a: 2\n", "chart/values.yamlbck": "a: 0\n",
                                 "chart/unedit_values.yaml": "a: 0\n", "chart/values.schema.json": "{}\n",
                                 "conf/app.properties": "k=2\n", "conf/app.properties_bkp200821": "k=0\n"})
    rc = main(["--base-dir", str(tmp_path / "base"), "--release-dirs", str(tmp_path / "release"),
               "--output-dir", str(tmp_path / "out"), "--report-dir", str(tmp_path / "reports")])
    out = {p.relative_to(tmp_path / "out").as_posix() for p in (tmp_path / "out").rglob("*") if p.is_file()}
    assert out == {"chart/values.yaml", "chart/values.schema.json", "conf/app.properties"}
    assert yaml.safe_load((tmp_path / "out/chart/values.yaml").read_text()) == {"a": 1}
    assert rc == 0
