#!/usr/bin/env python
"""Check whether the local TIFF/RAG API has the artifacts it needs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.api_backend import check_api_ready, make_paths  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--export-dir", default="local_data/organization/export")
    parser.add_argument("--manifest", default="local_data/pipeline_runs/latest_backend_pipeline.json")
    parser.add_argument("--quality", default="local_data/pipeline_runs/latest_quality_gate.json")
    parser.add_argument("--config", default="local_config.yaml")
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = make_paths(
        repo_root=args.repo_root,
        export_dir=args.export_dir,
        manifest_path=args.manifest,
        quality_path=args.quality,
        config_path=args.config,
    )
    result = check_api_ready(paths)
    summary = result.get("organization_summary") or {}

    print("TIFF API readiness")
    print(f"  Status: {result['status']}")
    print(f"  Export dir: {result['paths']['export_dir']}")
    print(f"  Quality gate status: {result.get('quality_status')}")
    print(f"  Pipeline manifest status: {result.get('manifest_status')}")
    print("  Files present:")
    for name, present in result.get("files_present", {}).items():
        print(f"    {name}: {present}")
    if summary:
        print("  Organization counts:")
        for key in ("manuals", "pages", "ata_groups", "parts", "part_mentions"):
            print(f"    {key}: {summary.get(key)}")
    if result.get("errors"):
        print("  Errors:")
        for error in result["errors"]:
            print(f"    - {error}")
    if args.strict and result["status"] != "OK":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
