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


def inspect_run(run_dir: Path) -> Dict[str, Any]:
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
        failures: List[str] = []

        if not writer:
            failures.append("missing_constrained_writer_telemetry")
        if call_count > 1:
            failures.append("more_than_one_gemma_call")
        if writer and not writer.get("single_call_maximum"):
            failures.append("single_call_contract_missing")
        if writer and not writer.get("legacy_freeform_gemma_suppressed"):
            failures.append("legacy_freeform_writer_not_suppressed")
        if eligible and call_count != 1:
            failures.append("eligible_record_did_not_make_exactly_one_call")
        if not eligible and call_count != 0:
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
        results.append({
            "file": path.name,
            "question_id": evaluation.get("question_id"),
            "route": route,
            "passed": not failures,
            "failures": failures,
            "eligible": eligible,
            "reason": writer.get("reason"),
            "call_count": call_count,
            "structured_output_accepted": accepted,
            "phase3_fallback_used": fallback,
            "writer_mode": trace.get("writer_mode"),
            "effective_writer_mode": effective_writer_mode,
        })

    passed = sum(bool(row["passed"]) for row in results)
    quality = "PASS" if results and passed == len(results) else "FAIL"
    if eligible_count and total_calls != eligible_count:
        quality = "FAIL"
        failure_counts["eligible_call_count_mismatch"] = 1
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
        "passed_record_count": passed,
        "failed_record_count": len(results) - passed,
        "eligible_record_count": eligible_count,
        "gemma_call_count": total_calls,
        "maximum_calls_per_record": max_calls,
        "structured_output_accepted_count": accepted_count,
        "phase3_fallback_count": fallback_count,
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
        f"Eligible records: {report.get('eligible_record_count')}",
        f"Gemma calls: {report.get('gemma_call_count')}",
        f"Maximum calls per record: {report.get('maximum_calls_per_record')}",
        f"Structured outputs accepted: {report.get('structured_output_accepted_count')}",
        f"Phase 3 fallbacks: {report.get('phase3_fallback_count')}",
        f"Packet leaks: {report.get('packet_leak_count')}",
        f"Post-validation rejected: {report.get('post_validation_rejected_count')}",
        "",
        "| Question | Route | Eligible | Calls | Accepted | Fallback | Status | Failures |",
        "|---|---|---|---:|---|---|---|---|",
    ]
    for row in report.get("results") or []:
        lines.append(
            f"| {row.get('question_id')} | {row.get('route')} | "
            f"{row.get('eligible')} | {row.get('call_count')} | "
            f"{row.get('structured_output_accepted')} | {row.get('phase3_fallback_used')} | "
            f"{'PASS' if row.get('passed') else 'FAIL'} | "
            f"{', '.join(row.get('failures') or []) or '—'} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = Path(args.run_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else run_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report = inspect_run(run_dir)
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
