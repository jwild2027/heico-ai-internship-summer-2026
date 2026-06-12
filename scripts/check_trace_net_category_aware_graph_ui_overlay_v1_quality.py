from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_category_aware_graph_ui_overlay_v1 import quality_report, read_json, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Category-Aware Graph UI Overlay v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-communities", type=int, default=1)
    parser.add_argument("--min-category-aware-community-cards", type=int, default=1)
    parser.add_argument("--min-page-category-profile-cards", type=int, default=1)
    parser.add_argument("--min-category-ui-edges", type=int, default=1)
    parser.add_argument("--require-source-graph-ui-quality-pass", action="store_true")
    parser.add_argument("--require-source-category-overlay-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = read_json(args.report_path)
    q = quality_report(
        report,
        require_page_count=args.require_page_count,
        min_communities=args.min_communities,
        min_category_aware_community_cards=args.min_category_aware_community_cards,
        min_page_category_profile_cards=args.min_page_category_profile_cards,
        min_category_ui_edges=args.min_category_ui_edges,
        require_source_graph_ui_quality_pass=args.require_source_graph_ui_quality_pass,
        require_source_category_overlay_quality_pass=args.require_source_category_overlay_quality_pass,
        write_json=args.write_json,
    )
    if args.write_json:
        path = Path(args.report_path)
        quality_path = path.with_name("trace_net_category_aware_graph_ui_overlay_v1_quality.json")
        write_json(quality_path, q)
        report["quality"] = q
        report["quality_status"] = q["status"]
        if isinstance(report.get("summary"), dict):
            report["summary"]["status"] = q["status"]
        write_json(path, report)
    print("TRACE-Net category-aware graph UI overlay v1 quality")
    print(f" Status: {q['status']}")
    for key, value in q.get("checks", {}).items():
        print(f" {key}: {value}")
    if args.write_json:
        print(f" quality_path: {Path(args.report_path).with_name('trace_net_category_aware_graph_ui_overlay_v1_quality.json')}")
    return 0 if q["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
