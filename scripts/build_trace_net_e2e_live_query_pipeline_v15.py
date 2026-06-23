from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


import argparse

from tiff.trace_net_e2e_live_query_pipeline_v15 import (
    build_live_query_pipeline_manifest,
    read_json,
    write_report_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E live query pipeline v15 manifest")
    parser.add_argument("--webui-final-answer-endpoint", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8018)
    parser.add_argument("--min-final-answers", type=int, default=5)
    parser.add_argument("--min-ready-pipeline-queries", type=int, default=5)
    parser.add_argument("--min-pipeline-stages-per-query", type=int, default=8)
    parser.add_argument("--min-total-pipeline-stages", type=int, default=40)
    parser.add_argument("--min-total-citations", type=int, default=15)
    parser.add_argument("--min-endpoint-routes", type=int, default=4)
    parser.add_argument("--max-unknown-query-final-answer-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()

    source = read_json(args.webui_final_answer_endpoint)
    report = build_live_query_pipeline_manifest(
        source,
        host=args.host,
        port=args.port,
        min_final_answers=args.min_final_answers,
        min_ready_pipeline_queries=args.min_ready_pipeline_queries,
        min_pipeline_stages_per_query=args.min_pipeline_stages_per_query,
        min_total_pipeline_stages=args.min_total_pipeline_stages,
        min_total_citations=args.min_total_citations,
        min_endpoint_routes=args.min_endpoint_routes,
        max_unknown_query_final_answer_count=args.max_unknown_query_final_answer_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report["source_webui_final_answer_endpoint_path"] = str(Path(args.webui_final_answer_endpoint))
    paths = write_report_files(report, args.output_dir)
    report.update(paths)
    # Rewrite with generated output paths included.
    write_report_files(report, args.output_dir)

    summary = report.get("summary", {})
    print("TRACE-Net E2E Live Query Pipeline v15")
    print(f" Status: {report.get('e2e_live_query_pipeline_status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "final_answer_count",
        "ready_pipeline_query_count",
        "total_pipeline_stage_count",
        "total_citation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" base_url_windows: {report.get('base_url_windows')}")
    print(f" base_url_open_webui_docker: {report.get('base_url_open_webui_docker')}")
    print(f" report_path: {paths['report_path']}")
    print(f" pipelines_jsonl_path: {paths['pipelines_jsonl_path']}")
    print(f" inspect_md_path: {paths['inspect_md_path']}")
    return 0 if not args.quality or report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
