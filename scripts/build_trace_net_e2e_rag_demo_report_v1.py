#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_rag_demo_report_v1 import build_e2e_rag_demo_report


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net E2E RAG demo report v1")
    p.add_argument("--e2e-query-planning-routing", required=True)
    p.add_argument("--e2e-hybrid-retrieval-runtime", required=True)
    p.add_argument("--e2e-context-pack-builder", required=True)
    p.add_argument("--e2e-evidence-sufficiency-gate", required=True)
    p.add_argument("--e2e-final-gate-smoke", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--min-stage-passes", type=int, default=5)
    p.add_argument("--min-demo-records", type=int, default=5)
    p.add_argument("--min-complete-demo-flows", type=int, default=5)
    p.add_argument("--min-route-plans", type=int, default=5)
    p.add_argument("--min-total-tunnels", type=int, default=15)
    p.add_argument("--min-retrieval-groups", type=int, default=5)
    p.add_argument("--min-successful-retrieval-queries", type=int, default=4)
    p.add_argument("--min-context-packs", type=int, default=5)
    p.add_argument("--min-final-gate-ready-packs", type=int, default=4)
    p.add_argument("--min-final-gate-records", type=int, default=5)
    p.add_argument("--min-safe-response-drafts", type=int, default=4)
    p.add_argument("--min-citation-backed-response-drafts", type=int, default=4)
    p.add_argument("--min-total-citations", type=int, default=10)
    p.add_argument("--min-pages-cited", type=int, default=2)
    p.add_argument("--min-field-count", type=int, default=3)
    p.add_argument("--max-schema-missing-required-key-records", type=int, default=0)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--quality", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    thresholds = vars(args).copy()
    report = build_e2e_rag_demo_report(
        query_planning_routing_path=args.e2e_query_planning_routing,
        e2e_hybrid_retrieval_runtime_path=args.e2e_hybrid_retrieval_runtime,
        e2e_context_pack_builder_path=args.e2e_context_pack_builder,
        e2e_evidence_sufficiency_gate_path=args.e2e_evidence_sufficiency_gate,
        e2e_final_gate_smoke_path=args.e2e_final_gate_smoke,
        output_dir=args.output_dir,
        thresholds=thresholds,
    )
    s = report["summary"]
    print("TRACE-Net E2E RAG Demo Report v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" e2e_rag_demo_status: {report['e2e_rag_demo_status']}")
    for key in [
        "stage_pass_count",
        "e2e_demo_record_count",
        "complete_demo_flow_count",
        "planned_query_route_plan_count",
        "total_query_tunnel_count",
        "retrieval_group_count",
        "successful_retrieval_query_count",
        "context_pack_count",
        "final_gate_record_count",
        "safe_response_draft_count",
        "citation_backed_response_draft_count",
        "total_citation_count",
        "page_with_citation_count",
        "unsafe_total_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {report['report_path']}")
    print(f" records_jsonl_path: {report['records_jsonl_path']}")
    print(f" inspect_md_path: {report['inspect_md_path']}")
    return 0 if report["quality_status"] == "PASS" or not args.quality else 1


if __name__ == "__main__":
    raise SystemExit(main())
