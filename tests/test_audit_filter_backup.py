"""
Audit file filter and backup-file detection (QE F-021..F-026, decisions agreed 2026-09-18).

  F-021  A `+path` force-include does not switch the filter to include-only mode.
  F-022  `!name` (no '/') excludes a file OR a directory with that name.
  F-023  A glob include containing '/' is matched against the relative path.
  F-024  A backup marker (bkp/bak/backup/orig/org/old/save) may be followed by any text
         (`_bkp200821`, `_bak17062026`); `_YYYYMMDDHHmmss` is a backup suffix too.
  F-025  A marker before the extension (`fsmapp_240226.properties`) is a backup when
         `fsmapp.properties` exists in the same directory.
  F-026  `_v2`-style names are NOT backups (can be a real separate version).
  A file is only ever treated as a backup when its original exists next to it.
"""

from __future__ import annotations

import pytest

from configmerge.auditor.engine import AuditEngine
from configmerge.auditor.file_filter import FileFilter


def _filter(tmp_path, rules: str) -> FileFilter:
    path = tmp_path / "filter.txt"
    path.write_text(rules, encoding="utf-8")
    return FileFilter(str(path))


def test_force_include_alone_does_not_switch_to_include_only(tmp_path):
    f = _filter(tmp_path, "!logs/archive\n+logs/archive/current\n")
    assert f.should_include("config/app.properties").included
    assert f.should_include("logs/archive/current/x.log").included
    assert not f.should_include("logs/archive/old/x.log").included


@pytest.mark.parametrize("path, included", [
    ("backup/app.properties", False),
    ("config/backup/app.properties", False),
    ("backup", False),
    ("config/backups/app.properties", True),
    ("config/app.properties", True),
])
def test_exclude_name_matches_file_or_directory(tmp_path, path, included):
    assert _filter(tmp_path, "!backup\n").should_include(path).included is included


def test_glob_include_with_directory_matches_relative_path(tmp_path):
    f = _filter(tmp_path, "config/*.xml\n")
    assert f.should_include("config/server.xml").included
    assert not f.should_include("other/server.xml").included


@pytest.fixture
def engine(tmp_path):
    return AuditEngine(nodes=[], report_dir=str(tmp_path / "reports"))


@pytest.mark.parametrize("name, original, is_backup", [
    ("GTPProxy.cfg_bkp_27072024", "GTPProxy.cfg", True),
    ("fsmapp.properties_bkp200821", "fsmapp.properties", True),
    ("server.xml_bak17062026", "server.xml", True),
    ("fsmapp.properties_bkpprobetrouleshoot", "fsmapp.properties", True),
    ("app.properties_20240727153000", "app.properties", True),
    ("fsmapp_240226.properties", "fsmapp.properties", True),
    ("dbwriter_bkp040322.cfg", "dbwriter.cfg", True),
    ("style_old_11jan07.css", "style.css", True),
    ("gtpproxy_v2.mib", "gtpproxy.mib", False),
    ("fsmapp.properties_couchbase", "fsmapp.properties", False),
    ("fsmapp_240226.properties", None, False),
])
def test_backup_detection(engine, name, original, is_backup):
    siblings = {name} | ({original} if original else set())
    assert engine._is_backup_file(name, siblings) is is_backup
