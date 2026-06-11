from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_incremental_state_commit_gate_v1 import (
    build_incremental_state_commit_gate,
    evaluate_step_commit_check,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def runner_report(steps: list[dict], *, full_rescan: bool = False, unsafe_count: int = 0) -> dict:
    return {
        "schema_version": "trace_net_incremental_processing_runner_v1",
        "status": "INCREMENTAL_PROCESSING_RUNNER_BUILT",
        "quality_status": "PASS" if unsafe_count == 0 and not full_rescan else "FAIL",
        "summary": {
            "quality_status": "PASS" if unsafe_count == 0 and not full_rescan else "FAIL",
            "page_count": 509,
            "source_record_count": 1018,
            "dirty_page_count": 2 if steps else 0,
            "affected_page_count": 2 if steps else 0,
            "planned_job_count": len(steps),
            "processing_step_count": len(steps),
            "processing_batch_count": len(steps),
            "no_op_processed": not steps,
            "full_rescan_required": full_rescan,
            "unchanged_page_reprocess_count": 0,
            "unsafe_processing_step_count": unsafe_count,
            "external_command_execution_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_truth_mutations_performed": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "state_commit_after_success_only": True,
        },
        "processing_steps": steps,
    }


def step(status: str = "planned_only", unsafe: bool = False) -> dict:
    return {
        "processing_step_id": f"step_{status}_{unsafe}",
        "job_id": "job_1",
        "job_type": "ocr_changed_pages",
        "job_family": "ocr",
        "priority": "medium",
        "execution_status": status,
        "affected_page_count": 2,
        "affected_page_ids": ["p1", "p2"],
        "unsafe_processing_step": unsafe,
        "source_truth_mutation_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
    }


def test_noop_processing_runner_needs_no_state_commit(tmp_path: Path) -> None:
    src = tmp_path / "runner.json"
    write_json(src, runner_report([]))
    report = build_incremental_state_commit_gate(
        src,
        tmp_path / "out",
        require_page_count=509,
        require_no_full_rescan=True,
        max_unchanged_page_reprocess=0,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["state_commit_decision"] == "no_op_no_state_commit_needed"
    assert report["summary"]["state_commit_allowed"] is False
    assert report["summary"]["state_commit_required"] is False
    assert report["commit_checks"] == []


def test_dirty_dry_run_blocks_commit_but_quality_passes(tmp_path: Path) -> None:
    src = tmp_path / "runner.json"
    write_json(src, runner_report([step("planned_only")]))
    report = build_incremental_state_commit_gate(
        src,
        tmp_path / "out",
        require_page_count=509,
        require_commit_blocked_for_pending=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["state_commit_decision"] == "state_commit_pending_execution"
    assert report["summary"]["state_commit_allowed"] is False
    assert report["summary"]["pending_execution_step_count"] == 1


def test_successful_steps_allow_commit_when_required(tmp_path: Path) -> None:
    src = tmp_path / "runner.json"
    write_json(src, runner_report([step("completed_success")]))
    report = build_incremental_state_commit_gate(
        src,
        tmp_path / "out",
        require_page_count=509,
        require_commit_allowed=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["state_commit_decision"] == "state_commit_allowed_after_success"
    assert report["summary"]["state_commit_allowed"] is True
    assert report["summary"]["state_commit_required"] is True


def test_failed_step_blocks_and_fails_quality(tmp_path: Path) -> None:
    src = tmp_path / "runner.json"
    write_json(src, runner_report([step("failed")]))
    report = build_incremental_state_commit_gate(src, tmp_path / "out", require_page_count=509)
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["state_commit_decision"] == "state_commit_blocked_failed_or_unsafe_jobs"
    assert report["summary"]["failed_execution_step_count"] == 1


def test_unsafe_step_blocks_and_fails_quality(tmp_path: Path) -> None:
    src = tmp_path / "runner.json"
    write_json(src, runner_report([step("completed_success", unsafe=True)], unsafe_count=1))
    report = build_incremental_state_commit_gate(src, tmp_path / "out")
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["state_commit_decision"] == "state_commit_blocked_safety"
    assert report["summary"]["safety_violation_commit_check_count"] == 1


def test_evaluate_step_commit_check_maps_statuses() -> None:
    pending = evaluate_step_commit_check(step("planned_only"), 1)
    success = evaluate_step_commit_check(step("success"), 2)
    failed = evaluate_step_commit_check(step("error"), 3)
    assert pending["commit_check_status"] == "pending_execution"
    assert success["state_commit_allowed_for_step"] is True
    assert failed["commit_check_status"] == "blocked_failed_execution"
