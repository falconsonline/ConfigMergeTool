"""
KV merge fidelity (QE F-020, decisions agreed with user 2026-09-18).

A file merged with itself must come out byte-for-byte unchanged and produce no report rows —
the KV processor is called directly so the engine's whitespace-only shortcut cannot hide defects.

  F-020a  A key commented out in both base and release is a comment, not a release-only parameter.
  F-020b  EMPTY_BASE_OVERRIDE only when base is empty and the release value is not.
  F-020c  Comment lines are copied exactly once (no duplicates, none dropped).
  F-020d  A section header repeated in one file keeps both blocks in place (release order).
  F-020e  `.sh` shell scripts are not KV-merged — the release copy is deployed as-is.
  F-020f  Blank lines between sections come from the release file, none are invented.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

from configmerge.cli import main
from configmerge.models import MergeConfig
from configmerge.processors.kv import KVProcessor


def _kv(tmp_path: Path, base: str, release: str) -> Tuple[str, List[str]]:
    (tmp_path / "base").mkdir(exist_ok=True)
    (tmp_path / "release").mkdir(exist_ok=True)
    b, r, out = tmp_path / "base/a.cfg", tmp_path / "release/a.cfg", tmp_path / "out.cfg"
    b.write_text(base, encoding="utf-8")
    r.write_text(release, encoding="utf-8")
    logger = logging.getLogger("kv-fidelity")
    logger.addHandler(logging.NullHandler())
    config = MergeConfig(base_dir=str(tmp_path / "base"), release_dirs=[str(tmp_path / "release")],
                         output_dir=str(tmp_path / "o"))
    entries = KVProcessor().process([str(b)], str(r), str(out), config, logger)
    return out.read_text(encoding="utf-8"), [e.type for e in entries]


def _identity(tmp_path: Path, text: str) -> None:
    out, types = _kv(tmp_path, text, text)
    assert out == text
    assert types == []


def test_key_commented_in_both_is_not_release_only(tmp_path):
    _identity(tmp_path, "#log4j.appender.logfile=x\nlog4j.rootLogger=INFO\n")


def test_empty_in_both_is_not_an_empty_base_override(tmp_path):
    _identity(tmp_path, "[Generic Cache]\ngeneric.caches=\n")


def test_empty_base_with_release_value_is_still_an_override(tmp_path):
    _, types = _kv(tmp_path, "k=\n", "k=v\n")
    assert types == ["EMPTY_BASE_OVERRIDE"]


def test_commented_group_entry_is_not_duplicated(tmp_path):
    _identity(tmp_path, "[S]\ntrans.filter.1.code=1\n## note\n#trans.filter.1.results=x\ntrans.filter.2.code=2\n")


def test_group_annotation_is_not_duplicated(tmp_path):
    _identity(tmp_path, "[S]\nrpc.x.1.name=a\n#rpc.x.1.dist=old\nrpc.x.1.dist=new\n")


def test_blank_lines_between_sections_come_from_release(tmp_path):
    _identity(tmp_path, "a=1\n[S]\n# heading\nb=2\n# end of S\n[T]\nc=3\n\n\n[U]\nd=4\n")


def test_repeated_section_keeps_both_blocks_in_place(tmp_path):
    text = "[A]\na=1\n\n[B]\nb=1\n\n[A]\nc=1\n"
    _identity(tmp_path, text)
    out, _ = _kv(tmp_path, text.replace("c=1", "c=BASE"), text)
    assert out == text.replace("c=1", "c=BASE")


def test_shell_script_release_copied_as_is(tmp_path):
    for side, text in (("base", "X=1\nif [ a ]; then\n  run\nfi\n"), ("release", "X=2\nif [ b ]; then\n  go\nfi\n")):
        (tmp_path / side).mkdir()
        (tmp_path / side / "start.sh").write_text(text, encoding="utf-8")
    main(["--base-dir", str(tmp_path / "base"), "--release-dirs", str(tmp_path / "release"),
          "--output-dir", str(tmp_path / "out"), "--report-dir", str(tmp_path / "reports")])
    assert (tmp_path / "out/start.sh").read_text(encoding="utf-8") == "X=2\nif [ b ]; then\n  go\nfi\n"


def test_comment_above_duplicate_group_key_is_kept(tmp_path):
    text = "[S]\nrpc.x.152.servers=1\n\n### For COS\nrpc.x.152.servers=2\nrpc.x.server.152.1.name=a\n"
    out, _ = _kv(tmp_path, text, text)
    assert out.count("### For COS") == 1
    assert out.count("rpc.x.152.servers=") == 1
