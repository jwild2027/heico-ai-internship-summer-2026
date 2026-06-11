from __future__ import annotations

from tiff.trace_net_page_element_registry_v1 import evaluate_registry_quality, summarize_registry


def safe_record(page_id: str) -> dict:
    return {
        "page_id": page_id,
        "page_traits": ["source_trace_present", "ocr_text_present"],
        "detected_elements": [
            {
                "element_type": "source_text",
                "answer_role": "answer_support_with_citation",
                "can_answer_directly": False,
            }
        ],
        "recommended_extraction_routes": ["source_trace_route", "source_text_route"],
        "fishnet_retry_plan": [{"fishnet_layer": 0, "can_answer_directly": False, "can_mutate_source_truth": False}],
        "comparison_targets": ["ocr", "graph", "source_citation"],
        "trust_assignment_policy": "evidence_consensus_then_trust_authority_gate",
        "graph_attachment_plan": {"clean_evidence_attached_or_available": True},
        "candidate_bucket_counts": {"source_text_evidence": 1, "source_evidence": 1},
        "answer_support_candidate_count": 1,
        "citation_count": 1,
        "context_v2_present": False,
        "authority": "page_element_registry_route_only",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutations_performed": 0,
    }


def empty_payloads() -> dict:
    return {
        "baseline_payload": {},
        "page_profiles_payload": {},
        "embedding_candidates_payload": {},
        "context_helpers_payload": {},
        "evidence_consensus_payload": {},
        "image_recognition_payload": {},
    }


def test_quality_passes_for_safe_records() -> None:
    records = [safe_record("p1"), safe_record("p2")]
    summary = summarize_registry(records, payloads=empty_payloads())
    quality = evaluate_registry_quality(
        summary,
        records,
        {
            "require_page_count": 2,
            "min_page_records": 2,
            "min_pages_with_detected_elements": 2,
            "min_pages_with_recommended_routes": 2,
            "min_pages_with_fishnet": 2,
            "min_pages_with_comparison_targets": 2,
            "min_pages_with_graph_attachment_plan": 2,
            "min_pages_with_trust_policy": 2,
            "min_pages_with_source_trace": 2,
            "min_pages_with_ocr": 2,
        },
    )
    assert quality["status"] == "PASS"


def test_quality_fails_when_page_count_too_low() -> None:
    records = [safe_record("p1")]
    summary = summarize_registry(records, payloads=empty_payloads())
    quality = evaluate_registry_quality(summary, records, {"require_page_count": 2, "min_page_records": 2})
    assert quality["status"] == "FAIL"
    assert any(c["name"] == "require_page_count" and not c["passed"] for c in quality["checks"])


def test_quality_fails_on_direct_answer_allowed() -> None:
    record = safe_record("p1")
    record["can_answer_directly"] = True
    records = [record]
    summary = summarize_registry(records, payloads=empty_payloads())
    quality = evaluate_registry_quality(summary, records, {"max_direct_answer_allowed": 0})
    assert quality["status"] == "FAIL"
    assert summary["direct_answer_allowed_count"] == 1


def test_quality_fails_on_source_truth_mutation() -> None:
    record = safe_record("p1")
    record["can_mutate_source_truth"] = True
    records = [record]
    summary = summarize_registry(records, payloads=empty_payloads())
    quality = evaluate_registry_quality(summary, records, {"max_source_truth_mutation_allowed": 0})
    assert quality["status"] == "FAIL"
    assert summary["source_truth_mutation_allowed_count"] >= 1
