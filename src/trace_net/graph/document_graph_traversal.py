"""Read-only traversal helpers for the exported document organization graph.

The graph export is intentionally JSON-based for the local MVP.  These helpers
load graph_nodes.json and graph_edges.json and test useful traversal paths such
as:

    Document -> Page -> Part -> Nomenclature, then Page -> PageContext

The code is deliberately defensive about JSON field names so it can survive
small shape changes in the graph exporter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from collections import defaultdict, Counter
from typing import Any, Iterable


NODE_ID_KEYS = ("id", "node_id", "uid")
NODE_TYPE_KEYS = ("type", "node_type", "kind")
NODE_LABEL_KEYS = ("label", "name", "title", "display", "text")
EDGE_SOURCE_KEYS = ("source", "source_id", "from", "from_id", "start", "start_id")
EDGE_TARGET_KEYS = ("target", "target_id", "to", "to_id", "end", "end_id")
EDGE_TYPE_KEYS = ("type", "edge_type", "relationship", "label", "kind")


@dataclass(frozen=True)
class GraphNode:
    id: str
    type: str
    label: str
    raw: dict[str, Any] = field(default_factory=dict)

    def prop(self, *names: str, default: Any = None) -> Any:
        for name in names:
            if name in self.raw and self.raw[name] not in (None, ""):
                return self.raw[name]
            props = self.raw.get("properties")
            if isinstance(props, dict) and props.get(name) not in (None, ""):
                return props[name]
            data = self.raw.get("data")
            if isinstance(data, dict) and data.get(name) not in (None, ""):
                return data[name]
        return default


@dataclass(frozen=True)
class GraphEdge:
    type: str
    source: str
    target: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraversalStep:
    edge_type: str
    node: GraphNode


@dataclass
class TraversalReport:
    status: str
    errors: list[str]
    warnings: list[str]
    graph_dir: str
    node_count: int
    edge_count: int
    node_type_counts: dict[str, int]
    edge_type_counts: dict[str, int]
    document: GraphNode | None
    page: GraphNode | None
    part: GraphNode | None
    nomenclature: GraphNode | None
    context: GraphNode | None
    document_to_page: list[TraversalStep]
    page_to_part: list[TraversalStep]
    part_to_name: list[TraversalStep]
    page_to_context: list[TraversalStep]
    part_to_context_pages: list[dict[str, Any]]

    def to_jsonable(self) -> dict[str, Any]:
        def node_obj(node: GraphNode | None) -> dict[str, Any] | None:
            if node is None:
                return None
            return {"id": node.id, "type": node.type, "label": node.label}

        def step_obj(step: TraversalStep) -> dict[str, Any]:
            return {"edge_type": step.edge_type, "node": node_obj(step.node)}

        return {
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "graph_dir": self.graph_dir,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "node_type_counts": self.node_type_counts,
            "edge_type_counts": self.edge_type_counts,
            "document": node_obj(self.document),
            "page": node_obj(self.page),
            "part": node_obj(self.part),
            "nomenclature": node_obj(self.nomenclature),
            "context": node_obj(self.context),
            "document_to_page": [step_obj(step) for step in self.document_to_page],
            "page_to_part": [step_obj(step) for step in self.page_to_part],
            "part_to_name": [step_obj(step) for step in self.part_to_name],
            "page_to_context": [step_obj(step) for step in self.page_to_context],
            "part_to_context_pages": self.part_to_context_pages,
        }


class GraphStore:
    def __init__(self, nodes: list[GraphNode], edges: list[GraphEdge], graph_dir: Path):
        self.nodes = nodes
        self.edges = edges
        self.graph_dir = graph_dir
        self.nodes_by_id: dict[str, GraphNode] = {node.id: node for node in nodes}
        self.nodes_by_type: dict[str, list[GraphNode]] = defaultdict(list)
        for node in nodes:
            self.nodes_by_type[node.type].append(node)
        self.out_edges: dict[str, list[GraphEdge]] = defaultdict(list)
        self.in_edges: dict[str, list[GraphEdge]] = defaultdict(list)
        for edge in edges:
            self.out_edges[edge.source].append(edge)
            self.in_edges[edge.target].append(edge)

    @classmethod
    def load(cls, graph_dir: str | Path = "local_data/organization/graph") -> "GraphStore":
        graph_dir = Path(graph_dir)
        nodes_path = graph_dir / "graph_nodes.json"
        edges_path = graph_dir / "graph_edges.json"
        if not nodes_path.exists():
            raise FileNotFoundError(f"missing graph nodes file: {nodes_path}")
        if not edges_path.exists():
            raise FileNotFoundError(f"missing graph edges file: {edges_path}")
        nodes_raw = _load_json_list(nodes_path)
        edges_raw = _load_json_list(edges_path)
        nodes = [_parse_node(row) for row in nodes_raw]
        edges = [_parse_edge(row) for row in edges_raw]
        return cls(nodes, edges, graph_dir)

    def node_type_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(node.type for node in self.nodes).items()))

    def edge_type_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(edge.type for edge in self.edges).items()))

    def neighbors(self, node_id: str, edge_type: str | Iterable[str] | None = None, direction: str = "out") -> list[tuple[GraphEdge, GraphNode]]:
        allowed = None
        if isinstance(edge_type, str):
            allowed = {edge_type}
        elif edge_type is not None:
            allowed = set(edge_type)
        edges = self.out_edges.get(node_id, []) if direction == "out" else self.in_edges.get(node_id, [])
        result: list[tuple[GraphEdge, GraphNode]] = []
        for edge in edges:
            if allowed is not None and edge.type not in allowed:
                continue
            other_id = edge.target if direction == "out" else edge.source
            other = self.nodes_by_id.get(other_id)
            if other:
                result.append((edge, other))
        return result

    def find_one(self, node_type: str, query: str | None = None) -> GraphNode | None:
        candidates = self.nodes_by_type.get(node_type, [])
        if not candidates:
            return None
        if query is None:
            return sorted(candidates, key=lambda n: n.id)[0]
        norm_query = _norm_text(query)
        for node in candidates:
            fields = [node.id, node.label]
            fields.extend(str(node.prop(name, default="")) for name in (
                "part_number", "page_id", "manual", "manual_id", "document_id", "title", "publication_number", "ata", "ata_code"
            ))
            if any(norm_query == _norm_text(field) or norm_query in _norm_text(field) for field in fields if field):
                return node
        return None

    def find_part(self, part_number: str | None = None) -> GraphNode | None:
        if part_number:
            return self.find_one("part", part_number)
        return self.find_one("part")

    def find_page(self, page_id: str | None = None) -> GraphNode | None:
        if page_id:
            return self.find_one("page", page_id)
        return self.find_one("page")


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("nodes", "edges", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    raise ValueError(f"expected JSON list or wrapper object in {path}")


def _first(row: dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
        props = row.get("properties")
        if isinstance(props, dict) and props.get(key) not in (None, ""):
            return props[key]
        data = row.get("data")
        if isinstance(data, dict) and data.get(key) not in (None, ""):
            return data[key]
    return default


def _parse_node(row: dict[str, Any]) -> GraphNode:
    node_id = str(_first(row, NODE_ID_KEYS, ""))
    node_type = str(_first(row, NODE_TYPE_KEYS, "unknown"))
    label = str(_first(row, NODE_LABEL_KEYS, node_id))
    if not node_id:
        raise ValueError(f"node missing id: {row}")
    return GraphNode(id=node_id, type=node_type, label=label, raw=row)


def _parse_edge(row: dict[str, Any]) -> GraphEdge:
    source = str(_first(row, EDGE_SOURCE_KEYS, ""))
    target = str(_first(row, EDGE_TARGET_KEYS, ""))
    edge_type = str(_first(row, EDGE_TYPE_KEYS, "UNKNOWN"))
    if not source or not target:
        raise ValueError(f"edge missing source/target: {row}")
    return GraphEdge(type=edge_type, source=source, target=target, raw=row)


def _norm_text(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def context_score(node: GraphNode | None) -> float:
    if node is None:
        return 0.0
    confidence = str(node.prop("confidence", default="")).lower()
    warning = bool(node.prop("warning", "has_warning", default=False))
    error = bool(node.prop("error", "has_error", default=False))
    base = {"high": 0.90, "medium": 0.65, "low": 0.35}.get(confidence, 0.50)
    if warning:
        base -= 0.20
    if error:
        base -= 0.30
    return max(0.0, round(base, 2))


def build_traversal_report(
    graph_dir: str | Path = "local_data/organization/graph",
    document: str | None = None,
    page: str | None = None,
    part: str | None = None,
    limit: int = 5,
    strict: bool = False,
) -> TraversalReport:
    graph = GraphStore.load(graph_dir)
    errors: list[str] = []
    warnings: list[str] = []

    doc_node = graph.find_one("document", document)
    if doc_node is None:
        errors.append("No document node found.")

    page_node = graph.find_page(page) if page else None
    part_node = graph.find_part(part) if part else None

    # If no explicit page is provided, choose a useful page from the document:
    # prefer pages that mention the selected part and have page context.
    doc_to_page_steps: list[TraversalStep] = []
    if doc_node:
        page_candidates = [n for _, n in graph.neighbors(doc_node.id, "HAS_PAGE") if n.type == "page"]
        if not page_candidates:
            # Some exports may only have reverse links.
            page_candidates = [n for _, n in graph.neighbors(doc_node.id, "BELONGS_TO_DOCUMENT", direction="in") if n.type == "page"]
        if not page_node:
            page_node = _select_best_page(graph, page_candidates, part_node)
        if page_node:
            edge_type = _find_edge_type(graph, doc_node.id, page_node.id, preferred="HAS_PAGE") or "HAS_PAGE"
            doc_to_page_steps = [TraversalStep(edge_type=edge_type, node=page_node)]
        else:
            errors.append("No page found under the selected document.")

    # If a part was not explicitly provided, use a part from the selected page.
    page_to_part_steps: list[TraversalStep] = []
    if page_node:
        page_parts = [n for _, n in graph.neighbors(page_node.id, "MENTIONS_PART") if n.type == "part"]
        if part_node:
            # Make sure selected part is represented in this page.  If not, choose a page where it is represented.
            if page_parts and all(n.id != part_node.id for n in page_parts):
                better_page = _first_part_page_with_context(graph, part_node)
                if better_page:
                    page_node = better_page
                    if doc_node:
                        edge_type = _find_edge_type(graph, doc_node.id, page_node.id, preferred="HAS_PAGE") or "HAS_PAGE"
                        doc_to_page_steps = [TraversalStep(edge_type=edge_type, node=page_node)]
                    page_parts = [n for _, n in graph.neighbors(page_node.id, "MENTIONS_PART") if n.type == "part"]
            page_to_part_steps = [TraversalStep(edge_type="MENTIONS_PART", node=part_node)]
        elif page_parts:
            part_node = sorted(page_parts, key=lambda n: n.label)[0]
            page_to_part_steps = [TraversalStep(edge_type="MENTIONS_PART", node=part_node)]
        else:
            errors.append(f"Selected page has no MENTIONS_PART edges: {page_node.id}")

    part_to_name_steps: list[TraversalStep] = []
    nomenclature_node = None
    if part_node:
        names = [n for _, n in graph.neighbors(part_node.id, "HAS_NOMENCLATURE") if n.type == "nomenclature"]
        if names:
            nomenclature_node = sorted(names, key=lambda n: n.label)[0]
            part_to_name_steps = [TraversalStep(edge_type="HAS_NOMENCLATURE", node=nomenclature_node)]
        else:
            warnings.append(f"Selected part has no HAS_NOMENCLATURE edge: {part_node.id}")

    page_to_context_steps: list[TraversalStep] = []
    context_node = None
    if page_node:
        contexts = [n for _, n in graph.neighbors(page_node.id, "HAS_CONTEXT") if n.type == "page_context"]
        if not contexts:
            contexts = [n for _, n in graph.neighbors(page_node.id, "SUMMARIZES", direction="in") if n.type == "page_context"]
        if contexts:
            context_node = sorted(contexts, key=lambda n: n.id)[0]
            page_to_context_steps = [TraversalStep(edge_type="HAS_CONTEXT", node=context_node)]
        else:
            warnings.append(f"Selected page has no page context yet: {page_node.id}")

    part_to_context_pages = []
    if part_node:
        seen_pages: set[str] = set()
        for edge, candidate_page in graph.neighbors(part_node.id, "APPEARS_ON"):
            if candidate_page.type != "page" or candidate_page.id in seen_pages:
                continue
            seen_pages.add(candidate_page.id)
            contexts = [n for _, n in graph.neighbors(candidate_page.id, "HAS_CONTEXT") if n.type == "page_context"]
            source_links = [n for _, n in graph.neighbors(candidate_page.id, "HAS_SOURCE_LINK") if n.type == "source_link"]
            part_to_context_pages.append({
                "page_id": candidate_page.id,
                "page_label": candidate_page.prop("page_label", "label", default=candidate_page.label),
                "edge_type": edge.type,
                "has_context": bool(contexts),
                "context_id": contexts[0].id if contexts else None,
                "context_summary": _context_summary(contexts[0]) if contexts else None,
                "context_score": context_score(contexts[0]) if contexts else 0.0,
                "has_source_link": bool(source_links),
                "source_label": source_links[0].label if source_links else None,
            })
            if len(part_to_context_pages) >= limit:
                break
        if not part_to_context_pages:
            warnings.append(f"Selected part has no APPEARS_ON pages: {part_node.id}")

    if strict:
        if doc_node is None:
            errors.append("Strict check failed: document missing.")
        if page_node is None:
            errors.append("Strict check failed: page missing.")
        if part_node is None:
            errors.append("Strict check failed: part missing.")
        if nomenclature_node is None:
            errors.append("Strict check failed: nomenclature missing.")
        if context_node is None:
            errors.append("Strict check failed: page context missing for selected page.")

    return TraversalReport(
        status="OK" if not errors else "NEEDS ATTENTION",
        errors=errors,
        warnings=warnings,
        graph_dir=str(graph.graph_dir),
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        node_type_counts=graph.node_type_counts(),
        edge_type_counts=graph.edge_type_counts(),
        document=doc_node,
        page=page_node,
        part=part_node,
        nomenclature=nomenclature_node,
        context=context_node,
        document_to_page=doc_to_page_steps,
        page_to_part=page_to_part_steps,
        part_to_name=part_to_name_steps,
        page_to_context=page_to_context_steps,
        part_to_context_pages=part_to_context_pages,
    )


def _select_best_page(graph: GraphStore, pages: list[GraphNode], part_node: GraphNode | None) -> GraphNode | None:
    if not pages:
        return None
    if part_node:
        page = _first_part_page_with_context(graph, part_node)
        if page:
            return page
    def score(page: GraphNode) -> tuple[int, str]:
        has_context = bool(graph.neighbors(page.id, "HAS_CONTEXT"))
        has_part = bool(graph.neighbors(page.id, "MENTIONS_PART"))
        return (int(has_context) + int(has_part), page.id)
    return sorted(pages, key=score, reverse=True)[0]


def _first_part_page_with_context(graph: GraphStore, part_node: GraphNode) -> GraphNode | None:
    pages = [n for _, n in graph.neighbors(part_node.id, "APPEARS_ON") if n.type == "page"]
    if not pages:
        # Fallback: part -> mention -> page.
        for _, mention in graph.neighbors(part_node.id, "HAS_MENTION"):
            for _, page in graph.neighbors(mention.id, "FOUND_ON"):
                if page.type == "page":
                    pages.append(page)
    if not pages:
        return None
    with_context = [p for p in pages if graph.neighbors(p.id, "HAS_CONTEXT")]
    return sorted(with_context or pages, key=lambda n: n.id)[0]


def _find_edge_type(graph: GraphStore, source: str, target: str, preferred: str | None = None) -> str | None:
    matches = [edge.type for edge in graph.out_edges.get(source, []) if edge.target == target]
    if preferred in matches:
        return preferred
    return matches[0] if matches else None


def _context_summary(node: GraphNode) -> str:
    value = node.prop("short_summary", "summary", "description", default=node.label)
    text = str(value).replace("\n", " ").strip()
    return text[:240]


def render_report(report: TraversalReport) -> str:
    lines: list[str] = []
    lines.append("Document graph traversal test")
    lines.append(f"  Status: {report.status}")
    lines.append(f"  Graph dir: {report.graph_dir}")
    lines.append(f"  Nodes: {report.node_count}")
    lines.append(f"  Edges: {report.edge_count}")
    lines.append("")
    lines.append("Selected traversal:")
    _render_node(lines, "Document", report.document)
    for step in report.document_to_page:
        _render_step(lines, step)
    for step in report.page_to_part:
        _render_step(lines, step)
    for step in report.part_to_name:
        _render_step(lines, step)
    if report.page_to_context:
        lines.append("  Back to AI context from the selected page:")
        for step in report.page_to_context:
            _render_step(lines, step)
            lines.append(f"      score={context_score(step.node):.2f}")
            lines.append(f"      summary={_context_summary(step.node)}")
    lines.append("")
    if report.part_to_context_pages:
        lines.append("Part -> pages -> AI context/source sample:")
        for idx, row in enumerate(report.part_to_context_pages, start=1):
            lines.append(
                f"  {idx}. page={row['page_id']} label={row.get('page_label')} "
                f"context={row['has_context']} score={row['context_score']:.2f} source_link={row['has_source_link']}"
            )
            if row.get("context_summary"):
                lines.append(f"     context: {row['context_summary']}")
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in report.warnings:
            lines.append(f"  - {warning}")
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for error in report.errors:
            lines.append(f"  - {error}")
    return "\n".join(lines)


def _render_node(lines: list[str], label: str, node: GraphNode | None) -> None:
    if node is None:
        lines.append(f"  {label}: -")
    else:
        lines.append(f"  {label}: {node.type} | {node.id} | {node.label}")


def _render_step(lines: list[str], step: TraversalStep) -> None:
    lines.append(f"    --{step.edge_type}--> {step.node.type} | {step.node.id} | {step.node.label}")



def _props(raw: dict[str, Any]) -> dict[str, Any]:
    """Return the most common nested property dictionary for graph JSON nodes.

    Graph exporter revisions have used both top-level node fields and nested
    properties/data dictionaries.  Traversal code should read all of them so
    old graph exports and new graph exports remain compatible.
    """
    for key in ("properties", "data", "payload"):
        value = raw.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _node_prop(node: GraphNode | None, *names: str, default: Any = None) -> Any:
    """Compatibility helper for newer traversal/report code.

    Older code calls GraphNode.prop directly; newer trace helpers call
    _node_prop.  Keep both paths supported so user-query tests and traceability
    tools can share the same graph reader.
    """
    if node is None:
        return default
    value = node.prop(*names, default=default)
    if value not in (None, ""):
        return value
    props = _props(node.raw)
    for name in names:
        if props.get(name) not in (None, ""):
            return props[name]
    return default


def _node_text(node: GraphNode | None) -> str:
    if node is None:
        return ""
    value = _node_prop(
        node,
        "part_number",
        "nomenclature",
        "short_summary",
        "summary",
        "page_id",
        "document_id",
        "ata_code",
        "text",
        "name",
        "title",
        "label",
        default=node.label,
    )
    return str(value or node.label or "")

def _context_summary(node: GraphNode) -> str:
    value = _node_prop(node, "short_summary", "summary", "description", "context", "text", default=node.label)
    text = str(value or node.label).replace("\n", " ").strip()
    return text[:240]


def _context_role(node: GraphNode) -> str:
    return _node_prop(node, "role", "page_role") or "-"


def _context_confidence(node: GraphNode) -> str:
    return _node_prop(node, "confidence") or "-"


def choose_page_for_document(
    graph: GraphData,
    document: GraphNode,
    page_query: str | None = None,
    part_query: str | None = None,
    require_context: bool = True,
) -> GraphNode | None:
    pages = follow(graph, document, "HAS_PAGE", "page")
    if page_query:
        query_norm = _norm(page_query)
        for page in pages:
            page_fields = [_node_text(page), _node_prop(page, "page_id"), _node_prop(page, "page_label")]
            if any(query_norm in _norm(field) for field in page_fields if field):
                return page
        return None

    part_norm = _norm(part_query or "")
    scored: list[tuple[int, GraphNode]] = []
    for page in pages:
        parts = follow(graph, page, "MENTIONS_PART", "part")
        contexts = follow(graph, page, "HAS_CONTEXT", "page_context")
        if part_norm and not any(part_norm in _norm(_node_text(part)) for part in parts):
            continue
        score = 0
        if parts:
            score += 10
        if contexts:
            score += 10
        if require_context and not contexts:
            score -= 100
        scored.append((score, page))
    if not scored:
        return None
    best_score = max(score for score, _ in scored)
    best = [page for score, page in scored if score == best_score]
    return _sort_pages(best)[0]


def choose_part_for_page(graph: GraphData, page: GraphNode, part_query: str | None = None) -> GraphNode | None:
    parts = follow(graph, page, "MENTIONS_PART", "part")
    if not parts:
        return None
    if part_query:
        query_norm = _norm(part_query)
        for part in parts:
            if query_norm in _norm(_node_text(part)):
                return part
        return None
    return sorted(parts, key=lambda n: _part_number(n))[0]


def trace_doc_page_part_name_context(
    graph: GraphData,
    document_query: str | None = None,
    page_query: str | None = None,
    part_query: str | None = None,
) -> dict[str, Any]:
    """Trace Document -> Page -> Part -> Nomenclature -> PageContext.

    The PageContext can be reached from the selected Page directly. If the user
    supplies a part, the function also verifies that the selected part appears
    back on the selected page before resolving context, which proves the graph can
    go across the part/page relationship without starting over at the document.
    """
    document = find_node(graph, "document", document_query)
    if not document:
        return {"status": "fail", "errors": ["document not found"]}

    page = choose_page_for_document(graph, document, page_query=page_query, part_query=part_query)
    if not page:
        return {"status": "fail", "errors": ["page not found under selected document"]}

    part = choose_part_for_page(graph, page, part_query=part_query)
    if not part:
        return {"status": "fail", "errors": ["part not found on selected page"]}

    names = follow(graph, part, "HAS_NOMENCLATURE", "nomenclature")
    contexts = follow(graph, page, "HAS_CONTEXT", "page_context")

    errors: list[str] = []
    if not names:
        errors.append("part has no HAS_NOMENCLATURE edge")
    if not contexts:
        errors.append("page has no HAS_CONTEXT edge")
    if not has_edge(graph, document, "HAS_PAGE", page):
        errors.append("document does not have expected HAS_PAGE edge")
    if not has_edge(graph, page, "MENTIONS_PART", part):
        errors.append("page does not have expected MENTIONS_PART edge")
    if not has_edge(graph, part, "APPEARS_ON", page):
        # This reverse edge is helpful but older exports may not include it. Treat
        # it as a warning rather than a hard failure.
        reverse_warning = "part has no APPEARS_ON edge back to selected page"
    else:
        reverse_warning = ""

    first_name = names[0] if names else None
    first_context = contexts[0] if contexts else None
    path = [
        {
            "step": 1,
            "from": document.id,
            "edge": "HAS_PAGE",
            "to": page.id,
            "from_label": document.label,
            "to_label": page.label,
        },
        {
            "step": 2,
            "from": page.id,
            "edge": "MENTIONS_PART",
            "to": part.id,
            "from_label": page.label,
            "to_label": part.label,
        },
    ]
    if first_name:
        path.append(
            {
                "step": 3,
                "from": part.id,
                "edge": "HAS_NOMENCLATURE",
                "to": first_name.id,
                "from_label": part.label,
                "to_label": first_name.label,
            }
        )
    if first_context:
        path.append(
            {
                "step": 4,
                "from": page.id,
                "edge": "HAS_CONTEXT",
                "to": first_context.id,
                "from_label": page.label,
                "to_label": first_context.label,
            }
        )

    result = {
        "status": "ok" if not errors else "fail",
        "errors": errors,
        "warnings": [reverse_warning] if reverse_warning else [],
        "document": _serialize_node(document),
        "page": _serialize_node(page),
        "part": _serialize_node(part),
        "nomenclature": _serialize_node(first_name) if first_name else None,
        "context": _serialize_context(first_context) if first_context else None,
        "path": path,
        "counts": {
            "page_parts": len(follow(graph, page, "MENTIONS_PART", "part")),
            "page_contexts": len(contexts),
            "part_names": len(names),
        },
    }
    return result


def _serialize_node(node: GraphNode | None) -> dict[str, Any] | None:
    if node is None:
        return None
    out = {"id": node.id, "type": node.type, "label": node.label}
    props = _props(node.raw)
    for key in (
        "document_id",
        "page_id",
        "page_label",
        "ata_code",
        "part_number",
        "nomenclature",
        "manual",
        "publication_number",
    ):
        value = node.raw.get(key, props.get(key))
        if value is not None:
            out[key] = value
    return out


def _serialize_context(node: GraphNode | None) -> dict[str, Any] | None:
    if node is None:
        return None
    out = _serialize_node(node) or {}
    out.update(
        {
            "role": _context_role(node),
            "confidence": _context_confidence(node),
            "summary": _context_summary(node),
        }
    )
    topics = _node_prop(node, "topics")
    if topics:
        out["topics"] = topics
    return out


def graph_stats(graph: GraphData) -> dict[str, Any]:
    node_counts: dict[str, int] = {}
    edge_counts: dict[str, int] = {}
    for node in graph.nodes.values():
        node_counts[node.type] = node_counts.get(node.type, 0) + 1
    for edge in graph.edges:
        edge_counts[edge.type] = edge_counts.get(edge.type, 0) + 1
    return {
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "node_types": dict(sorted(node_counts.items())),
        "edge_types": dict(sorted(edge_counts.items())),
    }
