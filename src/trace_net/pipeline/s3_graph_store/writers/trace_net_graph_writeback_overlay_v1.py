"""TRACE-Net Graph Writeback Dry Run / Graph UI Overlay v1.

This module consumes the read-only Step 18 element graph attachment plan and
produces a graph-UI-ready overlay artifact. It deliberately does not write to
Postgres. The overlay lets TRACE-Net inspect planned table, visual, fishnet,
citation, and trust nodes/edges before any database mutation.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_graph_writeback_overlay_v1"
ALGORITHM = "trace_net_graph_writeback_dry_run_overlay_planner_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/graph_writeback_overlay")

GRAPH_EXPLORER_QUALITY_FILENAMES = [
    "trace_net_graph_explorer_v2_nomenclature_quality.json",
    "trace_net_graph_explorer_v2_nomenclature_fix_quality.json",
    "trace_net_graph_explorer_quality.json",
    "trace_net_graph_explorer_v1_quality.json",
]

RETRIEVAL_ONLY_NODE_TYPES = {
    "PageElementRegistry",
    "VisualUnderstanding",
    "VisualRegion",
    "CalloutCandidate",
    "FishnetRetryPlan",
    "FishnetRetryAction",
    "ExtractionRoutePlan",
    "BlankSourceTracePreservation",
}

ANSWER_SUPPORT_NODE_TYPES = {
    "EvidenceCandidate",
    "TableElement",
    "TableRow",
    "TableCell",
}

FORBIDDEN_WRITEBACK_MODES = {"write-postgres", "write_postgres", "postgres", "mutate-postgres"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


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
        return value.strip().lower() in {"1", "true", "yes", "y", "allowed"}
    return False


def get_nested_bool(row: Mapping[str, Any], key: str) -> bool:
    if truthy(row.get(key)):
        return True
    props = row.get("properties")
    if isinstance(props, Mapping) and truthy(props.get(key)):
        return True
    return False


def normalize_properties(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def normalize_node(node: Mapping[str, Any]) -> dict[str, Any]:
    props = normalize_properties(node.get("properties"))
    node_id = str(node.get("node_id") or node.get("id") or stable_id("node", props, node.get("label")))
    node_type = str(node.get("node_type") or node.get("type") or "UnknownNode")
    page_id = node.get("page_id") or props.get("page_id")
    label = str(node.get("label") or props.get("label") or f"{node_type} | {page_id or node_id}")

    # Enforce dry-run safety fields in the overlay copy. These fields describe
    # what the overlay itself is allowed to do, not what the original artifact
    # may later become after trust/citation gates.
    props.setdefault("overlay_writeback_mode", "dry_run_overlay")
    props.setdefault("can_mutate_source_truth", False)
    props.setdefault("can_answer_directly", False)
    props.setdefault("can_prove_claims", False)
    props.setdefault("requires_authority_gate", True)

    return {
        "node_id": node_id,
        "node_type": node_type,
        "label": label,
        "page_id": page_id,
        "properties": props,
        "overlay_source": "element_graph_attachment_plan_v1",
        "writeback_mode": "dry_run_overlay",
        "can_answer_directly": bool(get_nested_bool(node, "can_answer_directly")),
        "can_prove_claims": bool(get_nested_bool(node, "can_prove_claims")),
        "can_mutate_source_truth": bool(get_nested_bool(node, "can_mutate_source_truth")),
    }


def normalize_edge(edge: Mapping[str, Any]) -> dict[str, Any]:
    props = normalize_properties(edge.get("properties"))
    source = str(edge.get("source_node_id") or edge.get("source") or "")
    target = str(edge.get("target_node_id") or edge.get("target") or "")
    edge_type = str(edge.get("edge_type") or edge.get("type") or "RELATED_TO")
    page_id = edge.get("page_id") or props.get("page_id")
    edge_id = str(edge.get("edge_id") or stable_id("edge", edge_type, source, target, page_id))

    props.setdefault("overlay_writeback_mode", "dry_run_overlay")
    props.setdefault("can_mutate_source_truth", False)
    props.setdefault("can_answer_directly", False)
    props.setdefault("can_prove_claims", False)

    return {
        "edge_id": edge_id,
        "edge_type": edge_type,
        "source_node_id": source,
        "target_node_id": target,
        "page_id": page_id,
        "properties": props,
        "overlay_source": "element_graph_attachment_plan_v1",
        "writeback_mode": "dry_run_overlay",
        "can_answer_directly": bool(get_nested_bool(edge, "can_answer_directly")),
        "can_prove_claims": bool(get_nested_bool(edge, "can_prove_claims")),
        "can_mutate_source_truth": bool(get_nested_bool(edge, "can_mutate_source_truth")),
    }


def load_graph_explorer_quality(graph_explorer_dir: str | Path | None) -> dict[str, Any]:
    if not graph_explorer_dir:
        return {
            "status": "NOT_PROVIDED",
            "quality_path": None,
            "nomenclature_nodes": 0,
            "has_nomenclature_edges": 0,
            "page_context_v2_nodes": 0,
            "has_context_v2_edges": 0,
            "required_context_v2_missing_page_count": None,
        }
    root = Path(graph_explorer_dir)
    for name in GRAPH_EXPLORER_QUALITY_FILENAMES:
        path = root / name
        if path.exists():
            payload = read_json(path)
            payload.setdefault("quality_path", path.as_posix())
            payload.setdefault("status", payload.get("quality_status", "UNKNOWN"))
            return dict(payload)
    return {
        "status": "MISSING",
        "quality_path": None,
        "nomenclature_nodes": 0,
        "has_nomenclature_edges": 0,
        "page_context_v2_nodes": 0,
        "has_context_v2_edges": 0,
        "required_context_v2_missing_page_count": None,
    }


def build_summary(
    attachment: Mapping[str, Any],
    overlay_nodes: list[dict[str, Any]],
    overlay_edges: list[dict[str, Any]],
    graph_quality: Mapping[str, Any],
    mode: str,
) -> dict[str, Any]:
    node_type_counts = Counter(n["node_type"] for n in overlay_nodes)
    edge_type_counts = Counter(e["edge_type"] for e in overlay_edges)
    node_ids = {n["node_id"] for n in overlay_nodes}
    orphan_edges = [e for e in overlay_edges if e["source_node_id"] not in node_ids or e["target_node_id"] not in node_ids]

    direct_answer_allowed_count = sum(1 for n in overlay_nodes if truthy(n.get("can_answer_directly"))) + sum(
        1 for e in overlay_edges if truthy(e.get("can_answer_directly"))
    )
    claim_proof_allowed_count = sum(1 for n in overlay_nodes if truthy(n.get("can_prove_claims"))) + sum(
        1 for e in overlay_edges if truthy(e.get("can_prove_claims"))
    )
    source_truth_mutation_allowed_count = sum(1 for n in overlay_nodes if truthy(n.get("can_mutate_source_truth"))) + sum(
        1 for e in overlay_edges if truthy(e.get("can_mutate_source_truth"))
    )

    retrieval_only_answer_allowed_count = sum(
        1
        for n in overlay_nodes
        if n["node_type"] in RETRIEVAL_ONLY_NODE_TYPES and truthy(n.get("can_answer_directly"))
    )

    answer_capable_without_citation_count = 0
    evidence_or_support_nodes = [
        n
        for n in overlay_nodes
        if n["node_type"] in ANSWER_SUPPORT_NODE_TYPES
        or str(n.get("properties", {}).get("rag_bucket", "")).endswith("evidence")
    ]
    citation_sources = {e["source_node_id"] for e in overlay_edges if e["edge_type"] == "HAS_CITATION"}
    for n in evidence_or_support_nodes:
        props = n.get("properties", {})
        requires_citation = truthy(props.get("requires_citation"))
        answer_support = truthy(props.get("answer_support_candidate")) or truthy(props.get("can_support_answer"))
        if (requires_citation or answer_support) and n["node_id"] not in citation_sources:
            # A table row/cell may be answer-support only through its parent table.
            # Do not count support nodes without explicit citation unless they are
            # explicitly marked answer-capable. The overlay itself still blocks
            # direct answering.
            if truthy(props.get("can_answer_directly")) or truthy(props.get("final_answer_allowed")):
                answer_capable_without_citation_count += 1

    attachment_summary = attachment.get("summary", {}) if isinstance(attachment.get("summary"), Mapping) else {}

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "writeback_mode": mode,
        "postgres_write_attempted": False,
        "postgres_write_attempt_count": 0,
        "attachment_plan_quality_status": attachment.get("quality_status") or attachment_summary.get("quality_status"),
        "attachment_plan_status": attachment.get("status"),
        "graph_explorer_quality_status": graph_quality.get("status") or graph_quality.get("quality_status"),
        "graph_explorer_quality_path": graph_quality.get("quality_path"),
        "page_count": node_type_counts.get("Page", attachment_summary.get("page_count", 0)),
        "overlay_node_count": len(overlay_nodes),
        "overlay_edge_count": len(overlay_edges),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "page_node_count": node_type_counts.get("Page", 0),
        "table_node_count": node_type_counts.get("TableElement", 0),
        "table_row_node_count": node_type_counts.get("TableRow", 0),
        "table_cell_node_count": node_type_counts.get("TableCell", 0),
        "visual_node_count": node_type_counts.get("VisualUnderstanding", 0) + node_type_counts.get("VisualRegion", 0),
        "callout_node_count": node_type_counts.get("CalloutCandidate", 0),
        "fishnet_node_count": node_type_counts.get("FishnetRetryPlan", 0),
        "fishnet_action_node_count": node_type_counts.get("FishnetRetryAction", 0),
        "evidence_candidate_node_count": node_type_counts.get("EvidenceCandidate", 0),
        "citation_node_count": node_type_counts.get("Citation", 0),
        "trust_authority_node_count": node_type_counts.get("TrustAuthority", 0),
        "blank_source_trace_preservation_node_count": node_type_counts.get("BlankSourceTracePreservation", 0),
        "has_table_cell_edge_count": edge_type_counts.get("HAS_TABLE_CELL", 0),
        "citation_edge_count": edge_type_counts.get("HAS_CITATION", 0),
        "has_nomenclature_edges_preserved": int(graph_quality.get("has_nomenclature_edges") or 0),
        "nomenclature_nodes_preserved": int(graph_quality.get("nomenclature_nodes") or 0),
        "has_context_v2_edges_preserved": int(graph_quality.get("has_context_v2_edges") or 0),
        "context_v2_nodes_preserved": int(graph_quality.get("page_context_v2_nodes") or graph_quality.get("context_v2_page_count") or 0),
        "required_context_v2_missing_page_count": graph_quality.get("required_context_v2_missing_page_count"),
        "orphan_edge_count": len(orphan_edges),
        "missing_page_id_count": sum(1 for n in overlay_nodes if n["node_type"] != "TrustAuthority" and not n.get("page_id")),
        "direct_answer_allowed_count": direct_answer_allowed_count,
        "claim_proof_allowed_count": claim_proof_allowed_count,
        "answer_capable_without_citation_count": answer_capable_without_citation_count,
        "retrieval_only_answer_allowed_count": retrieval_only_answer_allowed_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "confirmed_blank_pages_preserve_source_trace_count": node_type_counts.get("BlankSourceTracePreservation", 0),
        "unsafe_overlay_record_count": direct_answer_allowed_count
        + claim_proof_allowed_count
        + retrieval_only_answer_allowed_count
        + source_truth_mutation_allowed_count,
        "source_attachment_node_count": int(attachment_summary.get("node_plan_count", len(overlay_nodes)) or len(overlay_nodes)),
        "source_attachment_edge_count": int(attachment_summary.get("edge_plan_count", len(overlay_edges)) or len(overlay_edges)),
    }


@dataclass(frozen=True)
class QualityThresholds:
    require_page_count: int | None = None
    min_overlay_nodes: int = 0
    min_overlay_edges: int = 0
    min_page_nodes: int = 0
    min_table_cell_nodes: int = 0
    min_visual_nodes: int = 0
    min_fishnet_nodes: int = 0
    min_citation_edges: int = 0
    min_nomenclature_edges_preserved: int = 0
    min_context_v2_edges_preserved: int = 0
    min_confirmed_blank_preserve_source_trace: int = 0
    require_attachment_quality_pass: bool = False
    require_graph_explorer_quality_pass: bool = False
    require_dry_run_mode: bool = True


def evaluate_quality(report: Mapping[str, Any], thresholds: QualityThresholds) -> dict[str, Any]:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else report
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    if thresholds.require_page_count is not None:
        add("page_count", summary.get("page_count") == thresholds.require_page_count, summary.get("page_count"), thresholds.require_page_count)

    add("min_overlay_nodes", int(summary.get("overlay_node_count") or 0) >= thresholds.min_overlay_nodes, summary.get("overlay_node_count"), f">={thresholds.min_overlay_nodes}")
    add("min_overlay_edges", int(summary.get("overlay_edge_count") or 0) >= thresholds.min_overlay_edges, summary.get("overlay_edge_count"), f">={thresholds.min_overlay_edges}")
    add("min_page_nodes", int(summary.get("page_node_count") or 0) >= thresholds.min_page_nodes, summary.get("page_node_count"), f">={thresholds.min_page_nodes}")
    add("min_table_cell_nodes", int(summary.get("table_cell_node_count") or 0) >= thresholds.min_table_cell_nodes, summary.get("table_cell_node_count"), f">={thresholds.min_table_cell_nodes}")
    add("min_visual_nodes", int(summary.get("visual_node_count") or 0) >= thresholds.min_visual_nodes, summary.get("visual_node_count"), f">={thresholds.min_visual_nodes}")
    add("min_fishnet_nodes", int(summary.get("fishnet_node_count") or 0) >= thresholds.min_fishnet_nodes, summary.get("fishnet_node_count"), f">={thresholds.min_fishnet_nodes}")
    add("min_citation_edges", int(summary.get("citation_edge_count") or 0) >= thresholds.min_citation_edges, summary.get("citation_edge_count"), f">={thresholds.min_citation_edges}")
    add("min_nomenclature_edges_preserved", int(summary.get("has_nomenclature_edges_preserved") or 0) >= thresholds.min_nomenclature_edges_preserved, summary.get("has_nomenclature_edges_preserved"), f">={thresholds.min_nomenclature_edges_preserved}")
    add("min_context_v2_edges_preserved", int(summary.get("has_context_v2_edges_preserved") or 0) >= thresholds.min_context_v2_edges_preserved, summary.get("has_context_v2_edges_preserved"), f">={thresholds.min_context_v2_edges_preserved}")
    add("min_confirmed_blank_preserve_source_trace", int(summary.get("confirmed_blank_pages_preserve_source_trace_count") or 0) >= thresholds.min_confirmed_blank_preserve_source_trace, summary.get("confirmed_blank_pages_preserve_source_trace_count"), f">={thresholds.min_confirmed_blank_preserve_source_trace}")

    add("orphan_edge_count_zero", int(summary.get("orphan_edge_count") or 0) == 0, summary.get("orphan_edge_count"), 0)
    add("answer_capable_without_citation_zero", int(summary.get("answer_capable_without_citation_count") or 0) == 0, summary.get("answer_capable_without_citation_count"), 0)
    add("retrieval_only_answer_allowed_zero", int(summary.get("retrieval_only_answer_allowed_count") or 0) == 0, summary.get("retrieval_only_answer_allowed_count"), 0)
    add("direct_answer_allowed_zero", int(summary.get("direct_answer_allowed_count") or 0) == 0, summary.get("direct_answer_allowed_count"), 0)
    add("claim_proof_allowed_zero", int(summary.get("claim_proof_allowed_count") or 0) == 0, summary.get("claim_proof_allowed_count"), 0)
    add("source_truth_mutation_allowed_zero", int(summary.get("source_truth_mutation_allowed_count") or 0) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("postgres_write_not_attempted", int(summary.get("postgres_write_attempt_count") or 0) == 0 and summary.get("postgres_write_attempted") is False, summary.get("postgres_write_attempt_count"), 0)

    if thresholds.require_attachment_quality_pass:
        add("attachment_quality_pass", summary.get("attachment_plan_quality_status") == "PASS", summary.get("attachment_plan_quality_status"), "PASS")
    if thresholds.require_graph_explorer_quality_pass:
        graph_status = summary.get("graph_explorer_quality_status")
        add("graph_explorer_quality_pass", graph_status in {"PASS", "OK"}, graph_status, "PASS or OK")
    if thresholds.require_dry_run_mode:
        add("dry_run_mode", summary.get("writeback_mode") not in FORBIDDEN_WRITEBACK_MODES, summary.get("writeback_mode"), "not write-postgres")

    required_missing = summary.get("required_context_v2_missing_page_count")
    if required_missing is not None:
        add("required_context_v2_missing_zero", int(required_missing) == 0, required_missing, 0)

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "checks": checks,
        "generated_at": now_iso(),
        "summary": {k: summary.get(k) for k in [
            "page_count",
            "overlay_node_count",
            "overlay_edge_count",
            "page_node_count",
            "table_cell_node_count",
            "visual_node_count",
            "fishnet_node_count",
            "citation_edge_count",
            "has_nomenclature_edges_preserved",
            "has_context_v2_edges_preserved",
            "confirmed_blank_pages_preserve_source_trace_count",
            "orphan_edge_count",
            "answer_capable_without_citation_count",
            "retrieval_only_answer_allowed_count",
            "source_truth_mutation_allowed_count",
            "postgres_write_attempt_count",
        ]},
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# TRACE-Net Graph Writeback Dry Run / Graph UI Overlay v1",
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
        f"- Table cells: {s.get('table_cell_node_count')}",
        f"- Visual nodes: {s.get('visual_node_count')}",
        f"- Fishnet plans: {s.get('fishnet_node_count')}",
        f"- Citation edges: {s.get('citation_edge_count')}",
        f"- Orphan edges: {s.get('orphan_edge_count')}",
        f"- Nomenclature edges preserved: {s.get('has_nomenclature_edges_preserved')}",
        f"- ContextV2 edges preserved: {s.get('has_context_v2_edges_preserved')}",
        f"- Confirmed blank pages preserve source trace: {s.get('confirmed_blank_pages_preserve_source_trace_count')}",
        "",
        "## Safety",
        "",
        f"- Answer-capable without citation: {s.get('answer_capable_without_citation_count')}",
        f"- Retrieval-only answer allowed: {s.get('retrieval_only_answer_allowed_count')}",
        f"- Source-truth mutation allowed: {s.get('source_truth_mutation_allowed_count')}",
        f"- Postgres write attempts: {s.get('postgres_write_attempt_count')}",
        "",
        "This overlay is a dry-run graph plan. It does not mutate Postgres or source truth.",
    ]
    return "\n".join(lines) + "\n"


def render_html(markdown_text: str) -> str:
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line.strip() else "" for line in markdown_text.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Graph Overlay</title></head><body>{body}</body></html>\n"


def build_graph_writeback_overlay(
    attachment_plan_path: str | Path,
    graph_explorer_dir: str | Path | None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    mode: str = "dry-run",
    thresholds: QualityThresholds | None = None,
    write_quality: bool = True,
) -> dict[str, Any]:
    if mode in FORBIDDEN_WRITEBACK_MODES:
        raise ValueError("Step 19 v1 is dry-run/UI-overlay only; refusing Postgres writeback mode")

    attachment_path = Path(attachment_plan_path)
    attachment = read_json(attachment_path)
    raw_nodes = attachment.get("node_plans") or attachment.get("nodes") or []
    raw_edges = attachment.get("edge_plans") or attachment.get("edges") or []
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError("attachment plan must contain node_plans and edge_plans lists")

    overlay_nodes = [normalize_node(n) for n in raw_nodes]
    overlay_edges = [normalize_edge(e) for e in raw_edges]
    graph_quality = load_graph_explorer_quality(graph_explorer_dir)
    summary = build_summary(attachment, overlay_nodes, overlay_edges, graph_quality, "dry_run_overlay")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "trace_net_graph_writeback_overlay_v1.json"
    nodes_path = output / "trace_net_graph_writeback_overlay_v1_nodes.jsonl"
    edges_path = output / "trace_net_graph_writeback_overlay_v1_edges.jsonl"
    summary_path = output / "trace_net_graph_writeback_overlay_v1_summary.json"
    manifest_path = output / "trace_net_graph_writeback_overlay_v1_manifest.json"
    quality_path = output / "trace_net_graph_writeback_overlay_v1_quality.json"
    markdown_path = output / "trace_net_graph_writeback_overlay_v1.md"
    html_path = output / "trace_net_graph_writeback_overlay_v1.html"

    thresholds = thresholds or QualityThresholds()
    quality = evaluate_quality({"summary": summary}, thresholds)

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "GRAPH_WRITEBACK_OVERLAY_BUILT",
        "quality_status": quality["status"],
        "generated_at": now_iso(),
        "writeback_mode": "dry_run_overlay",
        "attachment_plan_path": attachment_path.as_posix(),
        "graph_explorer_dir": None if graph_explorer_dir is None else Path(graph_explorer_dir).as_posix(),
        "summary": summary,
        "graph_explorer_quality": graph_quality,
        "node_plans": overlay_nodes,
        "edge_plans": overlay_edges,
        "quality": quality,
        "report_path": report_path.as_posix(),
        "nodes_path": nodes_path.as_posix(),
        "edges_path": edges_path.as_posix(),
        "summary_path": summary_path.as_posix(),
        "manifest_path": manifest_path.as_posix(),
        "quality_path": quality_path.as_posix(),
        "markdown_path": markdown_path.as_posix(),
        "html_path": html_path.as_posix(),
    }

    write_json(report_path, report)
    write_jsonl(nodes_path, overlay_nodes)
    write_jsonl(edges_path, overlay_edges)
    write_json(summary_path, summary)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": report["generated_at"],
        "status": report["status"],
        "quality_status": quality["status"],
        "writeback_mode": "dry_run_overlay",
        "input_paths": {
            "attachment_plan": attachment_path.as_posix(),
            "graph_explorer_dir": None if graph_explorer_dir is None else Path(graph_explorer_dir).as_posix(),
        },
        "output_paths": {
            "report": report_path.as_posix(),
            "nodes": nodes_path.as_posix(),
            "edges": edges_path.as_posix(),
            "summary": summary_path.as_posix(),
            "quality": quality_path.as_posix(),
            "markdown": markdown_path.as_posix(),
            "html": html_path.as_posix(),
        },
    }
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, quality)
    md = render_markdown(report)
    markdown_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    return report


def thresholds_from_args(args: argparse.Namespace) -> QualityThresholds:
    return QualityThresholds(
        require_page_count=args.require_page_count,
        min_overlay_nodes=args.min_overlay_nodes,
        min_overlay_edges=args.min_overlay_edges,
        min_page_nodes=args.min_page_nodes,
        min_table_cell_nodes=args.min_table_cell_nodes,
        min_visual_nodes=args.min_visual_nodes,
        min_fishnet_nodes=args.min_fishnet_nodes,
        min_citation_edges=args.min_citation_edges,
        min_nomenclature_edges_preserved=args.min_nomenclature_edges_preserved,
        min_context_v2_edges_preserved=args.min_context_v2_edges_preserved,
        min_confirmed_blank_preserve_source_trace=args.min_confirmed_blank_preserve_source_trace,
        require_attachment_quality_pass=args.require_attachment_quality_pass,
        require_graph_explorer_quality_pass=args.require_graph_explorer_quality_pass,
        require_dry_run_mode=True,
    )


def print_build_summary(report: Mapping[str, Any]) -> None:
    s = report["summary"]
    print("TRACE-Net graph writeback dry run / graph UI overlay v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" writeback_mode: {s.get('writeback_mode')}")
    print(f" page_count: {s.get('page_count')}")
    print(f" overlay_node_count: {s.get('overlay_node_count')}")
    print(f" overlay_edge_count: {s.get('overlay_edge_count')}")
    print(f" table_cell_node_count: {s.get('table_cell_node_count')}")
    print(f" visual_node_count: {s.get('visual_node_count')}")
    print(f" fishnet_node_count: {s.get('fishnet_node_count')}")
    print(f" citation_edge_count: {s.get('citation_edge_count')}")
    print(f" orphan_edge_count: {s.get('orphan_edge_count')}")
    print(f" has_nomenclature_edges_preserved: {s.get('has_nomenclature_edges_preserved')}")
    print(f" has_context_v2_edges_preserved: {s.get('has_context_v2_edges_preserved')}")
    print(f" confirmed_blank_pages_preserve_source_trace_count: {s.get('confirmed_blank_pages_preserve_source_trace_count')}")
    print(f" answer_capable_without_citation_count: {s.get('answer_capable_without_citation_count')}")
    print(f" retrieval_only_answer_allowed_count: {s.get('retrieval_only_answer_allowed_count')}")
    print(f" source_truth_mutation_allowed_count: {s.get('source_truth_mutation_allowed_count')}")
    print(f" report_path: {report.get('report_path')}")
    print(f" nodes_path: {report.get('nodes_path')}")
    print(f" edges_path: {report.get('edges_path')}")
    print(f" quality_path: {report.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net graph writeback dry-run/UI overlay v1")
    parser.add_argument("--attachment-plan", required=True)
    parser.add_argument("--graph-explorer-dir", default="local_data/organization/trace_net/graph_explorer")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--mode", default="dry-run", choices=["dry-run", "ui-overlay"])
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-overlay-nodes", type=int, default=0)
    parser.add_argument("--min-overlay-edges", type=int, default=0)
    parser.add_argument("--min-page-nodes", type=int, default=0)
    parser.add_argument("--min-table-cell-nodes", type=int, default=0)
    parser.add_argument("--min-visual-nodes", type=int, default=0)
    parser.add_argument("--min-fishnet-nodes", type=int, default=0)
    parser.add_argument("--min-citation-edges", type=int, default=0)
    parser.add_argument("--min-nomenclature-edges-preserved", type=int, default=0)
    parser.add_argument("--min-context-v2-edges-preserved", type=int, default=0)
    parser.add_argument("--min-confirmed-blank-preserve-source-trace", type=int, default=0)
    parser.add_argument("--require-attachment-quality-pass", action="store_true")
    parser.add_argument("--require-graph-explorer-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        report = build_graph_writeback_overlay(
            attachment_plan_path=args.attachment_plan,
            graph_explorer_dir=args.graph_explorer_dir,
            output_dir=args.output_dir,
            mode=args.mode,
            thresholds=thresholds_from_args(args),
            write_quality=args.quality,
        )
        print_build_summary(report)
        return 0 if report["quality_status"] == "PASS" else 1
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"TRACE-Net graph writeback overlay failed: {exc}")
        return 2


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net graph writeback overlay v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-overlay-nodes", type=int, default=0)
    parser.add_argument("--min-overlay-edges", type=int, default=0)
    parser.add_argument("--min-page-nodes", type=int, default=0)
    parser.add_argument("--min-table-cell-nodes", type=int, default=0)
    parser.add_argument("--min-visual-nodes", type=int, default=0)
    parser.add_argument("--min-fishnet-nodes", type=int, default=0)
    parser.add_argument("--min-citation-edges", type=int, default=0)
    parser.add_argument("--min-nomenclature-edges-preserved", type=int, default=0)
    parser.add_argument("--min-context-v2-edges-preserved", type=int, default=0)
    parser.add_argument("--min-confirmed-blank-preserve-source-trace", type=int, default=0)
    parser.add_argument("--require-attachment-quality-pass", action="store_true")
    parser.add_argument("--require-graph-explorer-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: list[str] | None = None) -> int:
    parser = quality_arg_parser()
    args = parser.parse_args(argv)
    try:
        report_path = Path(args.report_path)
        report = read_json(report_path)
        thresholds = thresholds_from_args(args)
        quality = evaluate_quality(report, thresholds)
        if args.write_json:
            quality_path = report_path.with_name("trace_net_graph_writeback_overlay_v1_quality.json")
            write_json(quality_path, quality)
        s = quality["summary"]
        print("TRACE-Net graph writeback overlay v1 quality")
        print(f" Status: {quality['status']}")
        print(f" page_count: {s.get('page_count')}")
        print(f" overlay_node_count: {s.get('overlay_node_count')}")
        print(f" overlay_edge_count: {s.get('overlay_edge_count')}")
        print(f" table_cell_node_count: {s.get('table_cell_node_count')}")
        print(f" visual_node_count: {s.get('visual_node_count')}")
        print(f" fishnet_node_count: {s.get('fishnet_node_count')}")
        print(f" citation_edge_count: {s.get('citation_edge_count')}")
        print(f" orphan_edge_count: {s.get('orphan_edge_count')}")
        print(f" has_nomenclature_edges_preserved: {s.get('has_nomenclature_edges_preserved')}")
        print(f" has_context_v2_edges_preserved: {s.get('has_context_v2_edges_preserved')}")
        print(f" confirmed_blank_pages_preserve_source_trace_count: {s.get('confirmed_blank_pages_preserve_source_trace_count')}")
        print(f" answer_capable_without_citation_count: {s.get('answer_capable_without_citation_count')}")
        print(f" retrieval_only_answer_allowed_count: {s.get('retrieval_only_answer_allowed_count')}")
        print(f" source_truth_mutation_allowed_count: {s.get('source_truth_mutation_allowed_count')}")
        if args.write_json:
            print(f" quality_path: {report_path.with_name('trace_net_graph_writeback_overlay_v1_quality.json')}")
        return 0 if quality["status"] == "PASS" else 1
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"TRACE-Net graph writeback overlay quality check failed: {exc}")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
