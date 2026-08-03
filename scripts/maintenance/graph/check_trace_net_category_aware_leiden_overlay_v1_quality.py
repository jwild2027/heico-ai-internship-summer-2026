from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_category_aware_leiden_overlay_v1 import quality_report, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Category-Aware Leiden Overlay v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-communities", type=int, default=1)
    parser.add_argument("--min-page-category-profiles", type=int, default=1)
    parser.add_argument("--min-communities-with-category-summary", type=int, default=1)
    parser.add_argument("--min-category-overlay-edges", type=int, default=1)
    parser.add_argument("--require-source-leiden-quality-pass", action="store_true")
    parser.add_argument("--require-source-taxonomy-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = Path(args.report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    q = quality_report(
        report,
        require_page_count=args.require_page_count,
        min_communities=args.min_communities,
        min_page_category_profiles=args.min_page_category_profiles,
        min_communities_with_category_summary=args.min_communities_with_category_summary,
        min_category_overlay_edges=args.min_category_overlay_edges,
        require_source_leiden_quality_pass=args.require_source_leiden_quality_pass,
        require_source_taxonomy_quality_pass=args.require_source_taxonomy_quality_pass,
        write_json=args.write_json,
    )
    if args.write_json:
        quality_path = report_path.with_name("trace_net_category_aware_leiden_overlay_v1_quality.json")
        write_json(quality_path, q)
    summary = q.get("summary", {})
    print("TRACE-Net category-aware Leiden overlay v1 quality")
    print(f" Status: {q['status']}")
    for key in [
        "page_count",
        "community_count",
        "page_category_profile_count",
        "communities_with_category_summary_count",
        "category_overlay_edge_count",
        "giant_global_category_hub_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if args.write_json:
        print(f" quality_path: {report_path.with_name('trace_net_category_aware_leiden_overlay_v1_quality.json')}")
    if q["status"] != "PASS":
        for issue in q.get("issues", []):
            print(f" issue: {issue}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
