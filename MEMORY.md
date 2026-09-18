# Project Decisions Log

Confirmed decisions and working rules for ConfigMergeTool. Newest first.
Each entry: date · decision · why. Glossary terms are defined in [CONTEXT.md](CONTEXT.md).

---

## 2026-09-15 — Audit KV: section-by-section comparison against the base node

**Trigger:** Telstra RSC audit (legacyrsc / newlab / newprod), `binaries/callservice/config/fsmapp.properties`
showed the same parameter in two places — missing on one config in an upper row and missing on the other
config in a lower row. v2.0.1 ordered rows by the first node's file and treated `#[X]` as a section, which
hid active keys (false "missing") and pushed sections the first node lacks to the bottom.

**Decisions (confirmed by user):**
1. **Base node** = first node in the audit config. If the base node lacks the file, the first node that has
   it is the base for that file.
2. A parameter is compared **within its section**. The same key in two sections of one file is **not a bug** —
   two separate rows. Keys in different sections are never matched to each other.
3. A **commented section header** (`#[X]`) is a comment. Active keys after it belong to the enclosing real
   section (same rule the report download and `patch.py` already use).
4. Sections and keys the base node lacks are shown **at their file position**; no repeated section blocks.
5. **Section check** on each section header row: base parameter count, and per node match / differ /
   missing / extra, or "section absent".
6. A **commented-out key** counts as present (commented), not missing.
7. **Revised 2026-09-18:** the same key twice in one section on a node (**duplicate in section**) shows both
   values with line numbers; the **last (second) value is the effective value** and is compared. The duplicate is
   a warning (CMT-AUD-W007, names the value used), **not** a mismatch — identical files with duplicates now match
   (was: counted as a mismatch, see Telstra `iMASCodes_en_US.properties`, `cliapp-irdbreport.properties`).
   A repeated section header (e.g. `[Profile Engine]` twice) merges into one section, so its keys become duplicates.
8. **Empty sections** are listed; a node lacking the header is flagged "section absent". Keys before the first
   header form the "(no section)" block with its own check.

9. **Section header rule** stays the merge parser's: `[Name]` optionally followed by an inline `# comment`.
   Known gap: report download (`reconstructKV`) and `patch.py` only accept a bare `[Name]` line — 0 such
   headers in the Telstra RSC data (156 KV files), left as-is.
10. **"Show differences only"** keeps a section header visible when any row under it is visible OR the section
    is absent on a node that has the file (base included). Matched headers still hide; empty sections stay
    visible when the filter is off.

Derived counting: missing = no entry (active or commented); differ = both active and (last) values differ;
match = otherwise (incl. commented); extra = key not in base.

**Rejected:** folding a key into one row across different sections (e.g. `pools` in `[CouchBase]` vs
`[DBConnectionPool]`) — real data showed different sections with different meanings/values.

---

## Merge output, matching and error identifiers (confirmed 2026-09-17)

1. **Release-only files** (no base counterpart) are copied to the output as-is — the output dir must be
   deployment-complete. Real data: 12 such files per iCampaign node (e.g. `config/dbtocsv.properties`).
2. **Hidden files** (name starts with `.`, e.g. `.DS_Store`) are ignored on both sides, like hidden dirs.
3. **Ambiguous filename match** (no mapping, no same-path match, several base files share the name) → the file
   is skipped, not merged and not copied; `AMBIGUOUS_MATCH_SKIPPED` is critical (exit 1). Resolve with a mapping.
   A *unique* filename-only match writes the merged file at the base path — confirmed intended.
4. **--output-dir overlapping** any base/release dir (equal, parent or child) is refused with exit 2 before
   anything is deleted — also in --dry-run.
5. **Error identifiers**: every error/warning carries `CMT-<CLI|MRG|AUD|PAT>-<E|W|I><nnn>` from
   `configmerge/errors.py`; codes are never renumbered/reused and are listed in the readme.
6. **Patch exit codes**: 0 all written, 1 some files skipped/failed, 2 invalid patch or nothing to apply.
7. **Mapping file is authoritative for base↔release pairs**: one base → many release files and many bases →
   one release file are both valid. Many-to-one uses the KV rule for every processor (KV, XML, JSON): the
   first base listed in the mapping file wins; later bases only add what earlier bases lack.
9. **KV indexed groups (2026-09-17)**: matched by the `prefix.N.name` subkey when every base and release group
   has a unique name, else by index (nameless groups such as `server.N.uri` must not append release default
   hosts). Comma-list headers (`schedule.registry`) = union, base items first. `prefix.count` keeps the base
   value (sites may run fewer groups on purpose) but is flagged `GROUP_COUNT_MISMATCH` [CMT-MRG-W013] when it
   differs from the merged total — real data: `schedule.count=3` vs 11 groups in iCampaign fsmapp.properties.
