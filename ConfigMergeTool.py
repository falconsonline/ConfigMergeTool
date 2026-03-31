#!/usr/bin/env python3

import os
import re
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side, Alignment
import shutil
from collections import defaultdict
from difflib import SequenceMatcher

# ---------------- LOGGING ----------------
def important(msg, logger):
    print(msg)
    logger.info(msg)
    
def setup_logging(verbose=False):

    logger = logging.getLogger("config-merge")
    logger.setLevel(logging.DEBUG)   # capture everything

    # prevent duplicate handlers
    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # =========================================================
    # ✅ FILE HANDLER (FULL LOGGING)
    # =========================================================
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(
        log_dir,
        f"log_merge_config.{datetime.now().strftime('%Y%m%d.%H%M%S')}.log"
    )

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)   # everything goes to file
    file_handler.setFormatter(formatter)

    # =========================================================
    # ✅ CONSOLE HANDLER (MINIMAL ONLY)
    # =========================================================
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)   # ONLY errors

    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)

    # =========================================================
    # ✅ ADD HANDLERS
    # =========================================================
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # print only essential info manually
    important(f"[LOG FILE] {log_file}", logger)

    return logger
# ---------------- HELPERS ----------------
def ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)

def copy_file(src, dst, logger=None):
    if logger:
        logger.info(f"[COPY] {src}")
    ensure_dir(dst)
    with open(src, "rb") as s, open(dst, "wb") as d:
        d.write(s.read())

def get_tag(elem):
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

def clean_output_dir(path, logger=None):

    if os.path.exists(path):
        msg = f"[CLEANUP] Removing existing output dir: {path}"

        # log to file
        if logger:
            logger.info(msg)

        # prin  t to console (IMPORTANT EVENT)
        print(msg)

        shutil.rmtree(path)

    else:
        msg = f"[CLEANUP] Output dir does not exist, creating: {path}"

        if logger:
            logger.info(msg)

        print(msg)

    os.makedirs(path, exist_ok=True)

    msg = f"[CLEANUP] Output directory ready: {path}"

    if logger:
        logger.info(msg)

    print(msg)

def log_structured(logger, level, ftype, action, file, element="", message="", severity="INFO"):
    """
    Structured log format:
    [TYPE][ACTION][SEVERITY][FILE][ELEMENT] message
    """
    log_msg = f"[{ftype}][{action}][{severity}][{file}][{element}] {message}"

    level_map = {
        "ERROR": "error",
        "WARN": "warning",
        "WARNING": "warning",
        "INFO": "info",
        "DEBUG": "debug"
    }

    log_level = level_map.get(severity.upper(), level)

    getattr(logger, log_level)(log_msg)

def highlight_diff(old, new):

    old = str(old or "")
    new = str(new or "")

    # simple case → identical
    if old == new:
        return new

    # find first diff position
    i = 0
    while i < min(len(old), len(new)) and old[i] == new[i]:
        i += 1

    # find last diff position
    j_old = len(old) - 1
    j_new = len(new) - 1

    while j_old >= i and j_new >= i and old[j_old] == new[j_new]:
        j_old -= 1
        j_new -= 1

    # extract parts
    prefix = new[:i]
    changed_new = new[i:j_new+1]
    suffix = new[j_new+1:]

    # mark only changed part
    return f"{prefix}<<{changed_new}>>{suffix}"

