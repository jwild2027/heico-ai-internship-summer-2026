from pathlib import Path

from tiff.trace_net_table_route_value_audit_lep_v4_preset_v1 import (
    LepV4AuditPreset,
    collect_counts,
    first_search_ready_values,
    inspect_report,
    render_markdown_inspect,
)


def sample_audit_report():
    return {
        "quality_status": "PASS",
        "summary": {
            "source_normalizer_record_count": 20,
            "source_normalized_table_value_record_count": 2108,
            "table_route_value_audit_record_count": 20,
            "audited_table_count": 19,
            "evidence_ready_table_count": 18,
            "review_required_table_count": 4,
            "high_context_ratio_table_count": 1,
            "promoted_table_value_evidence_record_count": 1499,
            "search_ready_evidence_record_count": 1499,
            "context_only_record_count": 33,
            "covered_part_number_promoted_count": 151,
            "manual_page_reference_promoted_count": 39,
            "page_rev_or_sequence_value_promoted_count": 80,
            "ipl_part_number_promoted_count": 767,
            "ipl_figure_item_or_quantity_promoted_count": 843,
            "ipl_text_promoted_count": 188,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "records": [
            {
                "search_ready": True,
                "page_id": "t_p_120_1176_p000005",
                "table_id": "table_0001",
                "field_name": "manual_page_reference",
                "normalized_value": "32-10-01",
                "raw_value": "32-10-01",
                "confidence": 0.91,
            },
            {"search_ready": False, "field_name": "lep_context", "normalized_value": "REV"},
        ],
    }


def test_preset_build_args_pin_lep_v4_thresholds():
    preset = LepV4AuditPreset()
    args = preset.build_args(Path("normalizer.json"), Path("out"))
    assert "--min-source-normalized-records" in args
    index = args.index("--min-source-normalized-records")
    assert args[index + 1] == "1800"
    assert "--max-context-ratio" in args
    assert args[args.index("--max-context-ratio") + 1] == "0.75"
    assert "--quality" in args


def test_collect_counts_from_nested_audit_report():
    counts = collect_counts(sample_audit_report())
    assert counts["source_normalized_table_value_record_count"] == 2108
    assert counts["high_context_ratio_table_count"] == 1
    assert counts["search_ready_evidence_record_count"] == 1499
    assert counts["answer_permission_count"] == 0


def test_inspect_report_passes_and_preserves_watch_counters():
    inspection = inspect_report(sample_audit_report(), LepV4AuditPreset())
    assert inspection["quality_status"] == "PASS"
    assert inspection["watch_counters"]["high_context_ratio_table_count"] == 1
    assert inspection["promoted_fields"]["ipl_part_number"] == 767
    assert inspection["first_search_ready_values"][0]["field_name"] == "manual_page_reference"


def test_first_search_ready_values_is_compact_and_limited():
    values = first_search_ready_values(sample_audit_report(), limit=1)
    assert len(values) == 1
    assert "page_id" in values[0]
    assert "field_name" in values[0]


def test_render_markdown_inspect_contains_key_sections():
    inspection = inspect_report(sample_audit_report(), LepV4AuditPreset())
    text = render_markdown_inspect(inspection)
    assert "Watch counters" in text
    assert "Promoted fields" in text
    assert "Safety/write counters" in text
    assert "manual_page_reference" in text
