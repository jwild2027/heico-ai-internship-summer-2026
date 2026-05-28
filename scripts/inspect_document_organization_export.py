#!/usr/bin/env python3
"""Inspect UI/API-ready document organization export JSON files."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.document_organization_inspector import inspect_export, write_inspection_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", default="local_data/organization/export")
    parser.add_argument("--part", action="append", default=[], help="Part number expected in part_tree.json. May be repeated.")
    parser.add_argument("--page-id", action="append", default=[], help="Page id expected in page_index.json. May be repeated.")
    parser.add_argument("--ata", action="append", default=[], help="ATA code expected in ATA tree. May be repeated.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/organization/export_inspection.json")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if inspection finds errors.")
    return parser


def print_result(result) -> None:
    print("Document organization export inspection")
    print(f"  Status: {'OK' if result.ok else 'NEEDS ATTENTION'}")
    print(f"  Export dir: {result.export_dir}")
    print("")
    print("Files present:")
    for name, exists in result.files_present.items():
        print(f"  {name}: {exists}")
    print("")
    print("Counts:")
    print(f"  Manuals: {result.manual_count}")
    print(f"  Pages: {result.page_count}")
    print(f"  ATA groups: {result.ata_group_count}")
    print(f"  Parts: {result.part_count}")
    print("")
    if result.sample_parts:
        print("Sample part entries:")
        for i, item in enumerate(result.sample_parts, start=1):
            print(f"  {i}. {item.get('part_number')} | {item.get('nomenclature')} | pages={item.get('page_count')} mentions={item.get('mention_count')}")
        print("")
    if result.sample_ata:
        print("Sample ATA entries:")
        for i, item in enumerate(result.sample_ata, start=1):
            print(f"  {i}. ATA {item.get('ata')} | manual={item.get('manual')} | pages={item.get('page_count')}")
        print("")
    if result.sample_pages:
        print("Sample page entries:")
        for i, item in enumerate(result.sample_pages, start=1):
            print(f"  {i}. {item.get('page_id')} | ATA {item.get('ata')} | page {item.get('page_label')}")
            if item.get("source_url"):
                print(f"     Source: {item.get('source_url')}")
        print("")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
        print("")
    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = inspect_export(
        args.export_dir,
        sample_parts=args.part,
        sample_pages=args.page_id,
        sample_atas=args.ata,
        limit=args.limit,
    )
    print_result(result)
    if args.write_json:
        path = write_inspection_json(result, args.json_output)
        print(f"JSON: {path}")
    return 1 if args.strict and not result.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
