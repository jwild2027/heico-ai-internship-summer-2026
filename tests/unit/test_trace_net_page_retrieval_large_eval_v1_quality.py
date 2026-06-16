import json
from pathlib import Path

from tiff.trace_net_page_retrieval_large_eval_v1 import QualityThresholds, check_large_eval_quality


def test_quality_check_passes(tmp_path: Path):
    report = {
        "schema_version": "trace_net_page_retrieval_large_eval_v1",
        "status": "PAGE_RETRIEVAL_LARGE_EVAL_BUILT",
        "quality_status": "PASS",
        "summary": {
            "query_record_count": 170,
            "blank_expected_count": 5,
            "context_v2_query_count": 170,
            "evaluated_record_count": 170,
            "target_hit_at_k_count": 80,
            "answer_capable_payload_count": 0,
            "claim_proof_payload_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    out = check_large_eval_quality(
        report_path=path,
        thresholds=QualityThresholds(
            min_query_records=170,
            min_blank_queries=1,
            min_context_v2_queries=170,
            min_evaluated_records=170,
            min_target_hit_at_k=1,
        ),
        write_json_report=True,
    )
    assert out["quality_status"] == "PASS"
    assert Path(out["quality_path"]).exists()


def test_quality_check_fails_when_answer_payloads_present(tmp_path: Path):
    report = {
        "summary": {
            "query_record_count": 1,
            "blank_expected_count": 0,
            "context_v2_query_count": 1,
            "evaluated_record_count": 1,
            "target_hit_at_k_count": 1,
            "answer_capable_payload_count": 1,
            "claim_proof_payload_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    out = check_large_eval_quality(report_path=path, thresholds=QualityThresholds(), write_json_report=False)
    assert out["quality_status"] == "FAIL"
