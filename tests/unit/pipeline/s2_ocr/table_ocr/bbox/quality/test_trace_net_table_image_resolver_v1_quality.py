from __future__ import annotations

from tiff.trace_net_table_image_resolver_v1_quality import check_report


def test_quality_passes_safe_unresolved_when_min_resolved_zero() -> None:
    report = {
        "summary": {
            "schema_version": "trace_net_table_image_resolver_v1",
            "source_quality_status": "PASS",
            "source_table_geometry_card_count": 1,
            "resolver_card_count": 1,
            "resolved_image_card_count": 0,
            "unsafe_resolution_card_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    quality = check_report(
        report,
        {
            "min_source_cards": 1,
            "min_resolver_cards": 1,
            "min_resolved_image_cards": 0,
            "max_unsafe_resolution_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert quality["quality_status"] == "PASS"


def test_quality_fails_when_resolved_count_required() -> None:
    report = {
        "summary": {
            "schema_version": "trace_net_table_image_resolver_v1",
            "source_quality_status": "PASS",
            "source_table_geometry_card_count": 1,
            "resolver_card_count": 1,
            "resolved_image_card_count": 0,
            "unsafe_resolution_card_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    quality = check_report(report, {"min_source_cards": 1, "min_resolver_cards": 1, "min_resolved_image_cards": 1})
    assert quality["quality_status"] == "FAIL"
    assert "min_resolved_image_cards_met" in quality["quality_errors"]
