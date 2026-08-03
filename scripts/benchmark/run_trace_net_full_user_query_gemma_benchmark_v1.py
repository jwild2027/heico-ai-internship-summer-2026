#!/usr/bin/env python3
"""Run the 180-question bank against the current H30 mature cognitive contract."""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from scripts.operations.router.serve_trace_net_cognitive_router_v1 import extract_query_atoms, plan_route
from tiff.trace_net_answer_quality_guard_v1 import evaluate_answer_quality
from scripts.benchmark.trace_net_benchmark_reporting_v1 import (
    build_run_metadata,
    completed_question_ids,
    load_records_jsonl,
    rewrite_records_jsonl,
    write_json,
    write_qa_reports,
)


CURRENT_WRITER_SUCCESS = {
    "LLM_CALL_SUCCEEDED_AND_VALIDATED",
    "LLM_CALL_SUCCEEDED",
}
CURRENT_WRITER_SKIP = {"SKIPPED_NO_DIRECT_EVIDENCE"}
# Emitted by the evidence-aware answer-mode layer when a non-confirmed-direct
# question is rendered deterministically. It is a legitimate skip (no Gemma call
# was made) even when direct evidence rows exist but none is claim-supporting, so
# it must not be counted as a writer call nor scored as a writer failure.
TYPED_EVIDENCE_WRITER_SKIP = "SKIPPED_BY_TYPED_EVIDENCE_MODE"
TOPIC_KEYWORDS = {
    "part_number": ("part number", "characters", "digits", "prefix", "suffix", "markings"),
    "manufacturer": ("manufacturer", "vendor", "supplier", "company"),
    "component": ("component", "assembly", "function", "nomenclature"),
    "function": ("function", "used for", "purpose"),
    "appearance": ("appearance", "look like", "shape", "color", "marking"),
    "physical_description": (
        "physical description", "look like", "shape", "color", "size",
        "marking", "nearby hardware", "installed", "installation location",
    ),
    "ata": ("ata", "chapter", "system"),
    "figure": ("figure", "diagram", "callout"),
    "table": ("table", "ipl", "item"),
    "page": ("page", "manual location"),
}


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


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> List[str]:
    return [str(item) for item in value if str(item)] if isinstance(value, list) else []


def mature_expected_plan(
    record: Mapping[str, Any],
    trace: Optional[Mapping[str, Any]] = None,
) -> Tuple[str, List[str]]:
    """Use a validated adopted planner plan, otherwise use deterministic routing."""
    query = str(record.get("query") or "")
    deterministic = plan_route(extract_query_atoms(query))
    fallback_route = deterministic.primary_route
    fallback_tunnels = list(deterministic.retrieval_tunnels)

    trace_map = _mapping(trace)
    execution = _mapping(trace_map.get("planner_execution"))
    validation = _mapping(execution.get("planner_validation") or trace_map.get("planner_validation"))
    selected_route = str(execution.get("selected_route") or "")
    effective_route = str(execution.get("effective_route") or "")
    adopted = bool(execution.get("planner_plan_adopted") or trace_map.get("planner_plan_adopted"))
    applied = bool(execution.get("planner_route_applied") or trace_map.get("planner_route_applied"))
    valid_adoption = bool(
        adopted
        and applied
        and execution.get("quality_status") == "PASS"
        and validation.get("accepted") is True
        and execution.get("executor_owns_tunnel_selection") is True
        and selected_route
        and (not effective_route or effective_route == selected_route)
    )
    if not valid_adoption:
        return fallback_route, fallback_tunnels
    effective_tunnels = _string_list(execution.get("effective_tunnels"))
    if not effective_tunnels:
        effective_tunnels = _string_list(_mapping(trace_map.get("route_plan")).get("retrieval_tunnels"))
    return selected_route, effective_tunnels or fallback_tunnels


def is_mature_contract(trace: Mapping[str, Any]) -> bool:
    return bool(
        isinstance(trace.get("route_plan"), Mapping)
        or isinstance(trace.get("evidence_envelope"), Mapping)
        or "writer_mode" in trace
        or "gemma_status" in trace
    )


