"""TRACE-Net Graph Overlay PartCandidate Page-Lineage v1.

Step 19 built a dry-run graph overlay from the element graph attachment plan.
That overlay intentionally keeps PartCandidate nodes as cross-page entity nodes,
so they do not always have a single page_id. Before running Leiden/community
analysis, those cross-page nodes need explicit source_page_ids so graph
communities can use them as safe bridges without losing page lineage.

This module is read-only. It does not write to Postgres, Qdrant, source files,
or source-truth records.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_graph_overlay_part_lineage_v1"
ALGORITHM = "trace_net_part_candidate_page_lineage_refiner_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/graph_overlay_part_lineage")

CROSS_PAGE_NODE_TYPES = {"PartCandidate", "TrustAuthority"}
FORBIDDEN_WRITEBACK_MODES = {"write-postgres", "write_postgres", "postgres", "mutate-postgres"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return f"{prefix}::{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "allowed", "pass"}
    return False


def as_props(row: Mapping[str, Any]) -> dict[str, Any]:
    props = row.get("properties")
    return dict(props) if isinstance(props, Mapping) else {}


def node_page_id(node: Mapping[str, Any]) -> str | None:
    value = node.get("page_id") or as_props(node).get("page_id")
    if value is None or str(value).strip() == "":
        return None
    return str(value)


def edge_page_id(edge: Mapping[str, Any]) -> str | None:
    value = edge.get("page_id") or as_props(edge).get("page_id")
    if value is None or str(value).strip() == "":
        return None
    return str(value)


def edge_source(edge: Mapping[str, Any]) -> str:
    return str(edge.get("source_node_id") or edge.get("source") or "")


def edge_target(edge: Mapping[str, Any]) -> str:
    return str(edge.get("target_node_id") or edge.get("target") or "")


def enrich_part_candidate_lineage(
    nodes: list[Mapping[str, Any]],
    edges: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Attach source_page_ids to PartCandidate nodes.

    Page lineage is collected from:
      1. edge.page_id where the PartCandidate participates;
      2. the opposite endpoint's page_id;
      3. any existing node.page_id / properties.page_id.

    The resulting PartCandidate node is marked as a cross_page_entity. It is
    allowed to lack one single page_id, but it must have source_page_ids.
    """

    new_nodes = [copy.deepcopy(dict(n)) for n in nodes]
    new_edges = [copy.deepcopy(dict(e)) for e in edges]
    node_by_id = {str(n.get("node_id") or n.get("id") or ""): n for n in new_nodes}
    part_ids = {node_id for node_id, n in node_by_id.items() if str(n.get("node_type") or n.get("type")) == "PartCandidate"}

    page_lineage: dict[str, set[str]] = defaultdict(set)
    lineage_edge_counts: Counter[str] = Counter()

    for part_id in part_ids:
        page = node_page_id(node_by_id[part_id])
        if page:
            page_lineage[part_id].add(page)

    for edge in new_edges:
        src = edge_source(edge)
        tgt = edge_target(edge)
        participating = []
        if src in part_ids:
            participating.append((src, tgt))
        if tgt in part_ids:
            participating.append((tgt, src))
        if not participating:
            continue

        edge_page = edge_page_id(edge)
        for part_id, other_id in participating:
            if edge_page:
                page_lineage[part_id].add(edge_page)
            other = node_by_id.get(other_id)
            if other:
                other_page = node_page_id(other)
                if other_page:
                    page_lineage[part_id].add(other_page)
            lineage_edge_counts[part_id] += 1

    missing_source_pages = []
    for part_id in sorted(part_ids):
        node = node_by_id[part_id]
        props = as_props(node)
        source_pages = sorted(page_lineage.get(part_id, set()))
        props["node_scope"] = "cross_page_entity"
        props["source_page_ids"] = source_pages
        props["source_page_count"] = len(source_pages)
        props["page_lineage_method"] = "may_refer_to_part_edges_and_neighbor_page_ids"
        props["page_lineage_edge_count"] = int(lineage_edge_counts.get(part_id, 0))
        props.setdefault("can_answer_directly", False)
        props.setdefault("can_prove_claims", False)
        props.setdefault("can_mutate_source_truth", False)
        props.setdefault("requires_source_resolution", True)
        props.setdefault("requires_citation", True)
        props.setdefault("requires_authority_gate", True)
        node["properties"] = props
        node["node_scope"] = "cross_page_entity"
        node["source_page_ids"] = source_pages
        node["source_page_count"] = len(source_pages)
        node["lineage_refined"] = True
        node.setdefault("writeback_mode", "dry_run_overlay")
        node.setdefault("can_answer_directly", False)
        node.setdefault("can_prove_claims", False)
        node.setdefault("can_mutate_source_truth", False)
        if not source_pages:
            missing_source_pages.append(part_id)

    lineage_summary = {
        "part_candidate_node_count": len(part_ids),
        "part_candidate_nodes_with_source_page_ids_count": len(part_ids) - len(missing_source_pages),
        "part_candidate_missing_source_page_ids_count": len(missing_source_pages),
        "part_candidate_source_page_link_count": sum(len(v) for v in page_lineage.values()),
        "part_candidate_max_source_page_count": max((len(v) for v in page_lineage.values()), default=0),
        "part_candidate_lineage_edge_count": sum(lineage_edge_counts.values()),
        "part_candidate_missing_source_page_node_ids": missing_source_pages[:100],
    }
    return new_nodes, new_edges, lineage_summary


