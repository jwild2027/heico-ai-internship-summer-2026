"""Quality checks for TRACE-Net Weighted Search Simulation v1."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .trace_net_weighted_search_simulation import DEFAULT_OUTPUT_DIR, _as_dict, _read_json, _read_jsonl, _text, _write_json


@dataclass(frozen=True)
class WeightedSearchQualityPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    summary_path: Path | None = None
    results_jsonl_path: Path | None = None
    quality_path: Path | None = None

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / "trace_net_weighted_search_simulation_summary.json")

    @property
    def results_jsonl(self) -> Path:
        return self.results_jsonl_path or (self.output_dir / "trace_net_weighted_search_simulation_results.jsonl")

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / "trace_net_weighted_search_simulation_quality.json")


@dataclass(frozen=True)
class WeightedSearchQualityOptions:
    min_groups: int = 1
    min_pages: int = 1
    min_rank_comparison_records: int = 1
    min_feedback_signals_used: int = 0
    min_groups_adjusted: int = 0
    min_rank_changed_records: int = 0
    max_unsafe_results: int = 0
    max_excluded_results: int = 0
    max_source_truth_mutations: int = 0
    max_context_warning_signals_used: int = 0
    require_weights_policy: bool = True
    require_status_ok: bool = True
    write_json: bool = False


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def evaluate_weighted_search_quality(paths: WeightedSearchQualityPaths, options: WeightedSearchQualityOptions | None = None) -> dict[str, Any]:
    options = options or WeightedSearchQualityOptions()
    summary = _read_json(paths.summary)
    rows = _read_jsonl(paths.results_jsonl)
    jsonl_count = len(rows)
    pages = len({_text(row.get("page_id")) for row in rows if _text(row.get("page_id"))})
    unsafe_scan = sum(1 for row in rows if not row.get("weighted_simulation_safe", True))
    excluded_scan = sum(1 for row in rows if int(row.get("excluded_supporting_results") or 0) > 0)
    mutation_scan = sum(1 for row in rows if row.get("source_truth_mutation"))
    warning_scan = sum(int(_as_dict(row.get("weighted_score_components")).get("context_warning_signals_used") or 0) for row in rows)
    feedback_scan = sum(len(_as_dict(row.get("weighted_score_components")).get("feedback_signals_used") or []) for row in rows)
    adjusted_scan = sum(1 for row in rows if abs(_num(_as_dict(row.get("weighted_score_components")).get("feedback_adjustment"))) > 0.000001)
    rank_changed_scan = sum(1 for row in rows if row.get("rank_changed"))
    rank_comparison_scan = sum(1 for row in rows if row.get("original_rank") is not None and row.get("weighted_rank") is not None)
    report_summary = {
        "weighted_search_summary_present": paths.summary.exists(),
        "weighted_search_results_present": paths.results_jsonl.exists(),
        "weighted_search_status": summary.get("status", "missing"),
        "weighted_search_version": summary.get("version", ""),
        "weighted_search_query_fingerprint": summary.get("query_fingerprint", ""),
        "weighted_search_weights_policy_version": summary.get("weights_policy_version", ""),
        "weighted_search_grouped_input_records": summary.get("grouped_input_records", 0),
        "weighted_search_records": summary.get("weighted_group_records", 0),
        "weighted_search_jsonl_records": jsonl_count,
        "weighted_search_pages": summary.get("pages", pages),
        "weighted_search_pages_scan": pages,
        "weighted_search_feedback_enabled": summary.get("feedback_enabled", False),
        "weighted_search_matching_feedback_signals": summary.get("matching_feedback_signal_records", 0),
        "weighted_search_feedback_signals_used": summary.get("feedback_signals_used", 0),
        "weighted_search_feedback_signals_used_scan": feedback_scan,
        "weighted_search_groups_adjusted": summary.get("groups_with_feedback_adjustment", 0),
        "weighted_search_groups_adjusted_scan": adjusted_scan,
        "weighted_search_rank_changed_records": summary.get("rank_changed_records", 0),
        "weighted_search_rank_changed_scan": rank_changed_scan,
        "weighted_search_rank_comparison_records": rank_comparison_scan,
        "weighted_search_unsafe_results": summary.get("unsafe_weighted_records", 0),
        "weighted_search_unsafe_scan": unsafe_scan,
        "weighted_search_excluded_results": summary.get("excluded_weighted_records", 0),
        "weighted_search_excluded_scan": excluded_scan,
        "weighted_search_source_truth_mutations": summary.get("source_truth_mutation_records", 0),
        "weighted_search_source_truth_mutation_scan": mutation_scan,
        "weighted_search_context_warning_signals_used": summary.get("context_warning_signals_used", 0),
        "weighted_search_context_warning_signals_used_scan": warning_scan,
        "weighted_search_top_page_before": summary.get("top_page_before", ""),
        "weighted_search_top_page_after": summary.get("top_page_after", ""),
        "weighted_search_top_page_changed": summary.get("top_page_changed", False),
        "weighted_search_graph_nodes": summary.get("graph_nodes", 0),
        "weighted_search_graph_edges": summary.get("graph_edges", 0),
        "weighted_search_summary_path": str(paths.summary),
        "weighted_search_results_path": str(paths.results_jsonl),
    }
    checks: list[dict[str, Any]] = []
    checks.append(_check("artifacts_present", paths.summary.exists() and paths.results_jsonl.exists(), f"summary={paths.summary.exists()}; results={paths.results_jsonl.exists()}"))
    if options.require_status_ok:
        checks.append(_check("status_ok", summary.get("status") == "OK", f"status={summary.get('status')}"))
    checks.append(_check("groups", int(summary.get("weighted_group_records") or 0) >= options.min_groups and jsonl_count >= options.min_groups, f"summary={summary.get('weighted_group_records')}; jsonl={jsonl_count}; minimum={options.min_groups}"))
    checks.append(_check("record_count_match", int(summary.get("weighted_group_records") or 0) == jsonl_count, f"summary={summary.get('weighted_group_records')}; jsonl={jsonl_count}"))
    checks.append(_check("pages", pages >= options.min_pages or int(summary.get("pages") or 0) >= options.min_pages, f"pages summary={summary.get('pages')}; scan={pages}; minimum={options.min_pages}"))
    checks.append(_check("rank_comparison", rank_comparison_scan >= options.min_rank_comparison_records, f"rank_comparison_records={rank_comparison_scan}; minimum={options.min_rank_comparison_records}"))
    if options.require_weights_policy:
        version = _text(summary.get("weights_policy_version"))
        checks.append(_check("weights_policy_present", bool(version) and version != "unknown", f"weights_policy_version={version}"))
    checks.append(_check("feedback_signals_used", feedback_scan >= options.min_feedback_signals_used and int(summary.get("feedback_signals_used") or 0) >= options.min_feedback_signals_used, f"signals_used summary={summary.get('feedback_signals_used')}; scan={feedback_scan}; minimum={options.min_feedback_signals_used}"))
    checks.append(_check("groups_adjusted", adjusted_scan >= options.min_groups_adjusted, f"groups_adjusted={adjusted_scan}; minimum={options.min_groups_adjusted}"))
    checks.append(_check("rank_changed", rank_changed_scan >= options.min_rank_changed_records, f"rank_changed={rank_changed_scan}; minimum={options.min_rank_changed_records}"))
    checks.append(_check("unsafe_results", unsafe_scan <= options.max_unsafe_results and int(summary.get("unsafe_weighted_records") or 0) <= options.max_unsafe_results, f"unsafe summary={summary.get('unsafe_weighted_records')}; scan={unsafe_scan}; max={options.max_unsafe_results}"))
    checks.append(_check("excluded_results", excluded_scan <= options.max_excluded_results and int(summary.get("excluded_weighted_records") or 0) <= options.max_excluded_results, f"excluded summary={summary.get('excluded_weighted_records')}; scan={excluded_scan}; max={options.max_excluded_results}"))
    checks.append(_check("source_truth_mutations", mutation_scan <= options.max_source_truth_mutations and int(summary.get("source_truth_mutation_records") or 0) <= options.max_source_truth_mutations, f"mutations summary={summary.get('source_truth_mutation_records')}; scan={mutation_scan}; max={options.max_source_truth_mutations}"))
    checks.append(_check("context_warning_signals_ignored", warning_scan <= options.max_context_warning_signals_used and int(summary.get("context_warning_signals_used") or 0) <= options.max_context_warning_signals_used, f"context_warning_signals_used summary={summary.get('context_warning_signals_used')}; scan={warning_scan}; max={options.max_context_warning_signals_used}"))
    status = "OK" if all(check["ok"] for check in checks) else "FAIL"
    report = {"status": status, "summary": report_summary, "checks": checks}
    if options.write_json:
        _write_json(paths.quality, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net weighted search simulation quality.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--results-jsonl", type=Path, default=None)
    parser.add_argument("--quality", type=Path, default=None)
    parser.add_argument("--min-groups", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-rank-comparison-records", type=int, default=1)
    parser.add_argument("--min-feedback-signals-used", type=int, default=0)
    parser.add_argument("--min-groups-adjusted", type=int, default=0)
    parser.add_argument("--min-rank-changed-records", type=int, default=0)
    parser.add_argument("--max-unsafe-results", type=int, default=0)
    parser.add_argument("--max-excluded-results", type=int, default=0)
    parser.add_argument("--max-source-truth-mutations", type=int, default=0)
    parser.add_argument("--max-context-warning-signals-used", type=int, default=0)
    parser.add_argument("--no-require-weights-policy", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    paths = WeightedSearchQualityPaths(output_dir=args.output_dir, summary_path=args.summary, results_jsonl_path=args.results_jsonl, quality_path=args.quality)
    options = WeightedSearchQualityOptions(
        min_groups=args.min_groups,
        min_pages=args.min_pages,
        min_rank_comparison_records=args.min_rank_comparison_records,
        min_feedback_signals_used=args.min_feedback_signals_used,
        min_groups_adjusted=args.min_groups_adjusted,
        min_rank_changed_records=args.min_rank_changed_records,
        max_unsafe_results=args.max_unsafe_results,
        max_excluded_results=args.max_excluded_results,
        max_source_truth_mutations=args.max_source_truth_mutations,
        max_context_warning_signals_used=args.max_context_warning_signals_used,
        require_weights_policy=not args.no_require_weights_policy,
        write_json=args.write_json,
    )
    result = evaluate_weighted_search_quality(paths, options)
    print("TRACE-Net weighted search simulation quality gate")
    print(f"  Status: {result['status']}")
    print("  Summary:")
    for key, value in result.get("summary", {}).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in result.get("checks", []):
        label = "OK" if check.get("ok") else "FAIL"
        print(f"    {label} {check.get('name')}: {check.get('detail')}")
    if args.write_json:
        print(f"\nJSON: {paths.quality}")
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
