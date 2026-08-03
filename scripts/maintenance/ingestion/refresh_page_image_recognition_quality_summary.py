#!/usr/bin/env python3
"""Refresh page image-recognition quality summary into pipeline manifests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_QUALITY = Path("local_data/organization/image_recognition/page_image_recognition_quality.json")
LATEST_MANIFEST = Path("local_data/pipeline_runs/latest_backend_pipeline.json")


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _candidate_run_manifest(latest: dict[str, Any]) -> Path | None:
    run_id = latest.get("run_id") or latest.get("id")
    if not run_id:
        return None
    candidate = Path("local_data/pipeline_runs") / f"tiff_backend_pipeline_{run_id}.json"
    return candidate if candidate.exists() else None


def _merge_manifest(path: Path, quality: dict[str, Any]) -> bool:
    manifest = _load(path)
    if not manifest:
        return False
    summary = quality.get("summary", {}) if isinstance(quality.get("summary"), dict) else {}
    manifest["page_image_recognition_quality"] = quality
    manifest["page_image_recognition_summary"] = summary
    manifest.setdefault("quality_summaries", {})["page_image_recognition"] = quality
    _write(path, manifest)
    return True


def main() -> int:
    quality = _load(DEFAULT_QUALITY)
    if not quality:
        print(f"Page image-recognition quality JSON not found: {DEFAULT_QUALITY}")
        return 1
    latest = _load(LATEST_MANIFEST)
    updated = []
    if latest and _merge_manifest(LATEST_MANIFEST, quality):
        updated.append(str(LATEST_MANIFEST))
    run_manifest = _candidate_run_manifest(latest)
    if run_manifest and _merge_manifest(run_manifest, quality):
        updated.append(str(run_manifest))

    summary = quality.get("summary", {}) if isinstance(quality.get("summary"), dict) else {}
    print("Refreshed page image-recognition quality summary:")
    if updated:
        for item in updated:
            print(f"  Manifest: {item}")
    else:
        print("  Manifest: not updated")
    print(f"  Page image-recognition quality JSON: {DEFAULT_QUALITY}")
    print(f"  Status: {quality.get('status')}")
    print(f"  Pages checked: {summary.get('page_image_pages_checked')}")
    print(f"  Readable images: {summary.get('page_image_readable_images')}")
    print(f"  Likely visual pages: {summary.get('page_image_likely_visual_pages')}")
    return 0 if str(quality.get("status", "")).lower() == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
