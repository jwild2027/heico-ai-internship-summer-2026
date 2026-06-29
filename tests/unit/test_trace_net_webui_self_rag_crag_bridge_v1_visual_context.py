import json
from pathlib import Path

from tiff import trace_net_webui_self_rag_crag_bridge_v1 as bridge


def _write(path: Path, payload: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def test_bridge_marks_visual_route_used_from_webui_visual_context_bridge(tmp_path, monkeypatch):
    kernel = tmp_path / "kernel.json"
    kernel.write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
    route_dispatch = tmp_path / "route_dispatch.json"
    route_dispatch.write_text(json.dumps({"records": [{"page_id": "source_p000001"}]}), encoding="utf-8")
    visual_bridge = tmp_path / "visual_bridge.json"
    _write(
        visual_bridge,
        {
            "quality_status": "PASS",
            "summary": {
                "visual_context_card_count": 2,
                "review_only_visual_context_excluded_count": 10,
                "included_pages": ["t_p_120_1176_p000001", "t_p_120_1176_p000022"],
                "included_canonical_page_numbers": [1, 22],
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
            },
            "records": [
                {"page_id": "t_p_120_1176_p000001", "answer_permission": False, "source_truth_mutation_allowed": False},
                {"page_id": "t_p_120_1176_p000022", "answer_permission": False, "source_truth_mutation_allowed": False},
            ],
        },
    )

    def fake_query_planner(*, kernel_path, output_dir, questions):
        return _write(
            output_dir / bridge.STAGE_REPORT_NAMES["query_planner"],
            {"quality_status": "PASS", "summary": {"query_plan_count": 1}, "records": [{"answer_permission": False}]},
        )

    def fake_blueprint(*, query_planner_path, output_dir):
        return _write(
            output_dir / bridge.STAGE_REPORT_NAMES["context_pack_blueprint"],
            {"quality_status": "PASS", "summary": {"context_pack_blueprint_count": 1}, "records": [{"answer_permission": False}]},
        )

    def fake_pack_builder(**kwargs):
        return _write(
            kwargs["output_dir"] / bridge.STAGE_REPORT_NAMES["context_pack_builder"],
            {
                "quality_status": "PASS",
                "summary": {
                    "context_pack_count": 1,
                    "artifact_record_counts": {"fishnet_route_dispatch_handoff": 1},
                    "total_evidence_capsule_count": 1,
                    "total_high_signal_evidence_capsule_count": 1,
                },
                "records": [{"answer_permission": False}],
            },
        )

    def fake_self_rag(*, context_pack_path, output_dir, min_high_signal_capsules, min_evidence_strength_score):
        return _write(
            output_dir / bridge.STAGE_REPORT_NAMES["self_rag"],
            {"quality_status": "PASS", "summary": {"self_rag_record_count": 1, "crag_retry_required_count": 0}, "records": [{"answer_permission": False}]},
        )

    def fake_crag(*, self_rag_report_path, output_dir):
        return _write(
            output_dir / bridge.STAGE_REPORT_NAMES["crag_retry"],
            {"quality_status": "PASS", "summary": {"crag_retry_plan_count": 0}, "records": [{"answer_permission": False}]},
        )

    monkeypatch.setattr(
        bridge,
        "_import_stage_builders",
        lambda: {
            "query_planner": fake_query_planner,
            "context_pack_blueprint": fake_blueprint,
            "context_pack_builder": fake_pack_builder,
            "self_rag": fake_self_rag,
            "crag_retry": fake_crag,
        },
    )

    payload = bridge.build_webui_self_rag_crag_bridge(
        question="What visual context is available?",
        kernel_path=kernel,
        output_dir=tmp_path / "bridge",
        route_dispatch_handoff=route_dispatch,
        webui_visual_context_bridge=visual_bridge,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["tool_statuses"]["webui_visual_context_bridge"] == "used"
    assert payload["tool_statuses"]["visual_image_route"] == "used"
    assert payload["summary"]["visual_context_card_count"] == 2
    assert payload["summary"]["review_only_visual_context_excluded_count"] == 10
    assert payload["summary"]["visual_context_included_pages"] == ["t_p_120_1176_p000001", "t_p_120_1176_p000022"]
    assert len(payload["webui_visual_context_cards"]) == 2


def test_quality_check_can_require_visual_context_bridge(tmp_path):
    report = tmp_path / bridge.REPORT_NAME
    report.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "summary": {
                    "tool_checklist_count": 10,
                    "used_tool_count": 7,
                    "visual_context_card_count": 2,
                    "answer_permission_count": 0,
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
                    "visual_image_route": "used",
                    "webui_visual_context_bridge": "used",
                },
            }
        ),
        encoding="utf-8",
    )
    result = bridge.check_webui_self_rag_crag_bridge_quality(
        report_path=report,
        require_webui_visual_context_bridge_used=True,
        min_visual_context_cards=2,
        require_no_write_attempts=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"
