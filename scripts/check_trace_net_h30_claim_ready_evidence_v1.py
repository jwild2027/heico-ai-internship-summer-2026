#!/usr/bin/env python3
"""Check Phase 2 claim-ready evidence telemetry in a TRACE-Net live run directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

MODULE = "check_trace_net_h30_claim_ready_evidence_v1"
STATUS = "TRACE_NET_H30_CLAIM_READY_EVIDENCE_CHECK_V1"


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _trace(raw_response: Mapping[str, Any]) -> Dict[str, Any]:
    trace = raw_response.get("trace_net")
    if isinstance(trace, Mapping):
        return dict(trace)
    return dict(raw_response)


def inspect_run(run_dir: Path) -> Dict[str, Any]:
    files = sorted(
        path for path in run_dir.glob("*.json")
        if path.name not in {
            "summary.json",
            "question_bank.json",
            "public_answer_contract_report.json",
            "public_answer_golden_report.json",
            "claim_ready_evidence_report.json",
        }
        and path.name[:2].isdigit()
    )
    results: List[Dict[str, Any]] = []
    failure_counts: Dict[str, int] = {}
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        evaluation = _mapping(payload.get("evaluation"))
        raw = _mapping(payload.get("raw_response"))
        trace = _trace(raw)
        envelope = _mapping(trace.get("evidence_envelope"))
        claim_ready = _mapping(envelope.get("claim_ready_evidence"))
        coverage = _mapping(claim_ready.get("coverage"))
        validation = _mapping(claim_ready.get("validation"))
        answer_mode = _mapping(trace.get("answer_mode"))
        failures: List[str] = []

        if not claim_ready:
            failures.append("missing_claim_ready_evidence")
        elif claim_ready.get("quality_status") != "PASS":
            failures.append("claim_ready_quality_not_pass")
        if claim_ready and not claim_ready.get("typed_view_rebuilt_after_final_enrichment"):
            failures.append("typed_view_not_rebuilt_after_final_enrichment")
        if claim_ready and not coverage.get("complete_typed_audit_preserved"):
            failures.append("complete_typed_audit_not_preserved")
        if claim_ready and not validation.get("legacy_evidence_preserved"):
            failures.append("legacy_evidence_not_preserved")
        full_count = int(coverage.get("complete_typed_record_count") or 0)
        selected_count = int(coverage.get("selected_record_count") or 0)
        if selected_count > full_count:
            failures.append("selected_count_exceeds_complete_typed_count")
        if validation and validation.get("quality_status") != "PASS":
            failures.append("claim_ready_validation_failed")
        source = str(answer_mode.get("typed_record_source") or "")
        if answer_mode and source not in {"claim_ready_evidence", "complete_typed_evidence_fallback"}:
            failures.append("answer_mode_missing_typed_record_source")
        if evaluation and not evaluation.get("post_validation_accepted"):
            failures.append("public_answer_post_validation_rejected")

        for failure in failures:
            failure_counts[failure] = failure_counts.get(failure, 0) + 1
        results.append({
            "file": path.name,
            "question_id": evaluation.get("question_id"),
            "route": trace.get("route"),
            "passed": not failures,
            "failures": failures,
            "complete_typed_record_count": full_count,
            "selected_record_count": selected_count,
            "answer_mode_typed_record_source": source,
        })

    passed = sum(bool(row["passed"]) for row in results)
    report = {
        "module": MODULE,
        "status": STATUS,
        "quality_status": "PASS" if results and passed == len(results) else "FAIL",
        "record_count": len(results),
        "passed_record_count": passed,
        "failed_record_count": len(results) - passed,
        "failure_counts": failure_counts,
        "missing_claim_ready_count": failure_counts.get("missing_claim_ready_evidence", 0),
        "selector_validation_failure_count": failure_counts.get("claim_ready_validation_failed", 0),
        "typed_view_rebuild_failure_count": failure_counts.get("typed_view_not_rebuilt_after_final_enrichment", 0),
        "legacy_preservation_failure_count": failure_counts.get("legacy_evidence_not_preserved", 0),
        "post_validation_rejected_count": failure_counts.get("public_answer_post_validation_rejected", 0),
        "results": results,
    }
    return report


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# TRACE-Net H30 Phase 2 Claim-Ready Evidence",
        "",
        f"Status: **{report.get('quality_status')}**",
        "",
        f"Records passed: {report.get('passed_record_count')}/{report.get('record_count')}",
        f"Missing claim-ready evidence: {report.get('missing_claim_ready_count')}",
        f"Selector validation failures: {report.get('selector_validation_failure_count')}",
        f"Typed-view rebuild failures: {report.get('typed_view_rebuild_failure_count')}",
        f"Legacy preservation failures: {report.get('legacy_preservation_failure_count')}",
        f"Public post-validation rejected: {report.get('post_validation_rejected_count')}",
        "",
        "| Question | Route | Complete typed | Selected | Consumer source | Status | Failures |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for row in report.get("results") or []:
        lines.append(
            f"| {row.get('question_id')} | {row.get('route')} | "
            f"{row.get('complete_typed_record_count')} | {row.get('selected_record_count')} | "
            f"{row.get('answer_mode_typed_record_source') or '—'} | "
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
    json_path = output_dir / "claim_ready_evidence_report.json"
    md_path = output_dir / "claim_ready_evidence_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"claim_ready_report_json={json_path}")
    print(f"claim_ready_report_markdown={md_path}")
    return 1 if args.strict and report.get("quality_status") != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
