import json
from pathlib import Path

from tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 import (
    BridgeConfig,
    _bridge_cli_command,
    _bridge_status_payload,
    check_manifest_bridge_v1,
)


def _visual_bridge_payload():
    return {
        "status": "TRACE_NET_WEBUI_SELF_RAG_CRAG_BRIDGE_BUILT",
        "quality_status": "PASS",
        "summary": {
            "used_tools": [
                "query_planner",
                "context_pack_builder",
                "self_rag",
                "visual_image_route",
                "webui_visual_context_bridge",
            ],
            "crag_retry_plan_count": 0,
            "self_rag_ready_for_gemma_draft_count": 1,
            "self_rag_crag_retry_required_count": 0,
            "context_pack_count": 1,
            "total_evidence_capsule_count": 30,
            "total_high_signal_evidence_capsule_count": 30,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "webui_visual_context_bridge_used": True,
            "visual_image_route_used": True,
            "webui_visual_context_bridge_quality_status": "PASS",
            "visual_context_card_count": 2,
            "review_only_visual_context_excluded_count": 10,
            "visual_context_included_pages": ["t_p_120_1176_p000001", "t_p_120_1176_p000022"],
            "visual_context_included_canonical_page_numbers": [1, 22],
        },
        "tool_statuses": {
            "query_planner": "used",
            "context_pack_builder": "used",
            "self_rag": "used",
            "crag_retry": "skipped_not_needed",
            "visual_image_route": "used",
            "webui_visual_context_bridge": "used",
        },
        "webui_visual_context_cards": [
            {
                "page_id": "t_p_120_1176_p000001",
                "canonical_page_number": 1,
                "context_authority": "vision_derived_retrieval_guidance_not_source_truth",
                "answer_permission": False,
            },
            {
                "page_id": "t_p_120_1176_p000022",
                "canonical_page_number": 22,
                "context_authority": "vision_derived_retrieval_guidance_not_source_truth",
                "answer_permission": False,
            },
        ],
        "checklist_text": "visual/image/route: used\nwebui visual context bridge: used",
    }


def test_bridge_cli_command_passes_webui_visual_context_bridge_path(tmp_path: Path) -> None:
    visual_bridge = tmp_path / "webui_visual_context_bridge.json"
    config = BridgeConfig(
        kernel_path=tmp_path / "kernel.json",
        output_dir=tmp_path / "bridge_out",
        webui_visual_context_bridge=visual_bridge,
    )

    command = _bridge_cli_command("question", config, tmp_path / "target")

    assert "--webui-visual-context-bridge" in command
    assert command[command.index("--webui-visual-context-bridge") + 1] == str(visual_bridge)


def test_bridge_status_payload_exposes_visual_context_trace() -> None:
    payload = _bridge_status_payload("question", _visual_bridge_payload())

    assert payload["webui_visual_context_bridge_used"] is True
    assert payload["visual_image_route_used"] is True
    assert payload["webui_visual_context_bridge_quality_status"] == "PASS"
    assert payload["visual_context_card_count"] == 2
    assert payload["review_only_visual_context_excluded_count"] == 10
    assert payload["visual_context_included_pages"] == ["t_p_120_1176_p000001", "t_p_120_1176_p000022"]
    assert payload["visual_image_route"] == {"status": "used", "used": True}
    assert payload["webui_visual_context_bridge"] == {"status": "used", "used": True}
    assert len(payload["webui_visual_context_cards"]) == 2
    assert payload["webui_visual_context_cards"][0]["answer_permission"] is False


def test_manifest_quality_requires_visual_context_bridge_when_requested(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    summary = {
        "page_record_count": 509,
        "gated_draft_count": 1,
        "server_llm_model": "gemma4:26b",
        "self_rag_crag_bridge_enabled": True,
        "sample_bridge_used": True,
        "self_rag_used": True,
        "crag_retry_status": "skipped_not_needed",
        "webui_visual_context_bridge_used": True,
        "visual_image_route_used": True,
        "webui_visual_context_bridge_quality_status": "PASS",
        "visual_context_card_count": 2,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    report.write_text(json.dumps({"quality_status": "PASS", "summary": summary}), encoding="utf-8")

    result = check_manifest_bridge_v1(
        report_path=report,
        require_webui_visual_context_bridge_used=True,
        min_visual_context_cards=2,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )

    assert result["quality_status"] == "PASS"
    assert result["failures"] == []


def test_manifest_quality_fails_when_visual_context_missing(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    summary = {
        "page_record_count": 509,
        "gated_draft_count": 1,
        "self_rag_crag_bridge_enabled": True,
        "sample_bridge_used": True,
        "self_rag_used": True,
        "crag_retry_status": "skipped_not_needed",
        "webui_visual_context_bridge_used": False,
        "visual_image_route_used": False,
        "webui_visual_context_bridge_quality_status": None,
        "visual_context_card_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    report.write_text(json.dumps({"quality_status": "PASS", "summary": summary}), encoding="utf-8")

    result = check_manifest_bridge_v1(
        report_path=report,
        require_webui_visual_context_bridge_used=True,
        min_visual_context_cards=1,
    )

    assert result["quality_status"] == "FAIL"
    assert any("visual context bridge" in failure for failure in result["failures"])
    assert any("visual context cards" in failure for failure in result["failures"])
