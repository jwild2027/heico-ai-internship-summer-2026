from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json

from tiff.trace_net_answer_context_evidence_enricher_v1 import check_quality


def test_quality_passes_for_enriched_report(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "enriched_context_record_count": 2,
            "enriched_excerpt_count": 2,
            "citation_count": 2,
            "context_prompt_char_count": 500,
            "violation_record_count": 0,
            "source_context_pack_quality_status": "PASS",
            "source_ocr_route_scan_pack_quality_status": "PASS",
            "human_review_required_count": 0,
            "manual_review_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "llm_context_prompt": "x" * 500,
    }), encoding="utf-8")
    result = check_quality(
        report_path=report,
        min_records=1,
        min_enriched_excerpts=1,
        min_citations=1,
        min_prompt_chars=200,
        require_source_quality_pass=True,
        require_enriched_prompt=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_fails_on_violations(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {
            "enriched_context_record_count": 1,
            "enriched_excerpt_count": 1,
            "citation_count": 1,
            "context_prompt_char_count": 300,
            "violation_record_count": 1,
        },
        "llm_context_prompt": "x" * 300,
    }), encoding="utf-8")
    result = check_quality(report_path=report, max_violation_records=0)
    assert result["quality_status"] == "FAIL"
    assert "max_violation_records" in result["quality_check_failures"]
