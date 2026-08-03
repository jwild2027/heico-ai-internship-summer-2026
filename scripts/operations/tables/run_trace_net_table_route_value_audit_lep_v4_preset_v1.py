#!/usr/bin/env python
"""Run the TRACE-Net table-route value audit with post-LEP-v4 thresholds."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_table_route_value_audit_lep_v4_preset_v1 import (
    DEFAULT_AUDIT_OUTPUT_DIR,
    DEFAULT_AUDIT_REPORT_PATH,
    DEFAULT_NORMALIZER_PATH,
    DEFAULT_PRESET_MANIFEST_PATH,
    LepV4AuditPreset,
    write_inspection_outputs,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table-route-value-normalizer",
        type=Path,
        default=DEFAULT_NORMALIZER_PATH,
        help="Path to trace_net_table_route_value_normalizer_v1.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_AUDIT_OUTPUT_DIR,
        help="Output directory for the upstream audit and LEP-v4 preset inspect files.",
    )
    parser.add_argument(
        "--skip-upstream-build",
        action="store_true",
        help="Only inspect/check the existing audit JSON in --output-dir.",
    )
    parser.add_argument(
        "--inspect-limit",
        type=int,
        default=50,
        help="Maximum compact search-ready values to copy into the inspect file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    preset = LepV4AuditPreset(inspect_limit=args.inspect_limit)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_report_path = output_dir / DEFAULT_AUDIT_REPORT_PATH.name
    build_args = preset.build_args(args.table_route_value_normalizer, output_dir)

    manifest = {
        "schema_version": "trace_net_table_route_value_audit_lep_v4_preset_manifest_v1",
        "preset": preset.as_dict(),
        "table_route_value_normalizer": str(args.table_route_value_normalizer),
        "output_dir": str(output_dir),
        "audit_report_path": str(audit_report_path),
        "upstream_build_command": build_args,
        "skip_upstream_build": args.skip_upstream_build,
        "safety_contract": {
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    }

    if not args.skip_upstream_build:
        completed = subprocess.run(build_args, check=False)
        manifest["upstream_build_returncode"] = completed.returncode
        write_json(output_dir / DEFAULT_PRESET_MANIFEST_PATH.name, manifest)
        if completed.returncode != 0:
            return completed.returncode

    if not audit_report_path.exists():
        manifest["quality_status"] = "FAIL"
        manifest["error"] = f"Audit report not found: {audit_report_path}"
        write_json(output_dir / DEFAULT_PRESET_MANIFEST_PATH.name, manifest)
        print(manifest["error"], file=sys.stderr)
        return 2

    inspection = write_inspection_outputs(
        audit_report_path=audit_report_path,
        output_dir=output_dir,
        preset=preset,
        normalizer_path=args.table_route_value_normalizer,
    )
    manifest["quality_status"] = inspection["quality_status"]
    manifest["watch_counters"] = inspection["watch_counters"]
    manifest["promoted_fields"] = inspection["promoted_fields"]
    write_json(output_dir / DEFAULT_PRESET_MANIFEST_PATH.name, manifest)
    print(f"quality_status: {inspection['quality_status']}")
    print(f"inspect_json: {output_dir / 'trace_net_table_route_value_audit_lep_v4_preset_v1_inspect.json'}")
    print(f"inspect_md: {output_dir / 'trace_net_table_route_value_audit_lep_v4_preset_v1_inspect.md'}")
    return 0 if inspection["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
