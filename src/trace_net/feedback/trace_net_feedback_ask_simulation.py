"""TRACE-Net Feedback-Aware Ask Simulation v1.

This module composes a simulated answer draft from feedback-aware search
simulation results. It is simulation-only: it does not mutate production search
results, Evidence Consensus, trust tiers, source truth, RAG eligibility, or the
normal answer draft.

Inputs:
  local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_results.jsonl
  local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_summary.json
  local_data/organization/trace_net/search/trace_net_search_grouped_results.jsonl
  local_data/organization/trace_net/search/trace_net_search_grouped_summary.json
  local_data/organization/trace_net/answers/trace_net_answer_draft.json

Outputs:
  local_data/organization/trace_net/feedback_ask_simulation/
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
DEFAULT_ANSWERS_DIR = TRACE_NET_DIR / "answers"
DEFAULT_FEEDBACK_SEARCH_SIM_DIR = TRACE_NET_DIR / "feedback_search_simulation"
DEFAULT_OUTPUT_DIR = TRACE_NET_DIR / "feedback_ask_simulation"

VERSION = "trace_net_feedback_ask_simulation_v1"
SAFE_BUCKETS = {"source_evidence", "source_text_evidence", "verified_part_evidence", "derived_context"}
SAFE_RAG_ACTIONS = {"include_as_source_evidence", "include_as_verified_part_evidence", "include_as_derived_context"}


@dataclass(frozen=True)
class FeedbackAskSimulationPaths:
    search_dir: Path = DEFAULT_SEARCH_DIR
    answers_dir: Path = DEFAULT_ANSWERS_DIR
    feedback_search_sim_dir: Path = DEFAULT_FEEDBACK_SEARCH_SIM_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    current_grouped_results_path: Path | None = None
    current_grouped_summary_path: Path | None = None
    current_answer_path: Path | None = None
    current_answer_summary_path: Path | None = None
    feedback_search_simulation_path: Path | None = None
    feedback_search_simulation_results_path: Path | None = None
    feedback_search_simulation_summary_path: Path | None = None
    simulation_path: Path | None = None
    summary_path: Path | None = None
    evidence_path: Path | None = None
    answer_md_path: Path | None = None
    answer_html_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    quality_path: Path | None = None

    @property
    def current_grouped_results(self) -> Path:
        return self.current_grouped_results_path or (self.search_dir / "trace_net_search_grouped_results.jsonl")

    @property
    def current_grouped_summary(self) -> Path:
        return self.current_grouped_summary_path or (self.search_dir / "trace_net_search_grouped_summary.json")

    @property
    def current_answer(self) -> Path:
        return self.current_answer_path or (self.answers_dir / "trace_net_answer_draft.json")

    @property
    def current_answer_summary(self) -> Path:
        return self.current_answer_summary_path or (self.answers_dir / "trace_net_answer_summary.json")

    @property
    def feedback_search_simulation(self) -> Path:
        return self.feedback_search_simulation_path or (self.feedback_search_sim_dir / "trace_net_feedback_search_simulation.json")

    @property
    def feedback_search_simulation_results(self) -> Path:
        return self.feedback_search_simulation_results_path or (self.feedback_search_sim_dir / "trace_net_feedback_search_simulation_results.jsonl")

    @property
    def feedback_search_simulation_summary(self) -> Path:
        return self.feedback_search_simulation_summary_path or (self.feedback_search_sim_dir / "trace_net_feedback_search_simulation_summary.json")

    @property
    def simulation(self) -> Path:
        return self.simulation_path or (self.output_dir / "trace_net_feedback_ask_simulation.json")

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / "trace_net_feedback_ask_simulation_summary.json")

    @property
    def evidence(self) -> Path:
        return self.evidence_path or (self.output_dir / "trace_net_feedback_ask_simulation_evidence.jsonl")

    @property
    def answer_md(self) -> Path:
        return self.answer_md_path or (self.output_dir / "trace_net_feedback_ask_simulation_answer.md")

    @property
    def answer_html(self) -> Path:
        return self.answer_html_path or (self.output_dir / "trace_net_feedback_ask_simulation_answer.html")

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / "trace_net_feedback_ask_simulation_graph_nodes.json")

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / "trace_net_feedback_ask_simulation_graph_edges.json")

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / "trace_net_feedback_ask_simulation_quality.json")


@dataclass(frozen=True)
class FeedbackAskSimulationOptions:
    max_pages: int | None = None
    max_support_per_page: int = 5
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
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, str):
        if not value:
            return []
        if "," in value:
            return [v.strip() for v in value.split(",") if v.strip()]
        return [value]
    return [value]


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


def _first(mapping: Mapping[str, Any], keys: Sequence[str], default: Any = "") -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


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


# ---------------------------------------------------------------------------
# Group and answer helpers
# ---------------------------------------------------------------------------


def _supporting_results(group: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("supporting_results", "supporting_chunks", "supporting_evidence", "results", "chunks"):
        items = group.get(key)
        if isinstance(items, list):
            return [dict(item) for item in items if isinstance(item, Mapping)]
    return []


def _safe_group(group: Mapping[str, Any]) -> bool:
    if group.get("safe_group_after_feedback") is False:
        return False
    if group.get("safe_group") is False:
        return False
    if group.get("unsafe") or group.get("is_unsafe"):
        return False
    buckets = set(_text(v) for v in _as_list(group.get("rag_buckets") or group.get("evidence_buckets") or group.get("buckets")))
    if buckets and not buckets.issubset(SAFE_BUCKETS):
        return False
    for support in _supporting_results(group):
        bucket = _text(support.get("rag_bucket") or support.get("bucket"))
        action = _text(support.get("final_rag_action") or support.get("rag_action"))
        if bucket and bucket not in SAFE_BUCKETS:
            return False
        if action and action not in SAFE_RAG_ACTIONS:
            return False
        if support.get("safe_result") is False or support.get("unsafe") or support.get("excluded"):
            return False
    return True


def _source_url(group: Mapping[str, Any]) -> str:
    for key in ("source_url", "source", "url"):
        if _text(group.get(key)):
            return _text(group.get(key))
    for support in _supporting_results(group):
        for key in ("source_url", "source", "url"):
            if _text(support.get(key)):
                return _text(support.get(key))
    for citation in _as_list(group.get("citations")):
        citation_dict = _as_dict(citation)
        for key in ("source_url", "source", "url"):
            if _text(citation_dict.get(key)):
                return _text(citation_dict.get(key))
    return ""


def _tiff_path(group: Mapping[str, Any]) -> str:
    for key in ("tiff_path", "tiff", "image_path"):
        if _text(group.get(key)):
            return _text(group.get(key))
    for support in _supporting_results(group):
        for key in ("tiff_path", "tiff", "image_path"):
            if _text(support.get(key)):
                return _text(support.get(key))
    for citation in _as_list(group.get("citations")):
        citation_dict = _as_dict(citation)
        for key in ("tiff_path", "tiff", "image_path"):
            if _text(citation_dict.get(key)):
                return _text(citation_dict.get(key))
    return ""


def _ocr_path(group: Mapping[str, Any]) -> str:
    for key in ("ocr_path", "ocr", "ocr_file"):
        if _text(group.get(key)):
            return _text(group.get(key))
    for support in _supporting_results(group):
        for key in ("ocr_path", "ocr", "ocr_file"):
            if _text(support.get(key)):
                return _text(support.get(key))
    for citation in _as_list(group.get("citations")):
        citation_dict = _as_dict(citation)
        for key in ("ocr_path", "ocr", "ocr_file"):
            if _text(citation_dict.get(key)):
                return _text(citation_dict.get(key))
    return ""


def _buckets(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("rag_buckets", "evidence_buckets", "buckets"):
        values.extend(_as_list(group.get(key)))
    for support in _supporting_results(group):
        values.append(support.get("rag_bucket") or support.get("bucket") or support.get("candidate_type"))
    out: list[str] = []
    for value in values:
        if isinstance(value, Mapping):
            out.extend(value.keys())
        else:
            out.append(_text(value))
    return sorted({v for v in out if v})


def _matched_parts(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("matched_parts", "part_numbers", "parts", "matched_part_numbers"):
        values.extend(_as_list(group.get(key)))
    for support in _supporting_results(group):
        for key in ("matched_parts", "part_numbers", "parts", "matched_part_numbers"):
            values.extend(_as_list(support.get(key)))
    return sorted(set(_text(v).upper() for v in values if _text(v)))


def _matched_terms(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("matched_terms", "terms", "query_terms"):
        values.extend(_as_list(group.get(key)))
    for support in _supporting_results(group):
        for key in ("matched_terms", "terms", "query_terms"):
            values.extend(_as_list(support.get(key)))
    return sorted(set(_text(v).lower() for v in values if _text(v)))


def _preview(text: Any, limit: int = 280) -> str:
    value = re.sub(r"\s+", " ", _text(text)).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _group_score(group: Mapping[str, Any]) -> float:
    return _num(_first(group, ("simulated_group_score", "group_score", "score", "best_score", "top_score")))


def _base_score(group: Mapping[str, Any]) -> float:
    return _num(_first(group, ("base_group_score", "group_score", "score", "best_score", "top_score")))


def _page_id(group: Mapping[str, Any]) -> str:
    return _text(_first(group, ("page_id", "page", "page_node_id", "id")), "unknown_page")


def _build_support_summaries(group: Mapping[str, Any], max_support: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, support in enumerate(_supporting_results(group)[:max_support], start=1):
        out.append(
            {
                "rank": idx,
                "candidate_id": _text(_first(support, ("candidate_id", "record_id", "id"))),
                "bucket": _text(_first(support, ("rag_bucket", "bucket", "candidate_type"))),
                "layer": _text(_first(support, ("evidence_layer", "layer"))),
                "score": _num(_first(support, ("score", "result_score"))),
                "trust_tier": _text(_first(support, ("trust_tier", "trust", "selected_trust_tier"))),
                "usable_confidence": _num(_first(support, ("usable_confidence", "confidence", "selected_usable_confidence"))),
                "matched_parts": [_text(p).upper() for p in _as_list(_first(support, ("matched_parts", "part_numbers", "parts"))) if _text(p)],
                "matched_terms": [_text(t).lower() for t in _as_list(_first(support, ("matched_terms", "terms"))) if _text(t)],
                "text_preview": _preview(_first(support, ("text", "chunk_text", "text_preview", "preview"))),
            }
        )
    return out


def _build_simulated_page(group: Mapping[str, Any], rank: int, max_support: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "base_rank": int(group.get("base_rank") or group.get("rank") or rank),
        "rank_delta": int(group.get("rank_delta") or 0),
        "page_id": _page_id(group),
        "base_group_score": round(_base_score(group), 6),
        "feedback_score_delta": round(_num(group.get("feedback_score_delta")), 6),
        "simulated_group_score": round(_group_score(group), 6),
        "evidence_buckets": _buckets(group),
        "matched_parts": _matched_parts(group),
        "matched_terms": _matched_terms(group),
        "supporting_result_count": len(_supporting_results(group)) or int(group.get("supporting_result_count") or group.get("support_count") or 0),
        "citation_count": int(group.get("citation_count") or len(_as_list(group.get("citations"))) or (1 if _source_url(group) and _tiff_path(group) and _ocr_path(group) else 0)),
        "source_url": _source_url(group),
        "tiff_path": _tiff_path(group),
        "ocr_path": _ocr_path(group),
        "safe_group_after_feedback": _safe_group(group),
        "unsafe": not _safe_group(group),
        "feedback_signal_count": int(group.get("feedback_signal_count") or 0),
        "feedback_signal_types": _unique(_as_list(group.get("feedback_signal_types"))),
        "feedback_signals": [_as_dict(s) for s in _as_list(group.get("feedback_signals"))],
        "feedback_review_required": bool(group.get("feedback_review_required")),
        "supporting_evidence": _build_support_summaries(group, max_support=max_support),
    }


def _current_order(current_grouped: Sequence[Mapping[str, Any]]) -> list[str]:
    return [_page_id(group) for group in current_grouped]


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _render_markdown(payload: Mapping[str, Any]) -> str:
    summary = _as_dict(payload.get("summary"))
    pages = [_as_dict(p) for p in _as_list(payload.get("simulated_pages"))]
    lines: list[str] = [
        "# TRACE-Net Feedback-Aware Ask Simulation v1",
        "",
        f"Status: **{summary.get('status')}**",
        "",
        f"Query: `{summary.get('query') or summary.get('query_fingerprint')}`",
        "",
        "## Summary",
        "",
        f"Simulated answer pages: **{summary.get('simulated_answer_page_records')}**",
        f"Simulated evidence records: **{summary.get('simulated_answer_evidence_records')}**",
        f"Feedback signals used: **{summary.get('feedback_signals_used')}**",
        f"Groups adjusted: **{summary.get('groups_adjusted')}**",
        f"Rank changed records: **{summary.get('rank_changed_records')}**",
        f"Unsafe simulated answer groups: **{summary.get('unsafe_simulated_answer_groups')}**",
        f"Source truth mutations: **{summary.get('source_truth_mutation_records')}**",
        "",
        "## Current vs simulated",
        "",
        f"Top page before: `{summary.get('top_page_before') or 'none'}`",
        f"Top page after: `{summary.get('top_page_after') or 'none'}`",
        f"Page order changed: **{summary.get('page_order_changed')}**",
        "",
        "## Simulated page-level answer",
        "",
    ]
    if not pages:
        lines.append("No simulated groups were available.")
    for page in pages:
        lines.extend(
            [
                f"### {page.get('rank')}. Page `{page.get('page_id')}`",
                "",
                f"Simulated score: `{_num(page.get('simulated_group_score')):.6f}`",
                f"Base score: `{_num(page.get('base_group_score')):.6f}`",
                f"Feedback delta: `{_num(page.get('feedback_score_delta')):.6f}`",
                f"Base rank: `{page.get('base_rank')}` Rank delta: `{page.get('rank_delta')}`",
                f"Evidence buckets: `{', '.join(_as_list(page.get('evidence_buckets'))) or 'none'}`",
            ]
        )
        if page.get("matched_parts"):
            lines.append(f"Matched parts: `{', '.join(_as_list(page.get('matched_parts')))}`")
        if page.get("matched_terms"):
            lines.append(f"Matched terms: `{', '.join(_as_list(page.get('matched_terms')))}`")
        if page.get("feedback_signal_types"):
            lines.append(f"Feedback signals: `{', '.join(_as_list(page.get('feedback_signal_types')))}`")
        lines.extend(
            [
                "",
                "Source citation:",
                f"- Source URL: `{page.get('source_url') or 'missing'}`",
                f"- TIFF path: `{page.get('tiff_path') or 'missing'}`",
                f"- OCR path: `{page.get('ocr_path') or 'missing'}`",
                "",
            ]
        )
        supports = [_as_dict(s) for s in _as_list(page.get("supporting_evidence"))]
        if supports:
            lines.append("Supporting evidence:")
            for support in supports:
                label = support.get("bucket") or support.get("layer") or support.get("candidate_id") or f"support {support.get('rank')}"
                lines.append(
                    f"- `{label}` score=`{_num(support.get('score')):.6f}` trust=`{support.get('trust_tier') or 'n/a'}` confidence=`{_num(support.get('usable_confidence')):.6f}`"
                )
                if support.get("matched_parts"):
                    lines.append(f"  - parts: `{', '.join(_as_list(support.get('matched_parts')))}`")
                if support.get("matched_terms"):
                    lines.append(f"  - terms: `{', '.join(_as_list(support.get('matched_terms')))}`")
                if support.get("text_preview"):
                    lines.append(f"  - preview: {support.get('text_preview')}")
        else:
            lines.append("Supporting evidence details were not available.")
        lines.append("")
    lines.extend(
        [
            "## Safety note",
            "",
            "This is a simulation-only answer draft. It uses feedback-adjusted ranking artifacts but does not mutate production search, source truth, Evidence Consensus, RAG eligibility, or trust tiers.",
        ]
    )
    return "\n".join(lines) + "\n"


def _md_to_html(markdown: str) -> str:
    body = html.escape(markdown)
    return (
        "<!doctype html><meta charset='utf-8'><title>TRACE-Net Feedback Ask Simulation</title>"
        "<body style='font-family:Arial,sans-serif;margin:2rem;line-height:1.4'>"
        "<pre style='white-space:pre-wrap'>" + body + "</pre></body>"
    )


def _build_graph(pages: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
        edge = {"source": source, "target": target, "type": edge_type}
        edge.update({k: v for k, v in attrs.items() if v not in (None, "", [])})
        edges.append(edge)

    root = "trace_net:feedback_ask_simulation"
    query_node = f"query:{summary.get('query_fingerprint') or 'unknown'}"
    add_node(root, "feedback_ask_simulation", version=VERSION, status=summary.get("status"))
    add_node(query_node, "query_fingerprint", label=summary.get("query") or summary.get("query_fingerprint"))
    add_edge(root, query_node, "SIMULATES_ASK_FOR")
    for page in pages:
        page_id = _text(page.get("page_id"))
        result_id = f"feedback_ask_page:{page_id}"
        add_node(result_id, "feedback_ask_page_result", page_id=page_id, rank=page.get("rank"), score=page.get("simulated_group_score"))
        add_node(f"page:{page_id}", "page", page_id=page_id)
        add_edge(root, result_id, "HAS_SIMULATED_PAGE_RESULT")
        add_edge(result_id, f"page:{page_id}", "REFERS_TO_PAGE")
        for signal in _as_list(page.get("feedback_signals")):
            sig = _as_dict(signal)
            sid = _text(sig.get("signal_id"))
            add_node(sid, "feedback_policy_signal", signal=sig.get("signal"), delta=sig.get("delta"))
            add_edge(sid, result_id, "ADJUSTS_SIMULATED_PAGE", delta=sig.get("delta"))
        for bucket in _as_list(page.get("evidence_buckets")):
            bid = f"rag_bucket:{bucket}"
            add_node(bid, "rag_bucket", label=bucket)
            add_edge(result_id, bid, "HAS_EVIDENCE_BUCKET")
    return list(nodes.values()), edges


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------


def simulate_feedback_aware_ask(paths: FeedbackAskSimulationPaths, options: FeedbackAskSimulationOptions) -> dict[str, Any]:
    current_groups = _read_jsonl(paths.current_grouped_results)
    current_grouped_summary = _read_json(paths.current_grouped_summary)
    current_answer = _read_json(paths.current_answer)
    current_answer_summary = _read_json(paths.current_answer_summary)
    feedback_sim_summary = _read_json(paths.feedback_search_simulation_summary)
    feedback_sim_groups = _read_jsonl(paths.feedback_search_simulation_results)

    if options.max_pages is not None:
        feedback_sim_groups = feedback_sim_groups[: max(0, options.max_pages)]

    simulated_pages = [_build_simulated_page(group, rank=i + 1, max_support=options.max_support_per_page) for i, group in enumerate(feedback_sim_groups)]
    current_order = _current_order(current_groups)
    simulated_order = [_text(page.get("page_id")) for page in simulated_pages]

    simulated_evidence_records = sum(int(p.get("supporting_result_count") or 0) for p in simulated_pages)
    unsafe_answer_groups = sum(1 for p in simulated_pages if bool(p.get("unsafe")))
    missing_source_url = sum(1 for p in simulated_pages if not _text(p.get("source_url")))
    missing_tiff = sum(1 for p in simulated_pages if not _text(p.get("tiff_path")))
    missing_ocr = sum(1 for p in simulated_pages if not _text(p.get("ocr_path")))
    groups_with_citations = sum(1 for p in simulated_pages if int(p.get("citation_count") or 0) > 0)
    feedback_signals_used = sum(int(p.get("feedback_signal_count") or 0) for p in simulated_pages)
    groups_adjusted = sum(1 for p in simulated_pages if abs(_num(p.get("feedback_score_delta"))) > 0)
    boosted = sum(1 for p in simulated_pages if _num(p.get("feedback_score_delta")) > 0)
    demoted = sum(1 for p in simulated_pages if _num(p.get("feedback_score_delta")) < 0)
    rank_changed = sum(1 for p in simulated_pages if int(p.get("rank_delta") or 0) != 0)
    source_truth_mutations = int(feedback_sim_summary.get("source_truth_mutation_records") or 0)
    context_warning_signals_used = int(feedback_sim_summary.get("context_warning_signals_used") or 0)
    excluded_simulated = int(feedback_sim_summary.get("excluded_simulated_records") or 0)
    pages_with_multiple_buckets = sum(1 for p in simulated_pages if len(_as_list(p.get("evidence_buckets"))) >= 2)

    query = _text(feedback_sim_summary.get("effective_query") or feedback_sim_summary.get("query") or current_answer_summary.get("query") or "unspecified query")
    query_fingerprint = _text(feedback_sim_summary.get("query_fingerprint"))
    top_before = _text(feedback_sim_summary.get("top_page_before") or (current_order[0] if current_order else ""))
    top_after = _text(feedback_sim_summary.get("top_page_after") or (simulated_order[0] if simulated_order else ""))

    page_order_changed = current_order[: len(simulated_order)] != simulated_order
    top_page_changed = top_before != top_after
    answer_changed = bool(page_order_changed or rank_changed or groups_adjusted)
    status = "OK" if simulated_pages and unsafe_answer_groups == 0 and source_truth_mutations == 0 else ("EMPTY" if not simulated_pages else "FAIL")

    summary = {
        "status": status,
        "version": VERSION,
        "created_at": _utc_now(),
        "query": query,
        "query_fingerprint": query_fingerprint,
        "current_answer_status": current_answer_summary.get("status") or _as_dict(current_answer.get("summary")).get("status"),
        "current_answer_page_records": int(current_answer_summary.get("answer_page_records") or current_answer_summary.get("answer_page_count") or len(_as_list(current_answer.get("pages")))),
        "current_answer_evidence_records": int(current_answer_summary.get("answer_evidence_records") or current_answer_summary.get("supporting_result_records") or 0),
        "current_grouped_records": len(current_groups),
        "simulated_answer_page_records": len(simulated_pages),
        "simulated_answer_evidence_records": simulated_evidence_records,
        "feedback_search_sim_group_records": int(feedback_sim_summary.get("simulated_group_records") or len(feedback_sim_groups)),
        "matching_feedback_signals": int(feedback_sim_summary.get("matching_feedback_signal_records") or 0),
        "feedback_signals_used": feedback_signals_used,
        "groups_adjusted": groups_adjusted,
        "groups_boosted": boosted,
        "groups_demoted": demoted,
        "rank_changed_records": rank_changed,
        "top_page_before": top_before,
        "top_page_after": top_after,
        "top_page_changed": top_page_changed,
        "page_order_changed": page_order_changed,
        "answer_changed": answer_changed,
        "unsafe_simulated_answer_groups": unsafe_answer_groups,
        "excluded_simulated_answer_groups": excluded_simulated,
        "source_truth_mutation_records": source_truth_mutations,
        "context_warning_signals_used": context_warning_signals_used,
        "groups_with_citations": groups_with_citations,
        "missing_source_url_groups": missing_source_url,
        "missing_tiff_path_groups": missing_tiff,
        "missing_ocr_path_groups": missing_ocr,
        "pages_with_multiple_buckets": pages_with_multiple_buckets,
        "recommendation": "simulation_only_review_before_enabling_feedback_aware_ask",
        "paths": {
            "current_grouped_results": str(paths.current_grouped_results),
            "current_answer": str(paths.current_answer),
            "feedback_search_simulation_results": str(paths.feedback_search_simulation_results),
            "simulation": str(paths.simulation),
            "answer_md": str(paths.answer_md),
            "answer_html": str(paths.answer_html),
        },
    }

    payload = {"summary": summary, "simulated_pages": simulated_pages, "current_page_order": current_order, "simulated_page_order": simulated_order}
    markdown = _render_markdown(payload)
    graph_nodes, graph_edges = _build_graph(simulated_pages, summary)
    summary["graph_nodes"] = len(graph_nodes)
    summary["graph_edges"] = len(graph_edges)
    payload["summary"] = summary

    _write_json(paths.simulation, payload)
    _write_json(paths.summary, summary)
    _write_jsonl(paths.evidence, [support for page in simulated_pages for support in _as_list(page.get("supporting_evidence"))])
    _write_text(paths.answer_md, markdown)
    _write_text(paths.answer_html, _md_to_html(markdown))
    _write_json(paths.graph_nodes, graph_nodes)
    _write_json(paths.graph_edges, graph_edges)

    if options.open_report:
        try:
            webbrowser.open(paths.answer_html.resolve().as_uri())
        except Exception:
            pass

    return {"summary": summary, "simulated_pages": simulated_pages, "graph_nodes": graph_nodes, "graph_edges": graph_edges}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compose a simulation-only feedback-aware TRACE-Net answer from feedback-adjusted search results.")
    parser.add_argument("--search-dir", type=Path, default=DEFAULT_SEARCH_DIR)
    parser.add_argument("--answers-dir", type=Path, default=DEFAULT_ANSWERS_DIR)
    parser.add_argument("--feedback-search-sim-dir", type=Path, default=DEFAULT_FEEDBACK_SEARCH_SIM_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--current-grouped-results", type=Path, default=None)
    parser.add_argument("--current-grouped-summary", type=Path, default=None)
    parser.add_argument("--current-answer", type=Path, default=None)
    parser.add_argument("--current-answer-summary", type=Path, default=None)
    parser.add_argument("--feedback-search-simulation-results", type=Path, default=None)
    parser.add_argument("--feedback-search-simulation-summary", type=Path, default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--max-support-per-page", type=int, default=5)
    parser.add_argument("--open", action="store_true")
    return parser


def _make_paths(args: argparse.Namespace) -> FeedbackAskSimulationPaths:
    return FeedbackAskSimulationPaths(
        search_dir=args.search_dir,
        answers_dir=args.answers_dir,
        feedback_search_sim_dir=args.feedback_search_sim_dir,
        output_dir=args.output_dir,
        current_grouped_results_path=args.current_grouped_results,
        current_grouped_summary_path=args.current_grouped_summary,
        current_answer_path=args.current_answer,
        current_answer_summary_path=args.current_answer_summary,
        feedback_search_simulation_results_path=args.feedback_search_simulation_results,
        feedback_search_simulation_summary_path=args.feedback_search_simulation_summary,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = _make_paths(args)
    options = FeedbackAskSimulationOptions(max_pages=args.max_pages, max_support_per_page=args.max_support_per_page, open_report=args.open)
    result = simulate_feedback_aware_ask(paths, options)
    summary = result["summary"]
    print("TRACE-Net feedback-aware ask simulation")
    print(f"  Status: {summary.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in [
        "query_fingerprint", "current_answer_page_records", "simulated_answer_page_records", "simulated_answer_evidence_records",
        "feedback_signals_used", "groups_adjusted", "rank_changed_records", "top_page_before", "top_page_after",
        "unsafe_simulated_answer_groups", "source_truth_mutation_records", "context_warning_signals_used", "answer_changed",
    ]:
        print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    print(f"  simulation: {paths.simulation}")
    print(f"  summary: {paths.summary}")
    print(f"  answer_md: {paths.answer_md}")
    print(f"  answer_html: {paths.answer_html}")
    print(f"  evidence_jsonl: {paths.evidence}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    return 0 if summary.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
