from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.api_adapter_quality import DEFAULT_API_ADAPTER_QUALITY_JSON  # noqa: E402

DEFAULT_MANIFEST = Path("local_data/pipeline_runs/latest_backend_pipeline.json")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _run_manifest_path(latest_manifest: Path, manifest: dict) -> Path | None:
    run_id = manifest.get("run_id")
    if not run_id:
        return None
    return latest_manifest.parent / f"tiff_backend_pipeline_{run_id}.json"


def _refresh_one(manifest_path: Path, quality_path: Path, quality: dict) -> None:
    if not manifest_path.exists():
        return
    manifest = _read_json(manifest_path)
    manifest["api_adapter_quality_summary"] = quality.get("summary", {})
    manifest["api_adapter_quality_status"] = quality.get("status", "unknown").lower()
    _write_json(manifest_path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh API/adapter quality summary into pipeline manifest.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--api-adapter-quality-json", type=Path, default=DEFAULT_API_ADAPTER_QUALITY_JSON)
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Pipeline manifest not found: {args.manifest}")
        return 1
    if not args.api_adapter_quality_json.exists():
        print(f"API/adapter quality JSON not found: {args.api_adapter_quality_json}")
        return 1

    latest = _read_json(args.manifest)
    quality = _read_json(args.api_adapter_quality_json)
    _refresh_one(args.manifest, args.api_adapter_quality_json, quality)
    run_manifest = _run_manifest_path(args.manifest, latest)
    if run_manifest is not None and run_manifest.exists():
        _refresh_one(run_manifest, args.api_adapter_quality_json, quality)

    summary = quality.get("summary", {})
    print("Refreshed API/adapter quality summary:")
    print(f"  Manifest: {args.manifest}")
    if run_manifest is not None:
        print(f"  Run manifest: {run_manifest}")
    print(f"  API/adapter quality JSON: {args.api_adapter_quality_json}")
    print(f"  Status: {quality.get('status', 'unknown').lower()}")
    print(f"  API ready: {summary.get('api_ready_status')}")
    print(f"  Storage adapter ready: {summary.get('storage_adapter_status')}")
    print(f"  Adapter mode: {summary.get('storage_adapter_mode')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
