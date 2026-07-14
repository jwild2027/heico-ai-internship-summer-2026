#!/usr/bin/env python3
"""Send every benchmark question through the full-Gemma user-query canary."""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from tiff.trace_net_answer_quality_guard_v1 import evaluate_answer_quality


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * percent
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(
        ordered[lower] + ((ordered[upper] - ordered[lower]) * fraction),
        3,
    )


def post_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    query: str,
    timeout: int,
) -> Tuple[int, Dict[str, Any], float, str]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": query}],
        "temperature": 0,
        "stream": False,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8", errors="replace"))
            elapsed = round((time.perf_counter() - start) * 1000.0, 3)
            return response.status, value if isinstance(value, dict) else {}, elapsed, ""
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            value = {"error": str(exc)}
        elapsed = round((time.perf_counter() - start) * 1000.0, 3)
        return exc.code, value if isinstance(value, dict) else {}, elapsed, str(exc)
    except Exception as exc:
        elapsed = round((time.perf_counter() - start) * 1000.0, 3)
        return 599, {}, elapsed, f"{type(exc).__name__}: {exc}"


def answer_text(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], Mapping) else {}
    message = first.get("message") if isinstance(first.get("message"), Mapping) else {}
    return str(message.get("content") or "").strip()


def evaluate(
    record: Mapping[str, Any],
    *,
    status_code: int,
    response: Mapping[str, Any],
    latency_ms: float,
    transport_error: str,
) -> Dict[str, Any]:
    answer = answer_text(response)
    trace = dict(response.get("trace_net")) if isinstance(response.get("trace_net"), Mapping) else {}
    failures: List[str] = []

    if status_code != 200:
        failures.append(f"http_status:{status_code}")
    if transport_error:
        failures.append(f"transport_error:{transport_error}")
    if not answer:
        failures.append("empty_answer")
    if answer.startswith("{") or "TRACE-NET LIVE CONTEXT PACK" in answer:
        failures.append("internal_or_json_leak")

    expected_route = str(record.get("expected_execution_route") or "")
    expected_tunnel = str(record.get("expected_tunnel") or "")
    actual_route = str(trace.get("route") or "")
    actual_tunnel = str(trace.get("retrieval_tunnel") or "")
    if actual_route != expected_route:
        failures.append(f"route:{actual_route}!={expected_route}")
    if actual_tunnel != expected_tunnel:
        failures.append(f"tunnel:{actual_tunnel}!={expected_tunnel}")

    if not trace.get("response_composer_called"):
        failures.append("gemma_not_called")
    if trace.get("response_composer_status") != "LLM_CALL_SUCCEEDED":
        failures.append(
            f"gemma_status:{trace.get('response_composer_status') or 'missing'}"
        )

    followups = list(trace.get("follow_up_questions") or [])
    minimum = int(record.get("min_follow_up_questions") or 0)
    if len(followups) < minimum:
        failures.append(f"follow_up_count:{len(followups)}<{minimum}")
    if minimum > 0 and "?" not in answer:
        failures.append("followups_not_visible_in_answer")
    failures.extend(evaluate_answer_quality(query=str(record.get("query") or ""), answer=answer, trace=trace))

    for key in (
        "answer_permission",
        "final_answer_allowed",
        "can_answer_directly",
        "can_prove_claims",
        "source_truth_mutation_allowed",
    ):
        if trace.get(key):
            failures.append(f"safety_true:{key}")

    expectation = str(record.get("retrieval_expectation") or "not_checked")
    citations = int(trace.get("citation_count") or 0)
    gate = str(trace.get("final_gate_status") or "")
    if expectation == "positive" and actual_route == "normal_ask":
        if citations <= 0:
            failures.append("positive_query_has_no_citations")
        if gate != "LIVE_ORCHESTRATOR_FINAL_GATE_PASS":
            failures.append(f"positive_query_gate:{gate}")
    elif expectation == "negative" and actual_route == "normal_ask":
        if citations != 0:
            failures.append(f"negative_query_has_citations:{citations}")
        if gate != "LIVE_ORCHESTRATOR_AUDIT_ONLY":
            failures.append(f"negative_query_gate:{gate}")

    return {
        "question_id": record.get("question_id"),
        "category": record.get("category"),
        "query": record.get("query"),
        "expected_route": expected_route,
        "actual_route": actual_route,
        "expected_tunnel": expected_tunnel,
        "actual_tunnel": actual_tunnel,
        "http_status": status_code,
        "latency_ms": latency_ms,
        "transport_error": transport_error,
        "answer": answer,
        "answer_character_count": len(answer),
        "citation_count": citations,
        "final_gate_status": gate,
        "follow_up_questions": followups,
        "response_composer_called": bool(trace.get("response_composer_called")),
        "response_composer_status": trace.get("response_composer_status"),
        "response_composer_model": trace.get("response_composer_model"),
        "response_composer_latency_ms": float(
            trace.get("response_composer_latency_ms") or 0.0
        ),
        "response_composer_validation_failures": list(
            trace.get("response_composer_validation_failures") or []
        ),
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "trace_net": trace,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question-bank",
        default="tests/data/trace_net_router_followup_question_bank_v1.json",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8127")
    parser.add_argument("--api-key", default="trace-net-user-query-canary")
    parser.add_argument(
        "--model",
        default="trace-net-full-gemma-user-query-canary-v1",
    )
    parser.add_argument("--request-timeout", type=int, default=1200)
    parser.add_argument(
        "--output-dir",
        default="local_data/organization/trace_net/full_user_query_gemma_benchmark_v1",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--continue-on-error", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    bank = load_json(Path(args.question_bank))
    rows = bank.get("records")
    if not isinstance(rows, list):
        raise ValueError("Question bank records must be a list")
    records = [row for row in rows if isinstance(row, Mapping)]
    if args.limit > 0:
        records = records[: args.limit]

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records_path = output / "records.jsonl"
    results: List[Dict[str, Any]] = []
    total = len(records)
    all_start = time.perf_counter()

    with records_path.open("w", encoding="utf-8") as handle:
        for index, record in enumerate(records, 1):
            query = str(record.get("query") or "")
            qid = str(record.get("question_id") or f"q{index:03d}")
            category = str(record.get("category") or "unknown")
            print(
                f"[{index}/{total}] USER {qid} category={category} query={query[:160]}",
                flush=True,
            )
            status, response, latency, error = post_chat(
                base_url=args.base_url,
                api_key=args.api_key,
                model=args.model,
                query=query,
                timeout=args.request_timeout,
            )
            result = evaluate(
                record,
                status_code=status,
                response=response,
                latency_ms=latency,
                transport_error=error,
            )
            results.append(result)
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()

            preview = result["answer"].replace("\n", " ")[:180]
            print(
                f"[{index}/{total}] {result['quality_status']} "
                f"route={result['actual_route']} "
                f"tunnel={result['actual_tunnel']} "
                f"gemma={result['response_composer_status']} "
                f"citations={result['citation_count']} "
                f"followups={len(result['follow_up_questions'])} "
                f"latency_ms={result['latency_ms']:.1f}",
                flush=True,
            )
            print(f"[{index}/{total}] ANSWER {preview}", flush=True)

            if status == 599 and not args.continue_on_error:
                print("Transport error; stopping early.", flush=True)
                break

    latencies = [float(row["latency_ms"]) for row in results]
    category_latencies: Dict[str, List[float]] = defaultdict(list)
    for row in results:
        category_latencies[str(row.get("category") or "unknown")].append(
            float(row.get("latency_ms") or 0.0)
        )
    failed = [row for row in results if row["quality_status"] != "PASS"]
    elapsed = round(time.perf_counter() - all_start, 3)

    summary = {
        "status": "TRACE_NET_FULL_USER_QUERY_GEMMA_BENCHMARK_V1_DONE",
        "quality_status": (
            "PASS" if len(results) == total and not failed else "FAIL"
        ),
        "question_count": len(results),
        "expected_question_count": total,
        "pass_count": len(results) - len(failed),
        "fail_count": len(failed),
        "all_questions_sent_as_user_messages": len(results) == total,
        "gemma_call_count": sum(
            bool(row.get("response_composer_called")) for row in results
        ),
        "gemma_success_count": sum(
            row.get("response_composer_status") == "LLM_CALL_SUCCEEDED"
            for row in results
        ),
        "gemma_failure_count": sum(
            row.get("response_composer_status") != "LLM_CALL_SUCCEEDED"
            for row in results
        ),
        "average_latency_ms": round(statistics.mean(latencies), 3) if latencies else 0.0,
        "median_latency_ms": round(statistics.median(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": percentile(latencies, 0.95),
        "minimum_latency_ms": round(min(latencies), 3) if latencies else 0.0,
        "maximum_latency_ms": round(max(latencies), 3) if latencies else 0.0,
        "total_elapsed_seconds": elapsed,
        "average_answer_character_count": round(
            statistics.mean(row["answer_character_count"] for row in results),
            2,
        ) if results else 0.0,
        "route_counts": dict(Counter(row["actual_route"] for row in results)),
        "tunnel_counts": dict(Counter(row["actual_tunnel"] for row in results)),
        "category_counts": dict(Counter(row["category"] for row in results)),
        "category_average_latency_ms": {
            category: round(statistics.mean(values), 3)
            for category, values in sorted(category_latencies.items())
        },
        "failed_records": failed,
        "base_url": args.base_url,
        "model": args.model,
        "output_files": {
            "summary": str(output / "summary.json"),
            "records": str(records_path),
            "report": str(output / "report.md"),
        },
        "safety_contract": {
            "read_only_queries": True,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    report = [
        "# TRACE-Net Full User-Query Gemma Benchmark v1",
        "",
        f"- Quality: **{summary['quality_status']}**",
        f"- Questions: `{summary['question_count']}`",
        f"- Passed: `{summary['pass_count']}`",
        f"- Failed: `{summary['fail_count']}`",
        f"- Gemma successes: `{summary['gemma_success_count']}`",
        f"- Average latency: `{summary['average_latency_ms']} ms`",
        f"- P95 latency: `{summary['p95_latency_ms']} ms`",
        f"- Total elapsed: `{summary['total_elapsed_seconds']} seconds`",
    ]
    if failed:
        report.extend(["", "## Failures", ""])
        for row in failed:
            report.append(
                f"- `{row['question_id']}` {row['query']}: "
                + ", ".join(row["failures"])
            )
    (output / "report.md").write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )

    for key in (
        "status",
        "quality_status",
        "question_count",
        "pass_count",
        "fail_count",
        "all_questions_sent_as_user_messages",
        "gemma_call_count",
        "gemma_success_count",
        "gemma_failure_count",
        "average_latency_ms",
        "median_latency_ms",
        "p95_latency_ms",
        "total_elapsed_seconds",
    ):
        print(f"{key}={summary[key]}")
    print("output_dir=" + str(output))
    return 0 if summary["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
