#!/usr/bin/env python3
"""Check entity-trait graph overlay quality."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.entity_trait_graph import DEFAULT_OUTPUT_DIR  # noqa: E402
from tiff.entity_trait_graph_quality import (  # noqa: E402
    DEFAULT_ENTITY_TRAIT_QUALITY_JSON,
    EntityTraitQualityThresholds,
    build_entity_trait_quality_result,
    format_entity_trait_quality_result,
    write_entity_trait_quality_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json-output", default=DEFAULT_ENTITY_TRAIT_QUALITY_JSON)
    parser.add_argument("--min-trait-assertions", type=int, default=1)
    parser.add_argument("--min-trait-nodes", type=int, default=1)
    parser.add_argument("--min-evidence-sources", type=int, default=1)
    parser.add_argument("--min-page-cards", type=int, default=1)
    parser.add_argument("--max-pages-without-traits", type=int, default=0)
    parser.add_argument("--allow-no-derived-traits", action="store_true")
    parser.add_argument("--require-part-cards-when-parts-exist", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    thresholds = EntityTraitQualityThresholds(
        min_trait_assertions=args.min_trait_assertions,
        min_trait_nodes=args.min_trait_nodes,
        min_evidence_sources=args.min_evidence_sources,
        min_page_cards=args.min_page_cards,
        max_pages_without_traits=args.max_pages_without_traits,
        require_derived_traits=not args.allow_no_derived_traits,
        require_part_cards_when_parts_exist=args.require_part_cards_when_parts_exist,
    )
    result = build_entity_trait_quality_result(args.overlay_dir, thresholds=thresholds)
    print(format_entity_trait_quality_result(result))
    if args.write_json:
        out = write_entity_trait_quality_json(result, args.json_output)
        print(f"\nJSON: {out}")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
