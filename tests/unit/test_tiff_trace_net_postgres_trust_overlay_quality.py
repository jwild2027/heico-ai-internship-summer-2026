from tiff.trace_net_postgres_trust_overlay_quality import run_quality


def test_quality_passes_expected_summary():
    summary = {
        "pages": 509,
        "trust_overlay_records": 6478,
        "page_trust_trait_records": 1000,
        "pages_with_trust_traits": 509,
        "rag_candidate_records": 1426,
        "rag_candidate_missing_trust_tier": 0,
        "source_trace_A_records": 509,
        "source_text_A_records": 495,
        "verified_part_A_records": 362,
        "derived_context_records": 60,
        "unsafe_trusted_rag_records": 0,
        "source_truth_mutation_records": 0,
    }
    report = run_quality(summary, {
        "min_pages": 509,
        "min_trust_records": 1426,
        "min_page_trust_traits": 509,
        "min_source_trace_A_records": 509,
        "min_verified_part_A_records": 360,
        "min_derived_context_records": 60,
        "max_missing_candidate_trust_tier": 0,
        "max_unsafe_trusted_rag_records": 0,
        "max_source_truth_mutations": 0,
    })
    assert report["status"] == "OK"


def test_quality_fails_missing_candidate_trust():
    summary = {
        "pages": 509,
        "trust_overlay_records": 1426,
        "page_trust_trait_records": 509,
        "pages_with_trust_traits": 509,
        "rag_candidate_missing_trust_tier": 1426,
        "source_trace_A_records": 509,
        "verified_part_A_records": 362,
        "derived_context_records": 60,
        "unsafe_trusted_rag_records": 0,
        "source_truth_mutation_records": 0,
    }
    report = run_quality(summary, {"max_missing_candidate_trust_tier": 0})
    assert report["status"] == "FAIL"
    assert any(c["name"] == "missing_candidate_trust_tier" and c["status"] == "FAIL" for c in report["checks"])
