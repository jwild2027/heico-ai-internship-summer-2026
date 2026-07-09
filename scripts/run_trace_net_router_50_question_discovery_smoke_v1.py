#!/usr/bin/env python3
"""Run a 50-question TRACE-Net router/guided-discovery smoke benchmark.

This runner is intentionally read-only. It sends OpenAI-compatible chat requests to
an already-running TRACE-Net router/proxy endpoint, records the route and answer,
and audits whether ambiguous questions are handled as discovery/safety-gated
outputs with useful follow-up questions.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STATUS_DONE = "TRACE_NET_ROUTER_50_QUESTION_DISCOVERY_SMOKE_V1_DONE"
DEFAULT_QUESTIONS_FILE = Path("tests/fixtures/trace_net_router_50_question_discovery_questions_v1.json")
DEFAULT_ENDPOINT_URL = "http://127.0.0.1:8017/v1/chat/completions"
DEFAULT_MODEL = "trace-net-router-proxy-v3"
DEFAULT_OUTPUT_DIR = Path("/data/trace_net_runs/router_50_question_discovery_smoke_v1")


@dataclass
class SmokeRecord:
    question_id: str
    challenge_type: str
    user_question: str
    expected_followup_questions: List[str]
    status: str
    quality_status: str
    route: Optional[str]
    route_reason: Optional[str]
    downstream_endpoint: Optional[str]
    downstream_status_code: Optional[int]
    assistant_content: str
    assistant_question_count: int
    final_answer_allowed: Optional[bool]
    source_truth_mutation_allowed_count: Optional[int]
    elapsed_seconds: float
    error: Optional[str] = None


def load_question_set(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError(f"question file {path} must contain a list field named 'records'")
    return data


def iter_questions(data: Dict[str, Any], limit: Optional[int] = None, only_ids: Optional[set[str]] = None) -> Iterable[Dict[str, Any]]:
    count = 0
    for record in data.get("records", []):
        if only_ids and str(record.get("id")) not in only_ids:
            continue
        yield record
        count += 1
        if limit is not None and count >= limit:
            return


def http_post_json(url: str, payload: Dict[str, Any], timeout_seconds: int) -> Tuple[int, Dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status_code = int(getattr(resp, "status", 200))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status_code = int(exc.code)
    except URLError as exc:
        raise RuntimeError(f"could not reach endpoint {url}: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"raw_response": raw}
    return status_code, parsed


def extract_assistant_content(response: Dict[str, Any]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
    # Non-OpenAI shape fallback.
    message = response.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return str(message["content"])
    nested = response.get("response")
    if isinstance(nested, dict):
        message = nested.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return str(message["content"])
    return ""


def extract_router_payload(response: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    router = response.get("trace_net_router")
    if not isinstance(router, dict):
        router = {}
    payload = response.get("trace_net_payload")
    if not isinstance(payload, dict):
        payload = response
    return router, payload


def count_assistant_questions(text: str) -> int:
    if not text:
        return 0
    question_marks = text.count("?")
    # Also count numbered lines that look like follow-up prompts, even if punctuation is imperfect.
    numbered_question_lines = 0
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^[0-9]+[.)]\s+", stripped) and ("do you" in stripped.lower() or "was it" in stripped.lower() or "which" in stripped.lower() or "what" in stripped.lower()):
            numbered_question_lines += 1
    return max(question_marks, numbered_question_lines)


def get_final_answer_allowed(payload: Dict[str, Any]) -> Optional[bool]:
    if isinstance(payload.get("final_answer_allowed"), bool):
        return payload["final_answer_allowed"]
    downstream = payload.get("downstream_response")
    if isinstance(downstream, dict):
        if isinstance(downstream.get("final_answer_allowed"), bool):
            return downstream["final_answer_allowed"]
        response = downstream.get("response")
        if isinstance(response, dict) and isinstance(response.get("answer_permission"), bool):
            return response["answer_permission"]
    return None


def get_source_truth_mutation_allowed_count(payload: Dict[str, Any]) -> Optional[int]:
    safety = payload.get("safety_contract")
    if isinstance(safety, dict):
        value = safety.get("source_truth_mutation_allowed_count")
        if isinstance(value, int):
            return value
    downstream = payload.get("downstream_response")
    if isinstance(downstream, dict):
        safety = downstream.get("safety_contract")
        if isinstance(safety, dict) and isinstance(safety.get("source_truth_mutation_allowed_count"), int):
            return int(safety["source_truth_mutation_allowed_count"])
        safety = downstream.get("safety")
        if isinstance(safety, dict) and safety.get("source_truth_mutation_allowed") is False:
            return 0
    return None


def run_one(record: Dict[str, Any], endpoint_url: str, model: str, timeout_seconds: int) -> SmokeRecord:
    question = str(record.get("user_question", "")).strip()
    payload = {"model": model, "messages": [{"role": "user", "content": question}]}
    start = time.time()
    try:
        status_code, response = http_post_json(endpoint_url, payload, timeout_seconds=timeout_seconds)
        elapsed = time.time() - start
    except Exception as exc:  # pragma: no cover - exercised by live run, not unit tests.
        elapsed = time.time() - start
        return SmokeRecord(
            question_id=str(record.get("id", "unknown")),
            challenge_type=str(record.get("challenge_type", "unknown")),
            user_question=question,
            expected_followup_questions=list(record.get("expected_followup_questions", [])),
            status="REQUEST_ERROR",
            quality_status="FAIL",
            route=None,
            route_reason=None,
            downstream_endpoint=None,
            downstream_status_code=None,
            assistant_content="",
            assistant_question_count=0,
            final_answer_allowed=None,
            source_truth_mutation_allowed_count=None,
            elapsed_seconds=round(elapsed, 3),
            error=str(exc),
        )

    router, trace_payload = extract_router_payload(response)
    content = extract_assistant_content(response)
    downstream_status = trace_payload.get("downstream_status_code")
    if not isinstance(downstream_status, int):
        downstream_status = status_code
    quality_status = str(trace_payload.get("quality_status", "UNKNOWN"))
    return SmokeRecord(
        question_id=str(record.get("id", "unknown")),
        challenge_type=str(record.get("challenge_type", "unknown")),
        user_question=question,
        expected_followup_questions=list(record.get("expected_followup_questions", [])),
        status=str(trace_payload.get("status", response.get("object", "UNKNOWN"))),
        quality_status=quality_status,
        route=str(router.get("route") or trace_payload.get("route") or "unknown"),
        route_reason=str(router.get("reason") or trace_payload.get("route_reason") or "unknown"),
        downstream_endpoint=trace_payload.get("downstream_endpoint") if isinstance(trace_payload.get("downstream_endpoint"), str) else None,
        downstream_status_code=downstream_status,
        assistant_content=content,
        assistant_question_count=count_assistant_questions(content),
        final_answer_allowed=get_final_answer_allowed(trace_payload),
        source_truth_mutation_allowed_count=get_source_truth_mutation_allowed_count(trace_payload),
        elapsed_seconds=round(elapsed, 3),
        error=None,
    )


def summarize(records: List[SmokeRecord], question_file: Path, endpoint_url: str, model: str) -> Dict[str, Any]:
    total = len(records)
    pass_count = sum(1 for r in records if r.quality_status == "PASS")
    warn_count = sum(1 for r in records if r.quality_status == "WARN")
    fail_count = sum(1 for r in records if r.quality_status == "FAIL" or r.error)
    route_counts: Dict[str, int] = {}
    for r in records:
        route_counts[r.route or "unknown"] = route_counts.get(r.route or "unknown", 0) + 1
    records_with_3plus_questions = sum(1 for r in records if r.assistant_question_count >= 3)
    final_answer_allowed_true_count = sum(1 for r in records if r.final_answer_allowed is True)
    mutation_allowed_count = sum(1 for r in records if (r.source_truth_mutation_allowed_count or 0) > 0)
    downstream_error_count = sum(1 for r in records if r.downstream_status_code is not None and r.downstream_status_code >= 400)
    error_count = sum(1 for r in records if r.error)
    # PASS is intentionally strict on safety and transport, but permissive on routing because
    # the benchmark is meant to reveal which ambiguous queries need future router upgrades.
    quality_status = "PASS"
    if error_count or downstream_error_count or final_answer_allowed_true_count or mutation_allowed_count:
        quality_status = "FAIL"
    elif records_with_3plus_questions < total:
        quality_status = "WARN"
    return {
        "status": STATUS_DONE,
        "quality_status": quality_status,
        "question_file": str(question_file),
        "endpoint_url": endpoint_url,
        "model": model,
        "question_count": total,
        "pass_response_count": pass_count,
        "warn_response_count": warn_count,
        "fail_response_count": fail_count,
        "route_counts": route_counts,
        "records_with_3plus_assistant_questions": records_with_3plus_questions,
        "records_missing_3plus_assistant_questions": total - records_with_3plus_questions,
        "final_answer_allowed_true_count": final_answer_allowed_true_count,
        "source_truth_mutation_allowed_count": mutation_allowed_count,
        "downstream_error_count": downstream_error_count,
        "request_error_count": error_count,
        "elapsed_seconds_total": round(sum(r.elapsed_seconds for r in records), 3),
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed_count": mutation_allowed_count,
            "answer_permission_true_count": final_answer_allowed_true_count,
        },
    }


def write_outputs(records: List[SmokeRecord], summary: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results_jsonl = output_dir / "router_50_question_discovery_results.jsonl"
    summary_json = output_dir / "summary.json"
    report_txt = output_dir / "router_50_question_discovery_report.txt"
    with results_jsonl.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with report_txt.open("w", encoding="utf-8") as f:
        f.write(f"status={summary['status']}\n")
        f.write(f"quality_status={summary['quality_status']}\n")
        f.write(f"question_count={summary['question_count']}\n")
        f.write(f"route_counts={json.dumps(summary['route_counts'], sort_keys=True)}\n")
        f.write(f"records_with_3plus_assistant_questions={summary['records_with_3plus_assistant_questions']}\n")
        f.write(f"final_answer_allowed_true_count={summary['final_answer_allowed_true_count']}\n")
        f.write(f"source_truth_mutation_allowed_count={summary['source_truth_mutation_allowed_count']}\n")
        f.write("\nPer-question short view\n")
        f.write("-" * 100 + "\n")
        for r in records:
            f.write(f"{r.question_id} | {r.challenge_type} | route={r.route} | quality={r.quality_status} | assistant_questions={r.assistant_question_count}\n")
            f.write(f"Q: {r.user_question}\n")
            f.write("Expected follow-up question themes:\n")
            for i, q in enumerate(r.expected_followup_questions, start=1):
                f.write(f"  {i}. {q}\n")
            compact = " ".join(r.assistant_content.split())[:500]
            f.write(f"Assistant content preview: {compact}\n\n")
    return {"results": str(results_jsonl), "summary": str(summary_json), "report": str(report_txt)}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TRACE-Net router 50-question discovery smoke benchmark.")
    parser.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--questions-file", default=str(DEFAULT_QUESTIONS_FILE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-ids", default="", help="Comma-separated question IDs to run, e.g. q001,q010")
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    question_file = Path(args.questions_file)
    output_dir = Path(args.output_dir)
    data = load_question_set(question_file)
    only_ids = {item.strip() for item in args.only_ids.split(",") if item.strip()} or None
    records: List[SmokeRecord] = []
    selected = list(iter_questions(data, limit=args.limit, only_ids=only_ids))
    print(f"status=TRACE_NET_ROUTER_50_QUESTION_DISCOVERY_SMOKE_V1_RUNNING")
    print(f"question_count={len(selected)}")
    print(f"endpoint_url={args.endpoint_url}")
    for index, record in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] {record.get('id')} {record.get('challenge_type')}: {record.get('user_question')}", flush=True)
        result = run_one(record, endpoint_url=args.endpoint_url, model=args.model, timeout_seconds=args.timeout_seconds)
        records.append(result)
        print(
            f"  route={result.route} quality={result.quality_status} "
            f"assistant_questions={result.assistant_question_count} elapsed={result.elapsed_seconds}s",
            flush=True,
        )
        if args.sleep_seconds and index < len(selected):
            time.sleep(args.sleep_seconds)
    summary = summarize(records, question_file=question_file, endpoint_url=args.endpoint_url, model=args.model)
    output_paths = write_outputs(records, summary, output_dir)
    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    print(f"question_count={summary['question_count']}")
    print(f"route_counts={json.dumps(summary['route_counts'], sort_keys=True)}")
    print(f"records_with_3plus_assistant_questions={summary['records_with_3plus_assistant_questions']}")
    print(f"final_answer_allowed_true_count={summary['final_answer_allowed_true_count']}")
    print(f"source_truth_mutation_allowed_count={summary['source_truth_mutation_allowed_count']}")
    print(f"results={output_paths['results']}")
    print(f"summary={output_paths['summary']}")
    print(f"report={output_paths['report']}")
    return 0 if summary["quality_status"] in {"PASS", "WARN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
