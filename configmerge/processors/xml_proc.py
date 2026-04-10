"""
configmerge.processors.xml_proc
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
XML processor (.xml, .xsd)

Key behaviours:
  - Element-level replacement: base values replace matching release elements
  - Namespace header taken from RELEASE (adapt release namespace into output)
  - XML comments preceding elements: release comments preferred over base
  - Base-only elements inserted (unless --exclude-base-only)
  - Release-only elements preserved
  - Duplicate element detection
  - No per-element file re-read (base_text kept in memory)
"""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set, Tuple

from . import register, BaseProcessor
from ..models import MergeConfig, ReportEntry, EntryType
from ..logger import log_structured
from ..utils import ensure_dir, get_tag, open_text, detect_api_version_upgrade, is_java_fqcn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_xml_safe(
    file_path: str, logger: logging.Logger, label: str
) -> Tuple[Optional[ET.Element], Optional[str]]:
    try:
        content = open_text(file_path).strip()  # BUG-B: encoding-aware read
        if "<?xml" in content:
            content = content[content.index("<?xml"):]
        root = ET.fromstring(content)
        return root, content
    except ET.ParseError as e:
        log_structured(logger, "ERROR", "XML", "INVALID_XML", label, "", str(e))
        return None, None
    except Exception as e:
        log_structured(logger, "ERROR", "XML", "READ_ERROR", label, "", str(e))
        return None, None


def _is_xml_effectively_empty(elem: ET.Element) -> bool:
    return len(list(elem)) == 0 and not (elem.text or "").strip()


def _elem_signature(elem: ET.Element) -> str:
    """Stable identity string for deduplication — uses MD5 of full serialisation."""
    tag  = get_tag(elem)
    name = elem.attrib.get("name", "")
    raw  = ET.tostring(elem, encoding="unicode")
    sig  = f"{tag}:{name}:{hashlib.md5(raw.encode()).hexdigest()}"
    return sig


# ---------------------------------------------------------------------------
# Namespace handling helpers
# ---------------------------------------------------------------------------

def _extract_root_open_tag(text: str) -> str:
    """Return the opening tag of the root element (first non-PI tag)."""
    m = re.search(r'<(?!\?)[^>]+>', text, re.DOTALL)
    return m.group(0) if m else ""


def _adapt_namespace(base_text: str, rel_text: str, logger: logging.Logger) -> str:
    """
    Replace the root element's opening tag in base_text with the one from
    rel_text (which carries the release namespace).
    """
    rel_open  = _extract_root_open_tag(rel_text)
    base_open = _extract_root_open_tag(base_text)
    if rel_open and base_open and rel_open != base_open:
        return base_text.replace(base_open, rel_open, 1)
    return base_text


def _normalize_namespaces(merged_text: str, original_rel_open: str) -> str:
    """
    Remove any namespace declarations — and their prefix usages — that were
    NOT present in the original release file's root element opening tag.

    This prevents ElementTree-style ``ns0:``, ``ns1:``, ``ns2:`` prefixes
    (introduced when base-file blocks carry different namespace declarations)
    from leaking into the merged output.  The release file's own namespace
    setup is always preserved verbatim.
    """
    if not original_rel_open:
        return merged_text

    # Namespace declarations present in the original release root tag
    orig_decls: Set[str] = set(
        re.findall(r'xmlns(?::[\w-]+)?="[^"]*"', original_rel_open)
    )

    # Find the current root open tag in the merged output
    current_open = _extract_root_open_tag(merged_text)
    if not current_open:
        return merged_text

    # Declarations that appeared after merging but were not in original release
    current_decls: Set[str] = set(
        re.findall(r'xmlns(?::[\w-]+)?="[^"]*"', current_open)
    )
    added_decls = current_decls - orig_decls
    if not added_decls:
        return merged_text

    # Build a cleaned root tag by removing the extra declarations
    cleaned_open = current_open
    for decl in added_decls:
        cleaned_open = re.sub(r'\s+' + re.escape(decl), '', cleaned_open)

    # Collect the added prefix names (e.g. "ns0", "ns", "ns1")
    added_prefixes: List[str] = []
    for decl in added_decls:
        m = re.match(r'xmlns:([\w-]+)=', decl)
        if m:
            added_prefixes.append(m.group(1))

    # Apply cleaned root tag
    merged_text = merged_text.replace(current_open, cleaned_open, 1)

    # Strip added prefixes from all tag and attribute names in the document
    for prefix in added_prefixes:
        ep = re.escape(prefix)
        # Opening tags:   <ns0:tag  →  <tag
        merged_text = re.sub(rf'<{ep}:([\w-]+)', r'<\1', merged_text)
        # Closing tags:   </ns0:tag  →  </tag
        merged_text = re.sub(rf'</{ep}:([\w-]+)', r'</\1', merged_text)
        # Attribute names: ns0:attr=  →  attr=  (won't touch values)
        merged_text = re.sub(rf'\b{ep}:([\w-]+)(?==)', r'\1', merged_text)

    return merged_text


