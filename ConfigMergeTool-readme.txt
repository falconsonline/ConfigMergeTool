================================================================================
 ConfigMergeTool v2.0.1 — User Guide
 Author: Shiju Abraham
================================================================================

WHAT IT DOES
------------
ConfigMergeTool has two operating modes:

  MERGE MODE   Merge config files from a base (production/site) directory
               into a release (new software release) directory, producing a
               merged output directory ready for deployment.

  AUDIT MODE   Compare config files across multiple production nodes to detect
               configuration drift, flag mismatches, and produce an interactive
               HTML report with per-node resolution controls.

Merge rule:  BASE VALUES WIN.
  - If a key/element exists in both base and release → use the BASE value.
  - If a key/element exists only in base             → add it to output.
  - If a key/element exists only in release          → keep it in output.

Typical use case:
  A production node has customised configs (base/).
  A new software release ships updated default configs (release/).
  This tool creates merged configs (output/) that carry the site's
  customisations forward onto the new release baseline.
  After deployment, run audit mode to verify all nodes are consistent.


================================================================================
 REQUIREMENTS & INSTALLATION
================================================================================

Requirements
------------
  Python 3.9+

--------------------------------------------------------------------------------
 LINUX / macOS INSTALLATION
--------------------------------------------------------------------------------

Step 1 — Create a virtual environment (recommended):

  python3 -m venv ~/.venvs/configmergetool
  source ~/.venvs/configmergetool/bin/activate

Step 2 — Install from wheel:

  pip install configmergetool-2.0.1-py3-none-any.whl

  # With optional auto-encoding detection (recommended for non-UTF-8 sites):
  pip install "configmergetool-2.0.1-py3-none-any.whl[encoding]"

  # With all optional extras:
  pip install "configmergetool-2.0.1-py3-none-any.whl[all]"

Step 3 — Verify:

  configmergetool --version
  configmergetool --help

To deactivate the virtual environment when done:
  deactivate

--------------------------------------------------------------------------------
 WINDOWS INSTALLATION
--------------------------------------------------------------------------------

Step 1 — Install Python 3.9+ from https://www.python.org/downloads/windows/
  During setup, tick "Add Python to PATH".

Step 2 — Open Command Prompt or PowerShell, create a virtual environment:

  python -m venv C:\venvs\configmergetool

Step 3 — Activate the virtual environment:

  Command Prompt:
    C:\venvs\configmergetool\Scripts\activate.bat

  PowerShell:
    C:\venvs\configmergetool\Scripts\Activate.ps1

  If PowerShell blocks script execution, first run (once, as Administrator):
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

Step 4 — Install from wheel (copy the .whl file to a local folder first):

  pip install configmergetool-2.0.1-py3-none-any.whl

  # With optional encoding detection:
  pip install "configmergetool-2.0.1-py3-none-any.whl[encoding]"

  # With all optional extras:
  pip install "configmergetool-2.0.1-py3-none-any.whl[all]"

Step 5 — Verify:

  configmergetool --version
  configmergetool --help

To deactivate when done:
  deactivate

Note: On Windows, use backslashes or forward slashes in paths. Paths with
spaces must be quoted:
  configmergetool --base-dir "C:\configs\prod node" --release-dirs release ...

--------------------------------------------------------------------------------
 UPGRADING FROM A PREVIOUS VERSION
--------------------------------------------------------------------------------

To upgrade to a new .whl (e.g. from 2.0.0 to 2.0.1), activate your virtual
environment and run pip with --upgrade:

  # Linux / macOS
  source ~/.venvs/configmergetool/bin/activate
  pip install --upgrade configmergetool-2.0.1-py3-none-any.whl

  # Windows (Command Prompt)
  C:\venvs\configmergetool\Scripts\activate.bat
  pip install --upgrade configmergetool-2.0.1-py3-none-any.whl

  # Windows (PowerShell)
  C:\venvs\configmergetool\Scripts\Activate.ps1
  pip install --upgrade configmergetool-2.0.1-py3-none-any.whl

Confirm the new version is active:
  configmergetool --version

To check what is currently installed:
  pip show configmergetool

To list all installed packages in the environment:
  pip list

--------------------------------------------------------------------------------
 INSTALLATION OPTION B — RUN FROM SOURCE (no install needed)
--------------------------------------------------------------------------------

  pip install openpyxl        # only hard dependency
  pip install chardet         # optional but recommended for encoding detection
  python3 ConfigMergeTool.py [args]   # Linux/macOS
  python  ConfigMergeTool.py [args]   # Windows

  Both invocation forms produce identical behaviour.

--------------------------------------------------------------------------------
 OPTIONAL EXTRAS
--------------------------------------------------------------------------------

  [encoding]  chardet>=5.0    — auto-detect file encoding; fallback to latin-1
  [ssh]       paramiko>=3.0   — SSH/SFTP remote node fetching (Phase 11, stub)
  [email]     imapclient>=2.3 — email-triggered audit (Phase 12, stub)
  [all]       all of the above
  [dev]       pytest, build, twine — development tools

Verify active version:
  configmergetool --version
  python -c "import configmerge; print(configmerge.__version__)"


================================================================================
 FULL CLI REFERENCE — MERGE MODE
================================================================================

  configmergetool
      --base-dir BASE_DIR
      --release-dirs RELEASE_DIR [RELEASE_DIR ...]
      --output-dir OUTPUT_DIR
      [--base-config-file BASE_CONFIG_FILE]
      [--mapping-file MAPPING_FILE]
      [--copy-baseonlyconfigfile COPY_ONLY_FILE]
      [--exclude-params-in-baseonlyconfig]
      [--dry-run]
      [--verbose]
      [--quiet]
      [--version]

