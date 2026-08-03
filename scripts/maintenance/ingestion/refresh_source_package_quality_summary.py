#!/usr/bin/env python
"""Refresh source-package quality summary into the latest pipeline manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.source_package_quality import (  # noqa: E402
    DEFAULT_SOURCE_PACKAGE_QUALITY_JSON,
    DEFAULT_SOURCE_TRACEABILITY_JSON,
    build_source_package_quality_result,
    write_source_package_quality_json,
)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="local_data/pipeline_runs/latest_backend_pipeline.json")
    parser.add_argument("--traceability-json", default=DEFAULT_SOURCE_TRACEABILITY_JSON)
    parser.add_argument("--source-package-quality-json", default=DEFAULT_SOURCE_PACKAGE_QUALITY_JSON)
    args = parser.parse_args()

    result = build_source_package_quality_result(args.traceability_json)
    write_source_package_quality_json(result, args.source_package_quality_json)

    manifest_path = Path(args.manifest)
    manifest = _load_json(manifest_path)
    if not manifest:
        print(f"No manifest updated: {manifest_path}")
        return 1
    manifest["source_package_quality_summary"] = result.summary
    _write_json(manifest_path, manifest)

    run_id = str(manifest.get("run_id") or "")
    pipeline_name = str(manifest.get("pipeline") or "tiff_backend_pipeline")
    run_manifest = manifest_path.parent / f"{pipeline_name}_{run_id}.json" if run_id else None
    if run_manifest and run_manifest.exists():
        run_payload = _load_json(run_manifest)
        if run_payload:
            run_payload["source_package_quality_summary"] = result.summary
            _write_json(run_manifest, run_payload)

    print("Refreshed source-package quality summary:")
    print(f"  Manifest: {manifest_path}")
    if run_manifest and run_manifest.exists():
        print(f"  Run manifest: {run_manifest}")
    print(f"  Source-package quality JSON: {args.source_package_quality_json}")
    print(f"  Status: {result.status}")
    print(f"  ZIP TIFF files: {result.summary.get('source_package_zip_tiff_files')}")
    print(f"  Organization pages: {result.summary.get('source_package_organization_pages')}")
    print(f"  Matched pages: {result.summary.get('source_package_matched_pages')}")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