# ---------------------------------------------------------------------------
# XML comment extraction (preceding a block in raw text)
# ---------------------------------------------------------------------------

def _comments_before(text: str, pos: int) -> List[str]:
    """Extract XML comments that immediately precede *pos* in *text*."""
    before = text[:pos].rstrip()
    comments = []
    for m in re.finditer(r'<!--.*?-->', before, re.DOTALL):
        comments.append(m.group(0))
    return comments


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def _detect_xml_duplicates(
    root: ET.Element, rel_file: str, logger: logging.Logger
) -> List[ReportEntry]:
    seen: Dict[str, List[str]] = {}
    report: List[ReportEntry] = []

    def traverse(parent: ET.Element, parent_path: str) -> None:
        tag_count: Dict[str, int] = {}
        tag_index: Dict[str, int] = {}
        for child in parent:
            t = get_tag(child)
            tag_count[t] = tag_count.get(t, 0) + 1

        for child in parent:
            t    = get_tag(child)
            name = child.attrib.get("name", "")
            tag_index[t] = tag_index.get(t, 0) + 1
            if tag_count[t] > 1:
                path = f"{parent_path}/{t}[{tag_index[t]}]"
            elif name:
                path = f"{parent_path}/{t}[@name={name}]"
            else:
                path = f"{parent_path}/{t}"

            sig     = path + "|" + "|".join(f"{k}={v}" for k, v in sorted(child.attrib.items()))
            content = ET.tostring(child, encoding="unicode").strip()

            if sig not in seen:
                seen[sig] = []
            seen[sig].append(content)
            traverse(child, path)

    traverse(root, f"/{get_tag(root)}")

    for sig, values in seen.items():
        if len(values) > 1 and len(set(values)) > 1:
            report.append(ReportEntry(
                type=EntryType.DUPLICATE_KEY,
                file=rel_file,
                element=sig,
                old=" | ".join(values[:-1]),
                new=values[-1],
            ))
            log_structured(logger, "WARNING", "XML", "DUPLICATE_KEY",
                           rel_file, sig, f"duplicates={len(values)-1}")
    return report


# ---------------------------------------------------------------------------
# Find / replace blocks (text-level, keeps formatting)
# ---------------------------------------------------------------------------

def _find_matching_block(
    text: str, tag: str, name: Optional[str]
) -> Optional[re.Match]:
    if name:
        # Full block with name attribute
        pattern = re.compile(
            rf'<(?:[\w-]+:)?{re.escape(tag)}\b[^>]*\bname="{re.escape(name)}"[^>]*>.*?</(?:[\w-]+:)?{re.escape(tag)}>',
            re.DOTALL
        )
        matches = list(pattern.finditer(text))
        if matches:
            return max(matches, key=lambda m: len(m.group(0)))
        # Self-closing fallback
        pattern_sc = re.compile(
            rf'<(?:[\w-]+:)?{re.escape(tag)}\b[^>]*\bname="{re.escape(name)}"[^>]*/>', re.DOTALL
        )
        return pattern_sc.search(text)
    else:
        pattern = re.compile(
            rf'<(?:[\w-]+:)?{re.escape(tag)}\b[^>]*>.*?</(?:[\w-]+:)?{re.escape(tag)}>',
            re.DOTALL
        )
        return pattern.search(text)


