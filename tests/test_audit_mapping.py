"""
Audit --mapping-file: files at different relative paths on different nodes share one report row.

Rules (agreed with user, 2026-09-23):
  1. ``LEFT=RIGHT`` places the LEFT node's file into the row of the RIGHT path, so one source
     mapped to several instances (app → app-1, app-2) appears in each instance's row.
  2. The source's own row goes away unless another node has that same path.
  3. Directory lines map a whole subtree; a file line overrides a directory line.
  4. The first path component names the node (base_dir basename or name); a leading "/" is ignored.
  5. A pair with exactly one side missing is skipped with CMT-AUD-W011; both sides missing
     (hidden / filtered / binary) is skipped silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from configmerge.auditor.engine import AuditEngine, AuditResult
from configmerge.auditor.html_report import _serialise_result
from configmerge.errors import ConfigMergeError
from configmerge.models import BaseDirConfig

CHART = "name: app\nversion: 1.0\n"


def _tree(tmp_path: Path, layout: Dict[str, Dict[str, str]]) -> list:
    nodes = []
    for node, files in layout.items():
        root = tmp_path / node
        root.mkdir()
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        nodes.append(BaseDirConfig(base_dir=str(root), name=f"site-{node}"))
    return nodes


def _run(tmp_path: Path, layout, mapping: str) -> AuditResult:
    nodes = _tree(tmp_path, layout)
    mfile = tmp_path / "map.txt"
    mfile.write_text(mapping, encoding="utf-8")
    engine = AuditEngine(nodes, report_dir=str(tmp_path / "reports"), quiet=True, mapping_file=str(mfile))
    return engine.run()


def _file(result: AuditResult, rel: str):
    return next(f for f in result.files if f.rel_path == rel)


LAYOUT = {
    "STG":  {"app/Chart.yaml": CHART, "app/values.yaml": "a: 1\n"},
    "PROD": {"app-1/Chart.yaml": CHART, "app-1/values.yaml": "a: 1\n",
             "app-2/Chart.yaml": CHART, "app-2/values.yaml": "a: 2\n"},
    "DR":   {"app-1/Chart.yaml": CHART, "app-1/values.yaml": "a: 1\n",
             "app-2/Chart.yaml": CHART, "app-2/values.yaml": "a: 2\n"},
}


def test_one_source_mapped_to_several_instances_gets_a_row_per_instance(tmp_path):
    result = _run(tmp_path, LAYOUT, "\n".join(
        f"STG/app/{f}={side}/app-{i}/{f}"
        for f in ("Chart.yaml", "values.yaml") for side in ("PROD", "DR") for i in (1, 2)))
    assert sorted(f.rel_path for f in result.files) == [
        "app-1/Chart.yaml", "app-1/values.yaml", "app-2/Chart.yaml", "app-2/values.yaml"]
    chart = _file(result, "app-1/Chart.yaml")
    assert chart.present_in == ["site-STG", "site-PROD", "site-DR"]
    assert chart.absent_count == 0 and chart.mismatch_count == 0
    assert chart.node_paths == {"site-STG": "app/Chart.yaml"}
    assert _file(result, "app-2/values.yaml").mismatch_count == 1


def test_directory_lines_map_the_subtree_and_file_lines_override(tmp_path):
    layout = {
        "STG":  {"app/Chart.yaml": CHART, "app/alt.yaml": "a: 2\n", "app/values.yaml": "a: 1\n"},
        "PROD": {"app-1/Chart.yaml": CHART, "app-1/values.yaml": "a: 2\n"},
    }
    result = _run(tmp_path, layout, "# dirs\n/STG/app=/PROD/app-1/\nSTG/app/alt.yaml=PROD/app-1/values.yaml\n")
    values = _file(result, "app-1/values.yaml")
    assert values.node_paths == {"site-STG": "app/alt.yaml"}
    assert values.mismatch_count == 0
    assert _file(result, "app-1/Chart.yaml").node_paths == {"site-STG": "app/Chart.yaml"}
    # app/values.yaml was not placed anywhere, so it keeps its own row
    assert _file(result, "app/values.yaml").present_in == ["site-STG"]


def test_node_can_be_named_by_its_config_name(tmp_path):
    result = _run(tmp_path, LAYOUT, "site-STG/app/Chart.yaml=site-PROD/app-1/Chart.yaml\n")
    assert _file(result, "app-1/Chart.yaml").present_in == ["site-STG", "site-PROD", "site-DR"]


def test_unknown_node_prefix_is_a_config_error(tmp_path):
    with pytest.raises(ConfigMergeError) as exc:
        _run(tmp_path, LAYOUT, "QA/app/Chart.yaml=PROD/app-1/Chart.yaml\n")
    assert exc.value.code == "CMT-CLI-E018"


def test_pair_with_one_side_missing_warns_and_both_missing_is_silent(tmp_path, capsys):
    result = _run(tmp_path, LAYOUT, "STG/app/gone.yaml=PROD/app-1/Chart.yaml\n"
                                    "STG/app/.hidden=PROD/app-1/.hidden\n")
    assert "1 mapping pair(s) skipped" in capsys.readouterr().out
    log = (Path(result.run_dir) / "audit.log").read_text(encoding="utf-8")
    assert log.count("CMT-AUD-W011") == 1 and "site-STG/app/gone.yaml" in log
    assert _file(result, "app-1/Chart.yaml").present_in == ["site-PROD", "site-DR"]


def test_node_keeps_its_own_file_when_a_mapping_targets_the_same_path(tmp_path):
    layout = {"STG": {"app/x.yaml": "a: 1\n", "app-1/x.yaml": "a: 9\n"}, "PROD": {"app-1/x.yaml": "a: 9\n"}}
    result = _run(tmp_path, layout, "STG/app/x.yaml=PROD/app-1/x.yaml\n")
    row = _file(result, "app-1/x.yaml")
    assert row.node_paths == {} and row.mismatch_count == 0
    assert _file(result, "app/x.yaml").present_in == ["site-STG"]


def test_node_paths_reach_the_report_data(tmp_path):
    result = _run(tmp_path, LAYOUT, "STG/app=PROD/app-1\n")
    files = {f["path"]: f for f in _serialise_result(result)["files"]}
    assert files["app-1/Chart.yaml"]["nodePaths"] == {"site-STG": "app/Chart.yaml"}
    assert files["app-2/Chart.yaml"]["nodePaths"] == {}
