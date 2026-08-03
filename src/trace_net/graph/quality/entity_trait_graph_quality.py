"""Quality checks for the entity-trait graph overlay."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
from typing import Any, Mapping

from tiff.entity_trait_graph import (
    DEFAULT_OUTPUT_DIR,
    ENTITY_TRAITS_FILE,
    PAGE_CHARACTER_CARDS_FILE,
    PART_CHARACTER_CARDS_FILE,
    TRAIT_GRAPH_EDGES_FILE,
    TRAIT_GRAPH_NODES_FILE,
    TRAIT_GRAPH_SUMMARY_FILE,
)

DEFAULT_ENTITY_TRAIT_QUALITY_JSON = "local_data/organization/entity_traits/entity_trait_quality.json"


@dataclass(frozen=True)
class EntityTraitQualityThresholds:
    min_trait_assertions: int = 1
    min_trait_nodes: int = 1
    min_evidence_sources: int = 1
    min_page_cards: int = 1
    max_pages_without_traits: int = 0
    require_derived_traits: bool = True
    require_part_cards_when_parts_exist: bool = False


@dataclass(frozen=True)
class EntityTraitQualityCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class EntityTraitQualityResult:
    status: str
    summary: dict[str, Any]
    checks: list[EntityTraitQualityCheck] = field(default_factory=list)


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


def _as_list(payload: Any, *keys: str) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _node_type(node: Mapping[str, Any]) -> str:
    return str(node.get("type") or node.get("node_type") or node.get("kind") or "").strip().lower()


def _edge_type(edge: Mapping[str, Any]) -> str:
    return str(edge.get("type") or edge.get("edge_type") or edge.get("relationship") or "").strip().upper()


def _add_check(checks: list[EntityTraitQualityCheck], name: str, ok: bool, message: str) -> None:
    checks.append(EntityTraitQualityCheck(name=name, status="OK" if ok else "FAIL", message=message))


def build_entity_trait_quality_result(
    overlay_dir: str | Path = DEFAULT_OUTPUT_DIR,
    thresholds: EntityTraitQualityThresholds | None = None,
) -> EntityTraitQualityResult:
    thresholds = thresholds or EntityTraitQualityThresholds()
    root = Path(overlay_dir)

    summary_payload = _load_json(root / TRAIT_GRAPH_SUMMARY_FILE)
    assertions_payload = _load_json(root / ENTITY_TRAITS_FILE)
    nodes_payload = _load_json(root / TRAIT_GRAPH_NODES_FILE)
    edges_payload = _load_json(root / TRAIT_GRAPH_EDGES_FILE)
    page_cards_payload = _load_json(root / PAGE_CHARACTER_CARDS_FILE)
    part_cards_payload = _load_json(root / PART_CHARACTER_CARDS_FILE)

    assertions = [x for x in _as_list(assertions_payload, "assertions") if isinstance(x, Mapping)]
    nodes = [x for x in _as_list(nodes_payload, "nodes") if isinstance(x, Mapping)]
    edges = [x for x in _as_list(edges_payload, "edges") if isinstance(x, Mapping)]
    page_cards = [x for x in _as_list(page_cards_payload, "pages") if isinstance(x, Mapping)]
    part_cards = [x for x in _as_list(part_cards_payload, "parts") if isinstance(x, Mapping)]
    summary_obj = _as_mapping(summary_payload)

    node_counts = Counter(_node_type(node) for node in nodes)
    edge_counts = Counter(_edge_type(edge) for edge in edges)
    derived_assertions = [a for a in assertions if str(a.get("scope") or "").lower() == "derived"]
    pages_without_traits = 0
    for card in page_cards:
        traits = card.get("traits")
        if not isinstance(traits, list) or not traits:
            pages_without_traits += 1

    input_counts = _as_mapping(summary_obj.get("input_counts"))
    graph_part_count = int(input_counts.get("parts") or 0)

    summary = {
        "entity_trait_overlay_present": summary_payload is not None,
        "entity_trait_overlay_status": str(summary_obj.get("status") or "").lower() or None,
        "entity_trait_assertions": len(assertions),
        "entity_trait_nodes": node_counts.get("trait", 0),
        "entity_trait_assertion_nodes": node_counts.get("trait_assertion", 0),
        "entity_trait_evidence_source_nodes": node_counts.get("evidence_source", 0),
        "entity_trait_edges": len(edges),
        "entity_trait_has_trait_edges": edge_counts.get("HAS_TRAIT", 0),
        "entity_trait_has_assertion_edges": edge_counts.get("HAS_TRAIT_ASSERTION", 0),
        "entity_trait_asserts_trait_edges": edge_counts.get("ASSERTS_TRAIT", 0),
        "entity_trait_derived_from_edges": edge_counts.get("DERIVED_FROM", 0),
        "entity_trait_inherits_edges": edge_counts.get("INHERITS_TRAITS_FROM", 0),
        "entity_trait_derived_assertions": len(derived_assertions),
        "entity_trait_page_cards": len(page_cards),
        "entity_trait_part_cards": len(part_cards),
        "entity_trait_pages_without_traits": pages_without_traits,
        "entity_trait_graph_parts": graph_part_count,
    }

    checks: list[EntityTraitQualityCheck] = []
    _add_check(
        checks,
        "entity_trait_summary_present",
        summary_payload is not None,
        f"Trait overlay summary present at {root / TRAIT_GRAPH_SUMMARY_FILE}.",
    )
    _add_check(
        checks,
        "entity_trait_overlay_status",
        summary["entity_trait_overlay_status"] in {"ok", ""},
        f"Trait overlay status is {summary['entity_trait_overlay_status']}.",
    )
    _add_check(
        checks,
        "entity_trait_assertions",
        len(assertions) >= thresholds.min_trait_assertions,
        f"Trait assertions={len(assertions)}; minimum is {thresholds.min_trait_assertions}.",
    )
    _add_check(
        checks,
        "entity_trait_nodes",
        node_counts.get("trait", 0) >= thresholds.min_trait_nodes,
        f"Trait nodes={node_counts.get('trait', 0)}; minimum is {thresholds.min_trait_nodes}.",
    )
    _add_check(
        checks,
        "entity_trait_evidence_sources",
        node_counts.get("evidence_source", 0) >= thresholds.min_evidence_sources,
        f"Evidence source nodes={node_counts.get('evidence_source', 0)}; minimum is {thresholds.min_evidence_sources}.",
    )
    _add_check(
        checks,
        "entity_trait_edges",
        edge_counts.get("HAS_TRAIT_ASSERTION", 0) >= len(assertions)
        and edge_counts.get("ASSERTS_TRAIT", 0) >= len(assertions)
        and edge_counts.get("DERIVED_FROM", 0) >= len(assertions),
        "Trait assertion, trait, and evidence edges are present for assertions.",
    )
    _add_check(
        checks,
        "entity_trait_page_cards",
        len(page_cards) >= thresholds.min_page_cards,
        f"Page cards={len(page_cards)}; minimum is {thresholds.min_page_cards}.",
    )
    _add_check(
        checks,
        "entity_trait_page_trait_coverage",
        pages_without_traits <= thresholds.max_pages_without_traits,
        f"Pages without traits={pages_without_traits}; max allowed={thresholds.max_pages_without_traits}.",
    )
    if thresholds.require_derived_traits:
        _add_check(
            checks,
            "entity_trait_derived_traits",
            len(derived_assertions) > 0,
            f"Derived trait assertions={len(derived_assertions)}; expected at least 1.",
        )
    if thresholds.require_part_cards_when_parts_exist:
        _add_check(
            checks,
            "entity_trait_part_cards",
            graph_part_count == 0 or len(part_cards) > 0,
            f"Part cards={len(part_cards)} for graph parts={graph_part_count}.",
        )

    status = "ok" if all(check.status == "OK" for check in checks) else "fail"
    return EntityTraitQualityResult(status=status, summary=summary, checks=checks)


def format_entity_trait_quality_result(result: EntityTraitQualityResult) -> str:
    lines = ["Entity-trait graph quality gate", f"  Status: {result.status.upper()}", "  Summary:"]
    for key in sorted(result.summary):
        lines.append(f"    {key}: {result.summary[key]}")
    lines.append("  Checks:")
    for check in result.checks:
        lines.append(f"    {check.status} {check.name}: {check.message}")
    return "\n".join(lines)


def write_entity_trait_quality_json(
    result: EntityTraitQualityResult,
    output_path: str | Path = DEFAULT_ENTITY_TRAIT_QUALITY_JSON,
) -> Path:
    return _write_json(
        output_path,
        {
            "status": result.status,
            "summary": result.summary,
            "checks": [asdict(check) for check in result.checks],
        },
    )
