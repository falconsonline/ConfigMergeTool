#!/usr/bin/env python3
"""
ConfigMergeTool — CLI entry point.

Single-base mode (existing):
    python ConfigMergeTool.py \\
        --base-dir base --release-dirs release --output-dir output \\
        --mapping-file mapping.txt --copy-baseonlyconfigfile copy.txt

Multi-base mode (one pass per production node):
    python ConfigMergeTool.py \\
        --base-config-file bases.json \\
        --release-dirs release --output-dir output

bases.json format:
    [
      {"base_dir": "node1", "name": "prod-eu", "mapping_file": "map1.txt",
       "copy_only_file": "copy1.txt"},
      {"base_dir": "node2", "name": "prod-us"}
    ]

All logic lives in the `configmerge` package:
    from configmerge import MergeEngine, MergeConfig, BaseDirConfig
    results = MergeEngine(MergeConfig(...)).run()
"""

import argparse
import json
import sys
from configmerge import MergeEngine, MergeConfig
from configmerge.models import BaseDirConfig, EntryType


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Merge base (production) configs with release configs."
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

    # ── Common options ──────────────────────────────────────────────────
    p.add_argument("--release-dirs",  nargs="+", required=True,
                   help="One or more release config directories")
    p.add_argument("--output-dir",    required=True,
                   help="Destination directory for merged output")
    p.add_argument("--exclude-params-in-baseonlyconfig", action="store_true",
                   help="Skip parameters present only in base config")
    p.add_argument("--dry-run",   action="store_true",
                   help="Analyse without writing any output files")
    p.add_argument("--verbose",   action="store_true",
                   help="Show INFO-level messages on the console")
    p.add_argument("--log-dir",   default="logs",
                   help="Directory for log files (default: logs/)")
    p.add_argument("--report-dir", default="reports",
                   help="Directory for Excel/HTML reports (default: reports/)")
    return p.parse_args()


def _load_base_configs(path: str) -> list:
    """Load a JSON file describing multiple base-directory configurations."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ERROR] Cannot read --base-config-file {path!r}: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, list):
        print("[ERROR] --base-config-file must be a JSON array.", file=sys.stderr)
        sys.exit(2)
    configs = []
    for i, item in enumerate(data):
        if not isinstance(item, dict) or "base_dir" not in item:
            print(f"[ERROR] Entry {i} in base-config-file missing 'base_dir'.",
                  file=sys.stderr)
            sys.exit(2)
        configs.append(BaseDirConfig(
            base_dir       = item["base_dir"],
            mapping_file   = item.get("mapping_file"),
            copy_only_file = item.get("copy_only_file"),
            name           = item.get("name", ""),
        ))
    return configs


def main() -> int:
    args = parse_args()

    # Build base_configs
    if args.base_config_file:
        base_configs = _load_base_configs(args.base_config_file)
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
            sys.exit(2)
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
