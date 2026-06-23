#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_optional_tunnel_activator_v5 import build_optional_tunnel_activation_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E optional tunnel activator v5 artifacts.")
    parser.add_argument("--trace-net-root", default="local_data/organization/trace_net")
    parser.add_argument("--table-exact-search-adapter", required=True)
    parser.add_argument("--table-hybrid-retrieval-bridge", required=True)
    parser.add_argument("--page-retrieval-profiles", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-activated-tunnels", type=int, default=4)
    parser.add_argument("--min-graph-or-summary-tunnels", type=int, default=2)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()

    report = build_optional_tunnel_activation_report(
        trace_net_root=Path(args.trace_net_root),
        table_exact_search_adapter=Path(args.table_exact_search_adapter),
        table_hybrid_retrieval_bridge=Path(args.table_hybrid_retrieval_bridge),
        page_retrieval_profiles=Path(args.page_retrieval_profiles),
        output_dir=Path(args.output_dir),
        min_activated_tunnels=args.min_activated_tunnels,
        min_graph_or_summary_tunnels=args.min_graph_or_summary_tunnels,
    )

    summary = report.get("summary", {})
    print("TRACE-Net E2E Optional Tunnel Activator v5")
    print(f" Status: {report.get('e2e_optional_tunnel_activator_status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "activated_optional_tunnel_count",
        "graph_or_summary_tunnel_count",
        "page_summary_tunnel_activated",
        "graph_community_tunnel_activated",
        "graph_navigation_tunnel_activated",
        "table_route_summary_tunnel_activated",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {Path(args.output_dir) / 'trace_net_e2e_optional_tunnel_activator_v5.json'}")
    print(f" inspect_md_path: {Path(args.output_dir) / 'trace_net_e2e_optional_tunnel_activator_v5.md'}")

    if args.quality and report.get("quality_status") != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
