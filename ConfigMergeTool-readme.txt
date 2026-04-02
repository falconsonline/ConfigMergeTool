================================================================================
 ConfigMergeTool — User Guide
================================================================================

WHAT IT DOES
------------
ConfigMergeTool merges configuration files from a base (production/site)
directory into a release (new software release) directory, producing a merged
output directory.

Merge rule:  BASE VALUES WIN.
  - If a key/element exists in both base and release → use the BASE value.
  - If a key/element exists only in base             → add it to output.
  - If a key/element exists only in release          → keep it in output.

Typical use case:
  A production node has customised configs (base/).
  A new software release ships updated default configs (release/).
  This tool creates merged configs (output/) that carry the site's
  customisations forward onto the new release baseline.


REQUIREMENTS
------------
  Python 3.9+
  pip install openpyxl


QUICK START
-----------
  python3 ConfigMergeTool.py \
    --base-dir base \
    --release-dirs release \
    --output-dir output \
    --verbose


FULL CLI REFERENCE
------------------

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


================================================================================
 SINGLE-BASE EXAMPLE
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

  python3 ConfigMergeTool.py \
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

PATH FORMAT (important — paths are relative to the working directory):

  Preferred:
    base/config/fsmapp.cfg = release/config/app.properties

    Use the full path from the working directory for both sides.
    This makes mappings unambiguous regardless of the base_dir name.

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

Command:

  python3 ConfigMergeTool.py \
    --base-dir base \
    --release-dirs release \
    --output-dir output \
    --mapping-file mapping-file.txt

Without a mapping file:
  Files are matched by filename only (e.g. both called "app.properties").
  If a filename exists in multiple base locations the match is ambiguous
  and the file is skipped with a WARNING.

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

PATH FORMAT (important — paths are relative to the working directory):

  Preferred:
    base/config/ssl/server.keystore

    Use the full path from the working directory.  If the base_dir is
    "base", the path starts with "base/".  If the base_dir is
    "singtel/Singtel-APP-01", the path starts with
    "singtel/Singtel-APP-01/".

  Also accepted (backward compatible):
    config/ssl/server.keystore   <- bare path relative to within base dir

Example — copy-only.txt (base_dir = "base"):

  # Certificates - always use production versions
  base/config/ssl/server.keystore
  base/config/ssl/truststore.jks

  # Licence file
  base/config/licence.dat

  # Shell script with site-specific paths hardcoded
  base/bin/start.sh

Example — copy-only.txt (base_dir = "singtel/Singtel-APP-01"):

  singtel/Singtel-APP-01/config/InterfaceConfig.xml
  singtel/Singtel-APP-01/config/ssl/server.keystore

Command:

  python3 ConfigMergeTool.py \
    --base-dir base \
    --release-dirs release \
    --output-dir output \
    --copy-baseonlyconfigfile copy-only.txt

These files appear in the "BaseConfigAsIs" sheet of the Excel report and
are listed separately from merged files.


================================================================================
 MULTI-BASE USAGE (multiple production nodes)
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
      "base_dir":       "base/node2",
      "name":           "prod-us",
      "mapping_file":   "mappings/node2-mapping.txt"
    },
    {
      "base_dir":       "base/node3",
      "name":           "prod-ap"
    }
  ]

Fields:
  base_dir       (required)  Path to this node's base config directory
  name           (optional)  Display name; defaults to the directory's folder name
  mapping_file   (optional)  Per-node mapping file
  copy_only_file (optional)  Per-node copy-only list

  Paths in mapping_file and copy_only_file must use the full working-directory
  path format (e.g. "base/node1/config/file.properties"), not paths relative
  to within the base_dir.

Command:

  python3 ConfigMergeTool.py \
    --base-config-file base-configs.json \
    --release-dirs release \
    --output-dir output \
    --verbose

Output structure:

  output/
    prod-eu/
      config/app.properties
      config/server.xml
    prod-us/
      config/app.properties
      config/server.xml
    prod-ap/
      config/app.properties
      config/server.xml

  reports/
    run_20260401_143022/
      merge_report_prod-eu.xlsx
      merge_report_prod-us.xlsx
      merge_report_prod-ap.xlsx
      merge_diff.html           <- all nodes in one HTML file
      log_merge_config.log


================================================================================
 DRY-RUN EXAMPLE
================================================================================

Preview what will change without writing any output config files.
The full report (Excel + HTML) is still generated.

  python3 ConfigMergeTool.py \
    --base-dir base \
    --release-dirs release \
    --output-dir output \
    --dry-run \
    --verbose

Output files are NOT written.
Reports and log ARE written to: reports/run_YYYYMMDD_HHMMSS/


================================================================================
 EXCLUDE BASE-ONLY PARAMETERS
================================================================================

By default, parameters that exist only in the base file (no release
counterpart) are inserted into the merged output.

Use --exclude-params-in-baseonlyconfig to suppress this.

Example:
  base/config/app.properties contains:
    legacy.timeout=30000      <- not in release

  Without flag:  output/config/app.properties includes  legacy.timeout=30000
  With flag:     output/config/app.properties does NOT include legacy.timeout

