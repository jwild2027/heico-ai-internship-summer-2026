import json
from pathlib import Path

from tiff.trace_net_leiden_representative_label_tightening_v1 import check_quality, evaluate_quality


def test_evaluate_quality_passes_safe_report():
    report = {
        "quality_status": "PASS",
        "summary": {
            "community_profile_record_count": 229,
            "refined_label_count": 229,
            "communities_with_representative_pages_count": 223,
            "missing_page_membership_count": 6,
            "missing_category_summary_count": 6,
            "low_navigation_confidence_count": 40,
            "source_hydrator_quality_status": "PASS",
            "source_dublin_core_quality_status": "PASS",
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    quality = evaluate_quality(
        report,
        {
            "min_communities": 229,
            "min_refined_labels": 229,
            "min_communities_with_representative_pages": 200,
            "max_missing_page_membership": 6,
            "max_missing_category_summary": 6,
            "require_hydrator_quality_pass": True,
            "require_dublin_core_quality_pass": True,
        },
    )
    assert quality["quality_status"] == "PASS"


def test_evaluate_quality_fails_on_proof_leak():
    report = {
        "summary": {
            "community_profile_record_count": 1,
            "refined_label_count": 1,
            "communities_with_representative_pages_count": 1,
            "community_as_proof_count": 1,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    quality = evaluate_quality(report, {"min_communities": 1})
    assert quality["quality_status"] == "FAIL"
    assert any("community_as_proof_count" in f for f in quality["failures"])


def test_check_quality_writes_quality_json(tmp_path: Path):
    report_path = tmp_path / "trace_net_leiden_representative_label_tightening_v1.json"
    report_path.write_text(
        json.dumps(
            {
                "summary": {
                    "community_profile_record_count": 1,
                    "refined_label_count": 1,
                    "communities_with_representative_pages_count": 1,
                    "community_as_proof_count": 0,
                    "category_as_proof_count": 0,
                    "retrieval_only_answer_allowed_count": 0,
                    "can_answer_directly_count": 0,
                    "can_prove_claims_count": 0,
                    "source_truth_mutation_allowed_count": 0,
                    "postgres_write_attempt_count": 0,
                    "qdrant_write_attempt_count": 0,
                    "opensearch_write_attempt_count": 0,
                }
            }
        ),
        encoding="utf-8",
    )
    quality = check_quality(report_path=report_path, thresholds={"min_communities": 1}, write_json_report=True)
    assert quality["quality_status"] == "PASS"
    assert report_path.with_name("trace_net_leiden_representative_label_tightening_v1_quality.json").exists()
