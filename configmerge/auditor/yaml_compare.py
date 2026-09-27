"""
configmerge.auditor.yaml_compare
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Flatten a plain YAML document (e.g. a Helm values.yaml) into parameter paths so audit can
compare nodes by structure instead of by line order (rules: MEMORY.md, 2026-09-27).

Path forms:
  appcfg.main_cfg                                   map key
  appcfg.props[opt=kpi.stats.rotate.interval].val   list entry named by its first field
  appcfg.gmscspclist[=100]                          plain list value (compared as a set)
  instprop[#2].inst                                 instance block, paired by position

Every path carries the 1-based source lines of its key and value, for highlighting.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

# First field of a list entry that identifies an instance (inst, instance, instance_id, inst.num …)
_INSTANCE_KEY_RE = re.compile(r"^inst(?:ance)?(?:[._\-]?(?:id|num|number))?$", re.IGNORECASE)

# path -> (value, [lines])
Params = Dict[str, Tuple[str, List[int]]]
# path of every map / list / named list entry -> its lines
Spans = Dict[str, List[int]]
# (line, comment text) for every comment in the file
Comments = List[Tuple[int, str]]


class NotPlainYaml(Exception):
    """The text is not plain YAML (template code or a parse error)."""


def _lines(first: Node, last: Node) -> List[int]:
    """1-based lines from the start of *first* to the end of *last*."""
    start = first.start_mark.line
    end = last.end_mark.line
    # A block value ends at column 0 of the following line
    if last.end_mark.column == 0 and end > start:
        end -= 1
    return list(range(start + 1, end + 2))


def _scalar(node: Optional[Node]) -> Optional[str]:
    return node.value if isinstance(node, ScalarNode) else None


def _join(prefix: str, key: Node) -> str:
    name = _scalar(key)
    if name is None:                    # complex key: rare; name it by its position
        name = f"?L{key.start_mark.line + 1}"
    return f"{prefix}.{name}" if prefix else name


def _walk(node: Node, path: str, params: Params, spans: Spans, key: Optional[Node] = None) -> None:
    head = key or node
    if isinstance(node, ScalarNode):
        params[path] = (node.value, _lines(head, node))
        return
    if path:
        spans[path] = _lines(head, node)
    if isinstance(node, MappingNode):
        if not node.value and path:
            params[path] = ("{}", _lines(head, node))
        for k, v in node.value:
            _walk(v, _join(path, k), params, spans, k)
        return
    if not node.value and path:
        params[path] = ("[]", _lines(head, node))
    seen: Counter = Counter()
    instances = 0
    for item in node.value:
        first_key, first_val = item.value[0] if isinstance(item, MappingNode) and item.value else (None, None)
        fk, fv = _scalar(first_key), _scalar(first_val)

        if fk is not None and fv is not None and _INSTANCE_KEY_RE.match(fk):
            # Instance block: paired by position; the id is an ordinary field below it
            instances += 1
            _walk(item, f"{path}[#{instances}]", params, spans)
            continue
        if fk is not None:
            ident = f"{fk}={fv}" if fv is not None else fk
        elif isinstance(item, ScalarNode):
            ident = f"={item.value}"
        else:
            ident = "[]" if isinstance(item, SequenceNode) else "{}"
        seen[ident] += 1
        sub = f"{path}[{ident}]" if seen[ident] == 1 else f"{path}[{ident}#{seen[ident]}]"

        if isinstance(item, ScalarNode):
            params[sub] = ("(present)", _lines(item, item))
        elif fk is not None and fv is not None:
            # Named by its first field: the other fields sit below the name
            spans[sub] = _lines(item, item)
            rest = item.value[1:]
            if not rest:
                params[sub] = ("(present)", _lines(item, item))
            for k, v in rest:
                _walk(v, _join(sub, k), params, spans, k)
        else:
            _walk(item, sub, params, spans)


def parse_yaml(text: str) -> Tuple[Params, Spans]:
    """Parameters and container spans of a plain YAML text.
    Raises NotPlainYaml for template code or text YAML cannot parse."""
    if "{{" in text:
        raise NotPlainYaml("template code ({{ }})")
    try:
        docs = [d for d in yaml.compose_all(text, Loader=yaml.SafeLoader) if d is not None]
    except yaml.YAMLError as exc:
        raise NotPlainYaml(str(exc).splitlines()[0]) from exc
    params: Params = {}
    spans: Spans = {}
    for di, doc in enumerate(docs):
        _walk(doc, "" if len(docs) == 1 else f"doc{di + 1}", params, spans)
    return params, spans


def yaml_comments(text: str) -> Comments:
    """Full-line and inline comments; a '#' inside quotes or inside a word is not a comment."""
    out: Comments = []
    for i, line in enumerate(text.splitlines(), 1):
        quote = None
        for j, ch in enumerate(line):
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch
            elif ch == "#" and (j == 0 or line[j - 1] in " \t"):
                out.append((i, line[j:].strip()))
                break
    return out


def flatten_yaml(text: str) -> Tuple[Params, Comments]:
    """Parameters and comments of a plain YAML text (raises NotPlainYaml)."""
    return parse_yaml(text)[0], yaml_comments(text)
