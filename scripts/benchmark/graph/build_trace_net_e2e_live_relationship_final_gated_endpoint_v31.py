from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import build_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TRACE-Net live relationship final-gated endpoint v31 artifact.")
    parser.add_argument("--relationship-router-hardening", required=True, type=Path)
    parser.add_argument("--relationship-final-gate-hardener", required=True, type=Path)
    parser.add_argument("--table-exact-search-adapter", required=True, type=Path)
    parser.add_argument("--page-context-v2", type=Path)
    parser.add_argument("--leiden-communities", type=Path)
    parser.add_argument("--graph-signal-artifact", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8026)
    parser.add_argument("--llm-mode", default="ollama")
    parser.add_argument("--llm-model", default="gemma4:26b")
    parser.add_argument("--include-standard-demo-queries", action="store_true")
    parser.add_argument("--min-sample-queries", type=int, default=0)
    parser.add_argument("--min-sample-successes", type=int, default=0)
    parser.add_argument("--min-relationship-final-gate-applied", type=int, default=0)
    parser.add_argument("--min-relationship-records", type=int, default=0)
    parser.add_argument("--max-post-gate-issue-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()

    report = build_report(
        relationship_router_hardening=args.relationship_router_hardening,
        relationship_final_gate_hardener=args.relationship_final_gate_hardener,
        table_exact_search_adapter=args.table_exact_search_adapter,
        page_context_v2=args.page_context_v2,
        leiden_communities=args.leiden_communities,
        graph_signal_paths=args.graph_signal_artifact or None,
        output_dir=args.output_dir,
        include_standard_demo_queries=args.include_standard_demo_queries,
        min_sample_queries=args.min_sample_queries,
        min_sample_successes=args.min_sample_successes,
        min_relationship_final_gate_applied=args.min_relationship_final_gate_applied,
        min_relationship_records=args.min_relationship_records,
        max_post_gate_issue_count=args.max_post_gate_issue_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
        quality=args.quality,
    )

    print("TRACE-Net E2E Live Relationship Final-Gated Endpoint v31")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "sample_query_count",
        "sample_success_count",
        "relationship_final_gate_applied_count",
        "relationship_record_count",
        "repaired_relationship_sample_count",
        "post_gate_issue_count",
        "exact_search_document_count",
        "page_context_v2_page_count",
        "graph_has_nomenclature_page_count",
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