The excluded parameters are recorded in the ExcludedBaseOnlyParams sheet
of the Excel report so they can be reviewed.

  python3 ConfigMergeTool.py \
    --base-dir base \
    --release-dirs release \
    --output-dir output \
    --exclude-params-in-baseonlyconfig


================================================================================
 MERGE BEHAVIOUR BY FILE TYPE
================================================================================

.properties / .cfg / .ini / .conf / .sh  (Key-Value files)
-----------------------------------------------------------
  Sections ([section]) are tracked independently.
  For each key in base:
    - If key exists in release (active) -> output gets BASE value.
    - If key only in base               -> inserted into output (unless --exclude flag).
    - If base value is empty            -> release value is forced empty (EMPTY_BASE_OVERRIDE).
  For each key only in release:
    - Kept as-is in output.

  Comment handling:
    - Comment/blank lines above a key are preserved.
    - If both files have different comments for the same key, release comment
      is preferred in output.

  Annotation handling:
    - A commented line before an active key is a PRE-ANNOTATION:
        #event.list=UCGDML       <- pre-annotation: the old value
        event.list=UCM           <- active key
      The pre-annotation is emitted verbatim before the merged active entry.
    - A commented line AFTER an active key is a POST-ANNOTATION:
        event.list=UCM           <- active key
        #event.list=UCGDMLS      <- post-annotation: alternative value
        #event.list=UCGDMLug     <- post-annotation: another alternative
      Post-annotations are preserved verbatim after the active entry.

  Shadow sections:
    - If base has an entire section commented out:
        #[DBHandler]
        #PostgreSQL=...
        #Oracle=...
      AND release has the same section active:
        [DBHandler]
        PostgreSQL=...
      THEN output keeps all entries commented (base comment-state wins):
        [DBHandler]
        #PostgreSQL=...
        #Oracle=...

  Indexed group handling:
    - Keys matching prefix.N.subkey (e.g. schedule.1.name, schedule.2.name)
      form indexed groups.
    - Base groups are retained in order.
    - Release-only groups are appended after base groups with renumbered indices.
    - prefix.count is updated to the final group total.
    - Comma-separated header values (e.g. schedule.registry) are merged as a
      union of base + release values.

  Section ordering:
    - Sections follow the release file order.
    - Base-only sections are inserted at their natural relative position
      (immediately before the release section that follows them in base),
      NOT appended at the end.

  Duplicate key detection:
    - Only ACTIVE duplicate keys in the release file are flagged (DUPLICATE_KEY).
    - Commented entries alongside active entries are treated as annotations,
      not duplicates, and are never flagged.
    - Base duplicate keys are resolved silently (last value wins) without
      appearing in the HTML or Excel report.

  Example:
    base/app.properties:      release/app.properties:
      db.host=prod-db-01        db.host=localhost
      db.port=5432              db.port=5432
      db.pool.size=20           db.pool.size=10
                                db.timeout=30

    output/app.properties:
      db.host=prod-db-01        <- base value wins
      db.port=5432              <- same in both
      db.pool.size=20           <- base value wins
      db.timeout=30             <- release-only, kept as-is

.xml / .xsd  (XML files)
------------------------
  Elements are matched by tag name + "name" attribute.
  For each element in base:
    - If element exists in release -> output gets BASE element block verbatim.
    - If element only in base      -> inserted into output.
    - If base element is empty     -> release element forced empty (EMPTY_BASE_OVERRIDE_XML).
  For each element only in release:
    - Kept as-is.
  Release namespace declarations are preserved exactly in output.
  XML comments are captured and associated with the following element.

  Example:
    base/server.xml:                 release/server.xml:
      <Connector port="8443"           <Connector port="8080"
        scheme="https"                   scheme="http"
        SSLEnabled="true"/>              SSLEnabled="false"/>

    output/server.xml:
      <Connector port="8443"           <- entire base element used
        scheme="https"
        SSLEnabled="true"/>

.json  (JSON files)
-------------------
  Deep recursive merge: base values overwrite matching release values at any
  nesting depth.  Release-only keys at any depth are preserved.

  Example:
    base/config.json:            release/config.json:
      {                            {
        "server": {                  "server": {
          "host": "prod-host",         "host": "localhost",
          "port": 9090                 "port": 8080,
        }                              "timeout": 30
      }                            }
                                 }

    output/config.json:
      {
        "server": {
          "host": "prod-host",    <- base value wins
          "port": 9090,           <- base value wins
          "timeout": 30           <- release-only, preserved
        }
      }

.logrotate  (Logrotate files)
------------------------------
  Entire base file is copied to output verbatim.
  If the base file is empty, output is written as empty (LOGROTATE_EMPTY_BASE_OVERRIDE).

All other extensions  (Generic)
--------------------------------
  File is copied from the release directory as-is.
  No merge is performed.  A log entry is written.


================================================================================
 OUTPUT STRUCTURE PER RUN
================================================================================

