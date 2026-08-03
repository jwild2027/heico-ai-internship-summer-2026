#!/usr/bin/env python3
"""TRACE-Net NHA phase N4: conservative IPL hierarchy and attaching-parts resolution.

Consumes the inspected N0-N3 JSON artifacts.  It never re-writes those artifacts,
never calls an LLM, and never writes Postgres, Qdrant, OpenSearch, or a production
graph.  The output is a read-only hierarchy view with explicit direct-child,
attaching-part, and unresolved-variant relationships.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MODULE = "trace_net_nha_phase4_hierarchy_v1"
STATUS = "TRACE_NET_NHA_PHASE4_HIERARCHY_V1"
SCHEMA_VERSION = "trace_net_nha_phase4_hierarchy_v1"

HARDWARE_HEADS = {
    "BOLT", "NUT", "SCREW", "WASHER", "PIN", "FITTING", "RIVET", "CLIP",
    "FASTENER", "COTTER", "RING", "SPACER", "STUD", "LOCKWASHER", "PLUG",
    "GROMMET", "BUSHING", "BEARING", "COLLAR", "RETAINER", "SPRING",
}
SUBSTANTIVE_HEADS = {
    "ASSEMBLY", "ASSY", "STRUCTURE", "SEAT", "BACKREST", "FBACKREST",
    "ARMREST", "SUPPORT", "FRAME", "UNIT", "MODULE", "LEG", "PLATE",
    "PROTECTOR", "REINFORCEMENT", "COMPLEMENT", "COVER", "PANEL", "BRACKET",
}
NOISE_TOKENS = {
    "WS4956", "WVS4956", "VS4956", "MS4956", "VGS4956", "REF", "ALL",
}


def _compact(value: Any, limit: int = 20000) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _stable_id(prefix: str, *values: Any) -> str:
    blob = "|".join(_compact(value, 5000) for value in values)
    return f"{prefix}:{hashlib.sha256(blob.encode('utf-8')).hexdigest()[:20]}"


def _load_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "items", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def load_phase0_3_artifacts(input_dir: str | Path) -> dict[str, Any]:
    root = Path(input_dir).resolve()
    required = {
        "inventory": "trace_net_nha_page_inventory_v1.json",
        "anchors": "trace_net_nha_assembly_anchors_v1.json",
        "rows": "trace_net_nha_ipl_rows_v1.json",
        "relationships": "trace_net_nha_relationships_v1.json",
    }
    missing = [name for name in required.values() if not (root / name).exists()]
    if missing:
        raise FileNotFoundError("missing_phase0_3_artifacts: " + ", ".join(sorted(missing)))
    return {
        "input_dir": str(root),
        **{key: _load_records(root / name) for key, name in required.items()},
    }


def _nomenclature_tokens(row: Mapping[str, Any]) -> list[str]:
    text = str(row.get("nomenclature") or "").upper()
    tokens = re.findall(r"[A-Z][A-Z0-9-]*", text)
    return [token for token in tokens if token not in NOISE_TOKENS and not token.isdigit()]


def nomenclature_head(row: Mapping[str, Any]) -> str:
    tokens = _nomenclature_tokens(row)
    while tokens and tokens[0] in {"A", "AN", "THE"}:
        tokens.pop(0)
    return tokens[0] if tokens else ""


def is_attaching_hardware(row: Mapping[str, Any]) -> bool:
    """Classify only narrow, conventional hardware nouns as attaching parts.

    Words such as SUPPORT, PLATE, STRUCTURE, SEAT, and PROTECTOR are deliberately
    excluded even when their nomenclature contains ATTACH.  This prevents a sticky
    OCR ATTACHING PARTS marker from flattening the rest of an IPL page.
    """
    head = nomenclature_head(row)
    if head in HARDWARE_HEADS:
        return True
    part = str(row.get("part_number") or "").upper()
    return bool(
        re.fullmatch(r"(?:NAS|MS|AN)[A-Z0-9-]{4,}", part)
        and head not in SUBSTANTIVE_HEADS
    )


def normalized_component_family(row: Mapping[str, Any]) -> str:
    tokens = _nomenclature_tokens(row)
    cleaned: list[str] = []
    for token in tokens:
        if token in {"LH", "RH", "LEFT", "RIGHT"}:
            continue
        if re.fullmatch(r"[A-Z]", token):
            continue
        cleaned.append(token)
    return " ".join(cleaned[:5]) or str(row.get("part_number") or "")


def _anchor_by_page(anchors: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for anchor in anchors:
        grouped[str(anchor.get("page_id") or "")].append(dict(anchor))
    output: dict[str, dict[str, Any]] = {}
    for page_id, values in grouped.items():
        values.sort(key=lambda row: (int(row.get("sheet") or 0), str(row.get("anchor_id") or "")))
        output[page_id] = values[0]
    return output


def _figure_sort_key(anchor: Mapping[str, Any]) -> tuple[int, int, str]:
    raw = str(anchor.get("figure") or "")
    match = re.search(r"\d+", raw)
    figure_num = int(match.group(0)) if match else 10**9
    return figure_num, int(anchor.get("sheet") or 0), str(anchor.get("page_id") or "")


def _row_sort_key(row: Mapping[str, Any], page_order: Mapping[str, int]) -> tuple[int, int, str]:
    return (
        int(page_order.get(str(row.get("page_id") or ""), 10**9)),
        int(row.get("ocr_line_number") or 0),
        str(row.get("row_id") or ""),
    )


def _variant_group(rows: Sequence[Mapping[str, Any]], index: int) -> list[dict[str, Any]]:
    """Return contiguous same-nomenclature component variants ending at index."""
    current = dict(rows[index])
    family = normalized_component_family(current)
    output = [current]
    cursor = index - 1
    while cursor >= 0:
        prior = rows[cursor]
        if prior.get("row_type") != "component" or is_attaching_hardware(prior):
            break
        if normalized_component_family(prior) != family:
            break
        output.insert(0, dict(prior))
        cursor -= 1
    return output


def resolve_hierarchy(
    inventory: Sequence[Mapping[str, Any]],
    anchors: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    page_order = {
        str(row.get("canonical_page_id") or ""): int(row.get("page_ordinal") or 0)
        for row in inventory
    }
    anchors_by_page = _anchor_by_page(anchors)
    figure_pages: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for anchor in anchors:
        key = (str(anchor.get("figure") or ""), str(anchor.get("assembly_identifier_as_printed") or ""))
        figure_pages[key].append(dict(anchor))

    rows_by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_page[str(row.get("page_id") or "")].append(dict(row))

    hierarchy_rows: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    attaching_groups: list[dict[str, Any]] = []

    for key, figure_anchors in sorted(figure_pages.items(), key=lambda item: _figure_sort_key(sorted(item[1], key=_figure_sort_key)[0])):
        figure_anchors.sort(key=lambda anchor: (page_order.get(str(anchor.get("page_id") or ""), 10**9), int(anchor.get("sheet") or 0)))
        top_parts = list(dict.fromkeys(
            str(part).upper()
            for anchor in figure_anchors
            for part in anchor.get("assembly_part_variants") or []
            if str(part).strip()
        ))
        printed_parent = str(figure_anchors[0].get("assembly_identifier_as_printed") or "")
        assembly_name = str(figure_anchors[0].get("assembly_name") or "")
        figure = str(figure_anchors[0].get("figure") or "")
        figure_rows: list[dict[str, Any]] = []
        for anchor in figure_anchors:
            figure_rows.extend(rows_by_page.get(str(anchor.get("page_id") or ""), []))
        figure_rows.sort(key=lambda row: _row_sort_key(row, page_order))
        component_rows = [row for row in figure_rows if row.get("row_type") == "component"]
        current_variants: list[dict[str, Any]] = []
        active_group: dict[str, Any] | None = None

        for index, row in enumerate(component_rows):
            hardware = is_attaching_hardware(row)
            raw_attach = bool(row.get("attaching_parts_context"))

            if hardware and raw_attach and current_variants:
                immediate_candidates = list(dict.fromkeys(
                    str(parent.get("part_number") or "").upper()
                    for parent in current_variants
                    if str(parent.get("part_number") or "").strip()
                ))
                if active_group is None or active_group.get("parent_candidates") != immediate_candidates:
                    active_group = {
                        "group_id": _stable_id("nha_attach_group", figure, row.get("page_id"), row.get("row_id"), immediate_candidates),
                        "schema_version": SCHEMA_VERSION,
                        "truth_mode": "real_source",
                        "source_truth": True,
                        "figure": figure,
                        "top_assembly_candidates": top_parts,
                        "parent_candidates": immediate_candidates,
                        "start_row_id": row.get("row_id") or "",
                        "start_page_id": row.get("page_id") or "",
                        "child_row_ids": [],
                        "child_parts": [],
                        "resolution_status": "source_supported" if len(immediate_candidates) == 1 else "ambiguous",
                        "boundary_method": "hardware_noun_after_attaching_parts_marker",
                        "source_truth_mutation_allowed": False,
                    }
                    attaching_groups.append(active_group)
                active_group["child_row_ids"].append(row.get("row_id") or "")
                active_group["child_parts"].append(row.get("part_number") or "")
                parent_candidates = immediate_candidates
                direct_parent = parent_candidates[0] if len(parent_candidates) == 1 else ""
                status = "source_supported" if direct_parent else "ambiguous"
                relation_type = "attaching_part_of" if direct_parent else "attaching_part_candidate"
                depth = 2
                boundary = "attaching_hardware_to_nearest_component_group"
            else:
                # A substantive row closes a sticky ATTACHING PARTS region and is a
                # direct child candidate of the figure-title assembly.
                active_group = None
                current_variants = _variant_group(component_rows, index)
                parent_candidates = top_parts
                direct_parent = parent_candidates[0] if len(parent_candidates) == 1 else ""
                status = "source_supported" if direct_parent else "ambiguous"
                relation_type = "direct_component" if direct_parent else "direct_component_candidate"
                depth = 1
                boundary = (
                    "substantive_component_closes_sticky_attaching_region"
                    if raw_attach else "figure_title_direct_component"
                )

            top_direct = top_parts[0] if len(top_parts) == 1 else ""
            hierarchy_row = {
                "schema_version": SCHEMA_VERSION,
                "hierarchy_row_id": _stable_id("nha_hierarchy_row", row.get("row_id"), direct_parent, depth),
                "truth_mode": "real_source",
                "source_truth": True,
                "production_visible": True,
                "row_id": row.get("row_id") or "",
                "page_id": row.get("page_id") or "",
                "figure": figure,
                "item_number": row.get("item_number") or "",
                "part_number": row.get("part_number") or "",
                "nomenclature": row.get("nomenclature") or "",
                "quantity": row.get("quantity") or "",
                "raw_indentation_level": int(row.get("indentation_level") or 0),
                "resolved_hierarchy_depth": depth,
                "resolved_role": "attaching_part" if depth == 2 else "direct_component",
                "hardware_classified": hardware,
                "raw_attaching_parts_context": raw_attach,
                "resolved_attaching_parts_context": depth == 2,
                "direct_parent_part": direct_parent,
                "direct_parent_candidates": parent_candidates,
                "top_assembly_part": top_direct,
                "top_assembly_candidates": top_parts,
                "top_assembly_identifier_as_printed": printed_parent,
                "assembly_name": assembly_name,
                "boundary_resolution_method": boundary,
                "resolution_status": status,
                "can_prove_direct_parent": status == "source_supported",
                "guidance_only": status != "source_supported",
                "source_truth_mutation_allowed": False,
            }
            hierarchy_rows.append(hierarchy_row)

            relationship_id = _stable_id(
                "nha_hierarchy_membership", row.get("row_id"), relation_type,
                direct_parent or ",".join(parent_candidates), depth,
            )
            relationships.append({
                "schema_version": SCHEMA_VERSION,
                "relationship_id": relationship_id,
                "truth_mode": "real_source",
                "source_truth": True,
                "production_visible": True,
                "relationship_type": relation_type,
                "relationship_status": status,
                "child_part": str(row.get("part_number") or "").upper(),
                "direct_nha": direct_parent,
                "parent_candidates": parent_candidates,
                "top_assembly_part": top_direct,
                "top_assembly_candidates": top_parts,
                "ancestor_candidates": top_parts if depth > 1 else [],
                "hierarchy_depth": depth,
                "direct_child_of_top_assembly": depth == 1,
                "lower_descendant_of_top_assembly": depth > 1,
                "attaching_parts_context": depth == 2,
                "quantity": row.get("quantity") or "",
                "item_number": row.get("item_number") or "",
                "figure": figure,
                "row_page_id": row.get("page_id") or "",
                "anchor_page_ids": list(dict.fromkeys(str(anchor.get("page_id") or "") for anchor in figure_anchors)),
                "row_id": row.get("row_id") or "",
                "boundary_resolution_method": boundary,
                "ambiguity_reason": "" if status == "source_supported" else (
                    "multiple_immediate_component_variants" if depth > 1
                    else "multiple_top_assembly_variants_require_usage_or_effectivity_resolution"
                ),
                "can_prove_direct_nha": status == "source_supported",
                "guidance_only": status != "source_supported",
                "source_truth_mutation_allowed": False,
            })

    # Deduplicate in case multiple anchor pages repeat the same figure title.
    def dedup(rows_in: Iterable[dict[str, Any]], id_key: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value in rows_in:
            key_value = str(value.get(id_key) or "")
            if not key_value or key_value in seen:
                continue
            seen.add(key_value)
            output.append(value)
        return output

    return (
        dedup(hierarchy_rows, "hierarchy_row_id"),
        dedup(relationships, "relationship_id"),
        dedup(attaching_groups, "group_id"),
    )


def _detect_cycles(relationships: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for row in relationships:
        if row.get("relationship_status") != "source_supported":
            continue
        child = str(row.get("child_part") or "")
        parent = str(row.get("direct_nha") or "")
        if child and parent:
            graph[child].add(parent)
    cycles: list[list[str]] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> None:
        if node in visiting:
            start = stack.index(node) if node in stack else 0
            cycles.append(stack[start:] + [node])
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for parent in sorted(graph.get(node, set())):
            visit(parent)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)
    return cycles


def validate_phase4(
    hierarchy_rows: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
    attaching_groups: Sequence[Mapping[str, Any]],
    *,
    minimum_supported: int = 1,
    minimum_attaching_supported: int = 1,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    ids = [str(row.get("relationship_id") or "") for row in relationships]
    if len(ids) != len(set(ids)):
        failures.append("duplicate_hierarchy_relationship_id")
    if any(row.get("truth_mode") != "real_source" or not row.get("source_truth") for row in [*hierarchy_rows, *relationships, *attaching_groups]):
        failures.append("synthetic_or_non_source_truth_record_in_phase4")
    for row in relationships:
        status = str(row.get("relationship_status") or "")
        depth = int(row.get("hierarchy_depth") or 0)
        child = str(row.get("child_part") or "")
        parent = str(row.get("direct_nha") or "")
        if depth not in {1, 2}:
            failures.append(f"invalid_hierarchy_depth:{row.get('relationship_id')}:{depth}")
        if child and parent and child == parent:
            failures.append(f"self_parent_relationship:{row.get('relationship_id')}")
        if status == "source_supported":
            if not parent or len(row.get("parent_candidates") or []) != 1:
                failures.append(f"supported_parent_not_unique:{row.get('relationship_id')}")
            if row.get("guidance_only") or not row.get("can_prove_direct_nha"):
                failures.append(f"supported_relationship_contract_invalid:{row.get('relationship_id')}")
        elif row.get("can_prove_direct_nha"):
            failures.append(f"ambiguous_relationship_can_prove:{row.get('relationship_id')}")
        if depth == 2 and row.get("direct_child_of_top_assembly"):
            failures.append(f"attaching_part_flattened_to_top:{row.get('relationship_id')}")
        if depth == 1 and row.get("lower_descendant_of_top_assembly"):
            failures.append(f"direct_component_marked_lower_descendant:{row.get('relationship_id')}")

    cycles = _detect_cycles(relationships)
    if cycles:
        failures.append(f"hierarchy_cycle_count:{len(cycles)}")
    supported = sum(row.get("relationship_status") == "source_supported" for row in relationships)
    attaching_supported = sum(
        row.get("relationship_status") == "source_supported" and row.get("hierarchy_depth") == 2
        for row in relationships
    )
    if supported < minimum_supported:
        failures.append(f"supported_relationships_below_minimum expected>={minimum_supported} actual={supported}")
    if attaching_supported < minimum_attaching_supported:
        failures.append(f"supported_attaching_relationships_below_minimum expected>={minimum_attaching_supported} actual={attaching_supported}")
    if not relationships:
        warnings.append("no_hierarchy_relationships")

    counts = Counter(str(row.get("relationship_status") or "") for row in relationships)
    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "hierarchy_rows": len(hierarchy_rows),
            "hierarchy_relationships": len(relationships),
            "source_supported_relationships": supported,
            "ambiguous_relationships": counts.get("ambiguous", 0),
            "direct_component_relationships": sum(int(row.get("hierarchy_depth") or 0) == 1 for row in relationships),
            "lower_descendant_relationships": sum(int(row.get("hierarchy_depth") or 0) == 2 for row in relationships),
            "source_supported_attaching_relationships": attaching_supported,
            "attaching_groups": len(attaching_groups),
            "cycle_count": len(cycles),
            "synthetic_record_count": 0,
            "production_graph_write_count": 0,
        },
        "cycles": cycles,
        "safety_contract": {
            "read_only": True,
            "phase0_3_artifacts_mutated": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "llm_call_count": 0,
            "synthetic_records_allowed": False,
            "ambiguous_relationships_promoted_to_proof": False,
            "attaching_parts_never_flattened_to_top_assembly": True,
        },
    }


def build_answer_key(relationships: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for row in relationships:
        child = str(row.get("child_part") or "")
        direct = str(row.get("direct_nha") or "")
        status = str(row.get("relationship_status") or "")
        depth = int(row.get("hierarchy_depth") or 0)
        cases.append({
            "case_id": _stable_id("nha_phase4_case", row.get("relationship_id")),
            "truth_mode": "real_source",
            "question": f"What is the direct next higher assembly of part {child}?",
            "child_part": child,
            "expected_behavior": "direct_answer" if status == "source_supported" else "candidate_or_clarification",
            "expected_direct_nha": direct,
            "expected_parent_candidates": list(row.get("parent_candidates") or []),
            "expected_hierarchy_depth": depth,
            "expected_role": "attaching_part" if depth == 2 else "direct_component",
            "expected_top_assembly_candidates": list(row.get("top_assembly_candidates") or []),
            "expected_relationship_order": [child, direct] if direct else [child, *list(row.get("parent_candidates") or [])],
            "expected_figure": row.get("figure") or "",
            "expected_item_number": row.get("item_number") or "",
            "expected_quantity": row.get("quantity") or "",
            "expected_pages": list(dict.fromkeys([
                str(row.get("row_page_id") or ""),
                *[str(value) for value in row.get("anchor_page_ids") or []],
            ])),
            "must_not_claim": [
                "An attaching part is a direct child of the top assembly",
                "An ambiguous parent candidate is confirmed",
            ] if status != "source_supported" or depth > 1 else [],
            "source_relationship_id": row.get("relationship_id") or "",
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "truth_mode": "real_source",
        "case_count": len(cases),
        "direct_answer_case_count": sum(row["expected_behavior"] == "direct_answer" for row in cases),
        "candidate_case_count": sum(row["expected_behavior"] != "direct_answer" for row in cases),
        "direct_component_case_count": sum(row["expected_hierarchy_depth"] == 1 for row in cases),
        "lower_descendant_case_count": sum(row["expected_hierarchy_depth"] == 2 for row in cases),
        "cases": cases,
    }


def build_graph_bundle(
    inventory: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    part_ids: set[str] = set()
    page_ids = {
        str(row.get("canonical_page_id") or "")
        for row in inventory if str(row.get("canonical_page_id") or "")
    }
    for page_id in sorted(page_ids):
        nodes.append({"node_id": f"page:{page_id}", "node_type": "PageReference", "properties": {"page_id": page_id}})
    for row in relationships:
        child = str(row.get("child_part") or "")
        parents = [str(value) for value in row.get("parent_candidates") or []]
        top_parts = [str(value) for value in row.get("top_assembly_candidates") or []]
        for part in [child, *parents, *top_parts]:
            if part and part not in part_ids:
                part_ids.add(part)
                nodes.append({"node_id": f"part:{part}", "node_type": "Part", "properties": {"part_number": part, "truth_mode": "real_source"}})
        membership = str(row.get("relationship_id") or "")
        nodes.append({"node_id": membership, "node_type": "AssemblyMembership", "properties": dict(row)})
        if child:
            edges.append({"edge_type": "MEMBER_IN", "from": f"part:{child}", "to": membership, "properties": {}})
        for parent in parents:
            edges.append({"edge_type": "PARENT_ASSEMBLY", "from": membership, "to": f"part:{parent}", "properties": {"candidate": row.get("relationship_status") != "source_supported"}})
        for page_id in dict.fromkeys([str(row.get("row_page_id") or ""), *[str(v) for v in row.get("anchor_page_ids") or []]]):
            if page_id:
                edges.append({"edge_type": "EVIDENCED_BY_PAGE", "from": membership, "to": f"page:{page_id}", "properties": {}})
        if row.get("relationship_status") == "source_supported" and child and row.get("direct_nha"):
            parent = str(row.get("direct_nha"))
            props = {"relationship_id": membership, "hierarchy_depth": row.get("hierarchy_depth"), "source_supported": True}
            edges.append({"edge_type": "DIRECT_COMPONENT_OF", "from": f"part:{child}", "to": f"part:{parent}", "properties": props})
            edges.append({"edge_type": "HAS_DIRECT_COMPONENT", "from": f"part:{parent}", "to": f"part:{child}", "properties": props})
            if int(row.get("hierarchy_depth") or 0) > 1:
                for top in top_parts:
                    if top != parent:
                        edges.append({
                            "edge_type": "LOWER_DESCENDANT_OF",
                            "from": f"part:{child}",
                            "to": f"part:{top}",
                            "properties": {
                                "relationship_id": membership,
                                "derived_hop_count": 2,
                                "direct_relationship": False,
                                "guidance_only": len(top_parts) != 1,
                            },
                        })
    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "truth_mode": "real_source",
        "read_only": True,
        "source_truth_mutation_allowed": False,
        "nodes": nodes,
        "edges": edges,
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "parts": len(part_ids),
            "memberships": len(relationships),
            "source_supported_memberships": sum(row.get("relationship_status") == "source_supported" for row in relationships),
            "lower_descendant_edges": sum(edge.get("edge_type") == "LOWER_DESCENDANT_OF" for edge in edges),
        },
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def build_phase4(
    *,
    phase0_3_dir: str | Path,
    output_dir: str | Path,
    minimum_supported: int = 1,
    minimum_attaching_supported: int = 1,
) -> dict[str, Any]:
    source = load_phase0_3_artifacts(phase0_3_dir)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    hierarchy_rows, relationships, attaching_groups = resolve_hierarchy(
        source["inventory"], source["anchors"], source["rows"]
    )
    validation = validate_phase4(
        hierarchy_rows,
        relationships,
        attaching_groups,
        minimum_supported=minimum_supported,
        minimum_attaching_supported=minimum_attaching_supported,
    )
    answer_key = build_answer_key(relationships)
    graph = build_graph_bundle(source["inventory"], relationships)

    write_json(output / "trace_net_nha_hierarchy_rows_v1.json", {"records": hierarchy_rows})
    write_jsonl(output / "trace_net_nha_hierarchy_rows_v1.jsonl", hierarchy_rows)
    write_json(output / "trace_net_nha_hierarchy_relationships_v1.json", {"records": relationships})
    write_jsonl(output / "trace_net_nha_hierarchy_relationships_v1.jsonl", relationships)
    write_json(output / "trace_net_nha_attaching_groups_v1.json", {"records": attaching_groups})
    write_json(output / "trace_net_nha_phase4_answer_key_v1.json", answer_key)
    write_json(output / "trace_net_nha_phase4_graph_bundle_v1.json", graph)
    write_json(output / "trace_net_nha_phase4_quality_v1.json", validation)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "quality_status": validation["quality_status"],
        "phase0_3_dir": source["input_dir"],
        "output_dir": str(output),
        "input_counts": {
            "inventory_pages": len(source["inventory"]),
            "assembly_anchors": len(source["anchors"]),
            "ipl_rows": len(source["rows"]),
            "phase0_3_relationships": len(source["relationships"]),
        },
        "phase4_counts": validation["counts"],
        "failures": validation["failures"],
        "warnings": validation["warnings"],
        "artifacts": sorted(path.name for path in output.glob("trace_net_nha_phase4_*.json")) + [
            "trace_net_nha_hierarchy_rows_v1.json",
            "trace_net_nha_hierarchy_rows_v1.jsonl",
            "trace_net_nha_hierarchy_relationships_v1.json",
            "trace_net_nha_hierarchy_relationships_v1.jsonl",
            "trace_net_nha_attaching_groups_v1.json",
        ],
    }
    write_json(output / "trace_net_nha_phase4_summary_v1.json", summary)
    return summary
