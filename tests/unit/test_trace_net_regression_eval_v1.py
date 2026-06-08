from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_regression_eval_v1 import (
    DEFAULT_REGRESSION_CASES,
    build_quality_report,
    evaluate_regression_case,
    run_regression_eval,
)


def _group(page_id: str = "t_p_120_1176_p000001") -> dict:
    return {
        "page_id": page_id,
        "hybrid_score": 1.2,
        "safety_status": "retrieval_safe",
        "answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "unsafe_reasons": [],
    }


def _candidate_hit(page_id: str = "t_p_120_1176_p000001", bucket: str = "source_text_evidence") -> dict:
    return {
        "page_id": page_id,
        "rag_bucket": bucket,
        "authority": "source_text_evidence",
        "resolved_to_artifact": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "embedding_answer_authority_allowed": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "unsafe_reasons": [],
    }


def _page_hit(page_id: str = "t_p_120_1176_p000001") -> dict:
    return {
        "page_id": page_id,
        "rag_bucket": "page_retrieval_profile",
        "authority": "page_route_only",
        "resolved_to_artifact": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "embedding_answer_authority_allowed": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "unsafe_reasons": [],
    }


def fake_hybrid_report() -> dict:
    results = []
    for case in DEFAULT_REGRESSION_CASES:
        results.append(
            {
                "query_id": case["query_id"],
                "query": case["query_id"],
                "intent": case["expected_intent"],
                "ranked_groups": [_group("p1"), _group("p2"), _group("p3")],
                "ranked_group_count": 3,
                "candidate_hits": [_candidate_hit("p1"), _candidate_hit("p2"), _candidate_hit("p3")],
                "candidate_hit_count": 3,
                "page_profile_hits": [_page_hit("p1"), _page_hit("p2"), _page_hit("p3")],
                "page_profile_hit_count": 3,
            }
        )
    return {
        "schema_version": "trace_net_hybrid_retrieval_sim_v1",
        "status": "PASS",
        "quality": {"status": "PASS", "checks": []},
        "embedding_mode": "ollama",
        "embedding_model_name": "bge-m3:latest",
        "embedding_dim": 1024,
        "summary": {
            "candidate_collection_count": 1476,
            "page_profile_collection_count": 509,
            "embedding_dim": 1024,
            "unsafe_result_count": 0,
            "unsafe_hit_payload_count": 0,
            "direct_answer_allowed_result_count": 0,
            "claim_proof_allowed_without_authority_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "grouped_result_count": 15,
            "candidate_hit_count": 15,
            "page_profile_hit_count": 15,
            "resolved_candidate_hit_count": 15,
            "resolved_page_profile_hit_count": 15,
        },
        "results": results,
    }


def test_evaluate_case_passes_for_safe_result() -> None:
    report = fake_hybrid_report()
    index = {row["query_id"]: row for row in report["results"]}
    result = evaluate_regression_case(DEFAULT_REGRESSION_CASES[0], index)
    assert result["status"] == "PASS"
    assert result["direct_answer_allowed_count"] == 0
    assert result["unsafe_result_count"] == 0


def test_evaluate_case_fails_when_query_missing() -> None:
    result = evaluate_regression_case(DEFAULT_REGRESSION_CASES[0], {})
    assert result["status"] == "FAIL"
    assert result["missing_result"] is True


def test_evaluate_case_fails_when_direct_answer_is_allowed() -> None:
    report = fake_hybrid_report()
    report["results"][0]["ranked_groups"][0]["answer_allowed"] = True
    index = {row["query_id"]: row for row in report["results"]}
    result = evaluate_regression_case(DEFAULT_REGRESSION_CASES[0], index)
    assert result["status"] == "FAIL"
    assert result["direct_answer_allowed_count"] == 1


def test_build_quality_report_requires_no_unsafe_counts() -> None:
    summary = {
        "regression_case_count": 5,
        "case_pass_rate": 1.0,
        "cases_with_results_count": 5,
        "cases_with_candidate_hits_count": 5,
        "cases_with_page_profile_hits_count": 5,
        "total_ranked_group_count": 15,
        "total_candidate_hit_count": 15,
        "total_page_profile_hit_count": 15,
        "required_case_missing_count": 0,
        "case_fail_count": 0,
        "hybrid_quality_status": "PASS",
        "case_unsafe_result_count": 0,
        "case_direct_answer_allowed_count": 0,
        "case_claim_proof_allowed_count": 0,
        "case_source_truth_mutation_allowed_count": 0,
        "hybrid_unsafe_result_count": 0,
        "hybrid_unsafe_hit_payload_count": 0,
        "hybrid_direct_answer_allowed_result_count": 0,
        "hybrid_claim_proof_allowed_without_authority_count": 0,
        "hybrid_source_truth_mutation_allowed_count": 0,
        "candidate_collection_count": 1476,
        "page_profile_collection_count": 509,
        "embedding_dim": 1024,
    }
    quality = build_quality_report(
        summary,
        min_regression_cases=5,
        require_all_cases_pass=True,
        require_hybrid_quality_pass=True,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
    )
    assert quality.status == "PASS"


def test_run_regression_eval_writes_artifacts(tmp_path: Path) -> None:
    report_path = tmp_path / "hybrid.json"
    report_path.write_text(json.dumps(fake_hybrid_report()), encoding="utf-8")
    output_dir = tmp_path / "out"
    result = run_regression_eval(
        hybrid_report_path=report_path,
        output_dir=output_dir,
        min_regression_cases=5,
        min_cases_with_results=5,
        min_cases_with_candidate_hits=5,
        min_cases_with_page_profile_hits=5,
        min_total_ranked_groups=15,
        min_total_candidate_hits=15,
        min_total_page_profile_hits=15,
        require_all_cases_pass=True,
        require_hybrid_quality_pass=True,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
        write_quality=True,
    )
    assert result["status"] == "PASS"
    assert (output_dir / "trace_net_regression_eval_v1.json").exists()
    assert (output_dir / "trace_net_regression_eval_v1_cases.jsonl").exists()
    assert (output_dir / "trace_net_regression_set_v1.json").exists()
    assert (output_dir / "trace_net_regression_eval_v1_quality.json").exists()


def test_run_regression_eval_fails_when_hybrid_quality_fails(tmp_path: Path) -> None:
    report = fake_hybrid_report()
    report["quality"] = {"status": "FAIL", "checks": []}
    report_path = tmp_path / "hybrid.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    result = run_regression_eval(
        hybrid_report_path=report_path,
        output_dir=tmp_path / "out",
        min_regression_cases=5,
        min_cases_with_results=5,
        min_cases_with_candidate_hits=5,
        min_cases_with_page_profile_hits=5,
        min_total_ranked_groups=15,
        min_total_candidate_hits=15,
        min_total_page_profile_hits=15,
        require_all_cases_pass=True,
        require_hybrid_quality_pass=True,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
    )
    assert result["status"] == "FAIL"
