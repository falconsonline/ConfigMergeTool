"""
configmerge.processors.yaml_proc
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
YAML processor (.yaml, .yml) — e.g. Helm values.yaml (rules: MEMORY.md, 2026-09-28).

Merge: base (site) values win, base-only parameters are added in the same section,
release-only parameters are kept. Parameters are matched through the shared YAML model
(configmerge.yaml_model): maps by key, list entries by their first field, instance blocks by
position — so the order of entries never matters.

The release file's text is edited in place, so its layout and comments survive: a differing
value is rewritten where it stands, and a base-only map key or list entry is copied from the
base file (re-indented to the release section) right after the end of that section.

A base value that cannot be written into the release layout (the section is inline/flow style
or empty, or the value is a map in one file and a scalar in the other) is not forced: the
release value stays and YAML_NOT_MERGED asks for review. Files with template code ({{ }}) or
invalid YAML keep the release copy (YAML_RELEASE_COPIED when the site copy differs).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple, Union

from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from . import register, BaseProcessor
from ..logger import log_structured
from ..models import EntryType, MergeConfig, ReportEntry
from ..utils import detect_api_version_upgrade, ensure_dir, is_java_fqcn, open_text
from ..yaml_model import NotPlainYaml, parse_yaml_nodes, path_ancestors


class _Doc:
    """A parsed YAML text: parameters, container spans and the node behind every path."""

    def __init__(self, text: str):
        self.text = text
        self.params, self.spans, self.nodes = parse_yaml_nodes(text)


def _squeeze(text: str) -> str:
    return "".join(text.split())


def _section(path: str) -> str:
    return path_ancestors(path)[0] if path else ""


def _end_line(node: Node) -> int:
    """0-based index of the last line a node occupies. A block map or list "ends" where the
    next token starts, so its last line is taken from its last child."""
    if isinstance(node, MappingNode) and node.value and not node.flow_style:
        return _end_line(node.value[-1][1])
    if isinstance(node, SequenceNode) and node.value and not node.flow_style:
        return _end_line(node.value[-1])
    end = node.end_mark.line
    if node.end_mark.column == 0 and end > node.start_mark.line:
        end -= 1
    return end


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _reindent(line: str, delta: int) -> str:
    if not line.strip():
        return line
    if delta >= 0:
        return " " * delta + line
    return line[min(-delta, _indent(line)):]


def _parent(path: str, nodes: Dict[str, Tuple[Node, Optional[Node]]]) -> str:
    """Nearest enclosing path that is a real node ('' = the document root)."""
    chain = [a for a in path_ancestors(path) if a in nodes and a != path]
    return chain[-1] if chain else ""


def _unit_lines(unit: str, base: _Doc, rel: _Doc, rel_lines: List[str]) -> Union[str, Tuple[int, List[str]]]:
    """Lines to insert for a base-only map key / list entry, and the release line to insert
    them after — or the reason it cannot be inserted without breaking the release layout."""
    parent = _parent(unit, base.nodes)
    if parent not in rel.nodes or parent not in base.nodes:
        return "its section is not in the release file"
    rnode, _ = rel.nodes[parent]
    bparent, _ = base.nodes[parent]
    if type(rnode) is not type(bparent) or not isinstance(rnode, (MappingNode, SequenceNode)):
        return "its section has a different type in the release file"
    if rnode.flow_style or not rnode.value:
        return "its section is written inline or empty in the release file"
    if bparent.flow_style:
        return "its section is written inline in the site file"

    unode, ukey = base.nodes[unit]
    head = ukey or unode
    blines = base.text.splitlines()
    first, last = head.start_mark.line, _end_line(unode)
    prefix = blines[first][:head.start_mark.column]
    if isinstance(rnode, MappingNode):
        if prefix.strip():
            return "it shares a line with another entry in the site file"
        base_col = head.start_mark.column
        rel_col = rnode.value[0][0].start_mark.column
    else:
        first_item = rnode.value[0]
        rel_prefix = rel_lines[first_item.start_mark.line][:first_item.start_mark.column]
        if prefix.strip() != "-" or rel_prefix.strip() != "-":
            return "its list entry shares a line in the site or release file"
        base_col = _indent(blines[first])
        rel_col = _indent(rel_lines[first_item.start_mark.line])
    new_lines = [_reindent(line, rel_col - base_col) for line in blines[first:last + 1]]
    return min(_end_line(rnode), len(rel_lines) - 1), new_lines


def _value_of(doc_text: str, path: str) -> Optional[str]:
    try:
        params = parse_yaml_nodes(doc_text)[0]
    except NotPlainYaml:
        return None
    return params[path][0] if path in params else None


@register(".yaml", ".yml")
class YAMLProcessor(BaseProcessor):

    def process(
        self,
        base_files: List[str],
        rel_file: str,
        out_file: str,
        config: MergeConfig,
        logger: logging.Logger,
    ) -> List[ReportEntry]:
        logger.info(f"[YAML] {rel_file}")
        rel_text = open_text(rel_file)
        base_texts = [open_text(bf) for bf in base_files]
        try:
            rel = _Doc(rel_text)
            bases = [_Doc(t) for t in base_texts]
        except NotPlainYaml as exc:
            return self._release_copied(rel_text, base_texts, rel_file, out_file, config, logger, str(exc))

        report: List[ReportEntry] = []

        def not_merged(element: str, reason: str) -> None:
            report.append(ReportEntry(type=EntryType.YAML_NOT_MERGED, file=rel_file, element=element,
                                      old=reason, new="release kept", section=_section(element)))
            log_structured(logger, "WARNING", "YAML", "NOT_MERGED", rel_file, element,
                           f"{reason} — release kept, review required")

        # Many-to-One: the first base (mapping-file order) wins; later bases only add
        combined: Dict[str, Tuple[str, int]] = {}
        for bi, doc in enumerate(bases):
            for path, (value, _) in doc.params.items():
                combined.setdefault(path, (value, bi))

        # ── 1. Base-only map keys / list entries: copy them into the release layout ──
        units: Dict[str, int] = {}
        for path, (value, bi) in combined.items():
            if path in rel.params:
                continue
            chain = [a for a in path_ancestors(path) if a in bases[bi].nodes]
            unit = next((a for a in chain if a not in rel.nodes), None)
            if unit is None:
                not_merged(path, f"site value {value!r} but the release file has a section here")
                continue
            units.setdefault(unit, bi)

        rel_lines = rel_text.split("\n")
        # after-line -> [(depth, lines)]; at one position the deeper section's lines go first
        insertions: Dict[int, List[Tuple[int, List[str]]]] = {}
        added: List[ReportEntry] = []
        for unit, bi in units.items():
            base = bases[bi]
            unode, _ = base.nodes[unit]
            shown = base.params[unit][0] if unit in base.params else "(section)"
            if config.exclude_base_only:
                report.append(ReportEntry(type=EntryType.EXCLUDED_BASE_ONLY_PARAMETER, file=rel_file,
                                          element=unit, old="", new=shown, section=_section(unit)))
                continue
            placed = _unit_lines(unit, base, rel, rel_lines)
            if isinstance(placed, str):
                not_merged(unit, f"site-only entry not added: {placed}")
                continue
            after, lines = placed
            insertions.setdefault(after, []).append((len(path_ancestors(unit)), lines))
            added.append(ReportEntry(type=EntryType.BASE_ONLY_PARAMETER_ADDED, file=rel_file,
                                     element=unit, old="", new=shown, section=_section(unit)))
        for after in sorted(insertions, reverse=True):
            block = [line for _, lines in sorted(insertions[after], key=lambda d: -d[0]) for line in lines]
            rel_lines[after + 1:after + 1] = block
        merged = "\n".join(rel_lines)

        # ── 2. Differing values: base wins, rewritten where the release value stands ──
        try:
            merged_nodes = parse_yaml_nodes(merged)[2]
        except NotPlainYaml as exc:        # an insertion broke the layout: keep the release file
            for entry in added:
                not_merged(entry.element, f"site-only entry not added: merged file would not parse ({exc})")
            added = []
            merged, merged_nodes = rel_text, rel.nodes
        report.extend(added)
        edits = []
        for path, (bval, bi) in combined.items():
            if path not in rel.params or rel.params[path][0] == bval:
                continue
            rval = rel.params[path][0]
            rnode = merged_nodes.get(path, (None, None))[0]
            bnode = bases[bi].nodes[path][0]
            if not isinstance(rnode, ScalarNode) or not isinstance(bnode, ScalarNode):
                not_merged(path, "value is a section in one file and a single value in the other")
                continue
            if detect_api_version_upgrade(bval, rval):
                report.append(ReportEntry(type=EntryType.API_VERSION_UPGRADED, file=rel_file, element=path,
                                          old=bval, new=rval, section=_section(path)))
                continue
            if is_java_fqcn(bval) and is_java_fqcn(rval):
                report.append(ReportEntry(type=EntryType.JAVA_CLASS_NAME_FROM_RELEASE, file=rel_file,
                                          element=path, old=bval, new=rval, section=_section(path)))
                continue
            src = bases[bi].text[bnode.start_mark.index:bnode.end_mark.index]
            edits.append((rnode.start_mark.index, rnode.end_mark.index, src, path, rval, bval))

        for start, end, src, path, rval, bval in sorted(edits, reverse=True):
            candidate = merged[:start] + src + merged[end:]
            if _value_of(candidate, path) != bval:
                not_merged(path, f"site value {bval!r} could not be written in the release layout")
                continue
            merged = candidate
            empty = bval in ("", "null", "~") and rval not in ("", "null", "~")
            report.append(ReportEntry(
                type=EntryType.REVIEW_EMPTY_IN_BASE if empty else EntryType.BASE_TO_RELEASE_REPLACED,
                file=rel_file, element=path, old=rval, new=bval, section=_section(path)))

        # ── 3. Release-only parameters are kept (reported once per new section / entry) ──
        base_nodes = set().union(*(doc.nodes for doc in bases))
        seen = set()
        for path in rel.params:
            if path in combined:
                continue
            chain = [a for a in path_ancestors(path) if a in rel.nodes]
            unit = next((a for a in chain if a not in base_nodes), None)
            if unit and unit not in seen:
                seen.add(unit)
                shown = rel.params[unit][0] if unit in rel.params else "(section)"
                report.append(ReportEntry(type=EntryType.RELEASE_ONLY_PARAMETER_ADDED, file=rel_file,
                                          element=unit, old=shown, new=shown, section=_section(unit)))

        # ── 4. The output must still be valid YAML ──
        try:
            parse_yaml_nodes(merged)
        except NotPlainYaml as exc:
            not_merged("", f"merged file is not valid YAML ({exc}); release copied")
            merged = rel_text

        if not config.dry_run:
            ensure_dir(out_file)
            with open(out_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(merged)
        return report

    @staticmethod
    def _release_copied(rel_text: str, base_texts: List[str], rel_file: str, out_file: str,
                        config: MergeConfig, logger: logging.Logger, reason: str) -> List[ReportEntry]:
        """Template code or invalid YAML: deploy the release file; report when the site differs."""
        report: List[ReportEntry] = []
        if any(_squeeze(t) != _squeeze(rel_text) for t in base_texts):
            report.append(ReportEntry(type=EntryType.YAML_RELEASE_COPIED, file=rel_file, element="",
                                      old=reason, new="release copied — site copy differs, review"))
            log_structured(logger, "WARNING", "YAML", "RELEASE_COPIED", rel_file, "",
                           f"not plain YAML ({reason}) and the site copy differs — release copied")
        if not config.dry_run:
            ensure_dir(out_file)
            with open(out_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(rel_text)
        return report
