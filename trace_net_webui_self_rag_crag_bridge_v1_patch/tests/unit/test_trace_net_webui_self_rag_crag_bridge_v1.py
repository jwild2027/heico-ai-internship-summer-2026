import json
from pathlib import Path

from tiff import trace_net_webui_self_rag_crag_bridge_v1 as bridge


def _write(path: Path, payload: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def test_bridge_build_runs_planner_self_rag_and_crag_with_fake_stage_builders(tmp_path, monkeypatch):
    kernel = tmp_path / "kernel.json"
    kernel.write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
    route_dispatch = tmp_path / "route_dispatch.json"
    route_dispatch.write_text(json.dumps({"records": [{"page_id": "source_p000001", "text": "120-29073-001 seat assembly"}]}), encoding="utf-8")

    def fake_query_planner(*, kernel_path, output_dir, questions):
        assert kernel_path == kernel
        payload = {
            "quality_status": "PASS",
            "summary": {"query_plan_count": len(questions)},
            "records": [{"question_id": "q1", "user_question": questions[0], "answer_permission": False}],
        }
        return _write(output_dir / bridge.STAGE_REPORT_NAMES["query_planner"], payload)

    def fake_blueprint(*, query_planner_path, output_dir):
        assert query_planner_path.exists()
        payload = {
            "quality_status": "PASS",
            "summary": {"context_pack_blueprint_count": 1},
            "records": [{"blueprint_id": "b1", "answer_permission": False}],
        }
        return _write(output_dir / bridge.STAGE_REPORT_NAMES["context_pack_blueprint"], payload)

    def fake_pack_builder(**kwargs):
        assert kwargs["blueprint_path"].exists()
        assert kwargs["route_dispatch_handoff"] == route_dispatch
        payload = {
            "quality_status": "PASS",
            "summary": {
                "context_pack_count": 1,
                "total_evidence_capsule_count": 2,
                "total_high_signal_evidence_capsule_count": 1,
                "artifact_record_counts": {
                    "fishnet_route_dispatch_handoff": 1,
                    "table_exact_search_adapter": 0,
                    "page_context_v2": 0,
                    "leiden_communities": 0,
                    "image_visual_observer": 0,
                },
            },
            "records": [{"context_pack_id": "cp1", "answer_permission": False}],
        }
        return _write(kwargs["output_dir"] / bridge.STAGE_REPORT_NAMES["context_pack_builder"], payload)

    def fake_self_rag(*, context_pack_path, output_dir, min_high_signal_capsules, min_evidence_strength_score):
        assert context_pack_path.exists()
        payload = {
            "quality_status": "PASS",
            "summary": {
                "self_rag_record_count": 1,
                "ready_for_gemma_draft_count": 0,
                "crag_retry_required_count": 1,
                "self_rag_status_counts": {"CRAG_RETRY_REQUIRED": 1},
            },
            "records": [{"self_rag_record_id": "sr1", "crag_retry_required": True, "answer_permission": False}],
        }
        return _write(output_dir / bridge.STAGE_REPORT_NAMES["self_rag"], payload)

    def fake_crag(*, self_rag_report_path, output_dir):
        assert self_rag_report_path.exists()
        payload = {
            "quality_status": "PASS",
            "summary": {
                "crag_retry_plan_count": 1,
                "ready_for_crag_execution_count": 1,
                "answer_permission_count": 0,
            },
            "records": [{"crag_retry_plan_id": "cr1", "answer_permission": False}],
        }
        return _write(output_dir / bridge.STAGE_REPORT_NAMES["crag_retry"], payload)

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
        question="Find part number 120-29073-001",
        kernel_path=kernel,
        output_dir=tmp_path / "bridge",
        route_dispatch_handoff=route_dispatch,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["tool_statuses"]["query_planner"] == "used"
    assert payload["tool_statuses"]["self_rag"] == "used"
    assert payload["tool_statuses"]["crag_retry"] == "used"
    assert payload["tool_statuses"]["route_dispatch"] == "used"
    assert payload["summary"]["self_rag_crag_retry_required_count"] == 1
    assert payload["summary"]["answer_permission_count"] == 0


def test_crag_is_marked_skipped_not_needed_when_self_rag_is_strong(tmp_path):
    self_payload = {"summary": {"crag_retry_required_count": 0}}
    crag_payload = {"quality_status": "PASS", "summary": {"crag_retry_plan_count": 0}}
    row = bridge._crag_row(crag_payload, tmp_path / "crag.json", self_payload)
    assert row["status"] == "skipped_not_needed"
    assert "did not require" in row["reason"]


def test_checklist_text_includes_reasons():
    text = bridge._checklist_text([
        {"label": "Self-RAG", "status": "used", "reason": "stage report built"},
        {"label": "CRAG retry", "status": "skipped_not_needed", "reason": "Self-RAG was strong"},
    ])
    assert "Self-RAG: used" in text
    assert "CRAG retry: skipped_not_needed" in text
