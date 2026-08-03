"""Quality checker for TRACE-Net Hybrid Retrieval v3."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_hybrid_retrieval_v3 import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_FILE,
    SCHEMA_VERSION,
    as_bool,
    as_int,
    as_list,
    as_text,
    query_results,
    groups_from_query_result,
    read_json,
    write_json,
)


def evaluate_quality(
    payload: Mapping[str, Any],
    *,
    min_queries: int = 1,
    min_queries_with_results: int = 1,
    min_groups: int = 1,
    min_corrective_groups: int = 1,
    min_review_routed_groups: int = 0,
    max_unsafe_groups: int = 0,
    require_hybrid_v2_quality_pass: bool = False,
    require_corrective_planner_quality_pass: bool = False,
    require_graph_enrichment_quality_pass: bool = False,
    require_opensearch_loader_quality_pass: bool = False,
    require_opensearch_live_loader_quality_pass: bool = False,
    require_qdrant_quality_pass: bool = False,
    min_live_exact_hit_groups: int = 0,
    require_no_answer_permission: bool = True,
) -> dict[str, Any]:
    rows = query_results(payload)
    groups = [group for row in rows for group in groups_from_query_result(row)]
    source_status = payload.get("source_quality_statuses")
    if not isinstance(source_status, Mapping):
        summary = payload.get("summary")
        source_status = summary.get("source_quality_statuses") if isinstance(summary, Mapping) else {}
    source_status = dict(source_status) if isinstance(source_status, Mapping) else {}
    required_sources = []
    if require_hybrid_v2_quality_pass:
        required_sources.append("hybrid_retrieval_v2")
    if require_corrective_planner_quality_pass:
        required_sources.append("corrective_retrieval_planner")
    if require_graph_enrichment_quality_pass:
        required_sources.append("graph_query_evidence_enrichment")
    if require_opensearch_loader_quality_pass:
        required_sources.append("opensearch_loader_smoke")
    if require_opensearch_live_loader_quality_pass:
        required_sources.append("opensearch_live_loader")
    if require_qdrant_quality_pass:
        required_sources.append("qdrant_page_profile_quality")
    query_count = len(rows)
    queries_with_results = sum(1 for row in rows if groups_from_query_result(row))
    group_count = len(groups)
    corrective_group_count = sum(1 for group in groups if as_int(group.get("corrective_record_count")) > 0)
    review_group_count = sum(1 for group in groups if as_bool(group.get("review_required_before_final_answer")))
    live_exact_hit_group_count = sum(1 for group in groups if as_int(group.get("live_opensearch_exact_hit_count")) > 0)
    live_exact_hit_count = sum(as_int(group.get("live_opensearch_exact_hit_count")) for group in groups)
    unsafe_group_count = sum(as_int(group.get("source_group_unsafe_flag_count")) for group in groups)
    hard_zero_counts = {
        "answer_permission_count": sum(1 for group in groups if as_bool(group.get("answer_permission")) or as_bool(group.get("answer_allowed")) or as_bool(group.get("final_answer_allowed"))),
        "can_answer_directly_count": sum(1 for group in groups if as_bool(group.get("can_answer_directly"))),
        "can_prove_claims_count": sum(1 for group in groups if as_bool(group.get("can_prove_claims"))),
        "retrieval_only_answer_allowed_count": sum(1 for group in groups if as_bool(group.get("retrieval_only_answer_allowed"))),
        "source_truth_mutation_allowed_count": sum(1 for group in groups if as_bool(group.get("source_truth_mutation_allowed")) or as_bool(group.get("can_mutate_source_truth"))),
        "community_as_proof_count": sum(1 for group in groups if as_bool(group.get("community_as_proof"))),
        "category_as_proof_count": sum(1 for group in groups if as_bool(group.get("category_as_proof"))),
        "feedback_as_proof_count": sum(1 for group in groups if as_bool(group.get("feedback_as_proof"))),
        "corrective_action_as_proof_count": sum(1 for group in groups if as_bool(group.get("corrective_action_as_proof"))),
        "postgres_write_attempt_count": sum(1 for group in groups if as_bool(group.get("postgres_write_attempted"))),
        "qdrant_write_attempt_count": sum(1 for group in groups if as_bool(group.get("qdrant_write_attempted"))),
        "opensearch_write_attempt_count": sum(1 for group in groups if as_bool(group.get("opensearch_write_attempted"))),
    }
    fail_reasons: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        fail_reasons.append("schema_version_mismatch")
    if query_count < min_queries:
        fail_reasons.append(f"query_count_below_min:{query_count}<{min_queries}")
    if queries_with_results < min_queries_with_results:
        fail_reasons.append(f"queries_with_results_below_min:{queries_with_results}<{min_queries_with_results}")
    if group_count < min_groups:
        fail_reasons.append(f"group_count_below_min:{group_count}<{min_groups}")
    if corrective_group_count < min_corrective_groups:
        fail_reasons.append(f"corrective_group_count_below_min:{corrective_group_count}<{min_corrective_groups}")
    if review_group_count < min_review_routed_groups:
        fail_reasons.append(f"review_routed_group_count_below_min:{review_group_count}<{min_review_routed_groups}")
    if live_exact_hit_group_count < min_live_exact_hit_groups:
        fail_reasons.append(f"live_exact_hit_group_count_below_min:{live_exact_hit_group_count}<{min_live_exact_hit_groups}")
    if unsafe_group_count > max_unsafe_groups:
        fail_reasons.append(f"unsafe_group_count_above_max:{unsafe_group_count}>{max_unsafe_groups}")
    missing_source_quality = [name for name in required_sources if as_text(source_status.get(name)).upper() != "PASS"]
    if missing_source_quality:
        fail_reasons.append("source_quality_not_pass:" + ",".join(missing_source_quality))
    if require_no_answer_permission and any(hard_zero_counts.values()):
        fail_reasons.append("hard_zero_safety_counter_nonzero")
    quality = "PASS" if not fail_reasons else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "quality_status": quality,
        "summary": {
            "schema_version": SCHEMA_VERSION,
            "quality_status": quality,
            "query_count": query_count,
            "queries_with_results_count": queries_with_results,
            "hybrid_v3_group_count": group_count,
            "corrective_group_count": corrective_group_count,
            "review_routed_group_count": review_group_count,
            "live_opensearch_exact_hit_group_count": live_exact_hit_group_count,
            "live_opensearch_exact_hit_count": live_exact_hit_count,
            "unsafe_group_count": unsafe_group_count,
            "source_quality_statuses": source_status,
            "required_source_quality": required_sources,
            "quality_fail_reasons": fail_reasons,
            **hard_zero_counts,
        },
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Hybrid Retrieval v3 quality.")
    parser.add_argument("--report-path", default=str(DEFAULT_OUTPUT_DIR / DEFAULT_OUTPUT_FILE))
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-queries-with-results", type=int, default=1)
    parser.add_argument("--min-groups", type=int, default=1)
    parser.add_argument("--min-corrective-groups", type=int, default=1)
    parser.add_argument("--min-review-routed-groups", type=int, default=0)
    parser.add_argument("--max-unsafe-groups", type=int, default=0)
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-corrective-planner-quality-pass", action="store_true")
    parser.add_argument("--require-graph-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-opensearch-loader-quality-pass", action="store_true")
    parser.add_argument("--require-opensearch-live-loader-quality-pass", action="store_true")
    parser.add_argument("--require-qdrant-quality-pass", action="store_true")
    parser.add_argument("--min-live-exact-hit-groups", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = read_json(args.report_path)
    result = evaluate_quality(
        payload,
        min_queries=args.min_queries,
        min_queries_with_results=args.min_queries_with_results,
        min_groups=args.min_groups,
        min_corrective_groups=args.min_corrective_groups,
        min_review_routed_groups=args.min_review_routed_groups,
        max_unsafe_groups=args.max_unsafe_groups,
        require_hybrid_v2_quality_pass=args.require_hybrid_v2_quality_pass,
        require_corrective_planner_quality_pass=args.require_corrective_planner_quality_pass,
        require_graph_enrichment_quality_pass=args.require_graph_enrichment_quality_pass,
        require_opensearch_loader_quality_pass=args.require_opensearch_loader_quality_pass,
        require_opensearch_live_loader_quality_pass=args.require_opensearch_live_loader_quality_pass,
        require_qdrant_quality_pass=args.require_qdrant_quality_pass,
        min_live_exact_hit_groups=args.min_live_exact_hit_groups,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.write_json:
        report_path = Path(args.report_path)
        write_json(report_path.with_name("trace_net_hybrid_retrieval_v3_quality.json"), result)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
