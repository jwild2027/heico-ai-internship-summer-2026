from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_ask_api_dynamic_retrieval_v2 import (
    AskApiDynamicConfig,
    build_api_report,
    build_trace_net_dynamic_ask_response,
    openai_chat_completion_response,
    write_json,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fixture_config(tmp_path: Path) -> AskApiDynamicConfig:
    final_report = _write(
        tmp_path / "final.json",
        {
            "schema_version": "trace_net_final_answer_gate_v1",
            "quality_status": "PASS",
            "final_answer_allowed": True,
            "query": "Which pages discuss manual revision history?",
            "final_answer_text": "Final gated answer with citation [cite:source_text:p1:x].",
        },
    )
    final_md = tmp_path / "final.md"
    final_md.write_text("# Final\n\n## Final gated answer\nFallback answer", encoding="utf-8")
    hybrid_v2 = _write(
        tmp_path / "hybrid_v2.json",
        {
            "schema_version": "trace_net_hybrid_retrieval_v2",
            "quality_status": "PASS",
            "query_results": [
                {
                    "query_id": "part",
                    "query": "120-46137-001",
                    "ranked_group_count": 1,
                    "ranked_groups": [
                        {
                            "hybrid_v2_rank": 1,
                            "page_id": "t_p_120_1176_p000003",
                            "hybrid_v2_score": 0.92,
                            "exact_hit_count": 3,
                            "semantic_group_count": 1,
                            "category_boost": 0.05,
                            "feedback_advisory_delta": 0.0,
                            "category_labels": ["table_parts_diagram_page_review"],
                            "community_ids": ["tracenet_community_00001"],
                            "citation_ids": ["cite:table_structured:t_p_120_1176_p000003:x"],
                            "part_numbers": ["120-46137-001"],
                            "rag_buckets": ["table_cell_normalized"],
                            "safety_status": "retrieval_safe",
                            "can_answer_directly": False,
                            "can_prove_claims": False,
                            "source_truth_mutation_allowed": False,
                        }
                    ],
                }
            ],
        },
    )
    hybrid = _write(tmp_path / "hybrid.json", {"quality_status": "PASS", "query_results": []})
    opensearch = _write(tmp_path / "opensearch.json", {"quality_status": "PASS", "documents": []})
    category = _write(tmp_path / "category.json", {"quality_status": "PASS"})
    feedback = _write(tmp_path / "feedback.json", {"quality_status": "PASS"})
    return AskApiDynamicConfig(
        final_answer_report=final_report,
        final_answer_markdown=final_md,
        hybrid_v2_report=hybrid_v2,
        hybrid_report=hybrid,
        opensearch_adapter=opensearch,
        category_aware_leiden_overlay=category,
        feedback_memory=feedback,
        output_dir=tmp_path / "out",
    )


def test_final_gate_artifact_answer_for_matching_query(tmp_path: Path) -> None:
    cfg = _fixture_config(tmp_path)
    response = build_trace_net_dynamic_ask_response("Which pages discuss manual revision history?", cfg)
    assert response["quality_status"] == "PASS"
    assert response["summary"]["answer_status"] == "FINAL_GATE_ARTIFACT_ANSWER"
    assert response["summary"]["final_answer_allowed"] is True
    assert "Final gated answer" in response["answer_text"]


def test_dynamic_retrieval_for_new_query_is_retrieval_only(tmp_path: Path) -> None:
    cfg = _fixture_config(tmp_path)
    response = build_trace_net_dynamic_ask_response("120-46137-001", cfg)
    assert response["quality_status"] == "PASS"
    assert response["summary"]["answer_status"] == "DYNAMIC_RETRIEVAL_ONLY_FINAL_GATE_REQUIRED"
    assert response["summary"]["final_answer_allowed"] is False
    assert response["summary"]["dynamic_retrieval_used"] is True
    assert response["summary"]["retrieval_group_count"] == 1
    group = response["retrieval_groups"][0]
    assert group["page_id"] == "t_p_120_1176_p000003"
    assert group["exact_hit_count"] == 3
    assert group["can_answer_directly"] is False
    assert group["can_prove_claims"] is False


def test_openai_chat_completion_includes_dynamic_groups(tmp_path: Path) -> None:
    cfg = _fixture_config(tmp_path)
    ask = build_trace_net_dynamic_ask_response("120-46137-001", cfg)
    completion = openai_chat_completion_response("120-46137-001", ask, cfg.model_name)
    content = completion["choices"][0]["message"]["content"]
    assert "TRACE-Net dynamic hybrid retrieval groups" in content
    assert "t_p_120_1176_p000003" in content
    assert completion["trace_net"]["feedback_as_proof_count"] == 0


def test_build_api_report_is_read_only(tmp_path: Path) -> None:
    cfg = _fixture_config(tmp_path)
    report = build_api_report(cfg)
    assert report["quality_status"] == "PASS"
    assert report["summary"]["dynamic_retrieval_available"] is True
    assert report["summary"]["read_only_api"] is True
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0