Option details:

  --base-dir PATH
      Base (production/site) config directory.
      Required unless --base-config-file is used.

  --release-dirs PATH [PATH ...]
      One or more release config directories.
      Multiple release dirs are searched in order; first match wins.

  --output-dir PATH
      Directory where merged config files are written.
      Cleaned and recreated on every run (skipped with --dry-run).

  --base-config-file PATH
      JSON file listing multiple base directories (one pass per node).
      Replaces --base-dir when running against multiple production nodes.
      See "MULTI-BASE USAGE" section below.

  --mapping-file PATH
      Text file mapping base filenames to differently-named release files.
      Required when base and release use different names for the same config.
      See "MAPPING FILE FORMAT" section below.

  --copy-baseonlyconfigfile PATH
      Text file listing base files that should be copied as-is to output
      without any merge processing (e.g. certificates, binary blobs).
      See "COPY-ONLY FILE FORMAT" section below.

  --exclude-params-in-baseonlyconfig
      When set, parameters that exist only in the base file (no release
      counterpart) are NOT added to the merged output.
      They are still reported in the ExcludedBaseOnlyParams Excel sheet.

  --dry-run
      Analyse all files and generate the full report without writing any
      output config files. Useful for previewing what will change.

  --verbose
      Print all INFO-level log events to the console in addition to the
      log file. Default: only summary lines are printed.

  --quiet
      Suppress MATCH lines from console; print only DIFF, WARN, ERROR, and
      the final SUMMARY line. Useful for large runs or scheduled/CI jobs.
      All events still go to the log file regardless of this flag.

  --version
      Print the installed version number and exit.


================================================================================
 FULL CLI REFERENCE — AUDIT MODE
================================================================================

  configmergetool
      --audit-config-file AUDIT_CONFIG_FILE
      [--filter-file FILTER_FILE]
      [--quiet]
      [--version]

  configmergetool
      --apply-audit-patch PATCH_JSON_FILE
      --audit-config-file AUDIT_CONFIG_FILE
      --output-dir OUTPUT_DIR

  configmergetool
      --feedback-summary

Option details:

  --audit-config-file PATH
      JSON file listing production nodes to compare.
      Each entry specifies a base_dir and optional display name.
      Runs audit mode — no merge is performed.
      See "AUDIT CONFIG FILE FORMAT" section below.

  --filter-file PATH
      Optional filter file restricting which file types are audited.
      If omitted, all files are audited except binary archives.
      See "FILTER FILE FORMAT" section below.

  --apply-audit-patch PATCH_JSON_FILE
      Apply an audit patch JSON (exported from the HTML report) to source
      files, writing corrected configs to --output-dir.
      --audit-config-file is required to locate source files.
      --output-dir specifies where corrected files are written.

  --feedback-summary
      Print a summary of all past audit runs recorded in the feedback
      accumulator (~/.configmergetool/feedback_history.json).
      Does not run an audit.


================================================================================
 QUICK START — MERGE MODE
================================================================================

  configmergetool \
    --base-dir base \
    --release-dirs release \
    --output-dir output \
    --verbose


================================================================================
 QUICK START — AUDIT MODE
================================================================================

  configmergetool \
    --audit-config-file audit.json

Audit config file (audit.json):
  [
    { "base_dir": "prod/node1", "name": "APP-01" },
    { "base_dir": "prod/node2", "name": "APP-02" }
  ]

Result:
  reports/                        <- report_dir (default "reports")
    audit_20260401_143022/        <- one subdirectory per run (YYYYMMDD_HHMMSS)
      audit_report.html           <- interactive HTML report (index page when paginated)
      audit_report_p01.html       <- part 1 (only when report > 22 MB)
      audit_report_p02.html       <- part 2 (etc.)
      audit.log                   <- full audit log
      audit_diffs.xlsx            <- 8-sheet Excel diff workbook (auto-generated every run)
      feedback/
        skipped_backups.json      <- backup files detected and skipped
        filtered_files.json       <- files excluded by --filter-file
        logical_diff_summary.json
        log_name_warnings.json

  Each run creates a new timestamped subdirectory; previous runs are preserved.

audit_diffs.xlsx sheets:
  1. Summary          — run metadata and aggregate counts
  2. Issues           — all files with diffs or absent nodes (colour-coded)
  3. Parameter Diffs  — one row per differing parameter; one column per node
  4. Checksum Check   — files where raw bytes differ despite matched parsed values
  5. Absent Files     — files missing from one or more nodes
  6. Node Status      — all audited files with present/absent status per node
  7. Skipped Backups  — backup files auto-detected and skipped
  8. Filtered Files   — files excluded by --filter-file with reason


================================================================================
 AUDIT CONFIG FILE FORMAT
================================================================================

JSON array; each entry is one production node.

Minimal (local paths):
  [
    { "base_dir": "prod/APP-01", "name": "APP-01" },
    { "base_dir": "prod/APP-02", "name": "APP-02" }
  ]

Full example (all optional fields):
  [
    {
      "base_dir":      "prod/APP-01",
      "name":          "APP-01",
      "no_skip_files": ["fsmapp.properties_couchbase"]
    },
    {
      "base_dir":      "prod/APP-02",
      "name":          "APP-02"
    }
  ]

Fields:
  base_dir       (required)  Path to this node's config directory.
  name           (optional)  Display name in the HTML report.
                             Defaults to the folder's basename.
                             Must be unique across entries.
  no_skip_files  (optional)  List of filenames to exempt from backup
                             auto-detection even if they look like backups.
                             Example: ["fsmapp.properties_couchbase"]

Security note:
  Never put passwords in this file.  For remote nodes, use "password_env"
  (an env variable name) rather than a literal "password" field.
  The tool will reject entries with a literal "password" key.


================================================================================
 FILTER FILE FORMAT
================================================================================

