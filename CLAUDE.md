# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements-dev.txt          # runtime needs only openpyxl; chardet is optional (encoding falls back to latin-1)
python3 -m pytest tests/                      # all tests
python3 -m pytest tests/test_audit_kv_sections.py::test_duplicate_key_in_section_shows_both_values_and_is_mismatch
python -m build                               # sdist/wheel via pyproject.toml (entry point: configmergetool)
```

Run modes (`ConfigMergeTool.py`, `python -m configmerge` and `configmergetool` are equivalent):

```bash
python3 ConfigMergeTool.py --base-dir base --release-dirs release --output-dir output [--dry-run] [--verbose]
python3 ConfigMergeTool.py --base-config-file bases.json --release-dirs release --output-dir output
python3 ConfigMergeTool.py --audit-config-file audit.json --filter-file filter.txt [--quiet]
python3 ConfigMergeTool.py --apply-audit-patch audit_patch.json --output-dir corrections/
```

No linter/formatter is configured. Version lives in both `configmerge/__init__.py` and `pyproject.toml`.

## Architecture

`ConfigMergeTool.py` is a shim; `configmerge/cli.py::_main` routes purely by flags, in this order:
`--feedback-summary` → `--apply-audit-patch` (`AuditPatcher`) → `--audit-config-file` (`AuditEngine`) → merge
(`MergeEngine`). `--remote-audit` / `--email-config` and `configmerge/workflows/` are Phase 11/12 stubs.
Exit codes: merge returns 1 on `EntryType.CRITICAL_TYPES`; audit returns 1 on any mismatch or render error;
config errors raise `ConfigMergeError` → 2. Node/base JSON configs are arrays; an entry `{"output_dir": ...}`
without `base_dir` sets the patch output dir; a literal `"password"` key is rejected (use `password_env`).

**Merge** (base values win): `MergeConfig` is normalised to a list of `BaseDirConfig`; each base gets an
independent pass. `matcher.FileMatcher` resolves release→base files (mapping file → same relative path →
unique filename; ambiguous names are skipped). `processors/` register per extension via `@register` into
`PROCESSOR_REGISTRY`; unregistered extensions go to `GenericProcessor` (copy release file). Processors return
`ReportEntry` lists consumed by `reporter/excel.py` (one workbook per base) and `reporter/html_reporter.py`
(one combined HTML).

**Audit** (drift across nodes, no release dir): `auditor/engine.py::AuditEngine.run` scans each node
(backup-file detection, `FileFilter` rules), takes the union of relative paths and routes each file in
`_compare_file`: binary (extension or null byte on any node) → `.sstp` → KV → JSON → text/xml checksum. Output is
`AuditFile` with `AuditParam` rows. `auditor/html_report.py` serialises the result into an embedded
`AUDIT_DATA` JSON and renders a self-contained page with vanilla JS; large runs are split into report parts
behind an index page. In the page, edits are held as pending changes keyed by row `compound`; the user either
downloads a reconstructed file (JS `reconstructKV`) or exports a patch JSON applied by `auditor/patch.py`.

Cross-file invariants that are easy to break:
- KV row identity `compound = "[Section]|key"` must be derived the same way in `auditor/engine.py::_compare_kv`,
  JS `reconstructKV` (in `auditor/html_report.py`) and `auditor/patch.py::_apply_kv`. `#[X]` is a comment in all three.
- There are two KV readers: `processors/kv.py::parse_kv_doc` (merge; keeps `#[X]` as shadow sections so output
  can be emitted verbatim) and the audit section walker `_walk_kv_sections` in `auditor/engine.py`. Change audit
  semantics in the walker, not in `parse_kv_doc`.
- There are two HTML reporters: `reporter/html_reporter.py` (merge) and `auditor/html_report.py` (audit). In the
  latter the CSS/JS blocks are plain Python strings (single braces) while `_build_html` / `_build_index_html` are
  f-string templates (doubled braces).

## Domain, decisions and docs

- `CONTEXT.md` is the glossary (Base vs Base node, Section check, Commented section header, …). Use its terms.
- `MEMORY.md` records confirmed decisions (e.g. audit section-by-section comparison rules). Read it before
  changing comparison semantics; append new confirmed decisions there.
- Feature changes must also update `ConfigMergeTool-features.md` (developer reference + changelog) and
  `ConfigMergeTool-readme.txt` (user guide).
- Real site data (e.g. `Telstra-RSC*`, `singtel*`) sits untracked in the main checkout; never commit it or copy
  it into tests — tests use synthetic fixtures under `tmp_path`.

## Working rules (from the user)

- Before proposing a plan, show a snapshot with actual data, the issue details, how the fix is planned and the
  predicted end result computed on real data.
- On any doubt, stop and consult the user instead of assuming.
