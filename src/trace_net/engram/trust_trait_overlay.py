"""Build trust-tier trait overlays for visual-text evidence.

This module starts the TRACE-Net trust layer. It reads the cleaned visual-text
records produced by the v2.3 cleanup/scoring step and converts their trust tiers,
RAG eligibility, and review flags into graph traits.

The model follows the entity-trait pattern used elsewhere in this project:

    Entity -> HAS_TRAIT_ASSERTION -> TraitAssertion -> ASSERTS_TRAIT -> Trait
                                      |
                                      +-> DERIVED_FROM -> EvidenceSource

Trust traits are attached first to the evidence object that owns the trust value
(for now: VisualTextContext), then optionally summarized onto the Page as derived
review/RAG traits. This avoids saying a whole page is low-trust when only one
layer, such as visual_text, needs review.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_VISUAL_TEXT_DIR = Path("local_data/organization/visual_text")
DEFAULT_TRUST_TRAIT_DIR = Path("local_data/organization/trust_traits")
DEFAULT_CLEAN_RECORDS_FILE = "visual_text_extraction_clean.jsonl"
DEFAULT_OUTPUT_DIR = DEFAULT_TRUST_TRAIT_DIR

TRUST_ASSERTIONS_FILE = "trust_trait_assertions.jsonl"
TRUST_GRAPH_NODES_FILE = "trust_trait_graph_nodes.json"
TRUST_GRAPH_EDGES_FILE = "trust_trait_graph_edges.json"
TRUST_SUMMARY_FILE = "trust_trait_summary.json"
TRUST_QUALITY_FILE = "trust_trait_quality.json"
TRUST_REVIEW_MD_FILE = "trust_trait_review.md"

ACCEPTED_RECORD_STATUSES = {"ok", "planned"}
TRUST_TIERS = ("A", "B", "C", "D")

REVIEW_FLAG_TO_TRAIT: tuple[tuple[str, str], ...] = (
    ("metadata_leakage_risk", "metadata_leakage"),
    ("refusal_like", "refusal_like"),
    ("prompt_template_leakage_risk", "prompt_template_leakage"),
    ("section_bleed_risk", "section_bleed"),
    ("hallucination_risk", "hallucination_risk"),
    ("suspicious_phrase_risk", "suspicious_phrase"),
    ("table_expected_but_not_extracted", "table_expected_but_not_extracted"),
    ("too_summary_heavy", "summary_heavy"),
)


@dataclass(frozen=True)
class TrustTraitOverlayPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    clean_records_path: Path = DEFAULT_VISUAL_TEXT_DIR / DEFAULT_CLEAN_RECORDS_FILE
    assertions_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    summary_path: Path | None = None
    quality_path: Path | None = None
    review_md_path: Path | None = None

    @property
    def assertions(self) -> Path:
        return self.assertions_path or (self.output_dir / TRUST_ASSERTIONS_FILE)

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / TRUST_GRAPH_NODES_FILE)

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / TRUST_GRAPH_EDGES_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / TRUST_SUMMARY_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / TRUST_QUALITY_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / TRUST_REVIEW_MD_FILE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                out.append(dict(value))
    return out


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n")


def _node_id(prefix: str, raw: Any) -> str:
    text = _text(raw)
    if not text:
        return f"{prefix}:unknown"
    if text.startswith(f"{prefix}:"):
        return text
    return f"{prefix}:{_slug(text)}"


def _page_node_id(page_id: Any) -> str:
    return _node_id("page", page_id)


def _visual_text_node_id(page_id: Any) -> str:
    return _node_id("visual_text", page_id)


def _trait_node_id(trait_type: str, trait_key: str, trait_value: Any) -> str:
    return f"trait:{_slug(trait_type)}:{_slug(trait_key)}:{_slug(trait_value)}"


def _evidence_node_id(source_artifact: str) -> str:
    return f"evidence_source:{_slug(source_artifact)}"


def _edge_id(edge_type: str, source: str, target: str) -> str:
    return f"edge:{_slug(edge_type)}:{_slug(source)}:{_slug(target)}"


def _clean_props(props: Mapping[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in dict(props or {}).items():
        if value in (None, "", [], {}):
            continue
        out[key] = value
    return out


def _add_node(
    nodes: dict[str, dict[str, Any]],
    node_id: str,
    node_type: str,
    label: str,
    properties: Mapping[str, Any] | None = None,
) -> None:
    clean_properties = _clean_props(properties)
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
    clean_properties = _clean_props(properties)
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


def _record_page_id(record: Mapping[str, Any]) -> str:
    return _text(
        record.get("page_id")
        or record.get("page")
        or record.get("id")
        or _as_dict(record.get("source")).get("page_id")
    )


def _record_status(record: Mapping[str, Any]) -> str:
    return _norm(record.get("status") or "unknown") or "unknown"


def _cleanup_scores(record: Mapping[str, Any]) -> dict[str, Any]:
    return _as_dict(record.get("visual_text_cleanup_scores"))


def _clean_scores(record: Mapping[str, Any]) -> dict[str, Any]:
    return _as_dict(record.get("visual_text_scores_clean") or record.get("visual_text_scores"))


def _record_trust_tier(record: Mapping[str, Any]) -> str:
    cleanup = _cleanup_scores(record)
    raw = _text(cleanup.get("trust_tier") or record.get("trust_tier"), "D").upper()
    return raw if raw in TRUST_TIERS else "D"


def _record_usable_for_rag(record: Mapping[str, Any], tier: str) -> bool:
    cleanup = _cleanup_scores(record)
    if "usable_for_rag" in cleanup:
        return bool(cleanup.get("usable_for_rag"))
    return tier in {"A", "B"}


def _record_requires_review(record: Mapping[str, Any], tier: str) -> bool:
    cleanup = _cleanup_scores(record)
    if "requires_human_review" in cleanup:
        return bool(cleanup.get("requires_human_review"))
    return tier in {"C", "D"}


def _review_flags(record: Mapping[str, Any]) -> dict[str, bool]:
    cleanup = _cleanup_scores(record)
    scores = _clean_scores(record)
    flags: dict[str, bool] = {}
    for source_key, trait_value in REVIEW_FLAG_TO_TRAIT:
        if source_key in cleanup:
            flags[trait_value] = bool(cleanup.get(source_key))
        elif source_key in scores:
            flags[trait_value] = bool(scores.get(source_key))
        else:
            flags[trait_value] = False
    # Support v2.3.1 repaired flags as non-blocking review-trace traits.
    if cleanup.get("prompt_template_repaired"):
        flags["prompt_template_repaired"] = True
    if cleanup.get("section_bleed_repaired"):
        flags["section_bleed_repaired"] = True
    return flags


def _assertion_id(entity_id: str, trait_type: str, trait_key: str, trait_value: Any, page_id: str, scope: str) -> str:
    return (
        f"trait_assertion:{_slug(entity_id)}:{_slug(trait_type)}:"
        f"{_slug(trait_key)}:{_slug(trait_value)}:{_slug(page_id)}:{_slug(scope)}"
    )


def _add_trait_assertion(
    *,
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
    assertions: dict[str, dict[str, Any]],
    entity_id: str,
    entity_type: str,
    page_id: str,
    trait_type: str,
    trait_key: str,
    trait_value: Any,
    source_artifact: str,
    method: str,
    scope: str,
    confidence: float | None = None,
    properties: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    clean_value = _text(trait_value)
    trait_id = _trait_node_id(trait_type, trait_key, clean_value)
    evidence_id = _evidence_node_id(source_artifact)
    assertion_id = _assertion_id(entity_id, trait_type, trait_key, clean_value, page_id, scope)

    _add_node(
        nodes,
        trait_id,
        "trait",
        f"{trait_type}:{trait_key}={clean_value}",
        {
            "trait_type": trait_type,
            "trait_key": trait_key,
            "trait_value": clean_value,
        },
    )
    _add_node(
        nodes,
        evidence_id,
        "evidence_source",
        source_artifact,
        {
            "source_artifact": source_artifact,
            "method": method,
        },
    )
    assertion_props = {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "page_id": page_id,
        "trait_id": trait_id,
        "trait_type": trait_type,
        "trait_key": trait_key,
        "trait_value": clean_value,
        "source_artifact": source_artifact,
        "method": method,
        "scope": scope,
        "confidence": confidence,
        "evidence_id": evidence_id,
    }
    assertion_props.update(_clean_props(properties))
    _add_node(
        nodes,
        assertion_id,
        "trait_assertion",
        f"{entity_id} has {trait_type}:{trait_key}={clean_value}",
        assertion_props,
    )
    _add_edge(edges, "HAS_TRAIT_ASSERTION", entity_id, assertion_id)
    _add_edge(edges, "ASSERTS_TRAIT", assertion_id, trait_id)
    _add_edge(edges, "DERIVED_FROM", assertion_id, evidence_id)
    _add_edge(edges, "HAS_TRAIT", entity_id, trait_id, {"via": assertion_id})

    assertion = dict(assertion_props)
    assertion["id"] = assertion_id
    assertions[assertion_id] = assertion
    return assertion


def build_trust_trait_overlay(
    records: Sequence[Mapping[str, Any]],
    *,
    source_artifact: str = "visual_text_extraction_clean.jsonl",
) -> dict[str, Any]:
    """Build trust-tier graph nodes/edges/assertions from clean visual records."""

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    assertions: dict[str, dict[str, Any]] = {}
    page_ids: set[str] = set()
    accepted_records = 0
    tier_counts: Counter[str] = Counter()
    review_trait_counts: Counter[str] = Counter()
    rag_trait_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for record in records:
        page_id = _record_page_id(record)
        if not page_id:
            continue
        page_ids.add(page_id)
        status = _record_status(record)
        status_counts[status] += 1
        tier = _record_trust_tier(record)
        tier_counts[tier] += 1
        cleanup = _cleanup_scores(record)
        scores = _clean_scores(record)
        usable_for_rag = _record_usable_for_rag(record, tier)
        requires_review = _record_requires_review(record, tier)
        page_node = _page_node_id(page_id)
        visual_node = _visual_text_node_id(page_id)

        _add_node(nodes, page_node, "page", page_id, {"page_id": page_id})
        _add_node(
            nodes,
            visual_node,
            "visual_text_context",
            f"Visual text for {page_id}",
            {
                "page_id": page_id,
                "status": status,
                "trust_tier": tier,
                "usable_for_rag": usable_for_rag,
                "requires_human_review": requires_review,
                "prompt_version": record.get("prompt_version"),
                "cleanup_version": record.get("cleanup_version") or cleanup.get("cleanup_version"),
                "char_count_clean": record.get("char_count_clean") or record.get("char_count"),
            },
        )
        _add_edge(edges, "HAS_VISUAL_TEXT", page_node, visual_node)
        if status in ACCEPTED_RECORD_STATUSES:
            accepted_records += 1

        base_props = {
            "trust_tier": tier,
            "status": status,
            "usable_for_rag": usable_for_rag,
            "requires_human_review": requires_review,
            "trust_reasons": cleanup.get("trust_reasons", []),
        }
        # Evidence-layer trust tier. This is the primary trust trait.
        _add_trait_assertion(
            nodes=nodes,
            edges=edges,
            assertions=assertions,
            entity_id=visual_node,
            entity_type="visual_text_context",
            page_id=page_id,
            trait_type="trust",
            trait_key="visual_text",
            trait_value=tier,
            source_artifact=source_artifact,
            method="trace_net_trust_tier",
            scope="evidence_layer",
            confidence=None,
            properties=base_props,
        )

        # RAG include/exclude traits attach to both the visual context and page.
        rag_value = "include_visual_text" if usable_for_rag else "exclude_visual_text"
        rag_trait_counts[rag_value] += 1
        for entity_id, entity_type, scope in (
            (visual_node, "visual_text_context", "evidence_layer"),
            (page_node, "page", "derived_page"),
        ):
            _add_trait_assertion(
                nodes=nodes,
                edges=edges,
                assertions=assertions,
                entity_id=entity_id,
                entity_type=entity_type,
                page_id=page_id,
                trait_type="rag",
                trait_key="visual_text",
                trait_value=rag_value,
                source_artifact=source_artifact,
                method="trace_net_rag_gate",
                scope=scope,
                properties=base_props,
            )

        if requires_review:
            review_trait_counts["needs_human_review"] += 1
            for entity_id, entity_type, scope in (
                (visual_node, "visual_text_context", "evidence_layer"),
                (page_node, "page", "derived_page"),
            ):
                _add_trait_assertion(
                    nodes=nodes,
                    edges=edges,
                    assertions=assertions,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    page_id=page_id,
                    trait_type="review",
                    trait_key="visual_text",
                    trait_value="needs_human_review",
                    source_artifact=source_artifact,
                    method="trace_net_review_gate",
                    scope=scope,
                    properties=base_props,
                )

        # Specific review flags attach to visual_text context. These create easy
        # graph traversals like trait:review:visual_text=hallucination_risk -> pages.
        flags = _review_flags(record)
        for flag_name, enabled in sorted(flags.items()):
            if not enabled:
                continue
            review_trait_counts[flag_name] += 1
            _add_trait_assertion(
                nodes=nodes,
                edges=edges,
                assertions=assertions,
                entity_id=visual_node,
                entity_type="visual_text_context",
                page_id=page_id,
                trait_type="review",
                trait_key="visual_text",
                trait_value=flag_name,
                source_artifact=source_artifact,
                method="trace_net_review_flag",
                scope="evidence_layer",
                properties={
                    **base_props,
                    "flag": flag_name,
                    "metadata_leakage_marker_count": scores.get("metadata_leakage_marker_count"),
                    "prompt_template_markers": cleanup.get("prompt_template_leakage_markers", []),
                    "section_bleed_markers": cleanup.get("section_bleed_markers", []),
                    "suspicious_phrase_markers": cleanup.get("suspicious_phrase_markers", []),
                },
            )

    node_list = sorted(nodes.values(), key=lambda item: item["id"])
    edge_list = sorted(edges.values(), key=lambda item: item["id"])
    assertion_list = sorted(assertions.values(), key=lambda item: item["id"])
    node_counts = Counter(str(node.get("type") or "unknown") for node in node_list)
    edge_counts = Counter(str(edge.get("type") or "unknown") for edge in edge_list)
    assertion_counts_by_scope = Counter(str(assertion.get("scope") or "unknown") for assertion in assertion_list)
    assertion_counts_by_entity_type = Counter(str(assertion.get("entity_type") or "unknown") for assertion in assertion_list)
    assertion_counts_by_trait_type = Counter(str(assertion.get("trait_type") or "unknown") for assertion in assertion_list)

    status = "OK" if records and page_ids and assertion_list else "FAIL"
    summary = {
        "status": status,
        "created_at": utc_now_iso(),
        "overlay": "trace_net_trust_traits",
        "source_artifact": source_artifact,
        "records": len(records),
        "pages": len(page_ids),
        "accepted_records": accepted_records,
        "nodes": len(node_list),
        "edges": len(edge_list),
        "assertions": len(assertion_list),
        "page_nodes": node_counts.get("page", 0),
        "visual_text_context_nodes": node_counts.get("visual_text_context", 0),
        "trait_nodes": node_counts.get("trait", 0),
        "trait_assertion_nodes": node_counts.get("trait_assertion", 0),
        "evidence_source_nodes": node_counts.get("evidence_source", 0),
        "has_visual_text_edges": edge_counts.get("HAS_VISUAL_TEXT", 0),
        "has_trait_assertion_edges": edge_counts.get("HAS_TRAIT_ASSERTION", 0),
        "asserts_trait_edges": edge_counts.get("ASSERTS_TRAIT", 0),
        "derived_from_edges": edge_counts.get("DERIVED_FROM", 0),
        "has_trait_edges": edge_counts.get("HAS_TRAIT", 0),
        "status_counts": dict(sorted(status_counts.items())),
        "trust_tier_counts": {tier: tier_counts.get(tier, 0) for tier in TRUST_TIERS},
        "rag_trait_counts": dict(sorted(rag_trait_counts.items())),
        "review_trait_counts": dict(sorted(review_trait_counts.items())),
        "assertions_by_scope": dict(sorted(assertion_counts_by_scope.items())),
        "assertions_by_entity_type": dict(sorted(assertion_counts_by_entity_type.items())),
        "assertions_by_trait_type": dict(sorted(assertion_counts_by_trait_type.items())),
    }
    return {
        "status": status,
        "summary": summary,
        "assertions": assertion_list,
        "nodes": node_list,
        "edges": edge_list,
    }


def _build_review_md(summary: Mapping[str, Any], assertions: Sequence[Mapping[str, Any]]) -> str:
    by_page: dict[str, list[Mapping[str, Any]]] = {}
    for assertion in assertions:
        page_id = _text(assertion.get("page_id") or "unknown")
        by_page.setdefault(page_id, []).append(assertion)

    lines = ["# TRACE-Net trust trait overlay", ""]
    lines.append(f"- status: {summary.get('status')}")
    lines.append(f"- records: {summary.get('records')}")
    lines.append(f"- pages: {summary.get('pages')}")
    lines.append(f"- assertions: {summary.get('assertions')}")
    lines.append(f"- trust_tier_counts: {summary.get('trust_tier_counts')}")
    lines.append(f"- rag_trait_counts: {summary.get('rag_trait_counts')}")
    lines.append(f"- review_trait_counts: {summary.get('review_trait_counts')}")
    lines.append("")

    for page_id in sorted(by_page):
        page_assertions = by_page[page_id]
        trust = [a for a in page_assertions if a.get("trait_type") == "trust"]
        rag = [a for a in page_assertions if a.get("trait_type") == "rag"]
        review = [a for a in page_assertions if a.get("trait_type") == "review"]
        lines.append(f"## {page_id}")
        for label, group in (("trust", trust), ("rag", rag), ("review", review)):
            values = sorted({f"{a.get('trait_key')}={a.get('trait_value')}" for a in group})
            lines.append(f"- {label}: {', '.join(values) if values else 'none'}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_trust_trait_overlay(paths: TrustTraitOverlayPaths) -> dict[str, Any]:
    records = read_jsonl(paths.clean_records_path)
    result = build_trust_trait_overlay(records, source_artifact=paths.clean_records_path.name)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(paths.assertions, result["assertions"])
    _write_json(paths.graph_nodes, result["nodes"])
    _write_json(paths.graph_edges, result["edges"])
    _write_json(paths.summary, result["summary"])
    paths.review_md.write_text(_build_review_md(result["summary"], result["assertions"]), encoding="utf-8")
    return result


def _check(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "message": message}


def build_trust_trait_quality(
    paths: TrustTraitOverlayPaths,
    *,
    min_records: int = 1,
    expect_pages: int | None = None,
    max_trust_d_records: int | None = None,
    min_trait_nodes: int = 1,
) -> dict[str, Any]:
    summary_present = paths.summary.exists()
    assertions_present = paths.assertions.exists()
    nodes_present = paths.graph_nodes.exists()
    edges_present = paths.graph_edges.exists()
    summary = _as_dict(_read_json(paths.summary)) if summary_present else {}
    assertions = read_jsonl(paths.assertions) if assertions_present else []
    nodes = _read_json(paths.graph_nodes) if nodes_present else []
    edges = _read_json(paths.graph_edges) if edges_present else []
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []

    trust_counts = _as_dict(summary.get("trust_tier_counts"))
    records = int(summary.get("records") or 0)
    pages = int(summary.get("pages") or 0)
    trust_d = int(trust_counts.get("D") or 0)
    trait_nodes = int(summary.get("trait_nodes") or 0)
    assertion_count = int(summary.get("assertions") or 0)
    visual_context_nodes = int(summary.get("visual_text_context_nodes") or 0)
    has_visual_text_edges = int(summary.get("has_visual_text_edges") or 0)

    checks: list[dict[str, Any]] = []
    checks.append(_check("trust_trait_artifacts_present", summary_present and assertions_present and nodes_present and edges_present, f"summary={summary_present}; assertions={assertions_present}; nodes={nodes_present}; edges={edges_present}."))
    checks.append(_check("trust_trait_status", _text(summary.get("status")).lower() == "ok", f"Trust overlay status is {summary.get('status')!r}."))
    checks.append(_check("trust_trait_records", records >= min_records and len(assertions) >= min_records, f"records={records}, assertions_jsonl={len(assertions)}; minimum records={min_records}."))
    if expect_pages is not None:
        checks.append(_check("trust_trait_page_count", pages == expect_pages, f"pages={pages}; expected={expect_pages}."))
    checks.append(_check("trust_trait_nodes", len(nodes) >= min_trait_nodes and trait_nodes >= min_trait_nodes, f"nodes={len(nodes)}, trait_nodes={trait_nodes}; minimum trait_nodes={min_trait_nodes}."))
    checks.append(_check("trust_trait_edges", len(edges) >= records and has_visual_text_edges >= pages, f"edges={len(edges)}, has_visual_text_edges={has_visual_text_edges}, pages={pages}."))
    checks.append(_check("trust_trait_assertions", assertion_count >= records and visual_context_nodes >= pages, f"assertions={assertion_count}, visual_text_context_nodes={visual_context_nodes}, pages={pages}."))
    if max_trust_d_records is not None:
        checks.append(_check("trust_trait_trust_d", trust_d <= max_trust_d_records, f"trust_tier_D={trust_d}; max={max_trust_d_records}."))

    status = "OK" if all(check["ok"] for check in checks) else "FAIL"
    quality_summary = {
        "trust_trait_overlay_present": summary_present,
        "trust_trait_status": summary.get("status"),
        "trust_trait_records": records,
        "trust_trait_pages": pages,
        "trust_trait_assertions": assertion_count,
        "trust_trait_nodes": len(nodes),
        "trust_trait_edges": len(edges),
        "trust_trait_trait_nodes": trait_nodes,
        "trust_trait_visual_text_context_nodes": visual_context_nodes,
        "trust_trait_has_visual_text_edges": has_visual_text_edges,
        "trust_trait_tier_A": int(trust_counts.get("A") or 0),
        "trust_trait_tier_B": int(trust_counts.get("B") or 0),
        "trust_trait_tier_C": int(trust_counts.get("C") or 0),
        "trust_trait_tier_D": trust_d,
        "trust_trait_rag_trait_counts": summary.get("rag_trait_counts", {}),
        "trust_trait_review_trait_counts": summary.get("review_trait_counts", {}),
        "trust_trait_summary_path": str(paths.summary),
        "trust_trait_assertions_path": str(paths.assertions),
        "trust_trait_graph_nodes_path": str(paths.graph_nodes),
        "trust_trait_graph_edges_path": str(paths.graph_edges),
    }
    return {
        "status": status,
        "summary": quality_summary,
        "checks": checks,
        "created_at": utc_now_iso(),
    }


def print_export_result(result: Mapping[str, Any], paths: TrustTraitOverlayPaths, *, samples: int = 8) -> None:
    summary = _as_dict(result.get("summary"))
    print("TRACE-Net trust trait overlay export")
    print(f"  Status: {summary.get('status')}")
    print(f"  Clean records: {paths.clean_records_path}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "records",
        "pages",
        "accepted_records",
        "nodes",
        "edges",
        "assertions",
        "visual_text_context_nodes",
        "trait_nodes",
        "trust_tier_counts",
        "rag_trait_counts",
        "review_trait_counts",
    ):
        print(f"    {key}: {summary.get(key)}")
    assertions = list(result.get("assertions") or [])
    if samples and assertions:
        print("  Sample assertions:")
        for assertion in assertions[:samples]:
            print(
                "    "
                f"{assertion.get('entity_id')} | "
                f"{assertion.get('trait_type')}:{assertion.get('trait_key')}={assertion.get('trait_value')} | "
                f"scope={assertion.get('scope')}"
            )
    print("Files written:")
    print(f"  assertions: {paths.assertions}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    print(f"  summary: {paths.summary}")
    print(f"  review_md: {paths.review_md}")


def print_quality(report: Mapping[str, Any], paths: TrustTraitOverlayPaths) -> None:
    print("TRACE-Net trust trait quality gate")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key, value in _as_dict(report.get("summary")).items():
        if key.endswith("_path"):
            continue
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in _as_list(report.get("checks")):
        label = "OK" if check.get("ok") else "FAIL"
        print(f"    {label} {check.get('name')}: {check.get('message')}")
    print(f"\nJSON: {paths.quality}")


def make_paths_from_args(args: argparse.Namespace) -> TrustTraitOverlayPaths:
    return TrustTraitOverlayPaths(
        output_dir=Path(args.output_dir),
        clean_records_path=Path(args.clean_records),
    )


def export_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export TRACE-Net trust tier traits from clean visual-text records.")
    parser.add_argument("--clean-records", default=str(DEFAULT_VISUAL_TEXT_DIR / DEFAULT_CLEAN_RECORDS_FILE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--expect-records", type=int, default=None)
    parser.add_argument("--samples", type=int, default=8)
    args = parser.parse_args(argv)
    paths = make_paths_from_args(args)
    result = export_trust_trait_overlay(paths)
    print_export_result(result, paths, samples=args.samples)
    if args.expect_records is not None:
        records = int(_as_dict(result.get("summary")).get("records") or 0)
        if records != args.expect_records:
            print(f"Expected {args.expect_records} records but found {records}.")
            return 1
    return 0 if result.get("status") == "OK" else 1


def quality_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net trust trait overlay quality.")
    parser.add_argument("--clean-records", default=str(DEFAULT_VISUAL_TEXT_DIR / DEFAULT_CLEAN_RECORDS_FILE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--max-trust-d-records", type=int, default=None)
    parser.add_argument("--min-trait-nodes", type=int, default=1)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    paths = make_paths_from_args(args)
    report = build_trust_trait_quality(
        paths,
        min_records=args.min_records,
        expect_pages=args.expect_pages,
        max_trust_d_records=args.max_trust_d_records,
        min_trait_nodes=args.min_trait_nodes,
    )
    if args.write_json:
        _write_json(paths.quality, report)
    print_quality(report, paths)
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(export_cli())
