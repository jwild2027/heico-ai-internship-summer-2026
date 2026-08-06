"""TRACE-Net Graph Overlay PartCandidate Property Normalizer v1.

Step 19.1 adds page lineage to PartCandidate nodes. This Step 19.2 adds
readable/canonical part-number properties to those same cross-page bridge nodes
so Leiden communities, graph UI summaries, and future review reports can show
human-readable part families instead of only node IDs or labels.

This module is a read-only artifact transform. It does not write to Postgres,
mutate graph source truth, or grant answer authority.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_graph_overlay_part_property_normalizer_v1"
ALGORITHM = "trace_net_part_candidate_property_normalizer_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/graph_overlay_part_property_normalizer")

CROSS_PAGE_NODE_TYPES = {"PartCandidate", "TrustAuthority"}
RETRIEVAL_ONLY_NODE_TYPES = {
    "PageElementRegistry",
    "VisualUnderstanding",
    "VisualRegion",
    "CalloutCandidate",
    "FishnetRetryPlan",
    "FishnetRetryAction",
    "ExtractionRoutePlan",
    "BlankSourceTracePreservation",
    "PartCandidate",
}

# This intentionally supports common HEICO/Embraer style part numbers such as
# 120-29067-005, 120-46137-501, and similar multi-hyphen numeric identifiers.
PART_NUMBER_RE = re.compile(r"\b(?:[A-Z]{1,4}[-–—])?[A-Z]{0,4}\d{1,5}(?:[-–—]\d{2,6}){1,4}\b", re.IGNORECASE)


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
        return value.strip().lower() in {"1", "true", "yes", "y", "allowed"}
    return False


def normalize_properties(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def get_node_id(node: Mapping[str, Any]) -> str:
    return str(node.get("node_id") or node.get("id") or stable_id("node", node.get("label"), node.get("properties")))


def get_edge_source(edge: Mapping[str, Any]) -> str:
    return str(edge.get("source_node_id") or edge.get("source") or "")


def get_edge_target(edge: Mapping[str, Any]) -> str:
    return str(edge.get("target_node_id") or edge.get("target") or "")


def node_type(node: Mapping[str, Any]) -> str:
    return str(node.get("node_type") or node.get("type") or "")


def edge_type(edge: Mapping[str, Any]) -> str:
    return str(edge.get("edge_type") or edge.get("type") or "")


def node_page_id(node: Mapping[str, Any]) -> str | None:
    page_id = node.get("page_id")
    if page_id:
        return str(page_id)
    props = node.get("properties")
    if isinstance(props, Mapping) and props.get("page_id"):
        return str(props.get("page_id"))
    return None


def is_part_candidate(node: Mapping[str, Any]) -> bool:
    return node_type(node) == "PartCandidate"


def clean_part_number(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "unknown", "n/a"}:
        return None
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", "", text)
    # Reject labels that are clearly not part numbers unless they contain a match.
    match = PART_NUMBER_RE.search(text)
    if match:
        return match.group(0).upper()
    return None


def part_number_from_node_id(node_id: str) -> str | None:
    # Common form: part_candidate::120-29067-005
    tail = node_id.split("::", 1)[1] if "::" in node_id else node_id
    return clean_part_number(tail)


def derive_part_number(node: Mapping[str, Any]) -> tuple[str | None, str]:
    props = normalize_properties(node.get("properties"))
    candidates = [
        (props.get("part_number"), "properties.part_number"),
        (props.get("canonical_part_candidate"), "properties.canonical_part_candidate"),
        (props.get("part_candidate"), "properties.part_candidate"),
        (props.get("candidate_part_number"), "properties.candidate_part_number"),
        (node.get("part_number"), "node.part_number"),
        (node.get("canonical_part_candidate"), "node.canonical_part_candidate"),
        (node.get("label"), "node.label"),
        (get_node_id(node), "node_id"),
    ]
    for value, source in candidates:
        part = part_number_from_node_id(str(value)) if source == "node_id" else clean_part_number(value)
        if part:
            return part, source
    return None, "not_found"


def infer_part_family(part_number: str | None) -> str | None:
    if not part_number:
        return None
    parts = part_number.split("-")
    if len(parts) >= 2:
        return "-".join(parts[:2])
    return None


def normalize_part_candidate_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out_nodes: list[dict[str, Any]] = []
    for node in nodes:
        out = dict(node)
        props = normalize_properties(out.get("properties"))
        if is_part_candidate(out):
            part_number, source = derive_part_number(out)
            source_page_ids = out.get("source_page_ids") or props.get("source_page_ids") or []
            if not isinstance(source_page_ids, list):
                source_page_ids = [source_page_ids]
            source_page_ids = sorted({str(p) for p in source_page_ids if p})

            props["part_number"] = part_number
            props["canonical_part_candidate"] = part_number
            props["part_number_source"] = source
            props["part_family"] = infer_part_family(part_number)
            props["node_scope"] = "cross_page_entity"
            props["source_page_ids"] = source_page_ids
            props["source_page_count"] = len(source_page_ids)
            props["part_candidate_property_normalized"] = bool(part_number)
            props.setdefault("can_answer_directly", False)
            props.setdefault("can_prove_claims", False)
            props.setdefault("can_mutate_source_truth", False)
            props.setdefault("requires_catalog_compare", True)
            props.setdefault("requires_authority_gate", True)

            out["part_number"] = part_number
            out["canonical_part_candidate"] = part_number
            out["part_family"] = infer_part_family(part_number)
            out["node_scope"] = "cross_page_entity"
            out["source_page_ids"] = source_page_ids
            out["source_page_count"] = len(source_page_ids)
            out["part_candidate_property_normalized"] = bool(part_number)
            # Do not invent a single page_id for cross-page part candidates.
        else:
            props.setdefault("node_scope", "page_scoped" if node_page_id(out) else "global_or_unknown")
        out["properties"] = props
        out_nodes.append(out)
    return out_nodes


def compute_orphan_edges(nodes: list[Mapping[str, Any]], edges: list[Mapping[str, Any]]) -> int:
    ids = {get_node_id(n) for n in nodes}
    return sum(1 for e in edges if get_edge_source(e) not in ids or get_edge_target(e) not in ids)


def build_summary(source_report: Mapping[str, Any], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    node_counts = Counter(node_type(n) for n in nodes)
    edge_counts = Counter(edge_type(e) for e in edges)
    part_nodes = [n for n in nodes if is_part_candidate(n)]
    part_with_pages = [n for n in part_nodes if n.get("source_page_ids")]
    part_with_part_number = [n for n in part_nodes if n.get("part_number") or n.get("properties", {}).get("part_number")]
    part_missing_number = [n for n in part_nodes if not (n.get("part_number") or n.get("properties", {}).get("part_number"))]

    page_scoped_missing_page_id = [
        n for n in nodes if node_type(n) not in CROSS_PAGE_NODE_TYPES and not node_page_id(n)
    ]

    direct_answer_allowed_count = sum(
        1 for n in nodes if truthy(n.get("can_answer_directly")) or truthy(n.get("properties", {}).get("can_answer_directly"))
    )
    claim_proof_allowed_count = sum(
        1 for n in nodes if truthy(n.get("can_prove_claims")) or truthy(n.get("properties", {}).get("can_prove_claims"))
    )
    source_truth_mutation_allowed_count = sum(
        1 for n in nodes if truthy(n.get("can_mutate_source_truth")) or truthy(n.get("properties", {}).get("can_mutate_source_truth"))
    )
    retrieval_only_answer_allowed_count = sum(
        1
        for n in nodes
        if node_type(n) in RETRIEVAL_ONLY_NODE_TYPES
        and (truthy(n.get("can_answer_directly")) or truthy(n.get("properties", {}).get("can_answer_directly")))
    )

    source_summary = source_report.get("summary", {}) if isinstance(source_report.get("summary"), Mapping) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "writeback_mode": "dry_run_overlay_part_property_normalization",
        "postgres_write_attempted": False,
        "postgres_write_attempt_count": 0,
        "source_lineage_quality_status": source_report.get("quality_status") or source_summary.get("quality_status"),
        "source_lineage_status": source_report.get("status"),
        "page_count": int(source_summary.get("page_count") or node_counts.get("Page", 0)),
        "overlay_node_count": len(nodes),
        "overlay_edge_count": len(edges),
        "node_type_counts": dict(sorted(node_counts.items())),
        "edge_type_counts": dict(sorted(edge_counts.items())),
        "page_node_count": node_counts.get("Page", 0),
        "part_candidate_node_count": len(part_nodes),
        "part_candidate_nodes_with_source_page_ids_count": len(part_with_pages),
        "part_candidate_missing_source_page_ids_count": len([n for n in part_nodes if not n.get("source_page_ids")]),
        "part_candidate_nodes_with_part_number_count": len(part_with_part_number),
        "part_candidate_missing_part_number_count": len(part_missing_number),
        "part_candidate_source_page_link_count": sum(len(n.get("source_page_ids") or []) for n in part_nodes),
        "part_family_count": len({n.get("part_family") for n in part_nodes if n.get("part_family")}),
        "page_scoped_missing_page_id_count": len(page_scoped_missing_page_id),
        "missing_page_id_count": len(page_scoped_missing_page_id),
        "table_cell_node_count": node_counts.get("TableCell", 0),
        "visual_node_count": node_counts.get("VisualUnderstanding", 0) + node_counts.get("VisualRegion", 0),
        "fishnet_node_count": node_counts.get("FishnetRetryPlan", 0),
        "citation_edge_count": edge_counts.get("HAS_CITATION", 0),
        "has_nomenclature_edges_preserved": int(source_summary.get("has_nomenclature_edges_preserved") or 0),
        "has_context_v2_edges_preserved": int(source_summary.get("has_context_v2_edges_preserved") or 0),
        "confirmed_blank_pages_preserve_source_trace_count": int(source_summary.get("confirmed_blank_pages_preserve_source_trace_count") or 0),
        "orphan_edge_count": compute_orphan_edges(nodes, edges),
        "direct_answer_allowed_count": direct_answer_allowed_count,
        "claim_proof_allowed_count": claim_proof_allowed_count,
        "retrieval_only_answer_allowed_count": retrieval_only_answer_allowed_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "unsafe_property_record_count": direct_answer_allowed_count + claim_proof_allowed_count + retrieval_only_answer_allowed_count + source_truth_mutation_allowed_count,
    }


@dataclass(frozen=True)
class QualityThresholds:
    require_page_count: int | None = None
    min_overlay_nodes: int = 0
    min_overlay_edges: int = 0
    min_part_candidate_nodes: int = 0
    min_part_candidate_nodes_with_source_page_ids: int = 0
    min_part_candidate_nodes_with_part_number: int = 0
    min_part_families: int = 0
    min_table_cell_nodes: int = 0
    min_context_v2_edges_preserved: int = 0
    min_nomenclature_edges_preserved: int = 0
    min_confirmed_blank_preserve_source_trace: int = 0
    require_source_lineage_quality_pass: bool = False


def evaluate_quality(report: Mapping[str, Any], thresholds: QualityThresholds) -> dict[str, Any]:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else report
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any = None, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    if thresholds.require_page_count is not None:
        add("page_count", int(summary.get("page_count") or 0) == thresholds.require_page_count, summary.get("page_count"), thresholds.require_page_count)
    add("min_overlay_nodes", int(summary.get("overlay_node_count") or 0) >= thresholds.min_overlay_nodes, summary.get("overlay_node_count"), f">={thresholds.min_overlay_nodes}")
    add("min_overlay_edges", int(summary.get("overlay_edge_count") or 0) >= thresholds.min_overlay_edges, summary.get("overlay_edge_count"), f">={thresholds.min_overlay_edges}")
    add("min_part_candidate_nodes", int(summary.get("part_candidate_node_count") or 0) >= thresholds.min_part_candidate_nodes, summary.get("part_candidate_node_count"), f">={thresholds.min_part_candidate_nodes}")
    add("min_part_candidate_nodes_with_source_page_ids", int(summary.get("part_candidate_nodes_with_source_page_ids_count") or 0) >= thresholds.min_part_candidate_nodes_with_source_page_ids, summary.get("part_candidate_nodes_with_source_page_ids_count"), f">={thresholds.min_part_candidate_nodes_with_source_page_ids}")
    add("min_part_candidate_nodes_with_part_number", int(summary.get("part_candidate_nodes_with_part_number_count") or 0) >= thresholds.min_part_candidate_nodes_with_part_number, summary.get("part_candidate_nodes_with_part_number_count"), f">={thresholds.min_part_candidate_nodes_with_part_number}")
    add("min_part_families", int(summary.get("part_family_count") or 0) >= thresholds.min_part_families, summary.get("part_family_count"), f">={thresholds.min_part_families}")
    add("min_table_cell_nodes", int(summary.get("table_cell_node_count") or 0) >= thresholds.min_table_cell_nodes, summary.get("table_cell_node_count"), f">={thresholds.min_table_cell_nodes}")
    add("min_context_v2_edges_preserved", int(summary.get("has_context_v2_edges_preserved") or 0) >= thresholds.min_context_v2_edges_preserved, summary.get("has_context_v2_edges_preserved"), f">={thresholds.min_context_v2_edges_preserved}")
    add("min_nomenclature_edges_preserved", int(summary.get("has_nomenclature_edges_preserved") or 0) >= thresholds.min_nomenclature_edges_preserved, summary.get("has_nomenclature_edges_preserved"), f">={thresholds.min_nomenclature_edges_preserved}")
    add("min_confirmed_blank_preserve_source_trace", int(summary.get("confirmed_blank_pages_preserve_source_trace_count") or 0) >= thresholds.min_confirmed_blank_preserve_source_trace, summary.get("confirmed_blank_pages_preserve_source_trace_count"), f">={thresholds.min_confirmed_blank_preserve_source_trace}")

    add("part_candidate_missing_source_page_ids_zero", int(summary.get("part_candidate_missing_source_page_ids_count") or 0) == 0, summary.get("part_candidate_missing_source_page_ids_count"), 0)
    add("part_candidate_missing_part_number_zero", int(summary.get("part_candidate_missing_part_number_count") or 0) == 0, summary.get("part_candidate_missing_part_number_count"), 0)
    add("page_scoped_missing_page_id_zero", int(summary.get("page_scoped_missing_page_id_count") or 0) == 0, summary.get("page_scoped_missing_page_id_count"), 0)
    add("orphan_edge_count_zero", int(summary.get("orphan_edge_count") or 0) == 0, summary.get("orphan_edge_count"), 0)
    add("direct_answer_allowed_zero", int(summary.get("direct_answer_allowed_count") or 0) == 0, summary.get("direct_answer_allowed_count"), 0)
    add("claim_proof_allowed_zero", int(summary.get("claim_proof_allowed_count") or 0) == 0, summary.get("claim_proof_allowed_count"), 0)
    add("retrieval_only_answer_allowed_zero", int(summary.get("retrieval_only_answer_allowed_count") or 0) == 0, summary.get("retrieval_only_answer_allowed_count"), 0)
    add("source_truth_mutation_allowed_zero", int(summary.get("source_truth_mutation_allowed_count") or 0) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("postgres_write_not_attempted", int(summary.get("postgres_write_attempt_count") or 0) == 0 and summary.get("postgres_write_attempted") is False, summary.get("postgres_write_attempt_count"), 0)
    if thresholds.require_source_lineage_quality_pass:
        add("source_lineage_quality_pass", summary.get("source_lineage_quality_status") == "PASS", summary.get("source_lineage_quality_status"), "PASS")

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
            "part_candidate_node_count",
            "part_candidate_nodes_with_source_page_ids_count",
            "part_candidate_nodes_with_part_number_count",
            "part_candidate_missing_part_number_count",
            "part_family_count",
            "page_scoped_missing_page_id_count",
            "orphan_edge_count",
            "retrieval_only_answer_allowed_count",
            "source_truth_mutation_allowed_count",
            "postgres_write_attempt_count",
        ]},
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    s = report["summary"]
    return "\n".join([
        "# TRACE-Net Graph Overlay PartCandidate Property Normalizer v1",
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
        f"- PartCandidate nodes with part_number: {s.get('part_candidate_nodes_with_part_number_count')}",
        f"- PartCandidate missing part_number: {s.get('part_candidate_missing_part_number_count')}",
        f"- Part families: {s.get('part_family_count')}",
        f"- Orphan edges: {s.get('orphan_edge_count')}",
        f"- Retrieval-only answer allowed: {s.get('retrieval_only_answer_allowed_count')}",
        f"- Source truth mutations: {s.get('source_truth_mutation_allowed_count')}",
        "",
        "## Safety note",
        "",
        "PartCandidate nodes remain cross-page retrieval/graph bridge nodes. The normalizer copies or derives readable part_number metadata for UI/community summaries, but it does not grant answer authority or mutate source truth.",
    ])


def render_html(markdown_text: str) -> str:
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line else "" for line in markdown_text.splitlines())
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Part Property Normalizer</title></head><body>{body}</body></html>"


def build_graph_overlay_part_property_normalizer(
    source_lineage_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    thresholds: QualityThresholds | None = None,
    write_quality: bool = True,
) -> dict[str, Any]:
    source_path = Path(source_lineage_path)
    source_report = read_json(source_path)
    raw_nodes = source_report.get("node_plans") or source_report.get("nodes") or []
    raw_edges = source_report.get("edge_plans") or source_report.get("edges") or []
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError("source lineage overlay must contain node_plans and edge_plans lists")

    nodes = [dict(n) for n in raw_nodes]
    edges = [dict(e) for e in raw_edges]
    normalized_nodes = normalize_part_candidate_nodes(nodes)
    summary = build_summary(source_report, normalized_nodes, edges)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_graph_overlay_part_property_normalizer_v1.json"
    nodes_path = out / "trace_net_graph_overlay_part_property_normalizer_v1_nodes.jsonl"
    edges_path = out / "trace_net_graph_overlay_part_property_normalizer_v1_edges.jsonl"
    part_nodes_path = out / "trace_net_graph_overlay_part_property_normalizer_v1_part_candidates.jsonl"
    summary_path = out / "trace_net_graph_overlay_part_property_normalizer_v1_summary.json"
    manifest_path = out / "trace_net_graph_overlay_part_property_normalizer_v1_manifest.json"
    quality_path = out / "trace_net_graph_overlay_part_property_normalizer_v1_quality.json"
    markdown_path = out / "trace_net_graph_overlay_part_property_normalizer_v1.md"
    html_path = out / "trace_net_graph_overlay_part_property_normalizer_v1.html"

    thresholds = thresholds or QualityThresholds()
    quality = evaluate_quality({"summary": summary}, thresholds)
    report = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "GRAPH_OVERLAY_PART_PROPERTY_NORMALIZER_BUILT",
        "quality_status": quality["status"],
        "generated_at": now_iso(),
        "source_lineage_path": source_path.as_posix(),
        "writeback_mode": "dry_run_overlay_part_property_normalization",
        "summary": summary,
        "node_plans": normalized_nodes,
        "edge_plans": edges,
        "part_candidate_nodes": [n for n in normalized_nodes if is_part_candidate(n)],
        "quality": quality,
        "report_path": report_path.as_posix(),
        "nodes_path": nodes_path.as_posix(),
        "edges_path": edges_path.as_posix(),
        "part_candidates_path": part_nodes_path.as_posix(),
        "summary_path": summary_path.as_posix(),
        "manifest_path": manifest_path.as_posix(),
        "quality_path": quality_path.as_posix(),
        "markdown_path": markdown_path.as_posix(),
        "html_path": html_path.as_posix(),
    }
    write_json(report_path, report)
    write_jsonl(nodes_path, normalized_nodes)
    write_jsonl(edges_path, edges)
    write_jsonl(part_nodes_path, report["part_candidate_nodes"])
    write_json(summary_path, summary)
    if write_quality:
        write_json(quality_path, quality)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": report["generated_at"],
        "status": report["status"],
        "quality_status": report["quality_status"],
        "input_paths": {"source_lineage": source_path.as_posix()},
        "output_paths": {
            "report": report_path.as_posix(),
            "nodes": nodes_path.as_posix(),
            "edges": edges_path.as_posix(),
            "part_candidates": part_nodes_path.as_posix(),
            "summary": summary_path.as_posix(),
            "quality": quality_path.as_posix(),
            "markdown": markdown_path.as_posix(),
            "html": html_path.as_posix(),
        },
    }
    write_json(manifest_path, manifest)
    md = render_markdown(report)
    markdown_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    return report


def thresholds_from_args(args: argparse.Namespace) -> QualityThresholds:
    return QualityThresholds(
        require_page_count=args.require_page_count,
        min_overlay_nodes=args.min_overlay_nodes,
        min_overlay_edges=args.min_overlay_edges,
        min_part_candidate_nodes=args.min_part_candidate_nodes,
        min_part_candidate_nodes_with_source_page_ids=args.min_part_candidate_nodes_with_source_page_ids,
        min_part_candidate_nodes_with_part_number=args.min_part_candidate_nodes_with_part_number,
        min_part_families=args.min_part_families,
        min_table_cell_nodes=args.min_table_cell_nodes,
        min_context_v2_edges_preserved=args.min_context_v2_edges_preserved,
        min_nomenclature_edges_preserved=args.min_nomenclature_edges_preserved,
        min_confirmed_blank_preserve_source_trace=args.min_confirmed_blank_preserve_source_trace,
        require_source_lineage_quality_pass=args.require_source_lineage_quality_pass,
    )


def print_build_summary(report: Mapping[str, Any]) -> None:
    s = report["summary"]
    print("TRACE-Net graph overlay PartCandidate property normalizer v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" writeback_mode: {s.get('writeback_mode')}")
    print(f" page_count: {s.get('page_count')}")
    print(f" overlay_node_count: {s.get('overlay_node_count')}")
    print(f" overlay_edge_count: {s.get('overlay_edge_count')}")
    print(f" part_candidate_node_count: {s.get('part_candidate_node_count')}")
    print(f" part_candidate_nodes_with_source_page_ids_count: {s.get('part_candidate_nodes_with_source_page_ids_count')}")
    print(f" part_candidate_nodes_with_part_number_count: {s.get('part_candidate_nodes_with_part_number_count')}")
    print(f" part_candidate_missing_part_number_count: {s.get('part_candidate_missing_part_number_count')}")
    print(f" part_family_count: {s.get('part_family_count')}")
    print(f" page_scoped_missing_page_id_count: {s.get('page_scoped_missing_page_id_count')}")
    print(f" orphan_edge_count: {s.get('orphan_edge_count')}")
    print(f" retrieval_only_answer_allowed_count: {s.get('retrieval_only_answer_allowed_count')}")
    print(f" source_truth_mutation_allowed_count: {s.get('source_truth_mutation_allowed_count')}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net PartCandidate property-normalized graph overlay v1")
    parser.add_argument("--graph-overlay-part-lineage", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-overlay-nodes", type=int, default=0)
    parser.add_argument("--min-overlay-edges", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes-with-source-page-ids", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes-with-part-number", type=int, default=0)
    parser.add_argument("--min-part-families", type=int, default=0)
    parser.add_argument("--min-table-cell-nodes", type=int, default=0)
    parser.add_argument("--min-context-v2-edges-preserved", type=int, default=0)
    parser.add_argument("--min-nomenclature-edges-preserved", type=int, default=0)
    parser.add_argument("--min-confirmed-blank-preserve-source-trace", type=int, default=0)
    parser.add_argument("--require-source-lineage-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        report = build_graph_overlay_part_property_normalizer(
            source_lineage_path=args.graph_overlay_part_lineage,
            output_dir=args.output_dir,
            thresholds=thresholds_from_args(args),
            write_quality=args.quality,
        )
        print_build_summary(report)
        return 0 if report["quality_status"] == "PASS" else 1
    except Exception as exc:  # pragma: no cover
        print(f"TRACE-Net graph overlay part property normalizer failed: {exc}")
        return 2


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net PartCandidate property normalizer overlay quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-overlay-nodes", type=int, default=0)
    parser.add_argument("--min-overlay-edges", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes-with-source-page-ids", type=int, default=0)
    parser.add_argument("--min-part-candidate-nodes-with-part-number", type=int, default=0)
    parser.add_argument("--min-part-families", type=int, default=0)
    parser.add_argument("--min-table-cell-nodes", type=int, default=0)
    parser.add_argument("--min-context-v2-edges-preserved", type=int, default=0)
    parser.add_argument("--min-nomenclature-edges-preserved", type=int, default=0)
    parser.add_argument("--min-confirmed-blank-preserve-source-trace", type=int, default=0)
    parser.add_argument("--require-source-lineage-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def check_quality_main(argv: list[str] | None = None) -> int:
    parser = quality_arg_parser()
    args = parser.parse_args(argv)
    try:
        report_path = Path(args.report_path)
        report = read_json(report_path)
        quality = evaluate_quality(report, thresholds_from_args(args))
        if args.write_json:
            out = report_path.with_name("trace_net_graph_overlay_part_property_normalizer_v1_quality.json")
            write_json(out, quality)
        s = report.get("summary", {})
        print("TRACE-Net graph overlay PartCandidate property normalizer v1 quality")
        print(f" Status: {quality['status']}")
        for key in [
            "page_count",
            "overlay_node_count",
            "overlay_edge_count",
            "part_candidate_node_count",
            "part_candidate_nodes_with_source_page_ids_count",
            "part_candidate_nodes_with_part_number_count",
            "part_candidate_missing_part_number_count",
            "part_family_count",
            "page_scoped_missing_page_id_count",
            "orphan_edge_count",
            "retrieval_only_answer_allowed_count",
            "source_truth_mutation_allowed_count",
        ]:
            print(f" {key}: {s.get(key)}")
        return 0 if quality["status"] == "PASS" else 1
    except Exception as exc:  # pragma: no cover
        print(f"TRACE-Net graph overlay part property normalizer quality failed: {exc}")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
