#!/usr/bin/env python
"""Trace graph paths from parts/pages/ATA/vector-style payloads to sources and AI context."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.document_graph_traceability import (
    build_traceability_report,
    render_traceability_report,
    write_traceability_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trace document graph paths for source-backed answers.")
    parser.add_argument("--graph-dir", default="local_data/organization/graph")
    parser.add_argument("--part", help="Part number to trace, e.g. 120-37313-001.")
    parser.add_argument("--page", help="Page id to trace, e.g. t_p_120_1176_p000083.")
    parser.add_argument("--ata", help="ATA code to trace, e.g. 25-21-00.")
    parser.add_argument("--vector-page", help="Simulate a Qdrant payload returning this page_id, then resolve through graph.")
    parser.add_argument("--vector-chunk", help="Optional simulated Qdrant chunk_id payload.")
    parser.add_argument("--vector-score", type=float, help="Optional simulated Qdrant score payload.")
    parser.add_argument("--limit", type=int, default=8, help="Max sample pages/parts to show per trace.")
    parser.add_argument("--max-pages", type=int, help="Alias for --limit when tracing ATA/page samples.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/organization/graph/traceability_report.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    limit = args.max_pages if args.max_pages is not None else args.limit
    report = build_traceability_report(
        graph_dir=args.graph_dir,
        part=args.part,
        page=args.page,
        ata=args.ata,
        vector_page=args.vector_page,
        vector_chunk=args.vector_chunk,
        vector_score=args.vector_score,
        limit=limit,
        strict=args.strict,
    )
    print(render_traceability_report(report))
    if args.write_json:
        write_traceability_json(report, args.json_output)
        print(f"\nJSON: {args.json_output}")
    return 0 if report.status == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
