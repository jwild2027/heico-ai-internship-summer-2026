"""Quality gate for TRACE-Net Feedback-Aware Search Simulation v1."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from tiff.trace_net_feedback_search_simulation import DEFAULT_OUTPUT_DIR, _read_json, _read_jsonl, _write_json
import json


@dataclass(frozen=True)
class FeedbackSearchSimulationQualityPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    simulation_summary_path: Path | None = None
    simulation_jsonl_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    quality_path: Path | None = None

    @property
    def summary(self) -> Path:
        return self.simulation_summary_path or (self.output_dir / "trace_net_feedback_search_simulation_summary.json")

    @property
    def simulation_jsonl(self) -> Path:
        return self.simulation_jsonl_path or (self.output_dir / "trace_net_feedback_search_simulation_results.jsonl")

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / "trace_net_feedback_search_simulation_graph_nodes.json")

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / "trace_net_feedback_search_simulation_graph_edges.json")

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / "trace_net_feedback_search_simulation_quality.json")


@dataclass(frozen=True)
class FeedbackSearchSimulationQualityOptions:
    min_groups: int = 1
    min_feedback_signals_used: int = 0
    min_matching_feedback_signals: int = 0
    min_groups_adjusted: int = 0
    min_rank_changed_records: int = 0
    max_unsafe_results: int = 0
    max_excluded_results: int = 0
    max_source_truth_mutations: int = 0
    max_context_warning_signals_used: int = 0
    require_status_ok: bool = True
    write_json: bool = False


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def check_feedback_search_simulation_quality(paths: FeedbackSearchSimulationQualityPaths, options: FeedbackSearchSimulationQualityOptions) -> dict[str, Any]:
    summary = _read_json(paths.summary)
    rows = _read_jsonl(paths.simulation_jsonl)
    try:
        nodes_obj = json.loads(paths.graph_nodes.read_text(encoding="utf-8")) if paths.graph_nodes.exists() else []
    except Exception:
        nodes_obj = []
    try:
        edges_obj = json.loads(paths.graph_edges.read_text(encoding="utf-8")) if paths.graph_edges.exists() else []
    except Exception:
        edges_obj = []
    nodes_len = len(nodes_obj) if isinstance(nodes_obj, list) else 0
    edges_len = len(edges_obj) if isinstance(edges_obj, list) else 0

    unsafe_scan = sum(1 for r in rows if r.get("safe_group_after_feedback") is False)
    excluded_scan = sum(1 for r in rows if int(r.get("excluded_supporting_results") or 0) > 0)
    signals_used_scan = sum(int(r.get("feedback_signal_count") or 0) for r in rows)
    adjusted_scan = sum(1 for r in rows if abs(float(r.get("feedback_score_delta") or 0.0)) > 0)
    rank_changed_scan = sum(1 for r in rows if int(r.get("rank_delta") or 0) != 0)
    source_truth_mutation_scan = sum(1 for r in rows if r.get("source_truth_mutation") or r.get("ranking_mutation") is True)

    report_summary = {
        "feedback_search_sim_summary_present": paths.summary.exists(),
        "feedback_search_sim_results_present": paths.simulation_jsonl.exists(),
        "feedback_search_sim_status": summary.get("status"),
        "feedback_search_sim_version": summary.get("version"),
        "feedback_search_sim_query_fingerprint": summary.get("query_fingerprint"),
        "feedback_search_sim_grouped_input_records": summary.get("grouped_input_records", 0),
        "feedback_search_sim_records": summary.get("simulated_group_records", len(rows)),
        "feedback_search_sim_jsonl_records": len(rows),
        "feedback_search_sim_matching_feedback_signals": summary.get("matching_feedback_signal_records", 0),
        "feedback_search_sim_feedback_signals_used": summary.get("feedback_signals_used", signals_used_scan),
        "feedback_search_sim_feedback_signals_used_scan": signals_used_scan,
        "feedback_search_sim_groups_adjusted": summary.get("groups_with_feedback_adjustment", adjusted_scan),
        "feedback_search_sim_groups_adjusted_scan": adjusted_scan,
        "feedback_search_sim_rank_changed_records": summary.get("rank_changed_records", rank_changed_scan),
        "feedback_search_sim_rank_changed_scan": rank_changed_scan,
        "feedback_search_sim_groups_boosted": summary.get("groups_boosted", 0),
        "feedback_search_sim_groups_demoted": summary.get("groups_demoted", 0),
        "feedback_search_sim_unsafe_results": summary.get("unsafe_simulated_records", unsafe_scan),
        "feedback_search_sim_unsafe_scan": unsafe_scan,
        "feedback_search_sim_excluded_results": summary.get("excluded_simulated_records", excluded_scan),
        "feedback_search_sim_excluded_scan": excluded_scan,
        "feedback_search_sim_source_truth_mutations": summary.get("source_truth_mutation_records", source_truth_mutation_scan),
        "feedback_search_sim_source_truth_mutation_scan": source_truth_mutation_scan,
        "feedback_search_sim_context_warning_signals_used": summary.get("context_warning_signals_used", 0),
        "feedback_search_sim_top_page_before": summary.get("top_page_before"),
        "feedback_search_sim_top_page_after": summary.get("top_page_after"),
        "feedback_search_sim_graph_nodes": nodes_len,
        "feedback_search_sim_graph_edges": edges_len,
        "feedback_search_sim_summary_path": str(paths.summary),
        "feedback_search_sim_results_path": str(paths.simulation_jsonl),
    }

    checks: list[dict[str, Any]] = []
    checks.append(_check("artifacts_present", paths.summary.exists() and paths.simulation_jsonl.exists(), f"summary={paths.summary.exists()}; results={paths.simulation_jsonl.exists()}"))
    if options.require_status_ok:
        checks.append(_check("status_ok", summary.get("status") == "OK", f"status={summary.get('status')}"))
    records = int(summary.get("simulated_group_records") or 0)
    checks.append(_check("groups", records >= options.min_groups and len(rows) >= options.min_groups, f"summary={records}; jsonl={len(rows)}; minimum={options.min_groups}"))
    checks.append(_check("record_count_match", records == len(rows), f"summary={records}; jsonl={len(rows)}"))
    checks.append(_check("matching_feedback_signals", int(summary.get("matching_feedback_signal_records") or 0) >= options.min_matching_feedback_signals, f"matching={summary.get('matching_feedback_signal_records')}; minimum={options.min_matching_feedback_signals}"))
    checks.append(_check("feedback_signals_used", signals_used_scan >= options.min_feedback_signals_used and int(summary.get("feedback_signals_used") or 0) >= options.min_feedback_signals_used, f"signals_used summary={summary.get('feedback_signals_used')}; scan={signals_used_scan}; minimum={options.min_feedback_signals_used}"))
    checks.append(_check("groups_adjusted", adjusted_scan >= options.min_groups_adjusted, f"groups_adjusted={adjusted_scan}; minimum={options.min_groups_adjusted}"))
    checks.append(_check("rank_changed", rank_changed_scan >= options.min_rank_changed_records, f"rank_changed={rank_changed_scan}; minimum={options.min_rank_changed_records}"))
    checks.append(_check("unsafe_results", unsafe_scan <= options.max_unsafe_results and int(summary.get("unsafe_simulated_records") or 0) <= options.max_unsafe_results, f"unsafe summary={summary.get('unsafe_simulated_records')}; scan={unsafe_scan}; max={options.max_unsafe_results}"))
    checks.append(_check("excluded_results", excluded_scan <= options.max_excluded_results and int(summary.get("excluded_simulated_records") or 0) <= options.max_excluded_results, f"excluded summary={summary.get('excluded_simulated_records')}; scan={excluded_scan}; max={options.max_excluded_results}"))
    checks.append(_check("source_truth_mutations", source_truth_mutation_scan <= options.max_source_truth_mutations and int(summary.get("source_truth_mutation_records") or 0) <= options.max_source_truth_mutations, f"mutations summary={summary.get('source_truth_mutation_records')}; scan={source_truth_mutation_scan}; max={options.max_source_truth_mutations}"))
    checks.append(_check("context_warning_signals_ignored", int(summary.get("context_warning_signals_used") or 0) <= options.max_context_warning_signals_used, f"context_warning_signals_used={summary.get('context_warning_signals_used')}; max={options.max_context_warning_signals_used}"))
    checks.append(_check("graph_nodes", nodes_len >= max(1, len(rows)), f"graph_nodes={nodes_len}; records={len(rows)}"))
    checks.append(_check("graph_edges", edges_len >= max(0, len(rows)), f"graph_edges={edges_len}; records={len(rows)}"))

    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    result = {"status": status, "summary": report_summary, "checks": checks}
    if options.write_json:
        _write_json(paths.quality, result)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quality gate for TRACE-Net feedback-aware search simulation.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--results-jsonl", type=Path, default=None)
    parser.add_argument("--graph-nodes", type=Path, default=None)
    parser.add_argument("--graph-edges", type=Path, default=None)
    parser.add_argument("--quality", type=Path, default=None)
    parser.add_argument("--min-groups", type=int, default=1)
    parser.add_argument("--min-feedback-signals-used", type=int, default=0)
    parser.add_argument("--min-matching-feedback-signals", type=int, default=0)
    parser.add_argument("--min-groups-adjusted", type=int, default=0)
    parser.add_argument("--min-rank-changed-records", type=int, default=0)
    parser.add_argument("--max-unsafe-results", type=int, default=0)
    parser.add_argument("--max-excluded-results", type=int, default=0)
    parser.add_argument("--max-source-truth-mutations", type=int, default=0)
    parser.add_argument("--max-context-warning-signals-used", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = FeedbackSearchSimulationQualityPaths(
        output_dir=args.output_dir,
        simulation_summary_path=args.summary,
        simulation_jsonl_path=args.results_jsonl,
        graph_nodes_path=args.graph_nodes,
        graph_edges_path=args.graph_edges,
        quality_path=args.quality,
    )
    options = FeedbackSearchSimulationQualityOptions(
        min_groups=args.min_groups,
        min_feedback_signals_used=args.min_feedback_signals_used,
        min_matching_feedback_signals=args.min_matching_feedback_signals,
        min_groups_adjusted=args.min_groups_adjusted,
        min_rank_changed_records=args.min_rank_changed_records,
        max_unsafe_results=args.max_unsafe_results,
        max_excluded_results=args.max_excluded_results,
        max_source_truth_mutations=args.max_source_truth_mutations,
        max_context_warning_signals_used=args.max_context_warning_signals_used,
        write_json=args.write_json,
    )
    result = check_feedback_search_simulation_quality(paths, options)
    print("TRACE-Net feedback-aware search simulation quality gate")
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
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
