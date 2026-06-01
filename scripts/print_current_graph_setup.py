#!/usr/bin/env python
"""Print the current local TIFF document graph setup.

This is a read-only debug/reporting command. It expects the local generated
artifacts under local_data/ and prints the core graph plus the entity-trait
"character sheet" overlay when present.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from tiff.graph_setup_report import (
    DEFAULT_EXPORT_DIR,
    DEFAULT_GRAPH_DIR,
    DEFAULT_IMAGE_QUALITY_PATH,
    DEFAULT_TRAIT_DIR,
    DEFAULT_VISUAL_QUALITY_PATH,
    build_current_graph_setup_report,
    format_current_graph_setup_report,
    write_graph_setup_report_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print current TIFF graph setup from local artifacts.")
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR), help="Organization export directory.")
    parser.add_argument("--graph-dir", default=str(DEFAULT_GRAPH_DIR), help="Document graph artifact directory.")
    parser.add_argument("--trait-dir", default=str(DEFAULT_TRAIT_DIR), help="Entity-trait overlay artifact directory.")
    parser.add_argument("--image-quality", default=str(DEFAULT_IMAGE_QUALITY_PATH), help="Page image-recognition quality JSON.")
    parser.add_argument("--visual-quality", default=str(DEFAULT_VISUAL_QUALITY_PATH), help="Page visual/object quality JSON.")
    parser.add_argument("--expect-pages", type=int, default=None, help="Fail if the page count does not match this value.")
    parser.add_argument("--expect-documents", type=int, default=None, help="Fail if the document count does not match this value.")
    parser.add_argument("--samples", type=int, default=8, help="Number of sample page character sheets to print.")
    parser.add_argument("--top-edge-types", type=int, default=20, help="Number of edge types to print.")
    parser.add_argument("--write-json", default="", help="Optional path to write the full report JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_current_graph_setup_report(
        export_dir=Path(args.export_dir),
        graph_dir=Path(args.graph_dir),
        trait_dir=Path(args.trait_dir),
        image_quality_path=Path(args.image_quality),
        visual_quality_path=Path(args.visual_quality),
        expected_pages=args.expect_pages,
        expected_documents=args.expect_documents,
        sample_limit=args.samples,
    )
    print(
        format_current_graph_setup_report(
            report,
            sample_limit=args.samples,
            top_edge_types=args.top_edge_types,
        )
    )
    if args.write_json:
        path = write_graph_setup_report_json(report, args.write_json)
        print(f"\nJSON: {path}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
