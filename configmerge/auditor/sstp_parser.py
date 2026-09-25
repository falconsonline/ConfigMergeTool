"""
configmerge.auditor.sstp_parser
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Parser for Roamware Smart-STP (``.sstp``) routing rule scripts (Phase 8).

Format
------
Files are auto-generated SSTP routing rule scripts consisting of top-level
named blocks with optional parameters, each with a ``[...]`` body::

    MAPTIMEOUT [
        ...
    ]

    GCT (0x33) [
        CDPA(...) [ SET GCT(SRC=0x53) ... ]
    ]

Comments begin with ``#`` and run to end-of-line.
Nested ``[`` / ``]`` pairs are handled by tracking depth.

Usage
-----
::

    doc = SstpParser.parse(text)
    for block in doc.blocks:
        print(block.name, block.params, block.params_extracted)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SstpBlock:
    """One top-level named block in an SSTP file."""
    name: str                       # e.g. "GCT"
    params: str                     # e.g. "(0x33)"  or ""
    body_raw: str                   # text inside the outermost [ ... ], comments stripped
    text: str = ""                  # original lines of the block, verbatim (comments kept)
    cmp: str = ""                   # ``text`` with all whitespace removed — the comparison key
    start_line: int = 0             # 1-based line of the block header
    end_line: int = 0               # 1-based line of the closing ']'
    params_extracted: Dict[str, object] = field(default_factory=dict)
    # Compound key for AuditParam: "BLOCK|GCT(0x33)"
    compound: str = ""


@dataclass
class SstpDoc:
    """Parsed SSTP document."""
    blocks: List[SstpBlock] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extraction regexes
# ---------------------------------------------------------------------------

_RE_SET_GCT_SRC  = re.compile(r'SET\s+GCT\s*\(\s*SRC\s*=\s*([^),\s]+)', re.IGNORECASE)
_RE_SPC          = re.compile(r'SPC\s*=\s*([^\s,)]+)', re.IGNORECASE)
_RE_DIGITS       = re.compile(r'DIGITS\s*\(([^)]+)\)', re.IGNORECASE)
_RE_ROUTE        = re.compile(r'ROUTE\s+(?:APP|STACK)\s+(0x[0-9a-fA-F]+)', re.IGNORECASE)
_RE_SPREAD       = re.compile(r'SPREAD\s*\(([^)]+)\)', re.IGNORECASE)
# No '^': used with .match(text, pos), which already anchors at pos — a '^' only ever matched
# at offset 0, so blocks after leading comments were never parsed (F-030).
_RE_BLOCK_HDR    = re.compile(r'\s*([A-Z_][A-Z0-9_]*)\s*(\([^)]*\))?\s*\[', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class SstpParser:
    """Parse a ``.sstp`` file into a ``SstpDoc``."""

    @classmethod
    def parse(cls, text: str) -> SstpDoc:
        # Strip comments (brackets inside comments must not count); one clean line per original line
        orig  = text.splitlines()
        lines = []
        for raw in orig:
            idx = raw.find('#')
            lines.append(raw[:idx] if idx >= 0 else raw)
        clean = "\n".join(lines)

        doc = SstpDoc()
        pos = 0
        n   = len(clean)

        while pos < n:
            # Skip whitespace
            while pos < n and clean[pos] in ' \t\r\n':
                pos += 1
            if pos >= n:
                break

            # Try to match a block header: NAME [  or  NAME (params) [
            m = _RE_BLOCK_HDR.match(clean, pos)
            if not m:
                # Skip this line — not a block header
                end = clean.find('\n', pos)
                pos = end + 1 if end >= 0 else n
                continue

            block_name   = m.group(1).upper()
            block_params = (m.group(2) or "").strip()
            bracket_pos  = m.end() - 1  # position of '['
            pos = bracket_pos + 1

            # Collect body up to matching ']'
            depth      = 1
            body_start = pos
            while pos < n and depth > 0:
                if clean[pos] == '[':
                    depth += 1
                elif clean[pos] == ']':
                    depth -= 1
                pos += 1

            body_raw   = clean[body_start: pos - 1]
            compound   = f"BLOCK|{block_name}{block_params}"
            start_line = clean.count('\n', 0, m.start(1)) + 1
            end_line   = clean.count('\n', 0, pos - 1) + 1
            block_text = "\n".join(orig[start_line - 1:end_line])

            block = SstpBlock(
                name             = block_name,
                params           = block_params,
                body_raw         = body_raw,
                text             = block_text,
                cmp              = "".join(block_text.split()),
                start_line       = start_line,
                end_line         = end_line,
                params_extracted = cls._extract_params(body_raw),
                compound         = compound,
            )
            doc.blocks.append(block)

        return doc

    # ------------------------------------------------------------------
    # Parameter extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_params(body: str) -> Dict[str, object]:
        """Extract key named parameters from a block body for diff display."""
        result: Dict[str, object] = {}

        # SET GCT(SRC=...)
        m = _RE_SET_GCT_SRC.search(body)
        if m:
            result["src"] = m.group(1).strip()

        # SPC=...  (all occurrences)
        spcs = [m.group(1).strip() for m in _RE_SPC.finditer(body)]
        if spcs:
            result["spc"] = spcs

        # DIGITS(...)  — sort items for order-normalised comparison
        digits_matches = [m.group(1).strip() for m in _RE_DIGITS.finditer(body)]
        if digits_matches:
            result["digits"] = [
                sorted(d.split(',')) for d in digits_matches
            ]

        # ROUTE APP/STACK 0x... — preserve order (order matters)
        routes = [m.group(1).strip() for m in _RE_ROUTE.finditer(body)]
        if routes:
            result["routes"] = routes

        # SPREAD(...)
        spreads = [m.group(1).strip() for m in _RE_SPREAD.finditer(body)]
        if spreads:
            result["spread"] = spreads

        return result


# ---------------------------------------------------------------------------
# Diff categorisation helpers
# ---------------------------------------------------------------------------

def categorise_block_diff(a: SstpBlock, b: SstpBlock) -> str:
    """Informational label for two versions of the same block (never decides match).

    Returns one of:
    - ``"MATCH"``       — identical once whitespace is removed (comments count)
    - ``"VALUE_DIFF"``  — a route target, SRC, SPC or DIGITS value differs
    - ``"ORDER_DIFF"``  — same routes / digits, different order
    - ``"TEXT_DIFF"``   — any other difference (statements moved, comments, …)
    """
    if a.cmp == b.cmp:
        return "MATCH"

    pe_a = a.params_extracted
    pe_b = b.params_extracted

    routes_a, routes_b = pe_a.get("routes") or [], pe_b.get("routes") or []
    if routes_a != routes_b:
        return "ORDER_DIFF" if sorted(routes_a) == sorted(routes_b) else "VALUE_DIFF"  # type: ignore[arg-type]

    for key in ("src", "spc"):
        if pe_a.get(key) != pe_b.get(key):
            return "VALUE_DIFF"

    digits_a, digits_b = pe_a.get("digits") or [], pe_b.get("digits") or []
    if digits_a != digits_b:
        return "ORDER_DIFF" if sorted(digits_a) == sorted(digits_b) else "VALUE_DIFF"  # type: ignore[arg-type]

    return "TEXT_DIFF"
