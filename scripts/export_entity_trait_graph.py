#!/usr/bin/env python3
"""Export entity-trait graph overlay and page/part character cards."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.entity_trait_graph import (  # noqa: E402
    DEFAULT_GRAPH_DIR,
    DEFAULT_IMAGE_RECOGNITION_AUDIT,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PAGE_VISUAL_OBJECT_AUDIT,
    ENTITY_TRAITS_FILE,
    PAGE_CHARACTER_CARDS_FILE,
    PART_CHARACTER_CARDS_FILE,
    TRAIT_GRAPH_EDGES_FILE,
    TRAIT_GRAPH_NODES_FILE,
    TRAIT_GRAPH_SUMMARY_FILE,
    export_entity_trait_overlay,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-dir", default=DEFAULT_GRAPH_DIR, help="Input document graph directory.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output trait overlay directory.")
    parser.add_argument(
        "--image-audit",
        default=DEFAULT_IMAGE_RECOGNITION_AUDIT,
        help="Optional page image-recognition audit JSON.",
    )
    parser.add_argument(
        "--page-visual-audit",
        default=DEFAULT_PAGE_VISUAL_OBJECT_AUDIT,
        help="Optional page visual/object audit JSON.",
    )
    parser.add_argument("--sample-limit", type=int, default=8, help="Number of sample assertions/cards to print.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = export_entity_trait_overlay(
        graph_dir=args.graph_dir,
        output_dir=args.output_dir,
        image_audit_path=args.image_audit,
        page_visual_audit_path=args.page_visual_audit,
    )
    overlay_counts = result.summary["overlay_counts"]
    input_counts = result.summary["input_counts"]
    output_dir = Path(args.output_dir)

    print("Entity-trait graph overlay export")
    print(f"  Status: {result.status}")
    print(f"  Graph dir: {args.graph_dir}")
    print(f"  Output dir: {output_dir}")
    print("  Input counts:")
    for key in sorted(input_counts):
        print(f"    {key}: {input_counts[key]}")
    print("  Overlay counts:")
    for key in (
        "nodes",
        "edges",
        "assertions",
        "trait_nodes",
        "trait_assertion_nodes",
        "evidence_source_nodes",
        "derived_assertions",
        "page_cards",
        "part_cards",
    ):
        print(f"    {key}: {overlay_counts.get(key, 0)}")

    if result.assertions:
        print("\nSample assertions:")
        for assertion in result.assertions[: args.sample_limit]:
            print(
                "  "
                f"{assertion['entity_id']} | "
                f"{assertion['trait_type']}:{assertion['trait_key']}={assertion['trait_value']} | "
                f"{assertion['scope']} | {assertion['source']}"
            )
    if result.page_cards:
        print("\nSample page cards:")
        for card in result.page_cards[: args.sample_limit]:
            derived = ", ".join(card.get("derived_traits") or [])
            print(f"  {card['entity_id']} | derived=[{derived}]")
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    print("\nFiles written:")
    for name in (
        ENTITY_TRAITS_FILE,
        TRAIT_GRAPH_NODES_FILE,
        TRAIT_GRAPH_EDGES_FILE,
        PAGE_CHARACTER_CARDS_FILE,
        PART_CHARACTER_CARDS_FILE,
        TRAIT_GRAPH_SUMMARY_FILE,
    ):
        print(f"  {output_dir / name}")
    return 0 if result.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
