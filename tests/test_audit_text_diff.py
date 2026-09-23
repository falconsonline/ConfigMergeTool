"""
Audit text/XML files (yaml, tpl, txt, xml, …) list each changed block as a flagged row.

Rules (agreed with user, 2026-09-23):
  1. Whitespace is still ignored (2026-09-18): the whole-file check decides match / mismatch and
     blank lines or indentation never make a block.
  2. When content differs, every node is diffed line-by-line against the first present node;
     overlapping or touching changes across nodes form one block row ("L<a>–L<b>").
  3. A block row holds each node's original lines and their line numbers (None / [] when the node
     has no lines there); mismatch_count is the number of blocks.
  4. Rows are read-only (no patch support for text).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from configmerge.auditor.engine import AuditEngine, AuditFile

REL = "chart/values.yaml"


def _compare(tmp_path: Path, files: Dict[str, str], all_nodes: List[str] = None) -> AuditFile:
    all_nodes = all_nodes or list(files)
    abs_paths = {}
    for node, text in files.items():
        path = tmp_path / node / REL
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        abs_paths[node] = str(path)
    present_in = [n for n in all_nodes if n in files]
    engine = AuditEngine(nodes=[], report_dir=str(tmp_path / "reports"))
    return engine._compare_text(REL, "text", present_in, abs_paths, all_nodes)


def _blocks(af: AuditFile):
    return [p for p in af.params if p.compound.startswith("__blk__")]


def test_changed_value_is_one_block_with_lines_per_node(tmp_path):
    af = _compare(tmp_path, {
        "stg":  "image:\n  tag: v1\n  pull: Always\n",
        "prod": "image:\n  tag: v2\n  pull: Always\n",
    })
    (blk,) = _blocks(af)
    assert blk.key == "L2"
    assert blk.values == {"stg": "  tag: v1", "prod": "  tag: v2"}
    assert blk.lines == {"stg": [2], "prod": [2]}
    assert blk.has_mismatch and af.mismatch_count == 1
    assert af.params[0].compound == "__md5__" and af.params[0].has_mismatch


def test_inserted_and_deleted_lines_are_blocks(tmp_path):
    af = _compare(tmp_path, {
        "stg":  "a: 1\nb: 2\nc: 3\nd: 4\n",
        "prod": "new: 0\na: 1\nc: 3\nd: 4\n",
    })
    blocks = _blocks(af)
    assert [b.key for b in blocks] == ["before L1", "L2"]
    assert blocks[0].values == {"stg": None, "prod": "new: 0"}
    assert blocks[1].values == {"stg": "b: 2", "prod": None}
    assert blocks[1].lines == {"stg": [2], "prod": []}
    assert af.mismatch_count == 2


def test_whitespace_only_difference_has_no_blocks(tmp_path):
    af = _compare(tmp_path, {"stg": "a: 1\n\nb:  2\n", "prod": "a: 1\nb: 2   \n\n\n"})
    assert _blocks(af) == [] and af.mismatch_count == 0
    assert any("CMT-AUD-I001" in w for w in af.warnings)


def test_changes_on_several_nodes_merge_into_blocks_against_the_first_node(tmp_path):
    af = _compare(tmp_path, {
        "stg":  "a: 1\nb: 2\nc: 3\nd: 4\ne: 5\n",
        "prod": "a: 1\nb: 20\nc: 3\nd: 4\ne: 5\n",
        "dr":   "a: 1\nb: 2\nc: 30\nd: 4\ne: 50\n",
    }, all_nodes=["stg", "prod", "dr", "qa"])
    blocks = _blocks(af)
    # b (prod) and c (dr) touch → one block; e (dr) is separate
    assert [b.key for b in blocks] == ["L2–L3", "L5"]
    assert blocks[0].values == {"stg": "b: 2\nc: 3", "prod": "b: 20\nc: 3", "dr": "b: 2\nc: 30"}
    assert blocks[1].values == {"stg": "e: 5", "prod": "e: 5", "dr": "e: 50"}
    assert af.mismatch_count == 2 and af.absent_count == 1


def test_identical_files_keep_the_single_checksum_row(tmp_path):
    af = _compare(tmp_path, {"stg": "a: 1\n", "prod": "a: 1\n"})
    assert [p.compound for p in af.params] == ["__md5__"]
    assert af.mismatch_count == 0
