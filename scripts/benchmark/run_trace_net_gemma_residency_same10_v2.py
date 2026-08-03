#!/usr/bin/env python3
"""Run the same question ten times to isolate TRACE-Net Gemma residency latency."""
from __future__ import annotations

import argparse
import csv
import http.client
import json
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

DEFAULT_QUESTION = (
    "What bigger assembly is 120-20970-001 installed inside? "
    "Use TRACE-Net evidence and cite pages."
)


def get_json(url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        value = json.loads(response.read().decode("utf-8"))
    return dict(value) if isinstance(value, Mapping) else {}


def extract_content(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return ""
    delta = choices[0].get("delta")
    if isinstance(delta, Mapping) and isinstance(delta.get("content"), str):
        return str(delta.get("content") or "")
    message = choices[0].get("message")
    if isinstance(message, Mapping) and isinstance(message.get("content"), str):
        return str(message.get("content") or "")
    return ""


def run_one(
    *,
    parsed: Any,
    api_key: str,
    model: str,
    question: str,
    timeout: float,
    number: int,
    output_dir: Path,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
        "temperature": 0,
        "max_tokens": 256,
        "stream": True,
    }
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_cls(parsed.hostname, parsed.port, timeout=timeout)
    started = time.perf_counter()
    headers_at = first_event_at = first_content_at = None
    status = None
    error = ""
    answer_parts: list[str] = []
    progress_stages: list[str] = []
    raw_lines: list[str] = []
    try:
        connection.request(
            "POST",
            parsed.path.rstrip("/") + "/v1/chat/completions",
            body=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        response = connection.getresponse()
        headers_at = time.perf_counter()
        status = response.status
        for raw in response:
            now = time.perf_counter()
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            raw_lines.append(line)
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            if first_event_at is None:
                first_event_at = now
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            if event.get("object") == "trace_net.progress":
                progress = event.get("trace_net_progress")
                if isinstance(progress, Mapping):
                    progress_stages.append(str(progress.get("stage") or ""))
                continue
            content = extract_content(event)
            if content:
                if first_content_at is None:
                    first_content_at = now
                answer_parts.append(content)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        finished = time.perf_counter()
        connection.close()
    raw_path = output_dir / f"{number:02d}_stream.txt"
    raw_path.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
    elapsed = lambda value: None if value is None else round((value - started) * 1000.0, 3)
    return {
        "number": number,
        "http_status": status,
        "headers_ms": elapsed(headers_at),
        "first_event_ms": elapsed(first_event_at),
        "first_content_ms": elapsed(first_content_at),
        "total_ms": round((finished - started) * 1000.0, 3),
        "progress_stages": progress_stages,
        "answer_character_count": len("".join(answer_parts)),
        "error": error,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://172.17.0.1:8131")
    parser.add_argument("--api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-v1")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--max-first-ratio", type=float, default=2.0)
    parser.add_argument("--max-first-overhead-ms", type=float, default=10000.0)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--require-progress", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(args.base_url)
    health = get_json(args.base_url.rstrip("/") + "/health", min(30.0, args.timeout_seconds))
    (output_dir / "health_before.json").write_text(
        json.dumps(health, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    records = []
    for number in range(1, args.count + 1):
        record = run_one(
            parsed=parsed,
            api_key=args.api_key,
            model=args.model,
            question=args.question,
            timeout=args.timeout_seconds,
            number=number,
            output_dir=output_dir,
        )
        records.append(record)
        print(
            f"[{number:02d}/{args.count:02d}] status={record['http_status']} "
            f"first_event_ms={record['first_event_ms']} "
            f"first_content_ms={record['first_content_ms']} total_ms={record['total_ms']} "
            f"progress={','.join(record['progress_stages']) or 'none'} "
            f"error={record['error'] or 'none'}"
        )
        if number < args.count:
            time.sleep(max(0.0, args.pause_seconds))

    successful = [row for row in records if row["http_status"] == 200 and not row["error"]]
    warm = [float(row["total_ms"]) for row in successful[1:]]
    first_total = float(successful[0]["total_ms"]) if successful else 0.0
    warm_median = statistics.median(warm) if warm else 0.0
    ratio = first_total / warm_median if warm_median > 0 else None
    overhead = first_total - warm_median if warm_median > 0 else None
    failures: list[str] = []
    if health.get("quality_status") != "PASS":
        failures.append("health_not_pass")
    if health.get("gemma_model_resident") is not True:
        failures.append("gemma_not_resident_before_q1")
    if health.get("cold_start_risk") is not False:
        failures.append("cold_start_risk_true_before_q1")
    if len(successful) != args.count:
        failures.append(f"successful_count:{len(successful)}!={args.count}")
    if ratio is None or ratio > args.max_first_ratio:
        failures.append(f"first_ratio:{ratio}>{args.max_first_ratio}")
    if overhead is None or overhead > args.max_first_overhead_ms:
        failures.append(f"first_overhead_ms:{overhead}>{args.max_first_overhead_ms}")
    if args.require_progress:
        missing = [row["number"] for row in records if "request_accepted" not in row["progress_stages"]]
        if missing:
            failures.append("missing_progress:" + ",".join(map(str, missing)))

    summary = {
        "schema_version": "trace_net_gemma_residency_same10_v2",
        "quality_status": "PASS" if not failures else "FAIL",
        "question_count": args.count,
        "successful_question_count": len(successful),
        "first_total_ms": round(first_total, 3),
        "warm_total_median_ms": round(warm_median, 3),
        "first_ratio_vs_warm_median": None if ratio is None else round(ratio, 3),
        "first_overhead_vs_warm_median_ms": None if overhead is None else round(overhead, 3),
        "gemma_model_resident_before_q1": health.get("gemma_model_resident"),
        "cold_start_risk_before_q1": health.get("cold_start_risk"),
        "failure_count": len(failures),
        "failures": failures,
        "records": records,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (output_dir / "records.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "number", "http_status", "headers_ms", "first_event_ms", "first_content_ms",
            "total_ms", "answer_character_count", "error",
        ])
        writer.writeheader()
        for row in records:
            writer.writerow({key: row.get(key) for key in writer.fieldnames})
    print(json.dumps({key: value for key, value in summary.items() if key != "records"}, indent=2))
    print("TRACE_NET_GEMMA_RESIDENCY_SAME10_V2=" + summary["quality_status"])
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
