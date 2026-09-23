"""
configmerge.auditor.mapping
~~~~~~~~~~~~~~~~~~~~~~~~~~~
--mapping-file support for audit mode: files that live at different relative paths on
different nodes are compared in one report row.

Format — one pair per line, ``LEFT=RIGHT``; ``#`` lines and blank lines are ignored:

    STG/dra-SA/Chart.yaml=PROD/dra-SA-1/Chart.yaml     file line
    STG/dra-SA=PROD/dra-SA-1                           directory line (whole subtree)

The first path component names the node (its ``base_dir``, the basename of it, or its
``name``); a leading ``/`` is ignored. The LEFT file is placed into the report row of the
RIGHT path, so one LEFT file mapped to several instances (dra-SA-1, dra-SA-2, …) appears
in each instance's row (agreed 2026-09-23). A file line overrides a directory line for the
same row.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from ..errors import ConfigMergeError, tag
from ..models import BaseDirConfig

# (left node, left rel_path, right node, right rel_path) of one mapping line
MappingPair = Tuple[str, str, str, str]


@dataclass
class MappingResult:
    """row rel_path -> {node: actual rel_path on that node}, plus skipped-pair warnings."""
    rows: Dict[str, Dict[str, str]]
    applied: int = 0
    warnings: List[str] = field(default_factory=list)


def _node_prefixes(nodes: List[BaseDirConfig]) -> List[Tuple[str, str]]:
    """(prefix, node name) pairs, longest prefix first: full base_dir, its basename, the name."""
    out: List[Tuple[str, str]] = []
    for n in nodes:
        full = os.path.normpath(n.base_dir).replace(os.sep, "/").strip("/")
        for prefix in (full, os.path.basename(full), n.name):
            if prefix and (prefix, n.name) not in out:
                out.append((prefix, n.name))
    return sorted(out, key=lambda p: -len(p[0]))


def _split_side(raw: str, prefixes: List[Tuple[str, str]], path: str, lineno: int) -> Tuple[str, str]:
    side = raw.strip().replace("\\", "/").strip("/")
    for prefix, node in prefixes:
        if side.startswith(prefix + "/"):
            return node, side[len(prefix) + 1:]
    raise ConfigMergeError(
        "CMT-CLI-E018",
        f"{path}:{lineno}: {raw.strip()!r} does not start with a node directory or name "
        f"({', '.join(sorted({p for p, _ in prefixes}))}).",
    )


def load_audit_mapping(path: str, nodes: List[BaseDirConfig]) -> List[MappingPair]:
    """Parse the mapping file into (left_node, left_rel, right_node, right_rel) pairs."""
    prefixes = _node_prefixes(nodes)
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as exc:
        raise ConfigMergeError("CMT-CLI-E018", f"Cannot read mapping file {path!r}: {exc}") from exc
    pairs: List[MappingPair] = []
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ConfigMergeError("CMT-CLI-E018", f"{path}:{lineno}: expected LEFT=RIGHT, got {stripped!r}.")
        left, right = stripped.split("=", 1)
        pairs.append(_split_side(left, prefixes, path, lineno) + _split_side(right, prefixes, path, lineno))
    return pairs


def _is_dir(files: Set[str], rel: str) -> bool:
    prefix = rel + "/"
    return any(f.startswith(prefix) for f in files)


def resolve_mapping(node_files: Dict[str, Set[str]], pairs: List[MappingPair]) -> MappingResult:
    """Build report rows from the scanned (already filtered) files and the mapping pairs."""
    rows: Dict[str, Dict[str, str]] = {}
    for node, files in node_files.items():
        for rel in files:
            rows.setdefault(rel, {})[node] = rel

    warnings: List[str] = []
    # (left node, row) -> (left actual rel, priority): a file line (2) beats a directory line (1)
    placements: Dict[Tuple[str, str], Tuple[str, int]] = {}

    def place(l_node: str, l_rel: str, row: str, prio: int) -> None:
        cur = placements.get((l_node, row))
        if cur is None or prio > cur[1]:
            placements[(l_node, row)] = (l_rel, prio)

    for l_node, l_rel, r_node, r_rel in pairs:
        l_files, r_files = node_files.get(l_node, set()), node_files.get(r_node, set())
        if l_rel in l_files and r_rel in r_files:
            if l_rel != r_rel:
                place(l_node, l_rel, r_rel, 2)
        elif _is_dir(l_files, l_rel) and _is_dir(r_files, r_rel):
            if l_rel != r_rel:
                for f in r_files:
                    if f.startswith(r_rel + "/"):
                        src = l_rel + f[len(r_rel):]
                        if src in l_files:
                            place(l_node, src, f, 1)
        else:
            missing = [f"{n}/{r}" for n, r, fs in ((l_node, l_rel, l_files), (r_node, r_rel, r_files))
                       if r not in fs and not _is_dir(fs, r)]
            if len(missing) == 2:
                continue    # both sides hidden/filtered/binary-excluded on purpose — nothing to compare
            warnings.append(tag("CMT-AUD-W011",
                                f"Mapping {l_node}/{l_rel} = {r_node}/{r_rel} skipped: "
                                f"{', '.join(missing) or 'file vs directory'} not found "
                                f"(absent, hidden, backup or filtered)"))

    applied = 0
    consumed: Set[Tuple[str, str]] = set()
    for (l_node, row), (l_rel, _) in sorted(placements.items()):
        if rows[row].get(l_node) == row:
            # The node already has its own file at this path — never hide it behind a mapping
            warnings.append(tag("CMT-AUD-W011",
                                f"Mapping {l_node}/{l_rel} -> row {row} skipped: "
                                f"{l_node} already has its own {row}"))
            continue
        rows[row][l_node] = l_rel
        consumed.add((l_node, l_rel))
        applied += 1

    # A mapped file's own row goes away unless another node shares that path
    for l_node, l_rel in consumed:
        row = rows.get(l_rel)
        if row is not None and row.get(l_node) == l_rel and len(row) == 1:
            del rows[l_rel]

    return MappingResult(rows=rows, applied=applied, warnings=warnings)
