from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_fishnet_router_hardening_policy_v1 import (
    PolicyThresholds,
    build_fishnet_router_hardening_policy,
    evaluate_record,
)


def _packet(path: Path) -> Path:
    payload = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "source_p000004",
                "current_route": "image_visual",
                "current_route_page_id": "t_p_120_1176_p000004",
                "fishnet_route_candidate": "normal_text",
                "fishnet_best_route_candidate_before_review": "normal_text",
                "fishnet_route_confidence": 0.93,
                "fishnet_ocr_text_length": 900,
                "fishnet_ocr_word_count": 120,
                "fishnet_ocr_word_box_count": 130,
                "fishnet_ocr_sample_text": "INTRODUCTION manual prose",
                "fishnet_route_scores": {"normal_text": 1.0, "table": 0.01},
                "fishnet_route_adjusted_scores": {"normal_text": 1.0, "table": 0.01},
                "agreement_status": "high_confidence_disagreement",
                "selection_reason": "high_confidence_disagreement",
                "overlay_candidates": ["overlay.png"],
                "route_change_authorized": False,
            },
            {
                "page_id": "source_p000008",
                "current_route": "table",
                "fishnet_route_candidate": "review_required",
                "fishnet_route_confidence": 0.0,
                "fishnet_ocr_text_length": 2100,
                "fishnet_ocr_word_box_count": 370,
                "fishnet_review_reason_codes": ["low_route_margin"],
            },
        ],
    }
    p = path / "review_packet.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_evaluate_record_selects_high_confidence_normal_text() -> None:
    record = {
        "current_route": "blank_candidate",
        "fishnet_route_candidate": "normal_text",
        "fishnet_route_confidence": 0.91,
        "fishnet_ocr_text_length": 1000,
        "fishnet_ocr_word_box_count": 150,
    }
    selected, reasons = evaluate_record(record, PolicyThresholds())
    assert selected is True
    assert "normal_text_review_promotion_candidate" in reasons


def test_evaluate_record_blocks_low_margin_review() -> None:
    record = {
        "current_route": "blank_candidate",
        "fishnet_route_candidate": "normal_text",
        "fishnet_route_confidence": 0.91,
        "fishnet_ocr_text_length": 1000,
        "fishnet_ocr_word_box_count": 150,
        "fishnet_review_reason_codes": ["low_route_margin"],
    }
    selected, reasons = evaluate_record(record, PolicyThresholds())
    assert selected is False
    assert "low_route_margin_not_auto_promotable" in reasons


def test_build_policy_outputs_safe_records(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    payload = build_fishnet_router_hardening_policy(
        review_packet_path=packet,
        output_dir=tmp_path / "out",
        thresholds=PolicyThresholds(),
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["policy_record_count"] == 1
    record = payload["records"][0]
    assert record["recommendation_type"] == "normal_text_review_promotion"
    assert record["route_change_authorized"] is False
    assert record["source_truth_mutation_allowed"] is False
    assert (tmp_path / "out" / "trace_net_fishnet_router_hardening_policy_v1.md").exists()
