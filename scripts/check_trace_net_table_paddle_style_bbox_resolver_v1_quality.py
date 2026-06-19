from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_table_paddle_style_bbox_resolver_v1 import Thresholds, build_quality, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Paddle-style table bbox resolver v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-resolver-cards", type=int, default=1)
    parser.add_argument("--min-selected-bbox-cards", type=int, default=1)
    parser.add_argument("--max-route-blocked-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-resolver-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-route-contract-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.report_path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    quality = build_quality(
        summary,
        Thresholds(
            min_resolver_cards=args.min_resolver_cards,
            min_selected_bbox_cards=args.min_selected_bbox_cards,
            max_route_blocked_cards=args.max_route_blocked_cards,
            max_unsafe_resolver_cards=args.max_unsafe_resolver_cards,
            max_answer_permission_count=args.max_answer_permission_count,
            max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
            require_route_contract_quality_pass=args.require_route_contract_quality_pass,
            require_no_answer_permission=args.require_no_answer_permission,
        ),
    )
    print("TRACE-Net Paddle-style table bbox resolver v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "resolver_card_count",
        "selected_bbox_card_count",
        "candidate_bbox_count",
        "route_blocked_card_count",
        "review_required_card_count",
        "unsafe_resolver_card_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_table_paddle_style_bbox_resolver_v1_quality.json")
        write_json(quality_path, quality)
        print(f" quality_path: {quality_path}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
