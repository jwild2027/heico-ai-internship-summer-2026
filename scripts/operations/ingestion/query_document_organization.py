#!/usr/bin/env python
"""Query exported document-organization JSON files."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.document_organization_query import (  # noqa: E402
    format_ata,
    format_page,
    format_part,
    format_summary,
    load_export,
    query_ata,
    query_page,
    query_part,
    summarize_export,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--export-dir",
        default="local_data/organization/export",
        help="Directory containing organization export JSON files.",
    )
    parser.add_argument("--part", action="append", default=[], help="Part number to look up.")
    parser.add_argument("--ata", action="append", default=[], help="ATA code to look up.")
    parser.add_argument("--page", action="append", default=[], help="Page id or label to look up.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum rows per query.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero when a requested part/ATA/page is not found.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        export = load_export(args.export_dir)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(f"Document organization query\n  Status: FAIL\n  Error: {exc}")
        return 1

    print(format_summary(summarize_export(export)))

    errors: list[str] = []
    for part in args.part:
        rows = query_part(export, part, limit=args.limit)
        print(f"\nPart query: {part}")
        if not rows:
            print("  No matches")
            errors.append(f"part not found: {part}")
        for index, row in enumerate(rows, start=1):
            print(f"  {index}. {format_part(row).replace(chr(10), chr(10) + '     ')}")

    for ata in args.ata:
        rows = query_ata(export, ata, limit=args.limit)
        print(f"\nATA query: {ata}")
        if not rows:
            print("  No matches")
            errors.append(f"ATA not found: {ata}")
        for index, row in enumerate(rows, start=1):
            print(f"  {index}. {format_ata(row)}")

    for page in args.page:
        rows = query_page(export, page, limit=args.limit)
        print(f"\nPage query: {page}")
        if not rows:
            print("  No matches")
            errors.append(f"page not found: {page}")
        for index, row in enumerate(rows, start=1):
            print(f"  {index}. {format_page(row).replace(chr(10), chr(10) + '     ')}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")
        if args.strict:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
