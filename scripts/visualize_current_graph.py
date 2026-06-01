#!/usr/bin/env python3
"""Generate local HTML visualizations for the current TIFF graph."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.graph_visualization import (  # noqa: E402
    DEFAULT_ENTITY_TRAIT_DIR,
    DEFAULT_GRAPH_DIR,
    DEFAULT_VISUALIZATION_DIR,
    export_graph_visualizations,
    format_graph_visualization_result,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-dir", default=DEFAULT_GRAPH_DIR, help="Directory containing graph_nodes.json and graph_edges.json.")
    parser.add_argument("--trait-dir", default=DEFAULT_ENTITY_TRAIT_DIR, help="Directory containing entity-trait overlay outputs.")
    parser.add_argument("--output-dir", default=DEFAULT_VISUALIZATION_DIR, help="Directory where HTML visualizations will be written.")
    parser.add_argument("--samples", type=int, default=12, help="Number of page neighborhoods to render.")
    parser.add_argument("--expect-pages", type=int, default=None, help="Optional expected page-card count; nonzero exit if it differs.")
    parser.add_argument("--expect-documents", type=int, default=None, help="Optional expected document-node count; nonzero exit if it differs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = export_graph_visualizations(
        graph_dir=args.graph_dir,
        trait_dir=args.trait_dir,
        output_dir=args.output_dir,
        sample_limit=args.samples,
    )
    print(format_graph_visualization_result(result))

    status_ok = result.status == "ok"
    corpus = result.summary.get("processed_corpus", {})
    if args.expect_pages is not None and corpus.get("pages") != args.expect_pages:
        print(f"\nExpected pages={args.expect_pages}, got {corpus.get('pages')}")
        status_ok = False
    if args.expect_documents is not None and corpus.get("documents") != args.expect_documents:
        print(f"\nExpected documents={args.expect_documents}, got {corpus.get('documents')}")
        status_ok = False

    if status_ok:
        index_path = Path(result.files["index"]).resolve()
        print(f"\nOpen this file in your browser:\n  {index_path}")
    return 0 if status_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
