import json
from pathlib import Path

from tiff.trace_net_claim_evidence_entailment_v1 import (
    EntailmentThresholds,
    check_claim_evidence_entailment_quality,
)


def write_report(path: Path, summary: dict, records: list[dict]):
    path.write_text(
        json.dumps(
            {
                "schema_version": "trace_net_claim_evidence_entailment_v1",
                "status": "CLAIM_EVIDENCE_ENTAILMENT_BUILT",
                "quality_status": "PASS",
                "summary": summary,
                "entailment_records": records,
            }
        ),
        encoding="utf-8",
    )


def safe_summary(**overrides):
    summary = {
        "dynamic_final_gate_quality_status": "PASS",
        "dublin_core_source_quality_status": "PASS",
        "claim_record_count": 1,
        "entailment_record_count": 1,
        "query_count": 1,
        "source_resolved_record_count": 1,
        "unsafe_entailment_record_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_truth_mutations_performed": 0,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
    }
    summary.update(overrides)
    return summary


def safe_record(**overrides):
    record = {
        "entailment_record_id": "entailment_0001",
        "advisory_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "claim_text": "supported claim",
    }
    record.update(overrides)
    return record


def test_quality_passes_for_safe_advisory_report(tmp_path):
    path = tmp_path / "report.json"
    write_report(path, safe_summary(), [safe_record()])
    payload = check_claim_evidence_entailment_quality(
        report_path=path,
        thresholds=EntailmentThresholds(
            min_entailment_records=1,
            min_claim_records=1,
            min_queries=1,
            require_dynamic_final_gate_quality_pass=True,
            require_dublin_core_source_quality_pass=True,
        ),
        write_json_report=True,
    )
    assert payload["quality_status"] == "PASS"
    assert (tmp_path / "trace_net_claim_evidence_entailment_v1_quality.json").exists()


def test_quality_fails_when_record_grants_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    write_report(path, safe_summary(), [safe_record(can_answer_directly=True)])
    payload = check_claim_evidence_entailment_quality(
        report_path=path,
        thresholds=EntailmentThresholds(),
        write_json_report=False,
    )
    assert payload["quality_status"] == "FAIL"
    assert "record_grants_answer_or_proof_permission" in payload["summary"]["quality_failures"]


def test_quality_fails_on_source_truth_mutation_counter(tmp_path):
    path = tmp_path / "report.json"
    write_report(path, safe_summary(source_truth_mutation_allowed_count=1), [safe_record()])
    payload = check_claim_evidence_entailment_quality(report_path=path, thresholds=EntailmentThresholds())
    assert payload["quality_status"] == "FAIL"
    assert "source_truth_mutation_allowed_count_nonzero" in payload["summary"]["quality_failures"]