Use --filter-file to restrict which files are audited.
If not provided, all files are included (except binary archives).

Format — plain text, one rule per line.  # lines are comments.  Blank lines
are ignored.  All matching is case-insensitive.

A complete sample filter file is provided in:  sample-filter.txt

--------------------------------------------------------------------------------
 INCLUDE RULES
--------------------------------------------------------------------------------

  a) Suffix only — include ALL files with this extension
     json
     xml
     cfg
     properties

     Special value "noext" — include files that have NO extension at all
     (e.g. Makefile, Dockerfile, named executables):
     noext

  b) Suffix::filename(s) — include only named files with this suffix
     conf::sysctl.conf,sctp.conf,spread.conf
     txt::config.txt,system.txt

  c) Suffix::directory — include only files in directories matching pattern
     html::runtime,test
     (all items after :: must have no "." to be treated as directory names)

  d) Directory-path include — include everything under a subtree
     (contains "/" — no leading "!")
     config/routing
     app/conf

  e) Glob filename include — include filenames matching a glob pattern
     (contains *, ?, or [ — no leading "!")
     *.jar.*
     GTPProxy*
     jar.[0-9].*

--------------------------------------------------------------------------------
 EXCLUDE RULES  (evaluated after force-includes, before include rules)
--------------------------------------------------------------------------------

  f) Explicit name exclude — always skip this exact filename
     !nohup.out
     !.DS_Store

  g) Glob exclude — skip filenames matching a glob pattern
     !*.tmp
     !*.swp
     !*~

  h) Directory-path exclude — skip everything under a subtree
     (contains "/" after "!")
     !logs/archive
     !backup
     !old

  i) Built-in binary exclusions — ALWAYS active, cannot be overridden
     .tar  .gz  .bz2  .xz  .tgz  .rpm  .deb
     .zip  .7z  .rar
     .jar  .war  .ear
     .jks  .keystore  .p12  .pfx
     .pem  .crt  .cer  .der
     .so   .dll  .exe  .dylib
     .class  .pyc
     .bin  .img  .iso

--------------------------------------------------------------------------------
 FORCE-INCLUDE  (evaluated first — overrides directory excludes)
--------------------------------------------------------------------------------

  j) Force-include a path within an excluded directory
     (leading "+")
     +config/security/certs/active
     +logs/archive/current-session

     Example: exclude all of "logs/archive" but keep one subtree:
       !logs/archive
       +logs/archive/current-session

--------------------------------------------------------------------------------
 EVALUATION ORDER
--------------------------------------------------------------------------------

  1. Force-include (+path)     — if matched, INCLUDE immediately
  2. Explicit excludes (!)     — if matched, EXCLUDE immediately
  3. Include rules             — if matched, INCLUDE
  4. Binary archive exclusions — if matched, EXCLUDE (built-in, always)
  5. Default
       - No filter file:        pass all files
       - Filter file with includes:  skip unmatched files

  Skipped files are recorded in:  <run_dir>/feedback/filtered_files.json

--------------------------------------------------------------------------------
 EXAMPLES
--------------------------------------------------------------------------------

Minimal — include common config types only:
  properties
  cfg
  xml
  json
  conf::sysctl.conf,sctp.conf
  !nohup.out

Roamware GTP Proxy site with subtree rules:
  properties
  cfg
  xml
  json
  conf::sysctl.conf,sctp.conf,spread.conf
  config/routing
  !logs/archive
  +logs/archive/current-session
  !*.pid
  !*.lock
  GTPProxy*


================================================================================
 BACKUP FILE AUTO-DETECTION
================================================================================

The auditor automatically detects and skips backup files based on their
filename patterns and whether an active counterpart exists in the same
directory.

Auto-detected suffixes / patterns:
  _bkp            _bkp_*         _backup        _backup_*
  _org            _orig          _old           _old_*
  _save           .bak           .bkp
  _DDMMYYYY       _DDMMYYYY_*    _YYYYMMDD      _YYYYMMDD_*
  _YYYYMMDDHHmmss .properties_DDMMYYYY
  _v[0-9]*        .properties_bkp

Heuristic:
  A file is only skipped as a backup when BOTH conditions are true:
    1. Its filename matches a backup suffix pattern.
    2. The canonical stem (the filename without the backup suffix) exists
       as an active file in the same directory.
  This prevents legitimate files with numeric suffixes from being skipped.

Example:
  GTPProxy.cfg              <- active file (processed normally)
  GTPProxy.cfg_bkp_27072024 <- detected as backup, skipped
  GTPProxy.cfg_20240727     <- detected as backup, skipped

Whitelist (opt out of auto-detection):
  In the audit config JSON, add "no_skip_files" to any node entry:
    { "base_dir": "prod/APP-01", "no_skip_files": ["fsmapp.properties_couchbase"] }

  The named file will NOT be skipped even if it matches a backup pattern.

Feedback:
  All skipped files are recorded in:
    <run_dir>/feedback/skipped_backups.json
  Review this file after each run to confirm no legitimate configs were skipped.


================================================================================
 SINGLE-BASE MERGE EXAMPLE
================================================================================

Directory layout:
  base/
    config/
      app.properties        <- production customisations
      server.xml            <- production customisations
      logging.cfg
  release/
    config/
      app.properties        <- new release defaults
      server.xml            <- new release defaults
      logging.cfg
      newfeature.properties <- new in this release
  output/                   <- created by the tool

Command:
  configmergetool \
    --base-dir base \
    --release-dirs release \
    --output-dir output \
    --verbose

Result:
  output/
    config/
      app.properties        <- merged: base values + release-only keys
      server.xml            <- merged: base elements + release-only elements
      logging.cfg           <- merged
      newfeature.properties <- copied from release (no base counterpart)

  reports/
    run_20260401_143022/
      merge_report_base.xlsx   <- 6-sheet Excel report
      merge_diff.html          <- interactive HTML diff report
      log_merge_config.log     <- full debug log


