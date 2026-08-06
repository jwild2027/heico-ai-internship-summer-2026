from tiff.trace_net_trust_authority import derive_authority, build_authority_records


def test_source_evidence_is_source_truth_but_not_direct_answer():
    auth = derive_authority({"rag_bucket": "source_evidence", "evidence_layer": "source_trace", "trust_tier": "A", "safe_for_rag": True})
    assert auth["trust_scope"] == "source_trace"
    assert auth["evidence_authority"] == "source_truth"
    assert auth["claim_authority"] == "source_exists_only"
    assert auth["can_answer_directly"] is False
    assert auth["can_support_answer"] is True
    assert auth["canonical_source_truth"] is True
    assert auth["source_truth_mutation_allowed"] is False


def test_source_text_can_answer_with_citation():
    auth = derive_authority({"rag_bucket": "source_text_evidence", "evidence_layer": "source_text", "trust_tier": "A", "safe_for_rag": True})
    assert auth["trust_scope"] == "source_text"
    assert auth["evidence_authority"] == "source_backed_ocr_text"
    assert auth["claim_authority"] == "ocr_text_claim_with_citation"
    assert auth["can_answer_directly"] is True
    assert auth["requires_citation"] is True
    assert auth["requires_source_trace"] is True


def test_verified_part_can_support_part_claims():
    auth = derive_authority({"rag_bucket": "verified_part_evidence", "evidence_layer": "part_catalog", "trust_tier": "A", "safe_for_rag": True})
    assert auth["trust_scope"] == "part_catalog"
    assert auth["evidence_authority"] == "verified_part_reference"
    assert auth["claim_authority"] == "part_page_relationship"
    assert auth["can_answer_directly"] is True


def test_derived_context_is_not_direct_or_canonical():
    auth = derive_authority({"rag_bucket": "derived_context", "evidence_layer": "table_tile_text_refined", "trust_tier": "A", "safe_for_rag": True})
    assert auth["trust_scope"] == "table_tile_text_refined"
    assert auth["evidence_authority"] == "derived_context"
    assert auth["claim_authority"] == "supporting_context_only"
    assert auth["can_answer_directly"] is False
    assert auth["can_support_answer"] is True
    assert auth["canonical_source_truth"] is False


def test_unsafe_candidate_is_not_answer_capable():
    auth = derive_authority({"rag_bucket": "source_text_evidence", "evidence_layer": "source_text", "trust_tier": "D", "safe_for_rag": False})
    assert auth["can_answer_directly"] is False
    assert auth["can_support_answer"] is False
    assert auth["rag_role"] == "excluded_or_review_only"


def test_build_authority_records_adds_ids():
    rows = [
        {"candidate_id": "c1", "page_id": "p1", "rag_bucket": "source_text_evidence", "evidence_layer": "source_text", "trust_tier": "A", "safe_for_rag": True, "source_url": "http://x", "payload": {}},
    ]
    records = build_authority_records(rows)
    assert len(records) == 1
    rec = records[0]
    assert rec["authority_id"].startswith("trust_authority:")
    assert rec["candidate_id"] == "c1"
    assert rec["can_answer_directly"] is True