10. **XML base-only elements**: a named base-only element is inserted even if release has the same tag with
    other names; `--exclude-params-in-baseonlyconfig` suppresses it (included by default).
11. **Comments are context; unclear changes are annotated for review (2026-09-17)**: base comment lines are
    copied next to the parameter they describe, never dropped. Commented-out in base but active in release →
    release value kept, base comment + in-file `# [CMT-MRG-W014] REVIEW:` annotation (sections: W015 under the
    header). `#key = value` counts as a commented key only when the key is active in base or release (prose
    `# Database : text` stays prose — trimming all comments added blank lines to real doc headers). JSON base
    `{}` vs populated release → release keys taken, flagged W016 (real: icampaignservice openapi-config.json
    KPI_EP `{}` vs release `{"packet.logger": ""}` — base predates the key); base `[]` → base kept, flagged W016.
    Tool annotations are not re-read. Base comments equal to the active value are not copied; comment lines are
    byte-for-byte. Production Java class replaced by release (JAVA_CLASS_NAME_FROM_RELEASE) → in-file W017
    annotation naming the production class (real: fsmapp.properties executor.class BaseRuleExecutor →
    EmbeddedRuleExecutor).
12. **Whitespace-only differences are ignored (2026-09-18)**: if base and release are identical once all whitespace
    is removed (every mapped base must qualify), the release file is copied byte-for-byte — no merge rewrite,
    no report rows (`CMT-MRG-I003`, log only). Note: this also treats `a b` vs `ab` as equal (accepted literal rule).
13. **KV fidelity (2026-09-18)**: a file merged with itself must come out unchanged (harness: identity merge of
    all real KV files — 145/253 before these fixes → 177/253 after; the rest are Telstra audit files with interleaved
    indexed groups (F-020g) plus by-design DUPLICATE_KEY collapse / K-20 trailing spaces). A section repeated in one
    file keeps both blocks in place (decision 1a). `.sh` files are deployed from release, never KV-merged (2a);
    audit mode compares `.sh` as text (agreed 2026-09-18).
14. **Audit filter & backups (2026-09-18)**: `!name` excludes a file or a directory of that name; `+path` never
    switches the filter to include-only; a glob with `/` matches the relative path. Backup = marker
    (bkp/bak/backup/orig/org/old/save + any text, or a 6/8/14-digit date) after the full name or before the
    extension, and ONLY when the original exists next to it. `_v2` is not a backup (can be a real version).
15. **Audit text/XML & SSTP (2026-09-18)**: text/XML compared with all whitespace removed (indentation-only
    differences match, CMT-AUD-I001). SSTP parser never parsed any block before F-030 (`^` in the header regex used
    with `.match(text, pos)`), so every .sstp compare was a silent match; fixed, plus a text fallback when a node
    yields no blocks (CMT-AUD-W010). Filters must include `sstp` to audit routing rules (added to sample/Telstra filter).
8. **Critical entries are traceable**: every critical report entry is also logged with a `CMT-*` code; an
   unparseable JSON/XML input is critical (`INVALID_JSON` / `INVALID_XML`, exit 1), never silently dropped.

---

## Audit memory (confirmed 2026-09-18)

1. **Feedback history is appended in place (option A).** `~/.configmergetool/feedback_history.json` keeps its
   format and full content (filtered-file paths included); each run splices its entry before the closing
   `]}` without loading the file. Bytes equal a full `json.dump(indent=2)`. Any other layout falls back to
   load-and-rewrite. Rejected: storing counts only (B), capping to last N runs (C).
2. **Audit HTML pages are never joined in memory.** Rendered as head + AUDIT_DATA JSON + tail, validated and
   written piecewise; output bytes unchanged. `_validate_html_parts` parses head + tail (the escaped JSON is
   opaque script text) and falls back to the full page if the JSON ever contains `</script`.
3. **Measure memory with `HOME` isolated.** Real audit runs append to the user's history file.

---

## Working rules

- **Data first, no assumptions (2026-09-15).** Before proposing a plan, share a snapshot with actual data,
  the issue details, how the fix is planned, and the possible end result computed on real data. On any doubt,
  stop and consult the user.
- **Customer data stays out of git.** Real site inputs (e.g. `Telstra-RSC`, `Telstra-RSC1`) are never committed
  or copied into tests; tests use synthetic fixtures.
