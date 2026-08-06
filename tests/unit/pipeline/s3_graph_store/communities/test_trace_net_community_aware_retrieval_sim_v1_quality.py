from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_community_aware_retrieval_sim_v1 import quality_report


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def report_payload() -> dict:
    return {
        "schema_version": "trace_net_community_aware_retrieval_sim_v1",
        "quality_status": "PASS",
        "summary": {
            "community_aware_query_count": 5,
            "queries_with_results_count": 5,
            "grouped_result_count": 40,
            "community_boosted_result_count": 40,
            "feedback_adjusted_result_count": 1,
            "feedback_memory_record_count": 4,
            "hybrid_quality_status": "PASS",
            "leiden_quality_status": "PASS",
            "feedback_memory_quality_status": "PASS",
            "unsafe_result_count": 0,
            "community_as_proof_count": 0,
            "feedback_as_proof_count": 0,
            "direct_answer_allowed_result_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
            "feedback_can_answer_directly_count": 0,
            "feedback_can_prove_claims_count": 0,
            "feedback_can_mutate_source_truth_count": 0,
        },
    }


def test_quality_passes(tmp_path: Path) -> None:
    path = write_json(tmp_path / "report.json", report_payload())
    result = quality_report(
        path,
        min_queries=5,
        min_queries_with_results=5,
        min_grouped_results=25,
        min_community_boosted_results=1,
        min_feedback_boosted_results=1,
        require_hybrid_quality_pass=True,
        require_leiden_quality_pass=True,
        require_feedback_quality_pass=True,
        write_json_flag=True,
    )
    assert result["status"] == "PASS"
    assert Path(result["quality_path"]).exists()


def test_quality_fails_when_feedback_is_used_as_proof(tmp_path: Path) -> None:
    payload = report_payload()
    payload["summary"]["feedback_as_proof_count"] = 1
    path = write_json(tmp_path / "report.json", payload)
    result = quality_report(path, min_queries=1, min_queries_with_results=1, min_grouped_results=1, min_community_boosted_results=0, min_feedback_boosted_results=0, require_hybrid_quality_pass=False, require_leiden_quality_pass=False, require_feedback_quality_pass=False)
    assert result["status"] == "FAIL"


def test_quality_fails_when_raw_feedback_goes_to_llm(tmp_path: Path) -> None:
    payload = report_payload()
    payload["summary"]["raw_feedback_direct_to_llm_count"] = 1
    path = write_json(tmp_path / "report.json", payload)
    result = quality_report(path, min_queries=1, min_queries_with_results=1, min_grouped_results=1, min_community_boosted_results=0, min_feedback_boosted_results=0, require_hybrid_quality_pass=False, require_leiden_quality_pass=False, require_feedback_quality_pass=False)
    assert result["status"] == "FAIL"
