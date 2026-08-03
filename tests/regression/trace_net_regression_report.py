"""TRACE-Net fixed regression report aggregator v1.

Reads per-case regression artifacts produced by run_trace_net_fixed_regression.sh
and creates a consolidated safety/retrieval/weighted-ranking report.

This module is intentionally read-only with respect to pipeline artifacts. It
summarizes and copies no production ranking state.
"""

from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "trace_net_regression_report_v1"
DEFAULT_REGRESSION_DIR = Path("local_data/organization/trace_net/regression/fixed_set_v1")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/regression")


@dataclass(frozen=True)
class RegressionPaths:
    regression_dir: Path = DEFAULT_REGRESSION_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR

    @property
    def summary_path(self) -> Path:
        return self.output_dir / "trace_net_regression_report_summary.json"

    @property
    def cases_path(self) -> Path:
        return self.output_dir / "trace_net_regression_report_cases.jsonl"

    @property
    def report_md_path(self) -> Path:
        return self.output_dir / "trace_net_regression_report.md"

    @property
    def report_html_path(self) -> Path:
        return self.output_dir / "trace_net_regression_report.html"

    @property
    def graph_nodes_path(self) -> Path:
        return self.output_dir / "trace_net_regression_report_graph_nodes.json"

    @property
    def graph_edges_path(self) -> Path:
        return self.output_dir / "trace_net_regression_report_graph_edges.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except Exception:
                continue
    except Exception:
        return []
    return rows


