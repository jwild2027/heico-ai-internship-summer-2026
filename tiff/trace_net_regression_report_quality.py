from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/regression")
DEFAULT_SUMMARY = DEFAULT_OUTPUT_DIR / "trace_net_regression_report_summary.json"
DEFAULT_RECORDS = DEFAULT_OUTPUT_DIR / "trace_net_regression_report_cases.jsonl"
DEFAULT_QUALITY = DEFAULT_OUTPUT_DIR / "trace_net_regression_report_quality.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        return {"_read_error": str(exc)}


def _read_jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                continue
            count += 1
    return count


def _summary_int(summary: Dict[str, Any], keys: List[str], default: int = 0) -> int:
    for key in keys:
        value = summary.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                continue
    return default


def _summary_list(summary: Dict[str, Any], keys: List[str]) -> List[Any]:
    for key in keys:
        value = summary.get(key)
        if isinstance(value, list):
            return value
    return []


def _check(name: str, ok: bool, detail: str) -> Dict[str, Any]:
    return {"name": name, "status": "OK" if ok else "FAIL", "ok": ok, "detail": detail}


def run_quality(
    summary_path: Path = DEFAULT_SUMMARY,
    records_path: Path = DEFAULT_RECORDS,
    quality_path: Path = DEFAULT_QUALITY,
    min_cases: int = 1,
    max_failing_cases: int = 0,
    max_unsafe_answer_cases: int = 0,
    max_weighted_unsafe_cases: int = 0,
    max_source_truth_mutation_cases: int = 0,
    max_context_warning_used_cases: int = 0,
    max_missing_record_mismatch: int = 0,
    min_review_cases: int = 0,
    write_json: bool = False,
) -> Dict[str, Any]:
    summary = _read_json(summary_path)
    records_count = _read_jsonl_count(records_path)

    status = summary.get("status")
    case_count = _summary_int(summary, ["case_count", "records", "case_records"])
    case_fail_count = _summary_int(summary, ["case_fail_count", "failed_cases"])
    review_case_count = _summary_int(summary, ["review_case_count", "review_needed_cases"])
    unsafe_answer_case_count = _summary_int(summary, ["unsafe_answer_case_count", "unsafe_answer_group_total"])
    weighted_unsafe_case_count = _summary_int(summary, ["weighted_unsafe_case_count", "unsafe_weighted_record_total"])
    source_truth_mutation_case_count = _summary_int(summary, ["source_truth_mutation_case_count", "source_truth_mutation_total"])
    context_warning_used_case_count = _summary_int(summary, ["context_warning_used_case_count", "context_warning_signals_used_total"])
    top_changed_case_count = _summary_int(summary, ["top_changed_case_count", "top_page_changed_cases"])
    tie_case_count = _summary_int(summary, ["tie_case_count", "tie_heavy_cases"])
    graph_nodes = _summary_int(summary, ["graph_nodes"])
    graph_edges = _summary_int(summary, ["graph_edges"])

    checks: List[Dict[str, Any]] = []
    checks.append(_check("artifacts_present", summary_path.exists() and records_path.exists(), f"summary={summary_path.exists()}; records={records_path.exists()}"))
    checks.append(_check("status_ok", status == "OK", f"status={status!r}"))
    checks.append(_check("case_count", case_count >= min_cases, f"cases={case_count}; minimum={min_cases}"))
    mismatch = abs(case_count - records_count)
    checks.append(_check("record_count_match", mismatch <= max_missing_record_mismatch, f"summary={case_count}; jsonl={records_count}; mismatch={mismatch}; max={max_missing_record_mismatch}"))
    checks.append(_check("failing_cases", case_fail_count <= max_failing_cases, f"failing={case_fail_count}; max={max_failing_cases}"))
    checks.append(_check("unsafe_answer_cases", unsafe_answer_case_count <= max_unsafe_answer_cases, f"unsafe_answer={unsafe_answer_case_count}; max={max_unsafe_answer_cases}"))
    checks.append(_check("weighted_unsafe_cases", weighted_unsafe_case_count <= max_weighted_unsafe_cases, f"weighted_unsafe={weighted_unsafe_case_count}; max={max_weighted_unsafe_cases}"))
    checks.append(_check("source_truth_mutations", source_truth_mutation_case_count <= max_source_truth_mutation_cases, f"mutations={source_truth_mutation_case_count}; max={max_source_truth_mutation_cases}"))
    checks.append(_check("context_warning_used", context_warning_used_case_count <= max_context_warning_used_cases, f"context_warning_used={context_warning_used_case_count}; max={max_context_warning_used_cases}"))
    checks.append(_check("review_cases", review_case_count >= min_review_cases, f"review={review_case_count}; minimum={min_review_cases}"))
    checks.append(_check("graph_nodes", graph_nodes >= case_count, f"graph_nodes={graph_nodes}; cases={case_count}"))
    checks.append(_check("graph_edges", graph_edges >= max(0, case_count - 1), f"graph_edges={graph_edges}; cases={case_count}"))

    ok = all(item["ok"] for item in checks)
    quality = {
        "created_at": _utc_now(),
        "status": "OK" if ok else "FAIL",
        "regression_summary_present": summary_path.exists(),
        "regression_records_present": records_path.exists(),
        "regression_status": status,
        "regression_cases": case_count,
        "regression_jsonl_records": records_count,
        "regression_case_fail_count": case_fail_count,
        "regression_review_case_count": review_case_count,
        "regression_unsafe_answer_case_count": unsafe_answer_case_count,
        "regression_weighted_unsafe_case_count": weighted_unsafe_case_count,
        "regression_source_truth_mutation_case_count": source_truth_mutation_case_count,
        "regression_context_warning_used_case_count": context_warning_used_case_count,
        "regression_top_changed_case_count": top_changed_case_count,
        "regression_tie_case_count": tie_case_count,
        "regression_total_answer_pages": _summary_int(summary, ["total_answer_pages", "answer_page_total"]),
        "regression_total_evidence_records": _summary_int(summary, ["total_evidence_records", "answer_evidence_total"]),
        "regression_review_case_ids": _summary_list(summary, ["review_case_ids", "cases_requiring_review"]),
        "regression_failing_case_ids": _summary_list(summary, ["failing_case_ids", "cases_failing"]),
        "regression_graph_nodes": graph_nodes,
        "regression_graph_edges": graph_edges,
        "regression_summary_path": str(summary_path),
        "regression_records_path": str(records_path),
        "checks": checks,
    }

    if write_json:
        quality_path.parent.mkdir(parents=True, exist_ok=True)
        quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True), encoding="utf-8")
    return quality


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net fixed regression report quality")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--records", default=str(DEFAULT_RECORDS))
    parser.add_argument("--quality", default=str(DEFAULT_QUALITY))
    parser.add_argument("--min-cases", type=int, default=1)
    parser.add_argument("--max-failing-cases", type=int, default=0)
    parser.add_argument("--max-unsafe-answer-cases", type=int, default=0)
    parser.add_argument("--max-weighted-unsafe-cases", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-cases", type=int, default=0)
    parser.add_argument("--max-context-warning-used-cases", type=int, default=0)
    parser.add_argument("--min-review-cases", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    quality = run_quality(
        summary_path=Path(args.summary),
        records_path=Path(args.records),
        quality_path=Path(args.quality),
        min_cases=args.min_cases,
        max_failing_cases=args.max_failing_cases,
        max_unsafe_answer_cases=args.max_unsafe_answer_cases,
        max_weighted_unsafe_cases=args.max_weighted_unsafe_cases,
        max_source_truth_mutation_cases=args.max_source_truth_mutation_cases,
        max_context_warning_used_cases=args.max_context_warning_used_cases,
        min_review_cases=args.min_review_cases,
        write_json=args.write_json,
    )

    print("TRACE-Net fixed regression report quality gate")
    print(f"  Status: {quality['status']}")
    print("  Summary:")
    for key in [
        "regression_cases",
        "regression_jsonl_records",
        "regression_case_fail_count",
        "regression_review_case_count",
        "regression_unsafe_answer_case_count",
        "regression_weighted_unsafe_case_count",
        "regression_top_changed_case_count",
        "regression_tie_case_count",
        "regression_graph_nodes",
        "regression_graph_edges",
    ]:
        print(f"    {key}: {quality.get(key)}")
    print("  Checks:")
    for item in quality["checks"]:
        print(f"    {item['status']} {item['name']}: {item['detail']}")
    if args.write_json:
        print(f"\nJSON: {args.quality}")
    return 0 if quality["status"] == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
