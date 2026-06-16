from tiff.trace_net_page_query_response_source_cross_reference_v1 import quality_checks


def test_quality_checks_fail_on_checksum_mismatch():
    summary = {
        "record_count": 1,
        "response_count": 1,
        "zip_entry_resolved_count": 1,
        "mets_file_entry_resolved_count": 1,
        "checksum_verified_count": 0,
        "size_match_count": 1,
        "checksum_mismatch_count": 1,
        "missing_zip_entry_count": 0,
        "missing_mets_entry_count": 0,
        "wrong_source_entry_count": 0,
        "unsafe_response_count": 0,
        "answer_capable_response_count": 0,
        "claim_proof_response_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "metadata_xml_present": True,
        "source_dataset_quality_status": "PASS",
    }
    status, checks = quality_checks(summary, {"max_checksum_mismatches": 0, "require_dataset_quality_pass": True, "require_metadata_xml": True})
    assert status == "FAIL"
    assert any(c["name"] == "checksum_mismatch_count" and not c["ok"] for c in checks)


def test_quality_checks_pass_for_clean_summary():
    summary = {
        "record_count": 2,
        "response_count": 2,
        "zip_entry_resolved_count": 2,
        "mets_file_entry_resolved_count": 2,
        "checksum_verified_count": 2,
        "size_match_count": 2,
        "response_page_anchor_count": 2,
        "response_source_entry_anchor_count": 2,
        "blank_answer_cross_reference_count": 1,
        "checksum_mismatch_count": 0,
        "missing_zip_entry_count": 0,
        "missing_mets_entry_count": 0,
        "wrong_source_entry_count": 0,
        "unsafe_response_count": 0,
        "answer_capable_response_count": 0,
        "claim_proof_response_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "metadata_xml_present": True,
        "source_dataset_quality_status": "PASS",
    }
    status, _ = quality_checks(
        summary,
        {
            "min_records": 2,
            "min_responses": 2,
            "min_zip_entry_resolved": 2,
            "min_mets_file_entry_resolved": 2,
            "min_checksum_verified": 2,
            "min_size_matches": 2,
            "min_response_page_anchors": 2,
            "min_response_source_entry_anchors": 2,
            "min_blank_answer_cross_references": 1,
            "max_checksum_mismatches": 0,
            "max_missing_zip_entries": 0,
            "max_missing_mets_entries": 0,
            "max_wrong_source_entries": 0,
            "require_dataset_quality_pass": True,
            "require_metadata_xml": True,
            "require_no_answer_permission": True,
        },
    )
    assert status == "PASS"
