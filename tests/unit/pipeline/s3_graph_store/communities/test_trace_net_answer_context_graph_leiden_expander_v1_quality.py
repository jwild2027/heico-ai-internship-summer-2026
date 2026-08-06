import json
from pathlib import Path

from tiff.trace_net_answer_context_graph_leiden_expander_v1 import check_quality


def test_quality_passes_for_good_report(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "graph_expanded_context_record_count": 2,
            "citation_count": 2,
            "context_prompt_char_count": 1000,
            "community_annotation_count": 2,
            "graph_relation_annotation_count": 2,
            "violation_record_count": 0,
            "source_evidence_enricher_quality_status": "PASS",
            "human_review_required_count": 0,
            "manual_review_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "write_attempt_count": 0,
        },
        "llm_context_prompt": "x" * 1000,
    }), encoding="utf-8")
    result = check_quality(
        report_path=report,
        min_records=1,
        min_community_annotations=1,
        min_graph_relation_annotations=1,
        require_source_quality_pass=True,
        require_graph_prompt=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_fails_when_graph_annotations_missing(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "graph_expanded_context_record_count": 2,
            "citation_count": 2,
            "context_prompt_char_count": 1000,
            "community_annotation_count": 0,
            "graph_relation_annotation_count": 0,
            "violation_record_count": 0,
        },
        "llm_context_prompt": "x" * 1000,
    }), encoding="utf-8")
    result = check_quality(report_path=report, min_community_annotations=1, min_graph_relation_annotations=1)
    assert result["quality_status"] == "FAIL"
    assert "min_community_annotations" in result["quality_check_failures"]
