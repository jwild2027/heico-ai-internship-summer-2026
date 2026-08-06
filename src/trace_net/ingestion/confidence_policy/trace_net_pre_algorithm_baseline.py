"""TRACE-Net pre-algorithm-filter baseline metrics v1.

Captures a read-only baseline of OCR, graph, evidence, candidate, citation,
feedback, and quality metrics before applying a new algorithm filter/ranking mode.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_postgres_graph_audit import connect, database_url_from_args, _write_json

VERSION = "trace_net_pre_algorithm_baseline_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/baseline/pre_algorithm_filter_v1")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _one(cur, sql: str, params: tuple[Any, ...] = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _counter(cur, sql: str) -> dict[str, int]:
    cur.execute(sql)
    return {str(k or ""): int(v or 0) for k, v in cur.fetchall()}


def _scalar(cur, sql: str) -> Any:
    cur.execute(sql)
    row = cur.fetchone()
    return row[0] if row else None


def collect_baseline_metrics(database_url: str) -> dict[str, Any]:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            metrics: dict[str, Any] = {
                "status": "OK",
                "version": VERSION,
                "created_at": _utc_now(),
                "scope": "pre_algorithm_filter",
                "notes": [
                    "Read-only snapshot for comparison before applying future algorithm filters.",
                    "This snapshot does not mutate graph, trust tiers, RAG eligibility, feedback, or source truth.",
                ],
                "source_counts": {
                    "pages": _one(cur, "select count(*) from pages"),
                    "pages_with_source_url": _one(cur, "select count(*) from pages where coalesce(source_url,'') <> ''"),
                    "pages_with_tiff_path": _one(cur, "select count(*) from pages where coalesce(tiff_path,'') <> ''"),
                    "pages_with_ocr_path": _one(cur, "select count(*) from pages where coalesce(ocr_path,'') <> ''"),
                },
                "ocr_counts": {
                    "ocr_records": _one(cur, "select count(*) from ocr_records"),
                    "ocr_text_records": _one(cur, "select count(*) from ocr_records where coalesce(length(text),0) > 0"),
                    "ocr_empty_records": _one(cur, "select count(*) from ocr_records where coalesce(length(text),0) = 0"),
                    "ocr_total_chars": _one(cur, "select coalesce(sum(chars),0) from ocr_records"),
                    "ocr_median_chars": _scalar(cur, "select percentile_disc(0.5) within group (order by chars) from ocr_records"),
                    "ocr_classification_counts": _counter(cur, "select coalesce(classification,'') as k, count(*) from ocr_records group by k order by count(*) desc, k"),
                },
                "graph_counts": {
                    "graph_nodes": _one(cur, "select count(*) from graph_nodes"),
                    "graph_edges": _one(cur, "select count(*) from graph_edges"),
                    "node_type_counts": _counter(cur, "select coalesce(node_type,'') as k, count(*) from graph_nodes group by k order by count(*) desc, k"),
                    "edge_type_counts": _counter(cur, "select coalesce(edge_type,'') as k, count(*) from graph_edges group by k order by count(*) desc, k"),
                    "orphan_edges": _one(cur, """
                        select count(*) from graph_edges e
                        left join graph_nodes s on s.node_id = e.source_id
                        left join graph_nodes t on t.node_id = e.target_id
                        where s.node_id is null or t.node_id is null
                    """),
                },
                "evidence_counts": {
                    "evidence_consensus_records": _one(cur, "select count(*) from evidence_consensus_records"),
                    "evidence_layer_counts": _counter(cur, "select coalesce(evidence_layer,'') as k, count(*) from evidence_consensus_records group by k order by k"),
                    "evidence_trust_tier_counts": _counter(cur, "select coalesce(trust_tier,'') as k, count(*) from evidence_consensus_records group by k order by k"),
                    "evidence_rag_action_counts": _counter(cur, "select coalesce(rag_action,'') as k, count(*) from evidence_consensus_records group by k order by k"),
                    "stage5_decision_records": _one(cur, "select count(*) from stage5_decision_records"),
                    "stage5_selected_trust_counts": _counter(cur, "select coalesce(selected_trust_tier,'') as k, count(*) from stage5_decision_records group by k order by k"),
                    "stage5_selected_rag_action_counts": _counter(cur, "select coalesce(selected_rag_action,'') as k, count(*) from stage5_decision_records group by k order by k"),
                },
                "rag_counts": {
                    "rag_eligibility_records": _one(cur, "select count(*) from rag_eligibility_records"),
                    "rag_eligibility_safe_records": _one(cur, "select count(*) from rag_eligibility_records where safe_for_rag = true"),
                    "rag_eligibility_bucket_counts": _counter(cur, "select coalesce(rag_bucket,'') as k, count(*) from rag_eligibility_records group by k order by k"),
                    "rag_candidate_records": _one(cur, "select count(*) from rag_candidate_chunks"),
                    "rag_candidate_safe_records": _one(cur, "select count(*) from rag_candidate_chunks where safe_for_rag = true"),
                    "rag_candidate_unsafe_records": _one(cur, "select count(*) from rag_candidate_chunks where safe_for_rag = false"),
                    "rag_candidate_bucket_counts": _counter(cur, "select coalesce(rag_bucket,'') as k, count(*) from rag_candidate_chunks group by k order by k"),
                    "rag_candidate_layer_counts": _counter(cur, "select coalesce(evidence_layer,'') as k, count(*) from rag_candidate_chunks group by k order by k"),
                    "rag_candidate_missing_source_url": _one(cur, "select count(*) from rag_candidate_chunks where coalesce(source_url,'') = ''"),
                    "rag_candidate_missing_trust_tier": _one(cur, "select count(*) from rag_candidate_chunks where coalesce(trust_tier,'') = ''"),
                },
                "citation_counts": {
                    "source_citations": _one(cur, "select count(*) from source_citations"),
                    "citations_missing_source_url": _one(cur, "select count(*) from source_citations where coalesce(source_url,'') = ''"),
                    "citations_missing_tiff_path": _one(cur, "select count(*) from source_citations where coalesce(tiff_path,'') = ''"),
                    "citations_missing_ocr_path": _one(cur, "select count(*) from source_citations where coalesce(ocr_path,'') = ''"),
                },
                "feedback_counts": {
                    "feedback_events": _one(cur, "select count(*) from feedback_events"),
                    "feedback_policy_signals": _one(cur, "select count(*) from feedback_policy_signals"),
                    "feedback_rating_counts": _counter(cur, "select coalesce(rating,'') as k, count(*) from feedback_events group by k order by k"),
                    "feedback_context_status_counts": _counter(cur, "select coalesce(context_status,'') as k, count(*) from feedback_events group by k order by k"),
                    "feedback_policy_signal_eligible_records": _one(cur, "select count(*) from feedback_events where policy_signal_eligible = true"),
                },
                "quality_counts": {
                    "quality_runs": _one(cur, "select count(*) from quality_runs"),
                    "quality_status_counts": _counter(cur, "select coalesce(status,'') as k, count(*) from quality_runs group by k order by k"),
                    "load_runs": _one(cur, "select count(*) from trace_net_load_runs"),
                },
            }
    return metrics


def flatten_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {
        "status": metrics.get("status"),
        "version": metrics.get("version"),
        "created_at": metrics.get("created_at"),
        "scope": metrics.get("scope"),
    }
    for section, value in metrics.items():
        if isinstance(value, Mapping):
            for k, v in value.items():
                if isinstance(v, Mapping):
                    for subk, subv in v.items():
                        flat[f"{section}.{k}.{subk}"] = subv
                else:
                    flat[f"{section}.{k}"] = v
    return flat


def build_baseline(database_url: str, *, output_dir: Path) -> dict[str, Any]:
    metrics = collect_baseline_metrics(database_url)
    flat = flatten_metrics(metrics)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "trace_net_pre_algorithm_baseline_metrics.json", metrics)
    _write_json(output_dir / "trace_net_pre_algorithm_baseline_flat_metrics.json", flat)
    _write_json(output_dir / "trace_net_pre_algorithm_baseline_summary.json", _summary_from_metrics(metrics))
    report = _render_markdown(metrics)
    (output_dir / "trace_net_pre_algorithm_baseline_report.md").write_text(report, encoding="utf-8")
    (output_dir / "trace_net_pre_algorithm_baseline_report.html").write_text("<pre>" + report.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>", encoding="utf-8")
    _write_json(output_dir / "trace_net_pre_algorithm_baseline_graph_nodes.json", _graph_nodes(metrics))
    _write_json(output_dir / "trace_net_pre_algorithm_baseline_graph_edges.json", _graph_edges(metrics))
    return metrics


def _summary_from_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    s = metrics.get("source_counts", {})
    o = metrics.get("ocr_counts", {})
    g = metrics.get("graph_counts", {})
    r = metrics.get("rag_counts", {})
    c = metrics.get("citation_counts", {})
    return {
        "status": metrics.get("status"),
        "version": metrics.get("version"),
        "created_at": metrics.get("created_at"),
        "pages": s.get("pages"),
        "ocr_records": o.get("ocr_records"),
        "ocr_text_records": o.get("ocr_text_records"),
        "graph_nodes": g.get("graph_nodes"),
        "graph_edges": g.get("graph_edges"),
        "graph_orphan_edges": g.get("orphan_edges"),
        "rag_candidate_records": r.get("rag_candidate_records"),
        "rag_candidate_unsafe_records": r.get("rag_candidate_unsafe_records"),
        "rag_candidate_missing_source_url": r.get("rag_candidate_missing_source_url"),
        "rag_candidate_missing_trust_tier": r.get("rag_candidate_missing_trust_tier"),
        "source_citations": c.get("source_citations"),
        "citations_missing_source_url": c.get("citations_missing_source_url"),
    }


def _graph_nodes(metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = _summary_from_metrics(metrics)
    nodes = [{"id": "baseline:run", "type": "baseline_run", "label": "TRACE-Net pre-algorithm baseline"}]
    for key, value in summary.items():
        if key in {"status", "version", "created_at"}:
            continue
        nodes.append({"id": f"baseline:metric:{key}", "type": "baseline_metric", "label": key, "value": value})
    return nodes


def _graph_edges(metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"source": "baseline:run", "target": n["id"], "type": "HAS_BASELINE_METRIC"} for n in _graph_nodes(metrics) if n["id"] != "baseline:run"]


def _render_markdown(metrics: Mapping[str, Any]) -> str:
    summary = _summary_from_metrics(metrics)
    lines = [
        "# TRACE-Net Pre-Algorithm Baseline Metrics v1",
        "",
        f"Status: **{metrics.get('status')}**",
        f"Version: `{metrics.get('version')}`",
        "",
        "This is a read-only baseline snapshot before applying a new algorithm filter or ranking mode.",
        "",
        "## Summary",
    ]
    for k, v in summary.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    lines.append("## RAG bucket counts")
    for k, v in (metrics.get("rag_counts", {}).get("rag_candidate_bucket_counts", {}) or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## OCR classification counts")
    for k, v in (metrics.get("ocr_counts", {}).get("ocr_classification_counts", {}) or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Feedback counts")
    fb = metrics.get("feedback_counts", {})
    for k in ["feedback_events", "feedback_policy_signals", "feedback_policy_signal_eligible_records"]:
        lines.append(f"- {k}: {fb.get(k)}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net pre-algorithm-filter baseline metrics.")
    parser.add_argument("--database-url")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)

    database_url = database_url_from_args(args.database_url)
    metrics = build_baseline(database_url, output_dir=Path(args.output_dir))
    summary = _summary_from_metrics(metrics)
    print("TRACE-Net pre-algorithm baseline metrics")
    print(f"  Status: {summary.get('status')}")
    print(f"  Output dir: {Path(args.output_dir)}")
    print("  Summary:")
    for key in ["pages", "ocr_records", "ocr_text_records", "graph_nodes", "graph_edges", "rag_candidate_records", "rag_candidate_unsafe_records", "source_citations"]:
        print(f"    {key}: {summary.get(key)}")
    if args.open:
        print(f"  Review: {Path(args.output_dir) / 'trace_net_pre_algorithm_baseline_report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
