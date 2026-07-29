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
