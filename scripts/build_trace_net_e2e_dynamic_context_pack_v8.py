#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_dynamic_context_pack_v8 import (  # noqa: E402
    QualityThresholds,
    build_context_pack_report,
    load_json,
    write_report_files,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build TRACE-Net E2E dynamic context pack v8")
    p.add_argument("--dynamic-tunnel-ranker", required=True)
    p.add_argument("--dynamic-query-tunnels")
    p.add_argument("--table-exact-search-adapter")
    p.add_argument("--table-hybrid-retrieval-bridge")
    p.add_argument("--page-retrieval-profiles")
    p.add_argument("--page-context-v2")
    p.add_argument("--leiden-communities")
    p.add_argument("--community-navigation-metadata-bridge")
    p.add_argument("--route-dispatch-manifest")
    p.add_argument("--table-route-retrieval-handoff-summary")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-evidence-per-pack", type=int, default=5)
    p.add_argument("--min-context-packs", type=int, default=1)
    p.add_argument("--min-ready-context-packs", type=int, default=1)
    p.add_argument("--min-total-evidence-items", type=int, default=1)
    p.add_argument("--min-packs-with-evidence-box", type=int, default=1)
    p.add_argument("--min-packs-with-guidance-box", type=int, default=1)
    p.add_argument("--min-packs-with-rules-box", type=int, default=1)
    p.add_argument("--min-packs-with-graph-or-summary-guidance", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    thresholds = QualityThresholds(
        min_context_packs=args.min_context_packs,
        min_ready_context_packs=args.min_ready_context_packs,
        min_total_evidence_items=args.min_total_evidence_items,
        min_packs_with_evidence_box=args.min_packs_with_evidence_box,
        min_packs_with_guidance_box=args.min_packs_with_guidance_box,
        min_packs_with_rules_box=args.min_packs_with_rules_box,
        min_packs_with_graph_or_summary_guidance=args.min_packs_with_graph_or_summary_guidance,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = build_context_pack_report(
        dynamic_tunnel_ranker=load_json(args.dynamic_tunnel_ranker),
        dynamic_query_tunnels=load_json(args.dynamic_query_tunnels),
        table_exact_search_adapter=load_json(args.table_exact_search_adapter),
        table_hybrid_retrieval_bridge=load_json(args.table_hybrid_retrieval_bridge),
        page_retrieval_profiles=load_json(args.page_retrieval_profiles),
        page_context_v2=load_json(args.page_context_v2),
        leiden_communities=load_json(args.leiden_communities),
        community_navigation_metadata_bridge=load_json(args.community_navigation_metadata_bridge),
        route_dispatch_manifest=load_json(args.route_dispatch_manifest),
        table_route_retrieval_handoff_summary=load_json(args.table_route_retrieval_handoff_summary),
        max_evidence_per_pack=args.max_evidence_per_pack,
        thresholds=thresholds,
    )
    paths = write_report_files(report, args.output_dir)
    s = report["summary"]
    print("TRACE-Net E2E Dynamic Context Pack v8")
    print(f" Status: {report['e2e_dynamic_context_pack_status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "context_pack_count",
        "ready_context_pack_count",
        "total_evidence_item_count",
        "packs_with_evidence_box_count",
        "packs_with_guidance_box_count",
        "packs_with_rules_box_count",
        "packs_with_graph_or_summary_guidance_count",
        "guidance_item_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key, 0)}")
    for key, value in paths.items():
        print(f" {key}: {value}")
    return 0 if (not args.quality or report["quality_status"] == "PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
