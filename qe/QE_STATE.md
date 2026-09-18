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
| F-012 | P1 | XML _find_matching_block non-greedy regex truncates named blocks with same-tag descendants | FIXED (uncommitted) — balanced matching; real: 113/971 XML lookups corrected, 0 worse, merge output unchanged |
| F-013 | P2 | JSON _collapse_primitive_arrays rewrites "[a,b]" inside string values | FIXED (uncommitted) — string-aware collapse; also fixed commas inside strings in arrays |
| F-014 | P2 | KV _split_kv prefers '=' over ':' → `k: v=x` mis-keyed, line duplicated | FIXED (uncommitted) — _split_kv first delimiter; _has_valid_kv_key kept '=' first (else 18 prose comments became keys) |
| F-015 | P2 | JSON `!=` treats true==1 / false==0 → release value kept | FIXED (uncommitted) — _same_json type-strict compare |
| F-018 | P1 | XML block matching hit commented-out <!-- --> copies (48 real lookups) | FIXED (uncommitted) — test_xml_commented_out_element_is_not_matched |
| F-019 | P3 | XML output dropped the final newline | FIXED (uncommitted) — test_xml_merge_keeps_final_newline |
| F-020 | P2 | KV merge of identical base/release produced spurious report rows (e.g. log4j 24× RELEASE_ONLY_PARAMETER_ADDED, testexternalservice EMPTY_BASE_OVERRIDE) and non-faithful output (±1..20 bytes) | MASKED for whitespace-equal files by WS-1; root cause OPEN — may affect files with real differences |
| F-017 | P2 | KV commented key with space before delimiter (`#a = B`) not recognised → base comment leaks to end of output (vs `#a=B` merged) | VERIFIED; literal trim rule sim: 2322 commented lines/109 files newly keys; merge output changes 4 files/node (blank lines in doc-comment headers) — needs Q9 scope |
| F-017 | P2 | (see above) | FIXED (uncommitted) — tests/test_merge_review_annotations.py (9 tests) |
| F-016 | P2 | KV indexed-group header not a union; groups matched by index only | FIXED (uncommitted) — tests/test_merge_groups_and_xml.py (6 tests); real data: 0 output diffs, W013 flags |

## OPEN QUESTIONS
- Q7 ANSWERED (IMPLEMENTED): header union = base items then release-only items (real data: base registry ⊂ release → output unchanged)
- Q8 ANSWERED: match by name subkey, index fallback — IMPLEMENTED
- Q12 ANSWERED: keep base count, flag GROUP_COUNT_MISMATCH [CMT-MRG-W013] — IMPLEMENTED (real: 2 flags/node, 0 output diffs)
- Q9 ANSWERED + IMPLEMENTED (uncommitted): base comments copied in context; W014 param / W015 section review annotations in output; `#key = v` recognised only for real keys; annotations not re-read. Real: fsmapp.properties +3 W015, +1 W014 (+2 APP-02), +3 alt-value comments; genericupload.properties 1 trailing space stripped on a commented key line (K-20 rule)
- Q10 FINAL (uncommitted): JSON base {} → release keys taken + W016; base [] → base kept + W016. Real: openapi-config.json output identical to last commit, flagged.
- Review follow-up FINAL (uncommitted): W017 in-file annotation for production Java class replaced (real: executor.class); base comments equal to active value not copied; comment lines byte-for-byte. Real: only fsmapp.properties changes (+7 lines/node, +1 APP-02)
- Q11 ANSWERED (IMPLEMENTED): insert named base-only XML elements unless --exclude-params-in-baseonlyconfig

## TESTS: 71 passed (incl. 6 processor fixes, 6 whitespace); previously 59 passed (13 audit KV + 11 merge engine + 9 mappings + 6 groups/xml + 12 review annotations + 5 patch + 3 error codes), 0.46s
## PERFORMANCE BASELINES: none measured
## SONNET TASKS COMPLETED: 1 (S1: 5 findings, 4 exact + 1 corrected by orchestrator) | OPUS TASKS COMPLETED: 0

LAST COMPLETED ACTION: commit 52765a3; S1 review verified + real-data exposure measured
LAST: commit f9eb4f7 (review annotations); processor fixes implemented + side-by-side verification sent
NEXT ACTION: commit processor + whitespace fixes on approval; investigate F-020 root cause; then S2 filter/backup review