================================================================================
 MAPPING FILE FORMAT
================================================================================

Use --mapping-file when the base and release directories use different names
for the same configuration file.

Format:
  base_path = release_path

  One mapping per line.  Lines starting with # are ignored.

PATH FORMAT (paths are relative to the working directory):

  Preferred:
    base/config/fsmapp.cfg = release/config/app.properties

  Also accepted (backward compatible):
    config/fsmapp.cfg = config/app.properties   <- bare path within each dir

Example — mapping-file.txt:
  # Production uses "fsmapp.cfg", release renamed it "app.properties"
  base/config/fsmapp.cfg = release/config/app.properties

  # XML files with different names
  base/config/jetty-base.xml = release/config/jetty.xml

  # Many-to-One: two base files merge into one release file
  base/config/db-primary.properties = release/config/database.properties
  base/config/db-replica.properties = release/config/database.properties

Many-to-One mapping:
  Multiple base files can map to a single release file.  All base files
  are merged in order into one output file.  The Excel FileMappings sheet
  lists all applied mappings.


================================================================================
 COPY-ONLY FILE FORMAT
================================================================================

Use --copy-baseonlyconfigfile to list base files that should be copied
directly to output without any merge processing.

Use this for:
  - Binary or non-text config files
  - Keystores, certificates, licence files
  - Files where the entire base version must be used verbatim

Format:
  One file path per line.
  Lines starting with # are ignored.

PATH FORMAT:
  Preferred:  base/config/ssl/server.keystore   (full path from working dir)
  Also accepted: config/ssl/server.keystore      (bare path within base dir)

Example — copy-only.txt:
  # Certificates - always use production versions
  base/config/ssl/server.keystore
  base/config/ssl/truststore.jks

  # Licence file
  base/config/licence.dat


================================================================================
 MULTI-BASE MERGE USAGE (multiple production nodes)
================================================================================

When you have several production nodes with different base configs, use
--base-config-file to run one independent merge pass per node.

Each node gets:
  - Its own output subdirectory:  output/<node-name>/
  - Its own Excel report:         reports/run_YYYYMMDD_HHMMSS/merge_report_<node-name>.xlsx
  - All nodes share one HTML:     reports/run_YYYYMMDD_HHMMSS/merge_diff.html
  - One shared log:               reports/run_YYYYMMDD_HHMMSS/log_merge_config.log

JSON format — base-configs.json:
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

Command:
  configmergetool \
    --base-config-file base-configs.json \
    --release-dirs release \
    --output-dir output


================================================================================
 DRY RUN
================================================================================

Preview what will change without writing any output config files.
The full report (Excel + HTML) is still generated.

  configmergetool \
    --base-dir base \
    --release-dirs release \
    --output-dir output \
    --dry-run --verbose

Output files are NOT written.
Reports and log ARE written to: reports/run_YYYYMMDD_HHMMSS/


================================================================================
 MERGE BEHAVIOUR BY FILE TYPE
================================================================================

.properties / .cfg / .ini / .conf / .sh / .acl  (Key-Value files)
------------------------------------------------------------------
  Sections ([section]) are tracked independently.
  For each key in base:
    - If key exists in release (active) -> output gets BASE value.
    - If key only in base               -> inserted into output
                                          (unless --exclude flag).
    - If base value is empty            -> release value is forced empty
                                          (EMPTY_BASE_OVERRIDE).
  For each key only in release:
    - Kept as-is in output.

  Line fidelity:
    Unchanged parameters are emitted with their original raw line verbatim —
    indentation, delimiter spacing (`db.host = x` stays `db.host = x`),
    and any inline comments are preserved exactly.
    Trailing spaces and tabs after a value are always stripped from the output
    so that `param=value   ` becomes `param=value` regardless of source.

  Comment handling:
    - Release comments are always preferred over base comments.
    - Base comments are used only when the release entry has no comments of its own.
    - Blank lines and whitespace within comment blocks are preserved verbatim
      from whichever source is chosen (release or base).

  Section preamble:
    Comments appearing before a section header (e.g. before [SNMP]) are
    preserved in the merged output.  Release preamble is preferred; base
    preamble used as fallback.

  Trailing blank line:
    If the release file ends with a blank line, the merged output ends with
    one blank line too, preventing spurious diff noise.

  Annotation handling:
    - A commented line before an active key is a PRE-ANNOTATION:
        #event.list=UCGDML       <- pre-annotation: the old value
        event.list=UCM           <- active key
      The pre-annotation is emitted verbatim before the merged active entry.
    - A commented line AFTER an active key is a POST-ANNOTATION:
        event.list=UCM           <- active key
        #event.list=UCGDMLS      <- post-annotation: alternative value
      Post-annotations are preserved verbatim after the active entry.

  Java class name handling:
    When both the base and release values for a parameter are Java fully-
    qualified class names (e.g. com.example.pkg.MyClass) but differ, the
    RELEASE value is used.  Class names are deployment-specific and may
    legitimately differ between environments (different vendor packages,
    renamed classes, etc.).
    These entries are flagged as JAVA_CLASS_NAME_FROM_RELEASE in the report
    so a reviewer can verify the class name is correct for this environment.

  API version upgrade:
    When base and release values look like different versions of the same
    third-party artifact (e.g. log4j-1.2.17.jar vs log4j2-2.17.1.jar),
    the release (newer) value is used and reported as API_VERSION_UPGRADED.

  Shadow sections:
    - If base has an entire section commented out AND release has the same
      section active, output keeps all entries commented (base state wins).

  Indexed group handling:
    - Keys matching prefix.N.subkey (e.g. schedule.1.name) form indexed groups.
    - Base groups retained; release-only groups appended and renumbered.
    - prefix.count updated to the final group total.
    - Comma-separated header values merged as a union of base + release.

  Section ordering:
    - Sections follow release file order.
    - Base-only sections are inserted at their natural relative position.

  Duplicate key detection:
    - Only ACTIVE duplicate keys in the release file are flagged.
    - Commented entries alongside active entries are treated as annotations.

