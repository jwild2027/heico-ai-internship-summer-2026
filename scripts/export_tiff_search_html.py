#!/usr/bin/env python
"""Export local TIFF search results to a clickable HTML page."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

# Allow running directly from a source checkout without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tiff.search_index import search_db
from tiff.search_results_html import write_search_results_html


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a clickable local HTML page for TIFF search results."
    )
    parser.add_argument("query", help="Keyword, ATA code, publication number, or part number to search")
    parser.add_argument(
        "--db-path",
        default="local_data/db/tiff_search.db",
        help="Path to the TIFF search SQLite database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of search results to include in the HTML page",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "part", "keyword"],
        default="auto",
        help="Search mode. Use part for exact part-number testing.",
    )
    parser.add_argument(
        "--output-html",
        default="local_data/search_results/last_search.html",
        help="Path for the generated HTML page",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Base folder used to resolve relative TIFF/OCR paths",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the generated HTML page in the default browser",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    output_html = Path(args.output_html)
    repo_root = Path(args.repo_root).resolve()

    results = search_db(db_path=db_path, query=args.query, limit=args.limit, mode=args.mode)
    output = write_search_results_html(
        query=args.query,
        results=results,
        output_path=output_html,
        db_path=db_path,
        base_dir=repo_root,
        title="Local TIFF Search Click-Through Results",
    )

    print("TIFF search click-through HTML created")
    print(f"  Query: {args.query}")
    print(f"  Mode: {args.mode}")
    print(f"  Results: {len(results)}")
    print(f"  HTML: {output}")

    if args.open:
        webbrowser.open(output.resolve().as_uri())
        print("  Opened in browser: yes")
    else:
        print("  Opened in browser: no")
        print("  Add --open to open it automatically")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
