from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_eval_latency_harness_v26 import (
    EvalQuery,
    build_report,
    evaluate_response,
    run_eval_queries,
    standard_eval_queries,
)


def response(content, *, status="LIVE_ORCHESTRATOR_FINAL_GATE_PASS", citations=1, total=1, returned=1, capped=False):
    return {
        "choices": [{"message": {"content": content}}],
        "trace_net": {
            "final_gate_status": status,
            "citation_like_count": citations,
            "total_match_count": total,
            "returned_match_count": returned,
            "result_was_capped": capped,
            "safety": {
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "raw_5tb_scan_at_query_time": False,
                "graph_rebuild_at_query_time": False,
            },
        },
    }


def test_evaluate_present_exact_value_passes():
    q = EvalQuery("q1", "Find part number 120-1", "final_gated_answer", "part_number", "120-1")
    r = evaluate_response(q, response("Found 120-1 [1]."), "", 123.4)
    assert r["passed"] is True
    assert r["false_negative"] is False


def test_evaluate_missing_exact_value_audit_only_passes():
    q = EvalQuery("q2", "Find part number NOPE", "audit_only", "part_number", "NOPE")
    r = evaluate_response(
        q,
        response(
            "TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made.",
            status="LIVE_ORCHESTRATOR_AUDIT_ONLY",
            citations=0,
            total=0,
            returned=0,
        ),
        "",
        100.0,
    )
    assert r["passed"] is True
    assert r["audit_only"] is True
    assert r["false_positive"] is False


def test_evaluate_missing_exact_false_positive_fails():
    q = EvalQuery("q3", "Find part number NOPE", "audit_only", "part_number", "NOPE")
    r = evaluate_response(q, response("Found unrelated NUMBER [1].", citations=1, total=10), "", 100.0)
    assert r["passed"] is False
    assert r["false_positive"] is True


def test_run_eval_queries_with_fake_chat_fn():
    queries = standard_eval_queries()[:2]

    def fake_chat(query):
        if "DOES-NOT-EXIST" in query:
            return response(
                "TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made.",
                status="LIVE_ORCHESTRATOR_AUDIT_ONLY",
                citations=0,
                total=0,
                returned=0,
            )
        return response("TRACE-Net found part number 120-36833-503 [1].")

    records = run_eval_queries(endpoint_base_url="http://unused/v1", model="m", queries=queries, request_timeout=1, chat_fn=fake_chat)
    assert len(records) == 2
    assert all(r["passed"] for r in records)


def test_build_report_writes_files_with_fake_endpoint(monkeypatch, tmp_path):
    from tiff import trace_net_e2e_live_eval_latency_harness_v26 as mod

    def fake_run_eval_queries(**kwargs):
        return [
            evaluate_response(
                EvalQuery("q1", "Find part number 120-1", "final_gated_answer", "part_number", "120-1"),
                response("Found 120-1 [1]."),
                "",
                10.0,
            )
        ]

    monkeypatch.setattr(mod, "run_eval_queries", fake_run_eval_queries)
    monkeypatch.setattr(mod, "_get_health", lambda *a, **k: {"status": "ok"})
    report = build_report(
        endpoint_base_url="http://127.0.0.1:8021/v1",
        model="m",
        output_dir=tmp_path,
        queries=[EvalQuery("q1", "Find part number 120-1", "final_gated_answer", "part_number", "120-1")],
        request_timeout=1,
        min_eval_queries=1,
        min_success_count=1,
        min_latency_records=1,
        require_no_answer_permission=True,
    )
    assert report["quality_status"] == "PASS"
    assert Path(report["report_path"]).exists()
    assert Path(report["records_jsonl_path"]).exists()
    assert Path(report["inspect_md_path"]).exists()