def _first_value(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None:
            return value
    return default


def _get_number(data: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    return default


def _get_int(data: Dict[str, Any], *keys: str, default: int = 0) -> int:
    return int(_get_number(data, *keys, default=float(default)))


def _get_text(data: Dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return str(value)
    return default


def _case_dirs(regression_dir: Path) -> List[Path]:
    if not regression_dir.exists():
        return []
    return sorted(p for p in regression_dir.iterdir() if p.is_dir())


def _score_from_row(row: Dict[str, Any]) -> Optional[float]:
    for key in ("weighted_score", "score", "group_score", "final_score"):
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _page_from_row(row: Dict[str, Any]) -> str:
    for key in ("page_id", "page", "page_node_id"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _top_score_tie_count(rows: List[Dict[str, Any]], *, epsilon: float = 1e-6) -> int:
    scores = [s for s in (_score_from_row(row) for row in rows) if s is not None]
    if not scores:
        return 0
    top = max(scores)
    return sum(1 for score in scores if abs(score - top) <= epsilon)


def _score_spread(rows: List[Dict[str, Any]]) -> Optional[float]:
    scores = [s for s in (_score_from_row(row) for row in rows) if s is not None]
    if not scores:
        return None
    return max(scores) - min(scores)


def _analyze_case(case_dir: Path) -> Dict[str, Any]:
    ask = _read_json(case_dir / "ask_summary.json")
    ask_quality = _read_json(case_dir / "ask_quality.json")
    answer = _read_json(case_dir / "answer_summary.json")
    weighted = _read_json(case_dir / "weighted_search_summary.json")
    weighted_quality = _read_json(case_dir / "weighted_search_quality.json")
    search = _read_json(case_dir / "search_summary.json")
    grouped = _read_json(case_dir / "grouped_summary.json")
    weighted_rows = _read_jsonl(case_dir / "weighted_search_results.jsonl")
    grouped_rows = _read_jsonl(case_dir / "grouped_results.jsonl")

    missing_artifacts = []
    for name in (
        "ask_summary.json",
        "answer_summary.json",
        "weighted_search_summary.json",
        "search_summary.json",
        "grouped_summary.json",
    ):
        if not (case_dir / name).exists():
            missing_artifacts.append(name)

    case_id = case_dir.name
    ask_status = _get_text(ask, "status", "ask_status", default="UNKNOWN")
    ask_query = _get_text(ask, "query", "ask_query", "effective_query", default="")
    if not ask_query:
        ask_query = _get_text(weighted, "query", "effective_query", "query_fingerprint", default="")

    answer_pages = _get_int(answer, "answer_page_records", "pages", default=0)
    answer_evidence = _get_int(answer, "answer_evidence_records", "evidence_records", default=0)
    unsafe_answer = _get_int(answer, "unsafe_answer_groups", "unsafe_groups", default=0)
    missing_source_url = _get_int(answer, "missing_source_url_groups", default=0)
    missing_tiff = _get_int(answer, "missing_tiff_path_groups", default=0)
    missing_ocr = _get_int(answer, "missing_ocr_path_groups", default=0)

    top_before = _get_text(weighted, "top_page_before", default="")
    top_after = _get_text(weighted, "top_page_after", default="")
    top_page_changed = bool(top_before and top_after and top_before != top_after)

    weighted_unsafe = _get_int(weighted, "unsafe_weighted_records", "unsafe_results", default=0)
    weighted_excluded = _get_int(weighted, "excluded_weighted_records", "excluded_results", default=0)
    source_truth_mutations = _get_int(weighted, "source_truth_mutation_records", "source_truth_mutations", default=0)
    context_warning_used = _get_int(weighted, "context_warning_signals_used", default=0)
    feedback_used = _get_int(weighted, "feedback_signals_used", default=0)
    groups_adjusted = _get_int(weighted, "groups_with_feedback_adjustment", "groups_adjusted", default=0)
    rank_changed = _get_int(weighted, "rank_changed_records", default=0)
    grouped_input_records = _get_int(weighted, "grouped_input_records", default=_get_int(grouped, "grouped_page_records", default=0))
    weighted_records = _get_int(weighted, "weighted_group_records", "records", default=len(weighted_rows))

    feedback_enabled = bool(weighted.get("feedback_enabled", False))
    weights_policy_version = _get_text(weighted, "weights_policy_version", default="")
    query_fingerprint = _get_text(weighted, "query_fingerprint", default="")

    top_tie_count = _top_score_tie_count(weighted_rows)
    score_spread = _score_spread(weighted_rows)
    tie_heavy = top_tie_count >= 3

    flags: List[str] = []
    if missing_artifacts:
        flags.append("missing_artifacts")
    if ask_status.upper() != "OK":
        flags.append("ask_not_ok")
    if answer_pages <= 0:
        flags.append("no_answer_pages")
    if answer_evidence <= 0:
        flags.append("no_answer_evidence")
    if unsafe_answer > 0:
        flags.append("unsafe_answer_groups")
    if missing_source_url > 0:
        flags.append("missing_source_url")
    if missing_tiff > 0:
        flags.append("missing_tiff_path")
    if missing_ocr > 0:
        flags.append("missing_ocr_path")
    if weighted_unsafe > 0:
        flags.append("unsafe_weighted_records")
    if weighted_excluded > 0:
        flags.append("excluded_weighted_records")
    if source_truth_mutations > 0:
        flags.append("source_truth_mutations")
    if context_warning_used > 0:
        flags.append("context_warning_feedback_used")
    if top_page_changed:
        flags.append("weighted_top_page_changed")
    if tie_heavy:
        flags.append("tie_heavy_top_scores")
    if feedback_used > 0:
        flags.append("feedback_signals_used")
    if rank_changed > 0:
        flags.append("weighted_rank_changes")

    # A case is considered passing if it is safe and has usable answer artifacts.
    failed = any(
        flag in set(flags)
        for flag in (
            "missing_artifacts",
            "ask_not_ok",
            "no_answer_pages",
            "no_answer_evidence",
            "unsafe_answer_groups",
            "missing_source_url",
            "missing_tiff_path",
            "missing_ocr_path",
            "unsafe_weighted_records",
            "excluded_weighted_records",
            "source_truth_mutations",
            "context_warning_feedback_used",
        )
    )

    # Review is broader than failure; it includes ranking changes and ties.
    review_needed = failed or top_page_changed or tie_heavy

    return {
        "case_id": case_id,
        "case_dir": str(case_dir),
        "query": ask_query,
        "query_fingerprint": query_fingerprint,
        "ask_status": ask_status,
        "ask_feedback_mode": _get_text(ask, "feedback_mode", "ask_feedback_mode", default=""),
        "answer_page_records": answer_pages,
        "answer_evidence_records": answer_evidence,
        "unsafe_answer_groups": unsafe_answer,
        "missing_source_url_groups": missing_source_url,
        "missing_tiff_path_groups": missing_tiff,
        "missing_ocr_path_groups": missing_ocr,
        "search_result_records": _get_int(search, "result_records", "search_result_records", default=0),
        "grouped_page_records": _get_int(grouped, "grouped_page_records", "pages_found", default=0),
        "weighted_grouped_input_records": grouped_input_records,
        "weighted_group_records": weighted_records,
        "weights_policy_version": weights_policy_version,
        "top_page_before": top_before,
        "top_page_after": top_after,
        "top_page_changed": top_page_changed,
        "rank_changed_records": rank_changed,
        "unsafe_weighted_records": weighted_unsafe,
        "excluded_weighted_records": weighted_excluded,
        "source_truth_mutation_records": source_truth_mutations,
        "context_warning_signals_used": context_warning_used,
        "feedback_enabled": feedback_enabled,
        "feedback_signals_used": feedback_used,
        "groups_with_feedback_adjustment": groups_adjusted,
        "weighted_top_score_tie_count": top_tie_count,
        "weighted_score_spread": score_spread,
        "tie_heavy_top_scores": tie_heavy,
        "missing_artifacts": missing_artifacts,
        "review_flags": flags,
        "review_needed": review_needed,
        "failed": failed,
        "ask_quality_status": _get_text(ask_quality, "status", "ask_status", default=""),
        "weighted_quality_status": _get_text(weighted_quality, "status", "weighted_search_status", default=""),
    }


def _count_by(cases: Iterable[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for case in cases:
        value = str(case.get(key, ""))
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def _flag_counts(cases: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for case in cases:
        for flag in case.get("review_flags", []):
            counts[flag] = counts.get(flag, 0) + 1
    return dict(sorted(counts.items()))


def _make_summary(cases: List[Dict[str, Any]], paths: RegressionPaths) -> Dict[str, Any]:
    failed_cases = [case for case in cases if case.get("failed")]
    review_cases = [case for case in cases if case.get("review_needed")]
    top_changed = [case for case in cases if case.get("top_page_changed")]
    tie_heavy = [case for case in cases if case.get("tie_heavy_top_scores")]
    feedback_cases = [case for case in cases if _get_int(case, "feedback_signals_used", default=0) > 0]
    rank_changed = [case for case in cases if _get_int(case, "rank_changed_records", default=0) > 0]

    unsafe_answer_total = sum(_get_int(case, "unsafe_answer_groups", default=0) for case in cases)
    unsafe_weighted_total = sum(_get_int(case, "unsafe_weighted_records", default=0) for case in cases)
    excluded_weighted_total = sum(_get_int(case, "excluded_weighted_records", default=0) for case in cases)
    source_truth_mutation_total = sum(_get_int(case, "source_truth_mutation_records", default=0) for case in cases)
    context_warning_used_total = sum(_get_int(case, "context_warning_signals_used", default=0) for case in cases)

    status = "OK" if cases and not failed_cases else "FAIL"
    if not cases:
        status = "FAIL"

    recommendations: List[str] = []
    if not failed_cases:
        recommendations.append("fixed_regression_set_safe_for_current_outputs")
    if top_changed:
        recommendations.append("review_weighted_top_page_changes_before_applying_weighted_ranking")
    if tie_heavy:
        recommendations.append("review_tie_heavy_queries_for_additional_tie_breakers")
    if feedback_cases:
        recommendations.append("validated_feedback_path_exercised_in_regression_set")
    if not feedback_cases:
        recommendations.append("run_feedback_specific_regression_separately_for_feedback_weights")
    recommendations.append("do_not_apply_weighted_ranking_without_regression_review")

    return {
        "status": status,
        "version": VERSION,
        "created_at": _utc_now(),
        "regression_dir": str(paths.regression_dir),
        "output_dir": str(paths.output_dir),
        "case_records": len(cases),
        "passed_cases": len(cases) - len(failed_cases),
        "failed_cases": len(failed_cases),
        "review_needed_cases": len(review_cases),
        "top_page_changed_cases": len(top_changed),
        "tie_heavy_cases": len(tie_heavy),
        "feedback_signal_cases": len(feedback_cases),
        "rank_changed_cases": len(rank_changed),
        "unsafe_answer_group_total": unsafe_answer_total,
        "unsafe_weighted_record_total": unsafe_weighted_total,
        "excluded_weighted_record_total": excluded_weighted_total,
        "source_truth_mutation_total": source_truth_mutation_total,
        "context_warning_signals_used_total": context_warning_used_total,
        "answer_page_total": sum(_get_int(case, "answer_page_records", default=0) for case in cases),
        "answer_evidence_total": sum(_get_int(case, "answer_evidence_records", default=0) for case in cases),
        "ask_status_counts": _count_by(cases, "ask_status"),
        "flag_counts": _flag_counts(cases),
        "cases_with_top_page_changes": [case["case_id"] for case in top_changed],
        "cases_with_tie_heavy_scores": [case["case_id"] for case in tie_heavy],
        "cases_requiring_review": [case["case_id"] for case in review_cases],
        "recommendations": recommendations,
        "summary_path": str(paths.summary_path),
        "cases_path": str(paths.cases_path),
        "report_md_path": str(paths.report_md_path),
        "report_html_path": str(paths.report_html_path),
        "graph_nodes_path": str(paths.graph_nodes_path),
        "graph_edges_path": str(paths.graph_edges_path),
    }


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _make_markdown(summary: Dict[str, Any], cases: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("# TRACE-Net Fixed Regression Report v1")
    lines.append("")
    lines.append(f"Status: **{summary.get('status')}**")
    lines.append(f"Version: `{summary.get('version')}`")
    lines.append("")
    lines.append("## Summary")
    for key in (
        "case_records",
        "passed_cases",
        "failed_cases",
        "review_needed_cases",
        "top_page_changed_cases",
        "tie_heavy_cases",
        "feedback_signal_cases",
        "rank_changed_cases",
        "unsafe_answer_group_total",
        "unsafe_weighted_record_total",
        "excluded_weighted_record_total",
        "source_truth_mutation_total",
        "context_warning_signals_used_total",
        "answer_page_total",
        "answer_evidence_total",
    ):
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.append("")
    lines.append("## Recommendations")
    for rec in summary.get("recommendations", []):
        lines.append(f"- `{rec}`")
    lines.append("")
    lines.append("## Case table")
    lines.append("| Case | Query | Ask | Pages | Evidence | Unsafe answer | Weighted top before | Weighted top after | Flags |")
    lines.append("|---|---|---:|---:|---:|---:|---|---|---|")
    for case in cases:
        flags = ", ".join(f"`{flag}`" for flag in case.get("review_flags", [])) or ""
        lines.append(
            "| {case} | {query} | {ask} | {pages} | {evidence} | {unsafe} | {before} | {after} | {flags} |".format(
                case=case.get("case_id", ""),
                query=str(case.get("query") or case.get("query_fingerprint") or "").replace("|", "\\|"),
                ask=case.get("ask_status", ""),
                pages=case.get("answer_page_records", 0),
                evidence=case.get("answer_evidence_records", 0),
                unsafe=case.get("unsafe_answer_groups", 0),
                before=case.get("top_page_before", ""),
                after=case.get("top_page_after", ""),
                flags=flags,
            )
        )
    lines.append("")
    if summary.get("cases_with_top_page_changes"):
        lines.append("## Weighted top-page changes")
        for case in cases:
            if case.get("top_page_changed"):
                lines.append(
                    f"- `{case['case_id']}`: `{case.get('top_page_before')}` -> `{case.get('top_page_after')}`"
                )
        lines.append("")
    if summary.get("cases_with_tie_heavy_scores"):
        lines.append("## Tie-heavy cases")
        for case in cases:
            if case.get("tie_heavy_top_scores"):
                lines.append(
                    f"- `{case['case_id']}`: top_score_tie_count={case.get('weighted_top_score_tie_count')} score_spread={case.get('weighted_score_spread')}"
                )
        lines.append("")
    lines.append("## Safety")
    lines.append("The report is read-only. It does not change production ranking, source truth, Evidence Consensus, RAG eligibility, or feedback records.")
    lines.append("")
    return "\n".join(lines)


def _make_html(markdown_text: str, summary: Dict[str, Any], cases: List[Dict[str, Any]]) -> str:
    # Keep this dependency-free. Render the main table separately for readability.
    status = html.escape(str(summary.get("status", "")))
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>TRACE-Net Regression Report</title>",
        "<style>body{font-family:Arial,sans-serif;margin:24px;}table{border-collapse:collapse;width:100%;}td,th{border:1px solid #ddd;padding:6px;}th{background:#f3f3f3;}code{background:#f6f8fa;padding:1px 3px;border-radius:3px}.ok{color:green}.fail{color:#b00020}</style>",
        "</head><body>",
        f"<h1>TRACE-Net Fixed Regression Report v1</h1><p>Status: <strong class='{ 'ok' if status == 'OK' else 'fail' }'>{status}</strong></p>",
        "<h2>Summary</h2><table><tbody>",
    ]
    for key in (
        "case_records",
        "passed_cases",
        "failed_cases",
        "review_needed_cases",
        "top_page_changed_cases",
        "tie_heavy_cases",
        "unsafe_answer_group_total",
        "unsafe_weighted_record_total",
        "source_truth_mutation_total",
    ):
        parts.append(f"<tr><th>{html.escape(key)}</th><td>{html.escape(str(summary.get(key)))}</td></tr>")
    parts.extend(["</tbody></table>", "<h2>Cases</h2>"])
    parts.append("<table><thead><tr><th>Case</th><th>Query</th><th>Ask</th><th>Pages</th><th>Evidence</th><th>Top before</th><th>Top after</th><th>Flags</th></tr></thead><tbody>")
    for case in cases:
        flags = ", ".join(case.get("review_flags", []))
        parts.append(
            "<tr><td>{case}</td><td>{query}</td><td>{ask}</td><td>{pages}</td><td>{evidence}</td><td>{before}</td><td>{after}</td><td>{flags}</td></tr>".format(
                case=html.escape(str(case.get("case_id", ""))),
                query=html.escape(str(case.get("query") or case.get("query_fingerprint") or "")),
                ask=html.escape(str(case.get("ask_status", ""))),
                pages=html.escape(str(case.get("answer_page_records", 0))),
                evidence=html.escape(str(case.get("answer_evidence_records", 0))),
                before=html.escape(str(case.get("top_page_before", ""))),
                after=html.escape(str(case.get("top_page_after", ""))),
                flags=html.escape(flags),
            )
        )
    parts.append("</tbody></table>")
    parts.append("<h2>Recommendations</h2><ul>")
    for rec in summary.get("recommendations", []):
        parts.append(f"<li><code>{html.escape(str(rec))}</code></li>")
    parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts)


def _make_graph(summary: Dict[str, Any], cases: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    root_id = "regression_report:fixed_set_v1"
    nodes.append({"id": root_id, "type": "regression_report", "label": "Fixed Regression Report v1", "status": summary.get("status")})

    flag_nodes = set()
    page_nodes = set()
    for case in cases:
        case_id = f"regression_case:{case['case_id']}"
        nodes.append({
            "id": case_id,
            "type": "regression_case",
            "label": case["case_id"],
            "ask_status": case.get("ask_status"),
            "review_needed": case.get("review_needed"),
            "failed": case.get("failed"),
        })
        edges.append({"source": root_id, "target": case_id, "type": "HAS_CASE"})
        for page_key, edge_type in (("top_page_before", "TOP_PAGE_BEFORE"), ("top_page_after", "TOP_PAGE_AFTER")):
            page = case.get(page_key)
            if page:
                page_id = f"page:{page}"
                if page_id not in page_nodes:
                    page_nodes.add(page_id)
                    nodes.append({"id": page_id, "type": "page", "label": str(page)})
                edges.append({"source": case_id, "target": page_id, "type": edge_type})
        for flag in case.get("review_flags", []):
            flag_id = f"regression_flag:{flag}"
            if flag_id not in flag_nodes:
                flag_nodes.add(flag_id)
                nodes.append({"id": flag_id, "type": "regression_flag", "label": flag})
            edges.append({"source": case_id, "target": flag_id, "type": "HAS_REVIEW_FLAG"})
    return nodes, edges


def build_regression_report(paths: RegressionPaths) -> Dict[str, Any]:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    cases = [_analyze_case(case_dir) for case_dir in _case_dirs(paths.regression_dir)]
    summary = _make_summary(cases, paths)
    nodes, edges = _make_graph(summary, cases)
    summary["graph_nodes"] = len(nodes)
    summary["graph_edges"] = len(edges)

    md = _make_markdown(summary, cases)
    html_text = _make_html(md, summary, cases)

    _write_json(paths.summary_path, summary)
    _write_jsonl(paths.cases_path, cases)
    paths.report_md_path.write_text(md, encoding="utf-8")
    paths.report_html_path.write_text(html_text, encoding="utf-8")
    _write_json(paths.graph_nodes_path, nodes)
    _write_json(paths.graph_edges_path, edges)

    return {"summary": summary, "cases": cases, "graph_nodes": nodes, "graph_edges": edges}


def _open_file(path: Path) -> None:
    # Best-effort local opener; safe no-op on CI.
    import os
    import platform
    import subprocess

    try:
        if platform.system() == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net fixed regression report.")
    parser.add_argument("--regression-dir", default=str(DEFAULT_REGRESSION_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--open", action="store_true", help="Open the HTML report after building.")
    args = parser.parse_args(argv)

    paths = RegressionPaths(regression_dir=Path(args.regression_dir), output_dir=Path(args.output_dir))
    result = build_regression_report(paths)
    summary = result["summary"]

    print("TRACE-Net fixed regression report")
    print(f"  Status: {summary.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "case_records",
        "passed_cases",
        "failed_cases",
        "review_needed_cases",
        "top_page_changed_cases",
        "tie_heavy_cases",
        "unsafe_answer_group_total",
        "unsafe_weighted_record_total",
        "source_truth_mutation_total",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("  Recommendations:")
    for rec in summary.get("recommendations", []):
        print(f"    {rec}")
    print("Files written:")
    print(f"  summary: {paths.summary_path}")
    print(f"  cases: {paths.cases_path}")
    print(f"  report_md: {paths.report_md_path}")
    print(f"  report_html: {paths.report_html_path}")
    print(f"  graph_nodes: {paths.graph_nodes_path}")
    print(f"  graph_edges: {paths.graph_edges_path}")

    if args.open:
        _open_file(paths.report_html_path)
    return 0 if summary.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
