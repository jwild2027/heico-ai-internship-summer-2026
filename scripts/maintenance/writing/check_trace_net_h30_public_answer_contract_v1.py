#!/usr/bin/env python3
"""Check every public answer in a TRACE-Net benchmark summary against Phase 1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from src.trace_net.writing.trace_net_h30_public_answer_contract_v1 import (
    MODULE as CONTRACT_MODULE,
    STATUS as CONTRACT_STATUS,
    validate_public_answer_contract,
)

MODULE = "check_trace_net_h30_public_answer_contract_v1"
STATUS = "TRACE_NET_H30_PUBLIC_ANSWER_CONTRACT_CHECK_V1"


def _rows(value: Any) -> List[Dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def validate_summary(summary_payload: Mapping[str, Any]) -> Dict[str, Any]:
    records = _rows(summary_payload.get("records"))
    results: List[Dict[str, Any]] = []
    leak_count = 0
    structural_failure_count = 0
    post_validation_rejected_count = 0

    for row in records:
        qid = str(row.get("question_id") or "")
        route = str(row.get("actual_route") or row.get("route") or "")
        answer = str(row.get("answer") or "")
        validation = validate_public_answer_contract(answer, route=route)
        failures = list(validation.get("failures") or [])
        if not bool(row.get("post_validation_accepted")):
            failures.append("post_validation_rejected")
            post_validation_rejected_count += 1
        failures = list(dict.fromkeys(failures))
        leak_count += sum(str(value).startswith("public_leak:") for value in failures)
        structural_failure_count += sum(not str(value).startswith("public_leak:") and value != "post_validation_rejected" for value in failures)
        results.append({
            "question_id": qid,
            "route": route,
            "passed": not failures,
            "failures": failures,
            "headings": validation.get("headings") or [],
            "answer_line_count": validation.get("answer_line_count", 0),
            "evidence_line_count": validation.get("evidence_line_count", 0),
            "limit_line_count": validation.get("limit_line_count", 0),
        })

    passed = sum(bool(row.get("passed")) for row in results)
    return {
        "module": MODULE,
        "status": STATUS,
        "contract_module": CONTRACT_MODULE,
        "contract_status": CONTRACT_STATUS,
        "quality_status": "PASS" if passed == len(results) and results else "FAIL",
        "question_count": len(records),
        "passed_question_count": passed,
        "failed_question_count": len(results) - passed,
        "public_leak_count": leak_count,
        "structural_failure_count": structural_failure_count,
        "post_validation_rejected_count": post_validation_rejected_count,
        "results": results,
    }


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# TRACE-Net H30 Phase 1 Public Answer Contract",
        "",
        f"Status: **{report.get('quality_status')}**",
        "",
        f"Questions passed: {report.get('passed_question_count')}/{report.get('question_count')}",
        f"Public leaks: {report.get('public_leak_count')}",
        f"Structural failures: {report.get('structural_failure_count')}",
        f"Post-validation rejected: {report.get('post_validation_rejected_count')}",
        "",
        "| Question | Route | Status | Failures |",
        "|---|---|---|---|",
    ]
    for row in report.get("results") or []:
        failures = ", ".join(row.get("failures") or []) or "—"
        lines.append(
            f"| {row.get('question_id')} | {row.get('route')} | "
            f"{'PASS' if row.get('passed') else 'FAIL'} | {failures} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary_path = Path(args.summary).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else summary_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    report = validate_summary(payload)
    json_path = output_dir / "public_answer_contract_report.json"
    md_path = output_dir / "public_answer_contract_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"contract_report_json={json_path}")
    print(f"contract_report_markdown={md_path}")
    return 1 if args.strict and report.get("quality_status") != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
