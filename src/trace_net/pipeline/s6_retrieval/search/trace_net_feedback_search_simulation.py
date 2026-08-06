"""TRACE-Net Feedback-Aware Search Simulation v1.

Simulation-only layer that applies validated feedback policy signals to the
latest grouped search results. It does not mutate production search ranking,
source truth, RAG eligibility, Evidence Consensus, or trust tiers.

Inputs:
  local_data/organization/trace_net/search/trace_net_search_grouped_results.jsonl
  local_data/organization/trace_net/search/trace_net_search_grouped_summary.json
  local_data/organization/trace_net/search/trace_net_search_summary.json
  local_data/organization/trace_net/feedback/feedback_policy_signals.jsonl

Outputs:
  local_data/organization/trace_net/feedback_search_simulation/
"""
from __future__ import annotations

import argparse
import html
import json
import re
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_SEARCH_DIR = TRACE_NET_DIR / "search"
DEFAULT_FEEDBACK_DIR = TRACE_NET_DIR / "feedback"
DEFAULT_OUTPUT_DIR = TRACE_NET_DIR / "feedback_search_simulation"

VERSION = "trace_net_feedback_search_simulation_v1"
SAFE_BUCKETS = {"source_evidence", "source_text_evidence", "verified_part_evidence", "derived_context"}
SAFE_RAG_ACTIONS = {"include_as_source_evidence", "include_as_verified_part_evidence", "include_as_derived_context"}
PART_RE = re.compile(r"\b(?:\d{3}-\d{4,6}-[A-Z0-9]{2,4}|\d{2,4}TP\d{4,8}[A-Z0-9.\-]*|[A-Z]{1,4}\d{2,6}[A-Z0-9.\-]{1,})\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+_p\d{6}\b")


@dataclass(frozen=True)
class FeedbackSearchSimulationPaths:
    search_dir: Path = DEFAULT_SEARCH_DIR
    feedback_dir: Path = DEFAULT_FEEDBACK_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    grouped_results_path: Path | None = None
    grouped_summary_path: Path | None = None
    search_summary_path: Path | None = None
    feedback_signals_path: Path | None = None
    simulation_path: Path | None = None
    simulation_jsonl_path: Path | None = None
    summary_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    quality_path: Path | None = None

    @property
    def grouped_results(self) -> Path:
        return self.grouped_results_path or (self.search_dir / "trace_net_search_grouped_results.jsonl")

    @property
    def grouped_summary(self) -> Path:
        return self.grouped_summary_path or (self.search_dir / "trace_net_search_grouped_summary.json")

    @property
    def search_summary(self) -> Path:
        return self.search_summary_path or (self.search_dir / "trace_net_search_summary.json")

    @property
    def feedback_signals(self) -> Path:
        return self.feedback_signals_path or (self.feedback_dir / "feedback_policy_signals.jsonl")

    @property
    def simulation(self) -> Path:
        return self.simulation_path or (self.output_dir / "trace_net_feedback_search_simulation.json")

    @property
    def simulation_jsonl(self) -> Path:
        return self.simulation_jsonl_path or (self.output_dir / "trace_net_feedback_search_simulation_results.jsonl")

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / "trace_net_feedback_search_simulation_summary.json")

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / "trace_net_feedback_search_simulation_review.md")

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / "trace_net_feedback_search_simulation_review.html")

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
class FeedbackSearchSimulationOptions:
    query: str = ""
    part_number: str = ""
    page_id: str = ""
    boost_weight: float = 8.0
    demote_weight: float = 12.0
    review_penalty: float = 4.0
    top_k: int = 20
    open_report: bool = False


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                rows.append(dict(value))
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) + "\n")


