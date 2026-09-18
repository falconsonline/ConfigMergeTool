"""
Every emitted error/warning carries a stable, unique, documented identifier (agreed 2026-09-17).

  - Codes look like CMT-<AREA>-<E|W|I><nnn> and are unique.
  - Every log_structured(type, action) pair used in the package has a registered code.
  - Every code literal used in the package is registered, and every registered code is
    listed in ConfigMergeTool-readme.txt.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from configmerge.errors import CODES, STRUCTURED_CODES

PKG = Path(__file__).resolve().parent.parent / "configmerge"
README = PKG.parent / "ConfigMergeTool-readme.txt"
CODE_RE = re.compile(r"CMT-[A-Z]{3}-[EWI]\d{3}")


def test_codes_are_well_formed():
    assert all(CODE_RE.fullmatch(code) for code in CODES)
    assert set(STRUCTURED_CODES.values()) <= set(CODES)


def test_every_log_structured_pair_is_registered():
    missing = []
    for path in PKG.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            func = getattr(node, "func", None)
            if isinstance(node, ast.Call) and getattr(func, "id", getattr(func, "attr", "")) == "log_structured":
                pair = tuple(arg.value for arg in node.args[2:4])
                if pair not in STRUCTURED_CODES:
                    missing.append(f"{path.name}:{node.lineno} {pair}")
    assert missing == []


def test_every_code_used_is_registered_and_documented():
    used = set()
    for path in PKG.rglob("*.py"):
        if path.name != "errors.py":
            used |= set(CODE_RE.findall(path.read_text(encoding="utf-8")))
    assert used - set(CODES) == set()
    readme = README.read_text(encoding="utf-8")
    assert [code for code in CODES if code not in readme] == []
