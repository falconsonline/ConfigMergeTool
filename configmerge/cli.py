"""
configmerge.cli
~~~~~~~~~~~~~~~~
CLI entry point — the ``configmergetool`` console script calls ``main()`` here.

After ``pip install configmergetool``, run::

    configmergetool --help

For backward compatibility, ``python ConfigMergeTool.py`` still works
(that script is now a thin wrapper that calls this function).
"""

import argparse
import json
import sys

from configmerge import MergeEngine, MergeConfig
from configmerge.models import BaseDirConfig, EntryType, RemoteConfig
from configmerge.auditor import AuditEngine, AuditPatcher
from configmerge.auditor.feedback import print_summary as _print_feedback_summary


class ConfigMergeError(Exception):
    """Raised by helper functions to signal a fatal configuration error."""


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="configmergetool",
        description="Merge base (production) configs with release configs, "
                    "or audit config drift across multiple nodes.",
    )

    # ── Single-base options ─────────────────────────────────────────────
    p.add_argument("--base-dir",
                   help="Base (production/site) config directory [single-base mode]")
    p.add_argument("--mapping-file",
                   help="Optional base-to-release filename mapping file")
    p.add_argument("--copy-baseonlyconfigfile",
                   help="List of base files to copy as-is without processing")

    # ── Multi-base option ───────────────────────────────────────────────
    p.add_argument("--base-config-file",
                   help=(
                       "JSON file defining multiple base directories. "
                       "Each entry: {base_dir, name?, mapping_file?, copy_only_file?}. "
                       "When provided, --base-dir / --mapping-file / "
                       "--copy-baseonlyconfigfile are ignored."
                   ))

    # ── Apply-patch option ──────────────────────────────────────────────
    p.add_argument("--apply-audit-patch",
                   help=(
                       "Apply a patch JSON (exported from audit_report.html) to write "
                       "corrected config files into --output-dir. "
                       "Produces corrections.log alongside the corrected files."
                   ))

    # ── Audit-only option ───────────────────────────────────────────────
    p.add_argument("--audit-config-file",
                   help=(
                       "JSON file defining node directories to compare (audit mode). "
                       "Each entry: {base_dir, name?, remote?}. "
                       "When provided, --release-dirs and --output-dir are not required "
                       "and the tool generates an audit_report.html instead of merging."
                   ))

    # ── Audit filter file (Phase 3.3) ───────────────────────────────────
    p.add_argument("--filter-file",
                   help=(
                       "Path to a filter file controlling which file types/names are "
                       "audited. Each line is a suffix (e.g. 'cfg'), a named rule "
                       "(e.g. 'conf::sysctl.conf'), or an exclude (e.g. '!nohup.out'). "
                       "If not provided, all non-binary files are compared."
                   ))

    # ── Future remote-audit flag (reserved — Phase 11) ──────────────────
    p.add_argument("--remote-audit", action="store_true",
                   help=(
                       "[Coming in Phase 11] Use SSH/SFTP to fetch config files from "
                       "remote nodes defined in --audit-config-file. "
                       "Requires: pip install \"configmergetool[ssh]\""
                   ))

    # ── Future email-monitor flag (reserved — Phase 12) ─────────────────
    p.add_argument("--email-config",
                   help=(
                       "[Coming in Phase 12] Run in email-monitor mode using the "
                       "specified email config JSON. "
                       "Requires: pip install \"configmergetool[email]\""
                   ))

    # ── Common options ──────────────────────────────────────────────────
    p.add_argument("--release-dirs",  nargs="+", required=False, default=None,
                   help="One or more release config directories (not required in audit mode)")
    p.add_argument("--output-dir",    required=False, default=None,
                   help="Destination directory for merged output (not required in audit mode)")
    p.add_argument("--exclude-params-in-baseonlyconfig", action="store_true",
                   help="Skip parameters present only in base config")
    p.add_argument("--dry-run",   action="store_true",
                   help="Analyse without writing any output files")
    p.add_argument("--verbose",   action="store_true",
                   help="Show INFO-level messages on the console")
    p.add_argument("--quiet", action="store_true",
                   help="Audit mode: suppress MATCH lines; print only DIFF/WARN/ERROR/SUMMARY")
    p.add_argument("--log-dir",   default="logs",
                   help="Directory for log files (default: logs/)")
    p.add_argument("--report-dir", default="reports",
                   help="Directory for Excel/HTML reports (default: reports/)")
    p.add_argument("--feedback-summary", action="store_true",
                   help="Print a summary of cross-run feedback history "
                        "(~/.configmergetool/feedback_history.json) and exit.")
    p.add_argument("--version", action="version",
                   version=f"%(prog)s {_get_version()}")
    return p.parse_args(argv)