def question_visible(answer: str, question: str) -> bool:
    normalize = lambda value: " ".join(
        "".join(ch.lower() if ch.isalnum() else " " for ch in str(value)).split()
    )
    needle = normalize(question)
    haystack = normalize(answer)
    return bool(needle and needle in haystack)


def topic_visible(topic: str, questions: Sequence[str]) -> bool:
    blob = " ".join(str(value).lower() for value in questions)
    keywords = TOPIC_KEYWORDS.get(str(topic), tuple(str(topic).lower().split("_")))
    return any(keyword in blob for keyword in keywords)


def used_tunnel_matches_plan(
    tunnel: str,
    planned_tunnels: Sequence[str],
    route: str,
) -> bool:
    """Validate bounded executor-derived labels without weakening tunnel ownership."""
    value = str(tunnel or "")
    if value in set(planned_tunnels):
        return True
    if re.fullmatch(re.escape(route) + r"_specialized_\d+", value):
        return True
    if route == "multi_question_research" and re.fullmatch(r"claim_subquery_\d+", value):
        return True
    return value.startswith("crag_")


def current_writer_contract(
    trace: Mapping[str, Any],
    *,
    route: str,
    direct_count: int,
) -> Dict[str, Any]:
    writer_mode = str(trace.get("writer_mode") or "")
    gemma_status = str(trace.get("gemma_status") or "")
    old_called = bool(trace.get("response_composer_called"))
    old_status = str(trace.get("response_composer_status") or "")
    old_model = str(trace.get("response_composer_model") or "")

    if writer_mode or gemma_status:
        expected = direct_count > 0 and route != "safe_general_chat"
        typed_evidence_skip = gemma_status == TYPED_EVIDENCE_WRITER_SKIP
        # A typed-evidence deterministic render never issues a Gemma call, so it
        # is not a writer call regardless of how many direct rows were present.
        called = (
            expected
            and gemma_status not in CURRENT_WRITER_SKIP
            and not typed_evidence_skip
        )
        successful = gemma_status in CURRENT_WRITER_SUCCESS
        skipped_expected = (
            ((not expected) and gemma_status in CURRENT_WRITER_SKIP)
            or typed_evidence_skip
        )
        acceptable = (successful or typed_evidence_skip) if expected else skipped_expected
        return {
            "contract": "h30_mature_cognitive",
            "expected": expected,
            "called": called,
            "successful": successful,
            "skipped_expected": skipped_expected,
            "typed_evidence_deterministic": typed_evidence_skip,
            "acceptable": acceptable,
            "status": gemma_status,
            "mode": writer_mode,
            "model": str(trace.get("answer_model") or ""),
        }

    successful = old_status == "LLM_CALL_SUCCEEDED"
    return {
        "contract": "legacy_full_user_query_canary",
        "expected": True,
        "called": old_called,
        "successful": successful,
        "skipped_expected": False,
        "acceptable": old_called and successful,
        "status": old_status,
        "mode": "",
        "model": old_model,
    }


