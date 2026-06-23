from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from tiff.trace_net_e2e_relationship_router_hardening_v29_1 import build_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TRACE-Net relationship router hardening v29.1 artifact.")
    parser.add_argument("--table-exact-search-adapter", required=True, type=Path)
    parser.add_argument("--page-context-v2", required=False, type=Path)
    parser.add_argument("--leiden-communities", required=False, type=Path)
    parser.add_argument("--graph-signal-artifact", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8025)
    parser.add_argument("--llm-mode", default="simulate")
    parser.add_argument("--llm-model", default="gemma4:26b")
    parser.add_argument("--relationship-mode", default="guarded")
    parser.add_argument("--include-standard-demo-queries", action="store_true")
    parser.add_argument("--min-exact-search-documents", type=int, default=10)
    parser.add_argument("--min-endpoint-routes", type=int, default=4)
    parser.add_argument("--min-sample-queries", type=int, default=0)
    parser.add_argument("--min-sample-successes", type=int, default=0)
    parser.add_argument("--min-metadata-count-samples", type=int, default=0)
    parser.add_argument("--max-bad-broad-fallback-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()

    report = build_report(
        table_exact_search_adapter=args.table_exact_search_adapter,
        page_context_v2=args.page_context_v2,
        leiden_communities=args.leiden_communities,
        output_dir=args.output_dir,
        host=args.host,
        port=args.port,
        llm_mode=args.llm_mode,
        llm_model=args.llm_model,
        relationship_mode=args.relationship_mode,
        graph_signal_paths=args.graph_signal_artifact or None,
        include_standard_demo_queries=args.include_standard_demo_queries,
        min_sample_queries=args.min_sample_queries,
        min_sample_successes=args.min_sample_successes,
        min_metadata_count_samples=args.min_metadata_count_samples,
        max_bad_broad_fallback_count=args.max_bad_broad_fallback_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
        quality=args.quality,
    )

    print("TRACE-Net E2E Relationship Router Hardening v29.1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "exact_search_document_count",
        "page_context_v2_page_count",
        "graph_has_v2_page_count",
        "graph_has_nomenclature_page_count",
        "leiden_page_membership_count",
        "endpoint_route_count",
        "sample_query_count",
        "sample_success_count",
        "metadata_count_sample_count",
        "bad_broad_fallback_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "base_url_windows",
        "base_url_open_webui_docker",
        "report_path",
        "samples_jsonl_path",
        "inspect_md_path",
    ]:
        print(f" {key}: {report.get(key)}")

    if args.quality and report["quality_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