.xml / .xsd  (XML files)
------------------------
  Elements matched by tag name + "name" attribute.
  For each element in base:
    - If element exists in release -> output gets BASE element block verbatim.
    - If element only in base      -> inserted into output.
    - If base element is empty     -> release element forced empty.
    - If both base and release element text are Java FQCNs (e.g.
      com.example.pkg.MyClass) but differ -> RELEASE value kept, flagged as
      JAVA_CLASS_NAME_FROM_RELEASE for reviewer attention.
  Release namespace declarations preserved exactly.

.json  (JSON files)
-------------------
  Deep recursive merge: base values overwrite matching release values at any
  nesting depth.  Release-only keys preserved.
  Original indent style is detected (tab or 2/4/8 spaces) and preserved in the output.
  If both base and release string values are Java FQCNs but differ -> RELEASE
  value kept, flagged as JAVA_CLASS_NAME_FROM_RELEASE for reviewer attention.
  Arrays containing only primitive values (strings, numbers, booleans, null)
  are written inline: ["oauth2"] rather than expanded to multi-line.

.logrotate  (Logrotate files)
------------------------------
  Entire base file copied to output verbatim.
  If base file is empty, output written as empty (LOGROTATE_EMPTY_BASE_OVERRIDE).

.sstp  (Roamware Smart-STP routing rule files)
----------------------------------------------
  Auto-generated files — NOT hand-edited configs.
  In merge mode: release copy is always authoritative and copied as-is.
  In audit mode: semantic diff is performed; differences are categorised as
    VALUE DIFF (red), ORDER DIFF (orange), STRUCT EQUIV (yellow), MATCH (green).
  See "SSTP AUDIT DIFF" section below.

All other extensions  (Generic)
--------------------------------
  File copied from release directory as-is.  A log entry is written.


================================================================================
 SSTP AUDIT DIFF (Smart-STP routing rule files)
================================================================================

.sstp files contain named routing blocks:
  MAPTIMEOUT [...]
  GCT (0x33) [...]
  GCT (0x17,0x27) [...]

The auditor parses each block's parameters and categorises differences:

  VALUE DIFF   — parameter value differs between nodes
                 (e.g. SRC=0x53 vs SRC=0x51)
                 Shown in RED; requires review.

  ORDER DIFF   — route or digit list order differs
                 (e.g. ROUTE APP 0x27 OR ROUTE APP 0x17 vs reversed)
                 Shown in ORANGE; may be functionally significant.

  STRUCT EQUIV — structurally equivalent but written differently
                 (e.g. SET CDPA (A) AND SET CDPA (B)  vs  SET CDPA (A,B))
                 Shown in YELLOW; treated as a logical diff; not flagged.

  MATCH        — identical block bodies (after whitespace normalisation)
                 Shown in GREEN.

Whitespace and comment differences are always ignored.


================================================================================
 OUTPUT STRUCTURE PER RUN
================================================================================

Merge mode:
  reports/
    run_YYYYMMDD_HHMMSS/
      merge_diff.html           <- interactive HTML diff report
      merge_report_<base>.xlsx  <- Excel report (one per base dir)
      log_merge_config.log      <- full debug log

Audit mode:
  reports/
    audit_YYYYMMDD_HHMMSS/
      audit_report.html         <- interactive HTML report (or index page
                                   + audit_report_p01.html, p02.html …
                                   if report exceeds 22 MB)
      audit.log                 <- full audit log
      audit.xlsx                <- Excel summary
      feedback/
        skipped_backups.json    <- files auto-detected as backups
        filtered_files.json     <- files excluded by --filter-file
        logical_diff_summary.json  <- parameters flagged as logical diffs
        log_name_warnings.json  <- log file prefix uniqueness warnings


================================================================================
 EXCEL REPORT
================================================================================

Merge mode — 6 sheets (header row frozen, auto-filter enabled on all sheets):

  Sheet 1: MergeChanges
    All parameter-level changes.
    Columns: File | MergeCategory | ParameterName | ReleaseValue | BaseValue | Detail
    Colour coding:
      Red    -- EMPTY_BASE_OVERRIDE, DUPLICATE_KEY, INVALID_JSON (require review)
      Yellow -- BASE_ONLY_PARAMETER_ADDED
      Orange -- RELEASE_ONLY_PARAMETER_ADDED
      Purple -- JAVA_CLASS_NAME_FROM_RELEASE (reviewer should verify class name)

  Sheet 2: BaseOnlyFiles
    Config files in base dir with no release counterpart.

  Sheet 3: ReleaseOnlyFiles
    Config files in release dir with no base counterpart.

  Sheet 4: FileMappings
    Explicit base <-> release file mappings applied from --mapping-file.

  Sheet 5: ExcludedBaseOnlyParams
    Parameters excluded by --exclude-params-in-baseonlyconfig.

  Sheet 6: BaseConfigAsIs
    Files copied from base without merge (--copy-baseonlyconfigfile).


================================================================================
 MERGE HTML REPORT
================================================================================

Opens in any browser.  Self-contained (no internet connection needed).

Left sidebar:
  File-system tree of all processed files.  Click a file name to jump to it.
  Search box (Ctrl+K) to filter files — type to narrow, Enter to navigate,
  Escape to clear.  Collapse/expand directories.

