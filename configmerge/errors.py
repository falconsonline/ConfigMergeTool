"""
configmerge.errors
~~~~~~~~~~~~~~~~~~
Stable identifiers for every error and warning the tool emits.

Format: CMT-<AREA>-<E|W|I><nnn>
    AREA  CLI = arguments / config files, MRG = merge mode,
          AUD = audit mode,               PAT = --apply-audit-patch
    E = error, W = warning, I = informational

Codes are a public contract (grep-able in logs, listed in ConfigMergeTool-readme.txt):
never renumber or reuse one; add new codes at the end of their area.
"""

from __future__ import annotations

from typing import Dict, Tuple

CODES: Dict[str, str] = {
    # ── CLI / configuration ─────────────────────────────────────────────
    "CMT-CLI-E001": "Config file cannot be read or is not valid JSON",
    "CMT-CLI-E002": "Config file is not a JSON array",
    "CMT-CLI-E003": "Config entry is not a JSON object",
    "CMT-CLI-E004": "Config entry is missing 'base_dir'",
    "CMT-CLI-E005": "Config entry contains a literal 'password' (use 'password_env')",
    "CMT-CLI-E006": "Duplicate node name in config file",
    "CMT-CLI-E007": "'remote' is not an object with 'host'",
    "CMT-CLI-E008": "'remote' contains a literal 'password' (use 'password_env')",
    "CMT-CLI-E009": "'port' / 'timeout_secs' are not integers",
    "CMT-CLI-E010": "Config entry failed validation (e.g. directory not found)",
    "CMT-CLI-E011": "--release-dirs is required",
    "CMT-CLI-E012": "--output-dir is required",
    "CMT-CLI-E013": "--base-dir is required",
    "CMT-CLI-E014": "--email-config is not yet implemented",
    "CMT-CLI-E015": "--remote-audit requires --audit-config-file",
    "CMT-CLI-E016": "--remote-audit SSH connectivity is not yet implemented",
    "CMT-CLI-E017": "Merge arguments failed validation (e.g. directory not found)",
    # ── Merge mode ──────────────────────────────────────────────────────
    "CMT-MRG-E001": "Processor failed for a file",
    "CMT-MRG-E002": "Ambiguous filename match: several base candidates, file skipped",
    "CMT-MRG-E003": "Invalid JSON input",
    "CMT-MRG-E004": "Merged JSON output is invalid",
    "CMT-MRG-E005": "Empty JSON file",
    "CMT-MRG-E006": "JSON file cannot be read",
    "CMT-MRG-E007": "Invalid XML input",
    "CMT-MRG-E008": "XML file cannot be read",
    "CMT-MRG-E009": "Logrotate base file is empty; output forced empty",
    "CMT-MRG-E010": "--output-dir overlaps a base or release directory; run refused",
    "CMT-MRG-E011": "SSTP release file missing",
    "CMT-MRG-E012": "KV base value empty; release value forced empty (EMPTY_BASE_OVERRIDE)",
    "CMT-MRG-E013": "XML base element empty; release element forced empty (EMPTY_BASE_OVERRIDE_XML)",
    "CMT-MRG-E014": "JSON base value empty; release value forced empty (JSON_EMPTY_BASE_OVERRIDE)",
    "CMT-MRG-W001": "Release file has no base counterpart; copied from release",
    "CMT-MRG-W002": "Release file resolves outside its release directory; skipped",
    "CMT-MRG-W003": "Copy-only base file not found; skipped",
    "CMT-MRG-W004": "Copy-only entry escapes the base directory; skipped",
    "CMT-MRG-W005": "Mapping entry escapes the base directory; skipped",
    "CMT-MRG-W006": "(retired 2026-09-17 — one base → several release files is supported, see CMT-MRG-I002)",
    "CMT-MRG-W007": "Mapping: mapped base file not found",
    "CMT-MRG-W008": "XML duplicate key",
    "CMT-MRG-W009": "File in several release dirs; dir matching the base name selected",
    "CMT-MRG-W010": "File in several release dirs; first release dir used",
    "CMT-MRG-W011": "(retired 2026-09-17 — XML many-to-one mapping merges all base files)",
    "CMT-MRG-W012": "(retired 2026-09-17 — JSON many-to-one mapping merges all base files)",
    "CMT-MRG-W013": "Indexed group count kept from base differs from the merged group total",
    "CMT-MRG-W014": "KV parameter commented out in base but active in release; review annotation added",
    "CMT-MRG-W015": "KV section commented out in base but active in release; review annotation added",
    "CMT-MRG-W016": "JSON empty object/array in base but populated in release; review required ({} takes release keys, [] keeps base)",
    "CMT-MRG-W017": "KV production Java class name replaced by release class; review annotation added",
    "CMT-MRG-I001": "Mapping: several base files mapped to one release file (first listed wins)",
    "CMT-MRG-I002": "Mapping: one base file mapped to several release files",
    "CMT-MRG-I003": "Base and release differ only in whitespace; release file copied as-is",
    # ── Audit mode ──────────────────────────────────────────────────────
    "CMT-AUD-E001": "Node directory not found; audit aborted",
    "CMT-AUD-E002": "File could not be compared (render error)",
    "CMT-AUD-W001": "Invalid logical_diff_pattern regex ignored",
    "CMT-AUD-W002": "Feedback history could not be written",
    "CMT-AUD-W003": "SSTP parse error on a node",
    "CMT-AUD-W004": "Invalid JSON on a node",
    "CMT-AUD-W005": "File cannot be read on a node",
    "CMT-AUD-W006": "Raw/display content truncated",
    "CMT-AUD-W007": "Same key duplicated within one section on a node; last value is used",
    "CMT-AUD-W008": "Duplicate log-name prefixes detected",
    "CMT-AUD-W009": "Generated HTML report failed the sanity check",
    "CMT-AUD-W010": "SSTP file has no recognisable blocks on a node; compared as text",
    "CMT-AUD-I001": "Text/XML nodes differ only in whitespace; treated as a match",
    # ── Apply audit patch ───────────────────────────────────────────────
    "CMT-PAT-E001": "Patch file cannot be read or is not valid JSON",
    "CMT-PAT-E002": "Patch JSON is missing a required field",
    "CMT-PAT-E003": "Patch change entry is malformed",
    "CMT-PAT-E004": "Patch contains no changes",
    "CMT-PAT-E005": "Patch node not found in node_dirs; changes skipped",
    "CMT-PAT-E006": "Patch file path is absolute; changes skipped",
    "CMT-PAT-E007": "Patch file path escapes its directory; changes skipped",
    "CMT-PAT-E008": "Patch node name is not a plain directory name; changes skipped",
    "CMT-PAT-E009": "Applying changes to a file failed",
}

