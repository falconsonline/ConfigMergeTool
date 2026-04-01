# ConfigMergeTool — Features Reference

> Developer reference. Describes every feature implemented in the current codebase.
> Update this file whenever features are added, changed, or removed.

---

## Table of Contents
1. [Architecture](#architecture)
2. [CLI Arguments](#cli-arguments)
3. [File Format Support](#file-format-support)
4. [Feature Details](#feature-details)
   - [File Discovery & Matching](#file-discovery--matching)
   - [Multi-Base Execution](#multi-base-execution)
   - [Key-Value Processing](#key-value-processing)
   - [XML Processing](#xml-processing)
   - [JSON Processing](#json-processing)
   - [Logrotate Processing](#logrotate-processing)
   - [Generic Processing](#generic-processing)
   - [Excel Report](#excel-report)
   - [HTML Report](#html-report)
   - [Run Output Structure](#run-output-structure)
   - [Logging](#logging)
5. [Report Entry Types](#report-entry-types)
6. [Changelog](#changelog)

---

## Architecture

```
ConfigMergeTool/
├── ConfigMergeTool.py          — CLI shim: argparse → MergeConfig → MergeEngine.run()
└── configmerge/
    ├── __init__.py             — Public API: MergeEngine, MergeConfig, BaseDirConfig, MergeResult
    ├── models.py               — Dataclasses: BaseDirConfig, MergeConfig, MergeResult, ReportEntry, EntryType
    ├── logger.py               — setup_logging(), important(), log_structured()
    ├── utils.py                — ensure_dir(), copy_file()
    ├── matcher.py              — FileMatcher: file discovery, name matching, mapping resolution
    ├── engine.py               — MergeEngine: orchestrates one pass per base dir
    ├── processors/
    │   ├── __init__.py         — BaseProcessor ABC + PROCESSOR_REGISTRY dict
    │   ├── kv.py               — KVProcessor (.properties/.cfg/.ini/.conf/.sh)
    │   ├── xml_proc.py         — XMLProcessor (.xml/.xsd)
    │   ├── json_proc.py        — JSONProcessor (.json)
    │   ├── logrotate.py        — LogrotateProcessor (.logrotate)
    │   └── generic.py          — GenericProcessor (all other extensions)
    └── reporter/
        ├── excel.py            — write_excel(): 6-sheet .xlsx report
        └── html_reporter.py    — write_html(): self-contained HTML diff report
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
```

---

## CLI Arguments

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

**`--base-config-file` JSON format:**
```json
[
  {
    "base_dir":       "base/node1",
    "name":           "prod-eu",
    "mapping_file":   "mappings/node1-mapping.txt",
    "copy_only_file": "mappings/node1-copy-only.txt"
  },
  {
    "base_dir": "base/node2",
    "name":     "prod-us"
  }
]
```
All fields except `base_dir` are optional. `name` defaults to the directory's folder name.

**`--mapping-file` format:**
```
base/config/old-name.cfg=release/config/new-name.properties
base/config/db-primary.xml=release/config/database.xml
base/config/db-replica.xml=release/config/database.xml
```
Many-to-One is supported: multiple base paths can map to one release path.

**`--copy-baseonlyconfigfile` format:**
```
base/config/ssl/server.keystore
base/config/licence.dat
```

---

## File Format Support

| Extension(s) | Processor | Merge Strategy |
|---|---|---|
| `.properties`, `.cfg`, `.ini`, `.conf`, `.sh` | KVProcessor | Key-level per section; base wins; release-only preserved |
| `.xml`, `.xsd` | XMLProcessor | Element-level; base wins; release namespace retained |
| `.json` | JSONProcessor | Deep recursive merge; base wins; release-only keys preserved |
| `.logrotate` | LogrotateProcessor | Whole base file copied to output |
| All others | GenericProcessor | Copied as-is from release; no merge |

---

## Feature Details

### File Discovery & Matching

| ID | Feature | Behaviour |
|---|---|---|
| F-01 | Recursive walk | Both `base_dir` and all `release_dirs` are walked recursively |
| F-02 | Relative-path match | Release file matched to base file first by identical relative path |
| F-03 | Filename-only fallback | If relative paths differ, matched by filename alone |
| F-04 | Ambiguity detection | If the same filename appears in multiple base locations, the file is flagged ambiguous and skipped with a WARNING |
| F-05 | Explicit mapping | `--mapping-file` maps base paths to differently-named release paths; mapped files bypass filename matching |
| F-06 | Many-to-One mapping | Multiple base paths may map to one release path; all base files merged in order |
| F-07 | Copy-only bypass | Files listed in `--copy-baseonlyconfigfile` are copied from base without processing |
| F-08 | Path traversal guard | Paths from mapping and copy-only files are canonicalised with `os.path.realpath`; must remain within `base_dir` |
| F-09 | Output dir cleanup | Output dir is removed and recreated before each run (skipped in `--dry-run`) |
| F-10 | Release-only detection | Release files with no base counterpart are noted in the ReleaseOnlyFiles Excel sheet |

---

### Multi-Base Execution

| ID | Feature | Behaviour |
|---|---|---|
| M-01 | Independent pass per base | Each `BaseDirConfig` runs a completely independent `FileMatcher` + processor pass |
| M-02 | Per-base output subdirs | Multi-base: output goes to `output/<base_name>/`; single-base: directly to `output/` |
| M-03 | Per-base Excel report | Each base produces its own Excel file named `merge_report_<base_name>.xlsx` |
| M-04 | Combined HTML report | All bases appear in one HTML report; sidebar groups files by base name |
| M-05 | Per-base mapping & copy-only | Each `BaseDirConfig` can specify its own `mapping_file` and `copy_only_file` |
| M-06 | Single run directory | All run artifacts (logs, Excel, HTML) land in `reports/run_YYYYMMDD_HHMMSS/` so one zip captures a complete run |

---

### Key-Value Processing

Handles: `.properties`, `.cfg`, `.ini`, `.conf`, `.sh`

**Parser — `KVDocument`:**
- Section-aware (`[section]` headers tracked; global keys go in a default section)
- Each key captures: value, comment lines above it, whether it is currently commented-out, delimiter (`=` or `:`)
- Detects duplicate `section|key` pairs; last value wins; all logged as `DUPLICATE_KEY`

| ID | Feature | Behaviour |
|---|---|---|
| K-01 | Base value wins | For keys in both base and release, the base value is used in output |
| K-02 | Comment preservation | Comment/blank lines immediately preceding a key are re-emitted with the key |
| K-03 | Comment source preference | If both files have a comment for the same key and they differ, the release comment is used in output |
| K-04 | Commented-out key handling | If a release key is commented out (`# key=value`) but base has a value for it, the key is uncommented and set to the base value; reported as `UNCOMMENT_REPLACE` |
| K-05 | Base-only insertion | Keys in base absent from release are inserted into the matching section in output; reported as `BASE_ONLY_PARAMETER_ADDED` |
| K-06 | Release-only preservation | Keys in release absent from base are kept in output; reported as `RELEASE_ONLY_PARAMETER_ADDED` |
| K-07 | Exclude flag | `--exclude-params-in-baseonlyconfig` suppresses K-05; excluded params logged as `EXCLUDED_BASE_ONLY_PARAMETER` |
| K-08 | Empty base override | If the base value is blank/empty, the release value is forced blank; logged as `EMPTY_BASE_OVERRIDE` (requires review) |
| K-09 | Indexed group handling | Keys matching `prefix.N.subkey` (e.g. `schedule.1.name`) are detected as indexed groups; base groups retained in order; release-only groups appended with renumbered indices; `prefix.count` updated to final total |
| K-10 | Comma-value union | Group header params with comma-separated values (e.g. `schedule.registry`) get a union of base + release values |
| K-11 | Duplicate key detection | Multiple occurrences of the same `section|key` in base are reported as `DUPLICATE_KEY` |

---

### XML Processing

Handles: `.xml`, `.xsd`

| ID | Feature | Behaviour |
|---|---|---|
| X-01 | Element-level replacement | Each base element (matched by tag + `name` attribute) replaces the corresponding release element verbatim |
| X-02 | Namespace preservation | Release namespace declarations are captured before any processing; merged output is post-processed to restore the original release root namespace exactly, removing any `ns0:`, `ns1:` prefixes that ElementTree may inject |
| X-03 | Hyphenated namespace support | Tag and attribute regex patterns use `[\w-]+:` to match namespace prefixes containing hyphens |
| X-04 | Empty-base override | If a base element has no children and no text content, the release element is forced empty; logged as `EMPTY_BASE_OVERRIDE_XML` |
| X-05 | Base-only element insertion | Elements in base absent from release are inserted into output; controlled by `--exclude-params-in-baseonlyconfig` |
| X-06 | Release-only preservation | Elements only in release are kept in output; reported as `RELEASE_ONLY_PARAMETER_ADDED` |
| X-07 | Duplicate element detection | Duplicate tag+name combinations in base are reported as `DUPLICATE_KEY` |
| X-08 | BOM handling | Files are read with `encoding="utf-8-sig"` to silently strip UTF-8 BOM |
| X-09 | Garbage-before-declaration strip | Content before `<?xml` is removed before parsing |
| X-10 | Safe parse | XML parse errors produce structured log entries; the file is skipped without crashing the run |
| X-11 | Comment capture | XML comments preceding an element are stored and associated with that element for the HTML report |

---

### JSON Processing

Handles: `.json`

| ID | Feature | Behaviour |
|---|---|---|
| J-01 | Deep recursive merge | `merge(base, release)` recurses into nested objects; base values overwrite matching release values at any depth |
| J-02 | Release-only preservation | Keys present only in release at any depth are retained; reported as `RELEASE_ONLY_PARAMETER_ADDED` |
| J-03 | Empty-base override | If base value is `""`, release value is forced to `""`; reported as `JSON_EMPTY_BASE_OVERRIDE` |
| J-04 | Duplicate key detection | Custom object-pairs hook detects duplicate keys within the same JSON object; last value wins |
| J-05 | Input validation | Both files are validated before merge; invalid files produce `INVALID_JSON` entries |
| J-06 | Output validation | Merged JSON is re-parsed after serialisation to confirm validity; invalid output is discarded and reported as `INVALID_OUTPUT_JSON` |

---

### Logrotate Processing

Handles: `.logrotate`

| ID | Feature | Behaviour |
|---|---|---|
| L-01 | Whole-file replacement | The entire base logrotate file is written to output verbatim |
| L-02 | Empty-base override | If the base file is blank, output is written as empty; reported as `LOGROTATE_EMPTY_BASE_OVERRIDE` |

---

### Generic Processing

Handles: All extensions not matched by a registered processor.

| ID | Feature | Behaviour |
|---|---|---|
| G-01 | Copy from release | File is copied as-is from the release directory |
| G-02 | No merge | No key-level or element-level processing is performed |
| G-03 | Logged | A `[GENERIC]` log entry is written so unhandled formats are visible |

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

Colour rules on MergeChanges:
- **Red** — `EMPTY_BASE_OVERRIDE*`, `DUPLICATE_KEY`, `INVALID_JSON`, `INVALID_OUTPUT_JSON`
- **Yellow** — `BASE_ONLY_PARAMETER_ADDED`
- **Orange** — `RELEASE_ONLY_PARAMETER_ADDED`
- White — all other change types

---

### HTML Report

Single self-contained file. Filename: `merge_diff.html`  
No internet connection required; no external JS or CSS dependencies.

**Structure:**
- Fixed top bar: run metadata (base dir, release dir, output dir, timestamp)
- Summary bar: total counts per change type
- Left sidebar: collapsible file-system tree + search box
- Right panel: toolbar + one collapsible section per processed file
- Fixed bottom legend bar: always visible, hover for tooltip explanations

**Sidebar:**
- Tree mirrors the output directory structure
- Click any file to jump to its section and highlight it
- Search box filters the file list by name
- Multi-base: sidebar has one top-level group per base name
- Directories are collapsible

**File sections:**
- Click header to expand/collapse
- "Show Full Config" button toggles between:
  - **Changes-only view**: each changed parameter with release vs merged values side-by-side
  - **Full Config Diff**: entire file shown in two-column layout — Release (left) vs Merged Output (right)

**Full Config Diff colour coding:**

| Colour | Meaning |
|---|---|
| White | Line identical in release and merged output |
| Yellow | Line differs — release value was replaced by base value |
| Green | Line only in merged output — base-only parameter added |
| Red / strikethrough | Line in release not carried through to merged output |

**Change row colours:**

| Colour | Meaning |
|---|---|
| Blue tag | BASE_TO_RELEASE_REPLACED — value replaced by base |
| Green tag | BASE_ONLY_PARAMETER_ADDED — inserted from base |
| Orange tag | RELEASE_ONLY_PARAMETER_ADDED — kept from release |
| Red tag | EMPTY_BASE_OVERRIDE / DUPLICATE_KEY / errors |

**Legend bar (fixed bottom):**
- Always visible regardless of scroll position
- Two sections: Change Row colours and Full Config Diff colours
- Hover over any item for a tooltip with the full explanation

**Toolbar buttons:**
- All Changes, Empty Override, Base-Only, Release-Only — filter visible change rows
- Collapse All / Expand All — toggle all file sections

**JavaScript:** Pure vanilla JS (~80 lines); no external libraries.

---

### Run Output Structure

All artifacts for one run land in a single timestamped directory:

```
reports/
└── run_YYYYMMDD_HHMMSS/
    ├── log_merge_config.log        ← full DEBUG log
    ├── merge_diff.html             ← combined HTML (all bases)
    ├── merge_report_<base1>.xlsx   ← Excel per base
    └── merge_report_<base2>.xlsx
```

For single-base runs the Excel file is `merge_report_<base_dir_name>.xlsx`.  
The run directory can be zipped directly to archive the complete run:
```bash
zip -r run_20260401_143022.zip reports/run_20260401_143022/
```

---

### Logging

| ID | Feature | Behaviour |
|---|---|---|
| L-01 | File logging | All events at DEBUG level written to `log_merge_config.log` in the run directory |
| L-02 | Console logging | `--verbose`: INFO+ events; default: WARNING+ events and explicit `important()` calls |
| L-03 | No duplicate output | `important()` calls `print()` once and writes directly to the FileHandler only, bypassing the StreamHandler to avoid double-printing in verbose mode |
| L-04 | Structured format | `[TYPE][ACTION][SEVERITY][FILE][ELEMENT] message` |
| L-05 | Unique logger name | Each run gets a logger named `config-merge.YYYYMMDD.HHMMSS.mmm`; prevents handler bleed between runs in tests |
| L-06 | Dry-run labelled | Every run under `--dry-run` emits `[DRY-RUN] No files will be written` at the start |

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
| `RELEASE_ONLY_PARAMETER_ADDED` | Orange | Parameter only in release — kept as-is |
| `EXCLUDED_BASE_ONLY_PARAMETER` | Normal | Base-only parameter skipped due to `--exclude-params-in-baseonlyconfig` |
| `EMPTY_BASE_OVERRIDE` | **Red/ERROR** | KV: base value empty — release value forced empty; review required |
| `EMPTY_BASE_OVERRIDE_XML` | **Red/ERROR** | XML: base element empty — release element forced empty; review required |
| `JSON_EMPTY_BASE_OVERRIDE` | **Red/ERROR** | JSON: base value `""` — release value forced `""`; review required |
| `LOGROTATE_EMPTY_BASE_OVERRIDE` | **Red/ERROR** | Logrotate: base file blank — output forced empty; review required |
| `DUPLICATE_KEY` | **Red** | Duplicate key/element in base file; last value used |
| `INVALID_JSON` | **Red** | Input file contains invalid JSON; file skipped |
| `INVALID_OUTPUT_JSON` | **Red** | Merged JSON failed re-validation; output discarded |
| `FILE_MAPPING` | Normal | Explicit file mapping from `--mapping-file` applied |
| `NAMESPACE_ADAPTED` | Normal | XML namespace updated from release declarations |
| `INDEXED_GROUP_RENUMBERED` | Normal | Indexed group entries (e.g. `schedule.N.x`) renumbered |
| `INDEXED_GROUP_APPENDED` | Normal | Release-only indexed groups appended after base groups |
| `COMMA_VALUE_UNION` | Normal | Comma-separated group header value merged as union of base + release |

---

## Changelog

| Date | Change |
|---|---|
| 2026-04-01 | Fixed bottom legend bar with hover tooltips; always visible regardless of scroll position |
| 2026-04-01 | All run artifacts (log, Excel, HTML) consolidated into one `reports/run_YYYYMMDD_HHMMSS/` directory per run |
| 2026-04-01 | Full Config Diff corrected to release ↔ output direction (was base ↔ output); two-column side-by-side layout |
| 2026-04-01 | Multi-base execution: `--base-config-file` JSON option; independent pass per node; per-base output subdirs; combined HTML |
| 2026-04-01 | HTML sidebar: collapsible file-system tree, file search, click-to-navigate, multi-base grouping |
| 2026-04-01 | "Show Full Config" toggle per file section; shows complete merged file with diff highlights |
| 2026-04-01 | XML namespace protection: `_normalize_namespaces()` prevents `ns0:`, `ns1:` injection |
| 2026-04-01 | HTML report (`merge_diff.html`): self-contained, interactive, no external dependencies |
| 2026-04-01 | Excel report expanded to 6 sheets: added ExcludedBaseOnlyParams and BaseConfigAsIs |
| 2026-04-01 | Package restructure: `configmerge/` package with processors, reporter, engine, matcher modules |
| 2026-03-31 | Initial features, issues, and enhancements document created |
