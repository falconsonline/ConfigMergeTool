"""
Commented lines as context + review annotations (decisions agreed with user 2026-09-17).

  Q9  Base comment lines are copied into the output next to the parameter they describe.
      - base `#k=alt` after active `k=v` (alternative value) → kept right after the merged `k`.
      - base `#k=v` commented-only while release has `k` active → base comment + review annotation
        [CMT-MRG-W014] + release value (release value kept; user confirms).
      - spaces around a commented key are trimmed when that key is a real parameter (`#k = v`);
        prose such as `# Database : description` stays a plain comment.
      - base section commented out (`#[S]`) but active in release → entries stay commented,
        review annotation [CMT-MRG-W015] under the header.
      - tool annotation lines are never copied again on a re-run (no accumulation).
      - a restored base comment identical to the active output line is not copied.
      - commented lines are emitted byte-for-byte (no trailing-space trimming).
      - a production Java class name replaced by the release one gets an in-file review
        annotation showing the production value [CMT-MRG-W017].
  Q10 JSON base `{}` with a populated release object → release keys taken, flagged [CMT-MRG-W016];
      base `[]` with a populated release list → base (empty) kept, flagged [CMT-MRG-W016].
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from configmerge.cli import main


def _merge(tmp_path: Path, name: str, base: str, release: str, run: str = "run1") -> List[str]:
    root = tmp_path / run
    for side, text in (("base", base), ("release", release)):
        path = root / side / "c" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    rc = main(["--base-dir", str(root / "base"), "--release-dirs", str(root / "release"),
               "--output-dir", str(root / "out"), "--report-dir", str(root / "reports")])
    assert rc == 0
    return (root / "out/c" / name).read_text(encoding="utf-8").splitlines()


def _review_lines(lines: List[str]) -> List[str]:
    return [line for line in lines if "REVIEW" in line]


def test_base_commented_release_active_copies_comment_and_asks_for_review(tmp_path):
    out = _merge(tmp_path, "a.properties", "#a=B\n", "a=R\n")
    assert out[0] == "#a=B"
    assert "[CMT-MRG-W014]" in out[1] and "'a'" in out[1]
    assert out[2] == "a=R"


def test_commented_key_with_spaces_stays_next_to_its_parameter(tmp_path):
    out = _merge(tmp_path, "a.properties", "#a = B\n", "x=1\na=R\ny=2\n")
    i = out.index("a=R")
    assert out[i - 2] == "#a = B" and "[CMT-MRG-W014]" in out[i - 1]
    assert out[-1] == "y=2"


def test_base_alternative_value_comment_kept_after_merged_parameter(tmp_path):
    out = _merge(tmp_path, "a.properties", "a=B\n#a=ALT\n", "a=R\n")
    assert out[:2] == ["a=B", "#a=ALT"]
    assert _review_lines(out) == []


def test_comment_already_in_release_is_not_duplicated(tmp_path):
    out = _merge(tmp_path, "a.properties", "a=B\n#a=ALT\n", "a=R\n#a=ALT\n")
    assert out.count("#a=ALT") == 1


def test_prose_comment_with_colon_is_not_a_parameter(tmp_path):
    out = _merge(tmp_path, "a.properties", "# Database : description\na=B\n", "a=R\n")
    assert out.count("# Database : description") == 1
    assert "a=B" in out and _review_lines(out) == []


def test_commented_section_in_base_gets_review_annotation(tmp_path):
    out = _merge(tmp_path, "a.properties", "#[S]\n#k=1\n", "[S]\nk=2\n")
    i = out.index("[S]")
    assert "[CMT-MRG-W015]" in out[i + 1] and "[S]" in out[i + 1]
    assert not any(line.startswith("k=") for line in out)


def test_rerun_on_merged_output_does_not_accumulate_annotations(tmp_path):
    first = _merge(tmp_path, "a.properties", "#a=B\n", "a=R\n")
    second = _merge(tmp_path, "a.properties", "\n".join(first) + "\n", "a=R\n", run="run2")
    # the old annotation is not carried over; `a` is active in this base, so nothing to review
    assert _review_lines(second) == []
    assert second.count("#a=B") == 1


def test_json_empty_object_in_base_takes_release_keys_and_is_flagged(tmp_path, capsys):
    out = _merge(tmp_path, "a.json", '{"ep": {}, "k": 1}', '{"ep": {"x": 1}, "k": 2}')
    assert json.loads("\n".join(out)) == {"ep": {"x": 1}, "k": 1}
    assert "[CMT-MRG-W016]" in capsys.readouterr().out


def test_json_empty_list_in_base_is_kept_and_flagged(tmp_path, capsys):
    out = _merge(tmp_path, "a.json", '{"hosts": []}', '{"hosts": ["h1"]}')
    assert json.loads("\n".join(out)) == {"hosts": []}
    assert "[CMT-MRG-W016]" in capsys.readouterr().out


def test_restored_comment_identical_to_active_line_is_not_copied(tmp_path):
    out = _merge(tmp_path, "a.properties", "#a=100\n", "a=100\n")
    assert out.count("#a=100") == 0
    assert "[CMT-MRG-W014]" in out[0] and out[1] == "a=100"


def test_commented_lines_keep_trailing_spaces(tmp_path):
    text = "[A]\n#k    \t   :\tval \n[B]\nk=1\n"
    out = _merge(tmp_path, "a.properties", text, text.replace("k=1", "k=2"))
    assert "#k    \t   :\tval " in out


def test_java_class_replaced_by_release_shows_production_value_for_review(tmp_path):
    out = _merge(tmp_path, "a.properties",
                 "executor.class=com.x.BaseRuleExecutor\n###executor.class=com.x.EmbeddedRuleExecutor\n",
                 "executor.class=com.x.EmbeddedRuleExecutor\n")
    i = out.index("executor.class=com.x.EmbeddedRuleExecutor")
    assert "[CMT-MRG-W017]" in out[i - 1] and "com.x.BaseRuleExecutor" in out[i - 1]
    assert "###executor.class=com.x.EmbeddedRuleExecutor" not in out
