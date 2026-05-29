#!/usr/bin/env python
"""Inspect generated AI page contexts and their graph coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.page_context_inspector import DEFAULT_CONTEXT_FILE, DEFAULT_GRAPH_SUMMARY, inspect_page_contexts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect generated page context graph objects.")
    parser.add_argument("--context-file", default=str(DEFAULT_CONTEXT_FILE))
    parser.add_argument("--graph-summary", default=str(DEFAULT_GRAPH_SUMMARY))
    parser.add_argument("--page", action="append", default=[], help="Page ID to show. Can be repeated.")
    parser.add_argument("--role", action="append", default=[], help="Filter by page role. Can be repeated.")
    parser.add_argument("--topic", action="append", default=[], help="Filter by topic. Can be repeated.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/organization/context/page_context_inspection.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    inspection = inspect_page_contexts(
        context_file=Path(args.context_file),
        graph_summary_file=Path(args.graph_summary) if args.graph_summary else None,
        page_ids=args.page,
        roles=args.role,
        topics=args.topic,
        limit=args.limit,
        strict=args.strict,
    )

    print("Page context inspection")
    print(f"  Status: {inspection.status}")
    print(f"  Context file: {inspection.context_file}")
    if inspection.graph_summary_file:
        print(f"  Graph summary: {inspection.graph_summary_file}")
    print("\nCounts:")
    print(f"  Contexts: {inspection.total_contexts}")
    print(f"  Contexts with warnings: {inspection.contexts_with_warnings}")
    print(f"  Contexts with errors: {inspection.contexts_with_errors}")
    print(f"  Highlighted parts: {inspection.highlighted_part_count}")
    print(f"  Unique highlighted parts: {inspection.unique_highlighted_parts}")
    print("\nRole counts:")
    for key, value in inspection.role_counts.items():
        print(f"  {key}: {value}")
    print("\nConfidence counts:")
    for key, value in inspection.confidence_counts.items():
        print(f"  {key}: {value}")
    if inspection.warning_counts:
        print("\nWarning counts:")
        for key, value in inspection.warning_counts.items():
            print(f"  {key}: {value}")
    if inspection.topic_counts:
        print("\nTop topics:")
        for key, value in inspection.topic_counts.items():
            print(f"  {key}: {value}")
    print("\nGraph linkage:")
    print(f"  page_context nodes: {inspection.graph_page_context_nodes}")
    print(f"  HAS_CONTEXT edges: {inspection.graph_has_context_edges}")
    print(f"  TAGGED_AS edges: {inspection.graph_tagged_as_edges}")
    print(f"  HIGHLIGHTS_PART edges: {inspection.graph_highlights_part_edges}")

    if inspection.selected_contexts:
        print("\nSample contexts:")
        for idx, row in enumerate(inspection.selected_contexts, start=1):
            warning_marker = " warning" if row.get("warnings") else ""
            print(
                f"  {idx}. {row.get('page_id')} | role={row.get('page_role')} | "
                f"confidence={row.get('confidence')}{warning_marker}"
            )
            print(f"     {row.get('summary')}")
            if row.get("topics"):
                print(f"     topics: {', '.join(row['topics'][:8])}")
            if row.get("important_parts"):
                print(f"     parts: {', '.join(row['important_parts'][:8])}")
            if row.get("warnings"):
                print(f"     warnings: {', '.join(row['warnings'][:8])}")

    if inspection.issues:
        print("\nIssues:")
        for issue in inspection.issues:
            print(f"  - {issue}")

    if args.write_json:
        out_path = Path(args.json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(inspection.to_dict(), indent=2), encoding="utf-8")
        print(f"\nJSON: {out_path}")

    return 0 if inspection.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
