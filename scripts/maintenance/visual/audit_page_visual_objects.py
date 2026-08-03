#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.page_visual_object_audit import (  # noqa: E402
    DEFAULT_CONTEXT_FILE,
    DEFAULT_EXPORT_DIR,
    DEFAULT_GRAPH_SUMMARY,
    DEFAULT_OUTPUT,
    audit_page_visual_objects,
    write_visual_object_audit,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit page-level visual/table/figure signals from OCR text and AI page context.")
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--context-file", type=Path, default=DEFAULT_CONTEXT_FILE)
    parser.add_argument("--graph-summary", type=Path, default=DEFAULT_GRAPH_SUMMARY)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true", help="Return nonzero if the audit status is not OK.")
    args = parser.parse_args()

    summary, rows = audit_page_visual_objects(
        export_dir=args.export_dir,
        context_file=args.context_file,
        graph_summary=args.graph_summary,
        sample_limit=args.sample_limit,
        repo_root=Path.cwd(),
    )
    if args.write_json:
        write_visual_object_audit(summary, rows, args.json_output)

    print("Page visual/object audit")
    print(f"  Status: {summary.status}")
    print(f"  Export dir: {summary.export_dir}")
    print(f"  Context file: {summary.context_file}")
    print()
    print("Counts:")
    print(f"  Pages checked: {summary.pages_checked}")
    print(f"  Pages with context: {summary.pages_with_context}")
    print(f"  Pages with source URLs: {summary.pages_with_source_url}")
    print(f"  Pages with OCR text: {summary.pages_with_ocr_text}")
    print(f"  Pages without OCR text: {summary.pages_without_ocr_text}")
    print()
    print("Page roles:")
    for role, count in summary.role_counts.items():
        print(f"  {role}: {count}")
    print()
    print("Visual/table/figure signals:")
    print(f"  Figure-role pages: {summary.figure_role_pages}")
    print(f"  Table-role pages: {summary.table_role_pages}")
    print(f"  Parts-list role pages: {summary.parts_list_role_pages}")
    print(f"  Likely visual pages: {summary.likely_visual_pages}")
    print(f"  Likely figure pages: {summary.likely_figure_pages}")
    print(f"  Likely table pages: {summary.likely_table_pages}")
    print(f"  Pages with figure refs: {summary.pages_with_figure_refs}")
    print(f"  Pages with sheet refs: {summary.pages_with_sheet_refs}")
    print(f"  Pages with table refs: {summary.pages_with_table_refs}")
    print(f"  Pages with illustration refs: {summary.pages_with_illustration_refs}")
    print(f"  Pages with image/diagram terms: {summary.pages_with_image_terms}")
    print(f"  Total figure refs: {summary.total_figure_refs}")
    print(f"  Total sheet refs: {summary.total_sheet_refs}")
    print(f"  Total table refs: {summary.total_table_refs}")
    print(f"  Total illustration refs: {summary.total_illustration_refs}")
    print(f"  Total image/diagram terms: {summary.total_image_terms}")
    print(f"  Total part-like refs in combined OCR/context: {summary.total_part_refs}")
    print()
    print("Graph linkage:")
    print(f"  page_context nodes: {summary.graph_page_context_nodes}")
    print(f"  HAS_CONTEXT edges: {summary.graph_has_context_edges}")
    print(f"  TAGGED_AS edges: {summary.graph_tagged_as_edges}")
    print(f"  HIGHLIGHTS_PART edges: {summary.graph_highlights_part_edges}")

    if summary.sample_rows:
        print()
        print("Sample visual/table/figure rows:")
        for idx, row in enumerate(summary.sample_rows, 1):
            print(
                f"  {idx}. {row['page_id']} | role={row['role']} | label={row.get('page_label') or '-'} "
                f"| figure_refs={row['figure_refs']} sheet_refs={row['sheet_refs']} table_refs={row['table_refs']} score={row['visual_signal_score']}"
            )
            if row.get("context_summary"):
                print(f"     context: {row['context_summary'][:180]}")
            if row.get("sample_figure_refs"):
                print(f"     figure refs: {', '.join(row['sample_figure_refs'])}")
            if row.get("sample_sheet_refs"):
                print(f"     sheet refs: {', '.join(row['sample_sheet_refs'])}")
            if row.get("sample_table_refs"):
                print(f"     table refs: {', '.join(row['sample_table_refs'])}")
            if row.get("source_url"):
                print(f"     source: {row['source_url']}")

    if summary.warnings:
        print()
        print("Warnings:")
        for warning in summary.warnings:
            print(f"  - {warning}")

    if args.write_json:
        print()
        print(f"JSON: {args.json_output}")

    if args.strict and summary.status.lower() != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
