from tiff.trace_net_trust_authority_quality import run_quality


def test_quality_passes_for_expected_summary():
    summary = {
        "trust_authority_records": 1426,
        "missing_authority_records": 0,
        "missing_candidate_trust_tier": 0,
        "source_evidence_authority_records": 509,
        "source_text_authority_records": 495,
        "verified_part_authority_records": 362,
        "derived_context_authority_records": 60,
        "source_evidence_direct_answer_records": 0,
        "derived_context_direct_answer_records": 0,
        "derived_context_canonical_source_truth_records": 0,
        "unsafe_authority_records": 0,
        "missing_source_url_authority_records": 0,
        "source_truth_mutation_records": 0,
    }
    thresholds = {
        "min_authority_records": 1426,
        "max_missing_authority_records": 0,
        "max_missing_candidate_trust_tier": 0,
        "min_source_evidence_authority_records": 509,
        "min_source_text_authority_records": 495,
        "min_verified_part_authority_records": 360,
        "min_derived_context_authority_records": 60,
        "max_source_evidence_direct_answer_records": 0,
        "max_derived_context_direct_answer_records": 0,
        "max_derived_context_canonical_source_truth_records": 0,
        "max_unsafe_authority_records": 0,
        "max_missing_source_url_authority_records": 0,
        "max_source_truth_mutations": 0,
    }
    report = run_quality(summary, thresholds)
    assert report["status"] == "OK"


def test_quality_fails_if_derived_context_is_direct_answer():
    summary = {
        "trust_authority_records": 10,
        "missing_authority_records": 0,
        "missing_candidate_trust_tier": 0,
        "source_evidence_authority_records": 1,
        "source_text_authority_records": 1,
        "verified_part_authority_records": 1,
        "derived_context_authority_records": 1,
        "source_evidence_direct_answer_records": 0,
        "derived_context_direct_answer_records": 1,
        "derived_context_canonical_source_truth_records": 0,
        "unsafe_authority_records": 0,
        "missing_source_url_authority_records": 0,
        "source_truth_mutation_records": 0,
    }
    report = run_quality(summary, {"min_authority_records": 1, "max_derived_context_direct_answer_records": 0})
    assert report["status"] == "FAIL"
