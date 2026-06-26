
import json
from pathlib import Path

from tiff.trace_net_engineering_reasoning_kernel_v1 import (
    build_engineering_reasoning_kernel,
    check_engineering_reasoning_kernel_quality,
)


def _write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_kernel_with_route_dispatch_context(tmp_path):
    route_dispatch = {
        "quality_status": "PASS",
        "summary": {
            "route_handoff_counts": {
                "normal_text": 15,
                "blank_candidate": 461,
                "table": 21,
                "image_visual": 12,
            },
            "normal_text_handoff_count": 15,
            "table_handoff_count": 21,
            "image_visual_handoff_count": 12,
            "blank_candidate_handoff_count": 461,
        },
    }
    route_path = tmp_path / "route_dispatch.json"
    _write(route_path, route_dispatch)

    payload = build_engineering_reasoning_kernel(
        output_dir=tmp_path / "out",
        route_dispatch_handoff=route_path,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["playbook_count"] >= 5
    assert payload["summary"]["example_card_count"] >= 4
    assert payload["summary"]["route_dispatch_available"] is True
    assert payload["summary"]["normal_text_handoff_count"] == 15
    assert payload["safety_contract"]["llm_call_allowed"] is False
    assert payload["safety_contract"]["answers_user_question"] is False


def test_sample_intent_detects_dimensional_change(tmp_path):
    payload = build_engineering_reasoning_kernel(
        output_dir=tmp_path / "out",
        sample_questions=["This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?"],
    )
    plan = payload["sample_intent_plans"][0]
    assert plan["selected_playbook_id"] == "dimensional_change_candidate_search"
    assert plan["intent_family"] == "engineering_change_candidate"
    assert "dimension_table_search" in plan["retrieval_plan"]


def test_sample_intent_detects_clean_solvent_procedure(tmp_path):
    payload = build_engineering_reasoning_kernel(
        output_dir=tmp_path / "out",
        sample_questions=["Can I clean this part with solvent?"],
    )
    plan = payload["sample_intent_plans"][0]
    assert plan["selected_playbook_id"] == "fault_repair_procedure_reasoning"
    assert plan["intent_family"] == "repair_or_fault_context"
    assert "warning_caution_note_search" in plan["retrieval_plan"]


def test_quality_checker_passes(tmp_path):
    payload = build_engineering_reasoning_kernel(output_dir=tmp_path / "out")
    report = tmp_path / "out" / "trace_net_engineering_reasoning_kernel_v1.json"
    result = check_engineering_reasoning_kernel_quality(
        report_path=report,
        min_playbooks=5,
        min_examples=4,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
    )
    assert result["quality_status"] == "PASS"
