#!/usr/bin/env python3
"""Export graph-style nodes/edges from document organization JSON artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.document_organization_graph import (  # noqa: E402
    GRAPH_EDGES_FILE,
    GRAPH_NODES_FILE,
    GRAPH_SUMMARY_FILE,
    export_graph,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export graph-style organization nodes and edges.")
    parser.add_argument("--export-dir", default="local_data/organization/export", help="Input organization export directory.")
    parser.add_argument("--output-dir", default="local_data/organization/graph", help="Output graph directory.")
    parser.add_argument("--strict", action="store_true", help="Fail if required organization export files are missing or empty.")
    parser.add_argument("--sample-limit", type=int, default=8, help="Number of node/edge type examples to print.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = export_graph(args.export_dir, args.output_dir, strict=args.strict)
    except Exception as exc:  # pragma: no cover - CLI safety
        print("Document organization graph export")
        print("  Status: FAILED")
        print(f"  Error: {exc}")
        return 2

    node_types = result.summary["graph_counts"]["node_types"]
    edge_types = result.summary["graph_counts"]["edge_types"]
    output_dir = Path(args.output_dir)

    print("Document organization graph export")
    print(f"  Status: {result.status}")
    print(f"  Export dir: {args.export_dir}")
    print(f"  Output dir: {output_dir}")
    print("\nGraph counts:")
    print(f"  Nodes: {result.summary['graph_counts']['nodes']}")
    print(f"  Edges: {result.summary['graph_counts']['edges']}")
    print("\nNode types:")
    for key in sorted(node_types):
        print(f"  {key}: {node_types[key]}")
    print("\nEdge types:")
    for key in sorted(edge_types):
        print(f"  {key}: {edge_types[key]}")

    if result.nodes:
        print("\nSample nodes:")
        for node in result.nodes[: args.sample_limit]:
            print(f"  {node['type']} | {node['id']} | {node.get('label', '')}")
    if result.edges:
        print("\nSample edges:")
        for edge in result.edges[: args.sample_limit]:
            print(f"  {edge['type']} | {edge['from']} -> {edge['to']}")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    print("\nFiles written:")
    print(f"  {output_dir / GRAPH_NODES_FILE}")
    print(f"  {output_dir / GRAPH_EDGES_FILE}")
    print(f"  {output_dir / GRAPH_SUMMARY_FILE}")
    return 0 if result.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
