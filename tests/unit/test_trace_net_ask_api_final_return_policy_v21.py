from pathlib import Path

from tiff.trace_net_ask_api_final_return_policy_v21 import (
    FinalReturnPolicyConfig,
    build_final_return_policy,
    build_policy_record,
    read_json,
    write_json,
)


def _write_inputs(tmp_path: Path):
    dyn = {
        "quality_status": "PASS",
        "query_results": [
            {
                "query": "good query",
                "answer_status": "DYNAMIC_FINAL_GATE_APPROVED",
                "final_answer_allowed": True,
                "final_answer_text": "Safe cited answer [cite:abc].",
                "final_claim_count": 1,
                "uncited_final_claim_count": 0,
                "retrieval_only_final_claim_count": 0,
                "source_truth_mutation_allowed_count": 0,
            },
            {
                "query": "audit query",
                "answer_status": "DYNAMIC_FINAL_GATE_APPROVED",
                "final_answer_allowed": True,
                "final_answer_text": "Candidate answer withheld.",
                "final_claim_count": 1,
            },
            {
                "query": "retrieval only query",
                "answer_status": "DYNAMIC_RETRIEVAL_ONLY_FINAL_GATE_REQUIRED",
                "final_answer_allowed": False,
                "retrieval_group_count": 1,
                "ranked_groups": [{"page_id": "p1", "hybrid_v2_rank": 1, "exact_hit_count": 1}],
            },
            {
                "query": "unsafe query",
                "answer_status": "DYNAMIC_FINAL_GATE_APPROVED",
                "final_answer_allowed": True,
                "final_answer_text": "Unsafe local_data/path answer.",
                "local_path_leak_count": 1,
            },
        ],
    }
    ret = {
        "quality_status": "PASS",
        "critic_records": [
            {"query": "good query", "critic_status": "final_gate_already_authorized", "recommended_next_action": "return_final_gate_answer"},
            {"query": "audit query", "critic_status": "dynamic_final_gate_needs_audit", "recommended_next_action": "audit_dynamic_final_gate_before_returning_answer"},
            {"query": "retrieval only query", "critic_status": "retrieval_only_not_answer_ready"},
            {"query": "unsafe query", "critic_status": "final_gate_already_authorized"},
        ],
    }
    suff = {
        "quality_status": "PASS",
        "sufficiency_records": [
            {"query": "good query", "evidence_sufficiency_status": "final_evidence_sufficient", "recommended_next_action": "allow_answer_claim_critic"},
            {"query": "audit query", "evidence_sufficiency_status": "final_evidence_sufficient_but_retrieval_audit_required"},
            {"query": "retrieval only query", "evidence_sufficiency_status": "insufficient_retrieval_only_evidence"},
            {"query": "unsafe query", "evidence_sufficiency_status": "final_evidence_sufficient"},
        ],
    }
    ans = {
        "quality_status": "PASS",
        "answer_critic_records": [
            {"query": "good query", "answer_claim_critic_status": "answer_claims_clear_for_return", "recommended_next_action": "return_answer"},
            {"query": "audit query", "answer_claim_critic_status": "answer_claims_need_audit"},
            {"query": "retrieval only query", "answer_claim_critic_status": "answer_claims_need_audit"},
            {"query": "unsafe query", "answer_claim_critic_status": "answer_claims_clear_for_return"},
        ],
    }
    paths = {}
    for name, payload in [("dyn", dyn), ("ret", ret), ("suff", suff), ("ans", ans)]:
        p = tmp_path / f"{name}.json"
        write_json(p, payload)
        paths[name] = p
    return paths


def test_policy_allows_only_when_all_critics_clear(tmp_path):
    paths = _write_inputs(tmp_path)
    report = build_final_return_policy(
        FinalReturnPolicyConfig(
            dynamic_final_gate=paths["dyn"],
            retrieval_critic=paths["ret"],
            evidence_sufficiency_critic=paths["suff"],
            answer_claim_critic=paths["ans"],
        )
    )
    records = {r["query"]: r for r in report["policy_records"]}
    assert records["good query"]["policy_status"] == "FINAL_ANSWER_RETURN_ALLOWED"
    assert records["good query"]["final_answer_return_allowed"] is True
    assert records["audit query"]["policy_status"] == "FINAL_ANSWER_AUDIT_REQUIRED"
    assert records["audit query"]["final_answer_return_allowed"] is False
    assert records["retrieval only query"]["policy_status"] == "RETRIEVAL_ONLY_FINAL_GATE_REQUIRED"
    assert records["unsafe query"]["policy_status"] == "FINAL_ANSWER_BLOCKED_UNSAFE"


def test_policy_controller_never_claims_answer_authority():
    record = build_policy_record(
        "q",
        {"query": "q", "final_answer_allowed": True, "final_answer_text": "answer"},
        {"query": "q", "critic_status": "final_gate_already_authorized"},
        {"query": "q", "evidence_sufficiency_status": "final_evidence_sufficient"},
        {"query": "q", "answer_claim_critic_status": "answer_claims_clear_for_return"},
    )
    assert record["policy_status"] == "FINAL_ANSWER_RETURN_ALLOWED"
    assert record["can_answer_directly"] is False
    assert record["can_prove_claims"] is False
    assert record["source_truth_mutation_allowed"] is False


def test_read_json_missing_returns_empty(tmp_path):
    assert read_json(tmp_path / "missing.json") == {}
