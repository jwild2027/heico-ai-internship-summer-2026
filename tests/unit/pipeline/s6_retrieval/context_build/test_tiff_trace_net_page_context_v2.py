from tiff.trace_net_page_context_v2 import (
    default_authority,
    heuristic_context_v2,
    sanitize_context_v2,
    extract_json_from_text,
    normalize_list,
)


def test_default_authority_is_retrieval_helper_only():
    auth = default_authority()
    assert auth["rag_role"] == "retrieval_helper"
    assert auth["can_answer_directly"] is False
    assert auth["can_support_answer"] is True
    assert auth["canonical_source_truth"] is False
    assert auth["requires_citation"] is True


def test_heuristic_context_v2_builds_specific_seat_cues():
    rec = heuristic_context_v2({
        "page_id": "t_p_120_1176_p000015",
        "ocr_text": "PASSENGER SEAT seat bottom backrest armrest snack table upholstery frame",
        "source_url": "http://example/source",
        "v1_context": {"role": "parts_list", "summary": "Passenger seat design description", "topics": ["passenger seat"]},
    })
    cues = {x.lower() for x in rec["retrieval_cues"]}
    assert "passenger seat" in cues
    assert "backrest" in cues
    assert "snack table" in cues
    assert rec["authority"]["can_answer_directly"] is False
    assert rec["authority"]["canonical_source_truth"] is False


def test_sanitize_context_v2_overrides_unsafe_llm_authority():
    data = {
        "page_id": "p1",
        "role": "parts_list",
        "authority": {"can_answer_directly": True, "canonical_source_truth": True, "requires_citation": False},
        "retrieval_cues": ["seat"],
        "answerable_questions": ["Where is the seat?"],
    }
    rec = sanitize_context_v2(data, {"page_id": "p1"})
    assert rec["authority"]["can_answer_directly"] is False
    assert rec["authority"]["canonical_source_truth"] is False
    assert rec["authority"]["requires_citation"] is True


def test_extract_json_from_text_handles_markdown_fence():
    data = extract_json_from_text('```json\n{"page_id":"p1","role":"figure"}\n```')
    assert data["page_id"] == "p1"
    assert data["role"] == "figure"


def test_normalize_list_deduplicates():
    assert normalize_list([" Seat ", "seat", {"name": "Backrest"}]) == ["Seat", "Backrest"]
