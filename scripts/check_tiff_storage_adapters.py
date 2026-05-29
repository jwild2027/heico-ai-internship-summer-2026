#!/usr/bin/env python3
"""Check the local storage-adapter boundary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.storage_adapters import adapter_readiness, build_local_store_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TIFF storage adapter readiness.")
    parser.add_argument("--config", default="local_config.yaml")
    parser.add_argument("--part", default="120-37313-001")
    parser.add_argument("--page", default="t_p_120_1176_p000083")
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/api/storage_adapter_ready.json")
    args = parser.parse_args()

    bundle = build_local_store_bundle(repo_root=REPO_ROOT, config_path=args.config)
    report = adapter_readiness(bundle, part_probe=args.part, page_probe=args.page)

    print("TIFF storage adapter readiness")
    print(f"  Status: {report['status'].upper()}")
    print(f"  Mode: {report['mode']}")
    print(f"  Organization summary present: {report['organization_summary_present']}")
    part = report["part_probe"]
    print(f"  Part probe: {part['part_number']} | found={part['found']} | name={part.get('nomenclature')} | pages={part.get('pages')}")
    page = report["page_probe"]
    print(f"  Page probe: {page['page_id']} | found={page['found']} | source={page['has_source']}")
    print(f"  Quality status: {report.get('quality_status')}")

    if args.write_json:
        out = REPO_ROOT / args.json_output
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"  JSON: {out.relative_to(REPO_ROOT)}")

    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
