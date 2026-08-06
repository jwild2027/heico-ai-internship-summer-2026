from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_ask_api_final_return_policy_hybrid_v3_v22 import (
    FinalReturnHybridV3Config,
    answer_query,
    build_report,
    find_hybrid_result,
)


def sample_hybrid() -> dict:
    return {
        "quality_status": "PASS",
        "summary": {
            "quality_status": "PASS",
            "source_quality_statuses": {
                "hybrid_retrieval_v2": "PASS",
                "corrective_retrieval_planner": "PASS",
                "graph_query_evidence_enrichment": "PASS",
                "opensearch_loader_smoke": "PASS",
                "qdrant_page_profile_quality": "PASS",
            },
            "unsafe_group_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "corrective_action_as_proof_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "query_results": [
            {
                "query_id": "part_120_46137_001",
                "query": "120-46137-001",
                "ranked_groups": [
                    {
                        "query_id": "part_120_46137_001",
                        "page_id": "t_p_120_1176_p000003",
                        "hybrid_v3_rank": 1,
                        "hybrid_v3_score": 1.2,
                        "safe_routing_status": "ROUTING_READY",
                        "review_required_before_final_answer": False,
                        "corrective_issue_types": [],
                        "corrective_recommended_actions": [],
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                        "source_truth_mutation_allowed": False,
                    }
                ],
            },
            {
                "query_id": "manual_revision_history",
                "query": "Which pages discuss manual revision history?",
                "ranked_groups": [
                    {
                        "query_id": "manual_revision_history",
                        "page_id": "t_p_120_1176_p000001",
                        "hybrid_v3_rank": 1,
                        "hybrid_v3_score": 1.7,
                        "safe_routing_status": "REVIEW_ROUTE_REQUIRED",
                        "review_required_before_final_answer": True,
                        "corrective_issue_types": ["tiff_content_audit_review"],
                        "corrective_recommended_actions": ["route_to_tiff_content_review"],
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                        "source_truth_mutation_allowed": False,
                    }
                ],
            },
        ],
    }


def sample_final_gate() -> dict:
    return {
        "quality_status": "PASS",
        "records": [
            {
                "query": "120-46137-001",
                "final_answer_allowed": True,
                "final_answer_text": "Final-gate authorized answer for 120-46137-001.",
            }
        ],
    }


def test_finds_hybrid_result_by_query():
    result = find_hybrid_result("120-46137-001", sample_hybrid())
    assert result is not None
    assert result["query_id"] == "part_120_46137_001"


def test_returns_final_answer_only_when_gate_allows_and_no_review():
    response = answer_query("120-46137-001", sample_hybrid(), sample_final_gate())
    assert response["answer_status"] == "FINAL_ANSWER_RETURN_ALLOWED"
    assert response["final_answer_returned"] is True
    assert "Final-gate authorized" in response["message"]


def test_review_route_blocks_final_return_even_with_routing_groups():
    response = answer_query("Which pages discuss manual revision history?", sample_hybrid(), sample_final_gate())
    assert response["answer_status"] == "RETRIEVAL_ROUTE_REVIEW_REQUIRED"
    assert response["final_answer_returned"] is False
    assert response["review_required_group_count"] == 1
    assert response["ranked_groups"][0]["corrective_issue_types"] == ["tiff_content_audit_review"]


def test_build_report_passes_for_safe_hybrid_v3(tmp_path: Path):
    hybrid_path = tmp_path / "hybrid.json"
    final_path = tmp_path / "final.json"
    hybrid_path.write_text(json.dumps(sample_hybrid()), encoding="utf-8")
    final_path.write_text(json.dumps(sample_final_gate()), encoding="utf-8")
    config = FinalReturnHybridV3Config(
        hybrid_v3_report=hybrid_path,
        final_answer_report=final_path,
        output_dir=tmp_path / "out",
    )
    report = build_report(config, require_hybrid_v3_quality_pass=True)
    assert report["quality_status"] == "PASS"
    assert report["summary"]["hybrid_v3_quality_status"] == "PASS"
    assert report["summary"]["read_only_api"] is True
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0
