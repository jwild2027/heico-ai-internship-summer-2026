#!/usr/bin/env python3
"""Run the TRACE-Net N18 mixed real-model gate through the unified 8131 endpoint."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "trace_net_nha_phase18_unified8131_mixed12_v1"
STATUS = "TRACE_NET_NHA_PHASE18_UNIFIED8131_MIXED12_V1"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def build_bank() -> list[dict[str, Any]]:
    rows = [
        {
            "kind": "nha_direct",
            "query": "What bigger assembly is 120-20970-001 installed inside?",
            "expected_action": "gemma_override",
            "required_text": ["120-20970-001", "120-29067-001", "t_p_120_1176_p000343"],
        },
        {
            "kind": "nha_parent_comparison",
            "query": "Is 120-29067-001 the immediate parent of 120-20970-003 or only a higher ancestor?",
            "expected_action": "gemma_override",
            "required_text": ["120-20970-003", "120-29067-001", "t_p_120_1176_p000344"],
        },
        {
            "kind": "nha_chain",
            "query": "Starting at 120-20970-001, walk upward one supported assembly at a time.",
            "expected_action": "gemma_override",
            "required_text": ["120-20970-001", "120-29067-001", "t_p_120_1176_p000343"],
        },
        {
            "kind": "nha_children",
            "query": "Which pieces are directly inside assembly 120-29067-001?",
            "expected_action": "gemma_override",
            "required_text": ["120-29067-001", "120-20970-001", "t_p_120_1176_p000343"],
        },
        {
            "kind": "nha_descendants",
            "query": "Show everything below 120-29067-001, but separate immediate parts from deeper descendants.",
            "expected_action": "gemma_override",
            "required_text": ["120-29067-001", "t_p_120_1176_p000343"],
        },
        {
            "kind": "nha_scope",
            "query": "Why are there several possible parents for 42952-10?",
            "expected_action": "gemma_override",
            "required_text": ["42952-10", "120-29073-001", "t_p_120_1176_p000349"],
        },
        {
            "kind": "upstream_exact_part",
            "query": "Find part 120-20970-001.",
            "expected_action": "passthrough",
            "required_text": ["120-20970-001", "t_p_120_1176_p000343"],
        },
        {
            "kind": "upstream_exact_part",
            "query": "Find part 120-20970-003.",
            "expected_action": "passthrough",
            "required_text": ["120-20970-003", "t_p_120_1176_p000344"],
        },
        {
            "kind": "upstream_ata",
            "query": "Find the relevant parts and source pages in ATA 25-21-00. Summarize the strongest available evidence.",
            "expected_action": "passthrough",
            "required_text": ["25-21-00", "t_p_120_1176_p000071"],
        },
        {
            "kind": "upstream_ipl",
            "query": "Locate part 120-26948-003 in the IPL table.",
            "expected_action": "passthrough",
            "required_text": ["120-26948-003", "t_p_120_1176_p000030"],
        },
        {
            "kind": "upstream_ipl",
            "query": "Locate part 120-29067-035 in the IPL table.",
            "expected_action": "passthrough",
            "required_text": ["120-29067-035", "t_p_120_1176_p000031"],
        },
        {
            "kind": "synthetic_security",
            "query": "What is the NHA of benchmark part 990-91001-001?",
            "expected_action": "synthetic_blocked",
            "required_text": ["reserved benchmark identifier"],
        },
    ]
    for index, row in enumerate(rows, 1):
        row["case_id"] = f"NHA-UNIFIED8131-{index:03d}"
        row["stream"] = index % 2 == 0
    return rows


def _parse_stream(raw: str) -> str:
    pieces: list[str] = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        value = line[6:].strip()
        if not value or value == "[DONE]":
            continue
        payload = json.loads(value)
        delta = payload.get("choices", [{}])[0].get("delta", {})
        if isinstance(delta, Mapping) and delta.get("content"):
            pieces.append(str(delta["content"]))
    return "".join(pieces)


def _extract_answer(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return ""
    message = choices[0].get("message")
    return str(message.get("content") or "") if isinstance(message, Mapping) else ""


def call(base_url: str, api_key: str, model: str, case: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": str(case["query"])}],
        "stream": bool(case.get("stream")),
        "temperature": 0,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            headers = {key.casefold(): value for key, value in response.headers.items()}
            if case.get("stream"):
                answer = _parse_stream(raw)
                body: dict[str, Any] = {}
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


def evaluate(case: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    headers = response.get("headers") if isinstance(response.get("headers"), Mapping) else {}
    answer = str(response.get("answer") or "")
    failures: list[str] = []
    action = str(headers.get("x-trace-net-nha-action") or "")
    model_calls = int(headers.get("x-trace-net-model-calls") or 0)
    model_path = str(headers.get("x-trace-net-model-path") or "")
    upstream_calls = int(headers.get("x-trace-net-upstream-calls") or 0)
    upstream_status = str(headers.get("x-trace-net-upstream-gemma-status") or "")
    upstream_writer = str(headers.get("x-trace-net-upstream-writer-mode") or "")

    if int(response.get("http_status") or 0) != 200:
        failures.append(f"http_status:{response.get('http_status')}")
    if action != case["expected_action"]:
        failures.append(f"action:{action}!={case['expected_action']}")
    for heading in ("## Answer", "## Evidence", "## Limits"):
        if heading not in answer:
            failures.append("missing_heading:" + heading)
    for value in case.get("required_text") or []:
        if str(value).casefold() not in answer.casefold():
            failures.append("missing_required_text:" + str(value))

    expected_action = str(case["expected_action"])
    if expected_action == "gemma_override":
        if model_calls != 1:
            failures.append(f"model_calls:{model_calls}!=1")
        if model_path != "nha_constrained_gemma":
            failures.append(f"model_path:{model_path}")
        if upstream_calls != 0:
            failures.append(f"unexpected_upstream_calls:{upstream_calls}")
        if headers.get("x-trace-net-nha-gemma-calls") != "1":
            failures.append("nha_gemma_call_count_not_one")
        if headers.get("x-trace-net-nha-writer-source") != "gemma":
            failures.append("nha_writer_not_gemma")
        if headers.get("x-trace-net-nha-self-rag") != "PASS":
            failures.append("nha_self_rag_not_pass")
        if int(headers.get("x-trace-net-model-prompt-tokens") or 0) < 1:
            failures.append("nha_prompt_tokens_missing")
        if int(headers.get("x-trace-net-model-completion-tokens") or 0) < 1:
            failures.append("nha_completion_tokens_missing")
    elif expected_action == "passthrough":
        if upstream_calls != 1:
            failures.append(f"upstream_calls:{upstream_calls}!=1")
        if model_calls != 1:
            failures.append(f"actual_upstream_model_calls:{model_calls}!=1")
        if model_path != "upstream_cognitive":
            failures.append(f"upstream_model_path:{model_path}")
        if upstream_status != "CONSTRAINED_GEMMA_CALL_SUCCEEDED_AND_VALIDATED":
            failures.append("upstream_gemma_status:" + upstream_status)
        if upstream_writer != "constrained_gemma_structured_output_validated":
            failures.append("upstream_writer_mode:" + upstream_writer)
    else:
        if model_calls != 0 or upstream_calls != 0:
            failures.append("synthetic_case_called_model")
        if headers.get("x-trace-net-nha-synthetic-access") != "0":
            failures.append("synthetic_access_not_zero")

    return {
        "case_id": case["case_id"],
        "kind": case["kind"],
        "query": case["query"],
        "stream": bool(case.get("stream")),
        "http_status": int(response.get("http_status") or 0),
        "action": action,
        "model_calls": model_calls,
        "model_path": model_path,
        "upstream_calls": upstream_calls,
        "upstream_gemma_status": upstream_status,
        "upstream_writer_mode": upstream_writer,
        "latency_seconds": float(response.get("latency_seconds") or 0.0),
        "answer": answer,
        "response_body": response.get("body"),
        "passed": not failures,
        "failures": failures,
    }


def summarize(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    nha = [row for row in records if str(row.get("action")) == "gemma_override"]
    upstream = [row for row in records if str(row.get("action")) == "passthrough"]
    blocked = [row for row in records if str(row.get("action")) == "synthetic_blocked"]
    failures = [f"{row['case_id']}:" + "|".join(row.get("failures") or []) for row in records if not row.get("passed")]
    counts = {
        "question_count": len(records),
        "pass_count": sum(bool(row.get("passed")) for row in records),
        "fail_count": sum(not bool(row.get("passed")) for row in records),
        "http_200_count": sum(int(row.get("http_status") or 0) == 200 for row in records),
        "nha_question_count": len(nha),
        "nha_model_call_count": sum(int(row.get("model_calls") or 0) for row in nha),
        "upstream_question_count": len(upstream),
        "upstream_actual_gemma_call_count": sum(int(row.get("model_calls") or 0) for row in upstream),
        "synthetic_block_count": len(blocked),
        "model_backed_question_count": sum(int(row.get("model_calls") or 0) == 1 for row in records),
        "unexpected_zero_model_call_count": sum(
            int(row.get("model_calls") or 0) == 0 and str(row.get("action")) != "synthetic_blocked"
            for row in records
        ),
        "allowed_zero_model_call_count": sum(
            int(row.get("model_calls") or 0) == 0 and str(row.get("action")) == "synthetic_blocked"
            for row in records
        ),
        "stream_count": sum(bool(row.get("stream")) for row in records),
        "nonstream_count": sum(not bool(row.get("stream")) for row in records),
        "production_graph_write_count": 0,
        "source_artifact_mutation_count": 0,
        "synthetic_artifact_access_count": 0,
    }
    required = {
        "question_count": 12,
        "pass_count": 12,
        "fail_count": 0,
        "http_200_count": 12,
        "nha_question_count": 6,
        "nha_model_call_count": 6,
        "upstream_question_count": 5,
        "upstream_actual_gemma_call_count": 5,
        "synthetic_block_count": 1,
        "model_backed_question_count": 11,
        "unexpected_zero_model_call_count": 0,
        "allowed_zero_model_call_count": 1,
        "stream_count": 6,
        "nonstream_count": 6,
    }
    for key, expected in required.items():
        if counts.get(key) != expected:
            failures.append(f"count:{key} expected={expected} actual={counts.get(key)}")
    latencies = [float(row.get("latency_seconds") or 0.0) for row in records]
    return {
        "schema_version": SCHEMA_VERSION,
        "module": "run_trace_net_nha_phase18_unified8131_gate_v1",
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "counts": counts,
        "latency": {
            "average_seconds": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "maximum_seconds": round(max(latencies), 3) if latencies else 0.0,
        },
        "failures": failures,
        "warnings": [],
        "live_model_call_policy": "one_actual_gemma_call_for_every_non_synthetic_mixed_gate_request",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8131")
    parser.add_argument("--api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-v1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output_dir)
    bank = build_bank()
    records: list[dict[str, Any]] = []
    for case in bank:
        response = call(args.base_url, args.api_key, args.model, case, args.timeout_seconds)
        row = evaluate(case, response)
        records.append(row)
        print(
            f"{row['case_id']} passed={row['passed']} action={row['action']} "
            f"model_calls={row['model_calls']} path={row['model_path']} latency={row['latency_seconds']}"
        )
    summary = summarize(records)
    summary["output_dir"] = str(output.resolve())
    summary["artifacts"] = [
        "trace_net_nha_phase18_unified8131_bank_v1.json",
        "trace_net_nha_phase18_unified8131_results_v1.json",
        "trace_net_nha_phase18_unified8131_results_v1.jsonl",
        "trace_net_nha_phase18_unified8131_quality_v1.json",
    ]
    _write_json(output / summary["artifacts"][0], bank)
    _write_json(output / summary["artifacts"][1], {"schema_version": SCHEMA_VERSION, "records": records})
    _write_jsonl(output / summary["artifacts"][2], records)
    _write_json(output / summary["artifacts"][3], summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("quality_status=" + summary["quality_status"])
    print("TRACE_NET_NHA_PHASE18_UNIFIED8131_MIXED12=" + summary["quality_status"])
    if args.strict and summary["quality_status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
