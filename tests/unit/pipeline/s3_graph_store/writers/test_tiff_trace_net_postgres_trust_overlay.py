from tiff.trace_net_postgres_trust_overlay import derive_trust_tier, derive_rag_action, normalize_bool


def test_explicit_trust_tier_wins():
    assert derive_trust_tier(explicit="B", rag_bucket="source_evidence", usable_confidence=0.9) == "B"


def test_source_and_verified_fallbacks_are_a():
    assert derive_trust_tier(rag_bucket="source_evidence") == "A"
    assert derive_trust_tier(rag_bucket="verified_part_evidence") == "A"


def test_derived_context_uses_confidence_thresholds():
    assert derive_trust_tier(rag_bucket="derived_context", usable_confidence=0.881) == "A"
    assert derive_trust_tier(rag_bucket="derived_context", usable_confidence=0.755) == "B"
    assert derive_trust_tier(rag_bucket="derived_context", usable_confidence=0.5) == "B"


def test_rag_action_fallbacks():
    assert derive_rag_action(rag_bucket="source_evidence") == "include_as_source_evidence"
    assert derive_rag_action(rag_bucket="source_text_evidence") == "include_as_source_text_evidence"
    assert derive_rag_action(rag_bucket="verified_part_evidence") == "include_as_verified_part_evidence"
    assert derive_rag_action(rag_bucket="derived_context") == "include_as_derived_context"


def test_normalize_bool():
    assert normalize_bool("true") is True
    assert normalize_bool("false") is False
    assert normalize_bool(None, default=False) is False
