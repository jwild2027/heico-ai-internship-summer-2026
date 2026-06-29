from pathlib import Path
import json

from tiff.trace_net_image_visual_summary_v1 import (
    _normalize_visual_observation,
    check_image_visual_summary_quality,
)


def test_observation_cleanup_removes_prompt_leak_labels():
    raw = {
        "visual_page_type": "technical manual",
        "observed_visual_features": [
            {"feature": "text", "location": "center of page"},
            "TRACE-Net's visual observer for a scanned technical manual page.",
        ],
        "visible_callouts": [],
        "visible_text_or_labels": [
            {"label": "TRACE-Net's visual observer for a scanned technical manual page."},
            {"label": "You are"},
            {"label": "Passenger Seats"},
        ],
        "summary": "The page is a technical manual page with centered text.",
        "uncertainty_flags": [{"flag": "uncertain"}],
    }

    cleaned, report = _normalize_visual_observation(raw)

    assert report["prompt_leak_suspected"] is True
    assert report["prompt_leak_removed_item_count"] >= 2
    assert "Passenger Seats" in cleaned["visible_text_or_labels"]
    assert all("TRACE-Net" not in item for item in cleaned["visible_text_or_labels"])
    assert all(item != "You are" for item in cleaned["visible_text_or_labels"])
    assert "prompt_leak_removed_from_visual_model_output" in cleaned["uncertainty_flags"]


def test_observation_cleanup_moves_non_numeric_callout_text_to_labels():
    raw = {
        "visual_page_type": "technical manual",
        "observed_visual_features": [],
        "visible_callouts": ["Component Maintenance Manual with Illustrated Parts List", "10"],
        "visible_text_or_labels": [],
        "summary": "Cover page.",
        "uncertainty_flags": [],
    }

    cleaned, report = _normalize_visual_observation(raw)

    assert "10" in cleaned["visible_callouts"]
    assert "Component Maintenance Manual with Illustrated Parts List" in cleaned["visible_text_or_labels"]
    assert report["moved_non_numeric_callout_count"] == 1
    assert "non_numeric_callouts_reclassified_as_visible_labels" in cleaned["uncertainty_flags"]


def test_quality_check_can_reject_prompt_leak_count(tmp_path: Path):
    report = {
        "quality_status": "PASS",
        "summary": {
            "source_route_dispatch_handoff_quality_status": "PASS",
            "image_visual_handoff_count": 3,
            "visual_summary_card_count": 3,
            "image_source_found_count": 3,
            "vision_model_called_count": 3,
            "vision_mode": "ollama",
            "vision_observation_ready_count": 3,
            "clean_vision_observation_ready_count": 2,
            "prompt_leak_suspected_count": 1,
            "review_required_visual_observation_count": 1,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    path = tmp_path / "trace_net_image_visual_summary_v1.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    result = check_image_visual_summary_quality(
        report_path=path,
        require_source_route_dispatch_quality_pass=True,
        min_image_visual_handoffs=1,
        min_summary_cards=1,
        min_image_source_found=3,
        min_vision_model_called=1,
        require_vision_mode="ollama",
        require_vision_execution=True,
        min_clean_vision_observation_ready=3,
        max_prompt_leak_suspected=0,
        max_review_required=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )

    assert result["quality_status"] == "FAIL"
    assert "not enough clean vision observations" in result["failures"]
    assert "prompt leak suspected count exceeded" in result["failures"]
    assert "review-required visual observation count exceeded" in result["failures"]
