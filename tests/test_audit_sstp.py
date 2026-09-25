"""
Audit SSTP routing-rule files: strict block comparison on original text.

Rules (agreed with user, 2026-09-25):
  1. A block is a mismatch when its text differs on ANY node, ignoring only whitespace.
     Comments count. Nothing is downgraded to "expected" automatically.
  2. The VALUE/ORDER/TEXT category is informational, computed for every node against the
     first node that has the block.
  3. Cells show each node's original block lines verbatim; the file content is shown
     side-by-side with changed lines highlighted (line blocks, like text/XML).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from configmerge.auditor.engine import AuditEngine, AuditFile

REL = "configs/rule2.sstp"

STG = """GCT (0x1a)
[
        # Handle NTR
     [
            DIGITS(1234~)     #HLR GT
            [
                        SET CDPA (SPC=SPREAD(1001,1002)) AND SET CGPA (DIGITS (123450000001)) AND LOG DETAILS;
                        ROUTE STACK 0x33 ;
            ]
            ELSE
            [
                       SET CDPA (RI=GT);
                       ROUTE STACK 0x33;
            ]
     ]
]
"""

# Statement split and moved into the ELSE branch
PROD = STG.replace(
    " AND SET CGPA (DIGITS (123450000001)) AND LOG DETAILS;", ";").replace(
    "                       ROUTE STACK 0x33;\n",
    "                       ROUTE STACK 0x33;\n\t\t       SET CGPA (DIGITS (123450000001)) AND LOG DETAILS;\n")

# Same as PROD but a different digit value
DR = PROD.replace("\t\t       SET CGPA (DIGITS (123450000001))", "\t\t       SET CGPA (DIGITS (123450000014))")


def _compare(tmp_path: Path, files: Dict[str, str]) -> AuditFile:
    abs_paths = {}
    for node, text in files.items():
        path = tmp_path / node / REL
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        abs_paths[node] = str(path)
    engine = AuditEngine(nodes=[], report_dir=str(tmp_path / "reports"))
    return engine._compare_file(REL, list(files), abs_paths, list(files))


def _row(af: AuditFile, key: str):
    return next(p for p in af.params if p.key == key)


def test_moved_statement_is_a_mismatch_not_expected(tmp_path):
    af = _compare(tmp_path, {"stg": STG, "prod": PROD})
    row = _row(af, "GCT(0x1a)")
    assert row.has_mismatch and not row.is_logical_diff
    assert af.mismatch_count == 1 and af.logical_diff_count == 0


def test_every_node_is_compared_not_only_the_first_two(tmp_path):
    af = _compare(tmp_path, {"stg": STG, "prod": PROD, "dr": DR})
    row = _row(af, "GCT(0x1a)")
    assert row.has_mismatch
    assert row.compound.endswith("|VALUE_DIFF")   # dr's DIGITS value differs


def test_values_are_the_original_block_lines(tmp_path):
    af = _compare(tmp_path, {"stg": STG, "prod": PROD})
    row = _row(af, "GCT(0x1a)")
    assert row.values["stg"] == STG.rstrip("\n")
    assert row.values["prod"] == PROD.rstrip("\n")
    assert row.lines["stg"] == list(range(1, 17))
    assert row.lines["prod"] == list(range(1, 18))


def test_comment_change_is_a_mismatch(tmp_path):
    af = _compare(tmp_path, {"stg": STG, "prod": STG.replace("#HLR GT", "#HLR")})
    assert _row(af, "GCT(0x1a)").has_mismatch


def test_whitespace_only_change_matches(tmp_path):
    af = _compare(tmp_path, {"stg": STG, "prod": STG.replace("        # Handle", "\t# Handle") + "\n\n"})
    assert af.mismatch_count == 0


def test_set_merge_is_no_longer_treated_as_equal(tmp_path):
    a = "R\n[\n  SET CDPA (A) AND SET CDPA (B);\n]\n"
    b = "R\n[\n  SET CDPA (A,B);\n]\n"
    assert _compare(tmp_path, {"n1": a, "n2": b}).mismatch_count == 1


def test_change_outside_blocks_is_its_own_row(tmp_path):
    af = _compare(tmp_path, {"stg": "# v1\n" + STG, "prod": "# v2\n" + STG})
    row = _row(af, "(outside blocks)")
    assert row.has_mismatch and row.values == {"stg": "# v1", "prod": "# v2"}
    assert af.mismatch_count == 1


def test_raw_content_and_line_blocks_for_side_by_side(tmp_path):
    af = _compare(tmp_path, {"stg": STG, "prod": PROD})
    assert af.raw_content == {"stg": STG, "prod": PROD}
    changed = {n: sorted(l for b in af.line_blocks for l in b["lines"][n]) for n in ("stg", "prod")}
    assert changed == {"stg": [7], "prod": [7, 14]}


def test_block_missing_on_a_node_is_a_mismatch(tmp_path):
    extra = STG + "GCT (0x4e)\n[\n  ROUTE STACK 0x33;\n]\n"
    af = _compare(tmp_path, {"stg": STG, "prod": extra})
    row = _row(af, "GCT(0x4e)")
    assert row.has_mismatch and row.compound.endswith("|BLOCK_ABSENT")
    assert row.values["stg"] is None