def _get_version() -> str:
    try:
        from configmerge import __version__
        return __version__
    except Exception:
        return "unknown"


def _load_base_configs(path: str):
    """Load a JSON file describing multiple base-directory configurations.

    Returns ``(configs, no_skip_files, output_dir)`` where *no_skip_files* is a
    flat list of filenames that should never be classified as backups, collected
    from all ``"no_skip_files"`` arrays in the entries, and *output_dir* is the
    optional patch output directory (from an ``{"output_dir": "..."}`` entry).

    Raises ConfigMergeError on any validation failure.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigMergeError(f"Cannot read config file {path!r}: {e}")
    if not isinstance(data, list):
        raise ConfigMergeError(f"Config file {path!r} must be a JSON array.")

    # Validate unique node names (Phase 7.5)
    names_seen: set = set()
    configs = []
    no_skip_files: list = []
    output_dir: str = ""

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ConfigMergeError(f"Entry {i} in {path!r} is not a JSON object.")

        # Special entry: {"output_dir": "..."} — no base_dir
        if "output_dir" in item and "base_dir" not in item:
            output_dir = item["output_dir"].strip()
            continue

        if "base_dir" not in item:
            raise ConfigMergeError(f"Entry {i} in {path!r} missing 'base_dir'.")

        # Security: reject literal "password" key (must use "password_env")
        if "password" in item:
            raise ConfigMergeError(
                f"Entry {i} in {path!r}: use 'password_env' (name of an environment "
                "variable) instead of storing a literal 'password' in the config file."
            )

        name = item.get("name", "")
        if name and name in names_seen:
            raise ConfigMergeError(
                f"Entry {i} in {path!r}: duplicate node name {name!r}. "
                "Node names must be unique."
            )
        if name:
            names_seen.add(name)

        # Aggregate no_skip_files from each entry (Phase 3.2)
        entry_no_skip = item.get("no_skip_files", [])
        if isinstance(entry_no_skip, list):
            no_skip_files.extend(entry_no_skip)

        # Parse optional remote config (Phase 9)
        remote = None
        if "remote" in item:
            r = item["remote"]
            if not isinstance(r, dict) or "host" not in r:
                raise ConfigMergeError(
                    f"Entry {i} in {path!r}: 'remote' must be an object with at least 'host'."
                )
            if "password" in r:
                raise ConfigMergeError(
                    f"Entry {i} in {path!r}: use 'password_env' in remote config "
                    "instead of a literal 'password'."
                )
            try:
                port         = int(r.get("port", 22))
                timeout_secs = int(r.get("timeout_secs", 30))
            except (ValueError, TypeError) as e:
                raise ConfigMergeError(
                    f"Entry {i} in {path!r}: 'port' and 'timeout_secs' must be "
                    f"integers: {e}"
                )
            remote = RemoteConfig(
                host         = r["host"],
                port         = port,
                username     = r.get("username", ""),
                key_file     = r.get("key_file", ""),
                password_env = r.get("password_env", ""),
                remote_path  = r.get("remote_path", ""),
                timeout_secs = timeout_secs,
            )

        try:
            configs.append(BaseDirConfig(
                base_dir       = item["base_dir"],
                mapping_file   = item.get("mapping_file"),
                copy_only_file = item.get("copy_only_file"),
                name           = name,
                remote         = remote,
            ))
        except ValueError as e:
            raise ConfigMergeError(f"Entry {i} in {path!r}: {e}")
    return configs, no_skip_files, output_dir


def main(argv=None) -> int:
    try:
        return _main(argv)
    except ConfigMergeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


def _main(argv=None) -> int:
    args = parse_args(argv)

    # ── Feedback summary subcommand (Phase 5.3) ─────────────────────────
    if hasattr(args, 'feedback_summary') and args.feedback_summary:
        _print_feedback_summary()
        return 0

    # ── Future email-monitor mode (Phase 12) ────────────────────────────
    if args.email_config:
        print(
            "[ERROR] --email-config (email-triggered audit) is not yet implemented. "
            "It will be available in Phase 12.",
            file=sys.stderr,
        )
        return 2

    # ── Future remote-audit mode (Phase 11) ─────────────────────────────
    if args.remote_audit and not args.audit_config_file:
        print(
            "[ERROR] --remote-audit requires --audit-config-file with 'remote' entries.",
            file=sys.stderr,
        )
        return 2

    # ── Apply-patch mode ────────────────────────────────────────────────
    if args.apply_audit_patch:
        # output_dir: CLI flag wins; fallback to audit config; fallback to patch JSON
        patch_output_dir = args.output_dir or ""
        if not patch_output_dir and args.audit_config_file:
            _, _, patch_output_dir = _load_base_configs(args.audit_config_file)
        # If still empty, AuditPatcher will read output_dir from the patch JSON itself
        patcher = AuditPatcher(args.apply_audit_patch, patch_output_dir)
        written = patcher.apply()
        return 0 if written >= 0 else 1

    # ── Audit mode ──────────────────────────────────────────────────────
    if args.audit_config_file:
        nodes, no_skip_files, cfg_output_dir = _load_base_configs(args.audit_config_file)

        if args.remote_audit:
            # Phase 11: SSHNodeFetcher — not yet implemented
            print(
                "[ERROR] --remote-audit SSH connectivity is not yet implemented. "
                "It will be available in Phase 11 (pip install \"configmergetool[ssh]\").",
                file=sys.stderr,
            )
            return 2

        engine = AuditEngine(
            nodes,
            report_dir=args.report_dir,
            quiet=args.quiet,
            no_skip_files=no_skip_files,
            filter_file=getattr(args, 'filter_file', None),
            output_dir=cfg_output_dir,
        )
        result = engine.run()
        # Exit 1 when mismatches found OR when any file failed to process
        if result.total_mismatches > 0 or result.render_errors:
            return 1
        return 0

    # ── Merge mode: validate required args ─────────────────────────────
    if not args.release_dirs:
        print("[ERROR] --release-dirs is required unless --audit-config-file is provided.",
              file=sys.stderr)
        return 2
    if not args.output_dir:
        print("[ERROR] --output-dir is required unless --audit-config-file is provided.",
              file=sys.stderr)
        return 2

    # Build base_configs
    if args.base_config_file:
        base_configs, _, _ = _load_base_configs(args.base_config_file)
        config = MergeConfig(
            release_dirs      = args.release_dirs,
            output_dir        = args.output_dir,
            base_configs      = base_configs,
            exclude_base_only = args.exclude_params_in_baseonlyconfig,
            dry_run           = args.dry_run,
            verbose           = args.verbose,
        )
    else:
        if not args.base_dir:
            print("[ERROR] --base-dir is required unless --base-config-file is provided.",
                  file=sys.stderr)
            return 2
        config = MergeConfig(
            release_dirs      = args.release_dirs,
            output_dir        = args.output_dir,
            base_dir          = args.base_dir,
            mapping_file      = args.mapping_file,
            copy_only_file    = args.copy_baseonlyconfigfile,
            exclude_base_only = args.exclude_params_in_baseonlyconfig,
            dry_run           = args.dry_run,
            verbose           = args.verbose,
        )

    engine  = MergeEngine(config, log_dir=args.log_dir, report_dir=args.report_dir)
    results = engine.run()   # List[MergeResult]

    # Exit non-zero if any critical events occurred across all bases
    has_critical = any(
        e.type in EntryType.CRITICAL_TYPES
        for r in results
        for e in r.report
    )
    return 1 if has_critical else 0


if __name__ == "__main__":
    sys.exit(main())