File sections (right panel):
  Each processed file has a collapsible section showing all changes.

  "Show Full Config" button:
    Toggles between changes-only view and full two-column diff:
      Left = release (before merge), Right = output (after merge).
    Colour coding:
      White  -- line unchanged
      Yellow -- line differs (base value replaced release value)
      Green  -- line added (base-only parameter)
      Red    -- line in release not carried to output

  "3-Way Diff" button:
    Three-column view: Base | Release | Merged Output.
    Verifies base values were correctly applied.

Toolbar:
  Filter buttons: All Changes | Empty Override | Base-Only | Release-Only
  Collapse All / Expand All


================================================================================
 AUDIT HTML REPORT
================================================================================

Self-contained interactive report.  Opens in any browser.
For large audit runs (> 22 MB), the report is split into multiple part files
with an index page (audit_report.html → audit_report_p01.html, p02.html …).

Index page (multi-part runs):
  Opens automatically when there are multiple part files.
  Features:
    - "Files with differences" quick-list at top — all diff files in one
      place, sorted by mismatch count, with direct links to the correct part.
    - Collapsible directory tree showing diff/ok/absent status per directory.
    - "Show diffs only" toggle collapses all all-match directories.
    - Clicking a file link opens the correct part and jumps directly to that
      file (deep-link via URL hash).

Left sidebar (per-part pages):
  Recursive directory tree.  Directories with diffs auto-expand; all-match
  directories auto-collapse.  Per-directory badge shows diff count or ✓.

  At top of sidebar: collapsible "Files with differences" quick-list showing
  only files with mismatches.

  When most files match (< 50% have diffs), the sidebar "Diffs only" filter
  auto-enables on page load — only files with diffs are shown immediately.

  Click any file to load its parameter table in the right panel.

  File search (sidebar):
    Type in the search box to filter the file list as you type.
    A match count badge appears (green = N matches, red = no match).
    Press Enter to jump directly to the first matching file.
    Press Escape to clear the search and restore the full list.
    Press Ctrl+K (or Cmd+K on Mac) from anywhere in the report to focus
    the search box instantly.

