# QE_STATE — ConfigMergeTool

PROJECT VERSION: 2.0.1 — branch fix/audit-kv-section-compare @ 547f785 (fixes uncommitted)
CURRENT PHASE: 2 — P0–P3 fixes DONE, verified (2026-09-17)
CURRENT OBJECTIVE: MEMORY OPTIMIZATION — M-1 + M-2 VERIFIED + committed to PR #2; M-5 left by user decision

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
| F-020 | P1 | KV merge fidelity — pre-existing since 547f785 (not caused by this week's changes). Identity test (file merged with itself) on 253 real KV files: 143 not identical; 0 active params lost (160 dropped lines = documented DUPLICATE_KEY collapse) | ROOT CAUSES FOUND, split below |
| F-020a | P2 | Key commented out in BOTH base and release reported RELEASE_ONLY_PARAMETER_ADDED (e.g. log4j 24 rows) | FIXED (uncommitted) |
| F-020b | P1 | EMPTY_BASE_OVERRIDE (critical, exit 1) raised when release value is ALSO empty — real: fsmapp/testexternalservice `generic.caches=` empty on both sides → every real run exits 1 spuriously | FIXED (uncommitted) — real runs exit 1→0 |
| F-020c | P2 | Comments duplicated (493 lines) / lost (63 lines) across 96 real files, e.g. fsmapp `#trans.filter.1.results` twice, `#For parameter description…` dropped | FIXED (uncommitted) — group comment duplicates + dropped-duplicate comments |
| F-020d | P2 | Section repeated in one file (e.g. release icampaignservice/fsmapp.properties [EventTrigger Redistribution Poller] L282 & L308) → folded into one; 2nd header lost, its keys moved under the first | FIXED (uncommitted) — decision 1a; real icampaignservice fsmapp: 26→1 lines differing from release |
| F-020e | P1 (latent) | `.sh` registered as KV: shell script lines (fi/done/if …) dropped — 214 lines in Telstra Tomcat scripts; no .sh in current merge data | FIXED (uncommitted) — decision 2a (.sh → GenericProcessor); audit now compares .sh as text (real: 9 legacy Tomcat scripts) |
| F-021 | P1 | Filter: a `+path` force-include switches the filter into include-mode — a filter with only excludes + one force-include silently skips every other file (readme's own example) | FIXED (uncommitted) |
| F-022 | P2 | Filter: `!backup` / `!old` / `!tmp` (readme rule h "directory exclude") only match a FILE named so; directories are still audited | VERIFIED; real Telstra filter.txt uses them — 88 files under backup/, 56 under old/ audited | FIXED (uncommitted) — decision yes; real: 0 files change (Telstra filter already include-mode) |
| F-023 | P3 | Filter: glob include containing '/' (e.g. `config/*.xml`) never matches (glob tested against filename only) | FIXED (uncommitted) |
| F-024 | P1 | Backup: `<file>_bkp200821`, `_bak17062026`, `_bkpprobetrouleshoot` (no separator after bkp/bak) not detected — ~70 real backups with original present audited as live config (.properties/.cfg/.xml/.conf/.sstp) | FIXED (uncommitted) — real: 122 more backups skipped incl. F-025, all originals present |
| F-025 | P2 | Backup: marker before the extension (`fsmapp_240226.properties`, `dbwriter_bkp040322.cfg`, `style_old_11jan07.css`) not detected though `fsmapp.properties` exists | FIXED (uncommitted) — decision yes |
| F-026 | P3 | Backup: readme lists `_v[0-9]*` and `_YYYYMMDDHHmmss` but code detects neither | RESOLVED — decision no: _v not a backup; 14-digit timestamp added; readme corrected |
| F-027 | P2 | Audit: key duplicated within one section on a node counts as a mismatch even when every node is byte-identical or the file exists on one node only — real: 3 identical + 5 single-node KV files flagged (cliapp-irdbreport.properties, iMASCodes_en_US.properties, ss7txnwriter*.cfg); inflates mismatches / exit 1 | FIXED (uncommitted) — last value used, W007 warning; real: 0 identical/single-node mismatches |
| F-028 | P3 | Audit: text/xml comparison ignores trailing spaces + line endings but not indentation — real: subscription/cea/package.xml tabs vs 4 spaces = mismatch (23 other whitespace-only XML = match) | FIXED (uncommitted) — whitespace-insensitive, I001; real package.xml matches |
| F-029 | P2 (config) | Telstra filter.txt has no `sstp` include — SmartSTP routing-rule.sstp / rule-template.sstp never audited (7 files run a, 4 run b) | FIXED (uncommitted) — sstp in sample-filter.txt + Telstra-RSC1/filter.txt (user copies to OneDrive) |
| F-030 | P1 | SSTP parser `_RE_BLOCK_HDR` had `^` used with `.match(text, pos)` → 0 blocks for every real file (and repo sample) → every .sstp audit a silent MATCH; real routing-rule.sstp drift (SRC 0x…e vs 0x…d) hidden | FIXED (uncommitted) — regex + text fallback W010; real: 4 (a) / 2 (b) differing blocks now reported |
| F-020g | P3 | Telstra (audit-only) files: comment blocks of interleaved indexed groups duplicated/reordered (31 files) | OPEN — not in current merge data |
| F-020f | P3 | Synthetic blank separator between sections (+ preamble dedupe) adds/removes blank lines — 49 files whitespace-only | FIXED (uncommitted) — no synthetic separator, commented-header preamble kept, EOF = release |
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

## TESTS: 108 passed; earlier 81 passed; earlier 71 passed (incl. 6 processor fixes, 6 whitespace); previously 59 passed (13 audit KV + 11 merge engine + 9 mappings + 6 groups/xml + 12 review annotations + 5 patch + 3 error codes), 0.46s
## PERFORMANCE BASELINES (2026-09-18, Py 3.14.6, macOS 26.6.2, 12 CPU/24 GB, single process, no concurrency)
Workload (a) Telstra-RSC1 audit-rsc-all: 3 nodes, 823 audited files (after filter.txt), node dirs 0.55–1.0 GB (mostly jars/binaries, hashed streaming)
Workload (b) Telstra-RSC1 audit-rsc: 2 nodes, 745 audited files
Baseline peak RSS (3 runs, /usr/bin/time -l): (a) 700/749/748 MB, 4.80/4.17/4.19 s; (b) 710/709/730 MB, 2.66/2.77/2.68 s
Counterfactual empty ~/.configmergetool/feedback_history.json (HOME isolated, no code change): (a) 392/399/394 MB, 3.35–3.64 s; (b) 330/330/329 MB, 1.81–1.85 s
Phase profile (a, isolated HOME): scan 51 MB → compare loop 105 MB (tracemalloc 66 MB live) → xlsx 118 → part1 _build_html 227 → part2 371 → index 397 MB. tracemalloc peak 245 MB vs RSS 432 MB (≈190 MB allocator retention)
Measurement harness: scratchpad mem/prof.py (phase + per-file ru_maxrss attribution); ALWAYS run with HOME=<scratch> — real runs append to ~/.configmergetool

## MEMORY CHECKPOINT (2026-09-18) — M-1 + M-2
Golden: frozen-clock runs (scratch mem/golden.py, digest.py), 34 outputs (HTML parts, xlsx cells, feedback JSON, log, history) byte-identical g0 = g0b (determinism) = g1 (M-1) = g2 (M-1+M-2); exit codes 1/1 unchanged; no W009
After (3 runs, 195 MB history seeded): (a) 305/308/309 MB, 3.23–3.54 s (was 700–749 MB, 4.2–4.8 s) = −59%; (b) 274/274/275 MB, 1.71–1.79 s (was 709–730 MB, 2.7–2.8 s) = −62%
tracemalloc peak (a) 245 → 203 MB. Tests 108 → 125 passed
User history: ~/.configmergetool/feedback_history.json renamed to feedback_history.backup-20260918.json (archived, intact); removal of this session's 8 entries (20260918_144827..144950) BLOCKED by permission classifier — pending user

## MEMORY FINDINGS
| M-1 | P1 | _append_feedback_history json.load()s + rewrites the whole cross-run history every audit. Real file 195 MB / 53 runs / 1.93 M filtered_files paths (≤228k/run) → +350 MB peak, +0.8 s; grows every run, unbounded | FIXED (uncommitted, user chose A) — in-place append, bytes = json.dump(indent=2); real (195 MB history): (a) 748→387–395 MB, (b) 730→328–330 MB; tests/test_audit_feedback_history.py (7, mutation-checked) |
| M-2 | P2 | _build_html holds ~5 copies of each page (json.dumps indent=2 → 2× re.sub → f-string → encode) and page str is UCS-2 because template contains U+2713 → 24 Mchar page = 48 MB/copy, ≈+100–120 MB per part; _validate_html feeds whole page to HTMLParser | FIXED (uncommitted) — head/data/tail rendered, validated (_validate_html_parts) and written piecewise; (a) 395→305–309 MB, (b) 330→274 MB; tests/test_audit_report_pieces.py (10 incl. memory budget <3.5x raw: old 5.3x FAILS, new 2.1x) |
| M-3 | P3 | RSS ratchets across parts (freed page strings not returned to OS): part1 227 → part2 371 MB | PARTLY — stale previous-part page ref gone with M-2; allocator ratchet remains |
| M-4 | P3 | --feedback-summary loads the same 195 MB file (≈660 MB peak) | OPEN — small after history archived; grows again ~3.7 MB/run |
| M-5 | P3 | _render_html_parts: json.dumps(indent=2) (pure-Python encoder, millions of chunk strs) + 2 re.sub copies: +48/+82 MB per part | OPEN — streaming iterencode to file would rely on CPython chunk boundaries for </script escaping; user decision 2026-09-18: LEAVE (305 MB acceptable; no reliance on CPython chunking) |
Not causes (measured): binaries/jars (streamed sha256, 0 per-file jumps), scan (2 MB), compare loop total ~55 MB, xlsx +13 MB, _serialise_result +3 MB
## SONNET TASKS COMPLETED: 1 (S1: 5 findings, 4 exact + 1 corrected by orchestrator) | OPUS TASKS COMPLETED: 0

LAST COMPLETED ACTION: commit 52765a3; S1 review verified + real-data exposure measured
LAST: commit f9eb4f7 (review annotations); processor fixes implemented + side-by-side verification sent
LAST: commit a39f9d2; F-020 investigated (identity-merge harness scratch sep.*/ident.py, classify.py)
LAST: commit 7ce9138 (F-020) + audit .sh as text
LAST: S2 filter/backup review done by orchestrator (no delegation)
LAST: PR #2 opened; Telstra-RSC1 audits (a) 3 nodes 820 files 4.4s/740MB, (b) 2 nodes 743 files 2.5s/758MB; oracle check: 0 missed drifts
LAST: Memory Phase 1 baseline + root cause (M-1..M-4)
NEXT ACTION (memory): user: remove 8 session entries from archived history manually. Earlier: commit + push to PR #2 (plan approved); user copies sstp line into OneDrive Telstra-RSC/filter.txt
