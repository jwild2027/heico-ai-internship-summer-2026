from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path("scripts/serve_trace_net_gated_visual_live_endpoint_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("gated_visual_live_endpoint", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sample_docs() -> tuple[list[dict], list[dict]]:
    confirmed = [
        {
            "document_id": "doc1",
            "page_id": "p001",
            "search_ready": True,
            "review_only": False,
            "visual_route": "image_visual",
            "visual_subtype": "confirmed_diagram_dominant",
            "route_confidence": 0.8,
            "visual_summaries": ["Technical drawing showing passenger seat assembly callouts."],
            "identifiers": {
                "part_numbers": ["120-12345-001"],
                "figure_refs": ["figure 601"],
                "callouts": ["1", "2"],
                "nomenclature": ["seat assembly"],
            },
            "search_text": "passenger seat assembly diagram callout figure 601 part 120-12345-001",
            "citation_ready": True,
            "source_trace_ready": True,
        }
    ]
    review_only = [
        {
            "document_id": "review1",
            "page_id": "p999",
            "search_ready": False,
            "review_only": True,
            "visual_route": "visual_candidate_review",
            "visual_subtype": "borderline_old_image_visual",
            "search_text": "passenger seat assembly review only should not be used",
        }
    ]
    return confirmed, review_only


def test_visual_endpoint_logic_excludes_review_only_and_preserves_safety() -> None:
    mod = load_module()
    docs, review = sample_docs()
    endpoint = mod.VisualEndpoint(docs=docs, review_docs=review, top_k=8, min_score=0.001)

    health = endpoint.health()
    assert health["status"] == "ok"
    assert health["retrieval_document_count"] == 1
    assert health["review_only_document_count"] == 1
    assert health["answer_permission"] is False
    assert health["does_not_call_ollama"] is True

    ask = endpoint.ask_response("Find the passenger seat assembly diagram with callouts")
    assert ask["status"] == "ok"
    assert ask["final_answer_allowed"] is False
    assert ask["answer_permission"] is False
    assert ask["route_context"]["route_triggered"] is True
    assert ask["route_context"]["citation_count"] == 1
    assert ask["route_context"]["citations"][0]["page_id"] == "p001"
    assert all(c["page_id"] != "p999" for c in ask["route_context"]["citations"])
    assert "Answer permission: false" in ask["content"]


def test_visual_endpoint_chat_and_nonvisual_query() -> None:
    mod = load_module()
    docs, review = sample_docs()
    endpoint = mod.VisualEndpoint(docs=docs, review_docs=review, top_k=8, min_score=0.001)

    chat = endpoint.chat_response(
        {
            "model": "trace-net-gated-visual-live-endpoint-v1",
            "messages": [
                {"role": "user", "content": "Show figure references for passenger seat assembly diagram"}
            ],
        }
    )
    assert chat["choices"][0]["message"]["role"] == "assistant"
    assert chat["trace_net"]["route_context"]["citation_count"] == 1
    assert chat["trace_net"]["response_is_final_answer"] is False

    nonvisual = endpoint.build_payload("What is the torque limit")
    assert nonvisual["route_triggered"] is False
    assert nonvisual["context_pack_status"] == "visual_route_not_triggered"
    assert nonvisual["citation_count"] == 0
    assert nonvisual["answer_contract"]["final_answer_allowed"] is False