def _replace_elements(
    base_root: ET.Element,
    base_text: str,
    rel_text: str,
    rel_file: str,
    logger: logging.Logger,
) -> Tuple[str, List[ReportEntry]]:
    """Replace release element blocks with base element blocks."""
    report: List[ReportEntry] = []
    processed = set()

    for b_elem in base_root.iter():
        if b_elem is base_root:
            continue

        tag  = get_tag(b_elem)
        name = b_elem.attrib.get("name")
        sig  = f"{tag}:{name}:{hashlib.md5(ET.tostring(b_elem, encoding='unicode').encode()).hexdigest()}"

        if sig in processed:
            continue
        processed.add(sig)

        # locate block in base_text
        base_match = _find_matching_block(base_text, tag, name)
        if not base_match:
            continue
        base_block = base_match.group(0)

        # locate corresponding block in rel_text
        rel_match = _find_matching_block(rel_text, tag, name)
        if not rel_match:
            continue
        old_block = rel_match.group(0)
        element_id = f"{tag}:{name}"

        if old_block.strip() == base_block.strip():
            continue   # no change

        base_empty    = _is_xml_effectively_empty(b_elem)
        release_empty: Optional[bool] = None

        try:
            parsed = ET.fromstring(f"<root>{old_block}</root>")
            if len(parsed):
                release_empty = _is_xml_effectively_empty(parsed[0])
        except ET.ParseError:
            pass

        if base_empty and release_empty is True:
            continue   # both empty

        if base_empty and release_empty is False:
            start, end = rel_match.span()
            rel_text = rel_text[:start] + base_block + rel_text[end:]
            report.append(ReportEntry(
                type=EntryType.EMPTY_BASE_OVERRIDE_XML,
                file=rel_file,
                element=element_id,
                old=" ".join(old_block.strip().split()),
                new="",
                recommended=old_block,
            ))
            continue

        # Normal replace — check for API version upgrade or Java FQCN
        old_compact = " ".join(old_block.strip().split())
        new_compact  = " ".join(base_block.strip().split())
        if detect_api_version_upgrade(new_compact, old_compact):
            # Release has a newer version: keep release value (old_block) in output
            start, end = rel_match.span()
            # Leave rel_text unchanged (keep release block)
            report.append(ReportEntry(
                type=EntryType.API_VERSION_UPGRADED,
                file=rel_file,
                element=element_id,
                old=new_compact,   # old = base value
                new=old_compact,   # new = release (newer) value used
            ))
        elif is_java_fqcn(new_compact) and is_java_fqcn(old_compact):
            # Both base and release values are Java FQCNs — class names are
            # deployment-specific; keep the release value and flag for review.
            start, end = rel_match.span()
            # Leave rel_text unchanged (keep release block)
            report.append(ReportEntry(
                type=EntryType.JAVA_CLASS_NAME_FROM_RELEASE,
                file=rel_file,
                element=element_id,
                old=new_compact,   # old = base value
                new=old_compact,   # new = release value used
            ))
        else:
            start, end = rel_match.span()
            rel_text = rel_text[:start] + base_block + rel_text[end:]
            report.append(ReportEntry(
                type=EntryType.XML_BASE_TO_RELEASE_REPLACED,
                file=rel_file,
                element=element_id,
                old=old_compact,
                new=new_compact,
            ))

    return rel_text, report


def _include_base_only(
    base_root: ET.Element,
    base_text: str,
    rel_text: str,
    rel_file: str,
    logger: logging.Logger,
) -> Tuple[str, List[ReportEntry]]:
    """Insert elements present in base but missing from release."""
    report: List[ReportEntry] = []
    base_children = list(base_root)

    for i, child in enumerate(base_children):
        tag = get_tag(child)
        # Fixed: use word-boundary regex to avoid false substring matches
        if re.search(rf'<(?:[\w-]+:)?{re.escape(tag)}[\s/>]', rel_text):
            continue

        base_match = _find_matching_block(base_text, tag, None)
        if not base_match:
            continue
        block = base_match.group(0)

        # Find insert position: before the next sibling that exists in rel_text
        insert_pos = len(rel_text)
        for j in range(i + 1, len(base_children)):
            next_tag = get_tag(base_children[j])
            m = re.search(rf'<(?:[\w-]+:)?{re.escape(next_tag)}[\s/>]', rel_text)
            if m:
                insert_pos = m.start()
                break

        rel_text = rel_text[:insert_pos] + "\n" + block + "\n" + rel_text[insert_pos:]
        report.append(ReportEntry(
            type=EntryType.BASE_ONLY_PARAMETER_ADDED,
            file=rel_file,
            element=tag,
            old="",
            new=" ".join(block.strip().split()),
        ))

    return rel_text, report


