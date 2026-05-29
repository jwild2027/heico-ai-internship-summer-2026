#!/usr/bin/env python
"""Run a read-only traversal test against the exported organization graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.document_graph_traversal import build_traversal_report, render_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test document graph traversal paths.")
    parser.add_argument("--graph-dir", default="local_data/organization/graph")
    parser.add_argument("--document", help="Document id/title query. Defaults to first document.")
    parser.add_argument("--page", help="Page id to start/verify, e.g. t_p_120_1176_p000083.")
    parser.add_argument("--part", default="120-37313-001", help="Part number to traverse through. Defaults to 120-37313-001.")
    parser.add_argument("--limit", type=int, default=5, help="Number of part->page context samples to show.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if the main traversal path is incomplete.")
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default="local_data/organization/graph/graph_traversal_test.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_traversal_report(
        graph_dir=args.graph_dir,
        document=args.document,
        page=args.page,
        part=args.part,
        limit=args.limit,
        strict=args.strict,
    )
    print(render_report(report))
    if args.write_json:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report.to_jsonable(), indent=2), encoding="utf-8")
        print(f"\nJSON: {output}")
    return 0 if report.status == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
