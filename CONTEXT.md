# ConfigMergeTool

Carries site-specific configuration forward onto new software releases (merge), and detects configuration
drift across production nodes (audit), with corrections written back via a patch.

## Language

### Operations

**Merge**:
Producing an output configuration from a base directory and one or more release directories, where base values win.
_Avoid_: Sync, upgrade

**Audit**:
Comparing the same configuration files across several nodes to find drift.
_Avoid_: Diff run, comparison job

**Patch**:
A set of per-node corrections exported from the audit report and applied to produce corrected files.
_Avoid_: Fix file, corrections JSON

### Merge terms

**Base**:
In a merge, the production/site configuration directory whose values are carried forward.
_Avoid_: Production dir, old config

**Release**:
In a merge, the new software release's default configuration directory.
_Avoid_: New config, target

**Base-only parameter**:
A parameter present in the base file but not in the release file.

**Release-only parameter**:
A parameter present in the release file but not in the base file.

**Copy-only file**:
A base file copied to output verbatim without merge processing.
_Avoid_: As-is file, binary copy

**Many-to-one mapping**:
Several differently-named base files merged into one release file.

### Audit terms

**Node**:
One site/server configuration directory taking part in an audit, named in the audit config.
_Avoid_: Host, server, base dir (in audit context)

**Base node**:
The node every other node is checked against for a file: the first node in the audit config that has the file.
_Avoid_: Master, reference node, Base (that is a merge term)

**Section**:
A named block of parameters in a key-value file, opened by a `[Name]` header; keys before any header form the "(no section)" section.
_Avoid_: Block, group

**Commented section header**:
A `#[Name]` line; it is a comment and does not open a section.

**Parameter row**:
One section-and-key pair shown across all nodes in the audit report.
_Avoid_: Line, entry

**Section check**:
The per-section summary comparing the base node's parameters with the same section on each other node: match, differ, missing, extra, or section absent.

**Section absent**:
A node has the file but not the section header.

**File absent**:
A node does not have the file at all.

**Commented-out key**:
A `#key=value` line; counts as present on that node, not missing.

**Duplicate in section**:
The same key appearing more than once as active in one section of one node's file.

**Mismatch**:
A parameter row whose active values differ across nodes, or that is missing or duplicated on a node, and is not a logical diff.
_Avoid_: Diff, error

**Logical diff**:
A parameter expected to differ between nodes because it matches a configured logical-diff pattern.
_Avoid_: Expected diff (ambiguous with instance-specific value)

**Instance-specific value**:
A value auto-detected as naturally node-specific (log file name, instance number), shown separately and not counted as an error.

**Report part**:
One HTML file of a large audit report split across several files behind an index page.
