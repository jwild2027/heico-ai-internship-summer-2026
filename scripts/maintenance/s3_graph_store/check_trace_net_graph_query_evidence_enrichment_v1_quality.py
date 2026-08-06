#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_graph_query_evidence_enrichment_v1 import (
    check_graph_query_evidence_enrichment_quality,
    print_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Graph Query Evidence Enrichment v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-enriched-query-records", type=int, default=1)
    parser.add_argument("--min-enriched-page-records", type=int, default=1)
    parser.add_argument("--min-evidence-enriched-pages", type=int, default=1)
    parser.add_argument("--min-source-resolved-pages", type=int, default=1)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-category-as-proof", type=int, default=0)
    parser.add_argument("--max-retrieval-only-answer-allowed", type=int, default=0)
    parser.add_argument("--max-can-answer-directly", type=int, default=0)
    parser.add_argument("--max-can-prove-claims", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-graph-query-helper-quality-pass", action="store_true")
    parser.add_argument("--require-opensearch-quality-pass", action="store_true")
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-leiden-bridge-quality-pass", action="store_true")
    parser.add_argument("--require-dublin-core-quality-pass", action="store_true")
    parser.add_argument("--require-claim-entailment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()
    if args.require_no_answer_permission:
        args.max_can_answer_directly = 0
        args.max_can_prove_claims = 0
        args.max_retrieval_only_answer_allowed = 0
    thresholds = {
        "min_enriched_query_records": args.min_enriched_query_records,
        "min_enriched_page_records": args.min_enriched_page_records,
        "min_evidence_enriched_pages": args.min_evidence_enriched_pages,
        "min_source_resolved_pages": args.min_source_resolved_pages,
        "max_community_as_proof_count": args.max_community_as_proof,
        "max_category_as_proof_count": args.max_category_as_proof,
        "max_retrieval_only_answer_allowed_count": args.max_retrieval_only_answer_allowed,
        "max_can_answer_directly_count": args.max_can_answer_directly,
        "max_can_prove_claims_count": args.max_can_prove_claims,
        "max_source_truth_mutation_allowed_count": args.max_source_truth_mutation_allowed,
        "max_postgres_write_attempt_count": 0,
        "max_qdrant_write_attempt_count": 0,
        "max_opensearch_write_attempt_count": 0,
        "require_graph_query_helper_quality_pass": args.require_graph_query_helper_quality_pass,
        "require_opensearch_quality_pass": args.require_opensearch_quality_pass,
        "require_hybrid_v2_quality_pass": args.require_hybrid_v2_quality_pass,
        "require_leiden_bridge_quality_pass": args.require_leiden_bridge_quality_pass,
        "require_dublin_core_quality_pass": args.require_dublin_core_quality_pass,
        "require_claim_entailment_quality_pass": args.require_claim_entailment_quality_pass,
    }
    report = check_graph_query_evidence_enrichment_quality(
        report_path=args.report_path,
        thresholds=thresholds,
        write_json_report=args.write_json,
    )
    print_summary(report, quality=True)
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
