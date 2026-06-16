import json
from pathlib import Path

from tiff.trace_net_claim_evidence_entailment_v1 import (
    EntailmentThresholds,
    build_entailment_report,
    extract_claim_records,
    lexical_overlap_score,
)


def write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_dynamic_payload():
    return {
        "quality_status": "PASS",
        "status": "DYNAMIC_FINAL_GATE_EXECUTION_BUILT",
        "summary": {"final_claim_count": 3},
        "query_results": [
            {
                "query_id": "part_120_46137_001",
                "query": "120-46137-001",
                "final_claims": [
                    {
                        "claim_id": "c1",
                        "claim_text": "Part 120-46137-001 appears on page t_p_120_1176_p000003.",
                        "citation_ids": ["cite:source_text:t_p_120_1176_p000003:aaa"],
                        "page_id": "t_p_120_1176_p000003",
                        "status": "allowed",
                    },
                    {
                        "claim_id": "c2",
                        "claim_text": "Part 120-46137-001 does not appear on page t_p_120_1176_p000003.",
                        "citation_ids": ["cite:source_text:t_p_120_1176_p000003:bbb"],
                        "page_id": "t_p_120_1176_p000003",
                        "status": "allowed",
                    },
                    {
                        "claim_id": "c3",
                        "claim_text": "Unsupported claim with no citation.",
                        "status": "blocked",
                    },
                ],
            }
        ],
        "evidence_groups": [
            {
                "page_id": "t_p_120_1176_p000003",
                "citation_id": "cite:source_text:t_p_120_1176_p000003:aaa",
                "evidence_text": "Part 120-46137-001 appears on page t_p_120_1176_p000003 with related part evidence.",
            }
        ],
    }


def sample_dublin_payload():
    return {
        "quality_status": "PASS",
        "page_records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "source_package_entry": {"href": "file://./00000003.tif", "checksum_match": True},
            }
        ],
    }


def test_extract_claim_records_from_nested_final_claims():
    claims = extract_claim_records(sample_dynamic_payload())
    assert len(claims) == 3
    assert claims[0]["query_id"] == "unknown_query" or claims[0]["query_id"] == "part_120_46137_001"
    assert claims[0]["citation_ids"]
    assert "t_p_120_1176_p000003" in claims[0]["page_ids"]


def test_lexical_overlap_prefers_relevant_evidence():
    good = lexical_overlap_score("Part 120-46137-001 appears on page 3", "Part 120-46137-001 appears on page 3")
    bad = lexical_overlap_score("Part 120-46137-001 appears on page 3", "unrelated seat back material")
    assert good > bad
    assert good > 0.5


def test_build_entailment_report_scores_and_escalates(tmp_path):
    dynamic = tmp_path / "dynamic.json"
    dublin = tmp_path / "dublin.json"
    out = tmp_path / "out"
    write_json(dynamic, sample_dynamic_payload())
    write_json(dublin, sample_dublin_payload())

    payload = build_entailment_report(
        dynamic_final_gate_path=dynamic,
        dublin_core_source_package_extension_path=dublin,
        output_dir=out,
        thresholds=EntailmentThresholds(min_entailment_records=3, min_claim_records=3, min_queries=1),
        quality=True,
    )

    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["entailment_record_count"] == 3
    assert summary["source_resolved_record_count"] >= 2
    assert summary["contradiction_risk_record_count"] >= 2
    assert summary["human_review_escalation_count"] >= 1
    assert summary["can_answer_directly_count"] == 0
    assert summary["can_prove_claims_count"] == 0
    assert (out / "trace_net_claim_evidence_entailment_v1.json").exists()
    assert (out / "trace_net_claim_evidence_entailment_v1_quality.json").exists()
    assert (out / "trace_net_claim_evidence_entailment_v1.md").exists()


def test_summary_only_dynamic_gate_creates_weak_advisory_records(tmp_path):
    dynamic = tmp_path / "dynamic.json"
    out = tmp_path / "out"
    write_json(dynamic, {"quality_status": "PASS", "summary": {"final_claim_count": 2}})

    payload = build_entailment_report(
        dynamic_final_gate_path=dynamic,
        output_dir=out,
        thresholds=EntailmentThresholds(min_entailment_records=2, min_claim_records=2, min_queries=1),
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["missing_citation_review_count"] == 2
    assert all(r["advisory_only"] for r in payload["entailment_records"])