Right panel — parameter table:
  One row per parameter; one column per node.  Table fills full page width.
  Rows are colour-coded:
    White  -- all nodes match
    Yellow -- mismatch (values differ between nodes)
    Teal   -- instance-specific value (log file name, instance number, etc.)
               auto-detected; shown separately; not counted as an error
    Blue   -- pending change (user has applied a resolution)
    Purple -- logical diff (expected to differ; not flagged as error)
    Striped -- file absent from this node (FILE ABSENT cell)

  KV files (.properties / .cfg / .ini / .conf / .sh) are compared section by
  section against the base node -- the first node in the audit config that has
  the file.  Each [section] header row shows a section check:
    base <node>: N param(s)   <node>: M match . D differ . X missing . +E extra
  or "section absent" when a node has the file but not that section.
    - A key is compared only within its section; the same key in two sections
      is two separate rows.
    - A commented header (#[Name]) is a comment: active keys below it belong
      to the real section above.
    - A commented-out key (#key=value) counts as present (shown greyed).
    - The same key twice in one section on a node shows every value with its
      line number, tagged "duplicate in section", and counts as a mismatch.
    - Keys before the first header appear under "(no section)".
    - "Show differences only" still shows a section header when that section
      is absent on a node.

  Files absent from some nodes are flagged with a MISSING badge in the
  sidebar and appear in the "files with differences" lists.

  For many-node sites (> 4 nodes):
    - Horizontal scroll bar appears; parameter column stays frozen at left.
    - Node selector chips above the table let you hide/show individual nodes.
    - Columns are resizable by dragging the column header divider.
    - Column widths are persisted in browser localStorage.

Mismatch navigation:
  "◀ Prev" and "Next ▶" buttons in the panel toolbar navigate between all
  mismatch rows across all files.
  Counter shows current position: "Mismatch 7 / 37"
  "Show differences only" toggle state is preserved when navigating between
  files — turning it on once keeps it on for the whole session.

Resolution controls (per mismatch row):
  Use for all   -- apply this node's value to all other nodes (pending)
  Override      -- type a custom value to apply to all nodes (pending)
  Add           -- for keys missing from some nodes: add the key
  Skip          -- mark this parameter as intentionally different;
                   excluded from patch export and per-node download
  Revert        -- undo pending change on individual node

Panel toolbar (sticky — always visible while scrolling):
  Show diffs only        -- hide all matched rows; show only mismatches
  Show instance-specific -- toggle teal instance-specific rows
  Show expected diffs    -- toggle purple logical-diff rows
  ◀ Prev / Next ▶        -- navigate between mismatch rows (cross-file)
  💾 Save All            -- save corrected config for every node with
                            pending changes to the configured output dir;
                            prompts for a path if no output dir is set
  Export Patch           -- download audit_patch.json with all pending
                            changes and skipped parameters
  Download (per node)    -- reconstruct and download corrected config for
                            a specific node

Navigation guard:
  If you navigate away from a file that has unsaved pending changes, a
  confirmation modal appears:
    Save & Continue      -- saves to output dir, then navigates (default)
    Continue Without Saving -- discards unsaved changes and navigates
    Cancel               -- stays on the current file
  Pressing Enter in the modal triggers "Save & Continue".

Session persistence:
  All pending changes, skipped state, change log, and output directory
  setting are automatically saved to browser localStorage on every
  mutation.  Refreshing the HTML page restores the full session state —
  no work is lost on accidental refresh.

Change Log panel:
  Tracks all pending changes in real time.
  Click to open/close the log modal.

Summary bar:
  Shows full-run totals: Files | With Diffs | Mismatches | Binary Diff |
  Absent Files | Errors.
  For paginated reports, a sub-bar shows this-part counts alongside run totals.

Skipped Files panel (bottom):
  Collapsible section listing all files that were skipped:
    Backup files auto-detected (with backup-suffix matched)
    Files excluded by --filter-file
  Each entry has a "📋 Copy rule" button that copies a JSON snippet to
  clipboard — paste into audit config's no_skip_files or filter file to
  include that file in future runs.

Print / PDF:
  Use browser Print — sidebar is hidden in print layout; only the main
  content panel is printed.


================================================================================
 APPLYING AN AUDIT PATCH
================================================================================

After resolving mismatches in the HTML report, export a patch file and apply it:

Step 1 — Export the patch from the HTML report:
  Click "Export Patch" in the panel toolbar.
  Save the downloaded  audit_patch.json.

Step 2 — Apply the patch:
  configmergetool \
    --apply-audit-patch audit_patch.json \
    --audit-config-file audit.json \
    --output-dir corrections/

  The tool writes corrected config files to  corrections/<node>/<file>.
  A  corrections.log  lists every change applied.

Exit codes:
  0  -- patch applied successfully with no warnings
  1  -- mismatches remain after applying patch (review corrections.log)
  2  -- patch file invalid or no changes to apply


================================================================================
 FEEDBACK ACCUMULATOR
================================================================================

Every audit run appends a summary to:
  ~/.configmergetool/feedback_history.json

This records: timestamp, site name, nodes, backup files skipped, logical
diffs found, log-name warnings, and filtered files.

View a summary across all past runs:
  configmergetool --feedback-summary

The feedback file can be sent to the tool developer to help improve built-in
backup-detection patterns and logical-diff heuristics.


================================================================================
 LOG FILE PREFIX UNIQUENESS DETECTION
================================================================================

After every audit run, the tool checks whether any log-related config keys
share the same value across multiple nodes.  If two nodes use the same log
file prefix, they may write to the same file on a shared filesystem.

Keys checked (pattern-based):
  log.file, log.prefix, *.log, *.prefix, *.logfile,
  snmp.trap-file.prefix, kpi.stats.prefix, etc.

Warnings are written to:
  <run_dir>/feedback/log_name_warnings.json

and shown in the HTML report with an orange badge.


================================================================================
 CHANGE CATEGORIES
================================================================================

Merge mode (MergeCategory in Excel / HTML):

  BASE_TO_RELEASE_REPLACED       KV key: release value replaced by base value
  XML_BASE_TO_RELEASE_REPLACED   XML element: release element replaced by base
  JSON_BASE_TO_RELEASE_REPLACED  JSON key: release value replaced by base value
  LOGROTATE_BASE_TO_RELEASE_REPLACED  Logrotate file replaced from base

  BASE_ONLY_PARAMETER_ADDED      Parameter in base only -- inserted into output
  RELEASE_ONLY_PARAMETER_ADDED   Parameter in release only -- kept as-is
  EXCLUDED_BASE_ONLY_PARAMETER   Base-only parameter excluded by flag

  EMPTY_BASE_OVERRIDE            *** KV: base value empty -- review required ***
  EMPTY_BASE_OVERRIDE_XML        *** XML: base element empty -- review required ***
  JSON_EMPTY_BASE_OVERRIDE       *** JSON: base value "" -- review required ***
  LOGROTATE_EMPTY_BASE_OVERRIDE  *** Logrotate: base file empty -- review required ***

  DUPLICATE_KEY                  Duplicate ACTIVE key in release file
  INVALID_JSON                   Input file contains invalid JSON
  INVALID_OUTPUT_JSON            Merged JSON output failed validation
  FILE_MAPPING                   Explicit mapping from --mapping-file applied
  BASE_ONLY_FILE_COPIED          File copied as-is from --copy-baseonlyconfigfile
  UNCOMMENT_REPLACE              Commented-out key uncommented and set from base
  NAMESPACE_ADAPTED              XML namespace updated to match release
  INDEXED_GROUP_RENUMBERED       Indexed group entries renumbered
  INDEXED_GROUP_APPENDED         Release-only indexed groups appended
  COMMA_VALUE_UNION              Comma-separated group header value merged as union
  SSTP_RELEASE_COPIED            .sstp routing rule: release file copied as-is
  PROCESSOR_ERROR                Processor encountered an error (review log)


================================================================================
 EXIT CODES
================================================================================

Merge mode:
  0  -- merge completed; no EMPTY_BASE_OVERRIDE or critical errors
  1  -- one or more critical issues found (EMPTY_BASE_OVERRIDE, INVALID_JSON,
         PROCESSOR_ERROR); review the Excel report

Audit mode:
  0  -- audit completed; all nodes match (or all differences are logical diffs)
  1  -- one or more mismatches found between nodes; review audit_report.html

Patch mode:
  0  -- patch applied successfully
  1  -- residual mismatches after patch
  2  -- patch invalid or nothing to apply


================================================================================
 COMPLETE MERGE EXAMPLE WITH ALL OPTIONS
================================================================================

Directory layout:
  base/
    config/
      app.properties
      server.xml
      openapi.json
      ssl/server.keystore   <- binary, copy as-is
  release/
    config/
      application.properties  <- different name from base app.properties
      server.xml
      openapi.json

mapping-file.txt:
  base/config/app.properties = release/config/application.properties

copy-only.txt:
  base/config/ssl/server.keystore

Command:
  configmergetool \
    --base-dir base \
    --release-dirs release \
    --output-dir output \
    --mapping-file mapping-file.txt \
    --copy-baseonlyconfigfile copy-only.txt \
    --verbose

Output:
  output/
    config/
      application.properties  <- merged
      server.xml               <- merged
      openapi.json             <- merged
      ssl/server.keystore      <- copied as-is from base

  reports/
    run_20260401_143022/
      merge_report_base.xlsx
      merge_diff.html
      log_merge_config.log


================================================================================
 COMPLETE AUDIT EXAMPLE
================================================================================

audit.json:
  [
    {
      "base_dir": "prod/GTPProxy-APP-01",
      "name":     "APP-01",
      "no_skip_files": ["fsmapp.properties_couchbase"]
    },
    {
      "base_dir": "prod/GTPProxy-APP-02",
      "name":     "APP-02"
    }
  ]

filters.txt:
  properties
  cfg
  xml
  json
  conf::sysctl.conf,sctp.conf
  !nohup.out

Command:
  configmergetool \
    --audit-config-file audit.json \
    --filter-file filters.txt \
    --quiet

Results:
  Console shows only DIFF / WARN / ERROR / SUMMARY lines.
  reports/audit_20260401_143022/
    audit_report.html          <- open in browser
    audit.xlsx
    audit.log
    feedback/
      skipped_backups.json     <- review for false positives
      filtered_files.json
      logical_diff_summary.json
      log_name_warnings.json

Apply corrections:
  # 1. Open audit_report.html in browser
  # 2. Resolve mismatches using Use-for-all / Override / Skip
  # 3. Click "Export Patch" → save audit_patch.json
  # 4. Apply:
  configmergetool \
    --apply-audit-patch audit_patch.json \
    --audit-config-file audit.json \
    --output-dir corrections/


================================================================================
 ENGINEER DO'S AND DON'TS
================================================================================

DO:
  - Install into a virtual environment to avoid polluting system Python.
  - Keep audit.json in version control — it is configuration, not disposable.
  - Store audit output reports by date (tool does this automatically).
  - Run --feedback-summary periodically to spot recurring patterns.
  - Review feedback/skipped_backups.json after every audit run.
  - Use --quiet for scheduled / CI jobs to keep logs clean.
  - Use --dry-run before the first merge against a new site to preview changes.

DON'T:
  - Do NOT install with sudo pip install (system-wide install risks breaking OS tools).
  - Do NOT put passwords in audit.json — use "password_env" fields only.
  - Do NOT delete reports/ and logs/ before backing up — they are change evidence.
  - Do NOT use --output-dir pointing to a live production directory.
  - Do NOT run multiple concurrent jobs targeting the same --output-dir.
  - Do NOT ignore the exit code in CI pipelines — exit 1 means action is required.
  - Do NOT upgrade mid-audit — complete and apply the patch before upgrading.


================================================================================
 VERSION HISTORY
================================================================================

v2.0.1 (2026-04-07) — Audit report UX improvements
  + Index page "Files with differences" quick-list above directory tree
  + Deep-link navigation from index page to specific files in part pages
  + Sidebar "Diffs only" filter auto-enables when diffs are a minority of files
  + "Show differences only" panel toggle now persists across file navigation
  + Sticky toolbar layout fix — visible regardless of pagination bars (no
    more hardcoded 108px offset; uses CSS flex column layout)
  + Per-part sub-bar showing this-part file/diff/mismatch counts
  + Instance-specific value auto-detection (log paths, instance numbers)
    shown in teal — separate toggle; not counted as errors
  + Absent-file mismatch fix: KV and JSON files missing from some nodes now
    correctly appear in the "files with differences" list (was broken for
    KV/JSON; binary/text/SSTP already worked)
  + Full-width table layout: removed double table-wrap; XML raw content
    no longer capped at 500px height
  + Skipped files panel: "Copy rule" clipboard button per skipped file
  + HTML sanity check before write: DOCTYPE/script-tag balance/parse validation;
    warns to stderr if issues detected

v2.0.0 (2026-04-06)
  + Audit mode: multi-node configuration drift detection
  + Interactive HTML audit report with Use-for-all / Override / Skip / Revert
  + Audit patch export and --apply-audit-patch patcher
  + Backup file auto-detection and skipping
  + File/directory filter (--filter-file)
  + HTML report pagination for large audits (> 22 MB split into parts)
  + Next/Prev mismatch navigation with position counter
  + Resizable table columns with localStorage persistence
  + Node visibility chip controls for many-node sites
  + Sticky parameter column on horizontal scroll
  + Log file prefix uniqueness detection
  + Logical diff summary JSON
  + Cross-run feedback accumulator (~/.configmergetool/feedback_history.json)
  + SSTP routing rule semantic diff (VALUE / ORDER / STRUCT_EQUIV / MATCH)
  + .sstp copy-only processor for merge mode
  + Shared _open_text() encoding helper (utf-8-sig → chardet → latin-1)
  + SHA-256 binary file comparison in audit mode
  + Excel: freeze_panes, auto_filter, auto row heights on all sheets
  + --quiet flag to suppress MATCH lines in console output
  + --feedback-summary subcommand
  + --version flag
  + pip-installable wheel (configmergetool entry point)
  + pyproject.toml with optional extras [encoding] [ssh] [email] [all]
  + KV line fidelity: unchanged lines emitted verbatim (spacing preserved)
  + Comment merge policy: base comments kept for unchanged parameters
  + Section header raw line fidelity
  + Audit patcher preserves inline comments after changed values
  + Exit code 1 from audit mode when mismatches exist (was always 0)
  + Path-traversal guard in audit _scan_dir() via safe_realpath()
  + NodeFetcher abstraction for Phase 11 SSH/Phase 12 email (stubs)

v1.x
  + Merge mode: KV, XML, JSON, logrotate, generic processors
  + Multi-base merge (one pass per node via --base-config-file)
  + Mapping file and copy-only file support
  + 3-way diff HTML report (Base | Release | Output)
  + Interactive HTML merge report with sidebar and file tree
  + 6-sheet Excel report
  + --exclude-params-in-baseonlyconfig
  + --dry-run
  + Indexed group renumbering, comma-value union, shadow section handling
  + Duplicate key detection (release-file active keys only)
