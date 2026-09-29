================================================================================
 ConfigMergeTool v3.0.2 — User Guide
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

An illustrated version of the installation and user guide, with the same
config file reference, is in  docs/ConfigMergeTool-guide.html  (open it in
any browser; it works offline).


================================================================================
 REQUIREMENTS & INSTALLATION
================================================================================

Requirements
------------
  Python 3.9+
  Libraries installed automatically with the wheel:
    openpyxl  (+ et_xmlfile)  -- Excel reports
    PyYAML                    -- audit compares YAML files by structure
  Optional: chardet ([encoding]) -- detects non-UTF-8 file encodings

--------------------------------------------------------------------------------
 LINUX / macOS INSTALLATION
--------------------------------------------------------------------------------

Step 1 — Create a virtual environment (recommended):

  python3 -m venv ~/venv
  source ~/venv/bin/activate

Step 2 — Install from wheel:

  pip install configmergetool-3.0.2-py3-none-any.whl

  # With optional auto-encoding detection (recommended for non-UTF-8 sites):
  pip install "configmergetool-3.0.2-py3-none-any.whl[encoding]"

  # With all optional extras:
  pip install "configmergetool-3.0.2-py3-none-any.whl[all]"

Step 3 — Verify:

  configmergetool --version
  configmergetool --help

To deactivate the virtual environment when done:
  deactivate

--------------------------------------------------------------------------------
 INSTALLING INTO A FOLDER YOU CHOOSE (no admin / sudo)
--------------------------------------------------------------------------------

Everything is installed below ONE folder you pick, e.g. ~/venv (= /home/user/venv).
Nothing goes to /usr, /opt, /etc or the system Python's site-packages.

  INSTALL_DIR=~/venv                              # any folder you can write to
  [ -x "$INSTALL_DIR/bin/python" ] || python3 -m venv "$INSTALL_DIR"   # reuse if it exists
  "$INSTALL_DIR/bin/pip" install --no-cache-dir \
      "configmergetool-3.0.2-py3-none-any.whl[encoding]"
  "$INSTALL_DIR/bin/configmergetool" --version     # configmergetool 3.0.2

Resulting layout (Linux/macOS; Windows uses Scripts\ and Lib\ instead):

  /home/user/venv/
    bin/configmergetool        <- the command you run
    bin/python, bin/pip        <- private Python + pip for this install
    bin/activate               <- optional: "source" it to put bin/ on PATH
    bin/chardetect             <- from chardet (only with [encoding])
    lib/python3.X/site-packages/
      configmerge/             <- ConfigMergeTool code
      openpyxl/  et_xmlfile/   <- required libraries
      yaml/                    <- required library (PyYAML)
      chardet/                 <- optional library ([encoding])
      *.dist-info/             <- package metadata (used by pip)
    pyvenv.cfg                 <- records which Python created the folder
  A new folder holding only this tool is about 21 MB with [encoding].

Run it without typing the full path (pick one):
  mkdir -p ~/.local/bin                                  # link ONLY this command
  ln -sf ~/venv/bin/configmergetool ~/.local/bin/configmergetool
  # (~/.local/bin must be on PATH: add  export PATH="$HOME/.local/bin:$PATH"
  #  to ~/.bashrc or ~/.zshrc if it is not)
  source ~/venv/bin/activate                             # or activate per session
  Do not put ~/venv/bin itself on PATH permanently: its python3 and pip
  would then replace your normal ones in every terminal.

What is written OUTSIDE the install folder:
  At install time:  nothing (with --no-cache-dir; otherwise pip caches
                    downloads in ~/.cache/pip on Linux,
                    ~/Library/Caches/pip on macOS).
  At run time:      reports/ and logs/ under the folder you run from
                    (or --report-dir / --log-dir), and
                    ~/.configmergetool/feedback_history.json (audit runs).

Rules for this folder:
  - Create it where it will stay. The scripts in bin/ record the full
    path, so a moved or copied folder stops working
    ("bad interpreter"). To move it, delete it and create it again.
  - It uses the Python it was created with (the "home" line in
    pyvenv.cfg). If that Python is removed or upgraded to a new minor
    version, create the folder again.
  - Uninstall: "~/venv/bin/pip uninstall configmergetool". Delete the whole
    folder only if no other tool is installed in it (a shared ~/venv
    usually holds other packages too). ~/.configmergetool can be deleted
    if the run history is not needed.
  - Upgrading replaces only ConfigMergeTool (and openpyxl/chardet if a
    newer version is required); other packages in ~/venv are untouched.

Not recommended:  "pip install --prefix DIR" skips libraries the system
Python already has (the folder is not self-contained) and, like
"pip install --target DIR", only runs with PYTHONPATH pointing into it.

--------------------------------------------------------------------------------
 WINDOWS INSTALLATION
--------------------------------------------------------------------------------

Step 1 — Install Python 3.9+ from https://www.python.org/downloads/windows/
  During setup, tick "Add Python to PATH".

Step 2 — Open Command Prompt or PowerShell, create a virtual environment:

  python -m venv %USERPROFILE%\venv

Step 3 — Activate the virtual environment:

  Command Prompt:
    %USERPROFILE%\venv\Scripts\activate.bat

  PowerShell:
    %USERPROFILE%\venv\Scripts\Activate.ps1

  If PowerShell blocks script execution, first run (once, as Administrator):
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

Step 4 — Install from wheel (copy the .whl file to a local folder first):

  pip install configmergetool-3.0.2-py3-none-any.whl

  # With optional encoding detection:
  pip install "configmergetool-3.0.2-py3-none-any.whl[encoding]"

  # With all optional extras:
  pip install "configmergetool-3.0.2-py3-none-any.whl[all]"

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

To upgrade to a new .whl (e.g. from 3.0.1 to 3.0.2), activate your virtual
environment and run pip with --upgrade:

  # Linux / macOS
  source ~/venv/bin/activate
  pip install --upgrade configmergetool-3.0.2-py3-none-any.whl

  # Windows (Command Prompt)
  %USERPROFILE%\venv\Scripts\activate.bat
  pip install --upgrade configmergetool-3.0.2-py3-none-any.whl

  # Windows (PowerShell)
  %USERPROFILE%\venv\Scripts\Activate.ps1
  pip install --upgrade configmergetool-3.0.2-py3-none-any.whl

Confirm the new version is active:
  configmergetool --version

To check what is currently installed:
  pip show configmergetool

To list all installed packages in the environment:
  pip list

--------------------------------------------------------------------------------
 OFFLINE INSTALL ON RHEL 8 / RHEL 9 (no internet on the server)
--------------------------------------------------------------------------------

