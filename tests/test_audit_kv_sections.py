"""
Audit KV comparison is section-by-section against the base node.

Rules (agreed with user, 2026-09-15):
  1. Base = first node in the audit config; if it lacks the file, the first node that has it.
  2. A key is compared within its section; the same key in two sections is two rows.
  3. A commented header ``#[X]`` is a comment — active keys after it stay in the enclosing section.
  4. Sections/keys the base lacks appear at their file position (no repeated section blocks).
  5. Each section carries a check: base param count and per-node match/differ/missing/extra.
  6. A commented-out key counts as present (commented), not missing.
  7. The same key twice in one section on a node shows both values; the last (second) value is the
     effective one and is compared — the duplicate is a warning, not a mismatch (revised 2026-09-18).
  8. Empty sections are listed; keys before the first header form the DEFAULT section.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import openpyxl

from configmerge.auditor.engine import AuditEngine, AuditFile, AuditResult
from configmerge.auditor.html_report import _serialise_result, _write_diffs_xlsx
from configmerge.auditor.patch import AuditPatcher, PatchChange

REL = "config/app.properties"


def _compare(tmp_path: Path, files: Dict[str, str], all_nodes: List[str] = None) -> AuditFile:
    """Write one KV file per node (dict order = audit config order) and run the KV comparison."""
    all_nodes = all_nodes or list(files)
    abs_paths = {}
    for node, text in files.items():
        path = tmp_path / node / REL
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        abs_paths[node] = str(path)
    present_in = [n for n in all_nodes if n in files]
    engine = AuditEngine(nodes=[], report_dir=str(tmp_path / "reports"))
    return engine._compare_kv(REL, present_in, abs_paths, all_nodes)


def _rows(af: AuditFile):
    return [(p.section, p.key) for p in af.params]


def _row(af: AuditFile, section: str, key: str):
    return next(p for p in af.params if p.section == section and p.key == key)


def _section(af: AuditFile, name: str) -> dict:
    return next(s for s in af.sections if s["name"] == name)


# ── Rule 4: placement ───────────────────────────────────────────────────────

def test_section_missing_from_base_is_placed_at_its_file_position(tmp_path):
    af = _compare(tmp_path, {
        "n1": "[A]\na=1\n[C]\nc=1\n",
        "n2": "[A]\na=1\n[B]\nb=1\n[C]\nc=1\n",
        "n3": "[A]\na=1\n[B]\nb=1\n[C]\nc=1\n",
    })
    assert _rows(af) == [("[A]", "a"), ("[B]", "b"), ("[C]", "c")]


def test_key_missing_from_base_is_placed_inside_its_section(tmp_path):
    af = _compare(tmp_path, {
        "n1": "[A]\nx=1\nz=1\n[B]\nq=1\n",
        "n2": "[A]\nx=1\ny=1\nz=1\n[B]\nq=1\n",
    })
    assert _rows(af) == [("[A]", "x"), ("[A]", "y"), ("[A]", "z"), ("[B]", "q")]


# ── Rule 3: commented section header ───────────────────────────────────────

def test_active_key_after_commented_header_belongs_to_enclosing_section(tmp_path):
    af = _compare(tmp_path, {
        "n1": "[App]\nmode=on\nflag=true\n",
        "n2": "[App]\nmode=on\n#[Listeners]\n#DEFAULT=x\nflag=true\n",
    })
    row = _row(af, "[App]", "flag")
    assert row.values == {"n1": "true", "n2": "true"}
    assert row.has_mismatch is False
    assert not any(p.section.startswith("#[") for p in af.params)


# ── Rule 2: same key in two sections ───────────────────────────────────────

def test_same_key_in_two_sections_stays_two_rows(tmp_path):
    af = _compare(tmp_path, {
        "n1": "[P]\nuser=a\n[Q]\nuser=b\n",
        "n2": "[P]\nuser=a\n[Q]\nuser=b\n",
    })
    assert _rows(af) == [("[P]", "user"), ("[Q]", "user")]
    assert [p.has_mismatch for p in af.params] == [False, False]


# ── Rule 7: duplicate key within one section ───────────────────────────────

def test_duplicate_key_uses_last_value_and_is_a_warning_not_a_mismatch(tmp_path):
    af = _compare(tmp_path, {
        "n1": "[S]\ndefault=A\n",
        "n2": "[S]\ndefault=B\ndefault=A\n",
    })
    row = _row(af, "[S]", "default")
    assert row.dup_values == {"n2": ["B", "A"]}
    assert row.lines["n2"] == [2, 3]
    assert row.values["n2"] == "A"
    assert row.has_mismatch is False
    assert af.mismatch_count == 0
    assert any(w.startswith("n2:") and "'default' duplicated in [S]" in w and "last value 'A' (L3) is used" in w
               and "[CMT-AUD-W007]" in w for w in af.warnings)


def test_duplicate_key_with_different_last_value_is_a_mismatch(tmp_path):
    af = _compare(tmp_path, {
        "n1": "[S]\ndefault=A\n",
        "n2": "[S]\ndefault=A\ndefault=B\n",
    })
    assert _row(af, "[S]", "default").has_mismatch is True


def test_identical_files_with_duplicate_key_match(tmp_path):
    text = "[CouchBase]\ntimeout=100\nhost=h\ntimeout=200\n"
    af = _compare(tmp_path, {"n1": text, "n2": text})
    assert af.mismatch_count == 0


def test_single_node_file_with_duplicate_key_is_not_a_mismatch(tmp_path):
    af = _compare(tmp_path, {"n1": "[S]\nk=1\nk=2\n"}, all_nodes=["n1", "n2"])
    assert af.mismatch_count == 0


def test_xml_whitespace_only_difference_between_nodes_is_a_match(tmp_path):
    abs_paths = {}
    for node, text in (("n1", "<a>\n\t<b>1</b>\n</a>\n"), ("n2", "<a>\n    <b>1</b>\n\n</a>")):
        path = tmp_path / node / "p/package.xml"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        abs_paths[node] = str(path)
    engine = AuditEngine(nodes=[], report_dir=str(tmp_path / "reports"))
    af = engine._compare_file("p/package.xml", ["n1", "n2"], abs_paths, ["n1", "n2"])
    assert af.mismatch_count == 0
    assert any("[CMT-AUD-I001]" in w for w in af.warnings)


def test_xml_content_difference_between_nodes_is_a_mismatch(tmp_path):
    abs_paths = {}
    for node, text in (("n1", "<a><b>1</b></a>\n"), ("n2", "<a><b>2</b></a>\n")):
        path = tmp_path / node / "p/package.xml"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        abs_paths[node] = str(path)
    engine = AuditEngine(nodes=[], report_dir=str(tmp_path / "reports"))
    assert engine._compare_file("p/package.xml", ["n1", "n2"], abs_paths, ["n1", "n2"]).mismatch_count >= 1


# ── Rule 6: commented key ──────────────────────────────────────────────────

def test_commented_key_counts_as_present_not_missing(tmp_path):
    af = _compare(tmp_path, {
        "n1": "[S]\nk=1\n",
        "n2": "[S]\n#k=1\n",
    })
    row = _row(af, "[S]", "k")
    assert row.values == {"n1": "1", "n2": "1"}
    assert row.commented == {"n1": False, "n2": True}
    assert row.has_mismatch is False


# ── Rules 5, 8: section check ──────────────────────────────────────────────

def test_empty_section_absent_on_a_node_is_listed(tmp_path):
    af = _compare(tmp_path, {
        "n1": "[Init 1]\n[S]\nk=1\n",
        "n2": "[S]\nk=1\n",
    })
    assert [s["name"] for s in af.sections] == ["[Init 1]", "[S]"]
    assert _section(af, "[Init 1]")["present"] == {"n1": True, "n2": False}
    assert _section(af, "[Init 1]")["base_count"] == 0


def test_section_check_counts_against_first_node(tmp_path):
    af = _compare(tmp_path, {
        "n1": "[S]\na=1\nb=2\nc=3\n#d=4\n",
        "n2": "[S]\na=1\nb=9\nd=4\ne=5\n",
        "n3": "[T]\nx=1\n",
    })
    s = _section(af, "[S]")
    assert s["base"] == "n1"
    assert s["base_count"] == 4
    assert s["present"] == {"n1": True, "n2": True, "n3": False}
    assert s["counts"] == {"n2": {"match": 2, "differ": 1, "missing": 1, "extra": 1}}


def test_base_without_the_file_falls_back_to_first_node_that_has_it(tmp_path):
    af = _compare(
        tmp_path,
        {"n2": "[S]\na=1\n", "n3": "[S]\na=2\n"},
        all_nodes=["n1", "n2", "n3"],
    )
    s = _section(af, "[S]")
    assert s["base"] == "n2"
    assert s["counts"] == {"n3": {"match": 0, "differ": 1, "missing": 0, "extra": 0}}


def test_keys_before_first_header_form_default_section(tmp_path):
    af = _compare(tmp_path, {
        "n1": "k=1\n[S]\na=1\n",
        "n2": "k=2\n[S]\na=1\n",
    })
    assert [s["name"] for s in af.sections] == ["DEFAULT", "[S]"]
    assert _section(af, "DEFAULT")["counts"] == {"n2": {"match": 0, "differ": 1, "missing": 0, "extra": 0}}


# ── Report/patch contract: engine compound must be what patch.py edits ─────

def test_patch_edits_key_that_sat_under_commented_header(tmp_path):
    text = "[App]\nmode=on\n#[Listeners]\nflag=true\n"
    af = _compare(tmp_path, {"n1": "[App]\nmode=on\nflag=true\n", "n2": text})
    row = _row(af, "[App]", "flag")
    change = PatchChange({
        "file": REL, "node": "n2", "compound": row.compound, "key": row.key,
        "section": row.section, "original": "true", "corrected": "false",
    })
    out = AuditPatcher("unused.json")._apply_kv(text, [change])
    assert out == "[App]\nmode=on\n#[Listeners]\nflag=false\n"


# ── Report data and Excel carry the section check and duplicates ───────────

def _result(tmp_path: Path, af: AuditFile, nodes: List[str]) -> AuditResult:
    return AuditResult(
        nodes=nodes, node_dirs={n: str(tmp_path / n) for n in nodes}, files=[af],
        total_mismatches=af.mismatch_count, total_logical_diffs=0,
        run_timestamp="20260915_120000", run_dir=str(tmp_path),
    )


def test_report_data_carries_section_check_and_duplicate_lines(tmp_path):
    af = _compare(tmp_path, {"n1": "[S]\ndefault=A\n", "n2": "[S]\ndefault=B\ndefault=A\n"})
    data = _serialise_result(_result(tmp_path, af, ["n1", "n2"]))
    f = data["files"][0]
    assert [(s["name"], s["counts"]) for s in f["sections"]] == [
        ("[S]", {"n2": {"match": 1, "differ": 0, "missing": 0, "extra": 0}}),   # last value A == base
    ]
    assert f["params"][0]["dupValues"] == {"n2": ["B", "A"]}
    assert f["params"][0]["lines"] == {"n1": [2], "n2": [2, 3]}


def test_diffs_workbook_lists_every_duplicate_value_with_its_line(tmp_path):
    af = _compare(tmp_path, {"n1": "[S]\ndefault=A\n", "n2": "[S]\ndefault=A\ndefault=B\n"})
    path = _write_diffs_xlsx(_result(tmp_path, af, ["n1", "n2"]), str(tmp_path))
    ws = openpyxl.load_workbook(path)["Parameter Diffs"]
    values = [c.value for c in ws[2]]
    assert values[2:6] == ["[S]", "default", "A", "A (L2) | B (L3) → L3 used"]


def test_shell_script_is_compared_as_text_not_kv(tmp_path):
    """Shell scripts are not key/value files (agreed 2026-09-18): audit compares them as text."""
    abs_paths = {}
    for node, text in (("n1", "X=1\nif [ a ]; then\n  run\nfi\n"), ("n2", "X=2\nif [ a ]; then\n  run\nfi\n")):
        path = tmp_path / node / "bin/start.sh"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        abs_paths[node] = str(path)
    engine = AuditEngine(nodes=[], report_dir=str(tmp_path / "reports"))
    af = engine._compare_file("bin/start.sh", ["n1", "n2"], abs_paths, ["n1", "n2"])
    assert af.file_type == "text"
    assert af.mismatch_count >= 1


SSTP_A = "# Copyright\n# comment\nMAPTIMEOUT\n[\n  SET GCT (SRC=0x1e);\n  LOG \"x\";\n]\nROUTING\n[\n  ROUTE APP 0x10\n]\n"


def _sstp(tmp_path, texts):
    abs_paths = {}
    for node, text in texts.items():
        path = tmp_path / node / "cfg/routing-rule.sstp"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        abs_paths[node] = str(path)
    engine = AuditEngine(nodes=[], report_dir=str(tmp_path / "reports"))
    return engine._compare_file("cfg/routing-rule.sstp", list(texts), abs_paths, list(texts))


def test_sstp_blocks_after_leading_comments_are_parsed(tmp_path):
    from configmerge.auditor.sstp_parser import SstpParser
    assert [b.name for b in SstpParser.parse(SSTP_A).blocks] == ["MAPTIMEOUT", "ROUTING"]


def test_sstp_value_difference_is_a_mismatch(tmp_path):
    af = _sstp(tmp_path, {"n1": SSTP_A, "n2": SSTP_A.replace("0x1e", "0x1d")})
    assert af.mismatch_count >= 1


def test_sstp_identical_files_match(tmp_path):
    assert _sstp(tmp_path, {"n1": SSTP_A, "n2": SSTP_A}).mismatch_count == 0


def test_sstp_unparseable_but_different_files_are_a_mismatch(tmp_path):
    af = _sstp(tmp_path, {"n1": "no blocks here a=1\n", "n2": "no blocks here a=2\n"})
    assert af.mismatch_count >= 1