def build_summary(
    source_report: Mapping[str, Any],
    nodes: list[Mapping[str, Any]],
    edges: list[Mapping[str, Any]],
    lineage_summary: Mapping[str, Any],
) -> dict[str, Any]:
    source_summary = source_report.get("summary", {}) if isinstance(source_report.get("summary"), Mapping) else {}
    node_type_counts = Counter(str(n.get("node_type") or n.get("type") or "UnknownNode") for n in nodes)
    edge_type_counts = Counter(str(e.get("edge_type") or e.get("type") or "RELATED_TO") for e in edges)
    node_ids = {str(n.get("node_id") or n.get("id") or "") for n in nodes}
    orphan_edges = [e for e in edges if edge_source(e) not in node_ids or edge_target(e) not in node_ids]

    missing_page_id_total = sum(1 for n in nodes if not node_page_id(n))
    page_scoped_missing_page_id_count = sum(
        1
        for n in nodes
        if str(n.get("node_type") or n.get("type")) not in CROSS_PAGE_NODE_TYPES and not node_page_id(n)
    )

    direct_answer_allowed_count = sum(1 for n in nodes if truthy(n.get("can_answer_directly")) or truthy(as_props(n).get("can_answer_directly"))) + sum(
        1 for e in edges if truthy(e.get("can_answer_directly")) or truthy(as_props(e).get("can_answer_directly"))
    )
    claim_proof_allowed_count = sum(1 for n in nodes if truthy(n.get("can_prove_claims")) or truthy(as_props(n).get("can_prove_claims"))) + sum(
        1 for e in edges if truthy(e.get("can_prove_claims")) or truthy(as_props(e).get("can_prove_claims"))
    )
    source_truth_mutation_allowed_count = sum(1 for n in nodes if truthy(n.get("can_mutate_source_truth")) or truthy(as_props(n).get("can_mutate_source_truth"))) + sum(
        1 for e in edges if truthy(e.get("can_mutate_source_truth")) or truthy(as_props(e).get("can_mutate_source_truth"))
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "source_graph_overlay_status": source_report.get("status"),
        "source_graph_overlay_quality_status": source_report.get("quality_status"),
        "source_graph_overlay_writeback_mode": source_summary.get("writeback_mode") or source_report.get("writeback_mode"),
        "writeback_mode": "dry_run_lineage_refinement",
        "postgres_write_attempted": False,
        "postgres_write_attempt_count": 0,
        "page_count": node_type_counts.get("Page", source_summary.get("page_count", 0)),
        "overlay_node_count": len(nodes),
        "overlay_edge_count": len(edges),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "page_node_count": node_type_counts.get("Page", 0),
        "table_cell_node_count": node_type_counts.get("TableCell", 0),
        "visual_node_count": node_type_counts.get("VisualUnderstanding", 0) + node_type_counts.get("VisualRegion", 0),
        "fishnet_node_count": node_type_counts.get("FishnetRetryPlan", 0),
        "citation_edge_count": edge_type_counts.get("HAS_CITATION", 0),
        "has_nomenclature_edges_preserved": int(source_summary.get("has_nomenclature_edges_preserved") or 0),
        "has_context_v2_edges_preserved": int(source_summary.get("has_context_v2_edges_preserved") or 0),
        "confirmed_blank_pages_preserve_source_trace_count": int(source_summary.get("confirmed_blank_pages_preserve_source_trace_count") or 0),
        "orphan_edge_count": len(orphan_edges),
        "missing_page_id_count": missing_page_id_total,
        "page_scoped_missing_page_id_count": page_scoped_missing_page_id_count,
        "direct_answer_allowed_count": direct_answer_allowed_count,
        "claim_proof_allowed_count": claim_proof_allowed_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "retrieval_only_answer_allowed_count": int(source_summary.get("retrieval_only_answer_allowed_count") or 0),
        "answer_capable_without_citation_count": int(source_summary.get("answer_capable_without_citation_count") or 0),
        **dict(lineage_summary),
    }