Use the bundle  configmergetool-3.0.2-rhel8-9-offline.tar.gz  (attached to
the GitHub release).  It holds the tool and every library it needs, built
for RHEL 8 and 9 on x86_64 and aarch64 with Python 3.9, 3.11 or 3.12:
  configmergetool 3.0.2, openpyxl 3.1.5, et_xmlfile 2.0.0, PyYAML 6.0.3,
  chardet (7.6.0 for Python 3.11/3.12, 5.2.0 for Python 3.9)
No root rights are needed; nothing is written outside the install folder.

  Python: RHEL 8's default python3 is 3.6 (too old).  The administrator
  installs one once:  sudo dnf install python39   (or python3.11/python3.12).
  RHEL 9's default python3 is 3.9 and works as is.

  tar xzf configmergetool-3.0.2-rhel8-9-offline.tar.gz
  cd configmergetool-3.0.2-rhel8-9-offline
  ./install.sh                         # into ~/configmergetool
  ./install.sh /opt/apps/cmt           # or any folder you can write to
  ~/configmergetool/bin/configmergetool --version     # configmergetool 3.0.2

  install.sh picks the newest Python 3.9+ it finds (set PYTHON=... to
  choose), creates a virtual environment and installs from the bundled
  wheels with pip --no-index.  On RHEL 8 with Python 3.11/3.12, if it
  reports that the environment could not be created, the system libraries
  are older than the Python package: sudo dnf update expat.

  Tested with the network cut off on Rocky Linux 8.9 and 9.3 (x86_64 and
  aarch64) with Python 3.9, 3.11 and 3.12, including an audit and a merge.

--------------------------------------------------------------------------------
 INSTALLATION OPTION B — RUN FROM SOURCE (no install needed)
--------------------------------------------------------------------------------

  pip install openpyxl PyYAML # the two hard dependencies
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
      (--base-dir BASE_DIR | --base-config-file BASE_CONFIG_FILE)
      --release-dirs RELEASE_DIR [RELEASE_DIR ...]
      --output-dir OUTPUT_DIR
      [--mapping-file MAPPING_FILE]
      [--copy-baseonlyconfigfile COPY_ONLY_FILE]
      [--exclude-params-in-baseonlyconfig]
      [--dry-run] [--verbose] [--report-dir DIR]

Option details:

  --base-dir PATH
      Base (production/site) config directory.
      Required unless --base-config-file is used.

  --base-config-file PATH
      JSON file listing several bases, one merge pass each.  When given,
      --base-dir, --mapping-file and --copy-baseonlyconfigfile are ignored
      (each base sets its own).  See CONFIGURATION FILES — REFERENCE, 2.

  --release-dirs PATH [PATH ...]
      One or more release config directories.
      Multiple release dirs are searched in order; first match wins.

  --output-dir PATH
      Directory where merged config files are written.
      When a base file and its release file differ only in whitespace
      (spaces, tabs, blank lines, line breaks), the release file is copied
      byte-for-byte instead of being merged [CMT-MRG-I003, log only].
      Cleaned and recreated on every run (skipped with --dry-run).
      Must not be, contain, or sit inside any base or release directory —
      such runs are refused before anything is deleted [CMT-MRG-E010], exit 2.
      Release files with no base counterpart are copied here as-is.
      Hidden files (names starting with '.') are ignored.
      A release file matched by filename to several base files is skipped
      [CMT-MRG-E002] — add a --mapping-file entry to choose the base.

  --mapping-file PATH
      Pairs base files with differently named release files
      (base_path = release_path).  See CONFIGURATION FILES — REFERENCE, 5.

  --copy-baseonlyconfigfile PATH
      Base files to copy to the output unchanged, without merging
      (licences, keystores, certificates).
      See CONFIGURATION FILES — REFERENCE, 6.

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

  --report-dir PATH
      Parent folder for the run folder reports/run_YYYYMMDD_HHMMSS/, which
      holds the Excel report(s), merge_diff.html and log_merge_config.log.
      Default: reports

  --log-dir PATH
      Accepted for backward compatibility and ignored: the log is written
      into the run folder under --report-dir.

  --version
      Print the installed version number and exit.


================================================================================
 FULL CLI REFERENCE — AUDIT MODE
================================================================================

  Audit:
  configmergetool
      --audit-config-file AUDIT_CONFIG_FILE
      [--filter-file FILTER_FILE]
      [--mapping-file MAPPING_FILE]
      [--quiet] [--report-dir DIR]

  Apply the corrections exported from the report:
  configmergetool
      --apply-audit-patch PATCH_JSON_FILE
      [--output-dir OUTPUT_DIR]
      [--audit-config-file AUDIT_CONFIG_FILE]

  Summary of past audit runs:
  configmergetool --feedback-summary

Option details:

  --audit-config-file PATH
      JSON list of the nodes to compare (the first node is the base).
      Selects audit mode — no merge is performed.
      See CONFIGURATION FILES — REFERENCE, 1.

  --filter-file PATH
      Which files are audited.  If omitted, every file is audited except
      the built-in binary types.  See CONFIGURATION FILES — REFERENCE, 3.

  --mapping-file PATH
      NODE/path=NODE/path pairs (files or folders) that compare files stored
      at different paths on different nodes in one report row.
      See CONFIGURATION FILES — REFERENCE, 4.

  --quiet
      Console shows only DIFF, WARN, ERROR and the SUMMARY line; MATCH lines
      are suppressed.  audit.log still records everything.

  --report-dir PATH
      Parent folder for the run folder reports/audit_YYYYMMDD_HHMMSS/.
      Default: reports

  --apply-audit-patch PATCH_JSON_FILE
      Apply a patch exported from the HTML report ("Export Patch").
      Source files are located through the "node_dirs" stored in the
      patch, so run it from the folder the audit ran in.
      Corrected files go to the first of: --output-dir, "output_dir" in the
      --audit-config-file given here, "output_dir" in the patch,
      <run_dir>/corrections.  See CONFIGURATION FILES — REFERENCE, 7.

  --feedback-summary
      Print a summary of all past audit runs recorded in the feedback
      accumulator (~/.configmergetool/feedback_history.json).
      Does not run an audit.

  --remote-audit, --email-config
      Reserved for planned remote (SSH) and email-triggered audits.  Both
      stop with an error today [CMT-CLI-E014, E015, E016].


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

Mapped paths (--mapping-file in audit mode):
  When the same file lives at a different path on another node (e.g. Staging
  "dra-SA" vs Prod/DR "dra-SA-1" and "dra-SA-2"), add
    --mapping-file Mapping.cfg
  with lines such as  STG/dra-SA=PROD/dra-SA-1.
  See CONFIGURATION FILES — REFERENCE, 4.

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
 CONFIGURATION FILES — REFERENCE
================================================================================

