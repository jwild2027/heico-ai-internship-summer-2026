from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_community_aware_retrieval_v2 import check_community_aware_retrieval_v2_quality, evaluate_quality


def test_evaluate_quality_passes_with_expected_counters() -> None:
    summary = {
        "query_count": 5,
        "queries_with_navigation_hints_count": 5,
        "navigation_result_count": 20,
        "page_navigation_boost_count": 20,
        "review_only_hints_used_count": 0,
        "low_confidence_hints_used_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
    }
    status, failures = evaluate_quality(
        summary,
        {
            "min_queries": 5,
            "min_queries_with_navigation_hints": 5,
            "min_navigation_results": 1,
            "min_page_navigation_boosts": 1,
            "require_no_answer_permission": True,
        },
    )
    assert status == "PASS"
    assert failures == []


def test_evaluate_quality_blocks_category_as_proof() -> None:
    summary = {
        "query_count": 1,
        "queries_with_navigation_hints_count": 1,
        "navigation_result_count": 1,
        "page_navigation_boost_count": 1,
        "community_as_proof_count": 0,
        "category_as_proof_count": 1,
    }
    status, failures = evaluate_quality(summary, {"max_category_as_proof": 0})
    assert status == "FAIL"
    assert any("category_as_proof_count" in f for f in failures)


def test_check_quality_writes_json(tmp_path: Path) -> None:
    report_path = tmp_path / "trace_net_community_aware_retrieval_v2.json"
    payload = {
        "schema_version": "trace_net_community_aware_retrieval_v2",
        "status": "COMMUNITY_AWARE_RETRIEVAL_V2_BUILT",
        "quality_status": "PASS",
        "summary": {
            "query_count": 1,
            "queries_with_navigation_hints_count": 1,
            "navigation_result_count": 1,
            "page_navigation_boost_count": 1,
            "review_only_hints_used_count": 0,
            "low_confidence_hints_used_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
        },
    }
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    quality = check_community_aware_retrieval_v2_quality(
        report_path=report_path,
        thresholds={"min_queries": 1, "min_navigation_results": 1, "require_no_answer_permission": True},
        write_json_report=True,
    )

    assert quality["quality_status"] == "PASS"
    assert (tmp_path / "trace_net_community_aware_retrieval_v2_quality.json").exists()
