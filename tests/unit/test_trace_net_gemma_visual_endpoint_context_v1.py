from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path("scripts/build_trace_net_gemma_visual_endpoint_context_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("gemma_visual_endpoint_v1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gemma_visual_endpoint_v1"] = mod
    spec.loader.exec_module(mod)
    return mod


def sample_doc():
    return {
        "document_id": "confirmed_image_gemma_visual_card_clean::p1",
        "page_id": "p1",
        "route_name": "confirmed_image_gemma_visual_card_clean",
        "retrieval_text": "technical_diagram | Chair with a backrest and armrests | figures: figure 3 | callouts: Armrest on the chair, 3",
        "structured_visual_card": {
            "normalized_visual_page_type": "technical_diagram",
            "normalized_subject": "Chair with a backrest and armrests",
            "figure_refs": ["figure 3"],
            "part_numbers": [],
            "visible_callouts": ["Armrest on the chair", "3"],
            "evidence_use": "Use for retrieval. This is not final proof.",
            "uncertainty_notes": "Small text unclear.",
            "confidence": "medium",
            "retrieval_keywords": ["chair", "technical diagram", "figure 3"],
        },
        "safety_contract": {
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        },
    }


def test_visual_query_returns_context_payload() -> None:
    mod = load_module()
    payload = mod.build_payload_for_query(
        "Show figure references for chair diagram",
        [sample_doc()],
        top_k=4,
        min_score=0.001,
    )

    assert payload["route_triggered"] is True
    assert payload["route_name"] == "gemma_confirmed_image_visual"
    assert payload["citation_count"] == 1
    assert payload["citations"][0]["citation_type"] == "gemma_confirmed_image_visual_context"
    assert payload["answer_contract"]["final_answer_allowed"] is False
    assert payload["answer_contract"]["answer_permission"] is False


def test_nonvisual_query_does_not_trigger() -> None:
    mod = load_module()
    payload = mod.build_payload_for_query(
        "Find part number 120-41824-003",
        [sample_doc()],
        top_k=4,
        min_score=0.001,
    )

    assert payload["route_triggered"] is False
    assert payload["citation_count"] == 0
    assert payload["context_pack_status"] == "visual_route_not_triggered"


def test_validate_clean_doc_rejects_prompt_leak_and_safety_true() -> None:
    mod = load_module()
    doc = sample_doc()
    doc["retrieval_text"] += " TRACE-Net's visual observation specialist"
    doc["safety_contract"]["answer_permission"] = True

    ok, failures = mod.validate_clean_doc(doc)

    assert ok is False
    assert "prompt_leak_detected" in failures
    assert "safety_true:answer_permission" in failures
