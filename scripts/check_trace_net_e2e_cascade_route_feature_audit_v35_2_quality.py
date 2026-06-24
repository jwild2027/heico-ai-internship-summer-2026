from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _add(checks: List[Dict[str, Any]], name: str, observed: Any, expected: str, passed: bool) -> None:
    checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})


def check_report(report: Dict[str, Any], args: argparse.Namespace) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    _add(checks, "quality_status", report.get("quality_status"), "== PASS", report.get("quality_status") == "PASS")
    _add(checks, "source_page_count", report.get("source_page_count"), f">= {args.min_source_pages}", report.get("source_page_count", 0) >= args.min_source_pages)
    _add(checks, "feature_record_count", report.get("feature_record_count"), f">= {args.min_feature_records}", report.get("feature_record_count", 0) >= args.min_feature_records)
    _add(checks, "manual_screened_diagram_page_count", report.get("manual_screened_diagram_page_count"), f">= {args.min_manual_screened_diagram_pages}", report.get("manual_screened_diagram_page_count", 0) >= args.min_manual_screened_diagram_pages)
    if args.expected_actual_diagram_pages is not None:
        _add(checks, "actual_diagram_page_count", report.get("actual_diagram_page_count"), f"== {args.expected_actual_diagram_pages}", report.get("actual_diagram_page_count") == args.expected_actual_diagram_pages)
    _add(checks, "feature_column_count", report.get("feature_column_count"), f">= {args.min_feature_columns}", report.get("feature_column_count", 0) >= args.min_feature_columns)
    _add(checks, "confusion_matrix_total", report.get("confusion_matrix_total"), f">= {args.min_confusion_matrix_total}", report.get("confusion_matrix_total", 0) >= args.min_confusion_matrix_total)
    _add(checks, "label_coverage_count", report.get("label_coverage_count"), f">= {args.min_label_coverage}", report.get("label_coverage_count", 0) >= args.min_label_coverage)
    _add(checks, "answer_permission_count", report.get("answer_permission_count"), f"<= {args.max_answer_permission_count}", report.get("answer_permission_count", 0) <= args.max_answer_permission_count)
    _add(checks, "source_truth_mutation_allowed_count", report.get("source_truth_mutation_allowed_count"), f"<= {args.max_source_truth_mutation_allowed}", report.get("source_truth_mutation_allowed_count", 0) <= args.max_source_truth_mutation_allowed)
    if args.require_no_answer_permission:
        _add(checks, "require_no_answer_permission", report.get("answer_permission_count"), "== 0", report.get("answer_permission_count", 0) == 0)
    return checks


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TRACE-Net Cascade Route Feature Audit v35.2 Quality")
    p.add_argument("--report-path", required=True, type=Path)
    p.add_argument("--min-source-pages", type=int, default=1)
    p.add_argument("--min-feature-records", type=int, default=1)
    p.add_argument("--min-manual-screened-diagram-pages", type=int, default=1)
    p.add_argument("--expected-actual-diagram-pages", type=int, default=None)
    p.add_argument("--min-feature-columns", type=int, default=10)
    p.add_argument("--min-confusion-matrix-total", type=int, default=1)
    p.add_argument("--min-label-coverage", type=int, default=1)
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
    print("TRACE-Net Cascade Route Feature Audit v35.2 Quality")
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
