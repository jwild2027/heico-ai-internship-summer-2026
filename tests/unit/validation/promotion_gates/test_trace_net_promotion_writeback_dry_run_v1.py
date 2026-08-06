from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_promotion_writeback_dry_run_v1 import (
    build_promotion_writeback_dry_run,
    is_approved_promotion,
    planned_writeback_type,
)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def promotion_gate_payload(records: list[dict]) -> dict:
    return {
        "schema_version": "trace_net_human_review_promotion_gate_v1",
        "quality_status": "PASS",
        "summary": {"status": "PASS"},
        "promotion_records": records,
    }


def test_approved_table_repair_creates_dry_run_plan(tmp_path: Path) -> None:
    gate = tmp_path / "promotion_gate.json"
    write_json(
        gate,
        promotion_gate_payload([
            {
                "promotion_evaluation_id": "prom_1",
                "review_decision_id": "dec_1",
                "decision_type": "confirm_table_repair",
                "promotion_candidate": True,
                "promotion_gate_status": "approved_for_controlled_promotion",
                "promotion_effect": "promote_table_repair_candidate",
                "target_type": "triage_card",
                "target_id": "triage_1",
                "page_ids": ["t_p_120_1176_p000003"],
                "citation_ids": ["cite:table_structured:t_p_120_1176_p000003:abc"],
                "part_numbers": ["120-46137-001"],
            }
        ]),
    )

    report = build_promotion_writeback_dry_run(
        gate,
        tmp_path / "out",
        min_writeback_plans=1,
        require_promotion_gate_quality_pass=True,
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["writeback_plan_count"] == 1
    plan = report["writeback_plans"][0]
    assert plan["writeback_mode"] == "dry_run"
    assert plan["planned_writeback_type"] == "promote_reviewed_table_repair_candidate"
    assert plan["page_ids"] == ["t_p_120_1176_p000003"]
    assert plan["citation_ids"] == ["cite:table_structured:t_p_120_1176_p000003:abc"]
    assert plan["requires_writeback_gate"] is True
    assert plan["requires_regression_after_writeback"] is True
    assert plan["postgres_write_attempted"] is False
    assert plan["can_answer_directly"] is False
    assert plan["can_prove_claims"] is False
    assert plan["can_mutate_source_truth"] is False


def test_non_promotion_decisions_are_no_op(tmp_path: Path) -> None:
    gate = tmp_path / "promotion_gate.json"
    write_json(
        gate,
        promotion_gate_payload([
            {
                "promotion_evaluation_id": "prom_1",
                "review_decision_id": "dec_1",
                "decision_type": "needs_more_review",
                "promotion_candidate": False,
                "promotion_gate_status": "not_a_promotion_candidate",
                "target_type": "triage_card",
                "target_id": "triage_1",
            }
        ]),
    )

    report = build_promotion_writeback_dry_run(gate, tmp_path / "out", min_writeback_plans=0)

    assert report["quality_status"] == "PASS"
    assert report["summary"]["writeback_plan_count"] == 0
    assert report["summary"]["no_op_planned"] is True


def test_missing_table_citation_blocks_quality_when_plan_required(tmp_path: Path) -> None:
    gate = tmp_path / "promotion_gate.json"
    write_json(
        gate,
        promotion_gate_payload([
            {
                "promotion_evaluation_id": "prom_1",
                "review_decision_id": "dec_1",
                "decision_type": "confirm_table_repair",
                "promotion_candidate": True,
                "promotion_gate_status": "approved_for_controlled_promotion",
                "target_type": "triage_card",
                "target_id": "triage_1",
                "page_ids": ["t_p_120_1176_p000003"],
                "citation_ids": [],
            }
        ]),
    )

    report = build_promotion_writeback_dry_run(gate, tmp_path / "out", min_writeback_plans=1)

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["writeback_plan_missing_citation_count"] == 1
    assert report["writeback_plans"][0]["writeback_status"] == "blocked_missing_required_support"


def test_status_and_type_helpers() -> None:
    record = {"promotion_candidate": True, "promotion_gate_status": "approved_for_controlled_promotion", "decision_type": "confirm_part_link"}
    assert is_approved_promotion(record) is True
    assert planned_writeback_type(record) == "promote_reviewed_visual_part_link_candidate"
