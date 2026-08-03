#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.page_visual_object_quality import (  # noqa: E402
    DEFAULT_AUDIT_PATH,
    DEFAULT_QUALITY_PATH,
    build_page_visual_object_quality,
    write_page_visual_object_quality,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check page visual/object audit readiness for quality gates.")
    parser.add_argument("--audit-json", default=str(DEFAULT_AUDIT_PATH), help="Path to page visual/object audit JSON.")
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default=str(DEFAULT_QUALITY_PATH))
    parser.add_argument("--max-pages-without-ocr-text", type=int, default=20)
    args = parser.parse_args()

    report = build_page_visual_object_quality(Path(args.audit_json), max_pages_without_ocr_text=args.max_pages_without_ocr_text)
    summary = report.get("summary", {})
    checks = report.get("checks", [])

    print("Page visual/object quality gate")
    print(f"  Status: {str(report.get('status', 'fail')).upper()}")
    print("  Summary:")
    for key in sorted(summary):
        print(f"    {key}: {summary[key]}")
    print("  Checks:")
    for check in checks:
        status = "OK" if check.get("ok") else "FAIL"
        print(f"    {status} {check.get('name')}: {check.get('message')}")

    if args.write_json:
        out = write_page_visual_object_quality(report, Path(args.json_output))
        print(f"\nJSON: {out}")

    return 0 if str(report.get("status")).lower() == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
