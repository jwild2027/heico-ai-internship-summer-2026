#!/usr/bin/env python
"""Build the interactive org-chart style site for the current TIFF graph."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Allow running this file directly as:
#   python scripts/build_graph_org_chart_site.py
# When Python executes a file inside scripts/, sys.path starts at scripts/
# instead of the repository root, so add the repo root before importing tiff.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.graph_org_chart_site import OrgChartPaths, build_and_write_org_chart_site


def _open_in_browser(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as exc:  # pragma: no cover - best effort helper
        print(f"Could not open browser automatically: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", default="local_data/organization/export")
    parser.add_argument("--graph-dir", default="local_data/organization/graph")
    parser.add_argument("--trait-dir", default="local_data/organization/entity_traits")
    parser.add_argument("--image-recognition-dir", default="local_data/organization/image_recognition")
    parser.add_argument("--organization-dir", default="local_data/organization")
    parser.add_argument("--output-dir", default="local_data/organization/org_chart_site")
    parser.add_argument("--expect-pages", type=int, default=None, help="Fail if the generated view does not contain this many pages.")
    parser.add_argument("--expect-documents", type=int, default=None, help="Fail if the generated view does not contain this many documents.")
    parser.add_argument("--open", action="store_true", help="Open the generated index.html in the default browser.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = OrgChartPaths.from_strings(
        export_dir=args.export_dir,
        graph_dir=args.graph_dir,
        trait_dir=args.trait_dir,
        image_recognition_dir=args.image_recognition_dir,
        organization_dir=args.organization_dir,
        output_dir=args.output_dir,
    )
    report = build_and_write_org_chart_site(paths)
    summary = report.get("summary", {})
    files = report.get("files", {})

    print("Interactive graph org-chart site")
    print(f"  Status: {report.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Corpus:")
    for key in (
        "documents",
        "ata_sections",
        "pages",
        "parts",
        "page_part_links",
        "pages_with_parts",
        "pages_with_source_url",
        "pages_with_tiff_path",
        "pages_with_ocr_path",
        "pages_with_derived_traits",
    ):
        print(f"    {key}: {summary.get(key, 0)}")
    print("  Graph:")
    for key in ("graph_nodes", "graph_edges", "trait_assertions", "trait_nodes"):
        print(f"    {key}: {summary.get(key, 0)}")
    print("  Files written:")
    for label, path in files.items():
        print(f"    {label}: {path}")

    errors: list[str] = []
    if args.expect_pages is not None and summary.get("pages") != args.expect_pages:
        errors.append(f"expected pages={args.expect_pages}, got {summary.get('pages')}")
    if args.expect_documents is not None and summary.get("documents") != args.expect_documents:
        errors.append(f"expected documents={args.expect_documents}, got {summary.get('documents')}")
    if errors:
        print("  Errors:")
        for error in errors:
            print(f"    FAIL {error}")
        return 1

    index = Path(str(files.get("index", ""))).resolve()
    print("\nOpen this file in your browser:")
    print(f"  {index}")
    print("\nOr serve it locally:")
    print(f"  python -m http.server 8765 --directory {paths.output_dir}")
    print("  http://127.0.0.1:8765/index.html")
    if args.open:
        _open_in_browser(index)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