@dataclass(frozen=True)
class QualityThresholds:
    require_page_count: int | None = None
    min_overlay_nodes: int = 0
    min_overlay_edges: int = 0
    min_part_candidate_nodes: int = 0
    min_part_candidate_nodes_with_source_page_ids: int = 0
    min_nomenclature_edges_preserved: int = 0
    min_context_v2_edges_preserved: int = 0
    min_confirmed_blank_preserve_source_trace: int = 0
    require_source_overlay_quality_pass: bool = False
    require_dry_run_mode: bool = True
    require_page_scoped_missing_page_id_zero: bool = True


def evaluate_quality(report: Mapping[str, Any], thresholds: QualityThresholds) -> dict[str, Any]:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else report
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    if thresholds.require_page_count is not None:
        add("page_count", summary.get("page_count") == thresholds.require_page_count, summary.get("page_count"), thresholds.require_page_count)

    add("min_overlay_nodes", int(summary.get("overlay_node_count") or 0) >= thresholds.min_overlay_nodes, summary.get("overlay_node_count"), f">={thresholds.min_overlay_nodes}")
    add("min_overlay_edges", int(summary.get("overlay_edge_count") or 0) >= thresholds.min_overlay_edges, summary.get("overlay_edge_count"), f">={thresholds.min_overlay_edges}")
    add("min_part_candidate_nodes", int(summary.get("part_candidate_node_count") or 0) >= thresholds.min_part_candidate_nodes, summary.get("part_candidate_node_count"), f">={thresholds.min_part_candidate_nodes}")
    add(
        "min_part_candidate_nodes_with_source_page_ids",
        int(summary.get("part_candidate_nodes_with_source_page_ids_count") or 0) >= thresholds.min_part_candidate_nodes_with_source_page_ids,
        summary.get("part_candidate_nodes_with_source_page_ids_count"),
        f">={thresholds.min_part_candidate_nodes_with_source_page_ids}",
    )
    add("part_candidate_missing_source_page_ids_zero", int(summary.get("part_candidate_missing_source_page_ids_count") or 0) == 0, summary.get("part_candidate_missing_source_page_ids_count"), 0)
    add("min_nomenclature_edges_preserved", int(summary.get("has_nomenclature_edges_preserved") or 0) >= thresholds.min_nomenclature_edges_preserved, summary.get("has_nomenclature_edges_preserved"), f">={thresholds.min_nomenclature_edges_preserved}")
    add("min_context_v2_edges_preserved", int(summary.get("has_context_v2_edges_preserved") or 0) >= thresholds.min_context_v2_edges_preserved, summary.get("has_context_v2_edges_preserved"), f">={thresholds.min_context_v2_edges_preserved}")
    add("min_confirmed_blank_preserve_source_trace", int(summary.get("confirmed_blank_pages_preserve_source_trace_count") or 0) >= thresholds.min_confirmed_blank_preserve_source_trace, summary.get("confirmed_blank_pages_preserve_source_trace_count"), f">={thresholds.min_confirmed_blank_preserve_source_trace}")

    add("orphan_edge_count_zero", int(summary.get("orphan_edge_count") or 0) == 0, summary.get("orphan_edge_count"), 0)
    if thresholds.require_page_scoped_missing_page_id_zero:
        add("page_scoped_missing_page_id_zero", int(summary.get("page_scoped_missing_page_id_count") or 0) == 0, summary.get("page_scoped_missing_page_id_count"), 0)
    add("direct_answer_allowed_zero", int(summary.get("direct_answer_allowed_count") or 0) == 0, summary.get("direct_answer_allowed_count"), 0)
    add("claim_proof_allowed_zero", int(summary.get("claim_proof_allowed_count") or 0) == 0, summary.get("claim_proof_allowed_count"), 0)
    add("retrieval_only_answer_allowed_zero", int(summary.get("retrieval_only_answer_allowed_count") or 0) == 0, summary.get("retrieval_only_answer_allowed_count"), 0)
    add("answer_capable_without_citation_zero", int(summary.get("answer_capable_without_citation_count") or 0) == 0, summary.get("answer_capable_without_citation_count"), 0)
    add("source_truth_mutation_allowed_zero", int(summary.get("source_truth_mutation_allowed_count") or 0) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("postgres_write_not_attempted", int(summary.get("postgres_write_attempt_count") or 0) == 0 and summary.get("postgres_write_attempted") is False, summary.get("postgres_write_attempt_count"), 0)

    if thresholds.require_source_overlay_quality_pass:
        add("source_overlay_quality_pass", summary.get("source_graph_overlay_quality_status") == "PASS", summary.get("source_graph_overlay_quality_status"), "PASS")
    if thresholds.require_dry_run_mode:
        add("dry_run_lineage_mode", summary.get("writeback_mode") not in FORBIDDEN_WRITEBACK_MODES, summary.get("writeback_mode"), "not write-postgres")

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "generated_at": now_iso(),
        "checks": checks,
        "summary": {k: summary.get(k) for k in [
            "page_count",
            "overlay_node_count",
            "overlay_edge_count",
            "part_candidate_node_count",
            "part_candidate_nodes_with_source_page_ids_count",
            "part_candidate_missing_source_page_ids_count",
            "part_candidate_source_page_link_count",
            "missing_page_id_count",
            "page_scoped_missing_page_id_count",
            "orphan_edge_count",
            "has_nomenclature_edges_preserved",
            "has_context_v2_edges_preserved",
            "retrieval_only_answer_allowed_count",
            "answer_capable_without_citation_count",
            "source_truth_mutation_allowed_count",
            "postgres_write_attempt_count",
        ]},
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    s = report["summary"]
    return "\n".join([
        "# TRACE-Net Graph Overlay PartCandidate Page-Lineage v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Writeback mode:** {s.get('writeback_mode')}",
        "",
        "## Summary",
        "",
        f"- Pages: {s.get('page_count')}",
        f"- Overlay nodes: {s.get('overlay_node_count')}",
        f"- Overlay edges: {s.get('overlay_edge_count')}",
        f"- PartCandidate nodes: {s.get('part_candidate_node_count')}",
        f"- PartCandidate nodes with source pages: {s.get('part_candidate_nodes_with_source_page_ids_count')}",
        f"- PartCandidate missing source pages: {s.get('part_candidate_missing_source_page_ids_count')}",
        f"- Page-scoped missing page IDs: {s.get('page_scoped_missing_page_id_count')}",
        f"- Orphan edges: {s.get('orphan_edge_count')}",
        f"- Nomenclature edges preserved: {s.get('has_nomenclature_edges_preserved')}",
        f"- ContextV2 edges preserved: {s.get('has_context_v2_edges_preserved')}",
        "",
        "PartCandidate nodes are cross-page bridge entities. They keep `source_page_ids` instead of being forced into a single `page_id`.",
        "This is a dry-run lineage overlay and does not mutate Postgres or source truth.",
        "",
    ])


def render_html(markdown_text: str) -> str:
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line.strip() else "" for line in markdown_text.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net PartCandidate Lineage</title></head><body>{body}</body></html>\n"


def build_part_lineage_overlay(
    graph_overlay_report_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    thresholds: QualityThresholds | None = None,
    write_quality: bool = True,
) -> dict[str, Any]:
    report_path = Path(graph_overlay_report_path)
    source = read_json(report_path)
    raw_nodes = source.get("node_plans") or source.get("nodes") or []
    raw_edges = source.get("edge_plans") or source.get("edges") or []
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError("graph overlay report must contain node_plans and edge_plans lists")

    nodes, edges, lineage_summary = enrich_part_candidate_lineage(raw_nodes, raw_edges)
    summary = build_summary(source, nodes, edges, lineage_summary)
    thresholds = thresholds or QualityThresholds()
    quality = evaluate_quality({"summary": summary}, thresholds)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    refined_report_path = output / "trace_net_graph_overlay_part_lineage_v1.json"
    nodes_path = output / "trace_net_graph_overlay_part_lineage_v1_nodes.jsonl"
    edges_path = output / "trace_net_graph_overlay_part_lineage_v1_edges.jsonl"
    part_lineage_path = output / "trace_net_graph_overlay_part_lineage_v1_part_candidates.jsonl"
    summary_path = output / "trace_net_graph_overlay_part_lineage_v1_summary.json"
    manifest_path = output / "trace_net_graph_overlay_part_lineage_v1_manifest.json"
    quality_path = output / "trace_net_graph_overlay_part_lineage_v1_quality.json"
    markdown_path = output / "trace_net_graph_overlay_part_lineage_v1.md"
    html_path = output / "trace_net_graph_overlay_part_lineage_v1.html"

    part_nodes = [n for n in nodes if str(n.get("node_type") or n.get("type")) == "PartCandidate"]
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "GRAPH_OVERLAY_PART_LINEAGE_BUILT",
        "quality_status": quality["status"],
        "generated_at": now_iso(),
        "source_graph_overlay_report_path": report_path.as_posix(),
        "writeback_mode": "dry_run_lineage_refinement",
        "summary": summary,
        "node_plans": nodes,
        "edge_plans": edges,
        "part_candidate_nodes": part_nodes,
        "quality": quality,
        "report_path": refined_report_path.as_posix(),
        "nodes_path": nodes_path.as_posix(),
        "edges_path": edges_path.as_posix(),
        "part_lineage_path": part_lineage_path.as_posix(),
        "summary_path": summary_path.as_posix(),
        "manifest_path": manifest_path.as_posix(),
        "quality_path": quality_path.as_posix(),
        "markdown_path": markdown_path.as_posix(),
        "html_path": html_path.as_posix(),
    }

    write_json(refined_report_path, result)
    write_jsonl(nodes_path, nodes)
    write_jsonl(edges_path, edges)
    write_jsonl(part_lineage_path, part_nodes)
    write_json(summary_path, summary)
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "generated_at": result["generated_at"],
        "status": result["status"],
        "quality_status": result["quality_status"],
        "input_paths": {"graph_overlay_report": report_path.as_posix()},
        "output_paths": {
            "report": refined_report_path.as_posix(),
            "nodes": nodes_path.as_posix(),
            "edges": edges_path.as_posix(),
            "part_lineage": part_lineage_path.as_posix(),
            "summary": summary_path.as_posix(),
            "quality": quality_path.as_posix(),
            "markdown": markdown_path.as_posix(),
            "html": html_path.as_posix(),
        },
    })
    if write_quality:
        write_json(quality_path, quality)
    md = render_markdown(result)
    markdown_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    return result


