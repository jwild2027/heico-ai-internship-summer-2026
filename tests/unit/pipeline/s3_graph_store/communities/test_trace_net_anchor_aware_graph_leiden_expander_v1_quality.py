import json
from pathlib import Path

from tiff.trace_net_anchor_aware_graph_leiden_expander_v1 import check_anchor_aware_graph_leiden_expander_quality


def test_quality_checker_passes_good_report(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "anchor_aware_record_count": 3,
            "direct_exact_anchor_count": 1,
            "anchor_community_count": 1,
            "same_anchor_leiden_community_count": 1,
            "citation_count": 3,
            "context_prompt_char_count": 900,
            "violation_record_count": 0,
            "source_quality_statuses": {"anchor_injector": "PASS", "leiden_communities": "PASS"},
            "ready_for_gemma_anchor_aware_prompt": True,
            "human_review_required_count": 0,
            "manual_review_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
        },
    }), encoding="utf-8")
    result = check_anchor_aware_graph_leiden_expander_quality(
        report_path=path,
        write_json=True,
        min_records=1,
        min_direct_anchors=1,
        min_anchor_communities=1,
        min_same_anchor_relations=1,
        min_citations=1,
        min_prompt_chars=500,
        require_source_quality_pass=True,
        require_anchor_aware_prompt=True,
        require_no_human_review_required=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"
    assert path.with_name("trace_net_anchor_aware_graph_leiden_expander_v1_quality_check.json").exists()


def test_quality_checker_fails_missing_anchor_community(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "anchor_aware_record_count": 3,
            "direct_exact_anchor_count": 1,
            "anchor_community_count": 0,
            "same_anchor_leiden_community_count": 0,
            "citation_count": 3,
            "context_prompt_char_count": 900,
            "violation_record_count": 0,
            "source_quality_statuses": {"anchor_injector": "PASS"},
            "ready_for_gemma_anchor_aware_prompt": True,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
        }
    }), encoding="utf-8")
    result = check_anchor_aware_graph_leiden_expander_quality(
        report_path=path,
        min_anchor_communities=1,
        min_same_anchor_relations=1,
    )
    assert result["quality_status"] == "FAIL"
    assert "min_anchor_communities" in result["failures"]
