import json
from pathlib import Path

from tiff.trace_net_webui_visual_context_bridge_v1 import (
    build_webui_visual_context_bridge,
    check_webui_visual_context_bridge_quality,
)


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _allowed(page_id="t_p_120_1176_p000001"):
    return {
        "page_id": page_id,
        "canonical_page_number": 1,
        "accepted_route": "image_visual",
        "image_path": "local_data/page.tif",
        "vision_mode": "ollama",
        "vision_model": "llava:13b",
        "visual_model_execution_status": "vision_model_observation_ready",
        "visual_observation_quality_status": "CLEAN_VISION_OBSERVATION_READY",
        "semantic_validation_status": "WEBUI_VISUAL_CONTEXT_ALLOWED",
        "hallucination_risk_status": "LOW_SUPPORTED_BY_OCR",
        "webui_visual_context_allowed": True,
        "prompt_leak_suspected": False,
        "invented_item_sequence_suspected": False,
        "excessive_visual_label_count": False,
        "visual_summary_text": "Passenger Seats manual cover page.",
        "semantic_validation": {"ocr_supported_visual_terms": ["Passenger Seats"]},
        "visual_observation": {"visual_page_type": "technical manual", "visible_text_or_labels": ["Passenger Seats"]},
    }


def test_quality_check_passes_for_allowed_visual_context(tmp_path: Path):
    source = _write(
        tmp_path / "source.json",
        {"quality_status": "PASS", "summary": {}, "records": [_allowed(), {**_allowed("x"), "webui_visual_context_allowed": False}]},
    )
    report = build_webui_visual_context_bridge(image_visual_summary_path=source, output_dir=tmp_path / "out")
    result = check_webui_visual_context_bridge_quality(
        report_path=tmp_path / "out" / "trace_net_webui_visual_context_bridge_v1.json",
        min_source_records=2,
        min_context_cards=1,
        min_excluded_records=1,
        require_source_quality_pass=True,
        require_only_webui_allowed=True,
        require_review_only_excluded=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        max_unsafe=0,
    )
    assert report["quality_status"] == "PASS"
    assert result["quality_status"] == "PASS"


def test_quality_check_reports_failure_when_no_context_cards(tmp_path: Path):
    source = _write(
        tmp_path / "source.json",
        {"quality_status": "PASS", "summary": {}, "records": [{**_allowed(), "webui_visual_context_allowed": False}]},
    )
    build_webui_visual_context_bridge(image_visual_summary_path=source, output_dir=tmp_path / "out")
    result = check_webui_visual_context_bridge_quality(
        report_path=tmp_path / "out" / "trace_net_webui_visual_context_bridge_v1.json",
        min_context_cards=1,
    )
    assert result["quality_status"] == "FAIL"
    assert result["failures"]
