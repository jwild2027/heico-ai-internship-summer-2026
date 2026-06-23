import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 import (
    attach_quality,
    build_state,
    evaluate_quality,
    write_endpoint_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net live orchestrator stage timing + fast path v27")
    parser.add_argument("--table-exact-search-adapter", required=True)
    parser.add_argument("--page-context-v2")
    parser.add_argument("--leiden-communities")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8022)
    parser.add_argument("--llm-mode", default="simulate", choices=["simulate", "ollama"])
    parser.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--llm-model", default="gemma4:26b")
    parser.add_argument("--llm-api-key", default="ollama")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--request-timeout", type=int, default=240)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--max-pages-per-community", type=int, default=25)
    parser.add_argument("--fast-path-mode", default="exact", choices=["exact", "all_direct", "off"])
    parser.add_argument("--include-standard-demo-queries", action="store_true")
    parser.add_argument("--min-exact-search-documents", type=int, default=10)
    parser.add_argument("--min-endpoint-routes", type=int, default=4)
    parser.add_argument("--min-sample-queries", type=int, default=0)
    parser.add_argument("--min-sample-successes", type=int, default=0)
    parser.add_argument("--min-stage-timing-records", type=int, default=0)
    parser.add_argument("--min-fast-path-samples", type=int, default=0)
    parser.add_argument("--max-sample-llm-calls", type=int)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()

    state = build_state(
        table_exact_search_adapter_path=Path(args.table_exact_search_adapter),
        output_dir=Path(args.output_dir),
        page_context_v2_path=Path(args.page_context_v2) if args.page_context_v2 else None,
        leiden_communities_path=Path(args.leiden_communities) if args.leiden_communities else None,
        host=args.host,
        port=args.port,
        llm_mode=args.llm_mode,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
        llm_api_key=args.llm_api_key,
        temperature=args.temperature,
        request_timeout=args.request_timeout,
        top_k=args.top_k,
        max_pages_per_community=args.max_pages_per_community,
        fast_path_mode=args.fast_path_mode,
        include_standard_demo_queries=args.include_standard_demo_queries,
    )
    quality_status, checks = evaluate_quality(
        state,
        min_exact_search_documents=args.min_exact_search_documents,
        min_endpoint_routes=args.min_endpoint_routes,
        min_sample_queries=args.min_sample_queries,
        min_sample_successes=args.min_sample_successes,
        min_stage_timing_records=args.min_stage_timing_records,
        min_fast_path_samples=args.min_fast_path_samples,
        max_sample_llm_calls=args.max_sample_llm_calls,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    attach_quality(state, quality_status, checks)
    paths = write_endpoint_files(state, Path(args.output_dir))

    print("TRACE-Net E2E Live Orchestrator Stage Timing + Fast Path v27")
    print(f" Status: {state.get('status')}")
    print(f" Quality status: {state.get('quality_status')}")
    for key in [
        "exact_search_document_count",
        "page_summary_count",
        "leiden_page_membership_count",
        "endpoint_route_count",
        "sample_query_count",
        "sample_success_count",
        "stage_timing_record_count",
        "fast_path_sample_count",
        "llm_called_sample_count",
        "sample_avg_latency_ms",
        "sample_avg_llm_ms",
        "fast_path_mode",
        "llm_mode",
        "llm_model",
        "base_url_windows",
        "base_url_open_webui_docker",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {state.get(key)}")
    print(f" report_path: {paths['report_path']}")
    print(f" sample_jsonl_path: {paths['sample_jsonl_path']}")
    print(f" inspect_md_path: {paths['inspect_md_path']}")
    return 0 if quality_status == "PASS" or not args.quality else 1


if __name__ == "__main__":
    raise SystemExit(main())
