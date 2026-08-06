import json
from pathlib import Path

from tiff.trace_net_ask_api_hybrid_v3_routing_v1 import (
    AskApiHybridV3RoutingConfig,
    build_api_report,
    build_trace_net_hybrid_v3_routing_ask_response,
    convert_hybrid_v3_groups,
    write_build_outputs,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _hybrid_v3_payload() -> dict:
    return {
        "schema_version": "trace_net_hybrid_retrieval_v3",
        "quality_status": "PASS",
        "summary": {
            "quality_status": "PASS",
            "hybrid_v3_group_count": 2,
            "corrective_group_count": 1,
            "review_routed_group_count": 1,
            "unsafe_group_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "query_results": [
            {
                "query_id": "part_120_46137_001",
                "query": "120-46137-001",
                "ranked_group_count": 2,
                "ranked_groups": [
                    {
                        "hybrid_v3_rank": 1,
                        "page_id": "t_p_120_1176_p000003",
                        "hybrid_v3_score": 1.25,
                        "base_hybrid_v2_score": 1.1,
                        "channel_blend_score": 0.2,
                        "corrective_score_adjustment": -0.05,
                        "safe_routing_status": "REVIEW_ROUTE_REQUIRED",
                        "review_required_before_final_answer": True,
                        "corrective_issue_types": ["semantic_page_target_miss"],
                        "corrective_recommended_actions": [
                            "rerank_with_graph_page_anchor",
                            "run_opensearch_exact_if_identifier_present",
                        ],
                        "part_numbers": ["120-46137-001"],
                        "citation_ids": ["cite:t_p_120_1176_p000003"],
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                        "source_truth_mutation_allowed": False,
                    },
                    {
                        "hybrid_v3_rank": 2,
                        "page_id": "t_p_120_1176_p000340",
                        "hybrid_v3_score": 0.9,
                        "safe_routing_status": "ROUTING_READY",
                        "corrective_issue_types": [],
                        "corrective_recommended_actions": [],
                    },
                ],
            }
        ],
    }


def test_hybrid_v3_routing_response_is_retrieval_only_until_final_gate(tmp_path: Path) -> None:
    hybrid_path = _write(tmp_path / "hybrid_v3.json", _hybrid_v3_payload())
    config = AskApiHybridV3RoutingConfig(hybrid_v3_report=hybrid_path, max_groups=8)

    response = build_trace_net_hybrid_v3_routing_ask_response("120-46137-001", config)

    assert response["quality_status"] == "PASS"
    assert response["summary"]["answer_status"] == "HYBRID_V3_ROUTING_ONLY_FINAL_GATE_REQUIRED"
    assert response["summary"]["hybrid_v3_quality_status"] == "PASS"
    assert response["summary"]["retrieval_group_count"] == 2
    assert response["summary"]["corrective_group_count"] == 1
    assert response["summary"]["review_required_group_count"] == 1
    assert response["summary"]["can_answer_directly"] is False
    assert response["summary"]["can_prove_claims"] is False
    assert response["summary"]["source_truth_mutation_allowed"] is False

    first = response["retrieval_groups"][0]
    assert first["safe_routing_status"] == "REVIEW_ROUTE_REQUIRED"
    assert first["review_required_before_final_answer"] is True
    assert first["corrective_issue_types"] == ["semantic_page_target_miss"]
    assert "run_opensearch_exact_if_identifier_present" in first["corrective_recommended_actions"]
    assert first["can_answer_directly"] is False
    assert first["can_prove_claims"] is False
    assert first["source_truth_mutation_allowed"] is False
    assert first["corrective_action_as_proof"] is False


def test_exact_final_gate_artifact_can_supply_answer_without_hybrid_v3_becoming_proof(tmp_path: Path) -> None:
    hybrid_path = _write(tmp_path / "hybrid_v3.json", _hybrid_v3_payload())
    final_path = _write(
        tmp_path / "final_answer.json",
        {
            "quality_status": "PASS",
            "query": "120-46137-001",
            "final_answer_allowed": True,
            "final_answer_text": "Final gate authorized answer text.",
        },
    )
    config = AskApiHybridV3RoutingConfig(hybrid_v3_report=hybrid_path, final_answer_report=final_path)

    response = build_trace_net_hybrid_v3_routing_ask_response("120-46137-001", config)

    assert response["answer_text"] == "Final gate authorized answer text."
    assert response["summary"]["answer_status"] == "FINAL_GATE_ARTIFACT_ANSWER"
    assert response["summary"]["final_answer_used"] is True
    assert response["safety"]["source_truth_mutation_allowed"] is False
    assert all(group["can_answer_directly"] is False for group in response["retrieval_groups"])


def test_build_api_report_and_outputs_require_hybrid_v3_pass(tmp_path: Path) -> None:
    hybrid_path = _write(tmp_path / "hybrid_v3.json", _hybrid_v3_payload())
    config = AskApiHybridV3RoutingConfig(hybrid_v3_report=hybrid_path, output_dir=tmp_path / "out")

    report = build_api_report(config)
    assert report["summary"]["hybrid_v3_quality_status"] == "PASS"
    assert report["summary"]["hybrid_v3_routing_available"] is True
    assert report["summary"]["corrective_group_count"] == 1

    report, quality = write_build_outputs(config, require_hybrid_v3_quality_pass=True)
    assert quality["quality_status"] == "PASS"
    assert (tmp_path / "out" / "trace_net_ask_api_hybrid_v3_routing_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_ask_api_hybrid_v3_routing_v1_quality.json").exists()


def test_convert_hybrid_v3_groups_forces_safe_defaults() -> None:
    groups = convert_hybrid_v3_groups(
        {
            "ranked_groups": [
                {
                    "hybrid_v3_rank": 1,
                    "page_id": "t_p_120_1176_p000001",
                    "hybrid_v3_score": 2.0,
                    "can_answer_directly": True,
                    "can_prove_claims": True,
                    "source_truth_mutation_allowed": True,
                }
            ]
        },
        max_groups=3,
    )
    assert len(groups) == 1
    assert groups[0]["can_answer_directly"] is False
    assert groups[0]["can_prove_claims"] is False
    assert groups[0]["source_truth_mutation_allowed"] is False
    assert groups[0]["corrective_action_as_proof"] is False
