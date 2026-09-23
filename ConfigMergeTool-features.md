# ConfigMergeTool — Features Reference

> Developer reference. Describes every feature implemented in the current codebase (v2.1.0).
> Update this file whenever features are added, changed, or removed.

---

## Table of Contents
1. [Architecture](#architecture)
2. [CLI Arguments](#cli-arguments)
3. [File Format Support](#file-format-support)
4. [Feature Details — Merge Mode](#feature-details--merge-mode)
   - [File Discovery & Matching](#file-discovery--matching)
   - [Multi-Base Execution](#multi-base-execution)
   - [Key-Value Processing](#key-value-processing)
   - [XML Processing](#xml-processing)
   - [JSON Processing](#json-processing)
   - [Logrotate Processing](#logrotate-processing)
   - [SSTP Processing (Merge Mode)](#sstp-processing-merge-mode)
   - [Generic Processing](#generic-processing)
   - [Excel Report](#excel-report)
   - [Merge HTML Report](#merge-html-report)
   - [Run Output Structure (Merge)](#run-output-structure-merge)
   - [Logging](#logging)
5. [Feature Details — Audit Mode](#feature-details--audit-mode)
   - [Audit Engine](#audit-engine)
   - [Backup File Detection](#backup-file-detection)
   - [File Filter](#file-filter)
   - [Audit HTML Report](#audit-html-report)
   - [Audit Report UX](#audit-report-ux)
   - [Audit Intelligence](#audit-intelligence)
   - [SSTP Semantic Diff](#sstp-semantic-diff)
   - [Audit Patcher](#audit-patcher)
   - [Extensibility Architecture](#extensibility-architecture)
   - [Run Output Structure (Audit)](#run-output-structure-audit)
6. [Packaging & Distribution](#packaging--distribution)
7. [Report Entry Types](#report-entry-types)
8. [Changelog](#changelog)

---

## Architecture

```
ConfigMergeTool/
├── ConfigMergeTool.py          — Backward-compat shim: calls configmerge.cli.main()
├── pyproject.toml              — Build system; "configmergetool" entry point; optional extras
├── requirements.txt            — Core runtime deps (openpyxl)
├── requirements-dev.txt        — Dev/test deps (pytest, build, twine, chardet)
└── configmerge/
    ├── __init__.py             — Public API + __version__ = "2.1.0"
    ├── __main__.py             — Enables: python -m configmerge
    ├── cli.py                  — main() / _main() / parse_args() — pip entry point
    ├── models.py               — BaseDirConfig, RemoteConfig, MergeConfig, MergeResult,
    │                             ReportEntry, EntryType
    ├── logger.py               — setup_logging(), important() (thread-safe), log_structured()
    ├── utils.py                — open_text() (encoding-aware), file_sha256(), ensure_dir(),
    │                             safe_realpath(), file_md5(), copy_file()
    ├── matcher.py              — FileMatcher: file discovery, name matching, mapping resolution
    ├── engine.py               — MergeEngine: orchestrates one pass per base dir
    ├── processors/
    │   ├── __init__.py         — BaseProcessor ABC + PROCESSOR_REGISTRY dict
    │   ├── kv.py               — KVProcessor (.properties/.cfg/.ini/.conf/.sh)
    │   ├── xml_proc.py         — XMLProcessor (.xml/.xsd)
    │   ├── json_proc.py        — JSONProcessor (.json)
    │   ├── logrotate.py        — LogrotateProcessor (.logrotate)
    │   ├── sstp.py             — SstpProcessor (.sstp) — copy-only in merge mode
    │   └── generic.py          — GenericProcessor (all other extensions)
    ├── reporter/
    │   ├── excel.py            — write_excel(): 6-sheet .xlsx with freeze/filter/row heights
    │   └── html_reporter.py    — write_html(): self-contained HTML diff report
    ├── auditor/
    │   ├── __init__.py         — AuditEngine, AuditResult, AuditPatcher, FileFilter
    │   ├── engine.py           — AuditEngine: multi-node config drift detection
    │   ├── html_report.py      — write_audit_html(): interactive audit report (paginated)
    │   ├── patch.py            — AuditPatcher: apply audit patch JSON to source files
    │   ├── fetcher.py          — NodeFetcher ABC + LocalNodeFetcher
    │   ├── file_filter.py      — FileFilter: include/exclude rules from filter file
    │   ├── sstp_parser.py      — SstpParser: SSTP block parser + diff categoriser
    │   └── feedback.py         — Cross-run feedback accumulator (load_history, print_summary)
    └── workflows/
        ├── __init__.py         — exports WorkflowBase
        ├── base.py             — WorkflowBase ABC (run, deliver)
        ├── remote.py           — SSHNodeFetcher stub (Phase 11)
        └── email_workflow.py   — EmailAuditWorkflow stub (Phase 12)
```

**Public API usage:**
```python
from configmerge import MergeEngine, MergeConfig, BaseDirConfig

# Single base
config  = MergeConfig(base_dir="base", release_dirs=["release"], output_dir="output")
results = MergeEngine(config).run()   # returns List[MergeResult]

# Multi-base
config  = MergeConfig(
    release_dirs=["release"], output_dir="output",
    base_configs=[
        BaseDirConfig(base_dir="base/node1", name="prod-eu", mapping_file="map1.txt"),
        BaseDirConfig(base_dir="base/node2", name="prod-us"),
    ],
)
results = MergeEngine(config).run()

# Audit mode
from configmerge.auditor import AuditEngine
nodes  = [BaseDirConfig(base_dir="APP-01", name="App01"),
          BaseDirConfig(base_dir="APP-02", name="App02")]
result = AuditEngine(nodes, report_dir="reports").run()
```

---

## CLI Arguments

### Merge Mode

| Argument | Required | Description |
|---|---|---|
| `--base-dir` | Yes (or `--base-config-file`) | Single base (production) config directory |
| `--release-dirs` | Yes | One or more release config directories (searched in order) |
| `--output-dir` | Yes | Destination for merged output files |
| `--base-config-file` | No | JSON file defining multiple base directories (multi-base mode) |
| `--mapping-file` | No | Maps base filenames to differently-named release files |
| `--copy-baseonlyconfigfile` | No | List of base files to copy as-is without merge |
| `--exclude-params-in-baseonlyconfig` | No | Suppress base-only parameter insertion into output |
| `--dry-run` | No | Skip writing output files; still generates full report |
| `--verbose` | No | Print INFO-level log events to console |

### Audit Mode

| Argument | Required | Description |
|---|---|---|
| `--audit-config-file` | Yes | JSON array of node directories to compare |
| `--filter-file` | No | Filter file controlling which file types/names are audited |
| `--mapping-file` | No | `NODE/path=NODE/path` file or directory pairs; the left file is compared in the right path's row (A-17) |
| `--quiet` | No | Suppress MATCH lines; print only DIFF/WARN/ERROR/SUMMARY |
| `--report-dir` | No | Directory for audit report output (default: `reports/`) |

### Apply-Patch Mode

| Argument | Required | Description |
|---|---|---|
| `--apply-audit-patch` | Yes | Path to patch JSON exported from audit report |
| `--output-dir` | Yes | Directory to write corrected config files |

### Other Flags

| Argument | Description |
|---|---|
| `--feedback-summary` | Print cross-run feedback history and exit |
| `--version` | Print version and exit |
| `--log-dir` | Directory for log files (default: `logs/`) |
| `--remote-audit` | *(Coming Phase 11)* Fetch files via SSH |
| `--email-config` | *(Coming Phase 12)* Email-triggered audit mode |

**`--audit-config-file` JSON format:**
```json
[
  {
    "base_dir": "/opt/app/config",
    "name": "APP-01",
    "no_skip_files": ["fsmapp.properties_couchbase"]
  },
  {
    "base_dir": "/opt/app/config",
    "name": "APP-02",
    "remote": {
      "host": "10.0.0.2",
      "port": 22,
      "username": "admin",
      "key_file": "~/.ssh/id_rsa"
    }
  }
]
```

Fields: `base_dir` (required), `name`, `no_skip_files` (filenames exempt from backup skipping), `remote` (SSH config for Phase 11).

**`--base-config-file` JSON format:**
```json
[
  {
    "base_dir":       "base/node1",
    "name":           "prod-eu",
    "mapping_file":   "mappings/node1-mapping.txt",
    "copy_only_file": "mappings/node1-copy-only.txt"
  },
  { "base_dir": "base/node2", "name": "prod-us" }
]
```

---

## File Format Support

| Extension(s) | Processor | Merge Mode | Audit Mode |
|---|---|---|---|
| `.properties`, `.cfg`, `.ini`, `.conf`, `.sh`, `.acl` | KVProcessor | Key-level per section; base wins | Semantic KV comparison |
| `.xml`, `.xsd` | XMLProcessor | Element-level; base wins | Normalised text comparison |
| `.json` | JSONProcessor | Deep recursive merge; base wins | Deep JSON comparison |
| `.logrotate` | LogrotateProcessor | Whole base file copied | Text comparison |
| `.sstp` | SstpProcessor | Copy-only (release wins) | Semantic block diff |
| All others | GenericProcessor | Copied as-is from release | Text comparison |

---

## Feature Details — Merge Mode

### File Discovery & Matching

| ID | Feature | Behaviour |
|---|---|---|
| F-01 | Recursive walk | Both `base_dir` and all `release_dirs` are walked recursively |
| F-02 | Relative-path match | Release file matched to base file first by identical relative path |
| F-03 | Filename-only fallback | If relative paths differ, matched by filename alone — only when that filename is unique in base |
| F-04 | Ambiguity detection | Same filename in multiple base locations (no mapping, no same-path match) → file skipped, `AMBIGUOUS_MATCH_SKIPPED` reported, `[CMT-MRG-E002]` logged, exit 1. Resolve with `--mapping-file` |
| F-05 | Explicit mapping | `--mapping-file` maps base paths to differently-named release paths |
| F-06 | Many-to-One mapping | Multiple base paths may map to one release path — KV, XML and JSON: first base listed in the mapping file wins, later bases only add what earlier bases lack (`CMT-MRG-I001`) |
| F-14 | One-to-Many mapping | One base path may map to several release paths; each release file is merged from it (`CMT-MRG-I002`) |
| F-15 | Unique filename fallback output | A unique filename-only match writes the merged file at the base file's relative path (confirmed intended 2026-09-17) |
| F-07 | Copy-only bypass | Files in `--copy-baseonlyconfigfile` copied from base without processing |
| F-08 | Path traversal guard | Paths canonicalised with `safe_realpath()`; must remain within `base_dir` |
| F-09 | Output dir cleanup | Output dir removed and recreated before each run (skipped in `--dry-run`) |
| F-12 | Output dir overlap guard | `--output-dir` equal to, containing, or inside any base/release dir → run refused before anything is deleted, `[CMT-MRG-E010]`, exit 2 (also in `--dry-run`) |
| F-10 | Release-only files | Release files with no base counterpart are copied to output as-is and listed in the ReleaseOnlyFiles sheet (`[CMT-MRG-W001]`) |
| F-13 | Hidden files ignored | Files whose name starts with `.` (e.g. `.DS_Store`) are ignored in base and release, like hidden directories |
| F-11 | Flexible path format | Mapping and copy-only files accept full working-directory paths, base-dir-name-prefixed paths, or bare paths |

---

### Multi-Base Execution

| ID | Feature | Behaviour |
|---|---|---|
| M-01 | Independent pass per base | Each `BaseDirConfig` runs a completely independent `FileMatcher` + processor pass |
| M-02 | Per-base output subdirs | Multi-base: output goes to `output/<base_name>/`; single-base: directly to `output/` |
| M-03 | Per-base Excel report | Each base produces its own Excel file |
| M-04 | Combined HTML report | All bases appear in one HTML report; sidebar groups by base name |
| M-05 | Per-base mapping & copy-only | Each `BaseDirConfig` can specify its own `mapping_file` and `copy_only_file` |
| M-06 | Single run directory | All run artifacts land in `reports/run_YYYYMMDD_HHMMSS/` |

---

### Key-Value Processing

Handles: `.properties`, `.cfg`, `.ini`, `.conf`, `.sh`, `.acl`

| ID | Feature | Behaviour |
|---|---|---|
| K-01 | Base value wins | For keys in both files (both active), base value used in output |
| K-02 | Line fidelity (pass-through) | Unchanged parameters emitted using original raw line — indentation, delimiter spacing, and inline comments all preserved |
| K-03 | Line fidelity (changed value) | Changed parameters use raw line as template: prefix up to delimiter preserved, new value substituted, trailing inline comment (`# …`) retained |
| K-04 | Comment source preference | Release comments always preferred; base comments used only when release has none |
| K-05 | Commented-out key handling | Release commented key + active base value → uncommented and set to base value (`UNCOMMENT_REPLACE`) |
| K-06 | Base-only insertion | Keys in base absent from release inserted into output (`BASE_ONLY_PARAMETER_ADDED`) |
| K-07 | Release-only preservation | Keys in release absent from base kept in output (`RELEASE_ONLY_PARAMETER_ADDED`) |
| K-08 | Exclude flag | `--exclude-params-in-baseonlyconfig` suppresses K-06 |
| K-09 | Empty base override | Base value blank → release value forced blank (`EMPTY_BASE_OVERRIDE`) |
| K-10 | Indexed group handling | `prefix.N.subkey` groups matched by `prefix.N.name` when every group has a unique name, else by index; base groups retained, release-only groups appended with renumbered indices; `prefix.count` kept from base and flagged `GROUP_COUNT_MISMATCH` when it differs from the merged total |
| K-11 | Comma-list group header | Group header params whose value is a comma-separated name/class list (e.g. `schedule.registry`) are merged as a union: base items in order, then release-only items (`COMMA_VALUE_UNION`) |
| K-12 | Active duplicate detection | Multiple active occurrences of `section\|key` in release → `DUPLICATE_KEY` |
| K-13 | Shadow section handling | Base `#[SectionName]` merged with release active `[SectionName]`; all output entries remain commented |
| K-14 | Pre-annotation preservation | `#key=old` before active `key=new` in release emitted verbatim before merged active entry |
| K-15 | Post-annotation preservation | `#key=alt` after active `key=val` in release emitted verbatim after active entry |
| K-16 | Section interleaving | Base-only sections inserted before their successor release section, not appended at end |
| K-17 | Section header fidelity | Original section header line (`[Application]  # comment`) stored and emitted verbatim — inline comments on headers preserved |
| K-18 | Section preamble preservation | Comments appearing before a section header in the release (or base if release has none) emitted verbatim before the header line |
| K-19 | Section trailing preservation | Unrecognised lines / comments after the last KV entry of a section (e.g. comma-delimited data) emitted verbatim after all section entries |
| K-20 | Trailing-whitespace strip | Trailing spaces and tabs after a parameter value are removed from the output line (both pass-through and changed-value paths) |
| K-21 | Trailing blank line preservation | If the release file ends with a blank line, the merged output ends with one blank line too — prevents spurious `diff` output |
| K-22 | Java FQCN from release | When both base and release values are Java fully-qualified class names (e.g. `com.example.pkg.ClassName`) and they differ, the release value is used and flagged as `JAVA_CLASS_NAME_FROM_RELEASE` for reviewer attention |
| K-23 | API version upgrade | When base and release values look like different versions of the same third-party artifact (e.g. `log4j-1.2.17.jar` vs `log4j2-2.17.1.jar`), the release (newer) value is used (`API_VERSION_UPGRADED`) |
| K-24 | Multi-release-dir deduplication | If the same relative path exists in multiple release dirs, prefer the one whose directory name matches the base dir name; first otherwise; logs `WARNING` |
| K-25 | Filename-only fallback disambiguation | When multiple base files share the same filename, prefer the one in the same directory as the release file; use first with `WARNING` if no directory match |

---

### XML Processing

| ID | Feature | Behaviour |
|---|---|---|
| X-01 | Element-level replacement | Base element (matched by tag + `name` attribute) replaces release element verbatim |
| X-02 | Namespace preservation | Release namespace declarations restored; no `ns0:`, `ns1:` injection |
| X-03 | Hyphenated namespace support | Tag/attribute regex uses `[\w-]+:` to match hyphenated prefixes |
| X-04 | Empty-base override | Base element empty → release element forced empty (`EMPTY_BASE_OVERRIDE_XML`) |
| X-05 | Base-only element insertion | Elements in base absent from release inserted into output |
| X-06 | Release-only preservation | Elements only in release kept in output |
| X-07 | Duplicate detection | Duplicate tag+name in base → `DUPLICATE_KEY` |
| X-08 | Encoding-aware read | `open_text()` tries utf-8-sig → chardet → latin-1 fallback; ISO-8859 files handled |
| X-09 | Garbage-before-declaration strip | Content before `<?xml` removed before parsing |
| X-10 | Safe parse | XML parse errors produce structured log entries; file skipped without crash |
| X-11 | Comment capture | XML comments preceding an element stored and associated for the HTML report |
| X-12 | Multi-base warning | `len(base_files) > 1` emits warning — multi-base XML not fully supported |
| X-13 | Java FQCN from release | When both base and release element text are Java FQCNs and differ, the release value is kept and flagged as `JAVA_CLASS_NAME_FROM_RELEASE` |

---

### JSON Processing

| ID | Feature | Behaviour |
|---|---|---|
| J-01 | Deep recursive merge | `merge(base, release)` recurses into nested objects; base values overwrite release at any depth |
| J-02 | Release-only preservation | Keys only in release at any depth retained |
| J-03 | Empty-base override | Base value `""` → release forced `""` (`JSON_EMPTY_BASE_OVERRIDE`) |
| J-04 | Duplicate key detection | Custom object-pairs hook detects duplicate keys; last wins |
| J-05 | Input validation | Every base and the release file validated before merge; invalid/empty → `INVALID_JSON` (critical, exit 1), file skipped |
| J-06 | Output validation | Merged JSON re-parsed; invalid → discarded + `INVALID_OUTPUT_JSON` |
| J-07 | Indent preservation | Original indent style detected from the release file (tab or 2/4/8 spaces); output uses the same style (not forced to 2 spaces) |
| J-08 | Encoding-aware read | `open_text()` tries utf-8-sig → chardet → latin-1 fallback |
| J-09 | Multi-base warning | `len(base_files) > 1` emits warning — multi-base JSON not fully supported |
| J-10 | Java FQCN from release | When both base and release string values are Java FQCNs and differ, the release value is kept and flagged as `JAVA_CLASS_NAME_FROM_RELEASE` |
| J-11 | Primitive array inline format | After serialisation, arrays containing only primitive values (strings, numbers, booleans, null) are collapsed back to a single line — matching the inline style used in the source files (e.g. `["oauth2"]`) |

---

### Logrotate Processing

| ID | Feature | Behaviour |
|---|---|---|
| L-01 | Whole-file replacement | Entire base logrotate file written to output verbatim |
| L-02 | Empty-base override | Base file blank → output empty (`LOGROTATE_EMPTY_BASE_OVERRIDE`) |
| L-03 | Encoding-aware read | `open_text()` with latin-1 fallback |

---

### SSTP Processing (Merge Mode)

Handles: `.sstp` (Roamware Smart-STP routing rule scripts)

| ID | Feature | Behaviour |
|---|---|---|
| S-01 | Copy-only | Release file is always authoritative; copied as-is to output |
| S-02 | No line merge | Auto-generated routing rules are never hand-merged |
| S-03 | Registered | `.sstp` registered in `PROCESSOR_REGISTRY` via `@register('.sstp')` decorator |
| S-04 | Semantic diff in audit | Full block-level semantic comparison in audit mode (see [SSTP Semantic Diff](#sstp-semantic-diff)) |

---

### Generic Processing

| ID | Feature | Behaviour |
|---|---|---|
| G-01 | Copy from release | File copied as-is from release directory |
| G-02 | No merge | No key-level or element-level processing |
| G-03 | Logged | `[GENERIC]` log entry written |

---

### Excel Report

Generated per base directory. Filename: `merge_report_<base_name>.xlsx`

| Sheet | Columns | Colour coding |
|---|---|---|
| **MergeChanges** | File, MergeCategory, ParameterName, ReleaseValue, BaseValue, Detail | Red = errors; Yellow = base-only; Orange = release-only |
| **BaseOnlyFiles** | FilePath | — |
| **ReleaseOnlyFiles** | FilePath | — |
| **FileMappings** | BaseConfigFileName, ReleaseConfigFileName | — |
| **ExcludedBaseOnlyParams** | File, Parameter, BaseValue | — |
| **BaseConfigAsIs** | FilePath | — |

**Phase 6 usability improvements:**
- Header row frozen (`freeze_panes = "A2"`) — scrolling keeps column headers visible
- Column auto-filter drop-downs on all sheets
- Row heights auto-adjusted for multi-line cell values (15px per line)

---

### Merge HTML Report

Single self-contained file: `merge_diff.html`

- Fixed top bar: run metadata (base dir, release dir, output dir, timestamp)
- Summary bar: total counts per change type
- Left sidebar: collapsible file tree + search box + click-to-navigate
- Right panel: toolbar + one collapsible section per processed file
- Fixed bottom legend bar: always visible, hover for tooltip explanations
- **"Show Full Config"** toggle: changes-only view ↔ full file diff (release vs output)
- **"3-Way Diff"**: base | release | merged output in three columns
- Pure vanilla JS; no external dependencies

---

### Run Output Structure (Merge)

```
reports/
└── run_YYYYMMDD_HHMMSS/
    ├── log_merge_config.log        ← full DEBUG log
    ├── merge_diff.html             ← combined HTML (all bases)
    ├── merge_report_<base1>.xlsx
    └── merge_report_<base2>.xlsx
```

---

### Logging

| ID | Feature | Behaviour |
|---|---|---|
| L-01 | File logging | All events at DEBUG level written to `log_merge_config.log` |
| L-02 | Console logging | `--verbose`: INFO+; default: WARNING+ and `important()` calls |
| L-03 | Thread-safe | `important()` routes through logging handler `emit()` (not `print()`) — safe under `ThreadPoolExecutor` |
| L-04 | Structured format | `[TYPE][ACTION][SEVERITY][FILE][ELEMENT] message` |
| L-05 | Unique logger name | Logger named `config-merge.YYYYMMDD.HHMMSS.mmm` per run |
| L-06 | Dry-run labelled | `[DRY-RUN] No files will be written` emitted at start |

---

## Feature Details — Audit Mode

Audit mode compares configuration files across multiple site nodes (base directories) to detect configuration drift without a release directory.

**Invocation:**
```bash
configmergetool --audit-config-file audit.json
configmergetool --audit-config-file audit.json --filter-file filters.txt --quiet
```

---

### Audit Engine

| ID | Feature | Behaviour |
|---|---|---|
| A-01 | Multi-node diff | Compares every file across all nodes; produces per-file, per-parameter diff results |
| A-02 | KV semantic comparison | Section-by-section comparison against the **base node** (first node in the audit config that has the file). A key is compared only within its section — the same key in two sections is two rows. A commented header `#[X]` is a comment: active keys after it belong to the enclosing real section. A commented-out key counts as present (commented). Header rule: `[Name]` optionally followed by `# comment` |
| A-03 | JSON comparison | Deep parse and per-key comparison |
| A-04 | Text/XML comparison | Whitespace-insensitive checksum decides match/mismatch; on mismatch every node is line-diffed (`difflib`, whitespace removed, blank lines skipped) against the first present node and each changed block becomes a read-only `AuditParam` (`__blk__<n>`, key `L<a>–L<b>`, `lines` per node); `mismatch_count` = blocks (A-18) |
| A-05 | Binary comparison | SHA-256 + file size; replaces legacy MD5 |
| A-05b | Absent-file mismatch (all types) | KV and JSON comparisons now set `mismatch_count ≥ 1` when the file is absent from any node, consistent with binary/text/SSTP behaviour |
| A-06 | Logical diff patterns | `logical_diff_patterns` regex list marks expected node-specific params as `is_logical_diff=True` — excluded from mismatch count |
| A-07 | Pre-run validation | Each `node.base_dir` checked before scanning; missing directories abort with clear error |
| A-08 | Progress indicator | After every 25 files (total > 50, non-quiet): `[PROGRESS] 50/205 files processed (24%)` |
| A-09 | Quiet mode | `--quiet`: MATCH lines suppressed on console; DIFF/WARN/ERROR/SUMMARY still printed |
| A-10 | Encoding-aware read | All file reads via `open_text()` — utf-8-sig → chardet → latin-1 |
| A-11 | Exit code | Exit 0 = no mismatches; exit 1 = mismatches found; exit 2 = configuration error |
| A-12 | Path traversal guard | `safe_realpath()` applied in `_scan_dir()`; symlinks escaping `base_dir` silently skipped |
| A-13 | CRLF output | All written files use `newline="\n"` — consistent across Windows/Linux |
| A-14 | KV section check | `AuditFile.sections`: per section — base node, base param count (None when base lacks the section), per-node `match` / `differ` / `missing` / `extra`, or section absent. Empty sections are listed; keys before the first header form the `DEFAULT` "(no section)" block |
| A-15 | KV duplicate in section | Same active key twice in one section on a node: `AuditParam.dup_values` / `lines` keep every value with its line number; row counts as a mismatch; warning `node: 'key' duplicated in [Section] (Lx, Ly)` |
| A-17 | Audit mapping | `auditor/mapping.py`: `--mapping-file` pairs resolved after scanning; row = right path, left node's file placed in it (one source → several instance rows); source row dropped unless another node shares it; dir lines expand, file lines win; `AuditFile.node_paths` / JS `nodePaths` carry each node's real path for downloads, patch export and XLSX; W011 when one side is missing |
| A-18 | Text block diff UI | Block rows render node lines in `<pre>`, no Use-for-all/Override/+Add; side-by-side view numbered with block lines highlighted; "Show" scrolls to them; W012 above 500 blocks |
| A-16 | KV merged ordering | Sections and keys follow the base node's file; sections/keys it lacks are inserted after their predecessor in the file that has them — no repeated section blocks |

---

### Backup File Detection

| ID | Feature | Behaviour |
|---|---|---|
| B-01 | Auto-detection | Files matching backup suffix patterns are skipped when their canonical stem exists in the same directory |
| B-02 | Patterns detected | `_bkp`, `_bkp_*`, `_backup`, `_orig`, `_org`, `_old`, `.bak`, `_DDMMYYYY`, `_YYYYMMDD`, `_DDMMYY`, `_save` (case-insensitive) |
| B-03 | Stem matching | Only skipped when `GTPProxy.cfg` exists alongside `GTPProxy.cfg_bkp_27072024` — never skips orphaned backup-named files |
| B-04 | Whitelist | `"no_skip_files": ["fsmapp.properties_couchbase"]` in audit config JSON exempts specific filenames |
| B-05 | Feedback output | `<run_dir>/feedback/skipped_backups.json` — full list for review |
| B-06 | Console | `[BACKUP SKIP] 3 backup file(s) skipped — path/to/skipped_backups.json` |

---

### File Filter

Activated with `--filter-file <path>`.

| ID | Feature | Behaviour |
|---|---|---|
| FF-01 | Binary archive exclusion | `.tar`, `.gz`, `.rpm`, `.zip`, `.jar`, `.war`, `.ear`, `.jks`, `.p12`, `.pem`, etc. always excluded even without a filter file |
| FF-02 | Suffix include | Line `cfg` — include all `.cfg` files |
| FF-03 | Named include | Line `conf::sysctl.conf,sctp.conf` — include only those named files with `.conf` extension |
| FF-04 | Directory include | Line `html::runtime,test` — include `.html` only in dirs named `runtime` or `test` |
| FF-05 | Explicit exclude | Line `!nohup.out` — always exclude this filename |
| FF-06 | Glob exclude | Line `!*.tmp` — glob pattern excludes |
| FF-07 | Pass-through mode | No filter file → only binary archives excluded; everything else compared |
| FF-08 | Feedback output | `<run_dir>/feedback/filtered_files.json` — list of excluded files with reason |
| FF-09 | No-extension include | Line `noext` — include files with no extension (e.g. `Makefile`, `Dockerfile`); `_normalise_suffix("noext")` returns `""` which is a valid include rule |
| FF-10 | Directory-path include | Line `config/routing` (contains `/`) — include all files anywhere under that subtree relative to node `base_dir` |
| FF-11 | Glob filename include | Line `GTPProxy*` or `*.jar.*` (contains `*`/`?`/`[`) — include basenames matching the glob pattern |
| FF-12 | Directory-path exclude | Line `!logs/archive` (leading `!` + contains `/`) — skip all files under this subtree |
| FF-13 | Force-include override | Line `+config/security/certs/active` (leading `+`) — include this path even when its parent directory is excluded; evaluated in phase 1, before all other rules |
| FF-14 | Rule evaluation order | Phase 1: force-include; Phase 2: explicit excludes (name/glob/dir); Phase 3: include rules; Phase 4: binary exclusions; Phase 5: default pass-through or skip |
| FF-15 | Sample filter file | `sample-filter.txt` in the project root — demonstrates all 10 rule types with inline comments and a real-world example |

---

### Audit HTML Report

Output: `<run_dir>/audit_report.html` (or paginated part files for large runs)

| ID | Feature | Behaviour |
|---|---|---|
| R-01 | Self-contained | Full CSS + JS embedded; no internet connection required |
| R-02 | Interactive sidebar | Recursive directory tree with per-directory diff badges; click to navigate |
| R-03 | File search | Search box in sidebar filters file list as you type; shows match count; Enter jumps to first match; Escape clears; Ctrl+K focuses from anywhere |
| R-04 | Parameter table | One row per parameter; per-node value columns; full page width. KV: one header row per section showing the section check (base count; per node match · differ · missing · +extra, or section absent); duplicate cells list every value with its line and a "duplicate in section" tag |
| R-05 | Sticky key column | Parameter column stays visible on horizontal scroll (many-node runs) |
| R-06 | Horizontal scroll | `.table-wrap` scrolls horizontally; node columns visible on 16+ node runs |
| R-07 | Node chip visibility | When nodes > 4: chip buttons above table to hide/show individual node columns |
| R-08 | Column width scaling | Column width auto-scales: ≤4 nodes → 260px; 5-8 → 220px; 9-16 → 180px; >16 → 160px |
| R-09 | Pagination | Reports > 22 MB split into `audit_report_p01.html`, `p02.html`… with index page |
| R-10 | Script injection fix | `</script>` in file content escaped to `<\/script>` before embedding JSON |
| R-11 | Show diffs only | Toggle hides matched rows and collapses section dividers with no visible rows — except KV headers whose section is absent on a node; empty sections stay visible when the toggle is off; state persists across file navigation |
| R-12 | Show expected diffs | Toggle shows/hides logical-diff rows (purple) |
| R-13 | Per-node download | Reconstructed KV/JSON per node, excluding skipped compounds |
| R-14 | Export Patch | Downloads `audit_patch.json` with `changes` + `skipped` arrays |
| R-15 | Change Log panel | Tracks all pending corrections in real time |
| R-16 | Clear All | Change Log modal has "Clear All" button to revert all pending changes |
| R-17 | Binary rows | SHA-256 + file size displayed; no Use-for-all/Override buttons on binary rows |
| R-18 | Diff quick-list (sidebar) | Collapsible "Files with differences" list at top of sidebar; filename + mismatch count |
| R-19 | Diff quick-list (index) | Prominent red section above directory tree on index page; full path, type, diff count, part link |
| R-20 | Deep-link navigation | Index page file links use URL-encoded hash (`#<path>`); part pages open that file on load |
| R-21 | Auto sidebar diffs-only | Sidebar diffs-only filter auto-enables on page load when diff files < 50% of total |
| R-22 | Sticky toolbar layout | `body` uses flex column + `height:100vh`; `.layout` uses `flex:1;min-height:0` — toolbar stays visible regardless of part-nav or sub-stats bars |
| R-23 | Per-part stats | Sub-bar below summary shows this-part file/diff/mismatch counts; full-run totals also shown |
| R-24 | Instance-specific colouring | Parameters auto-detected as instance-specific (log paths, instance numbers) shown in teal |
| R-25 | Absent-file flagging | Files present on some nodes but absent on others: shown with MISSING badge in sidebar; FILE ABSENT cells in table |
| R-26 | Skipped files panel | Collapsible section lists backup-detected + filter-excluded files with path, reason, base dir, and "Copy rule" clipboard button |
| R-27 | Report errors panel | Collapsible section at bottom lists any files that failed to process with error message |
| R-28 | HTML sanity check | `_validate_html()` called before writing each output file; warns to stderr if DOCTYPE/script balance/parse issues found |
| R-29 | Full-width tables | Param tables no longer double-wrapped; XML/text raw content uncapped (no 500px max-height) |
| R-30 | Absent vs diff distinction | `mismatch_count` counts content differences only; `absent_count` counts nodes where file is missing; displayed separately: `(diff)`, `(absent/missing)`, or `(diff / absent/missing)` |
| R-31 | Absent-only match banner | Files present on some nodes with identical content show an orange "FILE ABSENT ON N NODES" banner rather than a green match banner |
| R-32 | 8-sheet XLSX auto-generated | `audit_diffs.xlsx` written at the start of every run: Summary, Issues, Parameter Diffs, Checksum Check, Absent Files, Node Status, Skipped Backups, Filtered Files |
| R-33 | Parameter Diffs XLSX sheet | One row per differing parameter; one column per node; `—absent—` in orange fill for nodes missing the file; header row frozen |
| R-34 | Checksum Check XLSX sheet | Files where raw SHA-256 bytes differ across nodes despite `mismatch_count == 0` (encoding/CRLF differences); yellow fill |
| R-35 | Absent Files XLSX sheet | Lists every file with `absent_count > 0`; shows which nodes are missing it |
| R-36 | Node Status XLSX sheet | All audited files with a ✓/✗ column per node indicating presence |
| R-37 | Download XLSX button | Static `<a href="audit_diffs.xlsx" download>` link replaces old client-side CSV export |
| R-38 | Section-level corrections | Section divider rows in the param table have "Skip section" / "Unskip section" / "Add from NodeX" buttons; operate on all params within the section at once |
| R-39 | Part indicators | Multi-part reports show a per-part badge beside each Part# link: diff count (red), absent count (orange), or ✓ (green) |
| R-40 | Sticky table headers | `<thead>` sticks to top on vertical scroll; achieved by moving `overflow-x:auto` from `.table-wrap` to `.main` (single scroll container) |
| R-41 | Node name tooltip | Node column headers show only the short name; full `base_dir` path shown as a `title=""` tooltip on hover |
| R-42 | Index page search | Search box on the index page (`audit_report.html`) filters the directory tree and diff quick-list in real time |
| R-43 | Index diffs-only sticky | "Show diffs only" button on the index page remains visible (sticky toolbar) when scrolling through large directory trees |

---

### Audit Report UX

| ID | Feature | Behaviour |
|---|---|---|
| U-01 | Skip button | Mismatch rows have `✗ Skip` button; skipped rows turn grey, italic `[Skipped]` label |
| U-02 | Unskip | Skipped rows show `↺ Unskip` button to restore |
| U-03 | Skip state in patch | `exportPatch()` includes `"skipped": [{file, compound}]` array |
| U-04 | Skip excluded from download | Skipped compounds excluded from per-node KV/JSON reconstruction |
| U-05 | Next Mismatch | `▶ Next` button in toolbar navigates to next mismatch across all files |
| U-06 | Prev Mismatch | `◀ Prev` button navigates to previous mismatch |
| U-07 | Mismatch counter | `Mismatch 7 / 37` counter in toolbar; updates on skip/unskip |
| U-08 | Cross-file navigation | Automatically switches to correct file and scrolls to target row |
| U-09 | Pulse highlight | Navigated-to row receives 0.8s CSS pulse animation |
| U-10 | Resizable columns | Drag handle on column headers resizes width; persisted to `localStorage` |
| U-11 | Column width restore | Saved column widths restored on page reload (keyed by file + column index) |
| U-12 | Diffs-only persists | "Show differences only" toggle state preserved when navigating with Prev/Next across files |
| U-13 | Index diffs filter | "Show diffs only" button on index page collapses all-match directories and hides matched file rows |
| U-14 | Dir auto-expand/collapse | Sidebar directories with diffs auto-expand on load; all-match directories auto-collapse |
| U-15 | Copy rule (skipped files) | Each skipped file row has a "📋 Copy rule" button; copies a `no_skip_files` or `include` JSON snippet to clipboard |
| U-16 | Global column width control | Toolbar **−/+** buttons resize all node columns simultaneously; `_colWidth` state persisted in `localStorage['cm_col_width']`; per-column drag still available for fine-tuning |
| U-17 | Value text wrap at N chars | Toolbar number input sets `--val-wrap` CSS variable (`max-width: Nch` on `.val-display`); default 80 ch; **∞** button removes limit; setting persisted in `localStorage['cm_val_wrap']` |
| U-18 | Sticky diffs-only on index | "Show diffs only" control on the index page is part of a sticky top toolbar; remains visible when scrolling long directory trees |
| U-19 | Index page search | Search input on index page filters both the directory tree and diff quick-list as the user types |
| U-20 | Section skip/unskip | Section divider row has "✗ Skip section" button; skips all parameters in that section at once; divider shows "↺ Unskip section" to restore |
| U-21 | Add section from node | "＋ Add from NodeX" dropdown on section dividers; copies the full section from the selected node to all others in the pending change set |
| U-22 | File search with keyboard navigation | Sidebar search input (Ctrl+K) filters files as you type; displays match count badge (green = N matches, red = no match); pressing Enter navigates to the first matched file; Escape clears the search |
| U-23 | State persistence across refresh | All pending changes, skipped state, change log, and local output dir saved to `localStorage` on every mutation; automatically restored on page reload — HTML state survives browser refresh |
| U-24 | Save All Changes button | Header "💾 Save All" button downloads corrected config for every node with pending changes; prompts for output directory if none is configured |
| U-25 | Navigation guard | Navigating away from a file with unsaved changes shows a modal prompt — "Save & Continue" (default/Enter), "Continue Without Saving", or "Cancel" |
| U-26 | Output directory prompt | If no `output_dir` is configured and user triggers a save, a prompt modal asks for the path; remembered for the session via `localStorage` |

---

### Audit Intelligence

| ID | Feature | Behaviour |
|---|---|---|
| I-01 | Logical diff summary | All `is_logical_diff=True` parameters written to `feedback/logical_diff_summary.json` |
| I-02 | Logical diff console | `[LOGICAL DIFFS] 12 parameters skipped — see feedback/logical_diff_summary.json` |
| I-03 | Log name uniqueness | KV parameters whose key matches log/prefix patterns checked for shared values across nodes |
| I-04 | Duplicate log warning | Two or more nodes sharing the same log file prefix → `feedback/log_name_warnings.json` |
| I-05 | Log patterns matched | `log.file`, `log.prefix`, `kpi.stats.prefix`, `snmp.trap-file.prefix`, etc. (regex-based) |
| I-06 | Feedback accumulator | Every run appends a summary record to `~/.configmergetool/feedback_history.json` |
| I-07 | Feedback summary CLI | `configmergetool --feedback-summary` prints counts by category across all recorded runs |
| I-08 | Advisory only | Feedback history is never auto-read or auto-applied; engineer reviews manually |

---

### SSTP Semantic Diff

Handles: `.sstp` (Roamware Smart-STP routing rule scripts)

| ID | Feature | Behaviour |
|---|---|---|
| SS-01 | Block parsing | Top-level named blocks (`GCT (0x33) [...]`) parsed by depth-tracking `[`/`]` scanner |
| SS-02 | Comment stripping | `#` comments stripped before parsing |
| SS-03 | Body normalisation | `SET CDPA (A) AND SET CDPA (B)` collapsed to `SET CDPA (A,B)`; whitespace collapsed |
| SS-04 | Parameter extraction | `SRC`, `SPC`, `DIGITS`, `ROUTE`, `SPREAD` extracted per block for detailed diff display |
| SS-05 | VALUE_DIFF | Parameter values differ (SRC, SPC, different route targets) → red in HTML |
| SS-06 | ORDER_DIFF | Same route targets in different order, or DIGITS order differs → orange in HTML |
| SS-07 | STRUCT_EQUIV | Structurally equivalent after normalisation (e.g. multi-SET merge) → treated as logical diff (yellow) |
| SS-08 | MATCH | Blocks identical → no mismatch |
| SS-09 | Compound key | Block keyed as `BLOCK|NAME(params)|DIFF_CATEGORY` in AuditParam |
| SS-10 | Audit integration | `AuditEngine._compare_sstp()` dispatched from `_compare_file()` for `.sstp` extension |

---

### Audit Patcher

Activated with `--apply-audit-patch <patch.json> --output-dir <dir>`.

| ID | Feature | Behaviour |
|---|---|---|
| P-01 | JSON patch apply | Reads `audit_patch.json`; applies `changes` to source config files |
| P-02 | KV patching | Finds delimiter position in original line; replaces value; preserves trailing inline comment (`# …` or `; …`) |
| P-03 | JSON patching | Deep path substitution into original JSON; preserves file structure |
| P-04 | Corrections log | Writes `corrections.log` alongside patched files |
| P-05 | CRLF safe | Output written with `newline="\n"` |
| P-06 | Node name guard | A node name that is not a plain directory name (`..`, contains `/` or `\`) is skipped with `[CMT-PAT-E008]` — patch files cannot write outside `--output-dir` |
| P-07 | Exit codes | 0 = all changes written; 1 = some files skipped/failed (`CMT-PAT-E005`–`E009`); 2 = patch unreadable, missing fields, malformed change or no changes (`CMT-PAT-E001`–`E004`) |

---

### Extensibility Architecture

| ID | Feature | Behaviour |
|---|---|---|
| E-01 | NodeFetcher ABC | `fetch(node) -> str` + `cleanup()` — translates `BaseDirConfig` to a local path the engine can scan |
| E-02 | LocalNodeFetcher | Default: returns `node.local_path` (files already on disk) — zero overhead |
| E-03 | SSHNodeFetcher stub | Scaffold for Phase 11; raises `NotImplementedError`; checks `paramiko` import |
| E-04 | RemoteConfig | `host`, `port`, `username`, `key_file`, `password_env`, `remote_path`, `timeout_secs` |
| E-05 | BaseDirConfig.local_path | Set by fetcher after `fetch()`; engine uses `local_path` internally, `base_dir` for display |
| E-06 | Local path skipped | `__post_init__` skips `os.path.isdir()` check when `remote` is configured |
| E-07 | Credential safety | `password_env` pattern enforced; literal `"password"` key in audit config JSON rejected |
| E-08 | WorkflowBase ABC | `run() -> AuditResult` + `deliver(result, report_path)` — contract for all workflows |
| E-09 | EmailAuditWorkflow stub | Scaffold for Phase 12; documents IMAP/SMTP interface and zip attachment convention |

---

### Run Output Structure (Audit)

```
reports/                            ← report_dir (passed via CLI or default "reports")
└── audit_YYYYMMDD_HHMMSS/          ← one subdirectory per run
    ├── audit_report.html           ← index page (or single-file report for small runs)
    ├── audit_report_p01.html       ← part 1 (only when report > 22 MB)
    ├── audit_report_p02.html       ← part 2 (etc.)
    ├── audit_diffs.xlsx            ← 8-sheet Excel workbook (auto-generated every run)
    ├── audit.log                   ← full audit log
    └── feedback/
        ├── skipped_backups.json    ← backup files auto-detected and skipped
        ├── filtered_files.json     ← files excluded by --filter-file
        ├── logical_diff_summary.json   ← all logical-diff parameters
        └── log_name_warnings.json  ← duplicate log prefix warnings
```

Each run creates a new `audit_YYYYMMDD_HHMMSS/` subdirectory; previous runs are preserved.

`audit_diffs.xlsx` sheet summary:

| Sheet | Contents |
|---|---|
| Summary | Run metadata: timestamp, node count, file count, total diffs, total absent |
| Issues | All files with diffs or absent nodes; colour-coded by severity |
| Parameter Diffs | One row per differing parameter; one column per node; absent nodes in orange |
| Checksum Check | Files whose raw SHA-256 bytes differ despite matching parsed values (encoding/CRLF) |
| Absent Files | Files with `absent_count > 0`; which nodes are missing each file |
| Node Status | All audited files with ✓/✗ present/absent per node |
| Skipped Backups | Backup files auto-detected and skipped; filename, node, reason |
| Filtered Files | Files excluded by `--filter-file`; path, reason |

---

## Packaging & Distribution

| Feature | Detail |
|---|---|
| Package name | `configmergetool` |
| Version | `2.1.0` |
| Entry point | `configmergetool = "configmerge.cli:main"` |
| Module invocation | `python -m configmerge` |
| Legacy invocation | `python ConfigMergeTool.py` (backward compatible) |
| Core dependency | `openpyxl>=3.1` |
| Optional `[encoding]` | `chardet>=5.0` — auto-detect file encoding; falls back to latin-1 if not installed |
| Optional `[ssh]` | `paramiko>=3.0` — Phase 11 SSH remote node access |
| Optional `[email]` | `imapclient>=2.3` — Phase 12 email-triggered audit |
| Optional `[all]` | All optional extras |
| Build | `python -m build` → `dist/configmergetool-2.1.0-py3-none-any.whl` |
| Install | `pip install configmergetool-2.1.0-py3-none-any.whl` |
| Type hints | `py.typed` marker present (PEP 561) |
| Python | 3.9+ |

**Version management:** bump in `configmerge/__init__.py` AND `pyproject.toml`; tag with `git tag v2.0.0`.

---

## Report Entry Types

| Type | Severity | Description |
|---|---|---|
| `BASE_TO_RELEASE_REPLACED` | Normal | KV key: release value replaced by base value |
| `XML_BASE_TO_RELEASE_REPLACED` | Normal | XML element: release element replaced by base |
| `JSON_BASE_TO_RELEASE_REPLACED` | Normal | JSON key: release value replaced by base value |
| `LOGROTATE_BASE_TO_RELEASE_REPLACED` | Normal | Logrotate file replaced from base |
| `UNCOMMENT_REPLACE` | Normal | Commented-out KV key uncommented and set from base |
| `BASE_ONLY_PARAMETER_ADDED` | Yellow | Parameter only in base — inserted into output |
| `BASE_ONLY_FILE_COPIED` | Normal | File copied as-is from `--copy-baseonlyconfigfile` |
| `SSTP_RELEASE_COPIED` | Normal | `.sstp` release file copied as-is (auto-generated routing rules) |
| `RELEASE_ONLY_PARAMETER_ADDED` | Orange | Parameter only in release — kept as-is |
| `EXCLUDED_BASE_ONLY_PARAMETER` | Normal | Base-only parameter skipped due to `--exclude-params-in-baseonlyconfig` |
| `EMPTY_BASE_OVERRIDE` | **Red/ERROR** | KV: base value empty — release value forced empty; review required |
| `EMPTY_BASE_OVERRIDE_XML` | **Red/ERROR** | XML: base element empty — release element forced empty; review required |
| `JSON_EMPTY_BASE_OVERRIDE` | **Red/ERROR** | JSON: base value `""` — release value forced `""`; review required |
| `LOGROTATE_EMPTY_BASE_OVERRIDE` | **Red/ERROR** | Logrotate: base file blank — output forced empty; review required |
| `DUPLICATE_KEY` | **Red** | Duplicate active key in **release** file; last value used |
| `INVALID_JSON` | **Red** | Input file contains invalid JSON; file skipped |
| `INVALID_OUTPUT_JSON` | **Red** | Merged JSON failed re-validation; output discarded |
| `INVALID_XML` | **Red** | Base or release XML cannot be parsed; file skipped (exit 1, `[CMT-MRG-E007]`) |
| `FILE_MAPPING` | Normal | Explicit file mapping from `--mapping-file` applied |
| `NAMESPACE_ADAPTED` | Normal | XML namespace updated from release declarations |
| `INDEXED_GROUP_RENUMBERED` | Normal | Indexed group entries (e.g. `schedule.N.x`) renumbered |
| `INDEXED_GROUP_APPENDED` | Normal | Release-only indexed groups appended after base groups |
| `COMMA_VALUE_UNION` | Normal | Comma-separated group header value merged as union of base + release |
| `JAVA_CLASS_NAME_FROM_RELEASE` | **Review** | Both base and release values are Java FQCNs but differ; release value used — reviewer should verify the class is correct for this environment |
| `PROCESSOR_ERROR` | **Red/ERROR** | Processor encountered a fatal error for this file (exit 1, `[CMT-MRG-E001]`) |
| `REVIEW_COMMENTED_IN_BASE` | **Review** | KV parameter commented out in base, active in release: release value kept, base comment + in-file review annotation (`[CMT-MRG-W014]`) |
| `REVIEW_COMMENTED_SECTION_IN_BASE` | **Review** | KV section commented out in base, active in release: entries kept commented, in-file review annotation under header (`[CMT-MRG-W015]`) |
| `REVIEW_EMPTY_IN_BASE` | **Review** | JSON `{}` in base, populated in release: release keys taken; `[]` in base: base kept (`[CMT-MRG-W016]`) |
| `GROUP_COUNT_MISMATCH` | **Review** | KV `prefix.count` kept from base but differs from the merged indexed-group total (`[CMT-MRG-W013]`, highlighted, not critical) |
| `AMBIGUOUS_MATCH_SKIPPED` | **Red/ERROR** | Release file matched several base files by name only; skipped (exit 1, `[CMT-MRG-E002]`) |

---

## Changelog

| Date | Change |
|---|---|
| 2026-09-23 | Audit: `--mapping-file` honoured (A-17) — mapped files were reported absent (Helm charts `dra-SA` → `dra-SA-1`/`-2`); file and directory lines, W011 for one-sided pairs, E018 for unknown node prefix. Text/XML (yaml, tpl, …) differences listed as changed-line blocks instead of only a checksum (A-18, W012). STC Helm audit: 227 rows, 0 Staging-only leftovers, `Mapping.cfg` and per-file mapping give identical rows |
| 2026-09-18 | Audit: key repeated in a section — last value used and compared, warning W007 names it, no longer a mismatch (F-027); text/XML whitespace-only differences match, I001 (F-028); `sstp` added to sample filter (F-029); SSTP parser fixed — no block was ever parsed, so routing-rule drift was reported as a match; text fallback W010 when a node has no blocks (F-030). Real Telstra audits: 0 false matches / 0 false mismatches vs raw bytes |
| 2026-09-18 | Audit filter/backup (F-021..F-026): `+path` no longer switches the filter to include-only; `!name` also excludes a directory with that name; globs with `/` match the relative path; backup markers may be followed by any text (`_bkp200821`) or sit before the extension (`fsmapp_240226.properties`), `_YYYYMMDDHHmmss` detected; `_v2` is not a backup (readme corrected). Real: 122 more backups skipped (all with original present), nothing newly audited |
| 2026-09-18 | Audit: `.sh` shell scripts compared as text instead of KV (matches merge, where `.sh` is deployed from release) |
| 2026-09-18 | KV fidelity (F-020): no EMPTY_BASE_OVERRIDE when release is also empty (real runs now exit 0); keys commented in both files not reported as release-only; repeated section headers kept in place (paired by occurrence); no invented blank lines between sections; commented section headers keep their preceding lines; output ends exactly like release; comments not duplicated, comments of a collapsed duplicate key kept; `.sh` no longer KV-merged — release copy deployed |
| 2026-09-18 | Whitespace-only base/release pairs (identical once all whitespace is removed; every mapped base must qualify) are copied from release byte-for-byte (`CMT-MRG-I003`); merged XML keeps the release file's trailing newline (F-019). Real data: 19 files/node copied from release, 15 outputs change whitespace only, 72 spurious MergeChanges rows gone |
| 2026-09-17 | Processor fixes (S1 review): XML element blocks matched with balanced same-tag nesting and never inside `<!-- -->` comments (F-012/F-018); JSON inline-array formatting no longer alters string contents (F-013); KV lines split at the first `=`/`:` (F-014); JSON values compared type-strictly — `true` ≠ `1` (F-015) |
| 2026-09-17 | Review follow-up: production Java class replaced by release class → in-file `[CMT-MRG-W017]` annotation with the production value; base comments equal to the active value not copied; commented lines emitted byte-for-byte; JSON base `{}` now takes release keys (flagged), `[]` keeps base |
| 2026-09-17 | Comments as context: base comment lines copied next to their parameter (alternative values, commented-in-base params); `#key = value` recognised when the key is a real parameter; review annotations `[CMT-MRG-W014]` (param) / `[CMT-MRG-W015]` (section) written into output and never re-copied on later runs; JSON base `{}`/`[]` kept over populated release and flagged `[CMT-MRG-W016]` |
| 2026-09-17 | KV indexed groups matched by `name` subkey (index fallback); comma-list group headers merged as union (base items then release-only); base `prefix.count` kept but flagged `GROUP_COUNT_MISMATCH` when it differs from the merged total; XML named base-only elements inserted even when release has the same tag with other names (respects `--exclude-params-in-baseonlyconfig`) |
| 2026-09-18 | **v2.1.0** — audit section-by-section KV comparison, merge fidelity and QE fixes (F-001–F-030), audit memory reduction (M-1, M-2), binary filter guidance |
| 2026-09-18 | Audit: tool version stamped in `audit.log` (first line), in every report page header and as `<meta name="generator">` |
| 2026-09-18 | Audit report: KV section names shown exactly as written (`[CouchBase]`); the section row CSS no longer uppercases them (display only — data and patches always kept the original case) |
| 2026-09-18 | Audit memory: feedback history appended in place instead of load-and-rewrite (a 195 MB history cost +350 MB peak per audit); HTML report pages rendered/validated/written as pieces instead of one joined string. Telstra-RSC1 audits: peak RSS 748 → 308 MB (3 nodes/823 files) and 730 → 274 MB (2 nodes/745 files); outputs byte-identical |
| 2026-09-17 | Mapping: One-to-Many supported (F-14, warning `CMT-MRG-W006` retired); Many-to-One now merges every base for XML and JSON with the KV first-wins rule (F-06, `W011`/`W012` retired). Unparseable JSON/XML inputs are critical (`INVALID_JSON`/`INVALID_XML`, exit 1) instead of silently missing from output. Empty-base overrides logged with `CMT-MRG-E012`–`E014` |
| 2026-09-17 | QE fixes: release-only files copied to output (F-10); hidden files ignored (F-13); ambiguous filename matches skipped + exit 1 (F-04); `--output-dir` overlapping inputs refused (F-12); `.sstp` merge no longer fails with PROCESSOR_ERROR and processor failures now exit 1; patch node-name traversal blocked (P-06) and patch exit codes 0/1/2 (P-07); stable error identifiers `CMT-<AREA>-<E\|W\|I><nnn>` on every error/warning (`configmerge/errors.py`) |
| 2026-09-15 | A-02, A-14–A-16, R-04, R-11: Audit KV compared section by section against the base node — fixes the same parameter shown in two rows (missing above / missing below) and false "missing" for active keys after `#[X]` commented headers; section check on header rows; duplicate-in-section values with line numbers (HTML + Excel "Parameter Diffs") |
| 2026-04-10 | **v2.0.1 released** — patch release covering all KV, JSON, XML, and output-format fixes from 2026-04-09–10 |
| 2026-04-10 | J-11: Primitive array inline format — `_collapse_primitive_arrays()` post-processes `json.dumps` output; arrays with no nested objects/arrays collapsed to single line (e.g. `["oauth2"]` not expanded to multi-line) |
| 2026-04-10 | J-10/X-13: Java FQCN from release extended to JSON and XML — `is_java_fqcn()` applied in JSON `_merge()` and XML `_replace_elements()`; both keep release value and emit `JAVA_CLASS_NAME_FROM_RELEASE` |
| 2026-04-10 | K-20: Trailing-whitespace strip — spaces/tabs after values stripped on all KV emit paths |
| 2026-04-10 | K-21: Trailing blank line preservation — merged output ends with blank line when release file does |
| 2026-04-10 | K-22: Java FQCN from release (KV) — `is_java_fqcn()` in `utils.py`; `_merge_single_entry()` uses release value; reported as `JAVA_CLASS_NAME_FROM_RELEASE` |
| 2026-04-10 | K-18/K-19: Section preamble and trailing content preserved verbatim; release source preferred over base |
| 2026-04-10 | K-23–K-25: API version upgrade, multi-release-dir deduplication, filename-only fallback disambiguation |
| 2026-04-10 | J-07 updated: JSON indent detection now handles tab-indented files |
| 2026-04-10 | KV `.acl` extension registered; empty DEFAULT section no longer emits spurious leading blank; commented-only indexed group entries preserved verbatim |
| 2026-04-08 | U-22: File search with keyboard navigation — Ctrl+K focuses sidebar search; match count badge; Enter jumps to first match; Escape clears |
| 2026-04-08 | U-23–U-26: Audit report session UX — localStorage state persistence, Save All button, navigation guard modal, output directory prompt modal |
| 2026-04-08 | R-42/U-19: Index page search — search box filters directory tree and diff quick-list in real time on `audit_report.html` |
| 2026-04-08 | R-43/U-18: Sticky diffs-only on index — "Show diffs only" button stays in sticky toolbar when scrolling index page |
| 2026-04-08 | R-38/U-20/U-21: Section-level corrections — Skip section / Unskip section / Add from NodeX buttons on section divider rows |
| 2026-04-08 | R-39: Part indicators — per-part diff/absent/ok badge beside each Part# link in multi-part reports |
| 2026-04-08 | R-40: Sticky table headers — `overflow-x:auto` moved from `.table-wrap` to `.main`; `<thead>` sticks on vertical scroll |
| 2026-04-08 | R-41: Node name tooltip — full `base_dir` in `title=""` attribute; column header shows short name only |
| 2026-04-08 | R-30/R-31: Absent vs diff distinction — `absent_count` field on `AuditFile`; badges and banners shown independently; engine no longer conflates absence with content diff |
| 2026-04-08 | R-32–R-37: 8-sheet `audit_diffs.xlsx` auto-generated each run — replaces client-side CSV export; all sheets formatted with openpyxl PatternFill/Font/Alignment/freeze_panes |
| 2026-04-08 | FF-09: `noext` filter rule — files with no extension correctly included; removed `if suffix:` guard that silently dropped the rule when `_normalise_suffix` returned `""` |
| 2026-04-08 | FF-10–FF-15: Extended filter file formats — directory-path include, glob include, directory-path exclude (`!dir/path`), force-include (`+path`); `sample-filter.txt` added |
| 2026-04-07 | U-16/U-17: Global col width control + value wrap — toolbar −/+ buttons resize all node columns at once; number input sets wrap at N chars (default 80ch via CSS `--val-wrap`); ∞ clears wrap; both persisted to localStorage |
| 2026-04-07 | Bug: "Show differences only" blanked the panel — `data-expDiff` HTML attribute was lowercased by the parser to `data-expdiff`; JS `dataset.expDiff` expects `data-exp-diff` (hyphen convention); fixed by renaming attribute to `data-exp-diff` in `renderRow()` |
| 2026-04-07 | Bug: Raw JSON rendered as page text — `</SCRIPT>` / `</Script>` uppercase variants in audited config files terminated the embedded `<script>` block; fixed with `re.sub(r'</(script)', r'<\/\1', ..., re.IGNORECASE)` so all case variants are escaped |
| 2026-04-07 | P3: HTML sanity check — `_validate_html()` called before every file write; checks DOCTYPE, `</body>`, `</html>`, `<script>` balance; warns to stderr |
| 2026-04-07 | P2: Absent-file mismatch fix — `_compare_kv()` and `_compare_json()` now set `mismatch_count ≥ 1` when file absent from any node (binary/text/SSTP already did this) |
| 2026-04-07 | P2: Full-width tables — `renderParamTable` no longer wraps in its own `.table-wrap` (removes double-wrap); `.raw-content` `max-height:500px` cap removed |
| 2026-04-07 | P2: Skipped files "Copy rule" button — each entry gets a clipboard button copying a `no_skip_files` or `include` JSON rule; `navigator.clipboard` with `execCommand` fallback |
| 2026-04-07 | P1: Sticky layout — `body` is now `display:flex;flex-direction:column;height:100vh;overflow:hidden`; `.layout` uses `flex:1;min-height:0` — toolbar/navigation always visible regardless of part-nav or sub-stats bars |
| 2026-04-07 | P1: Diffs-only toggle persists across file navigation — `selectFile()` no longer resets `showDiffsOnly`; checkbox re-synced; filter re-applied |
| 2026-04-07 | P0: Index page diff-file quick-list — prominent red section above directory tree listing all diff files sorted by mismatch count; full path, type, diff count, absent-nodes, direct part link |
| 2026-04-07 | P0: Deep-link from index → part — links use `urllib.parse.quote(path)` as URL hash; part pages handle `window.location.hash` on load to open the linked file directly |
| 2026-04-07 | P0: Sidebar diffs-only auto-enables on load when diff files < 50% of total; "Diffs only" button activates automatically |
| 2026-04-06 | Phase 8: SSTP routing rule semantic diff — `SstpParser`, `categorise_block_diff()`, `_compare_sstp()` in engine, `SstpProcessor` copy-only in merge mode, `.sstp` registered in PROCESSOR_REGISTRY |
| 2026-04-06 | Phase 5: Audit intelligence — logical diff summary JSON, log name uniqueness detection (orange warnings), cross-run feedback accumulator (`~/.configmergetool/feedback_history.json`), `--feedback-summary` flag |
| 2026-04-06 | Phase 4: Audit report UX — Skip/Unskip button on mismatch rows; Next/Prev mismatch navigation with counter; resizable columns with localStorage persistence |
| 2026-04-06 | Phase 3.1: HTML report pagination — 25 MB cap per part file; `audit_report_p01.html`, `p02.html`…; lightweight index page |
| 2026-04-06 | Phase 3.2: Backup file auto-detection — `_BACKUP_SUFFIX_RE` patterns; stem-matching heuristic; `no_skip_files` whitelist; `skipped_backups.json` feedback |
| 2026-04-06 | Phase 3.3: File/directory filter — `FileFilter` with suffix/named/dir/exclude rules; `--filter-file` flag; `filtered_files.json` feedback; binary archives always excluded |
| 2026-04-06 | Phase 10: Packaging — `pyproject.toml`, `configmerge/cli.py` entry point, `configmerge/__main__.py`, `py.typed`, `requirements.txt`, `requirements-dev.txt`; `--version` flag |
| 2026-04-06 | Phase 9: Extensibility architecture — `NodeFetcher` ABC, `LocalNodeFetcher`, `SSHNodeFetcher` stub, `EmailAuditWorkflow` stub, `RemoteConfig` dataclass, `BaseDirConfig.local_path`/`remote` fields, `WorkflowBase` ABC |
| 2026-04-06 | Phase 7: `--quiet` flag (suppress MATCH lines); progress indicator every 25 files; pre-run node directory validation; `--feedback-summary` subcommand |
| 2026-04-06 | Phase 6: Excel — freeze header row, auto-filter drop-downs, auto row heights on all 6 sheets |
| 2026-04-06 | Phase 3.0: Audit table layout for many nodes — `overflow-x:auto` on `.table-wrap`, `width:max-content` on table, `position:sticky;left:0` on key column; node chip visibility controls |
| 2026-04-10 | K-20: Trailing-whitespace strip — spaces and tabs after parameter values stripped on all emit paths (`_emit_entry` pass-through and changed-value, `_emit_raw_entry`) |
| 2026-04-10 | K-21: Trailing blank line preservation — KVProcessor detects `\n\n` at end of release file and appends one blank line to merged output; prevents spurious `diff` noise |
| 2026-04-10 | K-22: Java FQCN from release — `is_java_fqcn()` helper in `utils.py`; `_merge_single_entry()` detects when both base and release values are Java FQCNs and uses release value; reported as `JAVA_CLASS_NAME_FROM_RELEASE` |
| 2026-04-10 | K-18/K-19: Section preamble and trailing content — `KVDocument.section_preamble` / `section_trailing` store comments before section headers and after last KV entry; emitted verbatim preferring release source |
| 2026-04-10 | K-23: API version upgrade — `detect_api_version_upgrade()` in `_merge_single_entry()` uses release value when both values match artifact-version patterns; reported as `API_VERSION_UPGRADED` |
| 2026-04-10 | K-24/K-25: Multi-release-dir and filename-only fallback disambiguation — FileMatcher prefers release dir matching base dir name; prefers same-directory base candidate on filename fallback; both log `WARNING` |
| 2026-04-10 | J-07 updated: JSON indent detection now handles tab-indented files (returns `"\t"`) in addition to 2/4/8-space detection |
| 2026-04-10 | KV: `.acl` extension registered with KVProcessor (was falling through to GenericProcessor) |
| 2026-04-10 | KV: Empty-DEFAULT section no longer emits a spurious leading blank line when file starts with a named section |
| 2026-04-10 | KV: Commented-only indexed group entries preserved verbatim instead of silently dropped |
| 2026-04-06 | BUG-I: Section header fidelity — `KVDocument.section_raw_lines` stores original header line; emitted verbatim preserving inline comments |
| 2026-04-06 | BUG-G: JSON indent fidelity — `_detect_indent()` detects original indent width; merged output uses same width |
| 2026-04-06 | BUG-F: Patcher inline comment preservation — `_apply_kv()` detects trailing ` #` / ` ;` on changed lines; appended after new value |
| 2026-04-06 | BUG-E: KV comment merge policy — `_merge_single_entry()` uses release comments only when value is actually changing; unchanged params use base comments |
| 2026-04-06 | BUG-D/H: KV line fidelity — `_emit_entry()` and `_emit_raw_entry()` use `entry.raw_line` verbatim for pass-through; as template (delimiter pos + inline comment) for changed values |
| 2026-04-06 | BUG-C: Audit exit code — `return 1 if result.total_mismatches > 0 else 0` (was unconditional 0) |
| 2026-04-06 | BUG-B: ISO-8859 encoding — shared `open_text()` helper in `utils.py`; tries utf-8-sig → chardet → latin-1; applied to all processors and auditor |
| 2026-04-06 | BUG-A: HTML script injection — `</script>` in embedded AUDIT_DATA JSON escaped to `<\/script>` |
| 2026-04-06 | MOD-6: `file_sha256()` added to `utils.py`; audit binary comparison uses SHA-256 (was MD5) |
| 2026-04-06 | MOD-4: Path-traversal guard — `safe_realpath()` applied in `_scan_dir()`; symlinks escaping `base_dir` skipped |
| 2026-04-06 | MOD-3: Thread-safe logger — `important()` routes through handler `emit()` not `print()`; `ensure_dir()` wrapped in `try/except FileExistsError` |
| 2026-04-06 | MOD-2: Multi-base warning for XML/JSON — `logger.warning()` when `len(base_files) > 1`; extra files not silently discarded |
| 2026-04-02 | K-13/K-14: Pre-/post-annotation preservation; K-12 shadow section handling; K-15/K-16 section interleaving and ordering |
| 2026-04-02 | Duplicate key reporting: only release-file duplicates surfaced; base duplicates resolved silently |
| 2026-04-01 | Multi-base execution, HTML sidebar, 3-Way Diff, XML namespace protection, Excel 6 sheets |
| 2026-03-31 | Initial features document |
