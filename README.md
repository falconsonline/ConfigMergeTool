# ConfigMergeTool

Merges production configuration files (base) with new software release configuration files (release), producing a merged output where **base values always win**.

## Merge Rule

| Situation | Output |
|---|---|
| Key in **both** base and release | Base value used |
| Key in **base only** | Added to output |
| Key in **release only** | Kept as-is |

Supports `.properties`, `.cfg`, `.ini`, `.conf`, `.sh`, `.xml`, `.xsd`, `.json`, `.logrotate`, and all other file types.

---

## Requirements

```
Python 3.9+
pip install openpyxl
```

---

## Quick Start

```bash
python3 ConfigMergeTool.py \
  --base-dir base \
  --release-dirs release \
  --output-dir output \
  --verbose
```

---

## Full CLI Reference

```
python3 ConfigMergeTool.py
    --base-dir BASE_DIR
    --release-dirs RELEASE_DIR [RELEASE_DIR ...]
    --output-dir OUTPUT_DIR
    [--base-config-file BASE_CONFIG_FILE]
    [--mapping-file MAPPING_FILE]
    [--copy-baseonlyconfigfile COPY_ONLY_FILE]
    [--exclude-params-in-baseonlyconfig]
    [--dry-run]
    [--verbose]
```

| Argument | Required | Description |
|---|---|---|
| `--base-dir` | Yes (or `--base-config-file`) | Production/site config directory |
| `--release-dirs` | Yes | One or more release config directories (searched in order) |
| `--output-dir` | Yes | Destination for merged output files |
| `--base-config-file` | No | JSON file defining multiple base directories (multi-node mode) |
| `--mapping-file` | No | Maps base filenames to differently-named release files |
| `--copy-baseonlyconfigfile` | No | List of base files to copy as-is without merge |
| `--exclude-params-in-baseonlyconfig` | No | Suppress base-only parameter insertion into output |
| `--dry-run` | No | Generate reports without writing any output files |
| `--verbose` | No | Print INFO-level log events to console |

---

## Mapping File Format

Use `--mapping-file` when base and release directories use different names for the same config file.

```
# Format: base_path = release_path
# Paths are relative to the working directory.

base/config/fsmapp.cfg = release/config/app.properties
base/config/jetty-base.xml = release/config/jetty.xml

# Many-to-One: two base files merge into one release file
base/config/db-primary.properties = release/config/database.properties
base/config/db-replica.properties = release/config/database.properties
```

Path format for base side (all equivalent):
- Full path from working directory: `base/config/file.properties`  ← **preferred**
- Base dir name prefix: `base_dirname/config/file.properties`
- Bare relative path within base: `config/file.properties`  ← legacy, still accepted

---

## Copy-Only File Format

Use `--copy-baseonlyconfigfile` to list base files that must be copied verbatim (no merge).

```
# Format: one path per line, relative to working directory.

base/config/ssl/server.keystore
base/config/ssl/truststore.jks
base/config/licence.dat
base/bin/start.sh
```

Path format (all equivalent):
- Full path from working directory: `base/config/ssl/server.keystore`  ← **preferred**
- Base dir name prefix: `base_dirname/config/ssl/server.keystore`
- Bare relative path within base: `config/ssl/server.keystore`  ← legacy, still accepted

These files appear in the **BaseConfigAsIs** sheet of the Excel report.

---

## Multi-Base Usage

Run one independent merge pass per production node using `--base-config-file`:

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

```bash
python3 ConfigMergeTool.py \
  --base-config-file base-configs.json \
  --release-dirs release \
  --output-dir output \
  --verbose
```

Each node gets its own output subdirectory (`output/<node-name>/`) and Excel report. All nodes share one HTML report.

---

## Output Structure

```
output/
  config/
    app.properties   ← merged
    server.xml        ← merged

reports/
  run_YYYYMMDD_HHMMSS/
    merge_diff.html          ← interactive HTML diff report (all bases)
    merge_report_<base>.xlsx ← 6-sheet Excel report (one per base)
    log_merge_config.log     ← full debug log
```

Archive a complete run:
```bash
zip -r run_20260401_143022.zip reports/run_20260401_143022/
```

---

## HTML Report

Self-contained single file — no internet connection required.

- **Left sidebar**: file-system tree, click to navigate, search by name
- **Sidebar click**: jumps directly to the file header (Full Config / 3-Way Diff buttons are immediately visible — no scrolling needed)
- **Changes-only view**: each changed parameter with release vs merged values side-by-side
- **Show Full Config**: entire merged file in two-column Release ↔ Output layout with diff highlighting
- **3-Way Diff**: Base ↔ Release ↔ Merged in three columns
- **Toolbar**: filter by change type; Collapse All / Expand All
- **Legend bar**: fixed at bottom of screen, always visible, hover for explanations

---

## Excel Report — 6 Sheets

| Sheet | Content |
|---|---|
| **MergeChanges** | All parameter-level changes with Release and Base values |
| **BaseOnlyFiles** | Config files in base with no release counterpart |
| **ReleaseOnlyFiles** | Config files in release with no base counterpart |
| **FileMappings** | Explicit base ↔ release file mappings applied |
| **ExcludedBaseOnlyParams** | Base-only parameters skipped by `--exclude-params-in-baseonlyconfig` |
| **BaseConfigAsIs** | Files copied verbatim from base via `--copy-baseonlyconfigfile` |

Colour coding on MergeChanges:
- **Red** — `EMPTY_BASE_OVERRIDE`, `DUPLICATE_KEY`, `INVALID_JSON` (require review)
- **Yellow** — `BASE_ONLY_PARAMETER_ADDED`
- **Orange** — `RELEASE_ONLY_PARAMETER_ADDED`

---

## Key-Value Merge Behaviour

Advanced behaviour for `.properties`, `.cfg`, `.ini`, `.conf`, `.sh`:

| Feature | Behaviour |
|---|---|
| **Shadow sections** | If base has `#[SectionName]` (entire section commented out) and release has active `[SectionName]`, output keeps all entries commented — base comment-state wins |
| **Annotations** | `#key=old` appearing before an active `key=new` in release is emitted verbatim before the merged entry (pre-annotation) |
| **Post-annotations** | `#key=alternative` appearing after an active entry are preserved verbatim after the active line (e.g. `#event.list=UCGDMLS` after `event.list=UCM`) |
| **Indexed groups** | Keys matching `prefix.N.subkey` (e.g. `schedule.1.name`): base groups retained, release-only groups appended with renumbered indices, `prefix.count` updated |
| **Comma-value union** | Group header params with comma-separated values (e.g. `schedule.registry`) merged as union of base + release |
| **Section ordering** | Base-only sections interleaved at their natural relative position from the base file, not appended at end |
| **Duplicate detection** | Only active key duplicates flagged; commented entries (`#key=val`) alongside active entries are treated as annotations, never as duplicates |

---

## Programmatic API

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

For the full features reference, see [ConfigMergeTool-features.md](ConfigMergeTool-features.md).  
For the user guide with worked examples, see [ConfigMergeTool-readme.txt](ConfigMergeTool-readme.txt).
