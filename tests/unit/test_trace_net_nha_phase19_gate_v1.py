from __future__ import annotations

from scripts.run_trace_net_nha_phase19_unified8131_gate_v1 import evaluate, summarize


def upstream_case():
    return {
        "case_id": "NHA-UNIFIED8131-007",
        "kind": "upstream_exact_part",
        "query": "Find part 120-20970-001.",
        "expected_action": "passthrough",
        "required_headings": ["## Answer", "## Evidence", "## Limits"],
        "required_text": ["120-20970-001", "t_p_120_1176_p000343"],
        "stream": False,
    }


def response(status="CONSTRAINED_GEMMA_CALL_SUCCEEDED_AND_VALIDATED", accepted=True, fallback=False):
    answer = "## Answer\n\n120-20970-001 [1].\n\n## Evidence\n\n- t_p_120_1176_p000343 [1].\n\n## Limits\n\n- bounded."
    return {
        "http_status": 200,
        "headers": {
            "x-trace-net-nha-action": "passthrough",
            "x-trace-net-model-calls": "1",
            "x-trace-net-model-path": "upstream_cognitive",
            "x-trace-net-upstream-calls": "1",
            "x-trace-net-upstream-gemma-status": status,
            "x-trace-net-upstream-writer-mode": "constrained_gemma_structured_output_validated",
        },
        "answer": answer,
        "body": {
            "trace_net": {
                "phase19_route_completion_fastpath": {
                    "active": True,
                    "executed_calls": 1,
                    "skipped_call_count": 2,
                    "matching_source_page_resolved": True,
                },
                "phase19_preservation_writer": {
                    "active": True,
                    "structured_output_accepted": accepted,
                    "phase3_fallback_used": fallback,
                },
            }
        },
        "latency_seconds": 40.0,
    }


def test_n19_accepts_only_accepted_upstream_rewrite():
    row = evaluate(upstream_case(), response())
    assert row["passed"] is True, row
    assert row["phase19_fastpath_active"] is True
    assert row["phase19_preservation_accepted"] is True


def test_n19_rejects_safe_fallback_for_improvement_gate():
    row = evaluate(
        upstream_case(),
        response(
            status="CONSTRAINED_GEMMA_OUTPUT_REJECTED_PHASE3_FALLBACK",
            accepted=False,
            fallback=True,
        ),
    )
    assert row["passed"] is False
    assert any("rewrite_not_accepted" in value for value in row["failures"])


def test_summary_enforces_latency_limits():
    upstream = evaluate(upstream_case(), response())
    records = [upstream] * 5
    # Minimal synthetic/NHA-shaped rows sufficient to exercise latency failure.
    records += [
        {
            "passed": True,
            "action": "gemma_override",
            "model_calls": 1,
            "http_status": 200,
            "stream": index % 2 == 0,
            "latency_seconds": 3.0,
        }
        for index in range(6)
    ]
    records += [{
        "passed": True,
        "action": "synthetic_blocked",
        "model_calls": 0,
        "http_status": 200,
        "stream": True,
        "latency_seconds": 0.001,
    }]
    summary = summarize(
        records,
        upstream_average_max_seconds=30.0,
        upstream_maximum_max_seconds=50.0,
        nha_maximum_max_seconds=20.0,
    )
    assert summary["quality_status"] == "FAIL"
    assert any("upstream_average" in value for value in summary["failures"])