# log_structured(type, action) → code
STRUCTURED_CODES: Dict[Tuple[str, str], str] = {
    ("ENGINE",    "PROCESSOR_FAILED"):           "CMT-MRG-E001",
    ("ENGINE",    "OUTPUT_DIR_OVERLAP"):         "CMT-MRG-E010",
    ("FILE",      "AMBIGUOUS_MATCH"):            "CMT-MRG-E002",
    ("JSON",      "INVALID_JSON"):               "CMT-MRG-E003",
    ("JSON",      "INVALID_OUTPUT_JSON"):        "CMT-MRG-E004",
    ("JSON",      "EMPTY_FILE"):                 "CMT-MRG-E005",
    ("JSON",      "READ_ERROR"):                 "CMT-MRG-E006",
    ("XML",       "INVALID_XML"):                "CMT-MRG-E007",
    ("XML",       "READ_ERROR"):                 "CMT-MRG-E008",
    ("LOGROTATE", "EMPTY_BASE"):                 "CMT-MRG-E009",
    ("SSTP",      "RELEASE_MISSING"):            "CMT-MRG-E011",
    ("FILE",      "NO_MATCH"):                   "CMT-MRG-W001",
    ("FILE",      "PATH_TRAVERSAL"):             "CMT-MRG-W002",
    ("COPY_ONLY", "MISSING"):                    "CMT-MRG-W003",
    ("COPY_ONLY", "PATH_TRAVERSAL"):             "CMT-MRG-W004",
    ("MAPPING",   "PATH_TRAVERSAL"):             "CMT-MRG-W005",
    ("MAPPING",   "BASE_MISSING"):               "CMT-MRG-W007",
    ("XML",       "DUPLICATE_KEY"):              "CMT-MRG-W008",
    ("FILE",      "MULTI_RELEASE_DIR_RESOLVED"): "CMT-MRG-W009",
    ("FILE",      "MULTI_RELEASE_DIR_FIRST"):    "CMT-MRG-W010",
    ("MAPPING",   "MULTI_BASE"):                 "CMT-MRG-I001",
    ("MAPPING",   "BASE_TO_MANY_RELEASES"):      "CMT-MRG-I002",
    ("FILE",      "WHITESPACE_ONLY"):            "CMT-MRG-I003",
    ("KV",        "EMPTY_BASE_OVERRIDE"):        "CMT-MRG-E012",
    ("KV",        "GROUP_COUNT_MISMATCH"):       "CMT-MRG-W013",
    ("KV",        "REVIEW_COMMENTED_IN_BASE"):   "CMT-MRG-W014",
    ("KV",        "REVIEW_COMMENTED_SECTION"):   "CMT-MRG-W015",
    ("JSON",      "REVIEW_EMPTY_IN_BASE"):       "CMT-MRG-W016",
    ("KV",        "REVIEW_CLASS_NAME_FROM_RELEASE"): "CMT-MRG-W017",
    ("XML",       "EMPTY_BASE_OVERRIDE"):        "CMT-MRG-E013",
    ("JSON",      "EMPTY_BASE_OVERRIDE"):        "CMT-MRG-E014",
}


class ConfigMergeError(Exception):
    """Fatal configuration/usage error.  The CLI prints it and exits 2."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(tag(code, message))


def tag(code: str, message: str) -> str:
    """Prefix *message* with its stable identifier: ``[CMT-MRG-E001] message``."""
    return f"[{code}] {message}"
