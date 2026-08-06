from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_human_review_triage_v1 import (
    build_cards,
    build_human_review_triage,
    group_key_for_task,
)


def sample_task(task_id: str, page_id: str | None, task_type: str, priority: str = "medium") -> dict:
    return {
        "review_task_id": task_id,
        "task_type": task_type,
        "priority": priority,
        "origin_category": "visual_diagram" if "visual" in task_type or "callout" in task_type else "table_extraction",
        "source_stage": "unit",
        "page_id": page_id,
        "target_type": "page" if page_id else "community",
        "target_id": page_id or "community_1",
        "reason": f"Reason for {task_type}",
        "recommended_action": f"Action for {task_type}",
        "citation_ids": ["cite:1"] if page_id else [],
        "part_numbers": ["120-12345-001"] if page_id else [],
        "community_ids": ["community_1"] if not page_id else [],
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
    }


def test_group_key_critical_is_target_scoped() -> None:
    task = sample_task("t1", "p1", "review_prompt_injection_feedback", "critical")
    task["origin_category"] = "feedback_memory"
    task["target_type"] = "answer"
    task["target_id"] = "answer_1"
    assert group_key_for_task(task)[0] == "critical"


def test_build_cards_groups_page_tasks_and_preserves_safety() -> None:
    tasks = [
        sample_task("t1", "p1", "review_callout_candidates", "high"),
        sample_task("t2", "p1", "verify_visual_part_candidates", "medium"),
        sample_task("t3", "p2", "review_repaired_table_cells", "high"),
    ]
    cards = build_cards(tasks)
    assert len(cards) == 2
    p1 = next(card for card in cards if card.get("page_id") == "p1")
    assert p1["task_count"] == 2
    assert p1["priority"] == "high"
    assert p1["can_answer_directly"] is False
    assert p1["can_prove_claims"] is False
    assert p1["can_mutate_source_truth"] is False


def test_build_human_review_triage_writes_outputs(tmp_path: Path) -> None:
    queue = {
        "schema_version": "trace_net_human_review_queue_v1",
        "quality_status": "PASS",
        "summary": {"review_task_count": 4},
        "review_tasks": [
            sample_task("t1", "p1", "review_callout_candidates", "high"),
            sample_task("t2", "p1", "verify_visual_part_candidates", "medium"),
            sample_task("t3", "p2", "review_repaired_table_cells", "high"),
            sample_task("t4", None, "review_high_signal_graph_community", "low"),
        ],
    }
    qpath = tmp_path / "queue.json"
    qpath.write_text(json.dumps(queue), encoding="utf-8")
    report = build_human_review_triage(
        human_review_queue_path=qpath,
        output_dir=tmp_path / "out",
        min_triage_cards=1,
        min_high_priority_cards=1,
        require_source_queue_quality_pass=True,
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["input_review_task_count"] == 4
    assert report["summary"]["triage_card_count"] == 3
    assert report["summary"]["deduped_task_count"] == 1
    assert (tmp_path / "out" / "trace_net_human_review_triage_v1_cards.jsonl").exists()


def test_critical_task_preserved_as_card(tmp_path: Path) -> None:
    critical = sample_task("critical", "p1", "review_prompt_injection_feedback", "critical")
    critical["origin_category"] = "feedback_memory"
    critical["target_type"] = "answer"
    critical["target_id"] = "answer_1"
    normal = sample_task("normal", "p1", "review_callout_candidates", "medium")
    qpath = tmp_path / "queue.json"
    qpath.write_text(json.dumps({"quality_status": "PASS", "review_tasks": [critical, normal]}), encoding="utf-8")
    report = build_human_review_triage(human_review_queue_path=qpath, output_dir=tmp_path / "out")
    assert report["summary"]["critical_task_input_count"] == 1
    assert report["summary"]["critical_task_preserved_count"] == 1
    assert any(card["card_type"] == "critical_review_card" for card in report["triage_cards"])