def detect_json_duplicates(base_file, rel_file, report, logger):

    try:
        with open(base_file, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            return

        # =========================================================
        # ✅ CUSTOM PARSER TO TRACK DUPLICATES PER OBJECT
        # =========================================================
        duplicates = []

        def object_pairs_hook(pairs):
            seen = {}
            local_dups = {}

            for k, v in pairs:
                if k in seen:
                    local_dups[k] = local_dups.get(k, 1) + 1
                else:
                    seen[k] = v

            for key, count in local_dups.items():
                duplicates.append((key, count))

            return dict(pairs)

        json.loads(content, object_pairs_hook=object_pairs_hook)

        # =========================================================
        # ✅ REPORT TRUE DUPLICATES ONLY
        # =========================================================
        for key, count in duplicates:

            log_structured(
                logger,
                "warning",
                "JSON",
                "DUPLICATE_KEY",
                rel_file,
                key,
                f"duplicates={count} detected (last wins)"
            )

            report.append({
                "type": "DUPLICATE_KEY",
                "file": rel_file,
                "element": key,
                "old": f"{count} duplicates",
                "new": "LAST_VALUE_USED"
            })

    except Exception as e:
        log_structured(
            logger,
            "debug",
            "JSON",
            "DUP_SCAN_FAIL",
            rel_file,
            "",
            str(e)
        )

def is_xml_effectively_empty(elem):
    """
    XML element is empty ONLY if:
    - no children
    - AND no meaningful text
    """

    # check children
    if len(list(elem)) > 0:
        return False

    # check text
    if (elem.text or "").strip():
        return False

    return True

def find_release_only(b, r, path=""):
    for k in r:
        current_path = f"{path}.{k}" if path else k

        if k not in b:
            log_structured(logger, "info", "JSON", "RELEASE_ONLY_PARAMETER_ADDED",
                           rel_file, current_path,
                           "parameter present only in release → retained")

            report.append({
                "type": "RELEASE_ONLY_PARAMETER_ADDED",
                "file": rel_file,
                "element": current_path,
                "old": json.dumps(r[k]),
                "new": json.dumps(r[k])
            })

        elif isinstance(r[k], dict) and isinstance(b.get(k), dict):
            find_release_only(b[k], r[k], current_path)



# ----------------- LOAD BASE CONFIG --------------------------------

def load_copy_only(copy_file, base_dir):
    files = set()

    if not copy_file:
        return files

    base_dir = os.path.normpath(base_dir)
    base_dir_name = os.path.basename(base_dir)

    with open(copy_file) as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            path = os.path.normpath(line)

            # ✅ Case 1: Absolute path → convert to relative
            if os.path.isabs(path):
                rel_path = os.path.relpath(path, base_dir)

            else:
                path_norm = os.path.normpath(path)

                # ✅ Case 2: starts with base_dir_name
                if path_norm.startswith(base_dir_name + os.sep):
                    rel_path = os.path.relpath(path_norm, base_dir_name)

                # ✅ Case 3: already relative
                else:
                    rel_path = path_norm

            files.add(os.path.normpath(rel_path))

    return files

    
# ---------------- SITE - RELEASE CONFIG MAPPING  ----------------

def load_mapping(mapping_file):
    mapping = {}

    if not mapping_file:
        return mapping

    with open(mapping_file) as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            base, rel = line.split("=", 1)

            mapping[base.strip()] = rel.strip()

    return mapping
    
    
    
#-----------------
def extract_changed_part(old, new):

    old = str(old or "")
    new = str(new or "")

    if old == new:
        return ""

    # =========================================================
    # ✅ TOKENIZE (handles XML / JSON / KV)
    # =========================================================
    def tokenize(s):
        return re.findall(r'\w+|[^\w\s]', s)

    old_tokens = tokenize(old)
    new_tokens = tokenize(new)

    matcher = SequenceMatcher(None, old_tokens, new_tokens)

    changed_parts = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():

        if tag in ("replace", "insert"):
            changed_parts.extend(new_tokens[j1:j2])

    # =========================================================
    # ✅ CLEAN OUTPUT
    # =========================================================
    if not changed_parts:
        return ""

    # join smartly
    result = " ".join(changed_parts)

    # remove spacing artifacts
    result = result.replace(" ,", ",").replace(" :", ":")
    result = result.replace(" =", "=").replace("( ", "(").replace(" )", ")")

    return result.strip()  

#-----------------

def extract_changed_xml_param(old, new):
    old = str(old or "")
    new = str(new or "")

    def tokenize(s):
        return re.findall(r'\w+|[^\w\s]', s)

    old_tokens = tokenize(old)
    new_tokens = tokenize(new)

    matcher = SequenceMatcher(None, old_tokens, new_tokens)

    old_diff = []
    new_diff = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            old_diff.extend(old_tokens[i1:i2])
        if tag in ("replace", "insert"):
            new_diff.extend(new_tokens[j1:j2])

    if not old_diff and not new_diff:
        return ""

    return f"{' '.join(old_diff)}  →  {' '.join(new_diff)}"
    
# ---------------- XML BLOCK FIND ----------------
def find_matching_block(text, tag, name=None):

    if name:
        # ✅ 1. STRICT full block match FIRST (preferred)
        pattern_full = re.compile(
            rf"<(?:\w+:)?{tag}\b[^>]*\bname=\"{re.escape(name)}\"[^>]*>.*?</{tag}>",
            re.DOTALL
        )

        matches = list(pattern_full.finditer(text))

        if matches:
            # ✅ If multiple, pick the LARGEST (outermost / real block)
            return max(matches, key=lambda m: len(m.group(0)))

        # ✅ 2. fallback to self-closing ONLY if full block not found
        pattern_self = re.compile(
            rf"<(?:\w+:)?{tag}\b[^>]*\bname=\"{re.escape(name)}\"[^>]*/>",
            re.DOTALL
        )

        return pattern_self.search(text)

    else:
        pattern = re.compile(
            rf"<(?:\w+:)?{tag}\b[^>]*>.*?</{tag}>",
            re.DOTALL
        )
        return pattern.search(text)

# ---------------- XML EXTRACT ----------------
def extract_block_text(file, tag, name=None):
    with open(file, "r", encoding="utf-8") as f:
        text = f.read()

    match = find_matching_block(text, tag, name)
    return match.group(0) if match else None

# ---------------- XML REPLACE CORE ----------------
def replace_element_blocks(base_file, rel_text, report, rel_file, logger):

    base_tree = ET.parse(base_file)
    base_root = base_tree.getroot()

    processed = set()

    for b_elem in base_root.iter():

        if b_elem is base_root:
            continue

        tag = get_tag(b_elem)
        name = b_elem.attrib.get("name")

        identifier = f"{tag}:{name}:{ET.tostring(b_elem, encoding='unicode')[:80]}"

        if identifier in processed:
            continue
        processed.add(identifier)

        base_block = extract_block_text(base_file, tag, name)
        if not base_block:
            continue

        match = find_matching_block(rel_text, tag, name)
        if not match:
            continue

        old_block = match.group(0)

        element_id = f"{tag}:{name}"

        # =========================================================
        # ✅ 1. NO CHANGE CHECK (MUST BE FIRST)
        # =========================================================
        if old_block.strip() == base_block.strip():

            log_structured(logger, "debug", "XML", "NO_CHANGE",
                           rel_file,
                           element_id,
                           "element identical")

            continue

        # =========================================================
        # ✅ 2. EMPTY BASE CHECK (STRICT + SAFE)
        # =========================================================

        base_empty = is_xml_effectively_empty(b_elem)

        release_elem = None
        release_empty = None

        try:
            wrapped = f"<root>{old_block}</root>"
            parsed = ET.fromstring(wrapped)

            if len(parsed):
                release_elem = parsed[0]
                release_empty = is_xml_effectively_empty(release_elem)

        except ET.ParseError:
            log_structured(logger, "debug", "XML", "PARSE_ERROR",
                           rel_file,
                           element_id,
                           "failed to parse release block → skipping EMPTY check",
                           severity="warning")

        # 🚨 ONLY trigger EMPTY when parsing succeeded
        if base_empty and release_empty is True:

            # both empty → treat as NO CHANGE
            log_structured(logger, "debug", "XML", "NO_CHANGE",
                           rel_file,
                           element_id,
                           "both base and release empty")

            continue

        if base_empty and release_empty is False:

            start, end = match.span()
            rel_text = rel_text[:start] + base_block + rel_text[end:]

            log_structured(logger, "debug", "XML", "EMPTY_BASE",
                           rel_file,
                           element_id,
                           "release value ignored → forced empty",
                           severity="ERROR")

            report.append({
                "type": "EMPTY_BASE_OVERRIDE_XML",
                "file": rel_file,
                "element": element_id,
                "old": " ".join(old_block.strip().split()),
                "new": "",
                "recommended": "FROM_RELEASE"
            })

            continue

        # =========================================================
        # ✅ 3. NORMAL REPLACE
        # =========================================================

        start, end = match.span()
        rel_text = rel_text[:start] + base_block + rel_text[end:]

        log_structured(logger, "debug", "XML", "REPLACE",
                       rel_file,
                       element_id,
                       "element replaced from base")

        report.append({
            "type": "XML_BASE_TO_RELEASE_REPLACED",
            "file": rel_file,
            "element": element_id,
            "old": " ".join(old_block.strip().split()),
            "new": " ".join(base_block.strip().split())
        })

    return rel_text

# ---------------- INCLUDE BASE ONLY ----------------
def include_base_only(base_file, rel_text, report, rel_file):

    import xml.etree.ElementTree as ET

    base_tree = ET.parse(base_file)
    base_root = base_tree.getroot()

    base_children = list(base_root)

    for i, child in enumerate(base_children):

        tag = child.tag.split("}")[-1]

        # skip if already present
        if re.search(rf"<[^>]*{tag}[^>]*>", rel_text):
            continue

        block = extract_block_text(base_file, tag)
        if not block:
            continue

        # find correct insert position (based on next sibling)
        insert_pos = len(rel_text)

        for j in range(i + 1, len(base_children)):
            next_tag = base_children[j].tag.split("}")[-1]

            match = re.search(rf"<[^>]*{next_tag}[^>]*>", rel_text)
            if match:
                insert_pos = match.start()
                break

        rel_text = rel_text[:insert_pos] + "\n" + block + "\n" + rel_text[insert_pos:]

        # compact block for readability
        block_compact = " ".join(block.strip().split())
        
        report.append({
            "type": "BASE_ONLY_PARAMETER_ADDED",
            "file": rel_file,
            "element": tag,
            "old": "",
            "new": block_compact
        })

    return rel_text


#-----------------PARSE XML -------------------
def parse_xml_safe(file_path, logger, rel_file):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        # ✅ Fix: remove garbage before XML declaration
        if "<?xml" in content:
            content = content[content.index("<?xml"):]

        root = ET.fromstring(content)
        return root, content

    except ET.ParseError as e:
        log_structured(
            logger,
            "error",
            "XML",
            "INVALID_XML",
            rel_file,
            "",
            f"Invalid XML: {str(e)}"
        )
        return None, None

    except Exception as e:
        log_structured(
            logger,
            "error",
            "XML",
            "READ_ERROR",
            rel_file,
            "",
            str(e)
        )
        return None, None

# ----------------DETECT XML DUPLICATES ----------------
def detect_xml_duplicates(base_root, rel_file, report, logger):

    seen = {}

    def get_tag_clean(elem):
        return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

    def build_path(elem, parent_path, sibling_count, sibling_index):
        tag = get_tag_clean(elem)

        # Prefer name attribute
        if "name" in elem.attrib:
            return f"{parent_path}/{tag}[@name={elem.attrib['name']}]"

        # If multiple siblings → use index
        if sibling_count > 1:
            return f"{parent_path}/{tag}[{sibling_index}]"

        return f"{parent_path}/{tag}"

    def traverse(parent, parent_path):

        children = list(parent)

        # Count siblings
        tag_count = {}
        for c in children:
            t = get_tag_clean(c)
            tag_count[t] = tag_count.get(t, 0) + 1

        tag_index = {}

        for child in children:
            tag = get_tag_clean(child)

            tag_index[tag] = tag_index.get(tag, 0) + 1

            path = build_path(
                child,
                parent_path,
                tag_count[tag],
                tag_index[tag]
            )

            signature = (
                path +
                "|" +
                "|".join(f"{k}={v}" for k, v in sorted(child.attrib.items()))
            )

            content = ET.tostring(child, encoding="unicode").strip()

            if signature not in seen:
                seen[signature] = []

            seen[signature].append(content)

            traverse(child, path)

    traverse(base_root, f"/{get_tag_clean(base_root)}")

    # -------- REPORT TRUE DUPLICATES ONLY --------
    for sig, values in seen.items():

        if len(values) > 1:

            unique_values = list(set(values))

            # ✅ Ignore identical duplicates
            if len(unique_values) == 1:
                continue

            skipped = values[:-1]
            final_val = values[-1]

            log_structured(
                logger,
                "warning",
                "XML",
                "DUPLICATE_KEY",
                rel_file,
                sig,
                f"duplicates={len(skipped)} detected → using last"
            )

            report.append({
                "type": "DUPLICATE_KEY",
                "file": rel_file,
                "element": sig,
                "old": " | ".join(v.strip() for v in skipped),
                "new": final_val
            })


#-----------------PARSE XML -------------------

def process_xml(base_file, rel_file, out_file, args, logger, report):

    logger.info(f"[XML] {rel_file}")

    # =========================================================
    # ✅ SAFE PARSE (VALIDATION)
    # =========================================================
    base_root, base_text = parse_xml_safe(base_file, logger, rel_file)
    rel_root, rel_text = parse_xml_safe(rel_file, logger, rel_file)

    if base_root is None or rel_root is None:
        return

    logger.debug("==== XML PRE-PROCESSING START ====")

    initial_report_len = len(report)

    # =========================================================
    # ✅ FIXED DUPLICATE DETECTION
    # =========================================================
    detect_xml_duplicates(base_root, rel_file, report, logger)

    # =========================================================
    # ✅ STEP 1: REPLACE
    # =========================================================
    rel_text = replace_element_blocks(
        base_file, rel_text, report, rel_file, logger
    )

    replaced_count = len(report) - initial_report_len

    # =========================================================
    # ✅ STEP 2: INCLUDE BASE ONLY
    # =========================================================
    before_include = len(report)

    if not args.exclude_params_in_baseonlyconfig:
        rel_text = include_base_only(
            base_file, rel_text, report, rel_file
        )

    include_count = len(report) - before_include

    for r in report[before_include:]:
        log_structured(
            logger,
            "debug",
            "XML",
            "ADD_BASE_ONLY",
            r["file"],
            r.get("element"),
            "added from base"
        )

    # =========================================================
    # ✅ STEP 3: RELEASE ONLY DETECTION (FIXED PARSE)
    # =========================================================
    try:
        base_elements = set()

        for elem in base_root.iter():
            tag = get_tag(elem)
            name = elem.attrib.get("name")
            base_elements.add((tag, name))

        for elem in rel_root.iter():

            tag = get_tag(elem)
            name = elem.attrib.get("name")

            if tag == get_tag(rel_root):
                continue

            if not name:
                continue

            if is_xml_effectively_empty(elem):
                continue

            if (tag, name) not in base_elements:

                element_id = f"{tag}:{name}"

                log_structured(
                    logger,
                    "info",
                    "XML",
                    "RELEASE_ONLY_PARAMETER_ADDED",
                    rel_file,
                    element_id,
                    "element present only in release → retained"
                )

                element_text = ET.tostring(elem, encoding="unicode").strip()

                report.append({
                    "type": "RELEASE_ONLY_PARAMETER_ADDED",
                    "file": rel_file,
                    "element": element_id,
                    "old": "",
                    "new": " ".join(element_text.split())
                })

    except Exception as e:
        log_structured(
            logger,
            "warning",
            "XML",
            "RELEASE_ONLY_SCAN_FAILED",
            rel_file,
            "",
            str(e)
        )

    # =========================================================
    # ✅ SUMMARY
    # =========================================================
    log_structured(
        logger,
        "debug",
        "XML",
        "SUMMARY",
        rel_file,
        "",
        f"replaced={replaced_count}, added={include_count}"
    )

    logger.debug("==== XML POST-PROCESSING END ====\n")

    # =========================================================
    # ✅ WRITE OUTPUT
    # =========================================================
    if not args.dry_run:
        ensure_dir(out_file)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(rel_text)


# ---------------- KV FILES ----------------
def parse_kv(file):

    data = {}
    lines = []
    blocks = {}
    duplicate_map = {}

    current_section = "DEFAULT"

    # buffer for comments belonging to NEXT key
    comment_buffer = []

    with open(file) as f:
        for line in f:

            lines.append(line)
            stripped = line.strip()

            # ---------------- SECTION ----------------
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped
                comment_buffer = []   # reset on section change
                continue

            # ---------------- COMMENT ----------------
            if stripped.startswith("#") or stripped.startswith("!"):
                comment_buffer.append(line)
                continue

            # ---------------- EMPTY LINE ----------------
            if not stripped:
                # preserve spacing but DO NOT attach to next key
                comment_buffer.append(line)
                continue

            # ---------------- REAL KEY-VALUE ONLY ----------------
            if "=" in line:
                k, v = line.split("=", 1)
            elif ":" in line:
                k, v = line.split(":", 1)
            else:
                # not a valid KV → reset buffer
                comment_buffer = []
                continue

            key = k.strip()
            value = v.strip()

            compound_key = f"{current_section}|{key}"

            # =====================================================
            # ✅ DUPLICATE TRACKING (ONLY REAL KEYS)
            # =====================================================
            if compound_key not in duplicate_map:
                duplicate_map[compound_key] = []

            duplicate_map[compound_key].append(value)

            # latest wins
            data[compound_key] = value

            # =====================================================
            # ✅ BLOCK CAPTURE (STRICT ASSOCIATION)
            # =====================================================
            block = []

            # attach ONLY immediate preceding comments
            if comment_buffer:
                block.extend(comment_buffer)

            block.append(line)
            blocks[compound_key] = block

            # reset after consuming
            comment_buffer = []

    return data, lines, duplicate_map, blocks    
    
#--------------- PROCESS KEY VALUE ------------
def process_kv(base_file, rel_file, out_file, report, logger, args):

    logger.info(f"[KV] Processing file: {rel_file}")

    # ---------------- PARSE ----------------
    base_data, _, base_dup, base_blocks = parse_kv(base_file)
    _, rel_lines, _, _ = parse_kv(rel_file)

    # =========================================================
    # DUPLICATE REPORTING (UNCHANGED)
    # =========================================================
    for compound_key, values in base_dup.items():

        if len(values) > 1:

            skipped = values[:-1]
            final_val = values[-1]

            log_structured(
                logger,
                "warning",
                "KV",
                "DUPLICATE_KEY",
                rel_file,
                compound_key,
                f"duplicates={len(skipped)} skipped={' | '.join(skipped)} → using={final_val}"
            )

            report.append({
                "type": "DUPLICATE_KEY",
                "file": rel_file,
                "element": compound_key,
                "old": " | ".join(skipped),
                "new": final_val
            })

    # ---------------- PROCESS RELEASE ----------------
    new_lines = []
    replace_count = 0
    current_section = "DEFAULT"

    seen_keys = set()
    seen_keys_commented = set()

    for line in rel_lines:

        stripped = line.strip()

        logger.debug(f"[KV][DEBUG_LINE] raw='{line.rstrip()}' stripped='{stripped}'")

        # ---------------- SECTION ----------------
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped
            new_lines.append(line)
            continue

        # ---------------- COMMENT HANDLING (FIXED) ----------------
        if stripped.startswith("#") or stripped.startswith("!"):

            stripped_no_comment = stripped.lstrip("#").strip()

            if "=" in stripped_no_comment or ":" in stripped_no_comment:

                key_match = re.match(r"^\s*([^:=\s]+)", stripped_no_comment)

                if key_match:
                    key_name = key_match.group(1)
                    compound_key = f"{current_section}|{key_name}"

                    seen_keys_commented.add(compound_key)

                    # 🔥 FIX: if exists in base → replace (uncomment)
                    if compound_key in base_data:

                        base_value = base_data[compound_key]

                        new_line = f"{key_name}={base_value}\n"
                        new_lines.append(new_line)

                        seen_keys.add(compound_key)

                        log_structured(
                            logger,
                            "debug",
                            "KV",
                            "UNCOMMENT_REPLACE",
                            rel_file,
                            compound_key,
                            "commented in release → replaced from base"
                        )

                        report.append({
                            "type": "BASE_TO_RELEASE_REPLACED",
                            "file": rel_file,
                            "element": compound_key,
                            "old": stripped,
                            "new": base_value
                        })

                        continue

            # keep comment if not in base
            new_lines.append(line)
            continue

        # ---------------- EMPTY ----------------
        if not stripped:
            new_lines.append(line)
            continue

        updated = False

        for compound_key, base_value in base_data.items():

            section, key = compound_key.split("|", 1)

            if section != current_section:
                continue

            match = re.match(
                rf"^(\s*)({re.escape(key)})([ \t]*[:=][ \t]*)([^\r\n#]*)(.*)$",
                line
            )

            if match:

                leading_ws = match.group(1)
                delim = match.group(3)
                current_value = match.group(4).strip()
                trailing_comment = match.group(5)

                seen_keys.add(compound_key)

                line_ending = "\n" if line.endswith("\n") else ""

                # EMPTY BASE
                if base_value.strip() == "":
                    new_line = f"{leading_ws}{key}{delim}{trailing_comment}{line_ending}"
                    new_lines.append(new_line)

                    log_structured(logger, "debug", "KV", "EMPTY_BASE",
                                   rel_file, compound_key,
                                   f"release='{current_value}' → forced empty",
                                   severity="ERROR")

                    report.append({
                        "type": "EMPTY_BASE_OVERRIDE",
                        "file": rel_file,
                        "element": compound_key,
                        "old": current_value,
                        "new": "",
                        "recommended": current_value
                    })

                    updated = True
                    break

                # NORMAL REPLACE
                if current_value != base_value:
                    new_line = f"{leading_ws}{key}{delim}{base_value}{trailing_comment}{line_ending}"
                    new_lines.append(new_line)

                    log_structured(logger, "debug", "KV", "REPLACE",
                                   rel_file, compound_key,
                                   f"{current_value} → {base_value}")

                    report.append({
                        "type": "BASE_TO_RELEASE_REPLACED",
                        "file": rel_file,
                        "element": compound_key,
                        "old": current_value,
                        "new": base_value
                    })

                else:
                    new_lines.append(line)
                    replace_count += 1

                updated = True
                break

        if not updated:
            new_lines.append(line)

    # =========================================================
    # BASE-ONLY INSERTION (FIXED)
    # =========================================================
    base_sequence = list(base_data.keys())

    from collections import defaultdict
    section_wise_keys = defaultdict(list)

    for compound_key in base_sequence:
        section, key = compound_key.split("|", 1)
        section_wise_keys[section].append(compound_key)

    output_key_index = {}
    current_section = "DEFAULT"

    for idx, line in enumerate(new_lines):

        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped
            continue

        if "=" in stripped or ":" in stripped:
            key_match = re.match(r"^\s*([^:=\s]+)", stripped)
            if key_match:
                key = key_match.group(1)
                compound_key = f"{current_section}|{key}"
                output_key_index[compound_key] = idx

    # Section positions
    section_positions = {}
    current_section = "DEFAULT"

    for idx, line in enumerate(new_lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped
            section_positions[current_section] = idx

    # Insert keys
    for section, keys in section_wise_keys.items():

        if section not in section_positions:
            continue

        section_start = section_positions[section]

        for i, compound_key in enumerate(keys):

            # 🔥 CRITICAL FIX
            if (
                compound_key in seen_keys or
                compound_key in seen_keys_commented or
                compound_key in output_key_index
            ):
                continue

            base_lines = base_blocks.get(compound_key, [])
            if not base_lines:
                continue

            insert_pos = section_start + 1

            new_lines = (
                new_lines[:insert_pos] +
                base_lines +
                new_lines[insert_pos:]
            )

            report.append({
                "type": "BASE_ONLY_PARAMETER_ADDED",
                "file": rel_file,
                "element": compound_key,
                "old": "",
                "new": base_data[compound_key]
            })

    # =========================================================
    # CLEAN BLANK AFTER SECTION
    # =========================================================
    cleaned = []
    skip_blank = False

    for line in new_lines:
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            cleaned.append(line)
            skip_blank = True
            continue

        if skip_blank and stripped == "":
            skip_blank = False
            continue

        skip_blank = False
        cleaned.append(line)

    new_lines = cleaned

    # ---------------- WRITE ----------------
    if not args.dry_run:
        ensure_dir(out_file)
        with open(out_file, "w") as f:
            f.writelines(new_lines)

# ---------------- JSON ----------------
def process_json(base_file, rel_file, out_file, report, logger, args):

    logger.info(f"[JSON] {rel_file}")

    # =========================================================
    # ✅ STEP -1: VALIDATE INPUT JSON FILES
    # =========================================================
    def safe_load_json(file_path, file_role):

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
    
                if not content:
                    log_structured(logger, "error", "JSON", "EMPTY_FILE",
                                   file_path, "", f"{file_role} file is empty")
                    return {}
    
                # ✅ FULL VALIDATION
                parsed = json.loads(content)
    
                return parsed
    
        except json.JSONDecodeError as e:
            log_structured(logger, "error", "JSON", "INVALID_JSON",
                           file_path, "", f"{file_role} invalid JSON: {str(e)}")
    
            report.append({
                "type": "INVALID_JSON",
                "file": file_path,
                "element": "",
                "old": "INVALID_JSON",
                "new": ""
            })
    
            return {}
    
        except Exception as e:
            log_structured(logger, "error", "JSON", "READ_ERROR",
                           file_path, "", str(e))
            return {}

    base = safe_load_json(base_file, "BASE")
    rel = safe_load_json(rel_file, "RELEASE")

    # 🚨 STOP if invalid input
    if base is None or rel is None:
        return

    # =========================================================
    # ✅ DUPLICATE DETECTION (UNCHANGED)
    # =========================================================
    detect_json_duplicates(base_file, rel_file, report, logger)

    change_counter = {"count": 0}

    # =========================================================
    # ✅ MERGE LOGIC
    # =========================================================
    def merge(b, r, path=""):

        for k in b:

            current_path = f"{path}.{k}" if path else k

            if isinstance(b[k], dict) and isinstance(r.get(k), dict):
                merge(b[k], r[k], current_path)

            else:
                old_val = r.get(k)
                new_val = b[k]

                # -------- EMPTY BASE --------
                if new_val == "":
                    log_structured(logger, "debug", "JSON", "EMPTY_BASE",
                                   rel_file, current_path,
                                   f"release='{old_val}' → forced empty",
                                   severity="ERROR")

                    report.append({
                        "type": "JSON_EMPTY_BASE_OVERRIDE",
                        "file": rel_file,
                        "element": current_path,
                        "old": json.dumps(old_val),
                        "new": "",
                        "recommended": json.dumps(old_val)
                    })

                    r[k] = ""
                    change_counter["count"] += 1
                    continue

                # -------- NORMAL REPLACE --------
                if old_val != new_val:

                    log_structured(logger, "debug", "JSON", "REPLACE",
                                   rel_file, current_path,
                                   f"{old_val} → {new_val}")

                    report.append({
                        "type": "JSON_BASE_TO_RELEASE_REPLACED",
                        "file": rel_file,
                        "element": current_path,
                        "old": json.dumps(old_val),
                        "new": json.dumps(new_val)
                    })

                    r[k] = new_val
                    change_counter["count"] += 1

                else:
                    log_structured(logger, "debug", "JSON", "NO_CHANGE",
                                   rel_file, current_path,
                                   f"value={old_val}")

    # =========================================================
    # ✅ RELEASE-ONLY DETECTION
    # =========================================================
    def find_release_only(b, r, path=""):
        for k in r:

            current_path = f"{path}.{k}" if path else k

            if k not in b:

                log_structured(logger, "info", "JSON", "RELEASE_ONLY_PARAMETER_ADDED",
                               rel_file, current_path,
                               "parameter present only in release → retained")

                report.append({
                    "type": "RELEASE_ONLY_PARAMETER_ADDED",
                    "file": rel_file,
                    "element": current_path,
                    "old": json.dumps(r[k]),
                    "new": json.dumps(r[k])
                })

            elif isinstance(r[k], dict) and isinstance(b.get(k), dict):
                find_release_only(b[k], r[k], current_path)

    # =========================================================
    # ✅ EXECUTE MERGE
    # =========================================================
    merge(base, rel, "")
    find_release_only(base, rel)

    log_structured(logger, "debug", "JSON", "SUMMARY",
                   rel_file,
                   "",
                   f"total_changes={change_counter['count']}")

    # =========================================================
    # ✅ STEP 4: FINAL OUTPUT VALIDATION
    # =========================================================
    try:
        # validate by dumping + loading
        json_text = json.dumps(rel)
        json.loads(json_text)

    except Exception as e:
        log_structured(logger, "error", "JSON", "INVALID_OUTPUT_JSON",
                       rel_file, "",
                       f"Generated JSON invalid: {str(e)}")

        report.append({
            "type": "INVALID_OUTPUT_JSON",
            "file": rel_file,
            "element": "",
            "old": "INVALID_JSON_GENERATED",
            "new": ""
        })

        return  # 🚨 DO NOT WRITE INVALID OUTPUT

    # =========================================================
    # ✅ WRITE OUTPUT
    # =========================================================
    if not args.dry_run:
        ensure_dir(out_file)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(rel, f, indent=2)


            
# ---------------- LOGROTATE ----------------
def process_logrotate(base_file, rel_file, out_file, report, logger, args):

    logger.info(f"[LOGROTATE] {rel_file}")

    with open(base_file) as f:
        base = f.read()

    # -------- EMPTY BASE --------
    if not base.strip():

        log_structured(logger, "debug", "LOGROTATE", "EMPTY_BASE",
                       rel_file, "",
                       "release ignored → forced empty file",
                       severity="ERROR")

        report.append({
            "type": "LOGROTATE_EMPTY_BASE_OVERRIDE",
            "file": rel_file,
            "element": "",
            "old": "FULL_FILE",
            "new": "",
            "recommended": "FROM_RELEASE"
        })

        if not args.dry_run:
            ensure_dir(out_file)
            open(out_file, "w").close()

        return

    # -------- NORMAL REPLACE --------
    log_structured(logger, "debug", "LOGROTATE", "REPLACE",
                   rel_file, "",
                   "replaced from base")

    report.append({
        "type": "LOGROTATE_BASE_TO_RELEASE_REPLACED",
        "file": rel_file
    })

    if not args.dry_run:
        ensure_dir(out_file)
        with open(out_file, "w") as f:
            f.write(base)
            
# ---------------- REPORT ----------------
def write_excel(report, base_files, rel_files, base_dir=None, rel_dirs=None):

    from openpyxl import Workbook
    from openpyxl.styles import Font, Border, Side, Alignment
    from pathlib import Path
    from datetime import datetime
    import re
    from difflib import SequenceMatcher
    import os

    # ---------------------------------------------------------
    # ✅ NORMALIZE DIR NAMES (ONLY BASENAME)
    # ---------------------------------------------------------
    base_dir_name = os.path.basename(os.path.normpath(base_dir)) if base_dir else ""

    if not rel_dirs:
        rel_dirs = [""]

    rel_dir_name = os.path.basename(os.path.normpath(rel_dirs[0])) if rel_dirs else ""

    wb = Workbook()

    # =========================================================
    # 🔹 DIFF EXTRACTOR
    # =========================================================
    def extract_xml_changes(old_xml, new_xml):

        import xml.etree.ElementTree as ET
        from collections import defaultdict
    
        try:
            old_root = ET.fromstring(old_xml)
            new_root = ET.fromstring(new_xml)
        except Exception:
            return ""
    
        changes = []
    
        # ---------------------------------------------------------
        # BUILD ELEMENT MAP (TAG + NAME ATTR)
        # ---------------------------------------------------------
        def build_map(root):
            m = defaultdict(list)
    
            for elem in root.iter():
                tag = elem.tag.split("}")[-1]
                name = elem.attrib.get("name", "")
    
                key = (tag, name)
    
                m[key].append(elem)
    
            return m
    
        old_map = build_map(old_root)
        new_map = build_map(new_root)
    
        all_keys = set(old_map) | set(new_map)
    
        # ---------------------------------------------------------
        # HELPER
        # ---------------------------------------------------------
        def elem_text(e):
            return (e.text or "").strip()
    
        def elem_full(e):
            return ET.tostring(e, encoding="unicode").strip()
    
        def elem_start(e):
            return elem_full(e).split(">")[0] + ">"
    
        # ---------------------------------------------------------
        # COMPARE
        # ---------------------------------------------------------
        for key in all_keys:
    
            tag, name = key
    
            old_elems = old_map.get(key, [])
            new_elems = new_map.get(key, [])
    
            # ---------------- REMOVED ----------------
            if old_elems and not new_elems:
                old_str = " ".join(elem_full(e) for e in old_elems)
                changes.append(f"OLD: {old_str}  →  NEW: (removed)")
                continue
    
            # ---------------- ADDED ----------------
            if new_elems and not old_elems:
                new_str = " ".join(elem_full(e) for e in new_elems)
                changes.append(f"OLD: (added)  →  NEW: {new_str}")
                continue
    
            # ---------------- MULTIPLE ELEMENTS (address case) ----------------
            if len(old_elems) > 1 or len(new_elems) > 1:
    
                old_str = " ".join(elem_full(e) for e in old_elems)
                new_str = " ".join(elem_full(e) for e in new_elems)
    
                if old_str != new_str:
                    changes.append(f"OLD: {old_str}  →  NEW: {new_str}")
    
                continue
    
            # ---------------- SINGLE ELEMENT ----------------
            old_elem = old_elems[0]
            new_elem = new_elems[0]
    
            old_text = elem_text(old_elem)
            new_text = elem_text(new_elem)
    
            # =========================================================
            # ✅ CASE 1: TEXT CHANGE (property)
            # =========================================================
            if old_text != new_text:
                changes.append(
                    f"OLD: <{tag}>{old_text}</{tag}>  →  NEW: <{tag}>{new_text}</{tag}>"
                )
                continue
    
            # =========================================================
            # ✅ CASE 2: ATTRIBUTE CHANGE (RollingFile FIX)
            # =========================================================
            old_start = elem_start(old_elem)
            new_start = elem_start(new_elem)
    
            if old_start != new_start:
                changes.append(
                    f"OLD: {old_start}\nNEW: {new_start}"
                )
                continue
    
        return "\n".join(changes)

    
    def extract_json_changes(old, new):

        import json
    
        try:
            old_json = json.loads(old)
            new_json = json.loads(new)
        except Exception:
            return ""
    
        changes = []
    
        # ---------------------------------------------------------
        # HANDLE LIST OF LIST STRUCTURE (YOUR CASE)
        # ---------------------------------------------------------
        if isinstance(old_json, list) and isinstance(new_json, list):
    
            max_len = max(len(old_json), len(new_json))
    
            for i in range(max_len):
    
                old_item = old_json[i] if i < len(old_json) else None
                new_item = new_json[i] if i < len(new_json) else None
    
                # -------------------------------
                # REMOVED
                # -------------------------------
                if old_item is not None and new_item is None:
                    changes.append(
                        f"OLD: {json.dumps(old_item)}  →  NEW: (removed)"
                    )
                    continue
    
                # -------------------------------
                # ADDED
                # -------------------------------
                if old_item is None and new_item is not None:
                    changes.append(
                        f"OLD: (empty)  →  NEW: {json.dumps(new_item)}"
                    )
                    continue
    
                # -------------------------------
                # CHANGED BLOCK
                # -------------------------------
                if old_item != new_item:
                    changes.append(
                        f"OLD: {json.dumps(old_item)}\n→ NEW: {json.dumps(new_item)}"
                    )
    
            return "\n\n".join(changes)
    
        # ---------------------------------------------------------
        # FALLBACK (NON-LIST JSON)
        # ---------------------------------------------------------
        if old_json != new_json:
            return f"OLD: {json.dumps(old_json)}\n→ NEW: {json.dumps(new_json)}"
    
        return ""
    
    
    
    def extract_changed_portion(old, new, type_val=None):
    
        if type_val == "XML_BASE_TO_RELEASE_REPLACED":
            return extract_xml_changes(old, new)
    
        if type_val == "JSON_BASE_TO_RELEASE_REPLACED":
            return extract_json_changes(old, new)
    
        return ""
    

    # =========================================================
    # 🔹 BUILD ROWS
    # =========================================================
    def build_changes_rows(report):
        rows = []

        for r in report:
            old_val = r.get("old", "")
            new_val = r.get("new", "")
            type_val = r.get("type")

            changes = ""

            if type_val in (
                "XML_BASE_TO_RELEASE_REPLACED",
                "JSON_BASE_TO_RELEASE_REPLACED"
            ):
                changes = extract_changed_portion(old_val, new_val, type_val)

            rows.append([
                r.get("file"),
                type_val,
                r.get("element"),
                old_val,
                new_val,
                changes
            ])

        return rows

    # =========================================================
    # 🔹 SHEET BUILDER
    # =========================================================
    def add_sheet(name, rows, headers):
        ws = wb.create_sheet(name)

        bold_font = Font(bold=True)
        red_font = Font(color="FF0000")
        orange_font = Font(color="FFA500")
        yellow_font = Font(color="FFC000")

        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin")
        )

        wrap_align = Alignment(wrap_text=True, vertical="top")

        ws.append(headers)

        for col in ws[1]:
            col.font = bold_font
            col.border = thin_border
            col.alignment = wrap_align

        for idx, r in enumerate(rows, start=2):
            ws.append(r)

            row_type = r[1] if len(r) > 1 else None

            if row_type:

                if row_type in (
                    "DUPLICATE_KEY_BASE",
                    "DUPLICATE_KEY_RELEASE",
                    "EMPTY_BASE_OVERRIDE",
                    "EMPTY_BASE_OVERRIDE_XML",
                    "JSON_EMPTY_BASE_OVERRIDE",
                    "LOGROTATE_EMPTY_BASE_OVERRIDE",
                    "MAPPING_NOT_FOUND"
                ):
                    for cell in ws[idx]:
                        cell.font = red_font

                elif row_type == "BASE_ONLY_PARAMETER_ADDED":
                    for cell in ws[idx]:
                        cell.font = yellow_font

                elif row_type == "RELEASE_ONLY_PARAMETER_ADDED":
                    for cell in ws[idx]:
                        cell.font = orange_font

        for row in ws.iter_rows():
            for cell in row:
                cell.border = thin_border
                cell.alignment = wrap_align

        for col in ws.columns:
            max_length = 0
            col_letter = col[0].column_letter

            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))

            ws.column_dimensions[col_letter].width = min(max_length + 2, 80)

    # =========================================================
    # 🔹 CHANGES
    # =========================================================
    add_sheet(
        "Changes",
        build_changes_rows(report),
        ["File", "ParameterType", "Parameter",
         "Release Config Value", "New Value from Base/Prod", "Changes"]
    )

    # =========================================================
    # 🔹 BASE ONLY (FIXED)
    # =========================================================
    base_rows = [
        [f"{base_dir_name}/{f}" if base_dir_name else f]
        for f in base_files - rel_files
    ]

    add_sheet("BaseOnlyFiles", base_rows, ["Production Files"])

    # =========================================================
    # 🔹 RELEASE ONLY (FIXED)
    # =========================================================
    release_rows = [
        [f"{rel_dir_name}/{f}" if rel_dir_name else f]
        for f in rel_files - base_files
    ]

    add_sheet("ReleaseOnlyFiles", release_rows, ["Release Conf Files"])

    # =========================================================
    # 🔹 FILE MAPPING (FIXED)
    # =========================================================
    mapping_rows = []

    for r in report:
        if r.get("type") == "FILE_MAPPING":

            base_path = f"{base_dir_name}/{r.get('old')}" if base_dir_name else r.get("old")
            rel_path = f"{rel_dir_name}/{r.get('new')}" if rel_dir_name else r.get("new")

            mapping_rows.append([base_path, rel_path])

    add_sheet(
        "FileMapping",
        mapping_rows,
        ["Mapped Production Filename", "Release Conf Filename"]
    )

    # remove default
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)

    report_path = report_dir / f"merge_report.{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    wb.save(report_path)

    return report_path


