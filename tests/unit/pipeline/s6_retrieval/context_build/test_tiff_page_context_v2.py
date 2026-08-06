from tiff.page_context_v2 import build_fallback_card, enforce_card_schema, make_prompt, normalize_contexts, AUTHORITY


def test_normalize_contexts_mapping():
    raw = {"p1": {"role": "parts_list", "summary": "Parts"}}
    rows = normalize_contexts(raw)
    assert rows[0]["page_id"] == "p1"


def test_fallback_card_has_retrieval_guidance_and_safe_authority():
    ctx = {"page_id": "t_p_120_1176_p000015", "role": "parts_list", "summary": "Passenger seat armrest snack table backrest", "topics": ["passenger seat"]}
    card = build_fallback_card(ctx, "PASSENGER SEAT ARMREST SNACK TABLE BACKREST", None, None)
    assert card["retrieval_cues"]
    assert card["answerable_questions"]
    assert card["authority"]["can_answer_directly"] is False
    assert card["authority"]["canonical_source_truth"] is False
    assert card["authority"]["requires_citation"] is True


def test_enforce_schema_overrides_model_authority():
    card = enforce_card_schema({"page_id": "p", "authority": {"can_answer_directly": True, "canonical_source_truth": True}}, {"page_id": "p"})
    assert card["authority"]["can_answer_directly"] is False
    assert card["authority"]["canonical_source_truth"] is False


def test_prompt_contains_required_card_fields():
    prompt = make_prompt({"page_id": "p", "role": "parts_list", "summary": "summary"}, "ocr text", None, None)
    assert "answerable_questions" in prompt
    assert "retrieval_cues" in prompt
    assert "not canonical source truth" in prompt.lower() or "canonical_source_truth" in prompt
