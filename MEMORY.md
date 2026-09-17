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
7. The same key twice in one section on a node (**duplicate in section**) shows both values with line
   numbers, is flagged, and counts as a mismatch — **including identical duplicates** (re-confirmed with full
   Telstra run data: e.g. 20 repeated keys in single-node `iMASCodes_en_US.properties`, `txnwriter.alias=default`
   twice; run total 1,933 vs 1,898 in v2.0.1). A repeated section header (e.g. `[Profile Engine]` twice) merges
   into one section, so its keys become duplicates.
8. **Empty sections** are listed; a node lacking the header is flagged "section absent". Keys before the first
   header form the "(no section)" block with its own check.

9. **Section header rule** stays the merge parser's: `[Name]` optionally followed by an inline `# comment`.
   Known gap: report download (`reconstructKV`) and `patch.py` only accept a bare `[Name]` line — 0 such
   headers in the Telstra RSC data (156 KV files), left as-is.
10. **"Show differences only"** keeps a section header visible when any row under it is visible OR the section
    is absent on a node that has the file (base included). Matched headers still hide; empty sections stay
    visible when the filter is off.

Derived counting: missing = no entry (active or commented); differ = both active and values differ, or the
node has a duplicate; match = otherwise (incl. commented); extra = key not in base.

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
8. **Critical entries are traceable**: every critical report entry is also logged with a `CMT-*` code; an
   unparseable JSON/XML input is critical (`INVALID_JSON` / `INVALID_XML`, exit 1), never silently dropped.

---

## Working rules

- **Data first, no assumptions (2026-09-15).** Before proposing a plan, share a snapshot with actual data,
  the issue details, how the fix is planned, and the possible end result computed on real data. On any doubt,
  stop and consult the user.
- **Customer data stays out of git.** Real site inputs (e.g. `Telstra-RSC`, `Telstra-RSC1`) are never committed
  or copied into tests; tests use synthetic fixtures.
