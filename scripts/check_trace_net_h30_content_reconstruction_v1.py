#!/usr/bin/env python3
"""Check Phase 3 content reconstruction and Phase 2 stabilization in a live run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

MODULE = "check_trace_net_h30_content_reconstruction_v1"
STATUS = "TRACE_NET_H30_CONTENT_RECONSTRUCTION_CHECK_V1"
TARGET_ROUTES = {
    "ata_system_discovery",
    "exact_table_ipl_lookup",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
}


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _trace(raw_response: Mapping[str, Any]) -> Dict[str, Any]:
    trace = raw_response.get("trace_net")
    return dict(trace) if isinstance(trace, Mapping) else dict(raw_response)


def inspect_run(run_dir: Path) -> Dict[str, Any]:
    files = sorted(
        path for path in run_dir.glob("*.json")
        if path.name[:2].isdigit()
    )
    results: List[Dict[str, Any]] = []
    failure_counts: Dict[str, int] = {}
    target_count = 0
    relationship_field_total = 0
    visual_callout_total = 0
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        evaluation = _mapping(payload.get("evaluation"))
        trace = _trace(_mapping(payload.get("raw_response")))
        route = str(trace.get("route") or "")
        reconstruction = _mapping(trace.get("content_reconstruction"))
        answer_mode = _mapping(trace.get("answer_mode"))
        failures: List[str] = []

        if not evaluation.get("post_validation_accepted"):
            failures.append("public_answer_post_validation_rejected")

        source = str(answer_mode.get("typed_record_source") or "")
        if source not in {"claim_ready_evidence", "complete_typed_evidence_fallback"}:
            failures.append("answer_mode_missing_typed_record_source")

        if route in TARGET_ROUTES:
            target_count += 1
            if not reconstruction:
                failures.append("missing_content_reconstruction")
            elif reconstruction.get("quality_status") != "PASS":
                failures.append("content_reconstruction_quality_not_pass")
            elif not reconstruction.get("final_validation_accepted"):
                failures.append("content_reconstruction_validation_rejected")
            if reconstruction and reconstruction.get("gemma_call_count_added") not in {0, None}:
                failures.append("content_reconstruction_added_gemma_call")
            if reconstruction and reconstruction.get("retrieval_changed"):
                failures.append("content_reconstruction_changed_retrieval")
            if reconstruction and reconstruction.get("route_changed"):
                failures.append("content_reconstruction_changed_route")

            if route == "ata_system_discovery" and int(reconstruction.get("ata_page_role_count") or 0) < 1:
                failures.append("ata_page_role_missing")
            if route == "exact_table_ipl_lookup" and not reconstruction.get("table_part_page_match"):
                failures.append("table_part_page_match_missing")
            if route == "procedure_task_lookup":
                if int(reconstruction.get("procedure_step_count") or 0) < 1:
                    failures.append("procedure_steps_missing")
                sequence_count = int(reconstruction.get("procedure_sequence_count") or 0)
                if sequence_count < 1:
                    failures.append("procedure_sequences_missing")
                if str(evaluation.get("question_id") or "") == "q16" and sequence_count < 2:
                    failures.append("procedure_sequence_reset_not_detected")

        relationship_field_total += int(reconstruction.get("table_relationship_field_count") or 0)
        visual_callout_total += int(reconstruction.get("visual_resolved_callout_count") or 0)
        for failure in failures:
            failure_counts[failure] = failure_counts.get(failure, 0) + 1
        results.append({
            "file": path.name,
            "question_id": evaluation.get("question_id"),
            "route": route,
            "passed": not failures,
            "failures": failures,
            "typed_record_source": source,
            "reconstruction_applied": reconstruction.get("applied"),
            "table_relationship_fields": reconstruction.get("table_relationship_fields") or [],
            "procedure_sequence_count": int(reconstruction.get("procedure_sequence_count") or 0),
            "visual_resolved_callout_count": int(reconstruction.get("visual_resolved_callout_count") or 0),
        })

    passed = sum(bool(row["passed"]) for row in results)
    report = {
        "module": MODULE,
        "status": STATUS,
        "quality_status": "PASS" if results and passed == len(results) else "FAIL",
        "record_count": len(results),
        "passed_record_count": passed,
        "failed_record_count": len(results) - passed,
        "target_route_record_count": target_count,
        "failure_counts": failure_counts,
        "post_validation_rejected_count": failure_counts.get("public_answer_post_validation_rejected", 0),
        "missing_typed_record_source_count": failure_counts.get("answer_mode_missing_typed_record_source", 0),
        "content_reconstruction_failure_count": sum(
            count for key, count in failure_counts.items()
            if key.startswith("content_reconstruction") or key.startswith("missing_content")
        ),
        "table_relationship_field_total": relationship_field_total,
        "visual_resolved_callout_total": visual_callout_total,
        "results": results,
    }
    return report


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# TRACE-Net H30 Phase 3 Content Reconstruction",
        "",
        f"Status: **{report.get('quality_status')}**",
        "",
        f"Records passed: {report.get('passed_record_count')}/{report.get('record_count')}",
        f"Target-route records: {report.get('target_route_record_count')}",
        f"Post-validation rejected: {report.get('post_validation_rejected_count')}",
        f"Missing typed consumer source: {report.get('missing_typed_record_source_count')}",
        f"Reconstruction failures: {report.get('content_reconstruction_failure_count')}",
        f"Reconstructed table fields: {report.get('table_relationship_field_total')}",
        f"Resolved visual callouts: {report.get('visual_resolved_callout_total')}",
        "",
        "| Question | Route | Consumer | Reconstruction | Status | Failures |",
        "|---|---|---|---|---|---|",
    ]
    for row in report.get("results") or []:
        lines.append(
            f"| {row.get('question_id')} | {row.get('route')} | "
            f"{row.get('typed_record_source') or '—'} | "
            f"{'yes' if row.get('reconstruction_applied') else 'no'} | "
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
    json_path = output_dir / "content_reconstruction_report.json"
    md_path = output_dir / "content_reconstruction_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"content_reconstruction_report_json={json_path}")
    print(f"content_reconstruction_report_markdown={md_path}")
    return 1 if args.strict and report.get("quality_status") != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
