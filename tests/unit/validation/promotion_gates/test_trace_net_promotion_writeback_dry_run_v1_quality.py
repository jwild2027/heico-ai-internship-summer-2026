from __future__ import annotations

from tiff.trace_net_promotion_writeback_dry_run_v1 import quality_report


def base_report() -> dict:
    return {
        "summary": {
            "writeback_mode": "dry_run",
            "promotion_gate_quality_status": "PASS",
            "writeback_plan_count": 1,
            "promotion_candidate_count": 1,
            "approved_promotion_candidate_count": 1,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_truth_mutations_performed": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "final_answer_allowed_count": 0,
            "unsafe_writeback_plan_count": 0,
            "writeback_plan_missing_citation_count": 0,
            "writeback_plan_missing_page_id_count": 0,
        }
    }


def test_quality_report_passes_for_dry_run_safe_report() -> None:
    quality = quality_report(base_report(), min_writeback_plans=1, require_promotion_gate_quality_pass=True)
    assert quality["quality_status"] == "PASS"
    assert quality["failed_check_count"] == 0


def test_quality_report_fails_on_postgres_write_attempt() -> None:
    report = base_report()
    report["summary"]["postgres_write_attempt_count"] = 1
    quality = quality_report(report, min_writeback_plans=1)
    assert quality["quality_status"] == "FAIL"


def test_quality_report_fails_on_source_truth_mutation_allowed() -> None:
    report = base_report()
    report["summary"]["source_truth_mutation_allowed_count"] = 1
    quality = quality_report(report, min_writeback_plans=1)
    assert quality["quality_status"] == "FAIL"


def test_quality_report_fails_on_missing_minimum_plans() -> None:
    report = base_report()
    report["summary"]["writeback_plan_count"] = 0
    quality = quality_report(report, min_writeback_plans=1)
    assert quality["quality_status"] == "FAIL"