# ---------------- DIR PROCESS ----------------
def process_dirs(base_dir, rel_dirs, out_dir, args, logger):

    report = []

    base_files = set()
    rel_files = set()

    mapped_base_files = set()
    mapped_rel_files = set()

    base_dir = os.path.normpath(base_dir)

    mapping = load_mapping(args.mapping_file)
    copy_only_files = load_copy_only(args.copy_baseonlyconfigfile, base_dir)

    # ================= BASE INDEX =================
    base_name_index = defaultdict(list)

    for root, _, files in os.walk(base_dir):
        for f in files:
            rel_path = os.path.normpath(
                os.path.relpath(os.path.join(root, f), base_dir)
            )
            base_files.add(rel_path)
            base_name_index[f].append(rel_path)

    # ================= BUILD MAPPING LOOKUP =================
    mapping_lookup = {}

    for base_rel, mapped_rel in mapping.items():
    
        base_rel = os.path.normpath(base_rel.strip())
        mapped_rel = os.path.normpath(mapped_rel.strip())
    
        # ---------------- BASE NORMALIZATION ----------------
        if base_rel.startswith(base_dir + os.sep):
            base_rel_norm = os.path.relpath(base_rel, base_dir)
        elif base_rel.startswith(os.path.basename(base_dir) + os.sep):
            base_rel_norm = base_rel.split(os.sep, 1)[1]
        else:
            base_rel_norm = base_rel
    
        # ---------------- RELEASE NORMALIZATION ----------------
        mapped_rel_norm = None
    
        for rd in rel_dirs:
            rd_name = os.path.basename(os.path.normpath(rd))
    
            if mapped_rel.startswith(rd + os.sep):
                mapped_rel_norm = os.path.relpath(mapped_rel, rd)
                break
    
            elif mapped_rel.startswith(rd_name + os.sep):
                mapped_rel_norm = mapped_rel.split(os.sep, 1)[1]
                break
    
        if mapped_rel_norm is None:
            mapped_rel_norm = mapped_rel
    
        # remove leading ./
        mapped_rel_norm = mapped_rel_norm.lstrip("./")
    
        # store mapping
        mapping_lookup[mapped_rel_norm] = base_rel_norm
        mapping_lookup[os.path.basename(mapped_rel_norm)] = base_rel_norm

    logger.debug(f"[MAPPING_LOOKUP] size={len(mapping_lookup)}")

    # =====================================================
    # ✅ COPY-ONLY (RUN ONCE ONLY)
    # =====================================================
    for rel_path in copy_only_files:

        base_candidate = os.path.join(base_dir, rel_path)

        if not os.path.exists(base_candidate):
            log_structured(logger, "warning", "COPY_ONLY", "BASE_MISSING",
                           rel_path, "", "base file not found")
            continue

        out_file = os.path.join(out_dir, rel_path)

        log_structured(logger, "info", "COPY_ONLY", "BASE_ONLY",
                       rel_path, "", "copied (not present in release)")

        if not args.dry_run:
            ensure_dir(out_file)
            copy_file(base_candidate, out_file, logger)

        mapped_base_files.add(rel_path)

        report.append({
            "type": "BASE_ONLY_FILE_COPIED",
            "file": rel_path,
            "element": "",
            "old": "NOT_PRESENT_IN_RELEASE",
            "new": "FROM_BASE"
        })

    # ================= PROCESS RELEASE FILES =================
    for d in rel_dirs:

        d = os.path.normpath(d)

        for root, _, files in os.walk(d):
            for f in files:

                rel_file = os.path.join(root, f)
                rel_rel_path = os.path.normpath(os.path.relpath(rel_file, d))
                rel_files.add(rel_rel_path)

                base_file = None
                mapped = False

                # =====================================================
                # ✅ FAST MAPPING
                # =====================================================
                base_rel_norm = (
                    mapping_lookup.get(rel_rel_path) or
                    mapping_lookup.get(f)
                )

                if base_rel_norm:
                    base_file = os.path.join(base_dir, base_rel_norm)
                    mapped = True
                
                    # ✅ CRITICAL: mark mapped BEFORE anything else
                    mapped_base_files.add(os.path.normpath(base_rel_norm))
                    mapped_rel_files.add(os.path.normpath(rel_rel_path))
                
                    report.append({
                        "type": "FILE_MAPPING",
                        "file": rel_rel_path,
                        "element": "",
                        "old": base_rel_norm,
                        "new": rel_rel_path
                    })

                # =====================================================
                # ✅ FALLBACK
                # =====================================================
                if not base_file:

                    candidate = os.path.join(base_dir, rel_rel_path)

                    if os.path.exists(candidate):
                        base_file = candidate

                    else:
                        matches = base_name_index.get(f, [])

                        if len(matches) == 1:
                            base_file = os.path.join(base_dir, matches[0])

                        elif len(matches) > 1:
                            log_structured(logger, "warning", "FILE", "AMBIGUOUS_MATCH",
                                           rel_file, f, f"candidates={matches}")
                            continue

                        else:
                            log_structured(logger, "warning", "FILE", "NO_MATCH",
                                           rel_file, f, "no matching file in base")

                            # ❌ DO NOT append to report

                            # Just log
                            log_structured(logger, "info", "FILE", "NO_MATCH",
                                           rel_file, f, "no matching file in base")

                # =====================================================
                # ✅ VALIDATION
                # =====================================================
                if not base_file or not os.path.exists(base_file):
                    continue

                base_rel_matched = os.path.normpath(
                    os.path.relpath(base_file, base_dir)
                )

                mapped_base_files.add(base_rel_matched)
                mapped_rel_files.add(rel_rel_path)

                # =====================================================
                # ✅ OUTPUT PATH
                # =====================================================
                out_file = (
                    os.path.join(out_dir, rel_rel_path)
                    if mapped else
                    os.path.join(out_dir, base_rel_matched)
                )

                # =====================================================
                # ✅ PROCESS FILE
                # =====================================================
                if f.endswith((".xml", ".xsd")):
                    process_xml(base_file, rel_file, out_file, args, logger, report)

                elif f.endswith((".cfg", ".ini", ".conf", ".properties", ".sh")):
                    process_kv(base_file, rel_file, out_file, report, logger, args)

                elif f.endswith(".json"):
                    process_json(base_file, rel_file, out_file, report, logger, args)

                elif f.endswith(".logrotate"):
                    process_logrotate(base_file, rel_file, out_file, report, logger, args)

                else:
                    if not args.dry_run:
                        copy_file(rel_file, out_file, logger)

    # ================= FINAL CLEANUP =================
    base_only = base_files - mapped_base_files
    release_only = rel_files - mapped_rel_files

    normalized_base = set(os.path.normpath(f) for f in base_only)
    normalized_rel = set(os.path.normpath(f) for f in release_only)

    logger.debug(f"[FINAL] BaseOnly={len(normalized_base)} ReleaseOnly={len(normalized_rel)}")

    return report, normalized_base, normalized_rel
    
