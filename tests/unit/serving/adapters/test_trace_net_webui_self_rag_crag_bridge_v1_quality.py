import json
from pathlib import Path

from tiff.trace_net_webui_self_rag_crag_bridge_v1 import check_webui_self_rag_crag_bridge_quality


def test_quality_check_passes_for_required_brain_gates(tmp_path):
    report = tmp_path / "trace_net_webui_self_rag_crag_bridge_v1.json"
    payload = {
        "quality_status": "PASS",
        "summary": {
            "tool_checklist_count": 10,
            "used_tool_count": 4,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "tool_statuses": {
            "query_planner": "used",
            "context_pack_builder": "used",
            "self_rag": "used",
            "crag_retry": "skipped_not_needed",
        },
    }
    report.write_text(json.dumps(payload), encoding="utf-8")

    result = check_webui_self_rag_crag_bridge_quality(
        report_path=report,
        require_query_planner_used=True,
        require_context_pack_builder_used=True,
        require_self_rag_used=True,
        require_crag_evaluated=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )

    assert result["quality_status"] == "PASS"
    assert result["failures"] == []


def test_quality_check_fails_when_self_rag_not_used(tmp_path):
    report = tmp_path / "trace_net_webui_self_rag_crag_bridge_v1.json"
    payload = {
        "quality_status": "PASS",
        "summary": {
            "tool_checklist_count": 10,
            "used_tool_count": 3,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "tool_statuses": {
            "query_planner": "used",
            "context_pack_builder": "used",
            "self_rag": "available_not_used",
            "crag_retry": "available_not_used",
        },
    }
    report.write_text(json.dumps(payload), encoding="utf-8")

    result = check_webui_self_rag_crag_bridge_quality(
        report_path=report,
        require_self_rag_used=True,
        require_crag_evaluated=True,
    )

    assert result["quality_status"] == "FAIL"
    assert any("Self-RAG" in failure for failure in result["failures"])


def test_quality_check_supports_explicit_tool_status_requirements(tmp_path):
    report = tmp_path / "trace_net_webui_self_rag_crag_bridge_v1.json"
    payload = {
        "quality_status": "PASS",
        "summary": {"tool_checklist_count": 10, "used_tool_count": 4},
        "tool_statuses": {"crag_retry": "used", "self_rag": "used"},
    }
    report.write_text(json.dumps(payload), encoding="utf-8")

    result = check_webui_self_rag_crag_bridge_quality(
        report_path=report,
        require_tool_statuses=["crag_retry=used", "self_rag=used"],
    )

    assert result["quality_status"] == "PASS"
