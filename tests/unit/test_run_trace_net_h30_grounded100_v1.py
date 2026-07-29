from types import SimpleNamespace

import sys
import types
import re

_grounded_stub = types.ModuleType("scripts.run_trace_net_tiff_grounded20_v1")
_grounded_stub.answer = lambda payload: str((((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""))
def _stub_pages(value):
    text = str(value)
    return {match.lower() for match in re.findall(r"t_p_[a-z0-9_]+_p\d{6}", text, re.I)}
_grounded_stub.evidence_page_ids = _stub_pages
_grounded_stub.truth = lambda repo: {}
_grounded_stub.call = lambda *args, **kwargs: (200, {}, "")
sys.modules.setdefault("scripts.run_trace_net_tiff_grounded20_v1", _grounded_stub)

from scripts.run_trace_net_h30_grounded100_v1 import (
    _select_bank,
    evaluate_record,
    summarize_records,
)


def good_payload(route="exact_identifier_lookup"):
    return {
        "choices": [{"message": {"content": "## Answer\n\nPart `120-20001-001` is listed [1].\n\n## Evidence\n\n- Page `t_p_120_1176_p000001` [1]\n\n## Limits\n\n- Effectivity is not established [1]."}}],
        "trace_net": {
            "route": route,
            "post_answer_validation": {"accepted": True, "failures": []},
            "evidence_envelope": {
                "direct_evidence": [{"candidate_value": "120-20001-001", "page_id": "t_p_120_1176_p000001"}],
                "candidate_evidence": [],
                "source_resolution": [],
            },
            "citation_registry": [{"citation_id": 1, "can_prove_claims": True, "authority": "proof"}],
            "answer_mode": {"mode": "confirmed_direct"},
            "constrained_gemma_writer": {"eligible": True, "call_count": 1, "structured_output_accepted": True},
        },
    }


def item(route="exact_identifier_lookup"):
    return {
        "question_id": "q001", "ordinal": 1, "category": "exact_part",
        "question": "Find part 120-20001-001.", "expected_route": route,
        "expected_identifiers": ["120-20001-001"],
        "expected_pages": ["t_p_120_1176_p000001"],
        "negative_control": False, "authority_sensitive": False,
        "multi_claim": False, "requires_citation": True,
    }


def test_evaluate_record_accepts_grounded_valid_answer():
    row = evaluate_record(item(), good_payload(), 200, 1000.0, "", latency_hard_limit_seconds=180)
    assert row["passed_hard_gates"], row
    assert row["route_match"]
    assert row["expected_identifier_recovered"]
    assert row["expected_page_recovered"]
    assert row["public_contract_ok"]


def test_evaluate_record_rejects_unproved_authority_assertion():
    target = item("authority_eligibility_verification")
    target["authority_sensitive"] = True
    payload = good_payload("authority_eligibility_verification")
    payload["choices"][0]["message"]["content"] = (
        "## Answer\n\nThis is an approved replacement [1].\n\n## Evidence\n\n- Candidate record [1]\n\n## Limits\n\n- None."
    )
    payload["trace_net"]["citation_registry"] = [{"citation_id": 1, "can_prove_claims": False, "authority": "guidance"}]
    row = evaluate_record(target, payload, 200, 1000.0, "", latency_hard_limit_seconds=180)
    assert "authority_claim_without_proof" in row["hard_failures"]


def test_summary_enforces_coverage_thresholds():
    row = evaluate_record(item(), good_payload(), 200, 1000.0, "", latency_hard_limit_seconds=180)
    summary = summarize_records(
        [row], selected_count=1, full_bank_count=100,
        category_counts_expected={"exact_part": 1},
        route_match_threshold=0.9, identifier_recovery_threshold=0.75, page_recovery_threshold=0.7,
    )
    assert summary["quality_status"] == "PASS"
    assert summary["http_200_count"] == 1


def test_select_bank_supports_category_id_and_limit_filters():
    bank = [
        {"question_id": "q001", "ordinal": 1, "category": "a"},
        {"question_id": "q002", "ordinal": 2, "category": "b"},
        {"question_id": "q003", "ordinal": 3, "category": "a"},
    ]
    args = SimpleNamespace(only_categories="a", only_ids="", start_index=2, max_questions=1)
    selected = _select_bank(bank, args)
    assert [row["question_id"] for row in selected] == ["q003"]

# TRACE_NET_H30_PHASE5_CALIBRATED_EVALUATOR_V1
from scripts.run_trace_net_h30_grounded100_v1 import (
    _existing_record_matches_question,
    _regrade_existing_record,
)


def test_negative_no_match_does_not_treat_direct_query_echo_as_fabrication():
    target = item()
    target.update({
        "negative_control": True,
        "requires_citation": False,
        "expected_identifiers": ["999-99999-999"],
        "expected_pages": [],
    })
    payload = {
        "choices": [{"message": {"content": (
            "## Answer\n\nNo indexed match was found for `999-99999-999`.\n\n"
            "## Evidence\n\n- No matching indexed part record was returned."
        )}}],
        "trace_net": {
            "route": "exact_identifier_lookup",
            "post_answer_validation": {"accepted": True, "failures": []},
            "evidence_envelope": {
                "direct_evidence": [{"candidate_value": "999-99999-999", "match_status": "not_found"}],
                "candidate_evidence": [],
                "source_resolution": [],
            },
        },
    }
    row = evaluate_record(target, payload, 200, 1000.0, "", latency_hard_limit_seconds=180)
    assert row["passed_hard_gates"], row
    assert not row["negative_identifier_fabricated"]
    assert not row["required_citation_missing"]


def test_plain_clarification_can_use_nontechnical_public_contract():
    target = item("clarification_no_evidence")
    target.update({
        "category": "clarification",
        "question": "Can you help me identify the component?",
        "expected_identifiers": [],
        "expected_pages": [],
        "requires_citation": False,
        "public_contract_required": False,
    })
    payload = {
        "choices": [{"message": {"content": "Please share any part-number characters or ATA clues."}}],
        "trace_net": {
            "route": "clarification_no_evidence",
            "post_answer_validation": {"accepted": True, "failures": []},
            "evidence_envelope": {},
        },
    }
    row = evaluate_record(target, payload, 200, 5.0, "", latency_hard_limit_seconds=180)
    assert row["passed_hard_gates"], row
    assert row["public_contract_ok"]
    assert not row["public_contract_required"]


def test_public_model_meta_text_is_a_hard_failure():
    payload = good_payload()
    payload["choices"][0]["message"]["content"] = (
        "## Answer\n\nThe user's prompt contains an error. Part `120-20001-001` is listed [1].\n\n"
        "## Evidence\n\n- Page `t_p_120_1176_p000001` [1]"
    )
    row = evaluate_record(item(), payload, 200, 1000.0, "", latency_hard_limit_seconds=180)
    assert "public_model_meta_leak" in row["hard_failures"]
    assert row["public_output_anomalies"]


def test_existing_record_question_fingerprint_prevents_stale_resume():
    current = item()
    existing = {"question": dict(current), "evaluation": {}, "raw_response": {}}
    assert _existing_record_matches_question(existing, current)
    changed = dict(current)
    changed["question"] = "Find the same part using a changed benchmark prompt."
    assert not _existing_record_matches_question(existing, changed)


def test_existing_record_is_regraded_under_current_evaluator():
    target = item()
    existing = {
        "question": dict(target),
        "evaluation": {
            "http_status": 200,
            "latency_ms": 1000.0,
            "transport_error": "",
        },
        "raw_response": good_payload(),
    }
    refreshed = _regrade_existing_record(
        existing, target, latency_hard_limit_seconds=180,
    )
    assert refreshed["passed_hard_gates"], refreshed
    assert refreshed["public_contract_ok"]