def evaluate(
    record: Mapping[str, Any],
    *,
    status_code: int,
    response: Mapping[str, Any],
    latency_ms: float,
    transport_error: str,
) -> Dict[str, Any]:
    answer = answer_text(response)
    trace = _mapping(response.get("trace_net"))
    failures: List[str] = []

    if status_code != 200:
        failures.append(f"http_status:{status_code}")
    if transport_error:
        failures.append(f"transport_error:{transport_error}")
    if not answer:
        failures.append("empty_answer")
    if answer.startswith("{") or "TRACE-NET LIVE CONTEXT PACK" in answer:
        failures.append("internal_or_json_leak")

    legacy_expected_route = str(record.get("expected_execution_route") or "")
    legacy_expected_tunnel = str(record.get("expected_tunnel") or "")
    actual_route = str(trace.get("route") or "")
    mature = is_mature_contract(trace)

    route_plan = _mapping(trace.get("route_plan"))
    envelope = _mapping(trace.get("evidence_envelope"))
    planned_tunnels = _string_list(route_plan.get("retrieval_tunnels"))
    used_tunnels = _string_list(envelope.get("retrieval_tunnels_used"))
    old_tunnel = str(trace.get("retrieval_tunnel") or "")

    if mature:
        expected_route, expected_tunnels = mature_expected_plan(record, trace)
        if actual_route != expected_route:
            failures.append(f"route:{actual_route}!={expected_route}")
        if not planned_tunnels:
            failures.append("mature_route_plan_tunnels_missing")
        elif planned_tunnels != expected_tunnels:
            failures.append(
                "planned_tunnels:"
                + ",".join(planned_tunnels)
                + "!="
                + ",".join(expected_tunnels)
            )
        if used_tunnels and any(
            not used_tunnel_matches_plan(value, planned_tunnels, actual_route)
            for value in used_tunnels
        ):
            failures.append("used_tunnel_not_planned")
        actual_tunnels = used_tunnels or planned_tunnels
    else:
        expected_route = legacy_expected_route
        expected_tunnels = [legacy_expected_tunnel] if legacy_expected_tunnel else []
        if actual_route != expected_route:
            failures.append(f"route:{actual_route}!={expected_route}")
        if legacy_expected_tunnel and old_tunnel != legacy_expected_tunnel:
            failures.append(f"tunnel:{old_tunnel}!={legacy_expected_tunnel}")
        actual_tunnels = [old_tunnel] if old_tunnel else []

    direct_rows = [
        dict(row)
        for row in envelope.get("direct_evidence", [])
        if isinstance(row, Mapping)
    ] if isinstance(envelope.get("direct_evidence"), list) else []
    candidate_rows = [
        dict(row)
        for row in envelope.get("candidate_evidence", [])
        if isinstance(row, Mapping)
    ] if isinstance(envelope.get("candidate_evidence"), list) else []
    direct_count = len(direct_rows)
    citations = int(trace.get("citation_count") or 0)

    writer = current_writer_contract(
        trace,
        route=actual_route,
        direct_count=direct_count,
    )
    if not writer["acceptable"]:
        if writer["expected"]:
            failures.append("writer_not_validated:" + (writer["status"] or "missing"))
        else:
            failures.append(
                "candidate_or_guidance_writer_not_skipped:"
                + (writer["status"] or "missing")
            )

    followups = _string_list(trace.get("follow_up_questions"))
    minimum = int(record.get("min_follow_up_questions") or 0)
    if len(followups) < minimum:
        failures.append(f"follow_up_count:{len(followups)}<{minimum}")
    if minimum > 0:
        visible = sum(question_visible(answer, question) for question in followups)
        if visible < minimum:
            failures.append(f"followups_visible:{visible}<{minimum}")
        for topic in record.get("required_follow_up_topics") or []:
            if not topic_visible(str(topic), followups):
                failures.append(f"followup_topic_missing:{topic}")

    failures.extend(
        evaluate_answer_quality(
            query=str(record.get("query") or ""),
            answer=answer,
            trace=trace,
        )
    )

    for key in (
        "answer_permission",
        "final_answer_allowed",
        "can_answer_directly",
        "can_prove_claims",
        "source_truth_mutation_allowed",
    ):
        if trace.get(key):
            failures.append(f"safety_true:{key}")

    if mature:
        if direct_count > 0 and citations <= 0:
            failures.append("direct_evidence_has_no_citations")
        if direct_count == 0 and citations != 0:
            failures.append(f"guidance_only_has_citations:{citations}")
        if candidate_rows and direct_count == 0:
            lower = answer.lower()
            if "candidate" not in lower or "not a final identification" not in lower:
                failures.append("candidate_safety_boundary_missing")
    else:
        expectation = str(record.get("retrieval_expectation") or "not_checked")
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

    failures = list(dict.fromkeys(failures))
    return {
        "question_id": record.get("question_id"),
        "category": record.get("category"),
        "query": record.get("query"),
        "contract": "h30_mature_cognitive" if mature else "legacy_full_user_query_canary",
        "legacy_expected_route": legacy_expected_route,
        "expected_route": expected_route,
        "actual_route": actual_route,
        "legacy_expected_tunnel": legacy_expected_tunnel,
        "expected_tunnels": expected_tunnels,
        "planned_tunnels": planned_tunnels,
        "used_tunnels": used_tunnels,
        "actual_tunnels": actual_tunnels,
        "http_status": status_code,
        "latency_ms": latency_ms,
        "transport_error": transport_error,
        "answer": answer,
        "answer_character_count": len(answer),
        "citation_count": citations,
        "direct_evidence_count": direct_count,
        "candidate_evidence_count": len(candidate_rows),
        "follow_up_questions": followups,
        "writer_contract": writer["contract"],
        "writer_expected": writer["expected"],
        "writer_called": writer["called"],
        "writer_successful": writer["successful"],
        "writer_skipped_expected": writer["skipped_expected"],
        "writer_status": writer["status"],
        "writer_mode": writer["mode"],
        "writer_model": writer["model"],
        "response_composer_called": writer["called"],
        "response_composer_status": writer["status"],
        "response_composer_model": writer["model"],
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
    parser.add_argument("--base-url", default="http://172.17.0.1:8131")
    parser.add_argument("--api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-v1")
    parser.add_argument("--request-timeout", type=int, default=1200)
    parser.add_argument(
        "--output-dir",
        default="local_data/organization/trace_net/h30_mature_full_180_v1",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Append to an existing records.jsonl and skip completed question IDs.",
    )
    parser.add_argument(
        "--report-every",
        type=int,
        default=1,
        help="Rewrite complete Q&A reports after every N newly completed records; 0 disables periodic writes.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=180,
        help="Terminal-only answer preview length. Stored reports always contain the full answer.",
    )
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
    existing_results: List[Dict[str, Any]] = []
    load_warnings: List[str] = []
    if args.resume:
        existing_results, load_warnings = load_records_jsonl(records_path)
        if load_warnings:
            rewrite_records_jsonl(records_path, existing_results)
    results: List[Dict[str, Any]] = list(existing_results)
    completed_ids = set(completed_question_ids(existing_results))
    resumed_record_count = len(existing_results)
    total = len(records)
    all_start = time.perf_counter()
    interrupted = False

    run_metadata = build_run_metadata(
        repo_root=Path.cwd(),
        question_bank=Path(args.question_bank),
        output_dir=output,
        base_url=args.base_url,
        model=args.model,
        request_timeout=args.request_timeout,
        expected_question_count=total,
        resume_enabled=args.resume,
        existing_record_count=resumed_record_count,
    )
    write_json(output / "run_metadata.json", run_metadata)

    file_mode = "a" if args.resume else "w"
    newly_completed = 0
    try:
        with records_path.open(file_mode, encoding="utf-8") as handle:
            for index, record in enumerate(records, 1):
                query = str(record.get("query") or "")
                qid = str(record.get("question_id") or f"q{index:03d}")
                category = str(record.get("category") or "unknown")
                if qid in completed_ids:
                    print(f"[{index}/{total}] SKIP {qid} already_completed", flush=True)
                    continue
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
                completed_ids.add(qid)
                newly_completed += 1
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())

                if args.report_every > 0 and newly_completed % args.report_every == 0:
                    write_qa_reports(
                        results,
                        output_dir=output,
                        expected_question_count=total,
                        interrupted=False,
                        load_warnings=load_warnings,
                        run_metadata=run_metadata,
                    )

                preview = result["answer"].replace("\n", " ")[: max(0, args.preview_chars)]
                print(
                    f"[{index}/{total}] {result['quality_status']} "
                    f"route={result['actual_route']} "
                    f"writer={result['writer_status'] or 'missing'} "
                    f"citations={result['citation_count']} "
                    f"followups={len(result['follow_up_questions'])} "
                    f"latency_ms={result['latency_ms']:.1f}",
                    flush=True,
                )
                if result["failures"]:
                    print(
                        f"[{index}/{total}] FAILURES "
                        + " | ".join(result["failures"]),
                        flush=True,
                    )
                print(f"[{index}/{total}] ANSWER_PREVIEW {preview}", flush=True)

                if status == 599 and not args.continue_on_error:
                    print("Transport error; stopping early.", flush=True)
                    break
    except KeyboardInterrupt:
        interrupted = True
        print("Benchmark interrupted; preserving completed records and reports.", flush=True)
    finally:
        report_outputs = write_qa_reports(
            results,
            output_dir=output,
            expected_question_count=total,
            interrupted=interrupted,
            load_warnings=load_warnings,
            run_metadata=run_metadata,
        )

    latencies = [float(row["latency_ms"]) for row in results]
    category_latencies: Dict[str, List[float]] = defaultdict(list)
    for row in results:
        category_latencies[str(row.get("category") or "unknown")].append(
            float(row.get("latency_ms") or 0.0)
        )
    failed = [row for row in results if row["quality_status"] != "PASS"]
    elapsed = round(time.perf_counter() - all_start, 3)

    summary = {
        "status": (
            "TRACE_NET_H30_MATURE_FULL_180_BENCHMARK_V1_INTERRUPTED"
            if interrupted
            else "TRACE_NET_H30_MATURE_FULL_180_BENCHMARK_V1_DONE"
        ),
        "quality_status": "PASS" if len(results) == total and not failed and not interrupted else "FAIL",
        "interrupted": interrupted,
        "resume_enabled": args.resume,
        "resumed_record_count": resumed_record_count,
        "newly_completed_record_count": newly_completed,
        "load_warnings": load_warnings,
        "run_metadata": run_metadata,
        "contract": "h30_mature_cognitive_with_legacy_bank_adapter",
        "question_count": len(results),
        "expected_question_count": total,
        "pass_count": len(results) - len(failed),
        "fail_count": len(failed),
        "all_questions_sent_as_user_messages": len(results) == total,
        "writer_expected_count": sum(bool(row.get("writer_expected")) for row in results),
        "writer_call_count": sum(bool(row.get("writer_called")) for row in results),
        "writer_success_count": sum(bool(row.get("writer_successful")) for row in results),
        "writer_expected_skip_count": sum(bool(row.get("writer_skipped_expected")) for row in results),
        "writer_failure_count": sum(
            bool(row.get("writer_expected")) and not bool(row.get("writer_successful"))
            for row in results
        ),
        "gemma_call_count": sum(bool(row.get("writer_called")) for row in results),
        "gemma_success_count": sum(bool(row.get("writer_successful")) for row in results),
        "gemma_failure_count": sum(
            bool(row.get("writer_expected")) and not bool(row.get("writer_successful"))
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
        "writer_status_counts": dict(Counter(row["writer_status"] or "missing" for row in results)),
        "category_counts": dict(Counter(row["category"] for row in results)),
        "category_average_latency_ms": {
            category: round(statistics.mean(values), 3)
            for category, values in sorted(category_latencies.items())
        },
        "failure_counts": dict(Counter(
            failure
            for row in failed
            for failure in row.get("failures", [])
        )),
        "failed_records": failed,
        "base_url": args.base_url,
        "model": args.model,
        "output_files": {
            "summary": str(output / "summary.json"),
            "records": str(records_path),
            "report": str(output / "report.md"),
            **report_outputs,
            "run_metadata": str(output / "run_metadata.json"),
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
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    report = [
        "# TRACE-Net H30 Mature Full-180 Benchmark",
        "",
        f"- Quality: **{summary['quality_status']}**",
        f"- Questions: `{summary['question_count']}`",
        f"- Passed: `{summary['pass_count']}`",
        f"- Failed: `{summary['fail_count']}`",
        f"- Writer successes: `{summary['writer_success_count']}`",
        f"- Expected deterministic skips: `{summary['writer_expected_skip_count']}`",
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
        "contract",
        "question_count",
        "pass_count",
        "fail_count",
        "all_questions_sent_as_user_messages",
        "writer_expected_count",
        "writer_call_count",
        "writer_success_count",
        "writer_expected_skip_count",
        "writer_failure_count",
        "average_latency_ms",
        "median_latency_ms",
        "p95_latency_ms",
        "total_elapsed_seconds",
    ):
        print(f"{key}={summary[key]}")
    print("output_dir=" + str(output))
    if interrupted:
        return 130
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