Every file the tool reads, which option points at it, and what it may hold.

  #  File                 Option                          Mode      Format
  -  -------------------  ------------------------------  --------  -----------
  1  Audit config         --audit-config-file             audit,    JSON array
                                                          patch
  2  Base config          --base-config-file              merge     JSON array
  3  Filter file          --filter-file                   audit     text
  4  Audit mapping file   --mapping-file                  audit     text
  5  Merge mapping file   --mapping-file, or              merge     text
                          "mapping_file" in a base config
  6  Copy-only file       --copy-baseonlyconfigfile, or   merge     text
                          "copy_only_file" in a base config
  7  Audit patch          --apply-audit-patch             patch     JSON object
  8  Email config         --email-config                  reserved  JSON object

Rules that apply to all of them:
  - Save them as UTF-8.
  - Relative paths, inside the files and on the command line, are resolved
    from the folder you run the command in.
  - JSON files must be strict JSON: no comments, no trailing commas, and
    double quotes around every key and string.
  - In the text files (3-6) a line whose first character is "#" is a
    comment, and blank lines are ignored.  Leading and trailing spaces on a
    line are ignored.
  - A config error stops the run before anything is compared or written,
    prints "[ERROR] [CMT-CLI-Ennn] ...", and exits with code 2.

--------------------------------------------------------------------------------
 1. AUDIT CONFIG FILE   (--audit-config-file)
--------------------------------------------------------------------------------

Lists the nodes to compare.  Also read by --apply-audit-patch for its
"output_dir" entry.

Format: a JSON array.  Each element is either a NODE ENTRY (it has
"base_dir") or the OUTPUT ENTRY (it has "output_dir" and no "base_dir").

The order matters: the first node is the base node.  Other nodes are
compared against it (for KV sections and text lines, the base is the first
node that has the file).

NODE ENTRY fields:

  Field           Type      Required  Default           Meaning
  --------------  --------  --------  ----------------  --------------------
  base_dir        string    yes       —                 Folder that holds
                                                        this node's copy of
                                                        the configuration.
                                                        It must exist.
  name            string    no        last folder of    Node name shown in
                                      base_dir          the report, used as
                                                        the folder name for
                                                        corrected files, and
                                                        usable as a prefix in
                                                        the mapping file.
                                                        Must be unique.
  no_skip_files   array of  no        []                File NAMES (not
                  strings                               paths) that are never
                                                        treated as backup
                                                        copies.  Lists from
                                                        all entries are
                                                        combined and apply to
                                                        every node.
  remote          object    no        —                 Reserved for the
                                                        planned SSH audit
                                                        (see below).

  Keys that are ignored in audit mode: "mapping_file" and "copy_only_file"
  (merge only; use --mapping-file for audit mapping).
  Keys that are refused: "password" (use "password_env" in "remote").

OUTPUT ENTRY:

  { "output_dir": "corrections/" }

  Where --apply-audit-patch writes corrected files when --output-dir is not
  given.  It is also stored in the report, so the page can show the target
  path of each download and the exported patch carries it.  Optional; if
  there are several, the last one is used.

REMOTE block (reserved — the SSH audit is not implemented yet;
--remote-audit stops with CMT-CLI-E016).  The block is validated already:

  Field           Type      Required  Default   Meaning
  --------------  --------  --------  --------  ------------------------------
  host            string    yes       —         Host name or IP address.
  port            integer   no        22        SSH port.
  username        string    no        ""        Login user.
  key_file        string    no        ""        Path to an SSH private key.
  password_env    string    no        ""        NAME of an environment
                                                variable holding the password.
  remote_path     string    no        ""        Remote folder, when different
                                                from base_dir.
  timeout_secs    integer   no        30        Connection timeout in seconds.

Example — minimal:
  [
    { "base_dir": "STG",  "name": "Staging" },
    { "base_dir": "PROD", "name": "Prod-Site" },
    { "base_dir": "DR",   "name": "DR-Site" }
  ]

Example — every supported field:
  [
    {
      "base_dir":      "sites/APP-01/config",
      "name":          "APP-01",
      "no_skip_files": ["server.xml_20240705_active", "GTPProxy.cfg_old_routes"]
    },
    { "base_dir": "sites/APP-02/config", "name": "APP-02" },
    { "output_dir": "corrections/" }
  ]

Example — remote node (reserved, validated but not run):
  [
    {
      "base_dir": "/opt/app/config",
      "name":     "APP-01",
      "remote": {
        "host":         "10.0.0.1",
        "port":         22,
        "username":     "appuser",
        "key_file":     "~/.ssh/prod_key",
        "password_env": "APP01_SSH_PASS",
        "timeout_secs": 30
      }
    }
  ]

Errors (exit 2):
  CMT-CLI-E001  file cannot be read, or is not valid JSON
  CMT-CLI-E002  the top level is not an array
  CMT-CLI-E003  an element is not an object
  CMT-CLI-E004  an element has neither "base_dir" nor "output_dir"
  CMT-CLI-E005  an element holds a literal "password"
  CMT-CLI-E006  two nodes have the same "name"
  CMT-CLI-E007  "remote" is not an object with "host"
  CMT-CLI-E008  "remote" holds a literal "password"
  CMT-CLI-E009  "port" or "timeout_secs" is not an integer
  CMT-CLI-E010  "base_dir" does not exist or is not a folder

--------------------------------------------------------------------------------
 2. BASE CONFIG FILE   (--base-config-file)
--------------------------------------------------------------------------------

Merges several bases (e.g. several production nodes) in one run: one
independent merge pass per base, all against the same --release-dirs.
When it is given, --base-dir, --mapping-file and --copy-baseonlyconfigfile
are ignored.

Format: a JSON array of objects, read by the same loader as the audit
config, so the same validation and errors (E001-E010) apply.

  Field           Type      Required  Default           Meaning
  --------------  --------  --------  ----------------  --------------------
  base_dir        string    yes       —                 This base's config
                                                        folder.
  name            string    no        last folder of    Output subfolder and
                                      base_dir          report name.  Must be
                                                        unique.
  mapping_file    string    no        none              Merge mapping file for
                                                        this base (section 5).
                                                        Must exist.
  copy_only_file  string    no        none              Copy-only file for
                                                        this base (section 6).
                                                        Must exist.

  Ignored in merge mode: "no_skip_files", "remote", and an
  {"output_dir": ...} entry (use --output-dir).

Output layout:
  With 2 or more entries each base gets its own subfolder:
    output/<name>/...                                 merged files
    reports/run_YYYYMMDD_HHMMSS/merge_report_<name>.xlsx
  With 1 entry the files go straight into output/, as with --base-dir.
  One merge_diff.html and one log_merge_config.log cover all bases.

