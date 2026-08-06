
import json
from pathlib import Path

from tiff.trace_net_engineering_context_crag_retry_plan_v1 import (
    build_engineering_context_crag_retry_plan,
    check_engineering_context_crag_retry_plan_quality,
)


def _write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _self_rag_payload():
    return {
        "quality_status": "PASS",
        "summary": {"crag_retry_required_count": 2},
        "records": [
            {
                "self_rag_record_id": "engineering_self_rag_0001",
                "context_pack_id": "pack1",
                "question_id": "q1",
                "user_question": "This model number 123-45 needs to be 4 inches shorter.",
                "intent_family": "engineering_change_candidate",
                "selected_playbook_id": "dimensional_change_candidate_search",
                "self_rag_status": "CRAG_RETRY_REQUIRED",
                "evidence_strength_score": 52,
                "source_truth_evidence_strength": "partial_source_truth_context",
                "missing_evidence_types": ["source_dimension_not_confirmed"],
                "critical_missing_evidence_types": ["source_dimension_not_confirmed"],
                "missing_evidence": [
                    {"missing_type": "source_dimension_not_confirmed", "route": "table", "crag_retry_recommended": True}
                ],
                "crag_retry_reasons": [
                    "critical_missing:source_dimension_not_confirmed",
                    "missing_evidence:source_dimension_not_confirmed:table",
                ],
                "crag_retry_required": True,
            },
            {
                "self_rag_record_id": "engineering_self_rag_0002",
                "context_pack_id": "pack2",
                "question_id": "q2",
                "user_question": "Show visually similar callout parts in the same figure.",
                "intent_family": "visual_or_callout_similarity",
                "selected_playbook_id": "visual_similarity_candidate_search",
                "self_rag_status": "CRAG_RETRY_REQUIRED",
                "evidence_strength_score": 41,
                "source_truth_evidence_strength": "partial_source_truth_context",
                "missing_evidence_types": ["route_slot_unfilled"],
                "critical_missing_evidence_types": ["route_slot_unfilled"],
                "missing_evidence": [
                    {"missing_type": "route_slot_unfilled", "route": "image_visual", "crag_retry_recommended": True}
                ],
                "crag_retry_reasons": [
                    "critical_missing:route_slot_unfilled",
                    "missing_evidence:route_slot_unfilled:image_visual",
                ],
                "crag_retry_required": True,
            },
        ],
    }


def test_build_crag_retry_plan_dedupes_unknown_routes(tmp_path):
    src = tmp_path / "self_rag.json"
    _write(src, _self_rag_payload())

    payload = build_engineering_context_crag_retry_plan(
        self_rag_report_path=src,
        output_dir=tmp_path / "out",
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["crag_retry_plan_count"] == 2
    assert payload["summary"]["unknown_target_route_count"] == 0
    assert payload["summary"]["total_retry_action_count"] == 2

    first = payload["records"][0]
    assert first["target_routes"] == ["table"]
    assert len(first["retry_actions"]) == 1

    second = payload["records"][1]
    assert second["target_routes"] == ["image_visual"]
    assert len(second["retry_actions"]) == 1


def test_quality_checker_passes_with_unknown_route_limit(tmp_path):
    src = tmp_path / "self_rag.json"
    _write(src, _self_rag_payload())
    build_engineering_context_crag_retry_plan(self_rag_report_path=src, output_dir=tmp_path / "out")
    report = tmp_path / "out" / "trace_net_engineering_context_crag_retry_plan_v1.json"

    result = check_engineering_context_crag_retry_plan_quality(
        report_path=report,
        require_source_self_rag_quality_pass=True,
        min_crag_retry_plans=2,
        min_retry_actions=2,
        min_ready_for_crag_execution=2,
        max_unknown_target_routes=0,
        require_no_answer_permission=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"
