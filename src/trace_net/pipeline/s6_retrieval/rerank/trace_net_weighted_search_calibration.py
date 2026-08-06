"""TRACE-Net Weighted Search Calibration Report v1.

Reads the latest weighted-search simulation and explains why rankings did or
or did not move after applying official TRACE-Net weights and validated
feedback signals.

This is report-only. It never mutates production ranking, source truth,
Evidence Consensus, RAG eligibility, trust tiers, or feedback records.
"""
from __future__ import annotations

import argparse
import html
import json
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_WEIGHTED_SEARCH_DIR = TRACE_NET_DIR / "weighted_search"
DEFAULT_WEIGHTS_DIR = TRACE_NET_DIR / "weights"
DEFAULT_OUTPUT_DIR = TRACE_NET_DIR / "weighted_search_calibration"

VERSION = "trace_net_weighted_search_calibration_v1"
COMPONENT_KEYS = (
    "base_score",
    "bucket_bonus",
    "evidence_diversity_bonus",
    "exact_match_bonus",
    "confidence_bonus",
    "feedback_adjustment",
)


@dataclass(frozen=True)
class WeightedSearchCalibrationPaths:
    weighted_search_dir: Path = DEFAULT_WEIGHTED_SEARCH_DIR
    weights_dir: Path = DEFAULT_WEIGHTS_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    weighted_summary_path: Path | None = None
    weighted_results_path: Path | None = None
    weights_policy_path: Path | None = None
    calibration_path: Path | None = None
    calibration_jsonl_path: Path | None = None
    summary_path: Path | None = None
    report_md_path: Path | None = None
    report_html_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    quality_path: Path | None = None

    @property
    def weighted_summary(self) -> Path:
        return self.weighted_summary_path or (self.weighted_search_dir / "trace_net_weighted_search_simulation_summary.json")

    @property
    def weighted_results(self) -> Path:
        return self.weighted_results_path or (self.weighted_search_dir / "trace_net_weighted_search_simulation_results.jsonl")

    @property
    def weights_policy(self) -> Path:
        return self.weights_policy_path or (self.weights_dir / "trace_net_weights_policy.json")

    @property
    def calibration(self) -> Path:
        return self.calibration_path or (self.output_dir / "trace_net_weighted_search_calibration.json")

    @property
    def calibration_jsonl(self) -> Path:
        return self.calibration_jsonl_path or (self.output_dir / "trace_net_weighted_search_calibration_records.jsonl")

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / "trace_net_weighted_search_calibration_summary.json")

    @property
    def report_md(self) -> Path:
        return self.report_md_path or (self.output_dir / "trace_net_weighted_search_calibration_report.md")

    @property
    def report_html(self) -> Path:
        return self.report_html_path or (self.output_dir / "trace_net_weighted_search_calibration_report.html")

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / "trace_net_weighted_search_calibration_graph_nodes.json")

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / "trace_net_weighted_search_calibration_graph_edges.json")

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / "trace_net_weighted_search_calibration_quality.json")


@dataclass(frozen=True)
class WeightedSearchCalibrationOptions:
    epsilon: float = 0.000001
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


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


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
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
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


def _unique(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
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


def _count(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        text = _text(value)
        if not text:
            continue
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items()))


def _clip(value: Any, max_chars: int = 800) -> str:
    text = _text(value)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "…"


def _round(value: Any, digits: int = 6) -> float:
    return round(_num(value), digits)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------


def _component_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    comps = _as_dict(row.get("weighted_score_components"))
    return {key: _round(comps.get(key)) for key in COMPONENT_KEYS} | {
        "feedback_signals_used": _as_list(comps.get("feedback_signals_used")),
        "context_warning_signals_used": int(comps.get("context_warning_signals_used") or 0),
        "exact_part_number_match": bool(comps.get("exact_part_number_match")),
        "exact_page_id_match": bool(comps.get("exact_page_id_match")),
        "exact_phrase_match": bool(comps.get("exact_phrase_match")),
        "all_query_terms_matched": bool(comps.get("all_query_terms_matched")),
        "matched_terms": _unique(_as_list(comps.get("matched_terms"))),
        "query_terms": _unique(_as_list(comps.get("query_terms"))),
    }


