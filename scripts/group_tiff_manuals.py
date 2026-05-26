#!/usr/bin/env python3
"""Group scanned TIFF pages into logical manual objects and write JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.manual_grouping import build_manifest, write_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Group TIFF scan DB rows into manual objects")
    parser.add_argument("--db-path", required=True, help="Path to local TIFF scan SQLite DB")
    parser.add_argument("--output", required=True, help="Output manifest JSON path")
    parser.add_argument("--print-summary", action="store_true", help="Print a short summary after writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_manifest(args.db_path)
    output_path = write_manifest(manifest, args.output)
    print(f"Wrote manual group manifest: {output_path}")

    if args.print_summary:
        manuals = manifest.get("manuals") or []
        print(f"Manuals: {len(manuals)}")
        for manual in manuals:
            print(
                "  "
                f"manual_id={manual.get('manual_id')} | "
                f"publication={manual.get('publication_number')} | "
                f"pages={manual.get('page_count')} | "
                f"ata={manual.get('ata_code')}"
            )
            type_counts: dict[str, int] = {}
            for page in manual.get("pages") or []:
                page_type = page.get("detected_type") or "unknown"
                type_counts[page_type] = type_counts.get(page_type, 0) + 1
            for page_type, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))[:12]:
                print(f"    {page_type}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
