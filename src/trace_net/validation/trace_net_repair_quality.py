"""Quality gate for TRACE-Net repair plans."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_REPAIR_DIR = Path("local_data/organization/trace_net/repair")
DEFAULT_SUMMARY = DEFAULT_REPAIR_DIR / "trace_net_repair_plan_summary.json"
DEFAULT_PLAN_JSONL = DEFAULT_REPAIR_DIR / "trace_net_repair_plan.jsonl"
DEFAULT_GRAPH_NODES = DEFAULT_REPAIR_DIR / "trace_net_repair_graph_nodes.json"
DEFAULT_GRAPH_EDGES = DEFAULT_REPAIR_DIR / "trace_net_repair_graph_edges.json"
DEFAULT_QUALITY = DEFAULT_REPAIR_DIR / "trace_net_repair_quality.json"


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
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass(frozen=True)
class TraceNetRepairQualityPaths:
    summary_path: Path = DEFAULT_SUMMARY
    plan_jsonl_path: Path = DEFAULT_PLAN_JSONL
    graph_nodes_path: Path = DEFAULT_GRAPH_NODES
    graph_edges_path: Path = DEFAULT_GRAPH_EDGES
    quality_path: Path = DEFAULT_QUALITY


def build_trace_net_repair_quality(
    paths: TraceNetRepairQualityPaths,
    *,
    min_records: int = 1,
    expect_pages: int | None = None,
    min_repair_needed_records: int | None = None,
    max_unplanned_records: int = 0,
    min_table_route_records: int | None = None,
    require_graph_overlay: bool = True,
) -> dict[str, Any]:
    summary = _as_dict(_read_json(paths.summary_path, {}))
    records = _read_jsonl(paths.plan_jsonl_path)
    nodes = _read_json(paths.graph_nodes_path, []) if paths.graph_nodes_path.exists() else []
    edges = _read_json(paths.graph_edges_path, []) if paths.graph_edges_path.exists() else []
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    route_counts = _as_dict(summary.get("route_counts"))
    records_count = _to_int(summary.get("records"), len(records))
    pages_count = _to_int(summary.get("pages"), len({r.get("page_id") for r in records if r.get("page_id")}))
    repair_needed = _to_int(summary.get("repair_needed_records"))
    table_routes = _to_int(summary.get("table_route_records"))
    human_review = _to_int(summary.get("human_review_records"))
    rag_exclude = _to_int(summary.get("rag_exclude_records"))
    graph_nodes = _to_int(summary.get("graph_nodes"), len(nodes))
    graph_edges = _to_int(summary.get("graph_edges"), len(edges))
    unplanned = 0
    for record in records:
        route = str(record.get("primary_repair_route") or "")
        if not route or route == "unknown":
            unplanned += 1
    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, message: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "message": message})

    add_check("trace_net_repair_summary_present", bool(summary), f"summary present={bool(summary)} at {paths.summary_path}.")
    add_check("trace_net_repair_records", records_count >= min_records and len(records) >= min_records, f"records summary={records_count}, jsonl={len(records)}; minimum={min_records}.")
    if expect_pages is not None:
        add_check("trace_net_repair_page_count", pages_count == expect_pages, f"pages={pages_count}; expected={expect_pages}.")
    add_check("trace_net_repair_routes_present", bool(route_counts), f"route_counts={route_counts}.")
    add_check("trace_net_repair_unplanned", unplanned <= max_unplanned_records, f"unplanned_records={unplanned}; max={max_unplanned_records}.")
    if min_repair_needed_records is not None:
        add_check("trace_net_repair_needed", repair_needed >= min_repair_needed_records, f"repair_needed_records={repair_needed}; minimum={min_repair_needed_records}.")
    if min_table_route_records is not None:
        add_check("trace_net_repair_table_routes", table_routes >= min_table_route_records, f"table_route_records={table_routes}; minimum={min_table_route_records}.")
    if require_graph_overlay:
        add_check("trace_net_repair_graph_nodes", graph_nodes >= records_count, f"graph_nodes={graph_nodes}; records={records_count}.")
        add_check("trace_net_repair_graph_edges", graph_edges >= records_count, f"graph_edges={graph_edges}; records={records_count}.")
    # If all records are excluded from RAG, repair/human-review routes should exist.
    if rag_exclude:
        add_check("trace_net_repair_excluded_have_actions", repair_needed > 0 or human_review > 0, f"rag_exclude_records={rag_exclude}; repair_needed={repair_needed}; human_review={human_review}.")
    status = "OK" if all(check["ok"] for check in checks) else "FAIL"
    quality_summary = {
        "trace_net_repair_summary_present": bool(summary),
        "trace_net_repair_records": records_count,
        "trace_net_repair_records_jsonl": len(records),
        "trace_net_repair_pages": pages_count,
        "trace_net_repair_repair_needed_records": repair_needed,
        "trace_net_repair_rag_include_records": _to_int(summary.get("rag_include_records")),
        "trace_net_repair_rag_exclude_records": rag_exclude,
        "trace_net_repair_table_route_records": table_routes,
        "trace_net_repair_human_review_records": human_review,
        "trace_net_repair_rerun_visual_prompt_records": _to_int(summary.get("rerun_visual_prompt_records")),
        "trace_net_repair_clean_postprocess_records": _to_int(summary.get("clean_postprocess_records")),
        "trace_net_repair_unplanned_records": unplanned,
        "trace_net_repair_graph_nodes": graph_nodes,
        "trace_net_repair_graph_edges": graph_edges,
        "trace_net_repair_route_counts": route_counts,
        "trace_net_repair_priority_counts": _as_dict(summary.get("priority_counts")),
        "trace_net_repair_trust_tier_counts": _as_dict(summary.get("trust_tier_counts")),
        "trace_net_repair_review_flag_counts": _as_dict(summary.get("review_flag_counts")),
    }
    return {"status": status, "summary": quality_summary, "checks": checks}


def print_quality(report: Mapping[str, Any]) -> None:
    print("TRACE-Net repair plan quality gate")
    print(f"  Status: {report.get('status', 'unknown')}")
    print("  Summary:")
    for key, value in _as_dict(report.get("summary")).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in _as_list(report.get("checks")):
        prefix = "OK" if check.get("ok") else "FAIL"
        print(f"    {prefix} {check.get('name')}: {check.get('message')}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net repair plan quality.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--plan-jsonl", type=Path, default=DEFAULT_PLAN_JSONL)
    parser.add_argument("--graph-nodes", type=Path, default=DEFAULT_GRAPH_NODES)
    parser.add_argument("--graph-edges", type=Path, default=DEFAULT_GRAPH_EDGES)
    parser.add_argument("--quality-json", type=Path, default=DEFAULT_QUALITY)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--expect-pages", type=int)
    parser.add_argument("--min-repair-needed-records", type=int)
    parser.add_argument("--max-unplanned-records", type=int, default=0)
    parser.add_argument("--min-table-route-records", type=int)
    parser.add_argument("--no-require-graph-overlay", action="store_true")
    args = parser.parse_args(argv)
    paths = TraceNetRepairQualityPaths(
        summary_path=args.summary,
        plan_jsonl_path=args.plan_jsonl,
        graph_nodes_path=args.graph_nodes,
        graph_edges_path=args.graph_edges,
        quality_path=args.quality_json,
    )
    report = build_trace_net_repair_quality(
        paths,
        min_records=args.min_records,
        expect_pages=args.expect_pages,
        min_repair_needed_records=args.min_repair_needed_records,
        max_unplanned_records=args.max_unplanned_records,
        min_table_route_records=args.min_table_route_records,
        require_graph_overlay=not args.no_require_graph_overlay,
    )
    print_quality(report)
    if args.write_json:
        _write_json(paths.quality_path, report)
        print(f"\nJSON: {paths.quality_path}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
