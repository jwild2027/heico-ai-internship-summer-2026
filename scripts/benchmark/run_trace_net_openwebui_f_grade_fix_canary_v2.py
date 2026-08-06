#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Mapping

TESTS = (
    (
        "capabilities",
        "safe_general_chat",
        "What kinds of questions can you answer using the indexed aircraft manual?",
    ),
    (
        "exact_ipl_fields",
        "exact_table_ipl_lookup",
        "Search the illustrated parts list for part 120-41824-003. "
        "Report only source-backed item, nomenclature, quantity, and page fields. "
        "Clearly mark any field that is not proven.",
    ),
)


def post(url: str, api_key: str, payload: Mapping[str, Any], timeout: float) -> tuple[int, Dict[str, Any], str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), json.loads(response.read().decode("utf-8")), ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        return int(exc.code), payload, f"HTTPError:{exc.code}"
    except Exception as exc:
        return 0, {}, f"{type(exc).__name__}:{exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-v1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    records = []

    for index, (name, expected_route, question) in enumerate(TESTS, 1):
        started = time.perf_counter()
        status, payload, error = post(
            url,
            args.api_key,
            {
                "model": args.model,
                "messages": [{"role": "user", "content": question}],
                "temperature": 0,
                "stream": False,
            },
            args.timeout,
        )
        latency = round(time.perf_counter() - started, 3)
        choices = payload.get("choices") if isinstance(payload, Mapping) else []
        answer = ""
        if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
            message = choices[0].get("message")
            if isinstance(message, Mapping):
                answer = str(message.get("content") or "")
        trace = payload.get("trace_net") if isinstance(payload, Mapping) else {}
        trace = dict(trace) if isinstance(trace, Mapping) else {}
        actual_route = str(trace.get("route") or "")
        validation = trace.get("post_answer_validation")
        validation = dict(validation) if isinstance(validation, Mapping) else {}

        failures = []
        if status != 200:
            failures.append(f"http_status:{status}")
        if actual_route != expected_route:
            failures.append(f"route:{actual_route}")
        if not validation.get("accepted"):
            failures.append("post_answer_validation_not_accepted")
        for heading in ("## Answer", "## Evidence", "## Limits"):
            if heading not in answer:
                failures.append(f"missing_heading:{heading}")
        if "phase4_3" in answer or "_removed_" in answer:
            failures.append("internal_diagnostic_leak")
        if name == "capabilities":
            if "Exact part-number" not in answer or "Illustrated-parts-list" not in answer:
                failures.append("capabilities_missing")
            if "Helpful follow-up questions" in answer or "t_p_" in answer:
                failures.append("capabilities_wrong_retrieval_response")
        if name == "exact_ipl_fields":
            field_status = all(label in answer for label in ("Item", "Nomenclature", "Quantity", "Page"))
            explicit_no_row = "No citation-ready IPL row was confirmed" in answer
            if not field_status and not explicit_no_row:
                failures.append("ipl_fields_not_fulfilled_or_explicitly_limited")
            if "| Requested claim |" in answer or "Evidence status:**" in answer:
                failures.append("malformed_table_output")

        record = {
            "name": name,
            "question": question,
            "expected_route": expected_route,
            "actual_route": actual_route,
            "http_status": status,
            "latency_seconds": latency,
            "answer": answer,
            "validation": validation,
            "failures": failures,
            "passed": not failures,
            "transport_error": error,
            "raw_response": payload,
        }
        records.append(record)
        (output / f"{index:02d}_{name}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print("=" * 100)
        print(f"[{index}/2] {name} pass={not failures} route={actual_route} latency={latency}s")
        print(f"failures={failures}")
        print(answer)

    pass_count = sum(bool(row["passed"]) for row in records)
    summary = {
        "quality_status": "PASS" if pass_count == len(records) else "FAIL",
        "question_count": len(records),
        "pass_count": pass_count,
        "failure_count": len(records) - pass_count,
        "records": records,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("=" * 100)
    print(json.dumps({key: summary[key] for key in (
        "quality_status", "question_count", "pass_count", "failure_count"
    )}, indent=2))
    print(f"output={output}")
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
