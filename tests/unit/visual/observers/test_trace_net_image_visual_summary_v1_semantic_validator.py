import json
from pathlib import Path

from tiff.trace_net_image_visual_summary_v1 import (
    _validate_visual_observation_semantics,
    check_image_visual_summary_quality,
)


def test_semantic_validator_allows_ocr_supported_low_risk_visual_context():
    observation = {
        "visible_text_or_labels": ["Passenger Seats", "Component Maintenance Manual"],
        "visible_callouts": ["25-21-00"],
        "observed_visual_features": ["technical manual cover"],
        "summary": "Passenger seats component maintenance manual cover page.",
    }
    result = _validate_visual_observation_semantics(
        visual_observation=observation,
        ocr_text="Passenger Seats Component Maintenance Manual with Illustrated Parts List ATA 25-21-00",
        execution_status="vision_model_observation_ready",
        prompt_leak_suspected=False,
        vision_error=None,
    )
    assert result["webui_visual_context_allowed"] is True
    assert result["semantic_validation_status"] == "WEBUI_VISUAL_CONTEXT_ALLOWED"
    assert result["hallucination_risk_status"] == "LOW_SUPPORTED_BY_OCR"
    assert result["ocr_label_support_count"] >= 2


def test_semantic_validator_blocks_invented_item_sequence():
    observation = {
        "visible_text_or_labels": [f"Item {i}" for i in range(1, 100)],
        "visible_callouts": [],
        "observed_visual_features": ["text on page"],
        "summary": "A page with many items.",
    }
    result = _validate_visual_observation_semantics(
        visual_observation=observation,
        ocr_text="Passenger Seats Component Maintenance Manual",
        execution_status="vision_model_observation_ready",
        prompt_leak_suspected=False,
        vision_error=None,
    )
    assert result["webui_visual_context_allowed"] is False
    assert result["hallucination_risk_status"] == "HIGH_REVIEW_REQUIRED"
    assert result["invented_item_sequence_suspected"] is True
    assert "invented_item_sequence_suspected" in result["semantic_review_reasons"]


def test_semantic_quality_gate_can_require_webui_allowed_cards(tmp_path: Path):
    report = {
        "quality_status": "PASS",
        "summary": {
            "source_route_dispatch_handoff_quality_status": "PASS",
            "image_visual_handoff_count": 12,
            "visual_summary_card_count": 12,
            "image_source_found_count": 12,
            "vision_model_called_count": 12,
            "vision_observation_ready_count": 11,
            "clean_vision_observation_ready_count": 11,
            "prompt_leak_suspected_count": 0,
            "review_required_visual_observation_count": 1,
            "semantic_validation_status_counts": {"WEBUI_VISUAL_CONTEXT_ALLOWED": 4, "REVIEW_ONLY_VISUAL_CONTEXT": 8},
            "hallucination_risk_status_counts": {"LOW_SUPPORTED_BY_OCR": 4, "MEDIUM_REVIEW_REQUIRED": 8},
            "webui_visual_context_allowed_count": 4,
            "invented_item_sequence_suspected_count": 0,
            "excessive_visual_label_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "vision_mode": "ollama",
        },
    }
    path = tmp_path / "trace_net_image_visual_summary_v1.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    passed = check_image_visual_summary_quality(
        report_path=path,
        require_source_route_dispatch_quality_pass=True,
        min_summary_cards=12,
        min_image_source_found=12,
        min_vision_model_called=12,
        require_vision_mode="ollama",
        require_vision_execution=True,
        min_clean_vision_observation_ready=1,
        min_webui_visual_context_allowed=3,
        require_semantic_validation=True,
        max_hallucination_high=0,
        max_invented_item_sequence_suspected=0,
        max_excessive_visual_label_count=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert passed["quality_status"] == "PASS"

    failed = check_image_visual_summary_quality(
        report_path=path,
        min_webui_visual_context_allowed=5,
        require_semantic_validation=True,
    )
    assert failed["quality_status"] == "FAIL"
    assert "not enough WebUI-allowed visual context cards" in failed["failures"]
