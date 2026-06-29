import json
from pathlib import Path

from tiff.trace_net_webui_visual_context_bridge_v1 import build_webui_visual_context_bridge


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
        "ocr_label_support_count": 2,
        "unsupported_visual_label_count": 0,
        "semantic_validation": {
            "ocr_supported_visual_terms": ["Passenger Seats", "Component Maintenance Manual"],
            "unsupported_visual_labels": [],
        },
        "visual_observation": {
            "visual_page_type": "technical manual",
            "summary": "Passenger Seats manual cover page.",
            "visible_text_or_labels": ["Passenger Seats"],
            "visible_callouts": [],
            "observed_visual_features": ["text", "illustrations"],
            "uncertainty_flags": ["vision_derived_guidance_not_source_truth"],
        },
    }


def test_builds_bridge_with_only_allowed_cards(tmp_path: Path):
    source = _write(
        tmp_path / "image_visual_summary.json",
        {
            "quality_status": "PASS",
            "summary": {
                "image_visual_handoff_count": 12,
                "webui_visual_context_allowed_count": 1,
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
            },
            "records": [
                _allowed(),
                {**_allowed("t_p_120_1176_p000015"), "webui_visual_context_allowed": False, "semantic_validation_status": "REVIEW_ONLY_VISUAL_CONTEXT", "semantic_validation": {"semantic_review_reasons": ["unsupported_visual_labels_present"]}},
            ],
        },
    )
    payload = build_webui_visual_context_bridge(image_visual_summary_path=source, output_dir=tmp_path / "out")
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["visual_context_card_count"] == 1
    assert payload["summary"]["review_only_visual_context_excluded_count"] == 1
    assert payload["records"][0]["page_id"] == "t_p_120_1176_p000001"
    assert payload["records"][0]["context_authority"] == "vision_derived_retrieval_guidance_not_source_truth"
    assert payload["records"][0]["answer_permission"] is False
    assert (tmp_path / "out" / "trace_net_webui_visual_context_bridge_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_webui_visual_context_bridge_v1_context_cards.jsonl").exists()


def test_rejects_allowed_flag_with_bad_semantic_status(tmp_path: Path):
    bad = {**_allowed(), "semantic_validation_status": "REVIEW_ONLY_VISUAL_CONTEXT"}
    source = _write(tmp_path / "source.json", {"quality_status": "PASS", "summary": {}, "records": [bad]})
    payload = build_webui_visual_context_bridge(image_visual_summary_path=source, output_dir=tmp_path / "out")
    assert payload["summary"]["visual_context_card_count"] == 0
    assert payload["summary"]["review_only_visual_context_excluded_count"] == 1


def test_nested_output_directories_are_created(tmp_path: Path):
    source = _write(tmp_path / "source.json", {"quality_status": "PASS", "summary": {}, "records": [_allowed()]})
    nested = tmp_path / "a" / "b" / "c" / "bridge"
    payload = build_webui_visual_context_bridge(image_visual_summary_path=source, output_dir=nested)
    assert payload["quality_status"] == "PASS"
    assert (nested / "trace_net_webui_visual_context_bridge_v1_summary.json").exists()
