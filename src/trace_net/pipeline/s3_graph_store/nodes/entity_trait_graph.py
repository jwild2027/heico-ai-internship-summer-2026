"""Build an entity-trait graph overlay from the document organization graph.

This module keeps the core document graph clean and adds a separate overlay for
traits, trait assertions, evidence sources, and fast page/part "character cards".

The model is intentionally source-aware:

    Entity -> HAS_TRAIT_ASSERTION -> TraitAssertion -> ASSERTS_TRAIT -> Trait
                                      |
                                      +-> DERIVED_FROM -> EvidenceSource

A shortcut edge is also written:

    Entity -> HAS_TRAIT -> Trait

The shortcut makes browsing and filtering fast, while the assertion node keeps
method/source/confidence metadata so answers can explain why a trait exists.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from typing import Any, Iterable, Mapping

DEFAULT_GRAPH_DIR = "local_data/organization/graph"
DEFAULT_IMAGE_RECOGNITION_AUDIT = (
    "local_data/organization/image_recognition/page_image_recognition_audit.json"
)
DEFAULT_PAGE_VISUAL_OBJECT_AUDIT = "local_data/organization/page_visual_objects_audit.json"
DEFAULT_OUTPUT_DIR = "local_data/organization/entity_traits"

ENTITY_TRAITS_FILE = "entity_traits.json"
TRAIT_GRAPH_NODES_FILE = "trait_graph_nodes.json"
TRAIT_GRAPH_EDGES_FILE = "trait_graph_edges.json"
PAGE_CHARACTER_CARDS_FILE = "page_character_cards.json"
PART_CHARACTER_CARDS_FILE = "part_character_cards.json"
TRAIT_GRAPH_SUMMARY_FILE = "trait_graph_summary.json"


@dataclass(frozen=True)
class EntityTraitOverlayResult:
    """In-memory result returned by the trait-overlay builder."""

    status: str
    assertions: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    page_cards: list[dict[str, Any]]
    part_cards: list[dict[str, Any]]
    summary: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def _load_json(path: str | Path) -> Any:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: str | Path, data: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(payload: Any, *keys: str) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for key in ("items", "records", "pages", "nodes", "edges", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _slug(value: Any) -> str:
    text = _text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text or "unknown"


def _edge_id(edge_type: str, source: str, target: str) -> str:
    return f"edge:{_slug(edge_type)}:{_slug(source)}:{_slug(target)}"


def _node_id(node: Mapping[str, Any]) -> str:
    return _text(node.get("id") or node.get("node_id") or node.get("key"))


def _node_type(node: Mapping[str, Any]) -> str:
    return _text(node.get("type") or node.get("node_type") or node.get("kind")).lower()


def _node_label(node: Mapping[str, Any]) -> str:
    props = _as_mapping(node.get("properties"))
    for source in (node, props):
        for key in (
            "label",
            "name",
            "title",
            "part_number",
            "page_id",
            "ata_code",
            "short_summary",
        ):
            value = source.get(key)
            if value not in (None, "", [], {}):
                return _text(value)
    return _node_id(node)


def _edge_type(edge: Mapping[str, Any]) -> str:
    return _text(edge.get("type") or edge.get("edge_type") or edge.get("relationship")).upper()


def _edge_source(edge: Mapping[str, Any]) -> str:
    return _text(edge.get("from") or edge.get("source") or edge.get("from_id") or edge.get("src"))


def _edge_target(edge: Mapping[str, Any]) -> str:
    return _text(edge.get("to") or edge.get("target") or edge.get("to_id") or edge.get("dst"))


def _prop(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    props = _as_mapping(mapping.get("properties"))
    for source in (mapping, props):
        for key in keys:
            if key in source and source.get(key) not in (None, "", [], {}):
                return source.get(key)
    return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "ok"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return default


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                text = _text(
                    item.get("part_number")
                    or item.get("topic")
                    or item.get("name")
                    or item.get("label")
                    or item.get("value")
                )
            else:
                text = _text(item)
            if text and text not in out:
                out.append(text)
        return out
    if isinstance(value, str):
        return list(dict.fromkeys([x.strip() for x in re.split(r"[,;]\s*", value) if x.strip()]))
    return []


def _clean_trait_value(value: Any) -> str:
    text = _text(value).lower()
    text = re.sub(r"\s+", "_", text)
    return text.strip("_")


def _normalize_page_node_id(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    if text.startswith("page:"):
        return text
    return f"page:{_slug(text)}"


def _normalize_part(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", _text(value).upper()).strip("_")


class GraphView:
    """Small tolerant index over graph node/edge JSON."""

    def __init__(self, nodes: Iterable[Mapping[str, Any]], edges: Iterable[Mapping[str, Any]]) -> None:
        self.nodes = [dict(node) for node in nodes if isinstance(node, Mapping)]
        self.edges = [dict(edge) for edge in edges if isinstance(edge, Mapping)]
        self.node_by_id = {_node_id(node): node for node in self.nodes if _node_id(node)}
        self.out_edges: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        self.in_edges: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for edge in self.edges:
            source = _edge_source(edge)
            target = _edge_target(edge)
            if source:
                self.out_edges[source].append(edge)
            if target:
                self.in_edges[target].append(edge)

    def nodes_of_type(self, node_type: str) -> list[Mapping[str, Any]]:
        target = node_type.lower()
        return [node for node in self.nodes if _node_type(node) == target]

    def neighbors(self, node_id: str, edge_type: str) -> list[Mapping[str, Any]]:
        target_type = edge_type.upper()
        out: list[Mapping[str, Any]] = []
        for edge in self.out_edges.get(node_id, []):
            if _edge_type(edge) == target_type:
                node = self.node_by_id.get(_edge_target(edge))
                if node is not None:
                    out.append(node)
        return out

    def has_edge(self, node_id: str, edge_type: str) -> bool:
        target_type = edge_type.upper()
        return any(_edge_type(edge) == target_type for edge in self.out_edges.get(node_id, []))

    def first_neighbor(self, node_id: str, edge_type: str) -> Mapping[str, Any] | None:
        neighbors = self.neighbors(node_id, edge_type)
        return neighbors[0] if neighbors else None


def load_document_graph(graph_dir: str | Path = DEFAULT_GRAPH_DIR) -> GraphView:
    root = Path(graph_dir)
    nodes_payload = _load_json(root / "graph_nodes.json")
    edges_payload = _load_json(root / "graph_edges.json")
    nodes = _as_list(nodes_payload, "nodes", "graph_nodes")
    edges = _as_list(edges_payload, "edges", "graph_edges")
    return GraphView(nodes, edges)


def _load_audit_records(path: str | Path | None) -> tuple[list[Mapping[str, Any]], bool]:
    if not path:
        return [], False
    payload = _load_json(path)
    if payload is None:
        return [], False
    records = _as_list(
        payload,
        "records",
        "pages",
        "page_records",
        "results",
        "items",
        "image_records",
        "visual_records",
    )
    return [record for record in records if isinstance(record, Mapping)], True


def _page_id_from_record(record: Mapping[str, Any]) -> str:
    value = _prop(
        record,
        "page_node_id",
        "page_graph_id",
        "page_id",
        "page",
        "id",
        "source_page_id",
        "document_page_id",
        default="",
    )
    text = _text(value)
    if text.startswith("page:"):
        return text
    return text


def _records_by_page(
    records: Iterable[Mapping[str, Any]],
    page_id_to_node_id: Mapping[str, str],
) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for record in records:
        raw = _page_id_from_record(record)
        if not raw:
            continue
        node_id = raw if raw.startswith("page:") else page_id_to_node_id.get(raw)
        if not node_id:
            node_id = _normalize_page_node_id(raw)
        out[node_id] = record
    return out


def _add_node(
    nodes: dict[str, dict[str, Any]],
    node_id: str,
    node_type: str,
    label: str,
    properties: Mapping[str, Any] | None = None,
) -> None:
    clean_properties = {k: v for k, v in dict(properties or {}).items() if v not in (None, "", [], {})}
    if node_id in nodes:
        nodes[node_id].setdefault("properties", {}).update(clean_properties)
        if label and not nodes[node_id].get("label"):
            nodes[node_id]["label"] = label
        return
    nodes[node_id] = {
        "id": node_id,
        "type": node_type,
        "label": label or node_id,
        "properties": clean_properties,
    }


def _add_edge(
    edges: dict[str, dict[str, Any]],
    edge_type: str,
    source: str,
    target: str,
    properties: Mapping[str, Any] | None = None,
) -> None:
    if not source or not target or source == target:
        return
    edge_id = _edge_id(edge_type, source, target)
    clean_properties = {k: v for k, v in dict(properties or {}).items() if v not in (None, "", [], {})}
    if edge_id in edges:
        edges[edge_id].setdefault("properties", {}).update(clean_properties)
        return
    edges[edge_id] = {
        "id": edge_id,
        "type": edge_type,
        "from": source,
        "to": target,
        "properties": clean_properties,
    }


class TraitOverlayBuilder:
    def __init__(self, graph: GraphView) -> None:
        self.graph = graph
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.assertions: dict[str, dict[str, Any]] = {}
        self.traits_by_entity: dict[str, set[str]] = defaultdict(set)
        self.assertions_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add_trait(
        self,
        entity: Mapping[str, Any],
        trait_key: str,
        trait_value: Any,
        *,
        trait_type: str = "general",
        source: str = "document_graph",
        source_artifact: str = "graph_nodes.json",
        method: str = "direct",
        confidence: float | None = None,
        scope: str = "direct",
        properties: Mapping[str, Any] | None = None,
        supports: Iterable[tuple[str, str, str]] | None = None,
    ) -> dict[str, Any] | None:
        entity_id = _node_id(entity)
        entity_type = _node_type(entity)
        clean_key = _clean_trait_value(trait_key)
        clean_value = _clean_trait_value(trait_value)
        if not entity_id or not clean_key or not clean_value:
            return None

        trait_id = f"trait:{_slug(trait_type)}:{_slug(clean_key)}:{_slug(clean_value)}"
        evidence_label = source_artifact or source or method or "unknown"
        evidence_id = f"evidence_source:{_slug(evidence_label)}"
        assertion_id = (
            f"trait_assertion:{_slug(entity_id)}:{_slug(trait_type)}:"
            f"{_slug(clean_key)}:{_slug(clean_value)}:{_slug(source)}:{_slug(scope)}"
        )

        _add_node(
            self.nodes,
            trait_id,
            "trait",
            f"{clean_key}={clean_value}",
            {
                "trait_key": clean_key,
                "trait_value": clean_value,
                "trait_type": trait_type,
            },
        )
        _add_node(
            self.nodes,
            evidence_id,
            "evidence_source",
            evidence_label,
            {
                "source": source,
                "source_artifact": source_artifact,
                "method": method,
            },
        )
        assertion_properties = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "trait_id": trait_id,
            "trait_key": clean_key,
            "trait_value": clean_value,
            "trait_type": trait_type,
            "source": source,
            "source_artifact": source_artifact,
            "method": method,
            "scope": scope,
            "confidence": confidence,
            "evidence_id": evidence_id,
        }
        assertion_properties.update(dict(properties or {}))
        _add_node(
            self.nodes,
            assertion_id,
            "trait_assertion",
            f"{entity_id} has {clean_key}={clean_value}",
            assertion_properties,
        )
        _add_edge(self.edges, "HAS_TRAIT_ASSERTION", entity_id, assertion_id)
        _add_edge(self.edges, "ASSERTS_TRAIT", assertion_id, trait_id)
        _add_edge(self.edges, "DERIVED_FROM", assertion_id, evidence_id)
        _add_edge(self.edges, "HAS_TRAIT", entity_id, trait_id, {"via": assertion_id})

        for support_type, support_key, support_value in supports or []:
            support_trait_id = (
                f"trait:{_slug(support_type)}:{_slug(_clean_trait_value(support_key))}:"
                f"{_slug(_clean_trait_value(support_value))}"
            )
            if support_trait_id in self.nodes:
                _add_edge(self.edges, "SUPPORTS", support_trait_id, trait_id)

        assertion = dict(assertion_properties)
        assertion["id"] = assertion_id
        self.assertions[assertion_id] = assertion
        self.traits_by_entity[entity_id].add(trait_id)
        self.assertions_by_entity[entity_id].append(assertion)
        return assertion

    def has_trait(self, entity_id: str, trait_key: str, trait_value: str | None = None) -> bool:
        clean_key = _clean_trait_value(trait_key)
        clean_value = _clean_trait_value(trait_value) if trait_value is not None else None
        for assertion in self.assertions_by_entity.get(entity_id, []):
            if assertion.get("trait_key") != clean_key:
                continue
            if clean_value is None or assertion.get("trait_value") == clean_value:
                return True
        return False


def _context_role(context: Mapping[str, Any]) -> str:
    return _text(_prop(context, "page_role", "role", "context_role", default=""))


def _context_topics(context: Mapping[str, Any]) -> list[str]:
    return _as_text_list(_prop(context, "topics", "tags", default=[]))


def _context_parts(context: Mapping[str, Any]) -> list[str]:
    return _as_text_list(_prop(context, "important_parts", "highlighted_parts", "parts", default=[]))


def _image_class(record: Mapping[str, Any]) -> str:
    return _text(
        _prop(
            record,
            "classification",
            "image_class",
            "page_image_class",
            "visual_class",
            "class",
            default="",
        )
    )


def _image_bool(record: Mapping[str, Any], *keys: str) -> bool:
    for key in keys:
        value = _prop(record, key, default=None)
        if value not in (None, ""):
            return _as_bool(value, default=False)
    return False


def _image_number(record: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _prop(record, key, default=None)
        number = _as_float(value, default=None)
        if number is not None:
            return number
    return None


def _page_id_to_node_id(graph: GraphView) -> dict[str, str]:
    out: dict[str, str] = {}
    for page in graph.nodes_of_type("page"):
        node_id = _node_id(page)
        raw = _text(_prop(page, "page_id", "id", default=""))
        if raw:
            out[raw] = node_id
            out[_slug(raw)] = node_id
        if node_id.startswith("page:"):
            out[node_id] = node_id
            out[node_id.removeprefix("page:")] = node_id
    return out


def _page_empty_ocr(graph: GraphView, page: Mapping[str, Any]) -> bool:
    page_id = _node_id(page)
    if _as_bool(_prop(page, "empty_ocr", "is_empty_ocr", "ocr_empty", default=False)):
        return True
    for ocr in graph.neighbors(page_id, "HAS_OCR"):
        if _as_bool(_prop(ocr, "empty", "empty_ocr", "ocr_empty", default=False)):
            return True
    return False


def _page_part_numbers(graph: GraphView, page: Mapping[str, Any]) -> list[str]:
    numbers: list[str] = []
    for part in graph.neighbors(_node_id(page), "MENTIONS_PART"):
        number = _text(_prop(part, "part_number", "part", default=_node_label(part)))
        if number and number not in numbers:
            numbers.append(number)
    return numbers


def _best_context(graph: GraphView, page: Mapping[str, Any]) -> Mapping[str, Any] | None:
    contexts = graph.neighbors(_node_id(page), "HAS_CONTEXT")
    return contexts[0] if contexts else None


def _assert_base_entity_traits(builder: TraitOverlayBuilder) -> None:
    graph = builder.graph
    for document in graph.nodes_of_type("document"):
        builder.add_trait(
            document,
            "entity_kind",
            "document",
            trait_type="structure",
            source="document_graph",
            source_artifact="graph_nodes.json",
            method="node_type",
        )
        if graph.has_edge(_node_id(document), "HAS_PAGE"):
            builder.add_trait(document, "has_pages", "true", trait_type="structure")

    for ata in graph.nodes_of_type("ata_section"):
        builder.add_trait(
            ata,
            "entity_kind",
            "ata_section",
            trait_type="structure",
            source="document_graph",
            source_artifact="graph_nodes.json",
            method="node_type",
        )
        ata_code = _text(_prop(ata, "ata_code", "code", default=""))
        if ata_code:
            builder.add_trait(ata, "ata_code", ata_code, trait_type="structure")
        if graph.has_edge(_node_id(ata), "CONTAINS_PAGE"):
            builder.add_trait(ata, "has_pages", "true", trait_type="structure")


def _assert_page_traits(
    builder: TraitOverlayBuilder,
    image_by_page: Mapping[str, Mapping[str, Any]],
    visual_by_page: Mapping[str, Mapping[str, Any]],
) -> None:
    graph = builder.graph
    for page in graph.nodes_of_type("page"):
        page_id = _node_id(page)
        builder.add_trait(
            page,
            "entity_kind",
            "page",
            trait_type="structure",
            source="document_graph",
            source_artifact="graph_nodes.json",
            method="node_type",
        )
        if graph.has_edge(page_id, "BELONGS_TO_DOCUMENT"):
            builder.add_trait(page, "parent_type", "document", trait_type="hierarchy")
            parent = graph.first_neighbor(page_id, "BELONGS_TO_DOCUMENT")
            if parent is not None:
                _add_edge(builder.edges, "INHERITS_TRAITS_FROM", page_id, _node_id(parent))
        if graph.has_edge(page_id, "BELONGS_TO_ATA"):
            builder.add_trait(page, "parent_type", "ata_section", trait_type="hierarchy")
            parent = graph.first_neighbor(page_id, "BELONGS_TO_ATA")
            if parent is not None:
                _add_edge(builder.edges, "INHERITS_TRAITS_FROM", page_id, _node_id(parent))
        if graph.has_edge(page_id, "HAS_SOURCE_LINK"):
            builder.add_trait(page, "has_source_link", "true", trait_type="source")
        if graph.has_edge(page_id, "HAS_TIFF"):
            builder.add_trait(page, "has_tiff", "true", trait_type="source")
        if graph.has_edge(page_id, "HAS_OCR"):
            builder.add_trait(page, "has_ocr", "true", trait_type="source")
        if _page_empty_ocr(graph, page):
            builder.add_trait(page, "ocr_state", "empty", trait_type="ocr")
        elif graph.has_edge(page_id, "HAS_OCR"):
            builder.add_trait(page, "ocr_state", "non_empty", trait_type="ocr")
        if graph.has_edge(page_id, "HAS_CONTEXT"):
            builder.add_trait(page, "has_page_context", "true", trait_type="context")

        context = _best_context(graph, page)
        if context is not None:
            role = _context_role(context)
            if role:
                builder.add_trait(
                    page,
                    "page_role",
                    role,
                    trait_type="context",
                    source="page_context",
                    source_artifact="page_contexts.json",
                    method="ai_page_context",
                    confidence=_as_float(_prop(context, "confidence", default=None), default=None),
                    properties={"context_node_id": _node_id(context)},
                )
            for topic in _context_topics(context):
                builder.add_trait(
                    page,
                    "topic",
                    topic,
                    trait_type="context",
                    source="page_context",
                    source_artifact="page_contexts.json",
                    method="ai_page_context",
                    properties={"context_node_id": _node_id(context)},
                )
            for part_number in _context_parts(context):
                builder.add_trait(
                    page,
                    "highlighted_part",
                    part_number,
                    trait_type="context",
                    source="page_context",
                    source_artifact="page_contexts.json",
                    method="ai_page_context",
                    properties={"context_node_id": _node_id(context)},
                )

        image = image_by_page.get(page_id)
        if image is not None:
            readable = _image_bool(image, "readable", "image_readable", "is_readable")
            missing = _image_bool(image, "missing_image_file", "missing_file", "image_missing")
            unreadable = _image_bool(image, "unreadable", "image_unreadable")
            classification = _image_class(image)
            ink_ratio = _image_number(image, "ink_ratio", "average_ink_ratio", "page_ink_ratio")
            large_components = _image_number(
                image,
                "large_components",
                "large_component_count",
                "large_connected_components",
            )
            confidence = _as_float(_prop(image, "confidence", "score", default=None), default=None)
            image_properties = {
                "image_path": _prop(image, "image_path", "tiff_path", "path", default=None),
                "ink_ratio": ink_ratio,
                "large_components": large_components,
                "classification": classification,
            }
            if readable:
                builder.add_trait(
                    page,
                    "image_readable",
                    "true",
                    trait_type="image_recognition",
                    source="page_image_recognition",
                    source_artifact="page_image_recognition_audit.json",
                    method="image_audit",
                    confidence=confidence,
                    properties=image_properties,
                )
            if missing:
                builder.add_trait(
                    page,
                    "image_state",
                    "missing_file",
                    trait_type="image_recognition",
                    source="page_image_recognition",
                    source_artifact="page_image_recognition_audit.json",
                    method="image_audit",
                    properties=image_properties,
                )
            if unreadable:
                builder.add_trait(
                    page,
                    "image_state",
                    "unreadable",
                    trait_type="image_recognition",
                    source="page_image_recognition",
                    source_artifact="page_image_recognition_audit.json",
                    method="image_audit",
                    properties=image_properties,
                )
            if classification:
                builder.add_trait(
                    page,
                    "image_class",
                    classification,
                    trait_type="image_recognition",
                    source="page_image_recognition",
                    source_artifact="page_image_recognition_audit.json",
                    method="image_audit",
                    confidence=confidence,
                    properties=image_properties,
                )

            class_text = classification.lower()
            if "blank" in class_text or _image_bool(image, "likely_blank", "is_blank"):
                builder.add_trait(page, "likely_blank", "true", trait_type="visual")
            if "table" in class_text or "grid" in class_text or _image_bool(
                image,
                "likely_table_grid",
                "likely_table_or_grid",
                "is_table_grid",
            ):
                builder.add_trait(page, "likely_table_or_grid", "true", trait_type="visual")
            if "figure" in class_text or "diagram" in class_text or _image_bool(
                image,
                "likely_figure_diagram",
                "likely_figure_or_diagram",
                "is_figure_diagram",
            ):
                builder.add_trait(page, "likely_figure_or_diagram", "true", trait_type="visual")
            if "text" in class_text or "parts" in class_text or _image_bool(
                image,
                "likely_text",
                "likely_text_heavy",
                "likely_text_or_parts_list",
            ):
                builder.add_trait(page, "likely_text_or_parts_list", "true", trait_type="visual")
            if (
                builder.has_trait(page_id, "likely_table_or_grid", "true")
                or builder.has_trait(page_id, "likely_figure_or_diagram", "true")
                or _image_bool(image, "likely_visual", "is_visual")
            ):
                builder.add_trait(page, "likely_visual", "true", trait_type="visual")

        visual = visual_by_page.get(page_id)
        if visual is not None:
            role = _text(_prop(visual, "page_role", "role", "context_role", default=""))
            if role:
                builder.add_trait(
                    page,
                    "visual_audit_role",
                    role,
                    trait_type="visual_object",
                    source="page_visual_object_audit",
                    source_artifact="page_visual_objects_audit.json",
                    method="ocr_visual_terms",
                )
            for key, value in (
                ("has_figure_reference", _image_bool(visual, "has_figure_ref", "has_figure_reference")),
                ("has_table_reference", _image_bool(visual, "has_table_ref", "has_table_reference")),
                ("has_illustration_reference", _image_bool(visual, "has_illustration_ref", "has_illustration_reference")),
            ):
                if value:
                    builder.add_trait(
                        page,
                        key,
                        "true",
                        trait_type="visual_object",
                        source="page_visual_object_audit",
                        source_artifact="page_visual_objects_audit.json",
                        method="ocr_visual_terms",
                    )


def _assert_part_traits(builder: TraitOverlayBuilder) -> None:
    graph = builder.graph
    for part in graph.nodes_of_type("part"):
        part_id = _node_id(part)
        builder.add_trait(
            part,
            "entity_kind",
            "part",
            trait_type="structure",
            source="document_graph",
            source_artifact="graph_nodes.json",
            method="node_type",
        )
        nomenclature = _text(_prop(part, "nomenclature", "name", default=""))
        if nomenclature or graph.has_edge(part_id, "HAS_NOMENCLATURE"):
            builder.add_trait(part, "has_nomenclature", "true", trait_type="catalog")
        pages = graph.neighbors(part_id, "APPEARS_ON")
        if len(pages) >= 1:
            builder.add_trait(
                part,
                "appears_on_pages",
                "true",
                trait_type="catalog",
                properties={"page_count": len(pages)},
            )
        if len(pages) >= 2:
            builder.add_trait(
                part,
                "appears_on_multiple_pages",
                "true",
                trait_type="catalog",
                properties={"page_count": len(pages)},
            )
        source_pages = [page for page in pages if graph.has_edge(_node_id(page), "HAS_SOURCE_LINK")]
        if source_pages:
            builder.add_trait(
                part,
                "source_traceable_part",
                "true",
                trait_type="quality",
                properties={"source_page_count": len(source_pages)},
            )


def _assert_derived_traits(builder: TraitOverlayBuilder) -> None:
    graph = builder.graph
    for page in graph.nodes_of_type("page"):
        page_id = _node_id(page)
        supports_traceable = [
            ("source", "has_source_link", "true"),
            ("source", "has_tiff", "true"),
            ("source", "has_ocr", "true"),
            ("context", "has_page_context", "true"),
        ]
        if all(builder.has_trait(page_id, key, value) for _, key, value in supports_traceable):
            builder.add_trait(
                page,
                "fully_traceable_page",
                "true",
                trait_type="quality",
                source="derived_rules",
                source_artifact="entity_trait_graph.py",
                method="combo_trait",
                scope="derived",
                supports=supports_traceable,
            )
        if builder.has_trait(page_id, "has_source_link", "true") and builder.has_trait(
            page_id,
            "has_page_context",
            "true",
        ):
            builder.add_trait(
                page,
                "answer_ready_page",
                "true",
                trait_type="quality",
                source="derived_rules",
                source_artifact="entity_trait_graph.py",
                method="combo_trait",
                scope="derived",
            )
        if (
            builder.has_trait(page_id, "page_role", "parts_list")
            and (
                builder.has_trait(page_id, "likely_table_or_grid", "true")
                or builder.has_trait(page_id, "likely_figure_or_diagram", "true")
                or _page_part_numbers(graph, page)
            )
        ):
            builder.add_trait(
                page,
                "high_confidence_parts_list_page",
                "true",
                trait_type="quality",
                source="derived_rules",
                source_artifact="entity_trait_graph.py",
                method="combo_trait",
                scope="derived",
            )
        if (
            builder.has_trait(page_id, "ocr_state", "empty")
            and (
                builder.has_trait(page_id, "likely_blank", "true")
                or builder.has_trait(page_id, "page_role", "blank")
            )
        ):
            builder.add_trait(
                page,
                "verified_blank_page",
                "true",
                trait_type="quality",
                source="derived_rules",
                source_artifact="entity_trait_graph.py",
                method="combo_trait",
                scope="derived",
            )

    for part in graph.nodes_of_type("part"):
        part_id = _node_id(part)
        if builder.has_trait(part_id, "has_nomenclature", "true") and builder.has_trait(
            part_id,
            "source_traceable_part",
            "true",
        ):
            builder.add_trait(
                part,
                "high_confidence_part",
                "true",
                trait_type="quality",
                source="derived_rules",
                source_artifact="entity_trait_graph.py",
                method="combo_trait",
                scope="derived",
            )


def _trait_labels(assertions: Iterable[Mapping[str, Any]]) -> list[str]:
    labels = []
    for assertion in assertions:
        label = f"{assertion.get('trait_type')}:{assertion.get('trait_key')}={assertion.get('trait_value')}"
        if label not in labels:
            labels.append(label)
    return sorted(labels)


def _assertions_by_scope(assertions: Iterable[Mapping[str, Any]], scope: str) -> list[str]:
    return _trait_labels([a for a in assertions if a.get("scope") == scope])


def _build_page_cards(
    graph: GraphView,
    builder: TraitOverlayBuilder,
    image_by_page: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for page in graph.nodes_of_type("page"):
        page_id = _node_id(page)
        assertions = builder.assertions_by_entity.get(page_id, [])
        document = graph.first_neighbor(page_id, "BELONGS_TO_DOCUMENT")
        ata = graph.first_neighbor(page_id, "BELONGS_TO_ATA")
        context = _best_context(graph, page)
        image = image_by_page.get(page_id)
        parts = _page_part_numbers(graph, page)
        source_link = graph.first_neighbor(page_id, "HAS_SOURCE_LINK")
        tiff = graph.first_neighbor(page_id, "HAS_TIFF")
        ocr = graph.first_neighbor(page_id, "HAS_OCR")
        cards.append(
            {
                "entity_id": page_id,
                "entity_type": "page",
                "page_id": _text(_prop(page, "page_id", default=page_id.removeprefix("page:"))),
                "label": _node_label(page),
                "parents": {
                    "document_id": _node_id(document) if document else None,
                    "document_label": _node_label(document) if document else None,
                    "ata_id": _node_id(ata) if ata else None,
                    "ata_code": _prop(ata, "ata_code", default=None) if ata else _prop(page, "ata_code", default=None),
                },
                "source": {
                    "source_url": _prop(source_link or page, "source_url", "url", default=None),
                    "tiff_path": _prop(tiff or page, "path", "tiff_path", default=None),
                    "ocr_path": _prop(ocr or page, "path", "ocr_path", default=None),
                },
                "context": {
                    "context_node_id": _node_id(context) if context else None,
                    "page_role": _context_role(context) if context else None,
                    "topics": _context_topics(context) if context else [],
                    "important_parts": _context_parts(context) if context else [],
                    "summary": _prop(context or {}, "short_summary", "summary", default=None),
                },
                "signals": {
                    "image_classification": _image_class(image or {}) if image else None,
                    "ink_ratio": _image_number(image or {}, "ink_ratio", "average_ink_ratio", "page_ink_ratio") if image else None,
                    "large_components": _image_number(
                        image or {},
                        "large_components",
                        "large_component_count",
                        "large_connected_components",
                    ) if image else None,
                    "empty_ocr": _page_empty_ocr(graph, page),
                },
                "parts": parts,
                "direct_traits": _assertions_by_scope(assertions, "direct"),
                "derived_traits": _assertions_by_scope(assertions, "derived"),
                "traits": _trait_labels(assertions),
            }
        )
    return sorted(cards, key=lambda card: card["entity_id"])


def _build_part_cards(graph: GraphView, builder: TraitOverlayBuilder) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for part in graph.nodes_of_type("part"):
        part_id = _node_id(part)
        assertions = builder.assertions_by_entity.get(part_id, [])
        pages = graph.neighbors(part_id, "APPEARS_ON")
        best_pages = []
        for page in pages[:8]:
            best_pages.append(
                {
                    "page_node_id": _node_id(page),
                    "page_id": _prop(page, "page_id", default=_node_id(page).removeprefix("page:")),
                    "page_label": _prop(page, "page_label", "label", default=_node_label(page)),
                    "ata_code": _prop(page, "ata_code", default=None),
                    "source_url": _prop(page, "source_url", default=None),
                }
            )
        cards.append(
            {
                "entity_id": part_id,
                "entity_type": "part",
                "part_number": _text(_prop(part, "part_number", default=_node_label(part))),
                "nomenclature": _prop(part, "nomenclature", "name", default=None),
                "page_count": len(pages),
                "best_pages": best_pages,
                "direct_traits": _assertions_by_scope(assertions, "direct"),
                "derived_traits": _assertions_by_scope(assertions, "derived"),
                "traits": _trait_labels(assertions),
            }
        )
    return sorted(cards, key=lambda card: _normalize_part(card.get("part_number")))


def build_entity_trait_overlay(
    graph_dir: str | Path = DEFAULT_GRAPH_DIR,
    image_audit_path: str | Path | None = DEFAULT_IMAGE_RECOGNITION_AUDIT,
    page_visual_audit_path: str | Path | None = DEFAULT_PAGE_VISUAL_OBJECT_AUDIT,
) -> EntityTraitOverlayResult:
    """Build the entity-trait overlay from existing graph artifacts.

    Missing optional audit files do not fail the build. They simply reduce the
    number of image/visual-object traits available.
    """

    graph = load_document_graph(graph_dir)
    warnings: list[str] = []
    if not graph.nodes:
        warnings.append(f"document graph has no nodes: {graph_dir}")
    if not graph.edges:
        warnings.append(f"document graph has no edges: {graph_dir}")

    page_lookup = _page_id_to_node_id(graph)
    image_records, image_present = _load_audit_records(image_audit_path)
    visual_records, visual_present = _load_audit_records(page_visual_audit_path)
    if image_audit_path and not image_present:
        warnings.append(f"optional image-recognition audit not found/readable: {image_audit_path}")
    if page_visual_audit_path and not visual_present:
        warnings.append(f"optional page visual/object audit not found/readable: {page_visual_audit_path}")
    image_by_page = _records_by_page(image_records, page_lookup)
    visual_by_page = _records_by_page(visual_records, page_lookup)

    builder = TraitOverlayBuilder(graph)
    _assert_base_entity_traits(builder)
    _assert_page_traits(builder, image_by_page=image_by_page, visual_by_page=visual_by_page)
    _assert_part_traits(builder)
    _assert_derived_traits(builder)

    page_cards = _build_page_cards(graph, builder, image_by_page=image_by_page)
    part_cards = _build_part_cards(graph, builder)
    nodes = sorted(builder.nodes.values(), key=lambda node: (node["type"], node["id"]))
    edges = sorted(builder.edges.values(), key=lambda edge: (edge["type"], edge["from"], edge["to"]))
    assertions = sorted(builder.assertions.values(), key=lambda item: item["id"])

    node_counts = Counter(_node_type(node) for node in nodes)
    edge_counts = Counter(_edge_type(edge) for edge in edges)
    assertion_counts_by_entity_type = Counter(_text(a.get("entity_type")) for a in assertions)
    assertion_counts_by_trait_type = Counter(_text(a.get("trait_type")) for a in assertions)
    derived_assertions = [a for a in assertions if a.get("scope") == "derived"]

    status = "OK" if graph.nodes_of_type("page") and assertions else "NEEDS_ATTENTION"
    summary = {
        "status": status,
        "graph_dir": str(graph_dir),
        "image_audit_path": str(image_audit_path) if image_audit_path else None,
        "page_visual_audit_path": str(page_visual_audit_path) if page_visual_audit_path else None,
        "input_counts": {
            "graph_nodes": len(graph.nodes),
            "graph_edges": len(graph.edges),
            "pages": len(graph.nodes_of_type("page")),
            "parts": len(graph.nodes_of_type("part")),
            "image_audit_records": len(image_records),
            "image_audit_records_matched_to_pages": len(image_by_page),
            "page_visual_records": len(visual_records),
            "page_visual_records_matched_to_pages": len(visual_by_page),
        },
        "overlay_counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "assertions": len(assertions),
            "trait_nodes": node_counts.get("trait", 0),
            "trait_assertion_nodes": node_counts.get("trait_assertion", 0),
            "evidence_source_nodes": node_counts.get("evidence_source", 0),
            "page_cards": len(page_cards),
            "part_cards": len(part_cards),
            "derived_assertions": len(derived_assertions),
            "node_types": dict(sorted(node_counts.items())),
            "edge_types": dict(sorted(edge_counts.items())),
            "assertions_by_entity_type": dict(sorted(assertion_counts_by_entity_type.items())),
            "assertions_by_trait_type": dict(sorted(assertion_counts_by_trait_type.items())),
        },
        "warnings": warnings,
    }
    return EntityTraitOverlayResult(
        status=status,
        assertions=assertions,
        nodes=nodes,
        edges=edges,
        page_cards=page_cards,
        part_cards=part_cards,
        summary=summary,
        warnings=warnings,
    )


def export_entity_trait_overlay(
    graph_dir: str | Path = DEFAULT_GRAPH_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    image_audit_path: str | Path | None = DEFAULT_IMAGE_RECOGNITION_AUDIT,
    page_visual_audit_path: str | Path | None = DEFAULT_PAGE_VISUAL_OBJECT_AUDIT,
) -> EntityTraitOverlayResult:
    """Build and write the entity-trait overlay files."""

    result = build_entity_trait_overlay(
        graph_dir=graph_dir,
        image_audit_path=image_audit_path,
        page_visual_audit_path=page_visual_audit_path,
    )
    root = Path(output_dir)
    _write_json(root / ENTITY_TRAITS_FILE, {"assertions": result.assertions})
    _write_json(root / TRAIT_GRAPH_NODES_FILE, {"nodes": result.nodes})
    _write_json(root / TRAIT_GRAPH_EDGES_FILE, {"edges": result.edges})
    _write_json(root / PAGE_CHARACTER_CARDS_FILE, {"pages": result.page_cards})
    _write_json(root / PART_CHARACTER_CARDS_FILE, {"parts": result.part_cards})
    _write_json(root / TRAIT_GRAPH_SUMMARY_FILE, result.summary)
    return result
