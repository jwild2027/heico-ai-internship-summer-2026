"""Quality checks for TRACE-Net Weighted Search Calibration Report v1."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_weighted_search_calibration import (
    DEFAULT_OUTPUT_DIR,
    _as_dict,
    _read_json,
    _read_jsonl,
    _text,
    _num,
    _write_json,
)


@dataclass(frozen=True)
class WeightedSearchCalibrationQualityPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    summary_path: Path | None = None
    calibration_jsonl_path: Path | None = None
    quality_path: Path | None = None

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / "trace_net_weighted_search_calibration_summary.json")

    @property
    def calibration_jsonl(self) -> Path:
        return self.calibration_jsonl_path or (self.output_dir / "trace_net_weighted_search_calibration_records.jsonl")

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / "trace_net_weighted_search_calibration_quality.json")


@dataclass(frozen=True)
class WeightedSearchCalibrationQualityOptions:
    min_records: int = 1
    min_pages: int = 1
    min_component_breakdown_records: int = 1
    min_rank_comparison_records: int = 1
    min_feedback_adjusted_records: int = 0
    min_feedback_cap_hit_records: int = 0
    min_demotion_shortfall_records: int = 0
    max_unsafe_records: int = 0
    max_excluded_records: int = 0
    max_source_truth_mutations: int = 0
    max_context_warning_signals_used: int = 0
    max_missing_components: int = 0
    require_weights_policy: bool = True
    require_status_ok: bool = True
    write_json: bool = False


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _component_present(row: Mapping[str, Any]) -> bool:
    comps = _as_dict(row.get("components"))
    required = ["base_score", "bucket_bonus", "evidence_diversity_bonus", "exact_match_bonus", "confidence_bonus", "feedback_adjustment"]
    return all(key in comps for key in required)


def evaluate_weighted_search_calibration_quality(paths: WeightedSearchCalibrationQualityPaths, options: WeightedSearchCalibrationQualityOptions | None = None) -> dict[str, Any]:
    options = options or WeightedSearchCalibrationQualityOptions()
    summary = _read_json(paths.summary)
    rows = _read_jsonl(paths.calibration_jsonl)
    jsonl_count = len(rows)
    pages = len({_text(row.get("page_id")) for row in rows if _text(row.get("page_id"))})
    component_records = sum(1 for row in rows if _component_present(row))
    missing_components = jsonl_count - component_records
    rank_comparison = sum(1 for row in rows if row.get("original_rank") is not None and row.get("weighted_rank") is not None)
    feedback_adjusted = sum(1 for row in rows if abs(_num(_as_dict(row.get("components")).get("feedback_adjustment"))) > 0.000001)
    feedback_cap_hits = sum(1 for row in rows if row.get("feedback_cap_hit"))
    demotion_shortfalls = sum(1 for row in rows if row.get("feedback_direction") == "demote" and _num(row.get("additional_demotion_to_fall_below_next")) > 0)
    context_warning_scan = sum(int(_as_dict(row.get("components")).get("context_warning_signals_used") or 0) for row in rows)
    rank_changed_scan = sum(1 for row in rows if row.get("rank_changed"))
    diversity_overrode_scan = sum(1 for row in rows if row.get("evidence_diversity_overrode_feedback"))
    report_summary = {
        "weighted_calibration_summary_present": paths.summary.exists(),
        "weighted_calibration_records_present": paths.calibration_jsonl.exists(),
        "weighted_calibration_status": summary.get("status", "missing"),
        "weighted_calibration_version": summary.get("version", ""),
        "weighted_calibration_query_fingerprint": summary.get("query_fingerprint", ""),
        "weighted_calibration_weights_policy_version": summary.get("weights_policy_version", ""),
        "weighted_calibration_records": summary.get("records", 0),
        "weighted_calibration_jsonl_records": jsonl_count,
        "weighted_calibration_pages": summary.get("pages", pages),
        "weighted_calibration_pages_scan": pages,
        "weighted_calibration_component_breakdown_records": component_records,
        "weighted_calibration_missing_component_records": missing_components,
        "weighted_calibration_rank_comparison_records": rank_comparison,
        "weighted_calibration_feedback_signals_used": summary.get("feedback_signals_used", 0),
        "weighted_calibration_feedback_adjusted_records": summary.get("groups_with_feedback_adjustment", feedback_adjusted),
        "weighted_calibration_feedback_adjusted_scan": feedback_adjusted,
        "weighted_calibration_groups_boosted": summary.get("groups_boosted", 0),
        "weighted_calibration_groups_demoted": summary.get("groups_demoted", 0),
        "weighted_calibration_rank_changed_records": summary.get("rank_changed_records", rank_changed_scan),
        "weighted_calibration_rank_changed_scan": rank_changed_scan,
        "weighted_calibration_feedback_cap_hit_records": summary.get("feedback_cap_hit_records", feedback_cap_hits),
        "weighted_calibration_feedback_cap_hit_scan": feedback_cap_hits,
        "weighted_calibration_demotion_shortfall_records": summary.get("demotion_shortfall_records", demotion_shortfalls),
        "weighted_calibration_demotion_shortfall_scan": demotion_shortfalls,
        "weighted_calibration_evidence_diversity_overrode_feedback_records": summary.get("evidence_diversity_overrode_feedback_records", diversity_overrode_scan),
        "weighted_calibration_evidence_diversity_overrode_feedback_scan": diversity_overrode_scan,
        "weighted_calibration_unsafe_records": summary.get("unsafe_records", 0),
        "weighted_calibration_excluded_records": summary.get("excluded_records", 0),
        "weighted_calibration_source_truth_mutations": summary.get("source_truth_mutation_records", 0),
        "weighted_calibration_context_warning_signals_used": summary.get("context_warning_signals_used", context_warning_scan),
        "weighted_calibration_context_warning_signals_used_scan": context_warning_scan,
        "weighted_calibration_top_page_before": summary.get("top_page_before", ""),
        "weighted_calibration_top_page_after": summary.get("top_page_after", ""),
        "weighted_calibration_recommendations": summary.get("recommendations", []),
        "weighted_calibration_graph_nodes": summary.get("graph_nodes", 0),
        "weighted_calibration_graph_edges": summary.get("graph_edges", 0),
        "weighted_calibration_summary_path": str(paths.summary),
        "weighted_calibration_records_path": str(paths.calibration_jsonl),
    }
    checks: list[dict[str, Any]] = []
    checks.append(_check("artifacts_present", paths.summary.exists() and paths.calibration_jsonl.exists(), f"summary={paths.summary.exists()}; records={paths.calibration_jsonl.exists()}"))
    if options.require_status_ok:
        checks.append(_check("status_ok", summary.get("status") == "OK", f"status={summary.get('status')}"))
    checks.append(_check("records", int(summary.get("records") or 0) >= options.min_records and jsonl_count >= options.min_records, f"summary={summary.get('records')}; jsonl={jsonl_count}; minimum={options.min_records}"))
    checks.append(_check("record_count_match", int(summary.get("records") or 0) == jsonl_count, f"summary={summary.get('records')}; jsonl={jsonl_count}"))
    checks.append(_check("pages", pages >= options.min_pages or int(summary.get("pages") or 0) >= options.min_pages, f"pages summary={summary.get('pages')}; scan={pages}; minimum={options.min_pages}"))
    checks.append(_check("component_breakdowns", component_records >= options.min_component_breakdown_records, f"component_records={component_records}; minimum={options.min_component_breakdown_records}"))
    checks.append(_check("missing_components", missing_components <= options.max_missing_components, f"missing_components={missing_components}; max={options.max_missing_components}"))
    checks.append(_check("rank_comparison", rank_comparison >= options.min_rank_comparison_records, f"rank_comparison={rank_comparison}; minimum={options.min_rank_comparison_records}"))
    if options.require_weights_policy:
        version = _text(summary.get("weights_policy_version"))
        checks.append(_check("weights_policy_present", bool(version) and version != "unknown", f"weights_policy_version={version}"))
    checks.append(_check("feedback_adjusted_records", feedback_adjusted >= options.min_feedback_adjusted_records and int(summary.get("groups_with_feedback_adjustment") or 0) >= options.min_feedback_adjusted_records, f"feedback_adjusted summary={summary.get('groups_with_feedback_adjustment')}; scan={feedback_adjusted}; minimum={options.min_feedback_adjusted_records}"))
    checks.append(_check("feedback_cap_hit_records", feedback_cap_hits >= options.min_feedback_cap_hit_records and int(summary.get("feedback_cap_hit_records") or 0) >= options.min_feedback_cap_hit_records, f"cap_hits summary={summary.get('feedback_cap_hit_records')}; scan={feedback_cap_hits}; minimum={options.min_feedback_cap_hit_records}"))
    checks.append(_check("demotion_shortfall_records", demotion_shortfalls >= options.min_demotion_shortfall_records and int(summary.get("demotion_shortfall_records") or 0) >= options.min_demotion_shortfall_records, f"shortfalls summary={summary.get('demotion_shortfall_records')}; scan={demotion_shortfalls}; minimum={options.min_demotion_shortfall_records}"))
    checks.append(_check("unsafe_records", int(summary.get("unsafe_records") or 0) <= options.max_unsafe_records, f"unsafe={summary.get('unsafe_records')}; max={options.max_unsafe_records}"))
    checks.append(_check("excluded_records", int(summary.get("excluded_records") or 0) <= options.max_excluded_records, f"excluded={summary.get('excluded_records')}; max={options.max_excluded_records}"))
    checks.append(_check("source_truth_mutations", int(summary.get("source_truth_mutation_records") or 0) <= options.max_source_truth_mutations, f"mutations={summary.get('source_truth_mutation_records')}; max={options.max_source_truth_mutations}"))
    checks.append(_check("context_warning_signals_ignored", context_warning_scan <= options.max_context_warning_signals_used and int(summary.get("context_warning_signals_used") or 0) <= options.max_context_warning_signals_used, f"context_warning summary={summary.get('context_warning_signals_used')}; scan={context_warning_scan}; max={options.max_context_warning_signals_used}"))
    status = "OK" if all(check["ok"] for check in checks) else "FAIL"
    report = {"status": status, "summary": report_summary, "checks": checks}
    if options.write_json:
        _write_json(paths.quality, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net weighted search calibration quality.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--records-jsonl", type=Path, default=None)
    parser.add_argument("--quality", type=Path, default=None)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-component-breakdown-records", type=int, default=1)
    parser.add_argument("--min-rank-comparison-records", type=int, default=1)
    parser.add_argument("--min-feedback-adjusted-records", type=int, default=0)
    parser.add_argument("--min-feedback-cap-hit-records", type=int, default=0)
    parser.add_argument("--min-demotion-shortfall-records", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-excluded-records", type=int, default=0)
    parser.add_argument("--max-source-truth-mutations", type=int, default=0)
    parser.add_argument("--max-context-warning-signals-used", type=int, default=0)
    parser.add_argument("--max-missing-components", type=int, default=0)
    parser.add_argument("--no-require-weights-policy", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    paths = WeightedSearchCalibrationQualityPaths(output_dir=args.output_dir, summary_path=args.summary, calibration_jsonl_path=args.records_jsonl, quality_path=args.quality)
    options = WeightedSearchCalibrationQualityOptions(
        min_records=args.min_records,
        min_pages=args.min_pages,
        min_component_breakdown_records=args.min_component_breakdown_records,
        min_rank_comparison_records=args.min_rank_comparison_records,
        min_feedback_adjusted_records=args.min_feedback_adjusted_records,
        min_feedback_cap_hit_records=args.min_feedback_cap_hit_records,
        min_demotion_shortfall_records=args.min_demotion_shortfall_records,
        max_unsafe_records=args.max_unsafe_records,
        max_excluded_records=args.max_excluded_records,
        max_source_truth_mutations=args.max_source_truth_mutations,
        max_context_warning_signals_used=args.max_context_warning_signals_used,
        max_missing_components=args.max_missing_components,
        require_weights_policy=not args.no_require_weights_policy,
        write_json=args.write_json,
    )
    result = evaluate_weighted_search_calibration_quality(paths, options)
    print("TRACE-Net weighted search calibration quality gate")
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
