#!/usr/bin/env python3
"""Quality check for the TRACE-Net graph explorer v2/nomenclature overlay.

This check reads the JSON artifacts written by:

    scripts/build_trace_net_graph_explorer_v2_nomenclature_fix.py

It verifies that the browser graph includes both:

    Part -> HAS_NOMENCLATURE -> Nomenclature
    Page -> HAS_CONTEXT_V2 -> PageContextV2

The check is read-only and does not connect to or mutate PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional, Sequence

DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/graph_explorer")
VERSION = "trace_net_graph_explorer_v1_3_context_v2_nomenclature_quality"


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _edge_type_counts(edges: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(edge.get("type") or "") for edge in edges)


def _node_type_counts(nodes: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(node.get("type") or "") for node in nodes)


def _context_pages_from_edges(edges: list[dict[str, Any]]) -> set[str]:
    pages: set[str] = set()
    for edge in edges:
        if str(edge.get("type") or "") != "HAS_CONTEXT_V2":
            continue
        source = str(edge.get("source") or "")
        if source.startswith("page:"):
            pages.add(source.removeprefix("page:"))
    return pages


def _parse_page_range(value: str) -> tuple[int, int] | None:
    text = (value or "").strip()
    if not text:
        return None
    left, sep, right = text.partition("-")
    if not sep:
        raise ValueError("--require-first-pages must look like 1-50")
    start = int(left.strip())
    end = int(right.strip())
    if start > end:
        start, end = end, start
    return start, end


def _missing_required_pages(
    edges: list[dict[str, Any]],
    required_range: str,
    *,
    fallback_doc: str,
) -> list[str]:
    parsed = _parse_page_range(required_range)
    if parsed is None:
        return []
    start, end = parsed
    context_pages = _context_pages_from_edges(edges)
    missing = []
    for page_num in range(start, end + 1):
        page_id = f"{fallback_doc}_p{page_num:06d}"
        if page_id not in context_pages:
            missing.append(page_id)
    return missing


def check_quality(
    output_dir: Path,
    *,
    min_page_nodes: int,
    min_nomenclature_nodes: int,
    min_has_nomenclature_edges: int,
    min_context_v2_pages: int,
    require_first_pages: str,
    fallback_doc: str,
) -> dict[str, Any]:
    summary_path = output_dir / "trace_net_graph_explorer_summary.json"
    nodes_path = output_dir / "trace_net_graph_explorer_nodes.json"
    edges_path = output_dir / "trace_net_graph_explorer_edges.json"

    summary = _load_json(summary_path)
    nodes = _load_json(nodes_path)
    edges = _load_json(edges_path)

    if not isinstance(nodes, list):
        raise ValueError(f"Expected list in {nodes_path}")
    if not isinstance(edges, list):
        raise ValueError(f"Expected list in {edges_path}")

    node_counts = _node_type_counts(nodes)
    edge_counts = _edge_type_counts(edges)
    context_pages = _context_pages_from_edges(edges)
    missing_pages = _missing_required_pages(edges, require_first_pages, fallback_doc=fallback_doc)

    observed = {
        "status": "OK",
        "version": VERSION,
        "summary_version": summary.get("version"),
        "nodes": len(nodes),
        "edges": len(edges),
        "page_nodes": node_counts.get("page", 0),
        "part_nodes": node_counts.get("part", 0),
        "nomenclature_nodes": node_counts.get("nomenclature", 0),
        "page_context_v2_nodes": node_counts.get("page_context_v2", 0),
        "has_nomenclature_edges": edge_counts.get("HAS_NOMENCLATURE", 0),
        "has_context_v2_edges": edge_counts.get("HAS_CONTEXT_V2", 0),
        "context_v2_page_count": len(context_pages),
        "required_context_v2_page_range": require_first_pages,
        "required_context_v2_missing_pages": missing_pages,
        "required_context_v2_missing_page_count": len(missing_pages),
    }

    failures: list[str] = []
    if observed["page_nodes"] < min_page_nodes:
        failures.append(f"page_nodes below minimum: {observed['page_nodes']} < {min_page_nodes}")
    if observed["nomenclature_nodes"] < min_nomenclature_nodes:
        failures.append(
            f"nomenclature_nodes below minimum: {observed['nomenclature_nodes']} < {min_nomenclature_nodes}"
        )
    if observed["has_nomenclature_edges"] < min_has_nomenclature_edges:
        failures.append(
            f"HAS_NOMENCLATURE edges below minimum: "
            f"{observed['has_nomenclature_edges']} < {min_has_nomenclature_edges}"
        )
    if observed["context_v2_page_count"] < min_context_v2_pages:
        failures.append(
            f"context v2 pages below minimum: {observed['context_v2_page_count']} < {min_context_v2_pages}"
        )
    if missing_pages:
        preview = ", ".join(missing_pages[:12])
        suffix = "" if len(missing_pages) <= 12 else f" ... {len(missing_pages) - 12} more"
        failures.append(f"missing HAS_CONTEXT_V2 edges for required pages: {preview}{suffix}")

    observed["failures"] = failures
    observed["status"] = "PASS" if not failures else "FAIL"
    return observed


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net graph explorer v2/nomenclature overlay quality.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-page-nodes", type=int, default=509)
    parser.add_argument("--min-nomenclature-nodes", type=int, default=1)
    parser.add_argument("--min-has-nomenclature-edges", type=int, default=1)
    parser.add_argument("--min-context-v2-pages", type=int, default=50)
    parser.add_argument("--require-first-pages", default="1-50")
    parser.add_argument("--fallback-doc", default="t_p_120_1176")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    result = check_quality(
        output_dir,
        min_page_nodes=args.min_page_nodes,
        min_nomenclature_nodes=args.min_nomenclature_nodes,
        min_has_nomenclature_edges=args.min_has_nomenclature_edges,
        min_context_v2_pages=args.min_context_v2_pages,
        require_first_pages=args.require_first_pages,
        fallback_doc=args.fallback_doc,
    )

    if args.write_json:
        quality_path = output_dir / "trace_net_graph_explorer_v2_nomenclature_quality.json"
        quality_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        result["quality_path"] = str(quality_path)

    print("TRACE-Net graph explorer v2/nomenclature quality")
    print(f" Status: {result['status']}")
    for key in [
        "page_nodes",
        "part_nodes",
        "nomenclature_nodes",
        "page_context_v2_nodes",
        "has_nomenclature_edges",
        "has_context_v2_edges",
        "context_v2_page_count",
        "required_context_v2_missing_page_count",
    ]:
        print(f" {key}: {result.get(key)}")
    if result.get("quality_path"):
        print(f" quality_path: {result['quality_path']}")

    if result["status"] != "PASS":
        for failure in result["failures"]:
            print(f" - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