Example — base-configs.json:
  [
    {
      "base_dir":       "base/node1",
      "name":           "prod-eu",
      "mapping_file":   "mappings/node1-mapping.txt",
      "copy_only_file": "mappings/node1-copy-only.txt"
    },
    { "base_dir": "base/node2", "name": "prod-us" }
  ]

Command:
  configmergetool --base-config-file base-configs.json \
    --release-dirs release --output-dir output

--------------------------------------------------------------------------------
 3. FILTER FILE   (--filter-file)
--------------------------------------------------------------------------------

Chooses which files are audited.  Without it every file is audited except
the built-in binary types (see i).  A complete commented example ships with
the tool: sample-filter.txt.

Format: one rule per line.  Matching is case-insensitive.  Paths use "/"
and are relative to each node's base_dir.

INCLUDE RULES — once a filter has at least one include rule, a file that no
include rule matches is skipped.

  a) Extension — every file with this extension (leading dot optional)
       properties
       yaml
       .xml
     "noext" means files with no extension at all (Makefile, start_app):
       noext

  b) Extension::file names — only these names, with this extension
       conf::sysctl.conf,sctp.conf,spread.conf
       txt::config.txt,system.txt

  c) Extension::folder names — files with this extension that sit in a
     folder with one of these names, at any depth.  The items are treated
     as folder names when NONE of them contains a ".":
       html::runtime,test

  d) Folder path — everything below this path (the line contains "/"):
       config/routing
       smartstp/configs

  e) Glob — file names matching a pattern (the line contains * ? or [).
     A glob that contains "/" is matched against the whole relative path:
       GTPProxy*
       *.jar.*
       config/*.xml

EXCLUDE RULES — start with "!".  They win over include rules.

  f) Name — a file with this exact name, and everything inside a folder
     with this name:
       !nohup.out
       !backup            (skips backup/, config/backup/, ...)

  g) Glob — file names matching a pattern:
       !*.swp
       !*.tmp

  h) Folder path — everything below this path (contains "/"):
       !logs/archive

FORCE-INCLUDE — starts with "+".  Wins over every exclude rule, for the
given path and everything below it.  It is not an include rule: a filter
with only "!" and "+" lines still audits every other file.

  j) +logs/archive/current-session

BUILT-IN BINARY TYPES

  i) These are skipped even without a filter file:
       .tar .gz .bz2 .xz .tgz .rpm .deb .zip .7z .rar .jar .war .ear
       .jks .keystore .p12 .pfx .pem .crt .cer .der .so .dll .exe .dylib
       .class .pyc .bin .img .iso
     To audit one of them, add its extension as an include rule (e.g. a
     line "jar").  Binary files are compared by SHA-256 checksum and size.

EVALUATION ORDER (first match decides):
  1. Force-include (+)              -> audited
  2. Excludes (!)                   -> skipped
  3. Include rules                  -> audited
  4. Built-in binary type           -> skipped
  5. No include rules in the file   -> audited
     Include rules present          -> skipped

Every skipped file is listed with its reason in
<run_dir>/feedback/filtered_files.json and the "Filtered Files" tab.

Example — typical Helm / application site:
  # text config types
  yaml
  yml
  tpl
  properties
  cfg
  conf
  xml
  json
  sstp
  txt::config.txt,system.txt
  # licences and certificates, compared by checksum
  lic
  crt
  # never audit
  !nohup.out
  !*.swp
  !logs/archive
  +logs/archive/current-session

--------------------------------------------------------------------------------
 4. AUDIT MAPPING FILE   (--mapping-file with --audit-config-file)
--------------------------------------------------------------------------------

Compares files that live at DIFFERENT paths on different nodes in one
report row, e.g. Staging runs one chart "dra-SA" while Prod and DR run two
instances "dra-SA-1" and "dra-SA-2".  Without it those files are reported
as absent.

Format: one pair per line.

  LEFT=RIGHT

  - Both sides start with a node prefix followed by "/" and the path inside
    that node.  The prefix can be the node's full base_dir, the last folder
    of its base_dir, or its "name" (the longest match wins).  A leading "/"
    is ignored and "\" is read as "/".
  - A side that ends at a FILE maps that file.  A side that names a FOLDER
    maps every file below it, keeping the rest of the path.
  - The LEFT file is shown in the report row of the RIGHT path.  One LEFT
    mapped to several RIGHTs appears in each of those rows, and its own row
    disappears (unless another node has a file at that path).
  - A file line wins over a folder line for the same row.
  - A node's own file at the RIGHT path is never replaced by a mapped one.

Example — Mapping.cfg:
  # Staging's single chart compared with each Prod/DR instance
  STG/dra-SA=PROD/dra-SA-1
  STG/dra-SA=PROD/dra-SA-2
  STG/dra-SA=DR/dra-SA-1
  STG/dra-SA=DR/dra-SA-2
  # one file only (overrides the folder line for this file)
  STG/smartstp/values.yaml=PROD/smartstp0/values.yaml
  # node names work as prefixes too
  Staging/smartstp/values.yaml=DR-Site/smartstp1/values.yaml

In the report a mapped node shows "↪ original/path" next to its name, and
its download button saves under the node's own file name.

Messages:
  CMT-AUD-W011  a pair was skipped because the file exists on only one side
                (listed in audit.log).  A pair missing on both sides —
                hidden, filtered or backup — is skipped silently.
  CMT-CLI-E018  a line has no "=", or a side does not start with a known
                node prefix, or the file cannot be read (exit 2).

--------------------------------------------------------------------------------
 5. MERGE MAPPING FILE   (--mapping-file in merge mode, or "mapping_file")
--------------------------------------------------------------------------------

Pairs a base file with a release file of a DIFFERENT name.  Files with the
same relative path, or a unique file name, are paired automatically; list
only the exceptions here.  A file name found more than once in the base is
never guessed [CMT-MRG-E002] — map it here.

Format: one pair per line.

  base_path = release_path

  - Spaces around "=" are allowed.  A line without "=" is ignored.
  - base_path may be: an absolute path, the base folder path followed by
    the file (base/config/app.cfg), the base folder's last name followed by
    the file (node1/config/app.cfg), or the path inside the base folder
    (config/app.cfg).
  - release_path may be: the release folder path or its last name followed
    by the file, or the path inside the release folder.  A leading "./" is
    dropped.
  - A base path that leads outside the base folder is skipped with a
    warning (PATH_TRAVERSAL).

  Many-to-one: several base files mapped to one release file are merged
  into it in the order of the lines; the FIRST base wins for any key the
  bases share, later bases only add what is missing [CMT-MRG-I001].
  One-to-many: one base file mapped to several release files is merged into
  each of them independently [CMT-MRG-I002].

Example — mapping.txt:
  # production calls it fsmapp.cfg, the release renamed it
  base/config/fsmapp.cfg = release/config/app.properties
  base/config/jetty-base.xml = release/config/jetty.xml
  # two base files -> one release file (db-primary wins on shared keys)
  base/config/db-primary.properties = release/config/database.properties
  base/config/db-replica.properties = release/config/database.properties
  # one base file -> two release files
  base/config/common.properties = release/config/app1.properties
  base/config/common.properties = release/config/app2.properties

The Excel FileMappings sheet lists every mapping that was applied.

--------------------------------------------------------------------------------
 6. COPY-ONLY FILE   (--copy-baseonlyconfigfile, or "copy_only_file")
--------------------------------------------------------------------------------

Base files that are copied to the output unchanged, with no merge: licences,
keystores, certificates, or any file whose production copy must be kept
exactly.

Format: one base file per line, in any of these forms:
  base/config/ssl/server.keystore     base folder path + file
  node1/config/ssl/server.keystore    base folder's last name + file
  config/ssl/server.keystore          path inside the base folder
  /abs/path/base/config/licence.dat   absolute path
A path that leads outside the base folder is skipped with a warning.

Example — copy-only.txt:
  # certificates: always keep the production copies
  base/config/ssl/server.keystore
  base/config/ssl/truststore.jks
  # licence
  base/config/licence.dat

--------------------------------------------------------------------------------
 7. AUDIT PATCH FILE   (--apply-audit-patch)
--------------------------------------------------------------------------------

Written by the report's "Export Patch" button as
audit_patch_<date>T<hhmm>.json, e.g. audit_patch_2026-09-25T1015.json.  You normally don't edit it; the fields
are listed so you can review it before applying.

  Field        Type     Meaning
  -----------  -------  ------------------------------------------------------
  audit_run    string   Time stamp of the audit run the patch came from.
  exported_at  string   When the patch was exported (ISO 8601).
  node_dirs    object   node name -> base_dir.  Source files are read from
                        here, so apply the patch from the same folder the
                        audit ran in.
  output_dir   string   "output_dir" from the audit config ("" if none).
  run_dir      string   The audit's report folder.
  changes      array    One element per corrected value (below).
  skipped      array    Rows marked "Skip" in the report: {file, compound}.
                        For the record only; nothing is applied from it.

  Each element of "changes":
  file         path of the file on that node (its mapped path, if mapped)
  file_type    "kv" or "json" — only these types can be corrected
  node         node name; becomes the folder name under the output folder
  compound     row identity: "[Section]|key" for KV, dotted path for JSON
  key          parameter name
  section      KV section ("" for none)
  original     value before the change (null when the key was added)
  corrected    new value
  action       "modified" (change a value) or "added" (add a missing key)

Where the corrected files go (first one that is set):
  1. --output-dir on the command line
  2. "output_dir" in the --audit-config-file given with the patch
  3. "output_dir" inside the patch
  4. <run_dir>/corrections

  configmergetool --apply-audit-patch audit_patch_2026-09-25T1015.json \
    --output-dir corrections/

Result: corrections/<node>/<path> for every changed file, plus
corrections.log.  The node folders themselves are never modified.
Exit 1 when any file was skipped or failed.

--------------------------------------------------------------------------------
 8. EMAIL CONFIG FILE   (--email-config)        RESERVED — not implemented
--------------------------------------------------------------------------------

Planned for an email-triggered audit.  Using the option today stops with
CMT-CLI-E014 (exit 2).  Planned format, for reference only:

  {
    "imap":   { "host": "mail.company.com", "port": 993,
                "username": "audit@company.com",
                "password_env": "AUDIT_EMAIL_PASS" },
    "smtp":   { "host": "mail.company.com", "port": 587 },
    "filter": { "subject_contains": "[AUDIT REQUEST]",
                "from_whitelist": ["ops@company.com"] },
    "audit_config_template": "audit-template.json"
  }

--------------------------------------------------------------------------------
 FILES THE TOOL KEEPS FOR ITSELF (not config — don't edit)
--------------------------------------------------------------------------------

  ~/.configmergetool/feedback_history.json
      One summary per audit run; read by --feedback-summary.  Delete it to
      clear the history.
  <run_dir>/feedback/*.json
      Skipped backups, filtered files, expected differences and log-name
      warnings of one audit run.


================================================================================
 BACKUP FILE AUTO-DETECTION
================================================================================

The auditor and merge automatically detect and skip backup files based on
their filename patterns and whether an active counterpart exists in the same
directory.  In merge mode a backup copy (base or release) is neither merged
nor copied to the output; it is listed as BACKUP_FILE_SKIPPED in the report
[CMT-MRG-I004].  For --base-config-file runs, "no_skip_files" in the base
config works the same way.

Auto-detected suffixes / patterns (case-insensitive):
  _bkp / .bkp / _bck / _bk / .bk / _bak / .bak / _backup / _orig / _org /
  _old / .old / _save
    followed by anything or nothing:  _bkp  _bkp_27072024  _bkp200821
                                      _bak17062026  _bkpprobetrouleshoot
  _DDMMYY  _DDMMYYYY  _YYYYMMDD  _YYYYMMDDHHmmss  (optionally followed by _...)
  The marker may follow the full name or sit before the extension:
    fsmapp.properties_bkp200821    ->  original fsmapp.properties
    fsmapp_240226.properties       ->  original fsmapp.properties
    dbwriter_bkp040322.cfg         ->  original dbwriter.cfg
  Version suffixes such as _v2 are NOT backups (gtpproxy_v2.mib is audited).
  Helm values files: values.yaml is the final version.  Any other file whose
  name contains "values" (values_DR.yaml, unedit_values.yaml, values_DRA1.yml,
  values.yamlbck, ...) is skipped as a backup when a values.yaml sits in the
  same folder (reason "values_backup").  values.schema.json is part of the
  chart and is audited.  To audit one of them anyway, list it in
  "no_skip_files".

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
  GTPProxy_bkp0209.cfg      <- detected as backup, skipped

Whitelist (opt out of auto-detection):
  In the audit config JSON, add "no_skip_files" to any node entry:
    { "base_dir": "prod/APP-01", "no_skip_files": ["server.xml_20240705_active"] }

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

.properties / .cfg / .ini / .conf / .acl  (Key-Value files)
  (.sh shell scripts are not key-value merged: the release copy is deployed as-is.)
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
    The replaced production class is also written directly above the line:
      # [CMT-MRG-W017] REVIEW: 'executor.class' production value was <class> ...

  API version upgrade:
    When base and release values look like different versions of the same
    third-party artifact (e.g. log4j-1.2.17.jar vs log4j2-2.17.1.jar),
    the release (newer) value is used and reported as API_VERSION_UPGRADED.

  Shadow sections:
    - If base has an entire section commented out AND release has the same
      section active, output keeps all entries commented (base state wins).
      A review annotation is written under the section header:
        # [CMT-MRG-W015] REVIEW: section [X] is commented out in base but active ...

  Report accuracy:
    - A key commented out in both files is a comment, not a release-only
      parameter.  EMPTY_BASE_OVERRIDE is raised only when base is empty and
      the release value is not.

  Commented lines (context):
    - Base comment lines are copied into the output next to the parameter
      they describe (never dropped); lines already in release are not duplicated.
    - "#key=alt" after an active "key=value" in base is kept right after the
      merged parameter.
    - A parameter commented out in base but active in release keeps the
      release value; the base comment and a review annotation are written
      directly above it for the user to confirm:
        #key=base-value
        # [CMT-MRG-W014] REVIEW: 'key' is commented out in base but active ...
        key=release-value
    - Spaces around a commented key ("#key = value") are ignored when that key
      is a real parameter in base or release; prose comments such as
      "# Database : description" stay plain comments.
    - Review annotation lines are never copied again when a merged output is
      used as the base of a later run.
    - A base comment whose value equals the value now active is not copied
      (it would only repeat the active line).
    - Comment lines are emitted byte-for-byte (trailing spaces kept).

  Indexed group handling:
    - Keys matching prefix.N.subkey (e.g. schedule.1.name) form indexed groups.
    - Groups are matched by their "name" subkey (prefix.N.name) when every
      base and release group has a unique name; otherwise by index N.
      A release group named like a base group is the same group even at a
      different index — base values win inside it.
    - Base groups retained; release-only groups appended and renumbered.
    - prefix.count keeps the base value.  When it differs from the merged
      group total it is flagged GROUP_COUNT_MISMATCH [CMT-MRG-W013]
      (highlighted in the report) so the count can be verified.
    - Comma-separated header values (e.g. schedule.registry) are merged as a
      union: base items in base order, then release items the base lacks.

  Section ordering:
    - Sections follow release file order.
    - A section header that appears more than once in a file keeps each
      block in its own place; base and release blocks are paired by
      occurrence (1st with 1st, 2nd with 2nd).
    - Blank lines and comments between sections are copied from the file;
      no blank lines are inserted, and the output ends exactly like the
      release file (same final newline / trailing blank lines).
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
  An empty object {} or array [] in base with a populated release value is
  flagged REVIEW_EMPTY_IN_BASE [CMT-MRG-W016] for the user to confirm (report
  and log only — JSON has no comments):
    {}  base predates the release keys -> release keys are taken
    []  base list intentionally empty  -> base (empty) list is kept
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
  In audit mode: blocks are compared on their original text across all
    nodes (whitespace ignored, comments count); labelled BLOCK_ABSENT,
    VALUE_DIFF, ORDER_DIFF or TEXT_DIFF.
  See "SSTP AUDIT DIFF" section below.

.yaml / .yml  (e.g. Helm values.yaml)
-------------------------------------
  Merged by structure, base values win -- the same rules as KV and JSON:
    - A value that differs is rewritten with the site value where it stands
      in the release file (BASE_TO_RELEASE_REPLACED).
    - A site-only map key or list entry is copied from the site file into the
      same section of the release file, with the release's indentation
      (BASE_ONLY_PARAMETER_ADDED; not added with
      --exclude-params-in-baseonlyconfig).
    - Release-only parameters are kept (RELEASE_ONLY_PARAMETER_ADDED).
  Parameters are matched as in audit mode (maps by key, list entries by their
  first field, instance blocks by position), so the order of entries never
  matters.  The release file's layout and comments are kept.
  A site value that cannot be written into the release layout (the release
  section is written inline, e.g. "pullSecrets: [a]", or empty, or the value
  is a section in one file and a single value in the other) is NOT forced:
  the release value stays and YAML_NOT_MERGED asks for review
  [CMT-MRG-W018].
  Files with template code ({{ }}, Helm templates) or invalid YAML keep the
  release copy; when the site copy differs this is reported as
  YAML_RELEASE_COPIED [CMT-MRG-W019].

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

Each block is one row showing every node's original block lines, exactly
as in the file (read-only).  A block is a mismatch when its text differs on
any node -- only whitespace (indentation, blank lines) is ignored; comments
count -- or when the block is missing on a node that has the file.  Lines
outside every block (e.g. header comments) get an "(outside blocks)" row when
they differ.  Nothing is treated as an expected difference automatically.

The row key carries a label (informational, worst over all nodes):
  BLOCK_ABSENT -- block missing on a node
  VALUE_DIFF   -- route target, SRC, SPC or DIGITS value differs
  ORDER_DIFF   -- same routes / digits in a different order
  TEXT_DIFF    -- any other change (statement moved, comment edited, ...)

Below the table the file content is shown side-by-side with changed lines
highlighted; "Show differences only" trims it to the changed hunks.


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
      audit_diffs.xlsx          <- Excel diff workbook
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

  Shell scripts (.sh) are compared as plain text.
  XML and other text files (yaml, tpl, txt, md, ...) are compared with all
  whitespace ignored: nodes that differ only in indentation, blank lines or
  line endings match (noted as [CMT-AUD-I001]).
  When their content differs, each node is compared line by line with the
  first node that has the file; every changed block becomes a yellow row
  under "File checksum" (e.g. "L88-L91") showing each node's lines, counted
  as one mismatch and reachable with Prev/Next.  "Show" scrolls the
  side-by-side view, where changed lines are highlighted with line numbers
  (on each node only the lines that differ from the first node; on the first
  node the lines some other node changed).
  With "Show differences only" ticked the side-by-side view lists just the
  changed blocks, each with 3 unchanged lines above and below, lined up
  across nodes; skipped stretches show as "... N unchanged lines" and a node
  without lines in a block shows "no line here -- between L<a> and L<a+1>".
  These rows are read-only (download the node's file to edit it).  After 500
  blocks the rest are not listed [CMT-AUD-W012].
  Files over 512 KB are compared in full; the side-by-side view shows only
  the first 512 KB [CMT-AUD-W006], so changes further down appear in the
  rows only (the view says so).
  SSTP routing-rule files are compared block by block; if a node's file has
  no recognisable blocks it is compared as text instead [CMT-AUD-W010].
  YAML files (.yaml / .yml, e.g. Helm values.yaml) are compared by structure,
  one row per parameter, so the order of keys and list entries never matters:
    - Maps are matched by key, at every depth:  appcfg.main_cfg
    - A list entry is matched by its first field, and its other fields sit
      below that name:  appcfg.props[opt=kpi.stats.rotate.interval].val
    - Plain value lists are compared as sets:  appcfg.gmscspclist[=100]
    - The same entry in two sections is two rows (each compared in its own
      section), so an entry that only one node has in a section is flagged
      even when every node has it somewhere else.
    - Instance blocks (first field inst / instance / instance_id ...) are
      paired by position, not by id:  instprop[#2].inst.  A differing id is
      shown as "~ instance-specific value", not as an error.
    - Comments that only some nodes have are listed in one "(comments)" row.
  Rows are grouped under their top-level key; the side-by-side view shows the
  file with each row's lines highlighted.  YAML rows are read-only.
  With "Show differences only" each node's column shows its own changed lines
  (3 lines of context, every line at most once, in that node's order) under a
  label naming the rows; a row a node lacks shows "<row> -- not on this node"
  after the nearest row that node has.  The table lines the rows up.
  A YAML file with template code ({{ }}, Helm templates) or that YAML cannot
  parse on any node is compared line by line as above [CMT-AUD-I002].
  KV files (.properties / .cfg / .ini / .conf) are compared section by
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
      line number, tagged "duplicate — L<n> value used".  The LAST (second)
      value is the effective value and is what gets compared; the duplicate
      itself is a warning [CMT-AUD-W007] naming the value used, not a mismatch.
    - Keys before the first header appear under "(no section)".
    - A key missing from its section on a node, but present in another
      section of that node's file, shows "-- missing (in [X])" (or "(in no
      section)"): keys are compared within their section only, the hint
      just says where the key sits on that node.
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
  Save the downloaded file (audit_patch_<date>T<hhmm>.json); below it is
  called audit_patch.json.  Its fields: CONFIGURATION FILES — REFERENCE, 7.

Step 2 — Apply the patch, from the folder the audit ran in:
  configmergetool \
    --apply-audit-patch audit_patch.json \
    --output-dir corrections/

  Without --output-dir the corrected files go to "output_dir" from the
  audit config (pass --audit-config-file audit.json) or from the patch,
  else to <run_dir>/corrections.

  The tool writes corrected config files to  corrections/<node>/<file>.
  A  corrections.log  lists every change applied.

Exit codes:
  0  -- every change in the patch was written
  1  -- some files were skipped or failed (review corrections.log)
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
  INVALID_JSON                   Input file contains invalid JSON; file skipped
  INVALID_XML                    Input file contains invalid XML; file skipped
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
  AMBIGUOUS_MATCH_SKIPPED        Filename matched several base files; file skipped
  GROUP_COUNT_MISMATCH           Base prefix.count kept but differs from merged group total
  REVIEW_COMMENTED_IN_BASE       KV param commented in base, active in release; confirm value
  REVIEW_COMMENTED_SECTION_IN_BASE KV section commented in base, active in release; confirm
  REVIEW_EMPTY_IN_BASE           JSON {} / [] in base, populated in release; base kept; confirm


================================================================================
 EXIT CODES
================================================================================

Merge mode:
  0  -- merge completed; no EMPTY_BASE_OVERRIDE or critical errors
  1  -- one or more critical issues found (EMPTY_BASE_OVERRIDE, INVALID_JSON,
         INVALID_XML, PROCESSOR_ERROR, AMBIGUOUS_MATCH_SKIPPED); review the
         Excel report.  Each critical entry is also logged with its [CMT-*] code.
  2  -- invalid arguments/config, or --output-dir overlaps an input directory

Audit mode:
  0  -- audit completed; all nodes match (or all differences are logical diffs)
  1  -- one or more mismatches found between nodes; review audit_report.html

Patch mode:
  0  -- every change in the patch was written
  1  -- some files were skipped or failed (CMT-PAT-E005..E009); see corrections.log
  2  -- patch unreadable, missing fields, malformed change, or no changes
         (CMT-PAT-E001..E004)


================================================================================
 ERROR IDENTIFIERS
================================================================================

Every error and warning line carries a stable identifier for traceability, e.g.
  [CMT-MRG-E002][FILE][AMBIGUOUS_MATCH][ERROR][new/dup.properties] ...
Search logs for the code; codes are never renumbered or reused.
  CLI = arguments/config files   MRG = merge   AUD = audit   PAT = apply patch
  E = error   W = warning   I = informational

  CMT-CLI-E001   Config file cannot be read or is not valid JSON
  CMT-CLI-E002   Config file is not a JSON array
  CMT-CLI-E003   Config entry is not a JSON object
  CMT-CLI-E004   Config entry is missing 'base_dir'
  CMT-CLI-E005   Config entry contains a literal 'password' (use 'password_env')
  CMT-CLI-E006   Duplicate node name in config file
  CMT-CLI-E007   'remote' is not an object with 'host'
  CMT-CLI-E008   'remote' contains a literal 'password' (use 'password_env')
  CMT-CLI-E009   'port' / 'timeout_secs' are not integers
  CMT-CLI-E010   Config entry failed validation (e.g. directory not found)
  CMT-CLI-E011   --release-dirs is required
  CMT-CLI-E012   --output-dir is required
  CMT-CLI-E013   --base-dir is required
  CMT-CLI-E014   --email-config is not yet implemented
  CMT-CLI-E015   --remote-audit requires --audit-config-file
  CMT-CLI-E016   --remote-audit SSH connectivity is not yet implemented
  CMT-CLI-E017   Merge arguments failed validation (e.g. directory not found)
  CMT-CLI-E018   Audit --mapping-file cannot be read or a line does not name a node
  CMT-MRG-E001   Processor failed for a file
  CMT-MRG-E002   Ambiguous filename match: several base candidates, file skipped
  CMT-MRG-E003   Invalid JSON input
  CMT-MRG-E004   Merged JSON output is invalid
  CMT-MRG-E005   Empty JSON file
  CMT-MRG-E006   JSON file cannot be read
  CMT-MRG-E007   Invalid XML input
  CMT-MRG-E008   XML file cannot be read
  CMT-MRG-E009   Logrotate base file is empty; output forced empty
  CMT-MRG-E010   --output-dir overlaps a base or release directory; run refused
  CMT-MRG-E011   SSTP release file missing
  CMT-MRG-E012   KV base value empty; release value forced empty (EMPTY_BASE_OVERRIDE)
  CMT-MRG-E013   XML base element empty; release element forced empty (EMPTY_BASE_OVERRIDE_XML)
  CMT-MRG-E014   JSON base value empty; release value forced empty (JSON_EMPTY_BASE_OVERRIDE)
  CMT-MRG-W001   Release file has no base counterpart; copied from release
  CMT-MRG-W002   Release file resolves outside its release directory; skipped
  CMT-MRG-W003   Copy-only base file not found; skipped
  CMT-MRG-W004   Copy-only entry escapes the base directory; skipped
  CMT-MRG-W005   Mapping entry escapes the base directory; skipped
  CMT-MRG-W006   (retired 2026-09-17 — one base → several release files is supported, see CMT-MRG-I002)
  CMT-MRG-W007   Mapping: mapped base file not found
  CMT-MRG-W008   XML duplicate key
  CMT-MRG-W009   File in several release dirs; dir matching the base name selected
  CMT-MRG-W010   File in several release dirs; first release dir used
  CMT-MRG-W011   (retired 2026-09-17 — XML many-to-one mapping merges all base files)
  CMT-MRG-W012   (retired 2026-09-17 — JSON many-to-one mapping merges all base files)
  CMT-MRG-W013   Indexed group count kept from base differs from the merged group total
  CMT-MRG-W014   KV parameter commented out in base but active in release; review annotation added
  CMT-MRG-W015   KV section commented out in base but active in release; review annotation added
  CMT-MRG-W016   JSON empty object/array in base but populated in release; review required ({} takes release keys, [] keeps base)
  CMT-MRG-W017   KV production Java class name replaced by release class; review annotation added
  CMT-MRG-W018   YAML base value or entry could not be applied to the release
                 layout; release kept, review required
  CMT-MRG-W019   YAML file has template code or is invalid and the site copy
                 differs; release copied as-is
  CMT-MRG-I001   Mapping: several base files mapped to one release file (first listed wins)
  CMT-MRG-I002   Mapping: one base file mapped to several release files
  CMT-MRG-I003   Base and release differ only in whitespace; release file copied as-is
  CMT-MRG-I004   Backup copy skipped (backup marker, or values* file next to
                 values.yaml); not merged or deployed
  CMT-AUD-E001   Node directory not found; audit aborted
  CMT-AUD-E002   File could not be compared (render error)
  CMT-AUD-W001   Invalid logical_diff_pattern regex ignored
  CMT-AUD-W002   Feedback history could not be written
  CMT-AUD-W003   SSTP parse error on a node
  CMT-AUD-W004   Invalid JSON on a node
  CMT-AUD-W005   File cannot be read on a node
  CMT-AUD-W006   Raw/display content truncated
  CMT-AUD-W007   Same key duplicated within one section on a node; last value is used
  CMT-AUD-W008   Duplicate log-name prefixes detected
  CMT-AUD-W009   Generated HTML report failed the sanity check
  CMT-AUD-W010   SSTP file has no recognisable blocks on a node; compared as text
  CMT-AUD-W011   Audit mapping pair skipped (file not found, filtered, or already present on that node)
  CMT-AUD-W012   Text diff stopped at the block limit; remaining differences not listed
  CMT-AUD-I001   Text/XML nodes differ only in whitespace; treated as a match
  CMT-AUD-I002   YAML file is not plain YAML (template code or parse error) on a
                 node; compared line by line
  CMT-PAT-E001   Patch file cannot be read or is not valid JSON
  CMT-PAT-E002   Patch JSON is missing a required field
  CMT-PAT-E003   Patch change entry is malformed
  CMT-PAT-E004   Patch contains no changes
  CMT-PAT-E005   Patch node not found in node_dirs; changes skipped
  CMT-PAT-E006   Patch file path is absolute; changes skipped
  CMT-PAT-E007   Patch file path escapes its directory; changes skipped
  CMT-PAT-E008   Patch node name is not a plain directory name; changes skipped
  CMT-PAT-E009   Applying changes to a file failed


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
      "no_skip_files": ["server.xml_20240705_active"]
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
    audit_diffs.xlsx
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

v3.0.2 (2026-09-28) — YAML by structure, values backups, YAML merge
  + Audit: YAML files (Helm values.yaml) compared by structure, one row per
    parameter; entries in a different order are no longer flagged; instance
    blocks paired by position; comment changes in one "(comments)" row
  + Audit: values.yaml is the final version -- other values* files next to
    it are skipped as backups (values.schema.json is audited)
  + Audit: YAML side-by-side view shows every line once, per node
  + Merge: YAML merged with site values winning (was: release copied and
    site values lost); layout and comments of the release file kept
  + Merge: backup copies are no longer merged or deployed
  + _bck / _bk recognised as backup markers
  + PyYAML is now a required dependency; offline bundle for RHEL 8/9
  + New codes: CMT-AUD-I002, CMT-MRG-W018, CMT-MRG-W019, CMT-MRG-I004

v3.0.1 (2026-09-25) — Audit display accuracy
  + Audit: "Show differences only" also trims the side-by-side file view to
    the changed lines (3 lines of context, "no line here" markers)
  + Audit: only lines that really differ are highlighted on each node
  + Audit SSTP: blocks compared on their original text across all nodes
    (whitespace ignored, comments count); moved statements and value changes
    on any node are mismatches, never "expected"; blocks missing on a node
    and text outside blocks are mismatches
  + Audit SSTP: cells show the original block lines (read-only) and the file
    gets the side-by-side view

v3.0.0 (2026-09-23) — Audit mapping and text differences
  + Audit: --mapping-file applies in audit mode — a file at a different path
    on another node (Staging dra-SA vs Prod/DR dra-SA-1, dra-SA-2) is compared
    in one row per instance instead of being reported absent
  + Audit: mapping files accept whole-directory lines (NODE/dir=NODE/dir)
  + Audit: yaml, tpl, txt, xml and other text files list each changed block
    of lines as a mismatch row, with highlighted side-by-side lines
  + Mismatch totals now count changed blocks in text files, not whole files
  + New codes: CMT-CLI-E018, CMT-AUD-W011, CMT-AUD-W012

v2.1.0 (2026-09-18) — Audit accuracy, merge fidelity and memory
  + Audit: KV files compared section by section against the base node
  + Audit: duplicate keys in a section use the last value (warning shown)
  + Audit: .sh scripts compared as text; SSTP blocks parsed correctly
  + Audit: backup detection covers _bkp200821 / name_240226.properties styles
  + Audit: a +path force-include no longer switches the filter to include-only
  + Audit: section names shown in their original case ([CouchBase])
  + Audit: tool version stamped in audit.log and in every report page header
  + Audit: much lower memory use — feedback history appended in place and
    report pages written in pieces (Site A (RSC1): ~750 MB -> ~300 MB)
  + Merge: release-only files copied; ambiguous filename matches skipped
  + Merge: KV comments, repeated sections and review annotations preserved
  + Stable error identifiers CMT-<AREA>-<E|W|I><nnn> on every message
  + To audit jar/class/other binaries, list their extensions in the filter
    file (include rules override the built-in binary exclusion list)

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
