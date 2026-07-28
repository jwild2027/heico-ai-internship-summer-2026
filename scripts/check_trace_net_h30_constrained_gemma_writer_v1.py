#!/usr/bin/env python3
"""Check TRACE-Net H30 Phase 4 constrained-writer telemetry in a live run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

MODULE = "check_trace_net_h30_constrained_gemma_writer_v1"
STATUS = "TRACE_NET_H30_CONSTRAINED_GEMMA_WRITER_CHECK_V1"
TARGET_ROUTES = {
    "exact_identifier_lookup",
    "exact_table_ipl_lookup",
    "ata_system_discovery",
}
BUDGET_SKIP_REASONS = {"insufficient_remaining_budget"}
TIMEOUT_FALLBACK_REASONS = {"gemma_call_timeout"}


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _trace(raw_response: Mapping[str, Any]) -> Dict[str, Any]:
    value = raw_response.get("trace_net")
    return dict(value) if isinstance(value, Mapping) else dict(raw_response)


def _packet_has_forbidden_key(packet: Mapping[str, Any]) -> List[str]:
    forbidden = {
        "evidence_envelope",
        "typed_evidence",
        "claim_ready_evidence",
        "query_atoms",
        "coverage",
        "retrieval_tunnels",
        "identifier_blob",
        "source_trace",
        "route_scores",
        "raw_response",
    }
    blob = json.dumps(packet, ensure_ascii=False, sort_keys=True)
    return sorted(key for key in forbidden if f'"{key}"' in blob)


def inspect_run(run_dir: Path, *, expected_record_count: int = 0) -> Dict[str, Any]:
    files = sorted(
        path
        for path in run_dir.glob("[0-9][0-9]_*.json")
        if path.name not in {
            "summary.json",
            "question_bank.json",
            "constrained_gemma_writer_report.json",
        }
    )
    results: List[Dict[str, Any]] = []
    failure_counts: Dict[str, int] = {}
    total_calls = 0
    max_calls = 0
    eligible_count = 0
    accepted_count = 0
    fallback_count = 0
    budget_skip_count = 0
    timeout_fallback_count = 0
    maximum_total_elapsed_ms = 0.0
    over_budget_count = 0

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        evaluation = _mapping(payload.get("evaluation"))
        raw = _mapping(payload.get("raw_response"))
        trace = _trace(raw)
        writer = _mapping(trace.get("constrained_gemma_writer"))
        packet = _mapping(writer.get("packet"))
        route = str(trace.get("route") or evaluation.get("actual_route") or "")
        call_count = int(writer.get("call_count") or 0)
        eligible = bool(writer.get("eligible"))
        accepted = bool(writer.get("structured_output_accepted"))
        fallback = bool(writer.get("phase3_fallback_used"))
        reason = str(writer.get("reason") or "")
        total_elapsed_ms = float(writer.get("total_elapsed_ms") or 0.0)
        overall_budget_seconds = float(writer.get("overall_budget_seconds") or 0.0)
        budget_skipped = reason in BUDGET_SKIP_REASONS
        timeout_fallback = reason in TIMEOUT_FALLBACK_REASONS
        failures: List[str] = []

        if not writer:
            failures.append("missing_constrained_writer_telemetry")
        if call_count > 1:
            failures.append("more_than_one_gemma_call")
        if writer and not writer.get("single_call_maximum"):
            failures.append("single_call_contract_missing")
        if writer and not writer.get("legacy_freeform_gemma_suppressed"):
            failures.append("legacy_freeform_writer_not_suppressed")
        if eligible:
            if call_count == 0 and not (budget_skipped and fallback):
                failures.append("eligible_record_skipped_without_budget_fallback")
            if call_count not in {0, 1}:
                failures.append("eligible_record_invalid_call_count")
        elif call_count != 0:
            failures.append("ineligible_record_made_gemma_call")
        if route not in TARGET_ROUTES and call_count:
            failures.append("non_canary_route_made_gemma_call")
        if packet:
            forbidden = _packet_has_forbidden_key(packet)
            failures.extend(f"packet_leak:{value}" for value in forbidden)
            packet_validation = _mapping(writer.get("packet_validation"))
            if packet_validation.get("quality_status") != "PASS":
                failures.append("packet_validation_not_pass")
        if call_count and not accepted and not fallback:
            failures.append("rejected_output_without_phase3_fallback")
        if fallback and not _mapping(trace.get("post_answer_validation")).get("accepted"):
            failures.append("phase3_fallback_not_validated")
        if evaluation and not evaluation.get("post_validation_accepted"):
            failures.append("public_answer_post_validation_rejected")
        if timeout_fallback and not writer.get("model_call_timed_out"):
            failures.append("timeout_reason_without_timeout_telemetry")
        if budget_skipped and writer.get("call_attempted"):
            failures.append("budget_skip_attempted_model_call")
        if overall_budget_seconds > 0 and total_elapsed_ms > (overall_budget_seconds + 5.0) * 1000.0:
            failures.append("request_exceeded_phase4_budget")
            over_budget_count += 1

        effective_writer_mode = str(
            trace.get("writer_mode_before_public_answer_contract")
            or trace.get("writer_mode")
            or ""
        )
        if accepted and effective_writer_mode != "constrained_gemma_structured_output_validated":
            failures.append("accepted_output_writer_mode_mismatch")

        for failure in failures:
            failure_counts[failure] = failure_counts.get(failure, 0) + 1
        total_calls += call_count
        max_calls = max(max_calls, call_count)
        eligible_count += int(eligible)
        accepted_count += int(accepted)
        fallback_count += int(fallback)
        budget_skip_count += int(budget_skipped)
        timeout_fallback_count += int(timeout_fallback)
        maximum_total_elapsed_ms = max(maximum_total_elapsed_ms, total_elapsed_ms)
        results.append({
            "file": path.name,
            "question_id": evaluation.get("question_id"),
            "route": route,
            "passed": not failures,
            "failures": failures,
            "eligible": eligible,
            "reason": reason,
            "call_count": call_count,
            "structured_output_accepted": accepted,
            "phase3_fallback_used": fallback,
            "budget_skipped": budget_skipped,
            "model_call_timed_out": bool(writer.get("model_call_timed_out")),
            "upstream_elapsed_ms": writer.get("upstream_elapsed_ms"),
            "model_call_elapsed_ms": writer.get("model_call_elapsed_ms"),
            "total_elapsed_ms": total_elapsed_ms,
            "writer_mode": trace.get("writer_mode"),
            "effective_writer_mode": effective_writer_mode,
        })

    passed = sum(bool(row["passed"]) for row in results)
    quality = "PASS" if results and passed == len(results) else "FAIL"
    if expected_record_count > 0 and len(results) != expected_record_count:
        quality = "FAIL"
        failure_counts["incomplete_run"] = 1
    if total_calls > eligible_count:
        quality = "FAIL"
        failure_counts["eligible_call_count_exceeded"] = 1
    if eligible_count and accepted_count + fallback_count < eligible_count:
        quality = "FAIL"
        failure_counts["eligible_record_without_accept_or_fallback"] = 1
    if eligible_count and accepted_count == 0:
        quality = "FAIL"
        failure_counts["no_structured_output_accepted"] = 1

    return {
        "module": MODULE,
        "status": STATUS,
        "quality_status": quality,
        "record_count": len(results),
        "expected_record_count": expected_record_count,
        "passed_record_count": passed,
        "failed_record_count": len(results) - passed,
        "eligible_record_count": eligible_count,
        "gemma_call_count": total_calls,
        "maximum_calls_per_record": max_calls,
        "structured_output_accepted_count": accepted_count,
        "phase3_fallback_count": fallback_count,
        "budget_skip_count": budget_skip_count,
        "model_timeout_fallback_count": timeout_fallback_count,
        "maximum_total_elapsed_ms": round(maximum_total_elapsed_ms, 3),
        "over_budget_count": over_budget_count,
        "failure_counts": failure_counts,
        "second_call_violation_count": failure_counts.get("more_than_one_gemma_call", 0),
        "legacy_suppression_failure_count": failure_counts.get("legacy_freeform_writer_not_suppressed", 0),
        "packet_leak_count": sum(value for key, value in failure_counts.items() if key.startswith("packet_leak:")),
        "post_validation_rejected_count": failure_counts.get("public_answer_post_validation_rejected", 0),
        "results": results,
    }


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# TRACE-Net H30 Phase 4 Constrained Gemma Writer",
        "",
        f"Status: **{report.get('quality_status')}**",
        "",
        f"Records passed: {report.get('passed_record_count')}/{report.get('record_count')}",
        f"Expected records: {report.get('expected_record_count')}",
        f"Eligible records: {report.get('eligible_record_count')}",
        f"Gemma calls: {report.get('gemma_call_count')}",
        f"Maximum calls per record: {report.get('maximum_calls_per_record')}",
        f"Structured outputs accepted: {report.get('structured_output_accepted_count')}",
        f"Phase 3 fallbacks: {report.get('phase3_fallback_count')}",
        f"Budget skips: {report.get('budget_skip_count')}",
        f"Model-timeout fallbacks: {report.get('model_timeout_fallback_count')}",
        f"Maximum total elapsed ms: {report.get('maximum_total_elapsed_ms')}",
        f"Over-budget records: {report.get('over_budget_count')}",
        f"Packet leaks: {report.get('packet_leak_count')}",
        f"Post-validation rejected: {report.get('post_validation_rejected_count')}",
        "",
        "| Question | Route | Eligible | Calls | Accepted | Fallback | Reason | Total ms | Status | Failures |",
        "|---|---|---|---:|---|---|---|---:|---|---|",
    ]
    for row in report.get("results") or []:
        lines.append(
            f"| {row.get('question_id')} | {row.get('route')} | "
            f"{row.get('eligible')} | {row.get('call_count')} | "
            f"{row.get('structured_output_accepted')} | {row.get('phase3_fallback_used')} | "
            f"{row.get('reason')} | {row.get('total_elapsed_ms')} | "
            f"{'PASS' if row.get('passed') else 'FAIL'} | "
            f"{', '.join(row.get('failures') or []) or '—'} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--expected-record-count", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = Path(args.run_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else run_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report = inspect_run(run_dir, expected_record_count=max(0, args.expected_record_count))
    json_path = output_dir / "constrained_gemma_writer_report.json"
    md_path = output_dir / "constrained_gemma_writer_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"constrained_writer_report_json={json_path}")
    print(f"constrained_writer_report_markdown={md_path}")
    return 1 if args.strict and report.get("quality_status") != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
