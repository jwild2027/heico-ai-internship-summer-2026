"""Traceability helpers for the exported document organization graph.

This module is read-only.  It answers questions such as:

    part -> pages -> source links -> page context
    page -> document / ATA / parts / source links / page context
    vector candidate page_id -> graph source/context trace

The production idea is the same when Qdrant is added: Qdrant returns chunk_id/page_id
payloads, and this layer resolves those IDs through the PostgreSQL graph/catalog.
For the local MVP, we resolve against graph_nodes.json and graph_edges.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from collections import Counter
from typing import Any

from tiff.document_graph_traversal import GraphNode, GraphStore, context_score


DEFAULT_GRAPH_DIR = "local_data/organization/graph"
DEFAULT_JSON_OUTPUT = "local_data/organization/graph/traceability_report.json"


@dataclass
class TraceStep:
    label: str
    node_id: str
    node_type: str
    node_label: str
    edge_type: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "edge_type": self.edge_type,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "node_label": self.node_label,
            "properties": self.properties,
        }


@dataclass
class TracePath:
    id: str
    description: str
    status: str
    steps: list[TraceStep] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "summary": self.summary,
            "steps": [step.to_jsonable() for step in self.steps],
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class TraceabilityReport:
    status: str
    graph_dir: str
    node_count: int
    edge_count: int
    node_type_counts: dict[str, int]
    edge_type_counts: dict[str, int]
    traces: list[TracePath]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "graph_dir": self.graph_dir,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "node_type_counts": self.node_type_counts,
            "edge_type_counts": self.edge_type_counts,
            "warnings": self.warnings,
            "errors": self.errors,
            "traces": [trace.to_jsonable() for trace in self.traces],
        }


def write_traceability_json(report: TraceabilityReport, path: str | Path = DEFAULT_JSON_OUTPUT) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_jsonable(), indent=2), encoding="utf-8")


def build_traceability_report(
    graph_dir: str | Path = DEFAULT_GRAPH_DIR,
    part: str | None = None,
    page: str | None = None,
    ata: str | None = None,
    vector_page: str | None = None,
    vector_chunk: str | None = None,
    vector_score: float | None = None,
    limit: int = 8,
    strict: bool = False,
) -> TraceabilityReport:
    graph = GraphStore.load(graph_dir)
    warnings: list[str] = []
    errors: list[str] = []
    traces: list[TracePath] = []

    if part:
        traces.append(trace_part_to_sources(graph, part, limit=limit, strict=strict))
    if page:
        traces.append(trace_page_context(graph, page, limit=limit, strict=strict))
    if ata:
        traces.append(trace_ata_to_sources(graph, ata, limit=limit, strict=strict))
    if vector_page:
        traces.append(trace_vector_candidate_to_graph(
            graph,
            vector_page,
            chunk_id=vector_chunk,
            score=vector_score,
            limit=limit,
            strict=strict,
        ))

    if not traces:
        # Default to a useful known/current part if present, otherwise first part.
        fallback = graph.find_part("120-37313-001") or graph.find_one("part")
        if fallback:
            part_number = fallback.prop("part_number", default=fallback.label)
            traces.append(trace_part_to_sources(graph, str(part_number), limit=limit, strict=strict))
        else:
            errors.append("No part/page/vector-page argument was provided and no part node exists.")

    for trace in traces:
        warnings.extend(trace.warnings)
        errors.extend(trace.errors)

    status = "OK" if not errors and all(trace.status == "OK" for trace in traces) else "NEEDS ATTENTION"
    return TraceabilityReport(
        status=status,
        graph_dir=str(graph.graph_dir),
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        node_type_counts=graph.node_type_counts(),
        edge_type_counts=graph.edge_type_counts(),
        traces=traces,
        warnings=warnings,
        errors=errors,
    )


def trace_part_to_sources(graph: GraphStore, part_number: str, limit: int = 8, strict: bool = False) -> TracePath:
    part = graph.find_part(part_number)
    if not part:
        return TracePath(
            id="part_to_sources",
            description=f"Part -> pages -> source links/context trace for {part_number}.",
            status="NEEDS ATTENTION",
            errors=[f"Part not found in graph: {part_number}"],
        )

    errors: list[str] = []
    warnings: list[str] = []
    steps = [_step("Start part", part)]

    name_nodes = _neighbors(graph, part.id, "HAS_NOMENCLATURE", "nomenclature")
    if name_nodes:
        steps.append(_step("Canonical nomenclature", name_nodes[0], "HAS_NOMENCLATURE"))
    elif strict:
        errors.append(f"Part has no HAS_NOMENCLATURE edge: {part.id}")
    else:
        warnings.append(f"Part has no HAS_NOMENCLATURE edge: {part.id}")

    pages = _part_pages(graph, part)
    pages_with_source = 0
    pages_with_context = 0
    sample_count = 0
    for page in pages[:limit]:
        sample_count += 1
        steps.append(_step(f"Appearance page {sample_count}", page, "APPEARS_ON"))
        sources = _neighbors(graph, page.id, "HAS_SOURCE_LINK", "source_link")
        contexts = _neighbors(graph, page.id, "HAS_CONTEXT", "page_context")
        doc = _first_neighbor_any(graph, page.id, ("BELONGS_TO_DOCUMENT",), "document")
        ata = _first_neighbor_any(graph, page.id, ("BELONGS_TO_ATA",), "ata_section")
        if doc:
            steps.append(_step(f"Page {sample_count} document", doc, "BELONGS_TO_DOCUMENT"))
        if ata:
            steps.append(_step(f"Page {sample_count} ATA", ata, "BELONGS_TO_ATA"))
        if sources:
            pages_with_source += 1
            steps.append(_step(f"Page {sample_count} source link", sources[0], "HAS_SOURCE_LINK"))
        else:
            msg = f"Page missing source link: {page.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)
        if contexts:
            pages_with_context += 1
            steps.append(_step(
                f"Page {sample_count} AI context",
                contexts[0],
                "HAS_CONTEXT",
                {"score": context_score(contexts[0]), "summary": _context_summary(contexts[0])},
            ))
        else:
            warnings.append(f"Page has no AI context yet: {page.id}")

    if not pages:
        errors.append(f"Part has no APPEARS_ON/HAS_MENTION page trace: {part.id}")

    summary = {
        "part_number": part_number,
        "part_node": part.id,
        "nomenclature": name_nodes[0].label if name_nodes else None,
        "total_pages_found": len(pages),
        "sample_pages_shown": sample_count,
        "sample_pages_with_source_links": pages_with_source,
        "sample_pages_with_context": pages_with_context,
    }
    status = "OK" if not errors else "NEEDS ATTENTION"
    return TracePath(
        id="part_to_sources",
        description="Trace a part to its pages, source links, and AI page context.",
        status=status,
        steps=steps,
        summary=summary,
        warnings=warnings,
        errors=errors,
    )


def trace_page_context(graph: GraphStore, page_id: str, limit: int = 8, strict: bool = False) -> TracePath:
    page = graph.find_page(page_id)
    if not page:
        return TracePath(
            id="page_trace",
            description=f"Page -> document/ATA/parts/source/context trace for {page_id}.",
            status="NEEDS ATTENTION",
            errors=[f"Page not found in graph: {page_id}"],
        )
    errors: list[str] = []
    warnings: list[str] = []
    steps = [_step("Start page", page)]

    doc = _first_neighbor_any(graph, page.id, ("BELONGS_TO_DOCUMENT",), "document")
    ata = _first_neighbor_any(graph, page.id, ("BELONGS_TO_ATA",), "ata_section")
    source = _first_neighbor_any(graph, page.id, ("HAS_SOURCE_LINK",), "source_link")
    context = _first_neighbor_any(graph, page.id, ("HAS_CONTEXT",), "page_context")
    parts = _neighbors(graph, page.id, "MENTIONS_PART", "part")[:limit]

    if doc:
        steps.append(_step("Document", doc, "BELONGS_TO_DOCUMENT"))
    elif strict:
        errors.append(f"Page has no document trace: {page.id}")
    if ata:
        steps.append(_step("ATA section", ata, "BELONGS_TO_ATA"))
    elif strict:
        errors.append(f"Page has no ATA trace: {page.id}")
    if source:
        steps.append(_step("Source link", source, "HAS_SOURCE_LINK"))
    elif strict:
        errors.append(f"Page has no source link trace: {page.id}")
    if context:
        steps.append(_step("AI context", context, "HAS_CONTEXT", {"score": context_score(context), "summary": _context_summary(context)}))
    else:
        warnings.append(f"Page has no AI context yet: {page.id}")

    for idx, part in enumerate(parts, start=1):
        steps.append(_step(f"Mentioned part {idx}", part, "MENTIONS_PART"))
        names = _neighbors(graph, part.id, "HAS_NOMENCLATURE", "nomenclature")
        if names:
            steps.append(_step(f"Part {idx} nomenclature", names[0], "HAS_NOMENCLATURE"))

    summary = {
        "page_id": page_id,
        "page_node": page.id,
        "document": doc.label if doc else None,
        "ata": ata.label if ata else None,
        "source_link_present": bool(source),
        "context_present": bool(context),
        "context_score": context_score(context) if context else 0.0,
        "parts_sampled": len(parts),
    }
    return TracePath(
        id="page_trace",
        description="Trace a page to document, ATA, parts, nomenclature, source, and AI context.",
        status="OK" if not errors else "NEEDS ATTENTION",
        steps=steps,
        summary=summary,
        warnings=warnings,
        errors=errors,
    )



def trace_ata_to_sources(graph: GraphStore, ata_code: str, limit: int = 8, strict: bool = False) -> TracePath:
    """Trace an ATA section to pages, source links, AI context, and sampled parts."""
    ata = graph.find_one("ata_section", ata_code)
    if not ata:
        return TracePath(
            id="ata_to_sources",
            description=f"ATA -> pages -> source links/context trace for {ata_code}.",
            status="NEEDS ATTENTION",
            errors=[f"ATA section not found in graph: {ata_code}"],
        )

    errors: list[str] = []
    warnings: list[str] = []
    steps = [_step("Start ATA section", ata)]

    documents = _incoming_neighbors(graph, ata.id, "HAS_ATA_SECTION", "document")
    if documents:
        steps.append(_step("Owning document", documents[0], "HAS_ATA_SECTION"))
    elif strict:
        errors.append(f"ATA section has no owning document: {ata.id}")

    pages = _ata_pages(graph, ata)
    all_parts: dict[str, GraphNode] = {}
    pages_with_source = 0
    pages_with_context = 0
    sample_count = 0
    for page in pages[:limit]:
        sample_count += 1
        steps.append(_step(f"ATA page {sample_count}", page, "CONTAINS_PAGE"))
        sources = _neighbors(graph, page.id, "HAS_SOURCE_LINK", "source_link")
        contexts = _neighbors(graph, page.id, "HAS_CONTEXT", "page_context")
        parts = _neighbors(graph, page.id, "MENTIONS_PART", "part")
        for part_node in parts:
            all_parts[part_node.id] = part_node
        if sources:
            pages_with_source += 1
            steps.append(_step(f"Page {sample_count} source link", sources[0], "HAS_SOURCE_LINK"))
        else:
            msg = f"ATA page missing source link: {page.id}"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)
        if contexts:
            pages_with_context += 1
            steps.append(_step(
                f"Page {sample_count} AI context",
                contexts[0],
                "HAS_CONTEXT",
                {"score": context_score(contexts[0]), "summary": _context_summary(contexts[0])},
            ))
        else:
            warnings.append(f"ATA page has no AI context yet: {page.id}")
        for idx, part_node in enumerate(parts[:3], start=1):
            steps.append(_step(f"Page {sample_count} mentioned part {idx}", part_node, "MENTIONS_PART"))

    if not pages:
        errors.append(f"ATA section has no CONTAINS_PAGE/BELONGS_TO_ATA trace: {ata.id}")

    # Count all distinct parts in the ATA even if we only show a small page sample.
    for page in pages:
        for part_node in _neighbors(graph, page.id, "MENTIONS_PART", "part"):
            all_parts[part_node.id] = part_node

    summary = {
        "ata_code": ata_code,
        "ata_node": ata.id,
        "document": documents[0].label if documents else None,
        "total_pages_found": len(pages),
        "sample_pages_shown": sample_count,
        "sample_pages_with_source_links": pages_with_source,
        "sample_pages_with_context": pages_with_context,
        "distinct_parts_in_ata": len(all_parts),
    }
    return TracePath(
        id="ata_to_sources",
        description="Trace an ATA section to pages, source links, AI page context, and sampled parts.",
        status="OK" if not errors else "NEEDS ATTENTION",
        steps=steps,
        summary=summary,
        warnings=warnings,
        errors=errors,
    )

def trace_vector_candidate_to_graph(
    graph: GraphStore,
    page_id: str,
    chunk_id: str | None = None,
    score: float | None = None,
    limit: int = 8,
    strict: bool = False,
) -> TracePath:
    """Simulate the production Qdrant -> graph trace using a returned page_id.

    In production, Qdrant should return payloads like {chunk_id, page_id, document_id, ata_code}.
    This function starts from that returned page_id and resolves the graph context.
    """
    trace = trace_page_context(graph, page_id, limit=limit, strict=strict)
    trace.id = "vector_candidate_to_graph"
    trace.description = "Simulated vector result payload page_id -> page -> graph/source/context trace."
    trace.summary = {
        "vector_payload_page_id": page_id,
        "vector_payload_chunk_id": chunk_id,
        "vector_payload_score": score,
        **trace.summary,
    }
    payload_label = f"Qdrant returned page_id={page_id}"
    if chunk_id:
        payload_label += f", chunk_id={chunk_id}"
    if score is not None:
        payload_label += f", score={score}"
    trace.steps.insert(0, TraceStep(
        label="Simulated Qdrant payload",
        node_id=f"vector_payload:{chunk_id or page_id}",
        node_type="vector_payload",
        node_label=payload_label,
        edge_type=None,
        properties={
            "page_id": page_id,
            "chunk_id": chunk_id,
            "score": score,
            "note": "Future Qdrant payload should include chunk_id/page_id so PostgreSQL graph can resolve source context.",
        },
    ))
    return trace


def render_traceability_report(report: TraceabilityReport, max_steps: int = 80) -> str:
    lines: list[str] = []
    lines.append("Document graph traceability")
    lines.append(f"  Status: {report.status}")
    lines.append(f"  Graph dir: {report.graph_dir}")
    lines.append(f"  Nodes: {report.node_count}")
    lines.append(f"  Edges: {report.edge_count}")
    lines.append("")
    for trace in report.traces:
        lines.append(f"Trace: {trace.id}")
        lines.append(f"  Status: {trace.status}")
        lines.append(f"  {trace.description}")
        if trace.summary:
            lines.append("  Summary:")
            for key, value in trace.summary.items():
                lines.append(f"    {key}: {value}")
        lines.append("  Path:")
        for idx, step in enumerate(trace.steps[:max_steps], start=1):
            edge = f" --{step.edge_type}-->" if step.edge_type else ""
            lines.append(f"    {idx}. {step.label}{edge} {step.node_type} | {step.node_id} | {step.node_label}")
            if step.properties:
                for key, value in step.properties.items():
                    if value not in (None, "", [], {}):
                        lines.append(f"       {key}: {value}")
        if len(trace.steps) > max_steps:
            lines.append(f"    ... {len(trace.steps) - max_steps} more steps not shown")
        if trace.warnings:
            lines.append("  Warnings:")
            for warning in trace.warnings[:12]:
                lines.append(f"    - {warning}")
        if trace.errors:
            lines.append("  Errors:")
            for error in trace.errors[:12]:
                lines.append(f"    - {error}")
        lines.append("")

    if report.errors:
        lines.append("Report errors:")
        for error in report.errors[:12]:
            lines.append(f"  - {error}")
    if report.warnings and not report.errors:
        lines.append("Report warnings:")
        for warning in report.warnings[:12]:
            lines.append(f"  - {warning}")
    return "\n".join(lines).rstrip()


def _neighbors(graph: GraphStore, node_id: str, edge_type: str, node_type: str | None = None) -> list[GraphNode]:
    result = [node for _, node in graph.neighbors(node_id, edge_type) if node_type is None or node.type == node_type]
    return sorted(result, key=lambda n: n.id)


def _first_neighbor_any(graph: GraphStore, node_id: str, edge_types: tuple[str, ...], node_type: str | None = None) -> GraphNode | None:
    for edge_type in edge_types:
        nodes = _neighbors(graph, node_id, edge_type, node_type)
        if nodes:
            return nodes[0]
    return None


def _part_pages(graph: GraphStore, part: GraphNode) -> list[GraphNode]:
    pages: list[GraphNode] = []
    seen: set[str] = set()
    for page in _neighbors(graph, part.id, "APPEARS_ON", "page"):
        if page.id not in seen:
            seen.add(page.id)
            pages.append(page)
    # Fallback through mention nodes.
    for mention in _neighbors(graph, part.id, "HAS_MENTION", "part_mention"):
        for page in _neighbors(graph, mention.id, "FOUND_ON", "page"):
            if page.id not in seen:
                seen.add(page.id)
                pages.append(page)
    return sorted(pages, key=lambda n: _page_sort_key(n))



def _incoming_neighbors(graph: GraphStore, node_id: str, edge_type: str, node_type: str | None = None) -> list[GraphNode]:
    result = [node for _, node in graph.neighbors(node_id, edge_type, direction="in") if node_type is None or node.type == node_type]
    return sorted(result, key=lambda n: n.id)


def _ata_pages(graph: GraphStore, ata: GraphNode) -> list[GraphNode]:
    pages: list[GraphNode] = []
    seen: set[str] = set()
    for page in _neighbors(graph, ata.id, "CONTAINS_PAGE", "page"):
        if page.id not in seen:
            seen.add(page.id)
            pages.append(page)
    # Fallback for graph exports that only contain Page -> ATA edges.
    for page in _incoming_neighbors(graph, ata.id, "BELONGS_TO_ATA", "page"):
        if page.id not in seen:
            seen.add(page.id)
            pages.append(page)
    return sorted(pages, key=lambda n: _page_sort_key(n))

def _page_sort_key(page: GraphNode) -> tuple[int, str]:
    label = str(page.prop("page_label", default=page.label))
    digits = "".join(ch for ch in label if ch.isdigit())
    return (int(digits) if digits else 10**9, page.id)


def _step(label: str, node: GraphNode, edge_type: str | None = None, properties: dict[str, Any] | None = None) -> TraceStep:
    return TraceStep(
        label=label,
        edge_type=edge_type,
        node_id=node.id,
        node_type=node.type,
        node_label=node.label,
        properties=properties or {},
    )


def _context_summary(node: GraphNode) -> str:
    value = node.prop("short_summary", "summary", "description", default=node.label)
    return str(value).replace("\n", " ").strip()[:260]
