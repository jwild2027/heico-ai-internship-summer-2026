from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_incremental_state_commit_gate_v1 import (
    build_incremental_state_commit_gate,
    quality_report,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def runner_report(full_rescan: bool = False, unchanged_reprocess: int = 0) -> dict:
    return {
        "status": "INCREMENTAL_PROCESSING_RUNNER_BUILT",
        "quality_status": "PASS",
        "summary": {
            "quality_status": "PASS",
            "page_count": 509,
            "dirty_page_count": 0,
            "affected_page_count": 0,
            "planned_job_count": 0,
            "processing_step_count": 0,
            "no_op_processed": True,
            "full_rescan_required": full_rescan,
            "unchanged_page_reprocess_count": unchanged_reprocess,
            "unsafe_processing_step_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_truth_mutations_performed": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
        },
        "processing_steps": [],
    }


def test_quality_report_passes_clean_gate(tmp_path: Path) -> None:
    src = tmp_path / "runner.json"
    write_json(src, runner_report())
    build_incremental_state_commit_gate(src, tmp_path / "out")
    result = quality_report(
        tmp_path / "out" / "trace_net_incremental_state_commit_gate_v1.json",
        require_page_count=509,
        require_no_full_rescan=True,
        max_unchanged_page_reprocess=0,
    )
    assert result["status"] == "PASS"
    assert result["state_commit_decision"] == "no_op_no_state_commit_needed"


def test_quality_report_fails_full_rescan(tmp_path: Path) -> None:
    src = tmp_path / "runner.json"
    write_json(src, runner_report(full_rescan=True))
    build_incremental_state_commit_gate(src, tmp_path / "out")
    result = quality_report(
        tmp_path / "out" / "trace_net_incremental_state_commit_gate_v1.json",
        require_no_full_rescan=True,
    )
    assert result["status"] == "FAIL"


def test_quality_report_fails_unchanged_reprocess(tmp_path: Path) -> None:
    src = tmp_path / "runner.json"
    write_json(src, runner_report(unchanged_reprocess=3))
    build_incremental_state_commit_gate(src, tmp_path / "out")
    result = quality_report(
        tmp_path / "out" / "trace_net_incremental_state_commit_gate_v1.json",
        max_unchanged_page_reprocess=0,
    )
    assert result["status"] == "FAIL"


def test_quality_json_written(tmp_path: Path) -> None:
    src = tmp_path / "runner.json"
    write_json(src, runner_report())
    build_incremental_state_commit_gate(src, tmp_path / "out")
    result = quality_report(
        tmp_path / "out" / "trace_net_incremental_state_commit_gate_v1.json",
        write_json_report=True,
    )
    assert result["status"] == "PASS"
    assert (tmp_path / "out" / "trace_net_incremental_state_commit_gate_v1_quality.json").exists()
