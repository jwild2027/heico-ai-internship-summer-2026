import json
from pathlib import Path

from tiff.trace_net_raw_to_answer_context_engineered_native_v1 import check_quality


def test_quality_fails_when_anchor_missing(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"quality_status": "PASS", "summary": {"stage_report_count": 12, "postgres_contract_ready_count": 509, "qdrant_contract_ready_count": 450, "opensearch_contract_ready_count": 282, "qdrant_payload_count": 450, "opensearch_payload_count": 282, "direct_exact_anchor_count": 0, "anchor_community_count": 0, "citation_count": 5, "context_prompt_char_count": 1000, "violation_record_count": 0}}), encoding="utf-8")
    result = check_quality(report_path=report, min_direct_exact_anchors=1)
    assert result["quality_status"] == "FAIL"
    assert any("direct_exact_anchor_count" in f for f in result["failures"])


def test_quality_writes_json(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"quality_status": "PASS", "summary": {"stage_report_count": 12, "postgres_contract_ready_count": 509, "qdrant_contract_ready_count": 450, "opensearch_contract_ready_count": 282, "qdrant_payload_count": 450, "opensearch_payload_count": 282, "direct_exact_anchor_count": 1, "anchor_community_count": 0, "citation_count": 1, "context_prompt_char_count": 1000, "violation_record_count": 0}}), encoding="utf-8")
    result = check_quality(report_path=report, write_json=True)
    assert result["quality_status"] == "PASS"
    assert (tmp_path / "trace_net_raw_to_answer_context_engineered_native_v1_quality_check.json").exists()