def thresholds_from_args(args: argparse.Namespace) -> QualityThresholds:
    return QualityThresholds(
        require_page_count=args.require_page_count,
        min_overlay_nodes=args.min_overlay_nodes,
        min_overlay_edges=args.min_overlay_edges,
        min_part_candidate_nodes=args.min_part_candidate_nodes,
        min_part_candidate_nodes_with_source_page_ids=args.min_part_candidate_nodes_with_source_page_ids,
        min_nomenclature_edges_preserved=args.min_nomenclature_edges_preserved,
        min_context_v2_edges_preserved=args.min_context_v2_edges_preserved,
        min_confirmed_blank_preserve_source_trace=args.min_confirmed_blank_preserve_source_trace,
        require_source_overlay_quality_pass=args.require_source_overlay_quality_pass,
        require_dry_run_mode=True,
        require_page_scoped_missing_page_id_zero=True,
    )


def print_build_summary(report: Mapping[str, Any]) -> None:
    s = report["summary"]
    print("TRACE-Net graph overlay PartCandidate page-lineage v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" writeback_mode: {s.get('writeback_mode')}")
    print(f" page_count: {s.get('page_count')}")
    print(f" overlay_node_count: {s.get('overlay_node_count')}")
    print(f" overlay_edge_count: {s.get('overlay_edge_count')}")
    print(f" part_candidate_node_count: {s.get('part_candidate_node_count')}")
    print(f" part_candidate_nodes_with_source_page_ids_count: {s.get('part_candidate_nodes_with_source_page_ids_count')}")
    print(f" part_candidate_missing_source_page_ids_count: {s.get('part_candidate_missing_source_page_ids_count')}")
    print(f" part_candidate_source_page_link_count: {s.get('part_candidate_source_page_link_count')}")
    print(f" missing_page_id_count: {s.get('missing_page_id_count')}")
    print(f" page_scoped_missing_page_id_count: {s.get('page_scoped_missing_page_id_count')}")
    print(f" orphan_edge_count: {s.get('orphan_edge_count')}")
    print(f" has_nomenclature_edges_preserved: {s.get('has_nomenclature_edges_preserved')}")
    print(f" has_context_v2_edges_preserved: {s.get('has_context_v2_edges_preserved')}")
    print(f" retrieval_only_answer_allowed_count: {s.get('retrieval_only_answer_allowed_count')}")
    print(f" source_truth_mutation_allowed_count: {s.get('source_truth_mutation_allowed_count')}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net graph overlay PartCandidate page-lineage v1")
    parser.add_argument("--graph-overlay-report", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-overlay-nodes", type=int, default=0)
    parser.add_argument("--min-overlay-edges", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes-with-source-page-ids", type=int, default=0)
    parser.add_argument("--min-nomenclature-edges-preserved", type=int, default=0)
    parser.add_argument("--min-context-v2-edges-preserved", type=int, default=0)
    parser.add_argument("--min-confirmed-blank-preserve-source-trace", type=int, default=0)
    parser.add_argument("--require-source-overlay-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        report = build_part_lineage_overlay(
            graph_overlay_report_path=args.graph_overlay_report,
            output_dir=args.output_dir,
            thresholds=thresholds_from_args(args),
            write_quality=args.quality,
        )
        print_build_summary(report)
        return 0 if report["quality_status"] == "PASS" else 1
    except Exception as exc:  # pragma: no cover
        print(f"TRACE-Net graph overlay part-lineage failed: {exc}")
        return 2


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net graph overlay PartCandidate page-lineage v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-overlay-nodes", type=int, default=0)
    parser.add_argument("--min-overlay-edges", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes-with-source-page-ids", type=int, default=0)
    parser.add_argument("--min-nomenclature-edges-preserved", type=int, default=0)
    parser.add_argument("--min-context-v2-edges-preserved", type=int, default=0)
    parser.add_argument("--min-confirmed-blank-preserve-source-trace", type=int, default=0)
    parser.add_argument("--require-source-overlay-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: list[str] | None = None) -> int:
    parser = quality_arg_parser()
    args = parser.parse_args(argv)
    try:
        report_path = Path(args.report_path)
        report = read_json(report_path)
        quality = evaluate_quality(report, thresholds_from_args(args))
        if args.write_json:
            write_json(report_path.with_name("trace_net_graph_overlay_part_lineage_v1_quality.json"), quality)
        s = quality["summary"]
        print("TRACE-Net graph overlay PartCandidate page-lineage v1 quality")
        print(f" Status: {quality['status']}")
        print(f" page_count: {s.get('page_count')}")
        print(f" overlay_node_count: {s.get('overlay_node_count')}")
        print(f" overlay_edge_count: {s.get('overlay_edge_count')}")
        print(f" part_candidate_node_count: {s.get('part_candidate_node_count')}")
        print(f" part_candidate_nodes_with_source_page_ids_count: {s.get('part_candidate_nodes_with_source_page_ids_count')}")
        print(f" part_candidate_missing_source_page_ids_count: {s.get('part_candidate_missing_source_page_ids_count')}")
        print(f" page_scoped_missing_page_id_count: {s.get('page_scoped_missing_page_id_count')}")
        print(f" orphan_edge_count: {s.get('orphan_edge_count')}")
        print(f" has_nomenclature_edges_preserved: {s.get('has_nomenclature_edges_preserved')}")
        print(f" has_context_v2_edges_preserved: {s.get('has_context_v2_edges_preserved')}")
        print(f" retrieval_only_answer_allowed_count: {s.get('retrieval_only_answer_allowed_count')}")
        print(f" source_truth_mutation_allowed_count: {s.get('source_truth_mutation_allowed_count')}")
        if args.write_json:
            print(f" quality_path: {report_path.with_name('trace_net_graph_overlay_part_lineage_v1_quality.json')}")
        return 0 if quality["status"] == "PASS" else 1
    except Exception as exc:  # pragma: no cover
        print(f"TRACE-Net graph overlay part-lineage quality check failed: {exc}")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
