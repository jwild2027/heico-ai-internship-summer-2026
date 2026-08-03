from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.api_contract_quality import DEFAULT_QUALITY_PATH


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _run_manifest_path(manifest: Dict[str, Any], latest_path: Path) -> Path | None:
    run_id = manifest.get("run_id")
    if not run_id:
        return None
    candidate = latest_path.parent / f"tiff_backend_pipeline_{run_id}.json"
    return candidate if candidate.exists() else None


def _update_manifest(path: Path, quality: Dict[str, Any]) -> None:
    manifest = _load(path)
    summary = dict(quality.get("summary") or {})
    summary["status"] = quality.get("status")
    manifest["api_contract_quality_summary"] = summary
    quality_summaries = manifest.setdefault("quality_summaries", {})
    if isinstance(quality_summaries, dict):
        quality_summaries["api_contract_quality"] = summary
    _write(path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh API contract quality summary into pipeline manifest files.")
    parser.add_argument("--quality-json", default=str(DEFAULT_QUALITY_PATH))
    parser.add_argument("--manifest", default="local_data/pipeline_runs/latest_backend_pipeline.json")
    args = parser.parse_args()

    quality_path = Path(args.quality_json)
    manifest_path = Path(args.manifest)
    if not quality_path.exists():
        print(f"API contract quality JSON not found: {quality_path}")
        return 1
    if not manifest_path.exists():
        print(f"Pipeline manifest not found: {manifest_path}")
        return 1

    quality = _load(quality_path)
    manifest = _load(manifest_path)
    run_path = _run_manifest_path(manifest, manifest_path)

    _update_manifest(manifest_path, quality)
    if run_path:
        _update_manifest(run_path, quality)

    summary = quality.get("summary", {})
    print("Refreshed API contract quality summary:")
    print(f"  Manifest: {manifest_path}")
    if run_path:
        print(f"  Run manifest: {run_path}")
    print(f"  API contract quality JSON: {quality_path}")
    print(f"  Status: {quality.get('status')}")
    print(f"  API contract: {summary.get('api_contract_pass')}/{summary.get('api_contract_total')} cases; failures={summary.get('api_contract_fail')}")
    print(f"  Mode: {summary.get('api_contract_mode')}")
    return 0 if str(quality.get("status")).lower() == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
