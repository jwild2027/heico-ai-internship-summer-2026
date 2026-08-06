from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_human_review_queue_v1 import build_human_review_queue


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_human_review_queue_from_multiple_sources(tmp_path: Path) -> None:
    it_console = write_json(
        tmp_path / "it.json",
        {
            "quality_status": "PASS",
            "issues": [
                {
                    "severity": "warning",
                    "category": "ocr_text",
                    "stage_id": "ocr_depth",
                    "key": "empty_or_missing_ocr_page_count",
                    "value": 14,
                    "message": "14 pages have empty OCR.",
                    "recommended_action": "Review blank/source trace pages.",
                }
            ],
        },
    )
    fishnet = write_json(
        tmp_path / "fishnet.json",
        {
            "quality_status": "PASS",
            "records": [
                {
                    "page_id": "p1",
                    "fishnet_disposition": "review_required",
                    "priority": "high",
                    "review_actions": ["human_review_for_unverified_visual_page"],
                    "actual_retry_actions": ["validate_visual_regions_and_callouts"],
                    "needs_vision_model": True,
                },
                {
                    "page_id": "p2",
                    "fishnet_disposition": "source_confirmed_blank_preserve_trace",
                    "blank_handling_actions": ["confirm_blank_without_losing_source_trace"],
                },
            ],
        },
    )
    table = write_json(
        tmp_path / "table.json",
        {
            "quality_status": "PASS",
            "records": [
                {
                    "page_id": "p1",
                    "normalized_table_id": "t1",
                    "repair_count": 1,
                    "repairs": [{"merged_part_number": "120-46137-001"}],
                    "citation_ids": ["cite:table:p1"],
                }
            ],
        },
    )
    visual = write_json(
        tmp_path / "visual.json",
        {
            "quality_status": "PASS",
            "records": [
                {
                    "page_id": "p1",
                    "visual_type": "parts_diagram_or_illustrated_parts_list",
                    "needs_human_review": True,
                    "requires_catalog_compare": True,
                    "linked_part_candidates": ["120-46137-001"],
                    "callout_labels": ["1", "2"],
                }
            ],
        },
    )
    feedback = write_json(
        tmp_path / "feedback.json",
        {
            "quality_status": "PASS",
            "memory_records": [
                {
                    "memory_id": "m1",
                    "target_type": "answer",
                    "target_id": "a1",
                    "rating_score": -1,
                    "prompt_injection_flagged": False,
                    "feedback_summary": "not useful",
                },
                {
                    "memory_id": "m2",
                    "target_type": "answer",
                    "target_id": "a2",
                    "rating_score": -1,
                    "prompt_injection_flagged": True,
                },
            ],
        },
    )
    leiden = write_json(
        tmp_path / "leiden.json",
        {
            "quality_status": "PASS",
            "communities": [
                {
                    "community_id": "c1",
                    "node_count": 100,
                    "page_count": 10,
                    "dominant_node_types": ["TableCell", "CalloutCandidate"],
                    "part_families": ["120-46137"],
                    "part_numbers": ["120-46137-001"],
                }
            ],
        },
    )

    report = build_human_review_queue(
        it_console_path=it_console,
        fishnet_retry_refined_path=fishnet,
        table_cell_normalizer_path=table,
        figure_chart_understanding_path=visual,
        feedback_memory_path=feedback,
        leiden_communities_path=leiden,
        output_dir=tmp_path / "out",
        min_review_tasks=1,
        min_high_priority_review_tasks=1,
        require_it_console_quality_pass=True,
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["review_task_count"] >= 6
    assert summary["prompt_injection_review_task_count"] == 1
    assert summary["table_repair_review_task_count"] >= 1
    assert summary["visual_review_task_count"] >= 1
    assert summary["feedback_review_task_count"] >= 2
    assert summary["community_review_task_count"] == 1
    assert summary["review_task_can_answer_directly_count"] == 0
    assert summary["review_task_can_prove_claims_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0
    assert (tmp_path / "out" / "trace_net_human_review_queue_v1_tasks.jsonl").exists()


def test_review_tasks_do_not_include_raw_answer_authority(tmp_path: Path) -> None:
    feedback = write_json(
        tmp_path / "feedback.json",
        {
            "quality_status": "PASS",
            "memory_records": [
                {
                    "memory_id": "m2",
                    "target_type": "answer",
                    "target_id": "a2",
                    "rating_score": -1,
                    "prompt_injection_flagged": True,
                }
            ],
        },
    )
    report = build_human_review_queue(
        feedback_memory_path=feedback,
        output_dir=tmp_path / "out",
        min_review_tasks=1,
        min_high_priority_review_tasks=1,
    )
    assert report["quality_status"] == "PASS"
    task = report["review_tasks"][0]
    assert task["can_answer_directly"] is False
    assert task["can_prove_claims"] is False
    assert task["can_mutate_source_truth"] is False
    assert task["review_queue_authority"] == "human_review_advisory_only"


def test_missing_required_page_id_fails_quality(tmp_path: Path) -> None:
    fishnet = write_json(
        tmp_path / "fishnet.json",
        {
            "quality_status": "PASS",
            "records": [
                {
                    "fishnet_disposition": "review_required",
                    "review_actions": ["human_review_for_unverified_visual_page"],
                }
            ],
        },
    )
    report = build_human_review_queue(
        fishnet_retry_refined_path=fishnet,
        output_dir=tmp_path / "out",
        min_review_tasks=1,
        min_high_priority_review_tasks=0,
    )
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["missing_page_id_count"] >= 1