def _detect_release_only(
    base_root: ET.Element,
    rel_root: ET.Element,
    rel_file: str,
    logger: logging.Logger,
) -> List[ReportEntry]:
    """Report elements present only in release."""
    report: List[ReportEntry] = []
    base_elements = {(get_tag(e), e.attrib.get("name")) for e in base_root.iter()}

    for elem in rel_root.iter():
        tag  = get_tag(elem)
        name = elem.attrib.get("name")
        if tag == get_tag(rel_root):
            continue
        if not name:
            continue
        if _is_xml_effectively_empty(elem):
            continue
        if (tag, name) not in base_elements:
            element_text = ET.tostring(elem, encoding="unicode").strip()
            report.append(ReportEntry(
                type=EntryType.RELEASE_ONLY_PARAMETER_ADDED,
                file=rel_file,
                element=f"{tag}:{name}",
                old="",
                new=" ".join(element_text.split()),
            ))
    return report


# ---------------------------------------------------------------------------
# Processor class
# ---------------------------------------------------------------------------

@register(".xml", ".xsd")
class XMLProcessor(BaseProcessor):

    def process(
        self,
        base_files: List[str],
        rel_file: str,
        out_file: str,
        config: MergeConfig,
        logger: logging.Logger,
    ) -> List[ReportEntry]:
        logger.info(f"[XML] {rel_file}")
        report: List[ReportEntry] = []

        # MOD-2: warn if multiple base files supplied (not yet supported for XML)
        if len(base_files) > 1:
            logger.warning(
                f"[XML] {rel_file}: multi-base merge not fully supported for XML — "
                f"using base_files[0] only; {len(base_files) - 1} additional base(s) ignored"
            )
        base_file = base_files[0]
        base_root, base_text = _parse_xml_safe(base_file, logger, rel_file)
        rel_root,  rel_text  = _parse_xml_safe(rel_file,  logger, rel_file)

        if base_root is None or rel_root is None:
            return report

        # Capture release root open tag BEFORE any modifications (namespace race-condition fix)
        original_rel_open = _extract_root_open_tag(rel_text)

        # Duplicate detection
        report.extend(_detect_xml_duplicates(base_root, rel_file, logger))

        # Step 1: Replace matching elements (base values → release file)
        rel_text, rpt = _replace_elements(base_root, base_text, rel_text, rel_file, logger)
        report.extend(rpt)

        # Step 2: Ensure the root element's opening tag still matches the original
        #         release namespace (Step 1 may have swapped it via block replacement).
        if original_rel_open:
            current_open = _extract_root_open_tag(rel_text)
            if current_open and current_open != original_rel_open:
                rel_text = rel_text.replace(current_open, original_rel_open, 1)
                report.append(ReportEntry(
                    type=EntryType.NAMESPACE_ADAPTED,
                    file=rel_file,
                    element="root",
                    old=current_open,
                    new=original_rel_open,
                ))

        # Step 3: Include base-only elements
        if not config.exclude_base_only:
            rel_text, rpt = _include_base_only(
                base_root, base_text, rel_text, rel_file, logger
            )
            report.extend(rpt)
        else:
            # Still detect and report them as excluded
            _, excluded_rpt = _include_base_only(
                base_root, base_text, rel_text, rel_file, logger
            )
            for r in excluded_rpt:
                r.type = EntryType.EXCLUDED_BASE_ONLY_PARAMETER
            report.extend(excluded_rpt)

        # Step 4: Detect release-only elements
        report.extend(_detect_release_only(base_root, rel_root, rel_file, logger))

        # Step 5: Strip any ns0:/ns1:/ns: prefixes that were not in the original
        #         release root tag (prevents ElementTree namespace pollution).
        rel_text = _normalize_namespaces(rel_text, original_rel_open)

        if not config.dry_run:
            ensure_dir(out_file)
            with open(out_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(rel_text)

        return report
