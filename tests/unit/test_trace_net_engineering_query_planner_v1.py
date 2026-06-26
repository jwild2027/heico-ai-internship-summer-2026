
import json
from pathlib import Path

from tiff.trace_net_engineering_reasoning_kernel_v1 import build_engineering_reasoning_kernel
from tiff.trace_net_engineering_query_planner_v1 import (
    build_engineering_query_planner,
    check_engineering_query_planner_quality,
)


def test_query_planner_builds_dimensional_plan(tmp_path):
    kernel = build_engineering_reasoning_kernel(output_dir=tmp_path / "kernel")
    kernel_path = tmp_path / "kernel" / "trace_net_engineering_reasoning_kernel_v1.json"

    payload = build_engineering_query_planner(
        kernel_path=kernel_path,
        output_dir=tmp_path / "planner",
        questions=["This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?"],
    )

    plan = payload["records"][0]
    assert payload["quality_status"] == "PASS"
    assert plan["selected_playbook_id"] == "dimensional_change_candidate_search"
    assert plan["seed_entities"] == ["123-45"]
    assert plan["requested_change"]["property"] == "length"
    assert plan["requested_change"]["direction"] == "decrease"
    assert "table" in plan["dynamic_context_pack_blueprint"]["route_context_needed"]
    assert plan["llm_call_allowed"] is False
    assert plan["retrieval_execution_allowed"] is False


def test_query_planner_builds_solvent_procedure_plan(tmp_path):
    build_engineering_reasoning_kernel(output_dir=tmp_path / "kernel")
    kernel_path = tmp_path / "kernel" / "trace_net_engineering_reasoning_kernel_v1.json"

    payload = build_engineering_query_planner(
        kernel_path=kernel_path,
        output_dir=tmp_path / "planner",
        questions=["Can I clean this part with solvent?"],
    )

    plan = payload["records"][0]
    assert plan["selected_playbook_id"] == "fault_repair_procedure_reasoning"
    assert plan["intent_family"] == "repair_or_fault_context"
    assert "normal_text" in plan["dynamic_context_pack_blueprint"]["route_context_needed"]
    assert "uncited repair procedure" in plan["forbidden_answer_claims"]


def test_query_planner_quality_passes(tmp_path):
    build_engineering_reasoning_kernel(output_dir=tmp_path / "kernel")
    kernel_path = tmp_path / "kernel" / "trace_net_engineering_reasoning_kernel_v1.json"
    build_engineering_query_planner(
        kernel_path=kernel_path,
        output_dir=tmp_path / "planner",
        questions=["Find part number 120-29073-001 and nearby similar parts."],
    )
    report = tmp_path / "planner" / "trace_net_engineering_query_planner_v1.json"
    result = check_engineering_query_planner_quality(
        report_path=report,
        require_source_kernel_quality_pass=True,
        min_query_plans=1,
        min_plans_with_seed_entities=1,
        require_no_answer_permission=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"