def _feedback_cap(policy: Mapping[str, Any]) -> tuple[float, float]:
    feedback = _as_dict(policy.get("feedback_ranking"))
    return _num(feedback.get("cap_min"), -15.0), _num(feedback.get("cap_max"), 15.0)


def _feedback_direction(feedback_adjustment: float) -> str:
    if feedback_adjustment > 0.000001:
        return "boost"
    if feedback_adjustment < -0.000001:
        return "demote"
    return "none"


def _dominant_components(comps: Mapping[str, Any]) -> list[str]:
    pairs = [(key, abs(_num(comps.get(key)))) for key in COMPONENT_KEYS]
    pairs = [pair for pair in pairs if pair[1] > 0.000001]
    pairs.sort(key=lambda item: (-item[1], item[0]))
    return [key for key, _value in pairs[:3]]


def _next_lower_row(row: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    rank = int(row.get("weighted_rank") or 0)
    for candidate in rows:
        if int(candidate.get("weighted_rank") or 0) == rank + 1:
            return candidate
    return None


def _previous_higher_row(row: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    rank = int(row.get("weighted_rank") or 0)
    for candidate in rows:
        if int(candidate.get("weighted_rank") or 0) == rank - 1:
            return candidate
    return None


def _row_calibration(row: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], policy: Mapping[str, Any], epsilon: float) -> dict[str, Any]:
    comps = _component_dict(row)
    weighted_score = _num(row.get("weighted_score"))
    original_rank = int(row.get("original_rank") or 0)
    weighted_rank = int(row.get("weighted_rank") or 0)
    feedback_adjustment = _num(comps.get("feedback_adjustment"))
    cap_min, cap_max = _feedback_cap(policy)
    lower = _next_lower_row(row, rows)
    higher = _previous_higher_row(row, rows)
    margin_over_next = None
    additional_demotion_to_fall_below_next = None
    if lower:
        lower_score = _num(lower.get("weighted_score"))
        margin_over_next = round(weighted_score - lower_score, 6)
        additional_demotion_to_fall_below_next = round(max(0.0, weighted_score - lower_score + epsilon), 6)
    additional_boost_to_overtake_previous = None
    margin_below_previous = None
    if higher:
        higher_score = _num(higher.get("weighted_score"))
        margin_below_previous = round(higher_score - weighted_score, 6)
        additional_boost_to_overtake_previous = round(max(0.0, higher_score - weighted_score + epsilon), 6)
    feedback_direction = _feedback_direction(feedback_adjustment)
    feedback_cap_hit = False
    if feedback_direction == "demote" and abs(feedback_adjustment - cap_min) <= 0.000001:
        feedback_cap_hit = True
    if feedback_direction == "boost" and abs(feedback_adjustment - cap_max) <= 0.000001:
        feedback_cap_hit = True
    buckets = _unique(_as_list(row.get("rag_buckets")))
    layers = _unique(_as_list(row.get("evidence_layers")))
    reasons: list[str] = []
    if feedback_direction != "none":
        reasons.append(f"validated_feedback_{feedback_direction}")
    if feedback_cap_hit:
        reasons.append("feedback_cap_hit")
    if "verified_part_evidence" in buckets:
        reasons.append("verified_part_evidence_present")
    if "source_text_evidence" in buckets:
        reasons.append("source_text_evidence_present")
    if "derived_context" in buckets:
        reasons.append("derived_context_present")
    if len(buckets) > 1:
        reasons.append("multiple_evidence_buckets")
    if feedback_direction == "demote" and lower and weighted_rank == original_rank:
        reasons.append("demoted_but_rank_preserved")
    if feedback_direction == "demote" and lower and additional_demotion_to_fall_below_next and additional_demotion_to_fall_below_next > 0:
        reasons.append("additional_demotion_required_for_next_rank")
    if bool(row.get("rank_changed")):
        reasons.append("rank_changed")
    return {
        "page_id": _text(row.get("page_id")),
        "original_rank": original_rank,
        "weighted_rank": weighted_rank,
        "rank_changed": bool(row.get("rank_changed")),
        "weighted_score": _round(weighted_score),
        "original_group_score": _round(_num(row.get("group_score"), _num(row.get("best_score")))),
        "best_score": _round(_num(row.get("best_score"), _num(row.get("group_score")))),
        "rag_buckets": buckets,
        "evidence_layers": layers,
        "supporting_result_count": int(row.get("supporting_result_count") or row.get("supporting_results_count") or len(_as_list(row.get("supporting_results"))) or 0),
        "components": comps,
        "dominant_components": _dominant_components(comps),
        "feedback_direction": feedback_direction,
        "feedback_cap_hit": feedback_cap_hit,
        "feedback_signals_used": len(_as_list(comps.get("feedback_signals_used"))),
        "context_warning_signals_used": int(comps.get("context_warning_signals_used") or 0),
        "margin_over_next": margin_over_next,
        "margin_below_previous": margin_below_previous,
        "additional_demotion_to_fall_below_next": additional_demotion_to_fall_below_next,
        "additional_boost_to_overtake_previous": additional_boost_to_overtake_previous,
        "lower_page_id": _text(lower.get("page_id")) if lower else "",
        "higher_page_id": _text(higher.get("page_id")) if higher else "",
        "evidence_diversity_overrode_feedback": bool(feedback_direction == "demote" and feedback_cap_hit and lower and (additional_demotion_to_fall_below_next or 0) > 0),
        "reasons": reasons,
    }


def _component_stats(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for key in COMPONENT_KEYS:
        values = [_num(_as_dict(rec.get("components")).get(key)) for rec in records]
        stats[key] = {
            "avg": round(sum(values) / len(values), 6) if values else 0.0,
            "min": round(min(values), 6) if values else 0.0,
            "max": round(max(values), 6) if values else 0.0,
            "nonzero_records": sum(1 for value in values if abs(value) > 0.000001),
        }
    return stats


def _recommendations(summary: Mapping[str, Any]) -> list[str]:
    recs: list[str] = []
    if int(summary.get("unsafe_weighted_records") or summary.get("unsafe_records") or 0) == 0:
        recs.append("weighted_simulation_kept_unsafe_results_out")
    if int(summary.get("context_warning_signals_used") or 0) == 0:
        recs.append("context_warning_feedback_ignored_for_ranking")
    if int(summary.get("feedback_signals_used") or 0) > 0 and int(summary.get("rank_changed_records") or 0) == 0:
        recs.append("feedback_adjusted_scores_without_rank_change_review_margins_before_tuning")
    if int(summary.get("feedback_cap_hit_records") or 0) > 0:
        recs.append("feedback_cap_hit_review_repeated_or_expert_feedback_before_increasing_penalty")
    if int(summary.get("evidence_diversity_overrode_feedback_records") or 0) > 0:
        recs.append("evidence_diversity_preserved_rank_despite_negative_feedback")
    if int(summary.get("rank_changed_records") or 0) > 0:
        recs.append("ranking_changed_under_weight_policy_review_before_apply")
    recs.append("do_not_apply_weighted_ranking_until_regression_queries_pass")
    return recs


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _make_graph(summary: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()

    def node(node_id: str, node_type: str, **props: Any) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        nodes.append({"id": node_id, "type": node_type, **props})

    root = "weighted_search_calibration:current"
    node(root, "weighted_search_calibration", version=VERSION, query_fingerprint=summary.get("query_fingerprint"), status=summary.get("status"))
    for rec in records:
        page = _text(rec.get("page_id"))
        rid = f"weighted_calibration:{page}"
        node(rid, "weighted_search_calibration_record", page_id=page, weighted_rank=rec.get("weighted_rank"), original_rank=rec.get("original_rank"), weighted_score=rec.get("weighted_score"), feedback_direction=rec.get("feedback_direction"))
        edges.append({"source": root, "target": rid, "type": "HAS_CALIBRATION_RECORD"})
        if page:
            page_id = f"page:{page}"
            node(page_id, "page", page_id=page)
            edges.append({"source": rid, "target": page_id, "type": "CALIBRATES_PAGE"})
        for bucket in _as_list(rec.get("rag_buckets")):
            bid = f"rag_bucket:{bucket}"
            node(bid, "rag_bucket", name=bucket)
            edges.append({"source": rid, "target": bid, "type": "HAS_RAG_BUCKET"})
        for reason in _as_list(rec.get("reasons")):
            rsid = f"weighted_reason:{reason}"
            node(rsid, "weighted_calibration_reason", name=reason)
            edges.append({"source": rid, "target": rsid, "type": "HAS_REASON"})
    return nodes, edges


def _markdown_table(rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    lines = ["| " + " | ".join(str(x) for x in header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(lines)


def _make_report(summary: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# TRACE-Net Weighted Search Calibration Report")
    lines.append("")
    lines.append(f"Status: **{summary.get('status')}**")
    lines.append(f"Version: `{VERSION}`")
    lines.append("")
    lines.append("## Summary")
    for key in (
        "query_fingerprint",
        "weights_policy_version",
        "records",
        "pages",
        "feedback_signals_used",
        "groups_with_feedback_adjustment",
        "groups_boosted",
        "groups_demoted",
        "rank_changed_records",
        "feedback_cap_hit_records",
        "demotion_shortfall_records",
        "evidence_diversity_overrode_feedback_records",
        "unsafe_records",
        "excluded_records",
        "source_truth_mutation_records",
        "context_warning_signals_used",
        "top_page_before",
        "top_page_after",
    ):
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.append("")
    lines.append("## Component statistics")
    rows = [["Component", "Average", "Min", "Max", "Nonzero records"]]
    for key, stats in _as_dict(summary.get("component_stats")).items():
        rows.append([key, stats.get("avg"), stats.get("min"), stats.get("max"), stats.get("nonzero_records")])
    lines.append(_markdown_table(rows))
    lines.append("")
    lines.append("## Ranking records")
    rows = [["Weighted rank", "Original rank", "Page", "Score", "Feedback", "Buckets", "Margin next", "Demotion needed", "Reasons"]]
    for rec in records[:25]:
        comps = _as_dict(rec.get("components"))
        rows.append([
            rec.get("weighted_rank"),
            rec.get("original_rank"),
            rec.get("page_id"),
            rec.get("weighted_score"),
            comps.get("feedback_adjustment"),
            ", ".join(_as_list(rec.get("rag_buckets"))),
            rec.get("margin_over_next"),
            rec.get("additional_demotion_to_fall_below_next"),
            ", ".join(_as_list(rec.get("reasons"))),
        ])
    lines.append(_markdown_table(rows))
    lines.append("")
    cap_hits = [rec for rec in records if rec.get("feedback_cap_hit")]
    if cap_hits:
        lines.append("## Feedback cap hit records")
        rows = [["Page", "Feedback", "Lower page", "Additional demotion needed", "Buckets"]]
        for rec in cap_hits[:25]:
            comps = _as_dict(rec.get("components"))
            rows.append([rec.get("page_id"), comps.get("feedback_adjustment"), rec.get("lower_page_id"), rec.get("additional_demotion_to_fall_below_next"), ", ".join(_as_list(rec.get("rag_buckets")))])
        lines.append(_markdown_table(rows))
        lines.append("")
    lines.append("## Recommendations")
    for rec in _as_list(summary.get("recommendations")):
        lines.append(f"- `{rec}`")
    lines.append("")
    return "\n".join(lines)


def _html_document(title: str, markdown: str) -> str:
    body = html.escape(markdown)
    body = body.replace("\n", "<br>\n")
    return """<!doctype html>
<html><head><meta charset=\"utf-8\"><title>{title}</title>
<style>body{{font-family:Arial,sans-serif;margin:2rem;line-height:1.45}}code{{background:#f4f4f4;padding:0.1rem 0.25rem}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:0.25rem 0.5rem}}</style>
</head><body><pre>{body}</pre></body></html>
""".format(title=html.escape(title), body=body)


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------


def build_weighted_search_calibration(paths: WeightedSearchCalibrationPaths, options: WeightedSearchCalibrationOptions | None = None) -> dict[str, Any]:
    options = options or WeightedSearchCalibrationOptions()
    weighted_summary = _read_json(paths.weighted_summary)
    weighted_rows = _read_jsonl(paths.weighted_results)
    policy = _read_json(paths.weights_policy)
    ordered_rows = sorted(weighted_rows, key=lambda row: int(row.get("weighted_rank") or 999999))
    records = [_row_calibration(row, ordered_rows, policy, options.epsilon) for row in ordered_rows]
    pages = len(_unique(rec.get("page_id") for rec in records))
    feedback_adjusted = [rec for rec in records if _as_dict(rec.get("components")).get("feedback_adjustment") not in (None, 0, 0.0)]
    groups_boosted = sum(1 for rec in records if rec.get("feedback_direction") == "boost")
    groups_demoted = sum(1 for rec in records if rec.get("feedback_direction") == "demote")
    feedback_cap_hit = sum(1 for rec in records if rec.get("feedback_cap_hit"))
    demotion_shortfall = sum(1 for rec in records if rec.get("feedback_direction") == "demote" and _num(rec.get("additional_demotion_to_fall_below_next")) > 0)
    diversity_overrode = sum(1 for rec in records if rec.get("evidence_diversity_overrode_feedback"))
    context_warning_used = sum(int(_as_dict(rec.get("components")).get("context_warning_signals_used") or 0) for rec in records)
    feedback_signals_used = sum(int(rec.get("feedback_signals_used") or 0) for rec in records)
    unsafe = int(weighted_summary.get("unsafe_weighted_records") or weighted_summary.get("unsafe_records") or 0)
    excluded = int(weighted_summary.get("excluded_weighted_records") or weighted_summary.get("excluded_records") or 0)
    mutations = int(weighted_summary.get("source_truth_mutation_records") or 0)
    rank_changed = sum(1 for rec in records if rec.get("rank_changed"))
    top_page_before = _text(weighted_summary.get("top_page_before"))
    top_page_after = _text(weighted_summary.get("top_page_after"))
    summary = {
        "status": "OK" if records and unsafe == 0 and excluded == 0 and mutations == 0 and context_warning_used == 0 else "FAIL",
        "version": VERSION,
        "created_at": _utc_now(),
        "query_fingerprint": weighted_summary.get("query_fingerprint", ""),
        "weights_policy_version": weighted_summary.get("weights_policy_version") or policy.get("version", ""),
        "weighted_summary_path": str(paths.weighted_summary),
        "weighted_results_path": str(paths.weighted_results),
        "weights_policy_path": str(paths.weights_policy),
        "records": len(records),
        "pages": pages,
        "feedback_enabled": bool(weighted_summary.get("feedback_enabled")),
        "matching_feedback_signal_records": int(weighted_summary.get("matching_feedback_signal_records") or 0),
        "feedback_signals_used": feedback_signals_used,
        "groups_with_feedback_adjustment": len(feedback_adjusted),
        "groups_boosted": groups_boosted,
        "groups_demoted": groups_demoted,
        "rank_changed_records": rank_changed,
        "rank_comparison_records": sum(1 for rec in records if rec.get("original_rank") is not None and rec.get("weighted_rank") is not None),
        "feedback_cap_hit_records": feedback_cap_hit,
        "demotion_shortfall_records": demotion_shortfall,
        "evidence_diversity_overrode_feedback_records": diversity_overrode,
        "unsafe_records": unsafe,
        "excluded_records": excluded,
        "source_truth_mutation_records": mutations,
        "context_warning_signals_used": context_warning_used,
        "top_page_before": top_page_before,
        "top_page_after": top_page_after,
        "top_page_changed": bool(top_page_before and top_page_after and top_page_before != top_page_after),
        "component_stats": _component_stats(records),
        "dominant_component_counts": _count(component for rec in records for component in _as_list(rec.get("dominant_components"))),
        "feedback_direction_counts": _count(rec.get("feedback_direction") for rec in records),
        "reason_counts": _count(reason for rec in records for reason in _as_list(rec.get("reasons"))),
    }
    summary["recommendations"] = _recommendations(summary)
    nodes, edges = _make_graph(summary, records)
    summary["graph_nodes"] = len(nodes)
    summary["graph_edges"] = len(edges)
    report = {
        "status": summary["status"],
        "version": VERSION,
        "summary": summary,
        "records": records,
    }
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(paths.calibration, report)
    _write_jsonl(paths.calibration_jsonl, records)
    _write_json(paths.summary, summary)
    md = _make_report(summary, records)
    _write_text(paths.report_md, md)
    _write_text(paths.report_html, _html_document("TRACE-Net Weighted Search Calibration Report", md))
    _write_json(paths.graph_nodes, nodes)
    _write_json(paths.graph_edges, edges)
    if options.open_report:
        try:
            webbrowser.open(paths.report_html.resolve().as_uri())
        except Exception:
            pass
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net weighted search calibration report.")
    parser.add_argument("--weighted-search-dir", type=Path, default=DEFAULT_WEIGHTED_SEARCH_DIR)
    parser.add_argument("--weights-dir", type=Path, default=DEFAULT_WEIGHTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--weighted-summary", type=Path, default=None)
    parser.add_argument("--weighted-results", type=Path, default=None)
    parser.add_argument("--weights-policy", type=Path, default=None)
    parser.add_argument("--epsilon", type=float, default=0.000001)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    paths = WeightedSearchCalibrationPaths(
        weighted_search_dir=args.weighted_search_dir,
        weights_dir=args.weights_dir,
        output_dir=args.output_dir,
        weighted_summary_path=args.weighted_summary,
        weighted_results_path=args.weighted_results,
        weights_policy_path=args.weights_policy,
    )
    report = build_weighted_search_calibration(paths, WeightedSearchCalibrationOptions(epsilon=args.epsilon, open_report=args.open))
    summary = report.get("summary", {})
    print("TRACE-Net weighted search calibration report")
    print(f"  Status: {report.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "query_fingerprint",
        "weights_policy_version",
        "records",
        "pages",
        "feedback_signals_used",
        "groups_with_feedback_adjustment",
        "groups_boosted",
        "groups_demoted",
        "rank_changed_records",
        "feedback_cap_hit_records",
        "demotion_shortfall_records",
        "evidence_diversity_overrode_feedback_records",
        "unsafe_records",
        "excluded_records",
        "source_truth_mutation_records",
        "context_warning_signals_used",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("  Recommendations:")
    for rec in _as_list(summary.get("recommendations"))[:8]:
        print(f"    {rec}")
    print("Files written:")
    print(f"  calibration: {paths.calibration}")
    print(f"  calibration_jsonl: {paths.calibration_jsonl}")
    print(f"  summary: {paths.summary}")
    print(f"  report_html: {paths.report_html}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
