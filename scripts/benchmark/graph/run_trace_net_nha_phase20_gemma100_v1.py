#!/usr/bin/env python3
"""Run 100 real-Gemma direct-NHA questions through the isolated OpenAI endpoint."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trace_net.graph.trace_net_nha_phase20_gemma100_v1 import (
    EXPECTED_QUESTION_COUNT,
    build_gemma100_answer_key,
    build_gemma100_bank,
    evaluate_model_answer,
    load_phase5_bundle,
    summarize_results,
    write_json,
    write_jsonl,
)


def _parse_stream(raw: str) -> str:
    pieces: list[str] = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        value = line[6:].strip()
        if not value or value == "[DONE]":
            continue
        payload = json.loads(value)
        choices = payload.get("choices") if isinstance(payload, Mapping) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            continue
        delta = choices[0].get("delta")
        if isinstance(delta, Mapping) and delta.get("content"):
            pieces.append(str(delta.get("content")))
    return "".join(pieces)


def _extract_answer(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return ""
    message = choices[0].get("message")
    return str(message.get("content") or "") if isinstance(message, Mapping) else ""


def post_case(
    *,
    base_url: str,
    api_key: str,
    model: str,
    case: Mapping[str, Any],
    timeout: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": str(case.get("query") or "")}],
        "stream": bool(case.get("stream")),
        "temperature": 0,
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
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            headers = {key.casefold(): value for key, value in response.headers.items()}
            if case.get("stream"):
                body: dict[str, Any] = {}
                answer = _parse_stream(raw)
            else:
                body = json.loads(raw)
                answer = _extract_answer(body)
            return {
                "http_status": response.status,
                "headers": headers,
                "answer": answer,
                "body": body,
                "latency_seconds": round(time.perf_counter() - started, 3),
            }
    except urllib.error.HTTPError as exc:
        return {
            "http_status": exc.code,
            "headers": {key.casefold(): value for key, value in exc.headers.items()},
            "answer": "",
            "body": {"error": exc.read().decode("utf-8", errors="replace")},
            "latency_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        return {
            "http_status": 599,
            "headers": {},
            "answer": "",
            "body": {"error": f"{type(exc).__name__}: {exc}"},
            "latency_seconds": round(time.perf_counter() - started, 3),
        }


def evaluate_http_result(case: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    headers = response.get("headers") if isinstance(response.get("headers"), Mapping) else {}
    answer = str(response.get("answer") or "")
    failures: list[str] = []
    status = int(response.get("http_status") or 0)
    model_calls = int(headers.get("x-trace-net-model-calls") or 0)
    writer_source = str(headers.get("x-trace-net-writer-source") or "")
    accepted = str(headers.get("x-trace-net-gemma-accepted") or "") == "1"
    self_rag = str(headers.get("x-trace-net-self-rag") or "")
    prompt_tokens = int(headers.get("x-trace-net-prompt-tokens") or 0)
    completion_tokens = int(headers.get("x-trace-net-completion-tokens") or 0)
    fallback = int(headers.get("x-trace-net-deterministic-fallback") or 0)
    case_header = str(headers.get("x-trace-net-benchmark-case") or "")
    benchmark_only = str(headers.get("x-trace-net-benchmark-only") or "").casefold() == "true"

    if status != 200:
        failures.append(f"http_status:{status}")
    if case_header != str(case.get("case_id") or ""):
        failures.append(f"case_header:{case_header}!={case.get('case_id')}")
    if not benchmark_only:
        failures.append("benchmark_only_header_missing")
    if writer_source != "gemma":
        failures.append("writer_source_not_gemma:" + writer_source)
    if self_rag != "PASS":
        failures.append("self_rag_not_pass:" + self_rag)
    if fallback != 0:
        failures.append("deterministic_fallback_used")

    scored = evaluate_model_answer(
        case,
        answer,
        model_call_count=model_calls,
        writer_accepted=accepted,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    failures.extend(scored.get("failures") or [])
    return {
        "schema_version": "trace_net_nha_phase20_gemma100_http_result_v1",
        "case_id": str(case.get("case_id") or ""),
        "query": str(case.get("query") or ""),
        "stream": bool(case.get("stream")),
        "relationship_id": str(case.get("relationship_id") or ""),
        "template_index": int(case.get("template_index") or 0),
        "child_part": str(case.get("child_part") or ""),
        "expected_direct_nha": str(case.get("expected_direct_nha") or ""),
        "expected_page_id": str(case.get("expected_page_id") or ""),
        "http_status": status,
        "model_call_count": model_calls,
        "writer_source": writer_source,
        "gemma_writer_accepted": accepted,
        "self_rag_pass": self_rag == "PASS",
        "deterministic_fallback_used": bool(fallback),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_seconds": float(response.get("latency_seconds") or 0.0),
        "answer": answer,
        "answer_key_pass": not failures,
        "passed": not failures,
        "failures": list(dict.fromkeys(str(value) for value in failures)),
        "synthetic_artifact_access_count": 1,
        "production_graph_write_count": int(headers.get("x-trace-net-production-graph-writes") or 0),
        "source_artifact_mutation_count": int(headers.get("x-trace-net-source-mutations") or 0),
        "response_body": response.get("body"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8133")
    parser.add_argument("--api-key", default="trace-net-nha-gemma100-benchmark")
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-v1")
    parser.add_argument("--phase5-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    bundle = load_phase5_bundle(args.phase5_dir)
    if bundle.get("quality_status") != "PASS":
        raise SystemExit("phase5 bundle failed: " + ",".join(bundle.get("failures") or []))
    bank = build_gemma100_bank(bundle)
    answer_key = build_gemma100_answer_key(bank, bundle)
    if len(bank) != EXPECTED_QUESTION_COUNT:
        raise SystemExit("question bank count is not 100")

    results: list[dict[str, Any]] = []
    for case in bank:
        response = post_case(
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            case=case,
            timeout=args.timeout_seconds,
        )
        evaluated = evaluate_http_result(case, response)
        results.append(evaluated)
        print(
            f"{evaluated['case_id']} passed={evaluated['passed']} "
            f"gemma={evaluated['model_call_count']} accepted={evaluated['gemma_writer_accepted']} "
            f"latency={evaluated['latency_seconds']}"
        )

    quality = summarize_results(bank, results)
    output_files = {
        "trace_net_nha_phase20_gemma100_bank_v1.json": {"records": bank},
        "trace_net_nha_phase20_gemma100_answer_key_v1.json": answer_key,
        "trace_net_nha_phase20_gemma100_results_v1.json": {"records": results},
        "trace_net_nha_phase20_gemma100_quality_v1.json": quality,
    }
    for filename, payload in output_files.items():
        write_json(output / filename, payload)
    write_jsonl(output / "trace_net_nha_phase20_gemma100_results_v1.jsonl", results)

    summary = {
        "schema_version": "trace_net_nha_phase20_gemma100_summary_v1",
        "module": "run_trace_net_nha_phase20_gemma100_v1",
        "status": "TRACE_NET_NHA_PHASE20_GEMMA100_SUMMARY_V1",
        "quality_status": quality.get("quality_status"),
        "phase5_dir": str(Path(args.phase5_dir).resolve()),
        "output_dir": str(output),
        "counts": quality.get("counts"),
        "latency": quality.get("latency"),
        "failures": quality.get("failures"),
        "warnings": quality.get("warnings"),
        "artifacts": sorted([*output_files, "trace_net_nha_phase20_gemma100_results_v1.jsonl"]),
    }
    write_json(output / "trace_net_nha_phase20_gemma100_summary_v1.json", summary)
    print(json.dumps(quality, indent=2, ensure_ascii=False))
    print("TRACE_NET_NHA_PHASE20_GEMMA100=PASS" if quality.get("quality_status") == "PASS" else "TRACE_NET_NHA_PHASE20_GEMMA100=FAIL")
    if args.strict and quality.get("quality_status") != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE20_GEMMA100=FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
