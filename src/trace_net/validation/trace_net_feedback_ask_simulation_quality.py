"""Quality gate for TRACE-Net Feedback-Aware Ask Simulation v1."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_SIM_DIR = Path("local_data/organization/trace_net/feedback_ask_simulation")


@dataclass(frozen=True)
class FeedbackAskSimulationQualityPaths:
    summary_path: Path = DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_summary.json"
    simulation_path: Path = DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation.json"
    evidence_path: Path = DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_evidence.jsonl"
    answer_md_path: Path = DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_answer.md"
    answer_html_path: Path = DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_answer.html"
    graph_nodes_path: Path = DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_graph_nodes.json"
    graph_edges_path: Path = DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_graph_edges.json"
    quality_path: Path = DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_quality.json"


@dataclass(frozen=True)
class FeedbackAskSimulationQualityOptions:
    min_pages: int = 1
    min_evidence_records: int = 1
    min_feedback_signals_used: int = 0
    min_groups_adjusted: int = 0
    min_rank_changed_records: int = 0
    max_unsafe_groups: int = 0
    max_excluded_groups: int = 0
    max_source_truth_mutations: int = 0
    max_context_warning_signals_used: int = 0
    max_missing_source_url_groups: int | None = None
    max_missing_tiff_path_groups: int | None = None
    max_missing_ocr_path_groups: int | None = None
    require_answer_changed: bool = False
    write_json: bool = False


def _read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                continue
            count += 1
    return count


def _num(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "OK" if ok else "FAIL", "detail": detail}


def evaluate_feedback_ask_simulation_quality(paths: FeedbackAskSimulationQualityPaths, options: FeedbackAskSimulationQualityOptions) -> dict[str, Any]:
    summary = _read_json(paths.summary_path)
    summary = dict(summary) if isinstance(summary, Mapping) else {}
    sim = _read_json(paths.simulation_path)
    sim = dict(sim) if isinstance(sim, Mapping) else {}
    pages = sim.get("simulated_pages") if isinstance(sim.get("simulated_pages"), list) else []
    evidence_jsonl_count = _read_jsonl_count(paths.evidence_path)
    graph_nodes = _read_json(paths.graph_nodes_path)
    graph_edges = _read_json(paths.graph_edges_path)
    graph_node_count = len(graph_nodes) if isinstance(graph_nodes, list) else _num(summary.get("graph_nodes"), 0)
    graph_edge_count = len(graph_edges) if isinstance(graph_edges, list) else _num(summary.get("graph_edges"), 0)

    page_records = _num(summary.get("simulated_answer_page_records"), len(pages))
    evidence_records = _num(summary.get("simulated_answer_evidence_records"), evidence_jsonl_count)
    unsafe = _num(summary.get("unsafe_simulated_answer_groups"), 0)
    excluded = _num(summary.get("excluded_simulated_answer_groups"), 0)
    source_mutations = _num(summary.get("source_truth_mutation_records"), 0)
    context_warning = _num(summary.get("context_warning_signals_used"), 0)
    feedback_used = _num(summary.get("feedback_signals_used"), 0)
    groups_adjusted = _num(summary.get("groups_adjusted"), 0)
    rank_changed = _num(summary.get("rank_changed_records"), 0)
    missing_source = _num(summary.get("missing_source_url_groups"), 0)
    missing_tiff = _num(summary.get("missing_tiff_path_groups"), 0)
    missing_ocr = _num(summary.get("missing_ocr_path_groups"), 0)
    answer_changed = bool(summary.get("answer_changed"))

    checks = [
        _check("artifacts_present", paths.summary_path.exists() and paths.simulation_path.exists() and paths.evidence_path.exists(), f"summary={paths.summary_path.exists()}; simulation={paths.simulation_path.exists()}; evidence={paths.evidence_path.exists()}"),
        _check("answer_artifacts_present", paths.answer_md_path.exists() and paths.answer_html_path.exists(), f"answer_md={paths.answer_md_path.exists()}; answer_html={paths.answer_html_path.exists()}"),
        _check("status_ok", summary.get("status") == "OK", f"status={summary.get('status')}"),
        _check("simulated_pages", page_records >= options.min_pages, f"pages={page_records}; minimum={options.min_pages}"),
        _check("evidence_records", evidence_records >= options.min_evidence_records and evidence_jsonl_count == evidence_records, f"summary={evidence_records}; jsonl={evidence_jsonl_count}; minimum={options.min_evidence_records}"),
        _check("feedback_signals_used", feedback_used >= options.min_feedback_signals_used, f"signals_used={feedback_used}; minimum={options.min_feedback_signals_used}"),
        _check("groups_adjusted", groups_adjusted >= options.min_groups_adjusted, f"groups_adjusted={groups_adjusted}; minimum={options.min_groups_adjusted}"),
        _check("rank_changed", rank_changed >= options.min_rank_changed_records, f"rank_changed={rank_changed}; minimum={options.min_rank_changed_records}"),
        _check("unsafe_groups", unsafe <= options.max_unsafe_groups, f"unsafe={unsafe}; max={options.max_unsafe_groups}"),
        _check("excluded_groups", excluded <= options.max_excluded_groups, f"excluded={excluded}; max={options.max_excluded_groups}"),
        _check("source_truth_mutations", source_mutations <= options.max_source_truth_mutations, f"mutations={source_mutations}; max={options.max_source_truth_mutations}"),
        _check("context_warning_signals_ignored", context_warning <= options.max_context_warning_signals_used, f"context_warning_signals_used={context_warning}; max={options.max_context_warning_signals_used}"),
        _check("graph_nodes", graph_node_count >= page_records, f"graph_nodes={graph_node_count}; pages={page_records}"),
        _check("graph_edges", graph_edge_count >= page_records, f"graph_edges={graph_edge_count}; pages={page_records}"),
    ]
    if options.max_missing_source_url_groups is not None:
        checks.append(_check("missing_source_url", missing_source <= options.max_missing_source_url_groups, f"missing_source_url={missing_source}; max={options.max_missing_source_url_groups}"))
    if options.max_missing_tiff_path_groups is not None:
        checks.append(_check("missing_tiff_path", missing_tiff <= options.max_missing_tiff_path_groups, f"missing_tiff={missing_tiff}; max={options.max_missing_tiff_path_groups}"))
    if options.max_missing_ocr_path_groups is not None:
        checks.append(_check("missing_ocr_path", missing_ocr <= options.max_missing_ocr_path_groups, f"missing_ocr={missing_ocr}; max={options.max_missing_ocr_path_groups}"))
    if options.require_answer_changed:
        checks.append(_check("answer_changed", answer_changed, f"answer_changed={answer_changed}"))

    status = "OK" if all(c["status"] == "OK" for c in checks) else "FAIL"
    report = {
        "status": status,
        "summary": {
            "feedback_ask_sim_summary_present": paths.summary_path.exists(),
            "feedback_ask_simulation_present": paths.simulation_path.exists(),
            "feedback_ask_answer_md_present": paths.answer_md_path.exists(),
            "feedback_ask_answer_html_present": paths.answer_html_path.exists(),
            "feedback_ask_status": summary.get("status"),
            "feedback_ask_version": summary.get("version"),
            "feedback_ask_query_fingerprint": summary.get("query_fingerprint"),
            "feedback_ask_current_answer_pages": summary.get("current_answer_page_records"),
            "feedback_ask_simulated_answer_pages": page_records,
            "feedback_ask_simulated_evidence_records": evidence_records,
            "feedback_ask_evidence_jsonl_records": evidence_jsonl_count,
            "feedback_ask_feedback_signals_used": feedback_used,
            "feedback_ask_groups_adjusted": groups_adjusted,
            "feedback_ask_groups_boosted": summary.get("groups_boosted"),
            "feedback_ask_groups_demoted": summary.get("groups_demoted"),
            "feedback_ask_rank_changed_records": rank_changed,
            "feedback_ask_top_page_before": summary.get("top_page_before"),
            "feedback_ask_top_page_after": summary.get("top_page_after"),
            "feedback_ask_answer_changed": answer_changed,
            "feedback_ask_unsafe_groups": unsafe,
            "feedback_ask_excluded_groups": excluded,
            "feedback_ask_source_truth_mutations": source_mutations,
            "feedback_ask_context_warning_signals_used": context_warning,
            "feedback_ask_missing_source_url_groups": missing_source,
            "feedback_ask_missing_tiff_path_groups": missing_tiff,
            "feedback_ask_missing_ocr_path_groups": missing_ocr,
            "feedback_ask_graph_nodes": graph_node_count,
            "feedback_ask_graph_edges": graph_edge_count,
            "feedback_ask_summary_path": str(paths.summary_path),
            "feedback_ask_simulation_path": str(paths.simulation_path),
        },
        "checks": checks,
    }
    if options.write_json:
        paths.quality_path.parent.mkdir(parents=True, exist_ok=True)
        paths.quality_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quality gate for TRACE-Net feedback-aware ask simulation.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_summary.json")
    parser.add_argument("--simulation", type=Path, default=DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation.json")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_evidence.jsonl")
    parser.add_argument("--answer-md", type=Path, default=DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_answer.md")
    parser.add_argument("--answer-html", type=Path, default=DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_answer.html")
    parser.add_argument("--graph-nodes", type=Path, default=DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_graph_nodes.json")
    parser.add_argument("--graph-edges", type=Path, default=DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_graph_edges.json")
    parser.add_argument("--quality", type=Path, default=DEFAULT_SIM_DIR / "trace_net_feedback_ask_simulation_quality.json")
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-evidence-records", type=int, default=1)
    parser.add_argument("--min-feedback-signals-used", type=int, default=0)
    parser.add_argument("--min-groups-adjusted", type=int, default=0)
    parser.add_argument("--min-rank-changed-records", type=int, default=0)
    parser.add_argument("--max-unsafe-groups", type=int, default=0)
    parser.add_argument("--max-excluded-groups", type=int, default=0)
    parser.add_argument("--max-source-truth-mutations", type=int, default=0)
    parser.add_argument("--max-context-warning-signals-used", type=int, default=0)
    parser.add_argument("--max-missing-source-url-groups", type=int, default=None)
    parser.add_argument("--max-missing-tiff-path-groups", type=int, default=None)
    parser.add_argument("--max-missing-ocr-path-groups", type=int, default=None)
    parser.add_argument("--require-answer-changed", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = FeedbackAskSimulationQualityPaths(
        summary_path=args.summary,
        simulation_path=args.simulation,
        evidence_path=args.evidence,
        answer_md_path=args.answer_md,
        answer_html_path=args.answer_html,
        graph_nodes_path=args.graph_nodes,
        graph_edges_path=args.graph_edges,
        quality_path=args.quality,
    )
    options = FeedbackAskSimulationQualityOptions(
        min_pages=args.min_pages,
        min_evidence_records=args.min_evidence_records,
        min_feedback_signals_used=args.min_feedback_signals_used,
        min_groups_adjusted=args.min_groups_adjusted,
        min_rank_changed_records=args.min_rank_changed_records,
        max_unsafe_groups=args.max_unsafe_groups,
        max_excluded_groups=args.max_excluded_groups,
        max_source_truth_mutations=args.max_source_truth_mutations,
        max_context_warning_signals_used=args.max_context_warning_signals_used,
        max_missing_source_url_groups=args.max_missing_source_url_groups,
        max_missing_tiff_path_groups=args.max_missing_tiff_path_groups,
        max_missing_ocr_path_groups=args.max_missing_ocr_path_groups,
        require_answer_changed=args.require_answer_changed,
        write_json=args.write_json,
    )
    report = evaluate_feedback_ask_simulation_quality(paths, options)
    print("TRACE-Net feedback-aware ask simulation quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for key, value in report["summary"].items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in report["checks"]:
        print(f"    {check['status']} {check['name']}: {check['detail']}")
    if args.write_json:
        print(f"\nJSON: {paths.quality_path}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