# ---------------- MAIN ----------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--release-dirs", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--exclude-params-in-baseonlyconfig", action="store_true",
                    help="Exclude parameters present only in base config")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--mapping-file", help="Optional base-to-release file mapping")
    parser.add_argument("--copy-baseonlyconfigfile",
                    help="List of base files to copy directly without processing")

    args = parser.parse_args()
    logger = setup_logging(args.verbose)
    
    important(f"[BASE DIR]:{args.base_dir}, [RELEASE DIRS]:{', '.join(args.release_dirs)}, [OUTPUT DIR]:{args.output_dir}", logger)

    if args.dry_run:
        logger.info("[DRY-RUN] No files will be written")
    
    if not args.dry_run:
        clean_output_dir(args.output_dir, logger)

    report, base_files, rel_files = process_dirs(
        args.base_dir, args.release_dirs, args.output_dir, args, logger
    )

    excel = write_excel(report, base_files, rel_files, args.base_dir, args.release_dirs)

    # ---- IMPORTANT OUTPUT (console + log file) ----
    important(f"[REPORT] {excel}", logger)
    important(f"[SUMMARY] Total changes: {len(report)}", logger)
    
    logger.info(f"[REPORT] {excel}")
    logger.info(f"[SUMMARY] Total changes: {len(report)}")

if __name__ == "__main__":
    main()
