#!/usr/bin/env python3
"""Run only the seven Phase 4 constrained-writer canary questions."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Mapping

from scripts import run_trace_net_tiff_grounded20_v1 as grounded

CANARY_IDS = ("q01", "q02", "q03", "q10", "q11", "q12", "q13")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--request-timeout", type=float, default=240.0)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def trace(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = payload.get("trace_net") if isinstance(payload, Mapping) else None
    return dict(value) if isinstance(value, Mapping) else dict(payload) if isinstance(payload, Mapping) else {}


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root).resolve()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    truth = grounded.truth(repo)
    full_bank = grounded.build_bank(truth)
    by_id = {item["question_id"]: item for item in full_bank}
    missing = [qid for qid in CANARY_IDS if qid not in by_id]
    if missing:
        raise SystemExit("missing_canary_questions=" + ",".join(missing))
    bank = [by_id[qid] for qid in CANARY_IDS]
    (out / "question_bank.json").write_text(
        json.dumps({"artifact_counts": truth["counts"], "questions": bank}, indent=2),
        encoding="utf-8",
    )

    rows: list[dict[str, Any]] = []
    accepted_count = 0
    fallback_count = 0
    max_calls = 0
    for index, item in enumerate(bank, 1):
        print("=" * 100)
        print(f"[{index:02d}/07] {item['question_id']} {item['category']}")
        print(item["question"])
        started = time.perf_counter()
        status, payload, error = grounded.call(
            args.base_url,
            args.api_key,
            args.model,
            item["question"],
            args.request_timeout,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        row = grounded.evaluate(item, payload, status, elapsed_ms, error)
        rows.append(row)
        tr = trace(payload)
        writer = tr.get("constrained_gemma_writer") if isinstance(tr.get("constrained_gemma_writer"), Mapping) else {}
        accepted = bool(writer.get("structured_output_accepted"))
        fallback = bool(writer.get("phase3_fallback_used"))
        calls = int(writer.get("call_count") or 0)
        accepted_count += int(accepted)
        fallback_count += int(fallback)
        max_calls = max(max_calls, calls)
        structured_validation = writer.get("structured_output_validation") if isinstance(writer.get("structured_output_validation"), Mapping) else {}
        validation_failures = list(structured_validation.get("failures") or [])
        record = {"question": item, "evaluation": row, "raw_response": payload}
        (out / f"{index:02d}_{item['question_id']}_{item['category']}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(
            f"http={status} route={row['actual_route']} latency={elapsed_ms/1000:.1f}s "
            f"validation={row['post_validation_accepted']} calls={calls} "
            f"accepted={accepted} fallback={fallback} reason={writer.get('reason')}"
        )
        if validation_failures:
            print("structured_validation_failures=", json.dumps(validation_failures))
        print("answer:", " ".join(row["answer"].split())[:450] or "<EMPTY>")

    summary = {
        "quality_status": "PASS",
        "question_count": len(rows),
        "http_200_count": sum(row["http_status"] == 200 for row in rows),
        "nonempty_answer_count": sum(bool(row["nonempty_answer"]) for row in rows),
        "route_match_count": sum(bool(row["route_match"]) for row in rows),
        "post_validation_accepted_count": sum(bool(row["post_validation_accepted"]) for row in rows),
        "structured_output_accepted_count": accepted_count,
        "phase3_fallback_count": fallback_count,
        "maximum_calls_per_record": max_calls,
        "maximum_latency_ms": max((row["latency_ms"] for row in rows), default=0.0),
    }
    hard_failures = []
    expected = len(CANARY_IDS)
    if summary["http_200_count"] != expected:
        hard_failures.append("not_all_http_200")
    if summary["nonempty_answer_count"] != expected:
        hard_failures.append("empty_answer")
    if summary["route_match_count"] != expected:
        hard_failures.append("route_mismatch")
    if summary["post_validation_accepted_count"] != expected:
        hard_failures.append("post_validation_rejected")
    if summary["structured_output_accepted_count"] < 1:
        hard_failures.append("no_structured_output_accepted")
    if max_calls > 1:
        hard_failures.append("more_than_one_call")
    summary["hard_failures"] = hard_failures
    summary["quality_status"] = "FAIL" if hard_failures else "PASS"
    (out / "summary.json").write_text(
        json.dumps({"summary": summary, "records": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("=" * 100)
    print(json.dumps(summary, indent=2))
    print("summary=", out / "summary.json")
    return 1 if args.strict and hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
