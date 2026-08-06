from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_human_review_queue_table_geometry_integration_v1 import (
    build_human_review_queue_table_geometry_integration,
    convert_table_geometry_review_task,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_bridge() -> dict:
    return {
        "schema_version": "trace_net_table_geometry_review_bridge_v1",
        "quality_status": "PASS",
        "review_tasks": [
            {
                "review_task_id": "table_geometry_review::a",
                "priority": "HIGH",
                "issue_type": "table_geometry_image_line_detection_missing",
                "page_id": "t_p_120_1176_p000003",
                "table_id": "normtable__parts",
                "table_type": "parts_list_table",
                "geometry_confidence": 0.7,
                "image_line_detection_available": False,
                "cell_record_count": 215,
                "row_record_count": 75,
                "part_number_count": 68,
                "part_numbers": ["120-46137-001"],
                "review_flags": ["image_not_available_for_geometry_card", "line_detection_unavailable_or_empty"],
                "recommended_actions": ["run_or_expand_morphological_line_detection", "confirm_table_cell_assignment"],
                "requires_human_review": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            },
            {
                "review_task_id": "table_geometry_review::b",
                "priority": "MEDIUM",
                "issue_type": "table_geometry_image_line_detection_missing",
                "page_id": "t_p_120_1176_p000005",
                "table_id": "normtable__lep",
                "table_type": "list_of_effective_pages",
                "geometry_confidence": 0.6,
                "image_line_detection_available": False,
                "cell_record_count": 100,
                "row_record_count": 30,
                "part_number_count": 0,
                "review_flags": ["image_not_available_for_geometry_card"],
                "recommended_actions": ["verify_table_geometry_against_source_page"],
                "requires_human_review": True,
            },
        ],
    }


def sample_base_queue() -> dict:
    return {
        "schema_version": "trace_net_human_review_queue_v1",
        "quality_status": "PASS",
        "review_tasks": [
            {
                "review_task_id": "review_existing",
                "schema_version": "trace_net_human_review_queue_v1",
                "task_type": "review_existing_task",
                "priority": "low",
                "origin_category": "existing",
                "source_stage": "existing_stage",
                "page_id": "t_p_120_1176_p000001",
                "requires_page_id": True,
                "missing_page_id": False,
                "target_type": "page",
                "target_id": "t_p_120_1176_p000001",
                "reason": "Existing task",
                "recommended_action": "Review existing task",
                "review_status": "open",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
                "final_answer_allowed": False,
                "unsafe_review_task": False,
            }
        ],
    }


def test_convert_table_geometry_task_preserves_safety_and_metadata() -> None:
    task = convert_table_geometry_review_task(sample_bridge()["review_tasks"][0], artifact_path="bridge.json")
    assert task["task_type"] == "review_table_geometry_line_detection"
    assert task["priority"] == "high"
    assert task["origin_category"] == "table_geometry"
    assert task["source_stage"] == "table_geometry_review_bridge"
    assert task["page_id"] == "t_p_120_1176_p000003"
    assert task["table_id"] == "normtable__parts"
    assert task["part_number_count"] == 68
    assert "120-46137-001" in task["part_numbers"]
    assert task["requires_human_review"] is True
    assert task["can_answer_directly"] is False
    assert task["can_prove_claims"] is False
    assert task["source_truth_mutation_allowed"] is False
    assert task["final_answer_allowed"] is False


def test_build_merges_table_geometry_tasks_into_main_queue(tmp_path: Path) -> None:
    base_path = tmp_path / "human_review_queue" / "trace_net_human_review_queue_v1.json"
    bridge_path = tmp_path / "table_geometry_review_bridge" / "trace_net_table_geometry_review_bridge_v1.json"
    out_dir = tmp_path / "human_review_queue"
    write_json(base_path, sample_base_queue())
    write_json(bridge_path, sample_bridge())

    report = build_human_review_queue_table_geometry_integration(
        human_review_queue_path=base_path,
        table_geometry_review_bridge_path=bridge_path,
        output_dir=out_dir,
        min_review_tasks=3,
        min_table_geometry_review_tasks=2,
        require_table_geometry_bridge_quality_pass=True,
        require_no_answer_permission=True,
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["schema_version"] == "trace_net_human_review_queue_v1"
    assert report["summary"]["review_task_count"] == 3
    assert report["summary"]["table_geometry_review_task_count"] == 2
    assert report["summary"]["table_geometry_high_priority_task_count"] == 1
    assert report["summary"]["answer_permission_count"] == 0
    assert (out_dir / "trace_net_human_review_queue_v1.json").exists()
    assert (out_dir / "trace_net_human_review_queue_v1_tasks.jsonl").exists()
    assert (out_dir / "trace_net_human_review_queue_table_geometry_integration_v1_quality.json").exists()


def test_build_can_create_queue_without_existing_base(tmp_path: Path) -> None:
    bridge_path = tmp_path / "bridge.json"
    write_json(bridge_path, sample_bridge())
    report = build_human_review_queue_table_geometry_integration(
        human_review_queue_path=None,
        table_geometry_review_bridge_path=bridge_path,
        output_dir=tmp_path / "queue",
        min_review_tasks=2,
        min_table_geometry_review_tasks=2,
        require_table_geometry_bridge_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["base_review_task_count"] == 0
    assert report["summary"]["table_geometry_review_task_count"] == 2


def test_bridge_quality_requirement_can_fail(tmp_path: Path) -> None:
    bridge = sample_bridge()
    bridge["quality_status"] = "FAIL"
    bridge_path = tmp_path / "bridge.json"
    write_json(bridge_path, bridge)
    report = build_human_review_queue_table_geometry_integration(
        human_review_queue_path=None,
        table_geometry_review_bridge_path=bridge_path,
        output_dir=tmp_path / "queue",
        min_review_tasks=1,
        min_table_geometry_review_tasks=1,
        require_table_geometry_bridge_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert report["quality_status"] == "FAIL"
    assert "table_geometry_bridge_quality_pass" in report["summary"]["quality_fail_reasons"]
