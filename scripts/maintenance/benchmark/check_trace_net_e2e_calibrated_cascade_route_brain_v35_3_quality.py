from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _add(checks: List[Dict[str, Any]], name: str, observed: Any, expected: str, passed: bool) -> None:
    checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def check_report(report: Dict[str, Any], args: argparse.Namespace) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    _add(checks, "quality_status", report.get("quality_status"), "== PASS", report.get("quality_status") == "PASS")
    _add(checks, "source_page_count", report.get("source_page_count"), f">= {args.min_source_pages}", report.get("source_page_count", 0) >= args.min_source_pages)
    _add(checks, "route_decision_count", report.get("route_decision_count"), f">= {args.min_route_decisions}", report.get("route_decision_count", 0) >= args.min_route_decisions)
    _add(checks, "actual_diagram_page_count", report.get("actual_diagram_page_count"), f">= {args.min_actual_diagram_pages}", report.get("actual_diagram_page_count", 0) >= args.min_actual_diagram_pages)
    _add(checks, "diagram_recall", report.get("diagram_recall"), f">= {args.min_diagram_recall}", _safe_float(report.get("diagram_recall")) >= args.min_diagram_recall)
    _add(checks, "diagram_precision", report.get("diagram_precision"), f">= {args.min_diagram_precision}", _safe_float(report.get("diagram_precision")) >= args.min_diagram_precision)
    _add(checks, "false_negative_diagram_count", report.get("false_negative_diagram_count"), f"<= {args.max_false_negative_diagram_count}", report.get("false_negative_diagram_count", 0) <= args.max_false_negative_diagram_count)
    _add(checks, "fishnet_review_queue_count", report.get("fishnet_review_queue_count"), f">= {args.min_fishnet_review_queue_count}", report.get("fishnet_review_queue_count", 0) >= args.min_fishnet_review_queue_count)
    _add(checks, "answer_permission_count", report.get("answer_permission_count"), f"<= {args.max_answer_permission_count}", report.get("answer_permission_count", 0) <= args.max_answer_permission_count)
    _add(checks, "source_truth_mutation_allowed_count", report.get("source_truth_mutation_allowed_count"), f"<= {args.max_source_truth_mutation_allowed}", report.get("source_truth_mutation_allowed_count", 0) <= args.max_source_truth_mutation_allowed)
    if args.require_no_answer_permission:
        _add(checks, "require_no_answer_permission", report.get("answer_permission_count"), "== 0", report.get("answer_permission_count", 0) == 0)
    return checks


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TRACE-Net Calibrated Cascade Route Brain v35.3 Quality")
    p.add_argument("--report-path", required=True, type=Path)
    p.add_argument("--min-source-pages", type=int, default=1)
    p.add_argument("--min-route-decisions", type=int, default=1)
    p.add_argument("--min-actual-diagram-pages", type=int, default=1)
    p.add_argument("--min-diagram-recall", type=float, default=0.0)
    p.add_argument("--min-diagram-precision", type=float, default=0.0)
    p.add_argument("--max-false-negative-diagram-count", type=int, default=999999)
    p.add_argument("--min-fishnet-review-queue-count", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--write-json", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    report = json.loads(args.report_path.read_text(encoding="utf-8"))
    checks = check_report(report, args)
    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    print("TRACE-Net Calibrated Cascade Route Brain v35.3 Quality")
    print(f" quality_status: {status}")
    for c in checks:
        tag = "PASS" if c["passed"] else "FAIL"
        print(f" {tag} {c['name']}: observed={c['observed']} expected={c['expected']}")
    if args.write_json:
        report["quality_status"] = status
        report["quality_checks"] = checks
        args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
