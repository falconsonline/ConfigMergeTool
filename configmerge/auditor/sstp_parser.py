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
    body_raw: str                   # raw text inside the outermost [ ... ]
    body_norm: str                  # normalised body for direct comparison
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
_RE_BLOCK_HDR    = re.compile(r'^\s*([A-Z_][A-Z0-9_]*)\s*(\([^)]*\))?\s*\[', re.IGNORECASE)

# Normalise SET CDPA (A) AND SET CDPA (B) → SET CDPA (A,B)
_RE_MULTI_SETCDPA = re.compile(
    r'SET\s+(CDPA|CGPA|SCCP)\s*\(([^)]*)\)\s*AND\s+SET\s+\1\s*\(([^)]*)\)',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class SstpParser:
    """Parse a ``.sstp`` file into a ``SstpDoc``."""

    @classmethod
    def parse(cls, text: str) -> SstpDoc:
        # Strip comments
        lines = []
        for raw in text.splitlines():
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

            body_raw  = clean[body_start: pos - 1]
            body_norm = cls._normalise_body(body_raw)
            compound  = f"BLOCK|{block_name}{block_params}"

            block = SstpBlock(
                name             = block_name,
                params           = block_params,
                body_raw         = body_raw,
                body_norm        = body_norm,
                params_extracted = cls._extract_params(body_raw),
                compound         = compound,
            )
            doc.blocks.append(block)

        return doc

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_body(body: str) -> str:
        """Collapse whitespace, normalise SET X(A) AND SET X(B) → SET X(A,B)."""
        # Collapse multi SET ... AND SET ... for structural equivalence
        norm = body
        changed = True
        while changed:
            new = _RE_MULTI_SETCDPA.sub(
                lambda m: f"SET {m.group(1).upper()} ({m.group(2).strip()},{m.group(3).strip()})",
                norm,
                flags=re.IGNORECASE,
            )
            changed = new != norm
            norm = new

        # Collapse whitespace
        norm = re.sub(r'\s+', ' ', norm).strip()
        return norm

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
    """Return a diff category for two versions of the same block.

    Returns one of:
    - ``"VALUE_DIFF"``      — parameter values differ
    - ``"ORDER_DIFF"``      — route order differs
    - ``"STRUCT_EQUIV"``    — structurally equivalent (whitespace / ordering)
    - ``"MATCH"``           — identical
    """
    if a.body_norm == b.body_norm:
        return "MATCH"

    # Strip whitespace from raw bodies for structural comparison
    raw_a = re.sub(r'\s+', ' ', a.body_raw).strip()
    raw_b = re.sub(r'\s+', ' ', b.body_raw).strip()
    if raw_a == raw_b:
        return "MATCH"

    # Check if normalised bodies match (structural equivalence after merging
    # multi-SET patterns)
    if a.body_norm == b.body_norm:
        return "STRUCT_EQUIV"

    pe_a = a.params_extracted
    pe_b = b.params_extracted

    # Route order diff
    if pe_a.get("routes") != pe_b.get("routes"):
        # Check if it's purely order (same set, different order)
        if (pe_a.get("routes") and pe_b.get("routes") and
                sorted(pe_a["routes"]) == sorted(pe_b["routes"])):  # type: ignore[arg-type]
            return "ORDER_DIFF"
        # Otherwise it's a value diff (different route targets)
        return "VALUE_DIFF"

    # Value diff in named params
    for key in ("src", "spc"):
        if pe_a.get(key) != pe_b.get(key):
            return "VALUE_DIFF"

    # Digits order diff
    if pe_a.get("digits") != pe_b.get("digits"):
        return "ORDER_DIFF"

    # Catch-all — treat as structural equivalent if normalised bodies match
    return "STRUCT_EQUIV"
