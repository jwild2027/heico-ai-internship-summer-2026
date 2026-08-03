"""Quality gate for TRACE-Net Evidence Consensus Router v1.2."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_CONSENSUS_DIR = Path("local_data/organization/trace_net/evidence_consensus")
DEFAULT_RECORDS = DEFAULT_CONSENSUS_DIR / "evidence_consensus_records.jsonl"
DEFAULT_SUMMARY = DEFAULT_CONSENSUS_DIR / "evidence_consensus_summary.json"
DEFAULT_GRAPH_NODES = DEFAULT_CONSENSUS_DIR / "evidence_consensus_graph_nodes.json"
DEFAULT_GRAPH_EDGES = DEFAULT_CONSENSUS_DIR / "evidence_consensus_graph_edges.json"
DEFAULT_QUALITY = DEFAULT_CONSENSUS_DIR / "evidence_consensus_quality.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except Exception:
                continue
            if isinstance(value, Mapping):
                out.append(dict(value))
    return out


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass(frozen=True)
class EvidenceConsensusQualityPaths:
    records_path: Path = DEFAULT_RECORDS
    summary_path: Path = DEFAULT_SUMMARY
    graph_nodes_path: Path = DEFAULT_GRAPH_NODES
    graph_edges_path: Path = DEFAULT_GRAPH_EDGES
    quality_path: Path = DEFAULT_QUALITY


def build_evidence_consensus_quality(
    paths: EvidenceConsensusQualityPaths,
    *,
    min_pages: int = 1,
    min_records: int = 1,
    require_source_trace: bool = False,
    require_rag_safety: bool = True,
    require_graph_overlay: bool = True,
    min_visual_text_records: int | None = None,
    min_table_tile_records: int | None = None,
    min_table_tile_text_refined_records: int | None = None,
    require_confidence_scores: bool = False,
) -> dict[str, Any]:
    summary = _as_dict(_read_json(paths.summary_path, {}))
    records = _read_jsonl(paths.records_path)
    nodes = _read_json(paths.graph_nodes_path, []) if paths.graph_nodes_path.exists() else []
    edges = _read_json(paths.graph_edges_path, []) if paths.graph_edges_path.exists() else []
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []

    record_count = _to_int(summary.get("records"), len(records))
    pages_loaded = _to_int(summary.get("pages_loaded"), len({r.get("page_id") for r in records if r.get("page_id")}))
    source_trace_records = _to_int(summary.get("source_trace_records"))
    visual_text_records = _to_int(summary.get("visual_text_records"))
    table_candidate_records = _to_int(summary.get("table_candidate_records"))
    table_tile_records = _to_int(summary.get("table_tile_records"))
    table_tile_text_refined_records = _to_int(summary.get("table_tile_text_refined_records"))
    part_catalog_records = _to_int(summary.get("part_catalog_records"))
    unsafe_rag = _to_int(summary.get("unsafe_rag_include_records"))
    graph_nodes = _to_int(summary.get("graph_nodes"), len(nodes))
    graph_edges = _to_int(summary.get("graph_edges"), len(edges))
    layer_counts = _as_dict(summary.get("layer_counts"))
    tier_counts = _as_dict(summary.get("trust_tier_counts"))
    rag_counts = _as_dict(summary.get("rag_action_counts"))
    repair_counts = _as_dict(summary.get("repair_action_counts"))
    confidence_records = _to_int(summary.get("confidence_score_records"))
    confidence_tier_counts = _as_dict(summary.get("confidence_tier_counts"))
    confidence_avg_usable = summary.get("confidence_avg_usable")
    confidence_disagreements = _to_int(summary.get("confidence_tier_disagreement_records"))

    # Defensive record-level scan for unsafe include in case summary is stale.
    unsafe_record_scan = 0
    records_missing_confidence = 0
    for row in records:
        rag = str(row.get("rag_action") or "")
        tier = str(row.get("trust_tier") or "").upper()[:1]
        source = _as_dict(row.get("source_trace"))
        source_status = str(source.get("status") or "")
        if rag.startswith("include") and (tier == "D" or source_status in {"not_traceable", "missing_tiff", "missing_source_link"}):
            unsafe_record_scan += 1
        if not isinstance(row.get("confidence_scores"), Mapping):
            records_missing_confidence += 1

    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, message: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "message": message})

    add_check("evidence_consensus_artifacts_present", bool(summary) and bool(records), f"summary={bool(summary)}; records={bool(records)}.")
    add_check("evidence_consensus_status", str(summary.get("status", "")).upper() == "OK", f"status={summary.get('status')!r}.")
    add_check("evidence_consensus_records", record_count >= min_records and len(records) >= min_records, f"records summary={record_count}, jsonl={len(records)}; minimum={min_records}.")
    add_check("evidence_consensus_pages", pages_loaded >= min_pages, f"pages_loaded={pages_loaded}; minimum={min_pages}.")
    add_check("evidence_consensus_layers", bool(layer_counts), f"layer_counts={layer_counts}.")
    add_check("evidence_consensus_trust_tiers", bool(tier_counts), f"trust_tier_counts={tier_counts}.")
    if require_confidence_scores:
        add_check(
            "evidence_consensus_confidence_scores",
            confidence_records >= min_records and records_missing_confidence == 0 and bool(confidence_tier_counts),
            f"confidence_score_records={confidence_records}; missing_confidence_records={records_missing_confidence}; confidence_tier_counts={confidence_tier_counts}.",
        )
    add_check("evidence_consensus_rag_actions", bool(rag_counts), f"rag_action_counts={rag_counts}.")
    add_check("evidence_consensus_repair_actions", bool(repair_counts), f"repair_action_counts={repair_counts}.")
    if require_source_trace:
        add_check("evidence_consensus_source_trace", source_trace_records >= min_pages, f"source_trace_records={source_trace_records}; expected at least {min_pages}.")
    if require_rag_safety:
        add_check("evidence_consensus_no_unsafe_rag", unsafe_rag == 0 and unsafe_record_scan == 0, f"unsafe_rag_include_records summary={unsafe_rag}, record_scan={unsafe_record_scan}; expected 0.")
    if min_visual_text_records is not None:
        add_check("evidence_consensus_visual_text_records", visual_text_records >= min_visual_text_records, f"visual_text_records={visual_text_records}; minimum={min_visual_text_records}.")
    if min_table_tile_records is not None:
        add_check("evidence_consensus_table_tile_records", table_tile_records >= min_table_tile_records, f"table_tile_records={table_tile_records}; minimum={min_table_tile_records}.")
    if min_table_tile_text_refined_records is not None:
        add_check("evidence_consensus_table_tile_text_refined_records", table_tile_text_refined_records >= min_table_tile_text_refined_records, f"table_tile_text_refined_records={table_tile_text_refined_records}; minimum={min_table_tile_text_refined_records}.")
    if require_graph_overlay:
        add_check("evidence_consensus_graph_nodes", graph_nodes > 0 and len(nodes) > 0, f"graph_nodes={graph_nodes}; file_nodes={len(nodes)}.")
        add_check("evidence_consensus_graph_edges", graph_edges > 0 and len(edges) > 0, f"graph_edges={graph_edges}; file_edges={len(edges)}.")

    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    out_summary = {
        "evidence_consensus_summary_present": bool(summary),
        "evidence_consensus_records_present": bool(records),
        "evidence_consensus_status": summary.get("status"),
        "evidence_consensus_records": record_count,
        "evidence_consensus_jsonl_records": len(records),
        "evidence_consensus_pages_loaded": pages_loaded,
        "evidence_consensus_source_trace_records": source_trace_records,
        "evidence_consensus_visual_text_records": visual_text_records,
        "evidence_consensus_table_candidate_records": table_candidate_records,
        "evidence_consensus_table_tile_records": table_tile_records,
        "evidence_consensus_table_tile_text_refined_records": table_tile_text_refined_records,
        "evidence_consensus_part_catalog_records": part_catalog_records,
        "evidence_consensus_layer_counts": layer_counts,
        "evidence_consensus_trust_tier_counts": tier_counts,
        "evidence_consensus_confidence_score_records": confidence_records,
        "evidence_consensus_confidence_tier_counts": confidence_tier_counts,
        "evidence_consensus_confidence_avg_usable": confidence_avg_usable,
        "evidence_consensus_confidence_tier_disagreement_records": confidence_disagreements,
        "evidence_consensus_records_missing_confidence": records_missing_confidence,
        "evidence_consensus_rag_action_counts": rag_counts,
        "evidence_consensus_repair_action_counts": repair_counts,
        "evidence_consensus_unsafe_rag_include_records": unsafe_rag,
        "evidence_consensus_unsafe_rag_record_scan": unsafe_record_scan,
        "evidence_consensus_graph_nodes": graph_nodes,
        "evidence_consensus_graph_edges": graph_edges,
        "evidence_consensus_records_path": str(paths.records_path),
        "evidence_consensus_summary_path": str(paths.summary_path),
    }
    return {"status": status, "summary": out_summary, "checks": checks}


def _print_report(report: Mapping[str, Any]) -> None:
    print("TRACE-Net evidence consensus quality gate")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key, value in _as_dict(report.get("summary")).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in report.get("checks", []):
        mark = "OK" if check.get("ok") else "FAIL"
        print(f"    {mark} {check.get('name')}: {check.get('message')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Evidence Consensus Router quality.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--graph-nodes", type=Path, default=DEFAULT_GRAPH_NODES)
    parser.add_argument("--graph-edges", type=Path, default=DEFAULT_GRAPH_EDGES)
    parser.add_argument("--quality", type=Path, default=DEFAULT_QUALITY)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--require-source-trace", action="store_true")
    parser.add_argument("--no-rag-safety", action="store_true")
    parser.add_argument("--no-graph-overlay", action="store_true")
    parser.add_argument("--min-visual-text-records", type=int, default=None)
    parser.add_argument("--min-table-tile-records", type=int, default=None)
    parser.add_argument("--min-table-tile-text-refined-records", type=int, default=None)
    parser.add_argument("--require-confidence-scores", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = EvidenceConsensusQualityPaths(
        records_path=args.records,
        summary_path=args.summary,
        graph_nodes_path=args.graph_nodes,
        graph_edges_path=args.graph_edges,
        quality_path=args.quality,
    )
    report = build_evidence_consensus_quality(
        paths,
        min_pages=args.min_pages,
        min_records=args.min_records,
        require_source_trace=args.require_source_trace,
        require_rag_safety=not args.no_rag_safety,
        require_graph_overlay=not args.no_graph_overlay,
        min_visual_text_records=args.min_visual_text_records,
        min_table_tile_records=args.min_table_tile_records,
        min_table_tile_text_refined_records=args.min_table_tile_text_refined_records,
        require_confidence_scores=args.require_confidence_scores,
    )
    _print_report(report)
    if args.write_json:
        _write_json(paths.quality_path, report)
        print(f"\nJSON: {paths.quality_path}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
