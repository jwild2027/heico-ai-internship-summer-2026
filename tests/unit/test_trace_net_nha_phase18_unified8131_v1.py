from __future__ import annotations

from scripts.operations.graph.run_trace_net_nha_phase18_unified8131_gate_v1 import build_bank, evaluate, summarize
from scripts.operations.serving.serve_trace_net_nha_phase16_gemma_proxy_v1 import observe_upstream_model


def test_observe_upstream_constrained_gemma_success():
    result = {
        "trace_net": {
            "gemma_status": "CONSTRAINED_GEMMA_CALL_SUCCEEDED_AND_VALIDATED",
            "writer_mode": "constrained_gemma_structured_output_validated",
            "constrained_gemma_writer": {
                "call_attempted": True,
                "call_count": 1,
                "structured_output_accepted": True,
            },
        }
    }
    observed = observe_upstream_model(result)
    assert observed["model_call_count"] == 1
    assert observed["model_path"] == "upstream_cognitive"
    assert observed["accepted"] is True


def test_observe_upstream_deterministic_is_not_counted_as_model_call():
    result = {
        "trace_net": {
            "gemma_status": "SKIPPED_NO_DIRECT_EVIDENCE",
            "writer_mode": "deterministic_fail_closed",
            "constrained_gemma_writer": {"call_attempted": False, "call_count": 0},
        }
    }
    observed = observe_upstream_model(result)
    assert observed["model_call_count"] == 0
    assert observed["model_path"] == "upstream_cognitive_deterministic"
    assert observed["accepted"] is False


def test_observe_upstream_rejected_call_is_counted_but_not_accepted():
    result = {
        "trace_net": {
            "gemma_status": "CONSTRAINED_GEMMA_OUTPUT_REJECTED_PHASE3_FALLBACK",
            "writer_mode": "phase3_deterministic_fallback_after_constrained_output_rejection",
            "constrained_gemma_writer": {"call_attempted": True, "call_count": 1},
        }
    }
    observed = observe_upstream_model(result)
    assert observed["model_call_count"] == 1
    assert observed["model_path"] == "upstream_cognitive"
    assert observed["accepted"] is False


def test_mixed_bank_shape_and_model_policy():
    bank = build_bank()
    assert len(bank) == 12
    assert sum(row["expected_action"] == "gemma_override" for row in bank) == 6
    assert sum(row["expected_action"] == "passthrough" for row in bank) == 5
    assert sum(row["expected_action"] == "synthetic_blocked" for row in bank) == 1
    assert sum(bool(row["stream"]) for row in bank) == 6


def test_upstream_live_evaluation_requires_actual_gemma_acceptance():
    case = next(row for row in build_bank() if row["expected_action"] == "passthrough")
    response = {
        "http_status": 200,
        "headers": {
            "x-trace-net-nha-action": "passthrough",
            "x-trace-net-model-calls": "0",
            "x-trace-net-model-path": "upstream_cognitive_deterministic",
            "x-trace-net-upstream-calls": "1",
            "x-trace-net-upstream-gemma-status": "SKIPPED_NO_DIRECT_EVIDENCE",
            "x-trace-net-upstream-writer-mode": "deterministic_fail_closed",
        },
        "answer": "## Answer\n\n120-20970-001\n\n## Evidence\n\nt_p_120_1176_p000343\n\n## Limits\n\n- Limited.",
        "body": {},
        "latency_seconds": 1.0,
    }
    result = evaluate(case, response)
    assert result["passed"] is False
    assert any("actual_upstream_model_calls" in value for value in result["failures"])


def test_summary_requires_eleven_actual_model_backed_cases():
    records = []
    for case in build_bank():
        action = case["expected_action"]
        records.append({
            "case_id": case["case_id"],
            "passed": True,
            "http_status": 200,
            "action": action,
            "model_calls": 0 if action == "synthetic_blocked" else 1,
            "upstream_gemma_outcome": "accepted" if action == "passthrough" else "",
            "stream": case["stream"],
            "latency_seconds": 1.0,
            "failures": [],
        })
    summary = summarize(records)
    assert summary["quality_status"] == "PASS", summary
    assert summary["counts"]["model_backed_question_count"] == 11

# TRACE_NET_NHA_PHASE18_1_GATE_POLICY_FIX_V1

def test_upstream_completed_rejected_output_uses_safe_fallback_and_passes_gate():
    case = next(row for row in build_bank() if row["kind"] == "upstream_exact_part")
    response = {
        "http_status": 200,
        "headers": {
            "x-trace-net-nha-action": "passthrough",
            "x-trace-net-model-calls": "1",
            "x-trace-net-model-path": "upstream_cognitive",
            "x-trace-net-upstream-calls": "1",
            "x-trace-net-upstream-gemma-status": "CONSTRAINED_GEMMA_OUTPUT_REJECTED_PHASE3_FALLBACK",
            "x-trace-net-upstream-writer-mode": "public_answer_contract_v1",
        },
        "answer": (
            "## Answer\n\n120-20970-001 appears in the indexed source records [1].\n\n"
            "## Evidence\n\n- t_p_120_1176_p000343 [1]\n\n"
            "## Limits\n\n- The returned association remains bounded by the cited source."
        ),
        "body": {},
        "latency_seconds": 1.0,
    }
    result = evaluate(case, response)
    assert result["passed"] is True, result
    assert result["upstream_gemma_outcome"] == "safe_fallback"


def test_upstream_ipl_contract_does_not_invent_limits_requirement():
    case = next(row for row in build_bank() if row["kind"] == "upstream_ipl")
    required = case["required_text"]
    response = {
        "http_status": 200,
        "headers": {
            "x-trace-net-nha-action": "passthrough",
            "x-trace-net-model-calls": "1",
            "x-trace-net-model-path": "upstream_cognitive",
            "x-trace-net-upstream-calls": "1",
            "x-trace-net-upstream-gemma-status": "CONSTRAINED_GEMMA_CALL_SUCCEEDED_AND_VALIDATED",
            "x-trace-net-upstream-writer-mode": "public_answer_contract_v1",
        },
        "answer": (
            f"## Answer\n\n{required[0]} appears in the available IPL/table evidence [1].\n\n"
            f"## Evidence\n\n- Source-backed record on `{required[1]}` [1]."
        ),
        "body": {},
        "latency_seconds": 1.0,
    }
    result = evaluate(case, response)
    assert "## Limits" not in response["answer"]
    assert result["passed"] is True, result
    assert result["upstream_gemma_outcome"] == "accepted"


def test_upstream_timeout_is_not_a_safe_model_outcome():
    case = next(row for row in build_bank() if row["kind"] == "upstream_exact_part")
    response = {
        "http_status": 200,
        "headers": {
            "x-trace-net-nha-action": "passthrough",
            "x-trace-net-model-calls": "1",
            "x-trace-net-model-path": "upstream_cognitive",
            "x-trace-net-upstream-calls": "1",
            "x-trace-net-upstream-gemma-status": "CONSTRAINED_GEMMA_CALL_TIMED_OUT_PHASE3_FALLBACK",
            "x-trace-net-upstream-writer-mode": "public_answer_contract_v1",
        },
        "answer": (
            "## Answer\n\n120-20970-001 appears in the indexed source records [1].\n\n"
            "## Evidence\n\n- t_p_120_1176_p000343 [1]\n\n"
            "## Limits\n\n- Limited."
        ),
        "body": {},
        "latency_seconds": 1.0,
    }
    result = evaluate(case, response)
    assert result["passed"] is False
    assert result["upstream_gemma_outcome"] == "invalid"
    assert any("upstream_gemma_outcome" in value for value in result["failures"])

