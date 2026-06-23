#!/usr/bin/env python3
"""Build TRACE-Net E2E dynamic query tunnels v3."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_dynamic_query_tunnels_v3 import (  # noqa: E402
    DEFAULT_QUERY_PROBES,
    build_dynamic_query_tunnels_report,
    print_terminal_report,
    write_report_files,
)


def _path(value: str | None) -> Path | None:
    return Path(value) if value else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dynamic-query-endpoint", default="local_data/organization/trace_net/e2e_dynamic_query_endpoint/trace_net_e2e_dynamic_query_endpoint_v1.json")
    parser.add_argument("--table-exact-search-adapter", default="local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json")
    parser.add_argument("--table-hybrid-retrieval-bridge", default="local_data/organization/trace_net/table_hybrid_retrieval_bridge/trace_net_table_hybrid_retrieval_bridge_v1.json")
    parser.add_argument("--page-retrieval-profiles", default="local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json")
    parser.add_argument("--page-context-v2", default="local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json")
    parser.add_argument("--leiden-communities", default="local_data/organization/trace_net/leiden_communities/trace_net_leiden_communities_v1.json")
    parser.add_argument("--community-navigation-metadata-bridge", default="local_data/organization/trace_net/community_navigation_metadata_bridge/trace_net_community_navigation_metadata_bridge_v1.json")
    parser.add_argument("--route-dispatch-manifest", default="local_data/organization/trace_net/route_dispatch_manifest/trace_net_route_dispatch_manifest_v1.json")
    parser.add_argument("--table-route-retrieval-handoff-summary", default="local_data/organization/trace_net/table_route_retrieval_handoff_summary/trace_net_table_route_retrieval_handoff_summary_v1.json")
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--include-standard-demo-queries", action="store_true")
    parser.add_argument("--max-tunnels-per-query", type=int, default=8)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-query-tunnel-plans", type=int, default=5)
    parser.add_argument("--min-ready-query-tunnel-plans", type=int, default=5)
    parser.add_argument("--min-total-tunnels", type=int, default=20)
    parser.add_argument("--min-unique-tunnel-types", type=int, default=3)
    parser.add_argument("--min-plans-with-table-tunnels", type=int, default=5)
    parser.add_argument("--min-plans-with-graph-or-summary-tunnels", type=int, default=1)
    parser.add_argument("--min-available-artifacts", type=int, default=3)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queries = list(args.query or [])
    if args.include_standard_demo_queries or not queries:
        queries.extend(DEFAULT_QUERY_PROBES)

    thresholds = {
        "min_query_tunnel_plans": args.min_query_tunnel_plans,
        "min_ready_query_tunnel_plans": args.min_ready_query_tunnel_plans,
        "min_total_tunnels": args.min_total_tunnels,
        "min_unique_tunnel_types": args.min_unique_tunnel_types,
        "min_plans_with_table_tunnels": args.min_plans_with_table_tunnels,
        "min_plans_with_graph_or_summary_tunnels": args.min_plans_with_graph_or_summary_tunnels,
        "min_available_artifacts": args.min_available_artifacts,
        "max_unsafe_records": args.max_unsafe_records,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
    }

    report = build_dynamic_query_tunnels_report(
        queries=queries,
        dynamic_query_endpoint=_path(args.dynamic_query_endpoint),
        table_exact_search_adapter=_path(args.table_exact_search_adapter),
        table_hybrid_retrieval_bridge=_path(args.table_hybrid_retrieval_bridge),
        page_retrieval_profiles=_path(args.page_retrieval_profiles),
        page_context_v2=_path(args.page_context_v2),
        leiden_communities=_path(args.leiden_communities),
        community_navigation_metadata_bridge=_path(args.community_navigation_metadata_bridge),
        route_dispatch_manifest=_path(args.route_dispatch_manifest),
        table_route_retrieval_handoff_summary=_path(args.table_route_retrieval_handoff_summary),
        max_tunnels_per_query=args.max_tunnels_per_query,
        thresholds=thresholds,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    paths = write_report_files(report, Path(args.output_dir))
    print(print_terminal_report(report))
    for key, value in paths.items():
        print(f" {key}: {value}")
    return 0 if not args.quality or report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
