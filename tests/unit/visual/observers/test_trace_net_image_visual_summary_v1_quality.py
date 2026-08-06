from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_image_visual_summary_v1 import check_image_visual_summary_quality


def _write_report(path: Path, summary: dict, quality_status: str = "PASS") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"quality_status": quality_status, "summary": summary}), encoding="utf-8")
    return path


def test_quality_passes_with_required_safety_counts(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "report.json",
        {
            "source_route_dispatch_handoff_quality_status": "PASS",
            "image_visual_handoff_count": 2,
            "visual_summary_card_count": 2,
            "image_source_found_count": 0,
            "vision_model_called_count": 0,
            "vision_observation_ready_count": 0,
            "vision_mode": "dry_run",
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    )
    result = check_image_visual_summary_quality(
        report_path=report,
        require_source_route_dispatch_quality_pass=True,
        min_image_visual_handoffs=1,
        min_summary_cards=1,
        require_vision_mode="dry_run",
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_fails_when_answer_permission_present(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "report.json",
        {
            "source_route_dispatch_handoff_quality_status": "PASS",
            "image_visual_handoff_count": 1,
            "visual_summary_card_count": 1,
            "vision_mode": "dry_run",
            "unsafe_record_count": 0,
            "answer_permission_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    )
    result = check_image_visual_summary_quality(report_path=report, require_no_answer_permission=True)
    assert result["quality_status"] == "FAIL"
    assert any("answer permission" in failure for failure in result["failures"])


def test_quality_can_require_vision_execution(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "report.json",
        {
            "source_route_dispatch_handoff_quality_status": "PASS",
            "image_visual_handoff_count": 1,
            "visual_summary_card_count": 1,
            "vision_mode": "ollama",
            "vision_observation_ready_count": 0,
            "unsafe_record_count": 0,
        },
    )
    result = check_image_visual_summary_quality(report_path=report, require_vision_execution=True)
    assert result["quality_status"] == "FAIL"
    assert any("vision-model" in failure for failure in result["failures"])
