#!/usr/bin/env python3
"""Run an exact-query TRACE-Net router normal_ask smoke benchmark.

This benchmark complements the guided-discovery 50-question smoke. It verifies
that exact part-number lookup requests continue to route to the normal TRACE-Net
ask path, while keeping response text clean and safety flags locked.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

STATUS_DONE = "TRACE_NET_ROUTER_EXACT_NORMAL_ASK_SMOKE_V1_DONE"
DEFAULT_MODEL = "trace-net-router-proxy-v6"
DEFAULT_ENDPOINT_URL = "http://127.0.0.1:8017/v1/chat/completions"
DEFAULT_EXPECTED_ROUTE = "normal_ask"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return default
    return default


def load_questions(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        questions = data.get("questions")
    else:
        questions = data
    if not isinstance(questions, list) or not questions:
        raise ValueError(f"questions file must contain a non-empty list: {path}")

    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"question #{index} is not an object")
        question = item.get("user_question") or item.get("question") or item.get("query")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"question #{index} is missing user_question/question/query text")
        normalized.append(
            {
                "question_id": str(item.get("question_id") or item.get("id") or f"exact_{index:03d}"),
                "challenge_type": str(item.get("challenge_type") or "exact_normal_ask"),
                "user_question": question.strip(),
                "expected_route": str(item.get("expected_route") or DEFAULT_EXPECTED_ROUTE),
                "expected_behavior": item.get("expected_behavior") or [],
            }
        )
    return normalized


def extract_assistant_content(response_json: Mapping[str, Any]) -> str:
    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
    content = response_json.get("assistant_content")
    return content if isinstance(content, str) else ""


def extract_trace_payload(response_json: Mapping[str, Any]) -> Dict[str, Any]:
    payload = response_json.get("trace_net_payload")
    if isinstance(payload, dict):
        return dict(payload)
    payload = response_json.get("trace_payload")
    if isinstance(payload, dict):
        return dict(payload)
    # Some non-OpenAI smoke endpoints return the route fields at the top level.
    route_keys = {
        "route",
        "route_reason",
        "quality_status",
        "downstream_endpoint",
        "downstream_status_code",
        "final_answer_allowed",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    }
    if any(key in response_json for key in route_keys):
        return {key: response_json.get(key) for key in route_keys if key in response_json}
    return {}


def looks_like_json_blob_content(content: str) -> bool:
    stripped = content.strip()
    if not stripped:
        return False
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return False
    marker_text = stripped[:1500].lower()
    return any(
        marker in marker_text
        for marker in (
            "trace_net_payload",
            "downstream_endpoint",
            "source_truth_mutation",
            "final_answer_allowed",
            "route_reason",
        )
    )


def _recursive_list_count(value: Any, candidate_keys: Iterable[str]) -> int:
    candidate_key_set = set(candidate_keys)
    if isinstance(value, dict):
        total = 0
        for key, child in value.items():
            if key in candidate_key_set and isinstance(child, list):
                total += len(child)
            total += _recursive_list_count(child, candidate_key_set)
        return total
    if isinstance(value, list):
        return sum(_recursive_list_count(child, candidate_key_set) for child in value)
    return 0


def count_citations(response_json: Mapping[str, Any], payload: Mapping[str, Any]) -> int:
    return _recursive_list_count(response_json, {"citations", "citation_records", "source_citations"}) + _recursive_list_count(
        payload, {"citations", "citation_records", "source_citations"}
    )


def _safety_count(payload: Mapping[str, Any], key: str) -> int:
    safety = payload.get("safety_contract")
    if not isinstance(safety, dict):
        safety = {}
    return _as_int(payload.get(key, safety.get(key, 0)), 0)


def route_record(question: Mapping[str, Any], response_json: Mapping[str, Any], http_status: int, elapsed_seconds: float) -> Dict[str, Any]:
    payload = extract_trace_payload(response_json)
    content = extract_assistant_content(response_json)
    route = payload.get("route")
    expected_route = question.get("expected_route") or DEFAULT_EXPECTED_ROUTE
    citation_count = count_citations(response_json, payload)

    final_answer_allowed = _truthy(payload.get("final_answer_allowed")) or _truthy(payload.get("answer_permission"))
    source_truth_mutation_count = _safety_count(payload, "source_truth_mutation_allowed_count")
    postgres_write_count = _safety_count(payload, "postgres_write_attempt_count")
    qdrant_write_count = _safety_count(payload, "qdrant_write_attempt_count")
    opensearch_write_count = _safety_count(payload, "opensearch_write_attempt_count")
    json_blob_content = looks_like_json_blob_content(content)

    failure_reasons: List[str] = []
    if http_status != 200:
        failure_reasons.append(f"http_status_{http_status}")
    if route != expected_route:
        failure_reasons.append(f"route_mismatch_expected_{expected_route}_got_{route}")
    if not payload:
        failure_reasons.append("missing_trace_net_payload")
    if json_blob_content:
        failure_reasons.append("assistant_content_looks_like_raw_json_blob")
    if final_answer_allowed:
        failure_reasons.append("final_answer_allowed_true")
    if source_truth_mutation_count:
        failure_reasons.append("source_truth_mutation_allowed_nonzero")
    if postgres_write_count or qdrant_write_count or opensearch_write_count:
        failure_reasons.append("write_attempt_count_nonzero")

    downstream_status_code = payload.get("downstream_status_code")
    if _as_int(downstream_status_code, 200) >= 400:
        failure_reasons.append(f"downstream_status_{downstream_status_code}")

    return {
        "question_id": question.get("question_id"),
        "challenge_type": question.get("challenge_type"),
        "user_question": question.get("user_question"),
        "expected_route": expected_route,
        "status": STATUS_DONE,
        "quality_status": "FAIL" if failure_reasons else "PASS",
        "failure_reasons": failure_reasons,
        "http_status": http_status,
        "route": route,
        "route_reason": payload.get("route_reason"),
        "downstream_endpoint": payload.get("downstream_endpoint"),
        "downstream_status_code": downstream_status_code,
        "assistant_content": content,
        "assistant_content_preview": " ".join(content.split())[:500],
        "assistant_content_looks_like_json_blob": json_blob_content,
        "trace_net_payload_present": bool(payload),
        "citation_count": citation_count,
        "citation_backed_response": citation_count > 0,
        "final_answer_allowed": final_answer_allowed,
        "source_truth_mutation_allowed_count": source_truth_mutation_count,
        "postgres_write_attempt_count": postgres_write_count,
        "qdrant_write_attempt_count": qdrant_write_count,
        "opensearch_write_attempt_count": opensearch_write_count,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "raw_response_keys": sorted(response_json.keys()),
        "error": None,
    }


def error_record(question: Mapping[str, Any], error: str, elapsed_seconds: float) -> Dict[str, Any]:
    return {
        "question_id": question.get("question_id"),
        "challenge_type": question.get("challenge_type"),
        "user_question": question.get("user_question"),
        "expected_route": question.get("expected_route") or DEFAULT_EXPECTED_ROUTE,
        "status": STATUS_DONE,
        "quality_status": "FAIL",
        "failure_reasons": ["request_error"],
        "http_status": None,
        "route": "unknown",
        "route_reason": None,
        "downstream_endpoint": None,
        "downstream_status_code": None,
        "assistant_content": "",
        "assistant_content_preview": "",
        "assistant_content_looks_like_json_blob": False,
        "trace_net_payload_present": False,
        "citation_count": 0,
        "citation_backed_response": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "raw_response_keys": [],
        "error": error,
    }


def call_endpoint(endpoint_url: str, model: str, question: str, timeout_seconds: float) -> Tuple[int, Dict[str, Any]]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
    }
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        endpoint_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(response_body)
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError:
            parsed = {"error": response_body}
        return exc.code, parsed


def summarize_records(
    records: List[Mapping[str, Any]],
    *,
    question_file: str,
    endpoint_url: str,
    model: str,
    min_normal_ask_count: int,
    min_citation_backed_response_count: int,
    elapsed_seconds_total: float,
) -> Dict[str, Any]:
    route_counts = Counter(str(record.get("route")) for record in records)
    fail_response_count = sum(1 for record in records if record.get("quality_status") == "FAIL")
    pass_response_count = sum(1 for record in records if record.get("quality_status") == "PASS")
    normal_ask_count = route_counts.get("normal_ask", 0)
    citation_backed_response_count = sum(1 for record in records if record.get("citation_backed_response"))
    total_citation_count = sum(_as_int(record.get("citation_count"), 0) for record in records)
    missing_payload_count = sum(1 for record in records if not record.get("trace_net_payload_present"))
    json_blob_content_count = sum(1 for record in records if record.get("assistant_content_looks_like_json_blob"))
    route_mismatch_count = sum(1 for record in records if record.get("route") != record.get("expected_route"))
    request_error_count = sum(1 for record in records if record.get("error"))
    downstream_error_count = sum(1 for record in records if _as_int(record.get("downstream_status_code"), 200) >= 400)
    final_answer_allowed_true_count = sum(1 for record in records if record.get("final_answer_allowed"))
    source_truth_mutation_allowed_count = sum(_as_int(record.get("source_truth_mutation_allowed_count"), 0) for record in records)
    postgres_write_attempt_count = sum(_as_int(record.get("postgres_write_attempt_count"), 0) for record in records)
    qdrant_write_attempt_count = sum(_as_int(record.get("qdrant_write_attempt_count"), 0) for record in records)
    opensearch_write_attempt_count = sum(_as_int(record.get("opensearch_write_attempt_count"), 0) for record in records)

    failure_conditions = {
        "fail_response_count": fail_response_count,
        "route_mismatch_count": route_mismatch_count,
        "missing_payload_count": missing_payload_count,
        "json_blob_content_count": json_blob_content_count,
        "request_error_count": request_error_count,
        "downstream_error_count": downstream_error_count,
        "final_answer_allowed_true_count": final_answer_allowed_true_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": postgres_write_attempt_count,
        "qdrant_write_attempt_count": qdrant_write_attempt_count,
        "opensearch_write_attempt_count": opensearch_write_attempt_count,
        "normal_ask_shortfall": max(0, min_normal_ask_count - normal_ask_count),
        "citation_backed_shortfall": max(0, min_citation_backed_response_count - citation_backed_response_count),
    }
    quality_status = "PASS" if all(value == 0 for value in failure_conditions.values()) else "FAIL"

    return {
        "status": STATUS_DONE,
        "quality_status": quality_status,
        "question_file": question_file,
        "endpoint_url": endpoint_url,
        "model": model,
        "question_count": len(records),
        "pass_response_count": pass_response_count,
        "fail_response_count": fail_response_count,
        "route_counts": dict(sorted(route_counts.items())),
        "normal_ask_count": normal_ask_count,
        "min_normal_ask_count": min_normal_ask_count,
        "route_mismatch_count": route_mismatch_count,
        "records_with_trace_net_payload": len(records) - missing_payload_count,
        "missing_trace_net_payload_count": missing_payload_count,
        "json_blob_content_count": json_blob_content_count,
        "citation_backed_response_count": citation_backed_response_count,
        "min_citation_backed_response_count": min_citation_backed_response_count,
        "total_citation_count": total_citation_count,
        "final_answer_allowed_true_count": final_answer_allowed_true_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": postgres_write_attempt_count,
        "qdrant_write_attempt_count": qdrant_write_attempt_count,
        "opensearch_write_attempt_count": opensearch_write_attempt_count,
        "downstream_error_count": downstream_error_count,
        "request_error_count": request_error_count,
        "elapsed_seconds_total": round(elapsed_seconds_total, 3),
        "failure_conditions": failure_conditions,
        "safety_contract": {
            "read_only": True,
            "final_answer_allowed_true_count": final_answer_allowed_true_count,
            "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
            "postgres_write_attempt_count": postgres_write_attempt_count,
            "qdrant_write_attempt_count": qdrant_write_attempt_count,
            "opensearch_write_attempt_count": opensearch_write_attempt_count,
        },
    }


def write_report(summary: Mapping[str, Any], records: List[Mapping[str, Any]], path: Path) -> None:
    lines: List[str] = []
    lines.append(f"status={summary['status']}")
    lines.append(f"quality_status={summary['quality_status']}")
    lines.append(f"question_count={summary['question_count']}")
    lines.append(f"route_counts={json.dumps(summary['route_counts'])}")
    lines.append(f"normal_ask_count={summary['normal_ask_count']}")
    lines.append(f"records_with_trace_net_payload={summary['records_with_trace_net_payload']}")
    lines.append(f"json_blob_content_count={summary['json_blob_content_count']}")
    lines.append(f"citation_backed_response_count={summary['citation_backed_response_count']}")
    lines.append(f"total_citation_count={summary['total_citation_count']}")
    lines.append(f"final_answer_allowed_true_count={summary['final_answer_allowed_true_count']}")
    lines.append(f"source_truth_mutation_allowed_count={summary['source_truth_mutation_allowed_count']}")
    lines.append("")
    lines.append("Per-question short view")
    lines.append("-" * 100)
    for record in records:
        lines.append(
            f"{record.get('question_id')} | {record.get('challenge_type')} | "
            f"route={record.get('route')} | expected={record.get('expected_route')} | "
            f"quality={record.get('quality_status')} | citations={record.get('citation_count')}"
        )
        if record.get("failure_reasons"):
            lines.append(f"Failure reasons: {', '.join(record.get('failure_reasons') or [])}")
        lines.append(f"Q: {record.get('user_question')}")
        lines.append(f"Assistant content preview: {record.get('assistant_content_preview')}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_benchmark(args: argparse.Namespace) -> int:
    questions_path = Path(args.questions_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    questions = load_questions(questions_path)
    min_normal_ask_count = args.min_normal_ask_count
    if min_normal_ask_count is None:
        min_normal_ask_count = len(questions)

    started = time.time()
    records: List[Dict[str, Any]] = []
    for question in questions:
        request_started = time.time()
        try:
            http_status, response_json = call_endpoint(
                args.endpoint_url,
                args.model,
                str(question["user_question"]),
                args.timeout_seconds,
            )
            records.append(route_record(question, response_json, http_status, time.time() - request_started))
        except Exception as exc:  # pragma: no cover - exercised by live failures.
            records.append(error_record(question, repr(exc), time.time() - request_started))

    elapsed = time.time() - started
    summary = summarize_records(
        records,
        question_file=str(questions_path),
        endpoint_url=args.endpoint_url,
        model=args.model,
        min_normal_ask_count=min_normal_ask_count,
        min_citation_backed_response_count=args.min_citation_backed_response_count,
        elapsed_seconds_total=elapsed,
    )

    results_path = output_dir / "router_exact_normal_ask_results.jsonl"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "router_exact_normal_ask_report.txt"

    with results_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    write_report(summary, records, report_path)

    print(f"quality_status={summary['quality_status']}")
    print(f"question_count={summary['question_count']}")
    print(f"route_counts={json.dumps(summary['route_counts'])}")
    print(f"normal_ask_count={summary['normal_ask_count']}")
    print(f"records_with_trace_net_payload={summary['records_with_trace_net_payload']}")
    print(f"json_blob_content_count={summary['json_blob_content_count']}")
    print(f"citation_backed_response_count={summary['citation_backed_response_count']}")
    print(f"final_answer_allowed_true_count={summary['final_answer_allowed_true_count']}")
    print(f"source_truth_mutation_allowed_count={summary['source_truth_mutation_allowed_count']}")
    print(f"results={results_path}")
    print(f"summary={summary_path}")
    print(f"report={report_path}")

    return 0 if summary["quality_status"] == "PASS" else 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--questions-file",
        default="tests/fixtures/trace_net_router_exact_normal_ask_questions_v1.json",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--min-normal-ask-count", type=int, default=None)
    parser.add_argument("--min-citation-backed-response-count", type=int, default=0)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_benchmark(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
