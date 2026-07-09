from __future__ import annotations

from scripts.serve_trace_net_e2e_local_endpoint_target_gate_v1 import (
    citation_record_matches_any_target,
    extract_citation_like_records,
    extract_explicit_part_targets,
    extract_query_from_payload,
    gate_trace_response,
    has_target_matching_citation,
    norm_target,
)


def test_extract_explicit_part_targets_df_part() -> None:
    targets = extract_explicit_part_targets("Find part number DF250040-501 for A319")
    assert {t["target_norm"] for t in targets} == {"DF250040501"}


def test_extract_explicit_part_targets_covered_part() -> None:
    targets = extract_explicit_part_targets("What is 120-36833-001?")
    assert {t["target_norm"] for t in targets} == {"12036833001"}


def test_does_not_capture_aircraft_as_part_target() -> None:
    assert extract_explicit_part_targets("Is it eligible for A319 A320 A321 Boeing 737?") == []


def test_citation_record_matches_exact_target() -> None:
    targets = extract_explicit_part_targets("Find 120-36833-001")
    citation = {"field_name": "covered_part_number", "normalized_value": "120-36833-001"}
    assert citation_record_matches_any_target(citation, targets)


def test_citation_record_rejects_off_target() -> None:
    targets = extract_explicit_part_targets("Find DF250040-501")
    citation = {"field_name": "covered_part_number", "normalized_value": "120-36833-001"}
    assert not citation_record_matches_any_target(citation, targets)


def test_gate_trace_response_suppresses_off_target_citations() -> None:
    response = {
        "citations": [
            {"citation_id": "c1", "page_id": "p1", "normalized_value": "120-36833-001", "source_trace_ready": True}
        ],
        "response": {"citation_count": 1, "citations": [{"normalized_value": "120-36833-001"}]},
        "matched_artifact_response": True,
    }
    gated = gate_trace_response("Find part number DF250040-501.", response)
    assert gated["matched_artifact_response"] is False
    assert gated["citations"] == []
    assert gated["response"]["api_response_status"] == "AUDIT_ONLY_TARGET_NOT_FOUND"
    assert gated["target_gate"]["target_gate_applied"] is True
    assert gated["target_gate"]["off_target_citations_suppressed"] >= 1


def test_gate_trace_response_keeps_matching_target_citations() -> None:
    response = {
        "citations": [
            {"citation_id": "c1", "page_id": "p1", "normalized_value": "120-36833-001", "source_trace_ready": True}
        ],
        "response": {"citations": [{"normalized_value": "120-36833-001"}]},
        "matched_artifact_response": True,
    }
    gated = gate_trace_response("Find part number 120-36833-001.", response)
    assert gated["matched_artifact_response"] is True
    assert gated["citations"]
    assert gated["target_gate"]["target_quality_status"] == "TARGET_CITATION_MATCHED"


def test_gate_trace_response_keeps_no_citation_no_match() -> None:
    response = {
        "citations": [],
        "response": {"api_response_status": "AUDIT_ONLY_NO_MATCHING_E2E_DEMO_RESPONSE", "citations": []},
        "matched_artifact_response": False,
    }
    gated = gate_trace_response("DF250040-501", response)
    assert gated["matched_artifact_response"] is False
    assert gated["response"]["api_response_status"] == "AUDIT_ONLY_NO_MATCHING_E2E_DEMO_RESPONSE"
    assert gated["target_gate"]["target_quality_status"] == "NO_CITATIONS_RETURNED"


def test_extract_query_from_payload_question_and_chat() -> None:
    assert extract_query_from_payload("/api/trace-net/ask", {"question": "Find DF250040-501"}) == "Find DF250040-501"
    payload = {"messages": [{"role": "system", "content": "x"}, {"role": "user", "content": "Find 120-36833-001"}]}
    assert extract_query_from_payload("/v1/chat/completions", payload) == "Find 120-36833-001"


def test_extract_citation_like_records_nested() -> None:
    data = {"response": {"citations": [{"page_id": "p1", "normalized_value": "120-36833-001"}]}}
    records = extract_citation_like_records(data)
    assert records
    assert has_target_matching_citation(data, extract_explicit_part_targets("120-36833-001"))