All report artifacts for a run land in one timestamped directory so
they can be archived together.

  reports/
    run_YYYYMMDD_HHMMSS/        <- one folder per run
      merge_diff.html           <- interactive HTML diff report
      merge_report_<base>.xlsx  <- Excel report (one per base dir)
      log_merge_config.log      <- full debug log for this run

To archive a run:
  zip -r run_20260401_143022.zip reports/run_20260401_143022/


================================================================================
 EXCEL REPORT -- 6 SHEETS
================================================================================

Sheet 1: MergeChanges
  All parameter-level changes.
  Columns: File | MergeCategory | ParameterName | ReleaseValue | BaseValue | Detail
  Colour coding:
    Red    -- EMPTY_BASE_OVERRIDE, DUPLICATE_KEY, INVALID_JSON (require review)
    Yellow -- BASE_ONLY_PARAMETER_ADDED (parameter added from base)
    Orange -- RELEASE_ONLY_PARAMETER_ADDED (release parameter kept as-is)

Sheet 2: BaseOnlyFiles
  Config files found in base dir with no release counterpart.
  These files are not merged or copied unless listed in --copy-baseonlyconfigfile.

Sheet 3: ReleaseOnlyFiles
  Config files found in release dir with no base counterpart.
  These files are passed through to output unchanged.

Sheet 4: FileMappings
  Explicit base <-> release file mappings that were applied from --mapping-file.
  Columns: BaseConfigFileName | ReleaseConfigFileName

Sheet 5: ExcludedBaseOnlyParams
  Parameters that exist only in base and were excluded from output due to
  --exclude-params-in-baseonlyconfig.
  Columns: File | Parameter | BaseValue

Sheet 6: BaseConfigAsIs
  Files that were copied from base without merge processing, listed in
  --copy-baseonlyconfigfile.
  Column: FilePath


================================================================================
 HTML REPORT
================================================================================

Opens in any browser.  Self-contained (no internet connection needed).

Left sidebar:
  File-system tree of all processed files.
  Click a file name to jump to its section.
    -> The file HEADER is scrolled into view (not the body), so the
       "Show Full Config" and "3-Way Diff" buttons are immediately
       visible without further scrolling.
  Search box to filter files by name.
  Collapse/expand directories.

File sections (right panel):
  Each processed file has a collapsible section showing all changes.
  Click the file header to expand or collapse.

  "Show Full Config" button:
  Toggles between:
    - Changes-only view: lists each changed parameter with old/new values.
    - Full Config Diff:  shows the entire merged output file side-by-side
      with the release file.  Left = release (before), Right = output (after).

  Full Config Diff colours:
    White  -- line unchanged between release and output
    Yellow -- line differs: release value replaced by base value
    Green  -- line added in output (base-only parameter, not in release)
    Red    -- line in release not carried to output

  "3-Way Diff" button:
    Three-column view: Base (left) | Release (centre) | Merged Output (right).
    Useful for verifying that base values were correctly applied over release.

  Duplicate Key entries:
    Only release-file duplicates are shown (base duplicates resolved silently).
    Shows all duplicate values found and which final value was used.

  Legend bar (bottom of screen -- always visible):
    Colour meanings shown in a fixed bar at the bottom of the browser window
    regardless of scroll position.  Hover over any legend item to see a full
    explanation.

Toolbar:
  Filter buttons: All Changes | Empty Override | Base-Only | Release-Only
  Collapse All / Expand All


================================================================================
 CHANGE CATEGORIES (MergeCategory in Excel / HTML)
================================================================================

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

  DUPLICATE_KEY                  Duplicate ACTIVE key in release file -- last value used
  INVALID_JSON                   Input file contains invalid JSON
  INVALID_OUTPUT_JSON            Merged JSON output failed validation
  FILE_MAPPING                   Explicit mapping from --mapping-file applied
  BASE_ONLY_FILE_COPIED          File copied as-is from --copy-baseonlyconfigfile
  UNCOMMENT_REPLACE              Commented-out key uncommented and set from base
  NAMESPACE_ADAPTED              XML namespace updated to match release
  INDEXED_GROUP_RENUMBERED       Indexed group entries renumbered
  INDEXED_GROUP_APPENDED         Release-only indexed groups appended after base groups
  COMMA_VALUE_UNION              Comma-separated group header value merged as union


================================================================================
 COMPLETE EXAMPLE WITH ALL OPTIONS
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
  output/                     <- created by tool

mapping-file.txt:
  base/config/app.properties = release/config/application.properties

copy-only.txt:
  base/config/ssl/server.keystore

Command:
  python3 ConfigMergeTool.py \
    --base-dir base \
    --release-dirs release \
    --output-dir output \
    --mapping-file mapping-file.txt \
    --copy-baseonlyconfigfile copy-only.txt \
    --verbose

Output:
  output/
    config/
      application.properties  <- merged (base app.properties + release application.properties)
      server.xml               <- merged
      openapi.json             <- merged
      ssl/server.keystore      <- copied as-is from base

  reports/
    run_20260401_143022/
      merge_report_base.xlsx
      merge_diff.html
      log_merge_config.log
