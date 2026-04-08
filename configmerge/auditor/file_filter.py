"""
configmerge.auditor.file_filter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
FileFilter — parse and apply a filter file for audit mode (Phase 3.3).

Filter file format (plain text, ``#`` = comment, blank lines ignored)::

    # a) Suffix only — include ALL files with this extension
    json
    xml
    cfg
    properties

    # b) Suffix::filename(s) — only named files with this suffix
    conf::sysctl.conf,sctp.conf,spread.conf
    txt::config.txt,system.txt

    # c) Suffix::directory — only files inside directories matching pattern
    html::runtime,test

    # d) Explicit name excludes (leading !)
    !nohup.out

    # e) Built-in always-excluded binary archive extensions (applied even when
    #    no --filter-file is given).  List them here to document, but they are
    #    hard-coded in FileFilter as BINARY_EXCLUDES.
    !*.tar
    !*.tar.gz
    !*.gz
    !*.rpm
    !*.zip
    !*.jar
    !*.war
    !*.ear
    !*.jks
    !*.keystore
    !*.p12
    !*.pem

Behaviour
---------
* If ``--filter-file`` is **not** provided: only ``BINARY_EXCLUDES`` are
  skipped; everything else is compared.
* If ``--filter-file`` is provided **with** include rules: only matching
  files are processed; all others are skipped and recorded in
  ``<run_dir>/feedback/filtered_files.json``.
* Exclude rules (``!``) are evaluated **after** include rules; a file that
  would be included but matches an exclude rule is skipped.
* Filename matching (rule b) is **case-insensitive** for cross-platform safety.
* If a directory has no files passing the filter its subtree is skipped.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Built-in binary archive extensions — always excluded
# ---------------------------------------------------------------------------

BINARY_EXCLUDES: Set[str] = {
    ".tar", ".gz", ".bz2", ".xz", ".tgz",
    ".rpm", ".deb",
    ".zip", ".7z", ".rar",
    ".jar", ".war", ".ear",
    ".jks", ".keystore", ".p12", ".pfx",
    ".pem", ".crt", ".cer", ".der",
    ".so", ".dll", ".exe", ".dylib",
    ".class", ".pyc",
    ".bin", ".img", ".iso",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class _Rule:
    """One parsed line from the filter file."""
    kind: str               # "include_suffix" | "include_named" | "include_dir"
                            #   | "exclude_name" | "exclude_glob"
    suffix: str             # e.g. ".cfg"   (always lower-case with leading dot)
    names: Set[str]         # file basenames (lower-cased) — for "include_named"
    dirs: Set[str]          # directory name fragments — for "include_dir"
    glob: str               # glob pattern — for "exclude_glob"


@dataclass
class FilterResult:
    """Outcome of FileFilter.should_include()."""
    included: bool
    reason: str             # human-readable explanation for skipped_files.json


# ---------------------------------------------------------------------------
# FileFilter
# ---------------------------------------------------------------------------

class FileFilter:
    """Parse a filter file and decide whether a given file should be audited."""

    def __init__(self, filter_file_path: Optional[str] = None) -> None:
        self._rules: List[_Rule] = []
        self._has_include_rules = False

        if filter_file_path:
            self._parse(filter_file_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_include(self, rel_path: str) -> FilterResult:
        """Return whether *rel_path* (forward-slash relative path) should be audited.

        Parameters
        ----------
        rel_path:
            Forward-slash relative path from the node base_dir,
            e.g. ``"config/server.xml"`` or ``"GTPProxy.cfg"``.
        """
        fname = rel_path.split("/")[-1]
        fname_lower = fname.lower()
        ext_lower = os.path.splitext(fname_lower)[1]   # e.g. ".cfg"
        parts_lower = [p.lower() for p in rel_path.split("/")[:-1]]

        # Always-excluded binary archives
        if ext_lower in BINARY_EXCLUDES:
            return FilterResult(False, f"binary archive extension {ext_lower!r}")

        # Process explicit exclude rules first
        for rule in self._rules:
            if rule.kind == "exclude_name":
                if fname_lower in rule.names:
                    return FilterResult(False, f"exclude rule: {fname!r}")
            elif rule.kind == "exclude_glob":
                if fnmatch.fnmatch(fname_lower, rule.glob):
                    return FilterResult(False, f"exclude glob: {rule.glob!r}")

        # If no include rules are defined, everything passes
        if not self._has_include_rules:
            return FilterResult(True, "no include rules — pass-through")

        # Check include rules
        for rule in self._rules:
            if rule.kind == "include_suffix":
                if ext_lower == rule.suffix:
                    return FilterResult(True, f"suffix rule: {rule.suffix!r}")
            elif rule.kind == "include_named":
                if ext_lower == rule.suffix and fname_lower in rule.names:
                    return FilterResult(True,
                                        f"named rule: {rule.suffix!r}::{fname!r}")
            elif rule.kind == "include_dir":
                # File is included if any parent directory matches one of the listed dirs
                if ext_lower == rule.suffix and any(d in parts_lower for d in rule.dirs):
                    return FilterResult(True,
                                        f"dir rule: {rule.suffix!r}::{parts_lower!r}")

        return FilterResult(False, "no include rule matched")

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------

    def _parse(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as exc:
            raise ValueError(f"Cannot read filter file {path!r}: {exc}") from exc

        for lineno, raw in enumerate(lines, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # Explicit exclude: !filename  or  !*.glob
            if line.startswith("!"):
                pattern = line[1:].strip().lower()
                if '*' in pattern or '?' in pattern or '[' in pattern:
                    self._rules.append(_Rule(
                        kind="exclude_glob", suffix="",
                        names=set(), dirs=set(), glob=pattern,
                    ))
                else:
                    self._rules.append(_Rule(
                        kind="exclude_name", suffix="",
                        names={pattern}, dirs=set(), glob="",
                    ))
                continue

            # suffix::names_or_dirs
            if "::" in line:
                left, _, right = line.partition("::")
                suffix = self._normalise_suffix(left.strip())
                items  = {s.strip().lower() for s in right.split(",") if s.strip()}
                # Heuristic: if any item contains '/' or looks like a directory name
                # (no extension) → treat as dir rule; otherwise filename rule
                if items and all("." not in item for item in items):
                    self._rules.append(_Rule(
                        kind="include_dir", suffix=suffix,
                        names=set(), dirs=items, glob="",
                    ))
                else:
                    self._rules.append(_Rule(
                        kind="include_named", suffix=suffix,
                        names=items, dirs=set(), glob="",
                    ))
                self._has_include_rules = True
                continue

            # Plain suffix (e.g. "cfg", ".cfg", "json")
            suffix = self._normalise_suffix(line)
            if suffix:
                self._rules.append(_Rule(
                    kind="include_suffix", suffix=suffix,
                    names=set(), dirs=set(), glob="",
                ))
                self._has_include_rules = True

    @staticmethod
    def _normalise_suffix(text: str) -> str:
        """Return a lower-case suffix with a leading dot, e.g. 'cfg' → '.cfg'."""
        s = text.strip().lower()
        if not s:
            return ""
        if not s.startswith("."):
            s = "." + s
        return s
