from __future__ import annotations

import base64
import json
from pathlib import Path

from tiff.trace_net_e2e_image_visual_observer_route_v34_2 import (
    MODEL_ID,
    _extract_user_text_and_images,
    build_report,
    build_visual_package,
    evaluate_quality,
)


def test_extract_user_text_and_images_handles_openai_content_list() -> None:
    raw = base64.b64encode(b"fake image bytes").decode("ascii")
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Inspect this image."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{raw}"}},
                ],
            }
        ]
    }
    text, images = _extract_user_text_and_images(payload)
    assert text == "Inspect this image."
    assert len(images) == 1
    assert images[0]["base64"] == raw
    assert images[0]["mime_type"] == "image/png"


def test_build_visual_package_guidance_only_synthetic() -> None:
    pkg = build_visual_package(
        user_query="Does this image contain callouts?",
        synthetic_image_id="demo_image_001",
        synthetic_visual_type="callout_diagram_candidate",
    )
    assert pkg["query_intent"] == "uploaded_image_visual_inspection"
    assert pkg["final_gate_status"] == "VISUAL_FINAL_GATE_PASS"
    assert pkg["visual_proof_authority_violation_count"] == 0
    assert pkg["guidance_only_visual_card_count"] == 1
    assert pkg["source_truth_required_for_visual_claim_count"] == 1
    assert pkg["self_rag"]["source_truth_required_for_visual_claims"] is True
    assert pkg["crag"]["human_review_recommended"] is True
    assert "guidance only" in pkg["final_answer"].lower()


def test_missing_image_is_safe_audit_only() -> None:
    pkg = build_visual_package(user_query="Inspect this image for diagram callouts")
    assert pkg["query_intent"] == "image_visual_missing_upload"
    assert pkg["response_mode"] == "visual_audit_only_missing_image"
    assert pkg["crag_retry_required"] is True
    assert pkg["crag"]["fallback_safe"] is True
    assert "did not receive an image" in pkg["final_answer"]


def test_build_report_standard_demo_passes_quality(tmp_path: Path) -> None:
    report = build_report(
        output_dir=tmp_path,
        include_standard_demo_queries=True,
        llm_mode="simulate",
        port=8029,
    )
    assert report["quality_status"] == "PASS"
    assert report["sample_query_count"] == 4
    assert report["sample_success_count"] == 4
    assert report["visual_package_count"] == 4
    assert report["image_quality_card_count"] == 4
    assert report["visual_observation_card_count"] == 4
    assert report["llava_observer_card_count"] == 4
    assert report["guidance_only_visual_card_count"] == 4
    assert report["visual_proof_authority_violation_count"] == 0
    assert Path(report["report_path"]).exists()
    assert Path(report["records_jsonl_path"]).exists()
    assert Path(report["inspect_md_path"]).exists()


def test_evaluate_quality_thresholds_pass(tmp_path: Path) -> None:
    report = build_report(output_dir=tmp_path, include_standard_demo_queries=True)
    checks = evaluate_quality(
        report,
        min_sample_queries=4,
        min_sample_successes=4,
        min_visual_packages=4,
        min_image_quality_cards=4,
        min_visual_observation_cards=4,
        min_llava_observer_cards=4,
        min_guidance_only_visual_cards=4,
        min_self_rag_samples=4,
        min_crag_samples=4,
        max_visual_proof_authority_violations=0,
        max_unsupported_visual_claim_count=0,
        max_post_gate_issue_count=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_no_answer_permission=True,
    )
    assert all(c["passed"] for c in checks)


def test_model_id_is_v34() -> None:
    assert MODEL_ID == "trace-net-e2e-image-ocr-opencv-fusion-llava-v34-2"


def test_diagram_draft_request_returns_mermaid_and_json_card() -> None:
    pkg = build_visual_package(
        user_query="Turn this image into a diagram draft.",
        synthetic_image_id="demo_image_diagram_001",
        synthetic_visual_type="callout_diagram_candidate",
    )
    assert pkg["response_mode"] == "diagram_draft_guidance"
    assert pkg["diagram_draft_card_count"] == 1
    assert pkg["diagram_draft_guidance_only_count"] == 1
    card = pkg["diagram_draft_cards"][0]
    assert card["diagram_format"] == "mermaid_and_json"
    assert card["proof_authority"] is False
    assert "flowchart LR" in card["mermaid"]
    assert "```mermaid" in pkg["final_answer"]
    assert "not a verified technical drawing" in pkg["final_answer"]



def test_ocr_opencv_fusion_cards_are_added_to_visual_package() -> None:
    pkg = build_visual_package(
        user_query="Turn this image into a diagram draft.",
        synthetic_image_id="demo_image_fusion_001",
        synthetic_visual_type="callout_diagram_candidate",
    )
    assert pkg["ocr_text_card_count"] == 1
    assert pkg["opencv_layout_card_count"] == 1
    assert pkg["grounded_visual_package"] is True
    assert pkg["ocr_text_candidate_count"] >= 1
    assert pkg["opencv_layout_region_count"] >= 1
    assert "OCR/OpenCV-fused" in pkg["final_answer"]
    assert "OCR text candidates" in pkg["final_answer"]
    assert "Diagram draft generated from OCR/OpenCV-fused visual package" in pkg["final_answer"]


def test_diagram_draft_uses_ocr_opencv_grounding() -> None:
    pkg = build_visual_package(
        user_query="Turn this image into a diagram draft.",
        synthetic_image_id="demo_image_grounded_001",
        synthetic_visual_type="callout_diagram_candidate",
    )
    card = pkg["diagram_draft_cards"][0]
    assert card["diagram_type"] == "ocr_opencv_fused_visual_structure_draft"
    assert "ocr_text_candidates" in card["grounding_sources"]
    assert "opencv_layout_regions" in card["grounding_sources"]
    assert "Uploaded image" in card["mermaid"]
    assert "OCR text candidates" in card["mermaid"]
