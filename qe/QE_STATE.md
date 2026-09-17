# QE_STATE — ConfigMergeTool

PROJECT VERSION: 2.0.1 — branch fix/audit-kv-section-compare @ 547f785 (fixes uncommitted)
CURRENT PHASE: 2 — P0–P3 fixes DONE, verified (2026-09-17)
CURRENT OBJECTIVE: commit decision; then S1 (processor edge-case review)

## VERIFIED ARCHITECTURE
- cli.py::_main routes: --feedback-summary → --apply-audit-patch → --audit-config-file → merge
- Merge: MergeEngine._run_one_base → FileMatcher → PROCESSOR_REGISTRY[ext] else GenericProcessor
- Audit: auditor/engine.py → html_report.py (AUDIT_DATA) → patch.py AuditPatcher
- Error IDs: configmerge/errors.py (CODES, STRUCTURED_CODES, ConfigMergeError(code,msg), tag)

## KNOWN INVARIANTS
- KV compound "[Section]|key" identical in engine._compare_kv / JS reconstructKV / patch._apply_kv
- Merge: base wins; base-only added; release-only keys kept; release-only FILES copied; hidden files ignored
- Output dir never equals/contains/inside an input dir (refused, exit 2)
- Every log_structured pair + tagged code registered and in readme (tests/test_error_codes.py)

## USER DECISIONS (2026-09-17)
Q1 copy release-only files · Q2 A skip ambiguous (critical) · Q4 refuse overlap · hidden files skipped ·
Q5 stable error IDs, all modes, patch exit 0/1/2 · Q6 unique filename fallback writes at base path (intended) ·
F-009 mapping one↔many both valid, many→one first-listed base wins for KV/XML/JSON · F-010 fix · .gitignore

## FINDINGS
| ID | Sev | Summary | Status |
|----|-----|---------|--------|
| F-001 | P0 | Release-only files missing from output | FIXED — test_release_only_file_is_copied_to_output; real data: +12 files/node, all merged files byte-identical to pre-fix |
| F-002 | P1 | Ambiguous filename merged arbitrary base | FIXED — test_ambiguous_filename_match_is_skipped_reported_and_exits_1; real data: 0 cases |
| F-003 | P1 | SSTP TypeError; processor failure exit 0 | FIXED — test_sstp_*, test_processor_failure_is_critical_and_exits_1 |
| F-004 | P1 | --output-dir = input dir deleted it | FIXED — test_output_dir_overlapping_input_* (5 variants) |
| F-005 | P1 | Patch node "../X" writes outside output | FIXED — test_node_name_traversal_* |
| F-006 | P2 | Patch exit always 0 | FIXED — 0/1/2 tests |
| F-007 | P3 | Malformed patch traceback | FIXED — CMT-PAT-E003 exit 2 |
| F-008 | P3 | Bad --base-dir raised raw ValueError traceback | FIXED — CMT-CLI-E017 exit 2 (smoke) |
| F-009 | P2 | XML/JSON many-to-one merged only base_files[0]; one-to-many warned as ambiguous | FIXED — tests/test_merge_mappings.py (4 tests); real data unaffected (no mapping files) |
| F-010 | P3 | Critical processor entries had no log line/ID | FIXED — CMT-MRG-E012..E014; real data: 3 E012 lines/node |
| F-011 | P1 | Unparseable JSON/XML input silently missing from output, exit 0 | FIXED — INVALID_JSON/INVALID_XML critical, 2 tests |

## OPEN QUESTIONS
- none

## TESTS: 41 passed (13 audit KV + 11 merge engine + 9 mappings + 5 patch + 3 error codes), 0.27s
## PERFORMANCE BASELINES: none measured
## SONNET TASKS COMPLETED: 0 | OPUS TASKS COMPLETED: 0

LAST COMPLETED ACTION: fixes + docs + real-data old/new output diff (scratchpad real.*)
NEXT ACTION: commit on user approval; then S1 Sonnet review of kv/xml/json processors
