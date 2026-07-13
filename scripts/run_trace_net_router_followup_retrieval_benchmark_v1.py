#!/usr/bin/env python3
"""Run the 180-question TRACE-Net router/follow-up/retrieval benchmark v1."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_query_atom_router_v1 import analyze_query


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def run_retrieval(
    query: str,
    state: Mapping[str, Any],
    *,
    llm_mode: str = "simulate",
    llm_model: str = "gemma4:26b",
    llm_base_url: str = "http://127.0.0.1:11434/v1",
    llm_api_key: str = "ollama",
    request_timeout: int = 240,
) -> Dict[str, Any]:
    from tiff import trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 as v27

    mutable_state = dict(state)
    mutable_state["llm_mode"] = llm_mode
    mutable_state["llm_model"] = llm_model
    mutable_state["llm_base_url"] = llm_base_url
    mutable_state["llm_api_key"] = llm_api_key
    mutable_state["request_timeout"] = request_timeout
    result = v27.run_live_query_v27(
        query,
        mutable_state,
        llm_mode=llm_mode,
        request_timeout=request_timeout,
    )
    retrieval = result.get("retrieval") if isinstance(result.get("retrieval"), Mapping) else {}
    direct = retrieval.get("direct_evidence") if isinstance(retrieval.get("direct_evidence"), list) else []
    return {
        "final_gate_status": result.get("final_gate_status"),
        "direct_evidence_count": len(direct),
        "total_match_count": int(retrieval.get("total_match_count") or 0),
        "final_answer_preview": str(result.get("final_answer") or "")[:500],
    }


def evaluate_record(
    record: Mapping[str, Any],
    *,
    retrieval_state: Optional[Mapping[str, Any]],
    retrieval_config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    query = str(record.get("query") or "")
    decision = analyze_query(query)
    failures: List[str] = []

    expected_route = str(record.get("expected_execution_route") or "")
    expected_tunnel = str(record.get("expected_tunnel") or "")
    if decision.get("execution_route") != expected_route:
        failures.append(f"route:{decision.get('execution_route')}!={expected_route}")
    if decision.get("selected_tunnel") != expected_tunnel:
        failures.append(f"tunnel:{decision.get('selected_tunnel')}!={expected_tunnel}")

    questions = decision.get("clarifying_questions")
    questions = questions if isinstance(questions, list) else []
    min_questions = int(record.get("min_follow_up_questions") or 0)
    if len(questions) < min_questions:
        failures.append(f"follow_up_count:{len(questions)}<{min_questions}")

    actual_topics = set(
        decision.get("follow_up_topics")
        if isinstance(decision.get("follow_up_topics"), list)
        else []
    )
    for topic in record.get("required_follow_up_topics") or []:
        if topic not in actual_topics:
            failures.append(f"missing_follow_up_topic:{topic}")

    for safety_key in ("answer_permission", "final_answer_allowed", "source_truth_mutation_allowed"):
        if decision.get(safety_key):
            failures.append(f"safety_true:{safety_key}")

    retrieval_expectation = str(record.get("retrieval_expectation") or "not_checked")
    retrieval_result: Optional[Dict[str, Any]] = None
    if retrieval_state is not None and retrieval_expectation != "not_checked":
        config = dict(retrieval_config or {})
        retrieval_result = run_retrieval(
            query,
            retrieval_state,
            llm_mode=str(config.get("llm_mode") or "simulate"),
            llm_model=str(config.get("llm_model") or "gemma4:26b"),
            llm_base_url=str(config.get("llm_base_url") or "http://127.0.0.1:11434/v1"),
            llm_api_key=str(config.get("llm_api_key") or "ollama"),
            request_timeout=int(config.get("request_timeout") or 240),
        )
        direct_count = int(retrieval_result["direct_evidence_count"])
        gate = str(retrieval_result["final_gate_status"] or "")
        if retrieval_expectation == "positive":
            if direct_count <= 0:
                failures.append("retrieval_expected_positive_but_no_direct_evidence")
            if gate != "LIVE_ORCHESTRATOR_FINAL_GATE_PASS":
                failures.append(f"retrieval_positive_gate:{gate}")
        elif retrieval_expectation == "negative":
            if direct_count != 0:
                failures.append(f"retrieval_expected_negative_but_direct_count:{direct_count}")
            if gate != "LIVE_ORCHESTRATOR_AUDIT_ONLY":
                failures.append(f"retrieval_negative_gate:{gate}")

    return {
        "question_id": record.get("question_id"),
        "category": record.get("category"),
        "query": query,
        "expected_execution_route": expected_route,
        "actual_execution_route": decision.get("execution_route"),
        "expected_tunnel": expected_tunnel,
        "actual_tunnel": decision.get("selected_tunnel"),
        "clarification_required": decision.get("clarification_required"),
        "clarification_recommended": decision.get("clarification_recommended"),
        "follow_up_question_count": len(questions),
        "follow_up_topics": sorted(actual_topics),
        "clarifying_questions": questions,
        "retrieval_expectation": retrieval_expectation,
        "retrieval": retrieval_result,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "safety_contract": {
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        },
    }


def render_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net Router/Follow-up/Retrieval Benchmark v1",
        "",
        f"- Quality status: **{summary.get('quality_status')}**",
        f"- Questions: `{summary.get('question_count')}`",
        f"- Passed: `{summary.get('pass_count')}`",
        f"- Failed: `{summary.get('fail_count')}`",
        f"- Route accuracy: `{summary.get('route_accuracy_percent')}%`",
        f"- Tunnel accuracy: `{summary.get('tunnel_accuracy_percent')}%`",
        f"- Follow-up policy pass rate: `{summary.get('follow_up_policy_pass_percent')}%`",
        f"- Retrieval checks run: `{summary.get('retrieval_check_count')}`",
        f"- Retrieval checks passed: `{summary.get('retrieval_pass_count')}`",
        "",
        "## Route counts",
        "",
        "```json",
        json.dumps(summary.get("route_counts"), indent=2),
        "```",
        "",
        "## Tunnel counts",
        "",
        "```json",
        json.dumps(summary.get("tunnel_counts"), indent=2),
        "```",
    ]
    failures = summary.get("failed_records") or []
    if failures:
        lines.extend(["", "## Failures", ""])
        for row in failures[:50]:
            lines.append(
                f"- `{row.get('question_id')}` {row.get('query')}: "
                + ", ".join(row.get("failures") or [])
            )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question-bank",
        default="tests/data/trace_net_router_followup_question_bank_v1.json",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional v27 manifest. When provided, positive/negative retrieval checks run.",
    )
    parser.add_argument(
        "--output-dir",
        default="local_data/organization/trace_net/router_followup_retrieval_benchmark_v1",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-question-count", type=int, default=150)
    parser.add_argument(
        "--llm-mode",
        choices=["simulate", "ollama"],
        default="simulate",
        help="Answer-writer mode for manifest retrieval checks.",
    )
    parser.add_argument("--llm-model", default="gemma4:26b")
    parser.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--llm-api-key", default="ollama")
    parser.add_argument("--request-timeout", type=int, default=240)
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable per-question progress lines.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    bank = load_json(Path(args.question_bank))
    rows = bank.get("records")
    if not isinstance(rows, list):
        raise ValueError("Question bank records must be a list")
    if args.limit > 0:
        rows = rows[: args.limit]

    retrieval_state = None
    if args.manifest:
        from tiff import trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 as v27
        retrieval_state = v27.load_state_for_serving(Path(args.manifest))

    valid_rows = [row for row in rows if isinstance(row, Mapping)]
    total = len(valid_rows)
    results = []
    for index, row in enumerate(valid_rows, 1):
        query = str(row.get("query") or "")
        question_id = str(row.get("question_id") or f"q{index:03d}")
        category = str(row.get("category") or "unknown")
        retrieval_expectation = str(row.get("retrieval_expectation") or "not_checked")
        if not args.no_progress:
            print(
                f"[{index}/{total}] RUNNING {question_id} "
                f"category={category} retrieval={retrieval_expectation} "
                f"llm_mode={args.llm_mode} query={query[:140]}",
                flush=True,
            )
        result = evaluate_record(
            row,
            retrieval_state=retrieval_state,
            retrieval_config={
                "llm_mode": args.llm_mode,
                "llm_model": args.llm_model,
                "llm_base_url": args.llm_base_url,
                "llm_api_key": args.llm_api_key,
                "request_timeout": args.request_timeout,
            },
        )
        results.append(result)
        if not args.no_progress:
            retrieval = result.get("retrieval")
            direct_count = (
                int(retrieval.get("direct_evidence_count") or 0)
                if isinstance(retrieval, Mapping)
                else 0
            )
            print(
                f"[{index}/{total}] {result.get('quality_status')} "
                f"route={result.get('actual_execution_route')} "
                f"tunnel={result.get('actual_tunnel')} "
                f"followups={result.get('follow_up_question_count')} "
                f"direct_evidence={direct_count}",
                flush=True,
            )

    route_correct = sum(r["actual_execution_route"] == r["expected_execution_route"] for r in results)
    tunnel_correct = sum(r["actual_tunnel"] == r["expected_tunnel"] for r in results)
    follow_up_pass = sum(
        not any(
            failure.startswith(("follow_up_count:", "missing_follow_up_topic:"))
            for failure in r["failures"]
        )
        for r in results
    )
    retrieval_rows = [
        r
        for r in results
        if r["retrieval_expectation"] != "not_checked" and r["retrieval"] is not None
    ]
    retrieval_pass = sum(
        not any(failure.startswith("retrieval_") for failure in r["failures"])
        for r in retrieval_rows
    )
    failed = [r for r in results if r["quality_status"] != "PASS"]
    quality_failures = []
    if len(results) < args.min_question_count and args.limit <= 0:
        quality_failures.append(f"question_count_below_min:{len(results)}<{args.min_question_count}")
    if failed:
        quality_failures.append(f"failed_record_count:{len(failed)}")

    count = max(1, len(results))
    summary = {
        "status": "TRACE_NET_ROUTER_FOLLOWUP_RETRIEVAL_BENCHMARK_V1_DONE",
        "quality_status": "PASS" if not quality_failures else "FAIL",
        "quality_failures": quality_failures,
        "question_count": len(results),
        "pass_count": len(results) - len(failed),
        "fail_count": len(failed),
        "route_accuracy_percent": round(100.0 * route_correct / count, 2),
        "tunnel_accuracy_percent": round(100.0 * tunnel_correct / count, 2),
        "follow_up_policy_pass_percent": round(100.0 * follow_up_pass / count, 2),
        "retrieval_check_count": len(retrieval_rows),
        "retrieval_pass_count": retrieval_pass,
        "route_counts": dict(Counter(r["actual_execution_route"] for r in results)),
        "tunnel_counts": dict(Counter(r["actual_tunnel"] for r in results)),
        "category_counts": dict(Counter(r["category"] for r in results)),
        "failed_records": failed,
        "manifest": args.manifest or None,
        "llm_mode": args.llm_mode,
        "llm_model": args.llm_model,
        "llm_base_url": args.llm_base_url,
        "request_timeout": args.request_timeout,
        "safety_contract": {
            "read_only": True,
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out / "records.jsonl").open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out / "report.md").write_text(render_markdown(summary), encoding="utf-8")

    for key in (
        "status",
        "quality_status",
        "question_count",
        "pass_count",
        "fail_count",
        "route_accuracy_percent",
        "tunnel_accuracy_percent",
        "follow_up_policy_pass_percent",
        "retrieval_check_count",
        "retrieval_pass_count",
    ):
        print(f"{key}={summary[key]}")
    if quality_failures:
        print("quality_failures=" + json.dumps(quality_failures))
    print("output_dir=" + str(out))
    return 0 if summary["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