def _write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def _count(values: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        text = _text(value)
        if not text:
            continue
        out[text] = out.get(text, 0) + 1
    return dict(sorted(out.items()))


def _unique(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _text(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _query_fingerprint(query: str = "", part_number: str = "", page_id: str = "") -> str:
    if part_number:
        return "part_number:" + part_number.upper().strip()
    if page_id:
        return "page:" + page_id.strip()
    text = (query or "").strip()
    if not text:
        return "query:unknown"
    part_match = PART_RE.search(text.upper())
    if part_match:
        return "part_number:" + part_match.group(0)
    page_match = PAGE_RE.search(text)
    if page_match:
        return "page:" + page_match.group(0)
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return "query:" + "_".join(tokens[:12]) if tokens else "query:unknown"


def _infer_query_fingerprint(search_summary: Mapping[str, Any], options: FeedbackSearchSimulationOptions) -> str:
    # Explicit CLI context wins. This lets users simulate a specific query even
    # when the latest search summary was produced by a different ask run.
    if options.part_number or options.page_id or options.query:
        return _query_fingerprint(query=options.query, part_number=options.part_number, page_id=options.page_id)
    query = _text(search_summary.get("query")) or _text(search_summary.get("effective_query"))
    part_number = _text(search_summary.get("part_number"))
    page_id = _text(search_summary.get("page_id"))
    return _query_fingerprint(query=query, part_number=part_number, page_id=page_id)


def _safe_group(group: Mapping[str, Any]) -> bool:
    if group.get("safe_group") is False:
        return False
    buckets = set(_text(b) for b in _as_list(group.get("rag_buckets")))
    if buckets and not buckets.issubset(SAFE_BUCKETS):
        return False
    supporting = _as_list(group.get("supporting_results"))
    for row in supporting:
        r = _as_dict(row)
        bucket = _text(r.get("rag_bucket"))
        action = _text(r.get("final_rag_action"))
        if bucket and bucket not in SAFE_BUCKETS:
            return False
        if action and action not in SAFE_RAG_ACTIONS:
            return False
        if r.get("safe_result") is False:
            return False
    return True


# ---------------------------------------------------------------------------
# Feedback simulation
# ---------------------------------------------------------------------------


def _signals_for_query(signals: Sequence[Mapping[str, Any]], query_fingerprint: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for signal in signals:
        if _text(signal.get("query_fingerprint")) != query_fingerprint:
            continue
        if signal.get("advisory_only") is False:
            continue
        if signal.get("ranking_mutation") is True:
            continue
        out.append(dict(signal))
    return out


def _signal_delta(signal: Mapping[str, Any], options: FeedbackSearchSimulationOptions) -> float:
    kind = _text(signal.get("signal"))
    strength = max(0.0, min(1.0, _num(signal.get("strength"), 0.0)))
    if kind == "boost_for_query":
        return round(options.boost_weight * strength, 6)
    if kind == "demote_for_query":
        return round(-options.demote_weight * strength, 6)
    if kind == "review_for_query":
        return round(-options.review_penalty * max(strength, 0.25), 6)
    return 0.0


def _simulate_group(group: Mapping[str, Any], signals_by_page: Mapping[str, Sequence[Mapping[str, Any]]], options: FeedbackSearchSimulationOptions) -> dict[str, Any]:
    page_id = _text(group.get("page_id"))
    group_signals = list(signals_by_page.get(page_id, []))
    deltas: list[dict[str, Any]] = []
    total_delta = 0.0
    signal_types: list[str] = []
    for signal in group_signals:
        delta = _signal_delta(signal, options)
        total_delta += delta
        signal_types.append(_text(signal.get("signal")))
        deltas.append(
            {
                "signal_id": _text(signal.get("signal_id")),
                "signal": _text(signal.get("signal")),
                "strength": round(_num(signal.get("strength")), 6),
                "net_score": round(_num(signal.get("net_score")), 6),
                "event_count": int(signal.get("event_count") or 0),
                "reason_counts": signal.get("reason_counts") or {},
                "requires_review": bool(signal.get("requires_review", False)),
                "delta": round(delta, 6),
            }
        )

    base_score = _num(group.get("group_score")) or _num(group.get("best_score"))
    simulated_score = round(base_score + total_delta, 6)
    simulated = dict(group)
    simulated.update(
        {
            "base_rank": int(group.get("rank") or 0),
            "base_group_score": round(base_score, 6),
            "feedback_score_delta": round(total_delta, 6),
            "simulated_group_score": simulated_score,
            "feedback_signal_count": len(group_signals),
            "feedback_signal_types": _unique(signal_types),
            "feedback_signals": deltas,
            "feedback_review_required": any(bool(s.get("requires_review")) for s in group_signals),
            "safe_group_after_feedback": _safe_group(group),
            "source_truth_mutation": False,
            "ranking_mutation": False,
            "simulation_only": True,
        }
    )
    return simulated


def _build_graph(groups: Sequence[Mapping[str, Any]], used_signals: Sequence[Mapping[str, Any]], query_fingerprint: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, node_type: str, **attrs: Any) -> None:
        if not node_id:
            return
        node = nodes.setdefault(node_id, {"id": node_id, "type": node_type})
        node.update({k: v for k, v in attrs.items() if v not in (None, "", [])})

    def add_edge(source: str, target: str, edge_type: str, **attrs: Any) -> None:
        if not source or not target:
            return
        data = {"source": source, "target": target, "type": edge_type}
        data.update({k: v for k, v in attrs.items() if v not in (None, "", [])})
        edges.append(data)

    root = "trace_net:feedback_search_simulation"
    qnode = f"query:{query_fingerprint}"
    add_node(root, "feedback_search_simulation", version=VERSION)
    add_node(qnode, "query_fingerprint", query_fingerprint=query_fingerprint)
    add_edge(root, qnode, "SIMULATES_QUERY")
    for group in groups:
        gid = _text(group.get("group_id")) or f"feedback_sim_group:{_text(group.get('page_id'))}"
        page_id = _text(group.get("page_id"))
        add_node(gid, "feedback_simulated_page_group", page_id=page_id, simulated_score=group.get("simulated_group_score"), rank=group.get("simulated_rank"))
        add_node(page_id, "page")
        add_edge(root, gid, "HAS_SIMULATED_GROUP")
        add_edge(gid, page_id, "GROUPS_PAGE")
        for sig in _as_list(group.get("feedback_signals")):
            signal_id = _text(_as_dict(sig).get("signal_id"))
            add_node(signal_id, "feedback_policy_signal", signal=_as_dict(sig).get("signal"), strength=_as_dict(sig).get("strength"), delta=_as_dict(sig).get("delta"))
            add_edge(signal_id, gid, "ADJUSTS_GROUP", delta=_as_dict(sig).get("delta"))
    for signal in used_signals:
        sid = _text(signal.get("signal_id"))
        add_node(sid, "feedback_policy_signal", signal=signal.get("signal"), strength=signal.get("strength"))
        add_edge(qnode, sid, "HAS_FEEDBACK_SIGNAL")
    return list(nodes.values()), edges


def simulate_feedback_aware_search(paths: FeedbackSearchSimulationPaths, options: FeedbackSearchSimulationOptions | None = None) -> dict[str, Any]:
    options = options or FeedbackSearchSimulationOptions()
    grouped = _read_jsonl(paths.grouped_results)
    grouped_summary = _read_json(paths.grouped_summary)
    search_summary = _read_json(paths.search_summary)
    feedback_signals = _read_jsonl(paths.feedback_signals)

    query_fingerprint = _infer_query_fingerprint(search_summary, options)
    matching_signals = _signals_for_query(feedback_signals, query_fingerprint)
    signals_by_page: dict[str, list[dict[str, Any]]] = {}
    for signal in matching_signals:
        page_id = _text(signal.get("page_id"))
        if not page_id:
            continue
        signals_by_page.setdefault(page_id, []).append(dict(signal))

    simulated_groups = [_simulate_group(group, signals_by_page, options) for group in grouped]
    before_order = [_text(g.get("page_id")) for g in sorted(grouped, key=lambda g: int(g.get("rank") or 999999))]
    simulated_groups.sort(key=lambda g: (-_num(g.get("simulated_group_score")), int(g.get("base_rank") or 999999), _text(g.get("page_id"))))
    top_k = max(1, int(options.top_k or 20))
    simulated_groups = simulated_groups[:top_k]
    for rank, group in enumerate(simulated_groups, start=1):
        group["simulated_rank"] = rank
        group["rank_delta"] = int(group.get("base_rank") or rank) - rank
    after_order = [_text(g.get("page_id")) for g in simulated_groups]

    unsafe = sum(1 for g in simulated_groups if not bool(g.get("safe_group_after_feedback")))
    excluded = sum(1 for g in simulated_groups if int(g.get("excluded_supporting_results") or 0) > 0)
    groups_adjusted = sum(1 for g in simulated_groups if abs(_num(g.get("feedback_score_delta"))) > 0)
    demoted = sum(1 for g in simulated_groups if _num(g.get("feedback_score_delta")) < 0)
    boosted = sum(1 for g in simulated_groups if _num(g.get("feedback_score_delta")) > 0)
    rank_changed = sum(1 for g in simulated_groups if int(g.get("rank_delta") or 0) != 0)
    signals_used = sum(int(g.get("feedback_signal_count") or 0) for g in simulated_groups)
    context_warning_signals_used = sum(1 for s in matching_signals if s.get("context_status") == "needs_review")
    source_truth_mutations = sum(1 for s in matching_signals if s.get("source_truth_mutation") or s.get("ranking_mutation"))

    summary = {
        "status": "OK" if grouped else "FAIL",
        "version": VERSION,
        "created_at": _utc_now(),
        "query": search_summary.get("query", ""),
        "part_number": search_summary.get("part_number", ""),
        "page_id": search_summary.get("page_id", ""),
        "effective_query": search_summary.get("effective_query", ""),
        "query_fingerprint": query_fingerprint,
        "grouped_input_records": len(grouped),
        "simulated_group_records": len(simulated_groups),
        "pages": len(set(after_order)),
        "feedback_policy_signal_records": len(feedback_signals),
        "matching_feedback_signal_records": len(matching_signals),
        "feedback_signals_used": signals_used,
        "groups_with_feedback_adjustment": groups_adjusted,
        "groups_boosted": boosted,
        "groups_demoted": demoted,
        "rank_changed_records": rank_changed,
        "unsafe_simulated_records": unsafe,
        "excluded_simulated_records": excluded,
        "source_truth_mutation_records": source_truth_mutations,
        "context_warning_signals_used": context_warning_signals_used,
        "before_page_order": before_order,
        "simulated_page_order": after_order,
        "top_page_before": before_order[0] if before_order else "",
        "top_page_after": after_order[0] if after_order else "",
        "top_score_before": grouped_summary.get("top_group_score", 0),
        "top_score_after": simulated_groups[0].get("simulated_group_score") if simulated_groups else 0,
        "recommendation": "simulation_only_review_before_applying_feedback_to_ranking",
        "paths": {
            "grouped_results": str(paths.grouped_results),
            "feedback_signals": str(paths.feedback_signals),
            "simulation": str(paths.simulation),
            "simulation_jsonl": str(paths.simulation_jsonl),
            "summary": str(paths.summary),
            "review_html": str(paths.review_html),
        },
    }
    graph_nodes, graph_edges = _build_graph(simulated_groups, matching_signals, query_fingerprint)
    payload = {"summary": summary, "simulated_groups": simulated_groups, "matching_feedback_signals": matching_signals}

    _write_json(paths.simulation, payload)
    _write_jsonl(paths.simulation_jsonl, simulated_groups)
    _write_json(paths.summary, summary)
    _write_json(paths.graph_nodes, graph_nodes)
    _write_json(paths.graph_edges, graph_edges)
    _write_text(paths.review_md, _render_markdown(summary, simulated_groups, matching_signals))
    _write_text(paths.review_html, _render_html(summary, simulated_groups, matching_signals))
    if options.open_report:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return {"summary": summary, "simulated_groups": simulated_groups, "matching_feedback_signals": matching_signals, "graph_nodes": graph_nodes, "graph_edges": graph_edges}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_text(v).replace("\n", "<br>") for v in row) + " |")
    return "\n".join(lines)


def _render_markdown(summary: Mapping[str, Any], groups: Sequence[Mapping[str, Any]], signals: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# TRACE-Net Feedback-Aware Search Simulation v1",
        "",
        f"Status: **{summary.get('status')}**  Version: `{summary.get('version', VERSION)}`",
        "",
        "## Summary",
        "",
        _md_table(
            ["Metric", "Value"],
            [[k, summary.get(k)] for k in [
                "query_fingerprint", "grouped_input_records", "simulated_group_records", "matching_feedback_signal_records",
                "feedback_signals_used", "groups_with_feedback_adjustment", "groups_boosted", "groups_demoted", "rank_changed_records",
                "unsafe_simulated_records", "excluded_simulated_records", "source_truth_mutation_records", "context_warning_signals_used",
                "top_page_before", "top_page_after",
            ]],
        ),
        "",
        "## Matching feedback signals",
        "",
    ]
    if signals:
        rows = []
        for s in signals:
            rows.append([s.get("signal_id"), s.get("signal"), s.get("page_id"), s.get("strength"), s.get("net_score"), s.get("event_count"), json.dumps(s.get("reason_counts", {}), sort_keys=True)])
        lines.append(_md_table(["Signal", "Type", "Page", "Strength", "Net", "Events", "Reasons"], rows))
    else:
        lines.append("No matching feedback signals for this query fingerprint.")
    lines.extend(["", "## Simulated page ranking", ""])
    rows = []
    for g in groups:
        rows.append([
            g.get("simulated_rank"),
            g.get("base_rank"),
            g.get("rank_delta"),
            g.get("page_id"),
            g.get("base_group_score"),
            g.get("feedback_score_delta"),
            g.get("simulated_group_score"),
            ", ".join(_as_list(g.get("rag_buckets"))),
            g.get("feedback_signal_count"),
            ", ".join(_as_list(g.get("feedback_signal_types"))),
        ])
    lines.append(_md_table(["New rank", "Old rank", "Delta", "Page", "Base score", "Feedback delta", "Sim score", "Buckets", "Signals", "Signal types"], rows))
    return "\n".join(lines) + "\n"


def _render_html(summary: Mapping[str, Any], groups: Sequence[Mapping[str, Any]], signals: Sequence[Mapping[str, Any]]) -> str:
    md = _render_markdown(summary, groups, signals)
    body = html.escape(md)
    body = body.replace("\n", "<br>\n")
    return "<!doctype html><meta charset='utf-8'><title>TRACE-Net Feedback Search Simulation</title><body style='font-family:Arial,sans-serif'><pre style='white-space:pre-wrap'>" + html.escape(md) + "</pre></body>"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulate feedback-aware TRACE-Net search ranking without mutating production results.")
    parser.add_argument("--search-dir", type=Path, default=DEFAULT_SEARCH_DIR)
    parser.add_argument("--feedback-dir", type=Path, default=DEFAULT_FEEDBACK_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--grouped-results", type=Path, default=None)
    parser.add_argument("--grouped-summary", type=Path, default=None)
    parser.add_argument("--search-summary", type=Path, default=None)
    parser.add_argument("--feedback-signals", type=Path, default=None)
    parser.add_argument("--query", default="")
    parser.add_argument("--part-number", default="")
    parser.add_argument("--page-id", default="")
    parser.add_argument("--boost-weight", type=float, default=8.0)
    parser.add_argument("--demote-weight", type=float, default=12.0)
    parser.add_argument("--review-penalty", type=float, default=4.0)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--open", action="store_true")
    return parser


def _make_paths(args: argparse.Namespace) -> FeedbackSearchSimulationPaths:
    return FeedbackSearchSimulationPaths(
        search_dir=args.search_dir,
        feedback_dir=args.feedback_dir,
        output_dir=args.output_dir,
        grouped_results_path=args.grouped_results,
        grouped_summary_path=args.grouped_summary,
        search_summary_path=args.search_summary,
        feedback_signals_path=args.feedback_signals,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = _make_paths(args)
    options = FeedbackSearchSimulationOptions(
        query=args.query,
        part_number=args.part_number,
        page_id=args.page_id,
        boost_weight=args.boost_weight,
        demote_weight=args.demote_weight,
        review_penalty=args.review_penalty,
        top_k=args.top_k,
        open_report=args.open,
    )
    result = simulate_feedback_aware_search(paths, options)
    summary = result["summary"]
    print("TRACE-Net feedback-aware search simulation")
    print(f"  Status: {summary.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in [
        "query_fingerprint", "grouped_input_records", "simulated_group_records", "matching_feedback_signal_records",
        "feedback_signals_used", "groups_with_feedback_adjustment", "groups_boosted", "groups_demoted", "rank_changed_records",
        "unsafe_simulated_records", "excluded_simulated_records", "source_truth_mutation_records", "top_page_before", "top_page_after",
    ]:
        print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    print(f"  simulation: {paths.simulation}")
    print(f"  simulation_jsonl: {paths.simulation_jsonl}")
    print(f"  summary: {paths.summary}")
    print(f"  review_html: {paths.review_html}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    return 0 if summary.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
