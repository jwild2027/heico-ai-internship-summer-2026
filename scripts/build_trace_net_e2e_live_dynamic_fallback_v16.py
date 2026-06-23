from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from tiff.trace_net_e2e_live_dynamic_fallback_v16 import (
    build_live_dynamic_fallback_manifest,
    read_json,
    write_report_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E live dynamic fallback v16 manifest")
    parser.add_argument("--live-query-pipeline", required=True)
    parser.add_argument("--table-exact-search-adapter", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8019)
    parser.add_argument("--min-existing-pipeline-queries", type=int, default=5)
    parser.add_argument("--min-exact-search-documents", type=int, default=10)
    parser.add_argument("--min-dynamic-fallback-probes", type=int, default=3)
    parser.add_argument("--min-ready-dynamic-fallback-probes", type=int, default=3)
    parser.add_argument("--min-total-citations", type=int, default=15)
    parser.add_argument("--min-endpoint-routes", type=int, default=4)
    parser.add_argument("--max-unsupported-claim-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()

    live = read_json(args.live_query_pipeline)
    exact = read_json(args.table_exact_search_adapter)
    report = build_live_dynamic_fallback_manifest(
        live,
        exact,
        host=args.host,
        port=args.port,
        min_existing_pipeline_queries=args.min_existing_pipeline_queries,
        min_exact_search_documents=args.min_exact_search_documents,
        min_dynamic_fallback_probes=args.min_dynamic_fallback_probes,
        min_ready_dynamic_fallback_probes=args.min_ready_dynamic_fallback_probes,
        min_total_citations=args.min_total_citations,
        min_endpoint_routes=args.min_endpoint_routes,
        max_unsupported_claim_count=args.max_unsupported_claim_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report["source_live_query_pipeline_path"] = str(Path(args.live_query_pipeline))
    report["source_table_exact_search_adapter_path"] = str(Path(args.table_exact_search_adapter))
    paths = write_report_files(report, args.output_dir)
    report.update(paths)
    write_report_files(report, args.output_dir)

    summary = report.get("summary", {})
    print("TRACE-Net E2E Live Dynamic Fallback v16")
    print(f" Status: {report.get('e2e_live_dynamic_fallback_status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "existing_pipeline_query_count",
        "exact_search_document_count",
        "dynamic_fallback_probe_count",
        "ready_dynamic_fallback_probe_count",
        "total_dynamic_fallback_citation_count",
        "unsupported_claim_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" base_url_windows: {report.get('base_url_windows')}")
    print(f" base_url_open_webui_docker: {report.get('base_url_open_webui_docker')}")
    print(f" report_path: {paths['report_path']}")
    print(f" probes_jsonl_path: {paths['probes_jsonl_path']}")
    print(f" inspect_md_path: {paths['inspect_md_path']}")
    return 0 if not args.quality or report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
