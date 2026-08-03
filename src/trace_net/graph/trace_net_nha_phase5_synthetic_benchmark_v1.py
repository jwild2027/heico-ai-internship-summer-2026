#!/usr/bin/env python3
"""TRACE-Net NHA phase N5: deterministic synthetic relationship benchmark overlay.

The overlay is benchmark-only. It does not modify TIFF pages, OCR, N0-N4
artifacts, source truth, Postgres, Qdrant, OpenSearch, or the production graph.
All synthetic nodes and edges are explicitly isolated and production-invisible.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MODULE = "trace_net_nha_phase5_synthetic_benchmark_v1"
STATUS = "TRACE_NET_NHA_PHASE5_SYNTHETIC_BENCHMARK_V1"
SCHEMA_VERSION = "trace_net_nha_phase5_synthetic_benchmark_v1"
DEFAULT_SEED = "TRACE_NET_NHA_SYNTHETIC_SEED_V1_20260729"

CASE_COUNTS = {
    "simple_direct": 6,
    "three_hop_chain": 4,
    "direct_children": 4,
    "direct_and_descendants": 4,
    "same_child_two_projects": 3,
    "revision_change": 3,
    "attaching_parts": 2,
    "contradiction": 2,
    "no_nha": 2,
}
EXPECTED_SCENARIO_COUNT = sum(CASE_COUNTS.values())
EXPECTED_QUESTION_COUNT = EXPECTED_SCENARIO_COUNT * 2
SYNTHETIC_PART_RE = re.compile(r"^990-\d{5}-\d{3}$")


def _compact(value: Any, limit: int = 20000) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _stable_id(prefix: str, *values: Any) -> str:
    blob = "|".join(_compact(value, 5000) for value in values)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "items", "rows", "cases", "questions"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def load_inputs(phase0_3_dir: str | Path, phase4_dir: str | Path) -> dict[str, Any]:
    phase0 = Path(phase0_3_dir).resolve()
    phase4 = Path(phase4_dir).resolve()
    inventory_path = phase0 / "trace_net_nha_page_inventory_v1.json"
    relationships_path = phase4 / "trace_net_nha_hierarchy_relationships_v1.json"
    quality_path = phase4 / "trace_net_nha_phase4_quality_v1.json"
    required = [inventory_path, relationships_path, quality_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing_nha_phase5_inputs: " + ", ".join(missing))
    inventory = _records(_read_json(inventory_path))
    relationships = _records(_read_json(relationships_path))
    quality = _read_json(quality_path)
    if str(quality.get("quality_status") or "") != "PASS":
        raise ValueError("phase4_quality_status_not_pass")
    return {
        "phase0_3_dir": str(phase0),
        "phase4_dir": str(phase4),
        "inventory_path": str(inventory_path),
        "phase4_relationships_path": str(relationships_path),
        "inventory_sha256": _sha256_file(inventory_path),
        "phase4_relationships_sha256": _sha256_file(relationships_path),
        "inventory": inventory,
        "real_phase4_relationships": relationships,
    }


def _seed_int(seed: str) -> int:
    return int(hashlib.sha256(str(seed).encode("utf-8")).hexdigest()[:16], 16)


def _synthetic_flags() -> dict[str, Any]:
    return {
        "truth_mode": "synthetic_benchmark",
        "source_truth": False,
        "production_visible": False,
        "synthetic_overlay_only": True,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
    }


def _part(series: int, suffix: int = 1) -> str:
    return f"990-{series:05d}-{suffix:03d}"


def _project(index: int, variant: str = "A") -> str:
    return f"SYN-PROJECT-{index:02d}{variant}"


def _configuration(index: int, variant: str = "A") -> str:
    return f"SYN-CONFIG-{index:02d}{variant}"


def _revision(index: int, variant: str = "A") -> str:
    return f"SYN-REV-{index:02d}{variant}"


def choose_pages(inventory: Sequence[Mapping[str, Any]], count: int, seed: str) -> list[dict[str, Any]]:
    eligible = [
        dict(row)
        for row in inventory
        if row.get("source_exists")
        and str(row.get("canonical_page_id") or "")
        and str(row.get("tiff_filename") or "")
    ]
    eligible.sort(key=lambda row: int(row.get("page_ordinal") or 0))
    if len(eligible) < count:
        raise ValueError(f"insufficient_inventory_pages required={count} actual={len(eligible)}")
    rng = random.Random(_seed_int(seed))
    return rng.sample(eligible, count)


class PageAllocator:
    def __init__(self, pages: Sequence[Mapping[str, Any]], seed: str):
        self._pages = [dict(page) for page in pages]
        self._cursor = 0
        self.seed = seed

    def next(self) -> dict[str, Any]:
        if self._cursor >= len(self._pages):
            raise IndexError("synthetic_page_allocator_exhausted")
        page = dict(self._pages[self._cursor])
        self._cursor += 1
        return page


def _base_scenario(index: int, case_type: str, seed: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": f"SYN-NHA-{index:03d}",
        "case_type": case_type,
        "seed": seed,
        "project_ids": [],
        "configuration_ids": [],
        "revision_ids": [],
        "relationship_ids": [],
        "assigned_page_ids": [],
        "expected_behavior": "direct_answer",
        **_synthetic_flags(),
    }


def _relationship(
    scenario: Mapping[str, Any],
    *,
    child: str,
    parent: str,
    project_id: str,
    configuration_id: str,
    revision_id: str,
    page: Mapping[str, Any],
    item_number: str,
    quantity: str,
    hop_index: int,
    top_assembly: str,
    relation_kind: str = "direct_component",
    benchmark_truth_status: str = "confirmed",
    parent_candidates: Sequence[str] | None = None,
) -> dict[str, Any]:
    candidates = list(parent_candidates or ([parent] if parent else []))
    relationship_id = _stable_id(
        "synthetic_nha_membership",
        scenario.get("scenario_id"), child, parent, project_id,
        configuration_id, revision_id, item_number, hop_index,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "relationship_id": relationship_id,
        "scenario_id": scenario.get("scenario_id"),
        "case_type": scenario.get("case_type"),
        "child_part": child,
        "direct_nha": parent if benchmark_truth_status == "confirmed" else "",
        "parent_candidates": candidates,
        "top_assembly_part": top_assembly,
        "project_id": project_id,
        "configuration_id": configuration_id,
        "revision_id": revision_id,
        "item_number": item_number,
        "quantity": quantity,
        "figure": f"SYN-{scenario.get('scenario_id', '').split('-')[-1]}",
        "hop_index": hop_index,
        "relationship_type": relation_kind,
        "benchmark_truth_status": benchmark_truth_status,
        "assigned_page_id": str(page.get("canonical_page_id") or ""),
        "assigned_tiff_filename": str(page.get("tiff_filename") or ""),
        "assigned_page_ordinal": int(page.get("page_ordinal") or 0),
        "benchmark_assertion_only": True,
        "can_prove_benchmark_answer": benchmark_truth_status == "confirmed",
        "must_not_support_production_claim": True,
        **_synthetic_flags(),
    }


def _page_assignment(
    scenario: Mapping[str, Any],
    relationship: Mapping[str, Any] | None,
    page: Mapping[str, Any],
    trait_text: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "assignment_id": _stable_id(
            "synthetic_page_assignment",
            scenario.get("scenario_id"),
            relationship.get("relationship_id") if relationship else "no_relationship",
            page.get("canonical_page_id"),
        ),
        "scenario_id": scenario.get("scenario_id"),
        "relationship_id": relationship.get("relationship_id") if relationship else "",
        "case_type": scenario.get("case_type"),
        "page_id": str(page.get("canonical_page_id") or ""),
        "tiff_filename": str(page.get("tiff_filename") or ""),
        "page_ordinal": int(page.get("page_ordinal") or 0),
        "synthetic_trait_text": trait_text,
        "physical_tiff_modified": False,
        "ocr_source_modified": False,
        "benchmark_indexable": True,
        **_synthetic_flags(),
    }


def _question(
    scenario: Mapping[str, Any],
    number: int,
    *,
    category: str,
    query: str,
    expected_behavior: str,
    expected_direct_nha: str = "",
    expected_chain: Sequence[str] | None = None,
    expected_direct_children: Sequence[str] | None = None,
    expected_parent_candidates: Sequence[str] | None = None,
    expected_pages: Sequence[str] | None = None,
    expected_project_id: str = "",
    expected_configuration_id: str = "",
    expected_revision_id: str = "",
    expected_item_order: Sequence[str] | None = None,
    must_not_claim: Sequence[str] | None = None,
) -> dict[str, Any]:
    question_id = f"{scenario.get('scenario_id')}-Q{number}"
    return {
        "schema_version": SCHEMA_VERSION,
        "question_id": question_id,
        "scenario_id": scenario.get("scenario_id"),
        "case_type": scenario.get("case_type"),
        "category": category,
        "query": query,
        "expected_behavior": expected_behavior,
        "expected_direct_nha": expected_direct_nha,
        "expected_chain": list(expected_chain or []),
        "expected_direct_children": list(expected_direct_children or []),
        "expected_parent_candidates": list(expected_parent_candidates or []),
        "expected_pages": list(dict.fromkeys(str(page) for page in (expected_pages or []) if str(page))),
        "expected_project_id": expected_project_id,
        "expected_configuration_id": expected_configuration_id,
        "expected_revision_id": expected_revision_id,
        "expected_item_order": list(expected_item_order or []),
        "must_not_claim": list(must_not_claim or []),
        "answer_key_id": _stable_id("synthetic_answer_key", question_id),
        **_synthetic_flags(),
    }


def build_synthetic_benchmark(
    inventory: Sequence[Mapping[str, Any]],
    *,
    seed: str = DEFAULT_SEED,
) -> dict[str, Any]:
    # Canonical plan uses 68 distinct real page identifiers as retrieval anchors:
    # one per synthetic relationship plus one for each no-NHA case.
    pages = choose_pages(inventory, 68, seed)
    allocator = PageAllocator(pages, seed)
    scenarios: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    scenario_index = 0

    def add_scenario(case_type: str) -> dict[str, Any]:
        nonlocal scenario_index
        scenario_index += 1
        scenario = _base_scenario(scenario_index, case_type, seed)
        scenarios.append(scenario)
        return scenario

    def add_relation(scenario: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        page = allocator.next()
        relation = _relationship(scenario, page=page, **kwargs)
        relationships.append(relation)
        scenario["relationship_ids"].append(relation["relationship_id"])
        scenario["assigned_page_ids"].append(relation["assigned_page_id"])
        trait = (
            f"SYNTHETIC BENCHMARK ONLY. Scenario {scenario['scenario_id']}. "
            f"Project {relation['project_id']}; configuration {relation['configuration_id']}; "
            f"revision {relation['revision_id']}; item {relation['item_number']}; "
            f"part {relation['child_part']} has parent candidate(s) "
            f"{', '.join(relation['parent_candidates']) or 'none'}; hop {relation['hop_index']}."
        )
        assignments.append(_page_assignment(scenario, relation, page, trait))
        return relation

    # 1) Six simple direct child -> NHA cases.
    for offset in range(CASE_COUNTS["simple_direct"]):
        scenario = add_scenario("simple_direct")
        base = 91001 + offset
        child, parent = _part(base, 1), _part(base + 100, 1)
        project, config, revision = _project(scenario_index), _configuration(scenario_index), _revision(scenario_index)
        relation = add_relation(
            scenario, child=child, parent=parent, project_id=project,
            configuration_id=config, revision_id=revision, item_number="10",
            quantity="2", hop_index=1, top_assembly=parent,
        )
        scenario.update(project_ids=[project], configuration_ids=[config], revision_ids=[revision], expected_relationship_order=[child, parent])
        questions.extend([
            _question(scenario, 1, category="direct_nha", query=f"What is the direct NHA of synthetic part {child}?", expected_behavior="direct_answer", expected_direct_nha=parent, expected_chain=[child, parent], expected_pages=[relation["assigned_page_id"]], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision),
            _question(scenario, 2, category="relationship_evidence_page", query=f"Which benchmark page carries the synthetic relationship for {child} and what item/quantity are recorded?", expected_behavior="page_and_trait_answer", expected_direct_nha=parent, expected_pages=[relation["assigned_page_id"]], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision, expected_item_order=["10"], must_not_claim=["The physical TIFF itself contains the synthetic trait"]),
        ])

    # 2) Four three-hop leaf -> top chains.
    for offset in range(CASE_COUNTS["three_hop_chain"]):
        scenario = add_scenario("three_hop_chain")
        base = 92001 + offset * 10
        leaf, parent1, parent2, top = (_part(base + i, 1) for i in range(4))
        project, config, revision = _project(scenario_index), _configuration(scenario_index), _revision(scenario_index)
        rels = [
            add_relation(scenario, child=leaf, parent=parent1, project_id=project, configuration_id=config, revision_id=revision, item_number="10", quantity="4", hop_index=1, top_assembly=top),
            add_relation(scenario, child=parent1, parent=parent2, project_id=project, configuration_id=config, revision_id=revision, item_number="20", quantity="1", hop_index=2, top_assembly=top),
            add_relation(scenario, child=parent2, parent=top, project_id=project, configuration_id=config, revision_id=revision, item_number="30", quantity="1", hop_index=3, top_assembly=top),
        ]
        chain = [leaf, parent1, parent2, top]
        scenario.update(project_ids=[project], configuration_ids=[config], revision_ids=[revision], expected_relationship_order=chain)
        questions.extend([
            _question(scenario, 1, category="ancestor_chain", query=f"Show the ordered synthetic assembly chain above {leaf}.", expected_behavior="ordered_chain_answer", expected_direct_nha=parent1, expected_chain=chain, expected_pages=[r["assigned_page_id"] for r in rels], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision, expected_item_order=["10", "20", "30"], must_not_claim=[f"{parent2} is the direct NHA of {leaf}", f"{top} is the direct NHA of {leaf}"]),
            _question(scenario, 2, category="direct_nha", query=f"Which single part is the direct NHA of {leaf}, not merely a higher ancestor?", expected_behavior="direct_answer", expected_direct_nha=parent1, expected_chain=chain, expected_pages=[rels[0]["assigned_page_id"]], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision),
        ])

    # 3) Four parents with four direct children each.
    for offset in range(CASE_COUNTS["direct_children"]):
        scenario = add_scenario("direct_children")
        base = 93001 + offset * 10
        parent = _part(base, 1)
        children = [_part(base + i, 1) for i in range(1, 5)]
        project, config, revision = _project(scenario_index), _configuration(scenario_index), _revision(scenario_index)
        rels = []
        for child_index, child in enumerate(children, 1):
            rels.append(add_relation(scenario, child=child, parent=parent, project_id=project, configuration_id=config, revision_id=revision, item_number=str(child_index * 10), quantity=str(child_index), hop_index=1, top_assembly=parent))
        scenario.update(project_ids=[project], configuration_ids=[config], revision_ids=[revision], expected_relationship_order=[parent, *children])
        questions.extend([
            _question(scenario, 1, category="direct_children", query=f"List the direct synthetic children of assembly {parent} in item order.", expected_behavior="direct_children_answer", expected_direct_children=children, expected_pages=[r["assigned_page_id"] for r in rels], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision, expected_item_order=["10", "20", "30", "40"]),
            _question(scenario, 2, category="direct_child_count", query=f"How many direct components does synthetic assembly {parent} have?", expected_behavior="count_answer", expected_direct_children=children, expected_pages=[r["assigned_page_id"] for r in rels], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision),
        ])

    # 4) Four mixed direct/lower-descendant trees.
    for offset in range(CASE_COUNTS["direct_and_descendants"]):
        scenario = add_scenario("direct_and_descendants")
        base = 94001 + offset * 10
        top, subassembly, component, hardware = (_part(base + i, 1) for i in range(4))
        project, config, revision = _project(scenario_index), _configuration(scenario_index), _revision(scenario_index)
        rels = [
            add_relation(scenario, child=subassembly, parent=top, project_id=project, configuration_id=config, revision_id=revision, item_number="10", quantity="1", hop_index=1, top_assembly=top, relation_kind="direct_component"),
            add_relation(scenario, child=component, parent=subassembly, project_id=project, configuration_id=config, revision_id=revision, item_number="20", quantity="2", hop_index=2, top_assembly=top, relation_kind="lower_component"),
            add_relation(scenario, child=hardware, parent=component, project_id=project, configuration_id=config, revision_id=revision, item_number="30", quantity="4", hop_index=3, top_assembly=top, relation_kind="attaching_part_of"),
        ]
        chain = [hardware, component, subassembly, top]
        scenario.update(project_ids=[project], configuration_ids=[config], revision_ids=[revision], expected_relationship_order=chain)
        questions.extend([
            _question(scenario, 1, category="direct_vs_descendant", query=f"Which parts are direct children of {top}, and which are lower descendants?", expected_behavior="tree_answer", expected_direct_children=[subassembly], expected_chain=chain, expected_pages=[r["assigned_page_id"] for r in rels], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision, must_not_claim=[f"{component} is a direct child of {top}", f"{hardware} is a direct child of {top}"]),
            _question(scenario, 2, category="attaching_chain", query=f"Show the exact parent order from attaching part {hardware} to top assembly {top}.", expected_behavior="ordered_chain_answer", expected_direct_nha=component, expected_chain=chain, expected_pages=[r["assigned_page_id"] for r in rels], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision, expected_item_order=["30", "20", "10"]),
        ])

    # 5) Same child, different project/configuration parents.
    for offset in range(CASE_COUNTS["same_child_two_projects"]):
        scenario = add_scenario("same_child_two_projects")
        base = 95001 + offset * 10
        child, parent_a, parent_b = _part(base, 1), _part(base + 1, 1), _part(base + 2, 1)
        project_a, project_b = _project(scenario_index, "A"), _project(scenario_index, "B")
        config_a, config_b = _configuration(scenario_index, "A"), _configuration(scenario_index, "B")
        revision = _revision(scenario_index)
        rel_a = add_relation(scenario, child=child, parent=parent_a, project_id=project_a, configuration_id=config_a, revision_id=revision, item_number="10", quantity="1", hop_index=1, top_assembly=parent_a)
        rel_b = add_relation(scenario, child=child, parent=parent_b, project_id=project_b, configuration_id=config_b, revision_id=revision, item_number="20", quantity="2", hop_index=1, top_assembly=parent_b)
        scenario.update(project_ids=[project_a, project_b], configuration_ids=[config_a, config_b], revision_ids=[revision], expected_relationship_order=[child, parent_a, parent_b])
        questions.extend([
            _question(scenario, 1, category="project_scoped_nha", query=f"In {project_a}, what is the direct NHA of {child}?", expected_behavior="direct_answer", expected_direct_nha=parent_a, expected_pages=[rel_a["assigned_page_id"]], expected_project_id=project_a, expected_configuration_id=config_a, expected_revision_id=revision, must_not_claim=[f"{parent_b} applies to {project_a}"]),
            _question(scenario, 2, category="project_comparison", query=f"Compare the direct NHA of {child} between {project_a} and {project_b}.", expected_behavior="scoped_comparison_answer", expected_parent_candidates=[parent_a, parent_b], expected_pages=[rel_a["assigned_page_id"], rel_b["assigned_page_id"]], expected_revision_id=revision, must_not_claim=["The child has one context-free universal NHA"]),
        ])

    # 6) Same child/project/configuration, different revision parent.
    for offset in range(CASE_COUNTS["revision_change"]):
        scenario = add_scenario("revision_change")
        base = 96001 + offset * 10
        child, parent_a, parent_b = _part(base, 1), _part(base + 1, 1), _part(base + 2, 1)
        project, config = _project(scenario_index), _configuration(scenario_index)
        revision_a, revision_b = _revision(scenario_index, "A"), _revision(scenario_index, "B")
        rel_a = add_relation(scenario, child=child, parent=parent_a, project_id=project, configuration_id=config, revision_id=revision_a, item_number="10", quantity="1", hop_index=1, top_assembly=parent_a)
        rel_b = add_relation(scenario, child=child, parent=parent_b, project_id=project, configuration_id=config, revision_id=revision_b, item_number="10", quantity="1", hop_index=1, top_assembly=parent_b)
        scenario.update(project_ids=[project], configuration_ids=[config], revision_ids=[revision_a, revision_b], expected_relationship_order=[child, parent_a, parent_b])
        questions.extend([
            _question(scenario, 1, category="revision_scoped_nha", query=f"In revision {revision_a}, what is the direct NHA of {child}?", expected_behavior="direct_answer", expected_direct_nha=parent_a, expected_pages=[rel_a["assigned_page_id"]], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision_a, must_not_claim=[f"{parent_b} applies to {revision_a}"]),
            _question(scenario, 2, category="revision_change", query=f"Did the direct NHA of {child} change between {revision_a} and {revision_b}?", expected_behavior="scoped_comparison_answer", expected_parent_candidates=[parent_a, parent_b], expected_pages=[rel_a["assigned_page_id"], rel_b["assigned_page_id"]], expected_project_id=project, expected_configuration_id=config, must_not_claim=["Both revision relationships apply simultaneously"]),
        ])

    # 7) Two explicit attaching-part chains.
    for offset in range(CASE_COUNTS["attaching_parts"]):
        scenario = add_scenario("attaching_parts")
        base = 97001 + offset * 10
        top, component, hardware = _part(base, 1), _part(base + 1, 1), _part(base + 2, 1)
        project, config, revision = _project(scenario_index), _configuration(scenario_index), _revision(scenario_index)
        rel_top = add_relation(scenario, child=component, parent=top, project_id=project, configuration_id=config, revision_id=revision, item_number="10", quantity="1", hop_index=1, top_assembly=top)
        rel_hw = add_relation(scenario, child=hardware, parent=component, project_id=project, configuration_id=config, revision_id=revision, item_number="20", quantity="8", hop_index=2, top_assembly=top, relation_kind="attaching_part_of")
        chain = [hardware, component, top]
        scenario.update(project_ids=[project], configuration_ids=[config], revision_ids=[revision], expected_relationship_order=chain)
        questions.extend([
            _question(scenario, 1, category="attaching_direct_nha", query=f"What is the direct NHA of synthetic attaching part {hardware}?", expected_behavior="direct_answer", expected_direct_nha=component, expected_chain=chain, expected_pages=[rel_hw["assigned_page_id"]], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision, must_not_claim=[f"{top} is the direct NHA of {hardware}"]),
            _question(scenario, 2, category="attaching_ancestor_chain", query=f"Show the complete chain from {hardware} to {top}.", expected_behavior="ordered_chain_answer", expected_direct_nha=component, expected_chain=chain, expected_pages=[rel_hw["assigned_page_id"], rel_top["assigned_page_id"]], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision),
        ])

    # 8) Two intentional same-context conflicts. No positive NHA may be asserted.
    for offset in range(CASE_COUNTS["contradiction"]):
        scenario = add_scenario("contradiction")
        base = 98001 + offset * 10
        child, parent_a, parent_b = _part(base, 1), _part(base + 1, 1), _part(base + 2, 1)
        project, config, revision = _project(scenario_index), _configuration(scenario_index), _revision(scenario_index)
        rel_a = add_relation(scenario, child=child, parent=parent_a, parent_candidates=[parent_a, parent_b], project_id=project, configuration_id=config, revision_id=revision, item_number="10", quantity="1", hop_index=1, top_assembly="", relation_kind="conflicting_parent_candidate", benchmark_truth_status="conflict")
        rel_b = add_relation(scenario, child=child, parent=parent_b, parent_candidates=[parent_a, parent_b], project_id=project, configuration_id=config, revision_id=revision, item_number="20", quantity="1", hop_index=1, top_assembly="", relation_kind="conflicting_parent_candidate", benchmark_truth_status="conflict")
        scenario.update(project_ids=[project], configuration_ids=[config], revision_ids=[revision], expected_behavior="conflict_limited", expected_relationship_order=[child, parent_a, parent_b])
        questions.extend([
            _question(scenario, 1, category="contradiction_resolution", query=f"What is the direct NHA of {child} in {project} revision {revision}?", expected_behavior="conflict_limited", expected_parent_candidates=[parent_a, parent_b], expected_pages=[rel_a["assigned_page_id"], rel_b["assigned_page_id"]], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision, must_not_claim=[f"{parent_a} is confirmed", f"{parent_b} is confirmed"]),
            _question(scenario, 2, category="conflict_evidence", query=f"Which synthetic pages conflict about the parent of {child}?", expected_behavior="conflict_evidence_answer", expected_parent_candidates=[parent_a, parent_b], expected_pages=[rel_a["assigned_page_id"], rel_b["assigned_page_id"]], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision),
        ])

    # 9) Two explicit no-NHA cases with page-level synthetic traits only.
    for offset in range(CASE_COUNTS["no_nha"]):
        scenario = add_scenario("no_nha")
        part = _part(99001 + offset, 1)
        project, config, revision = _project(scenario_index), _configuration(scenario_index), _revision(scenario_index)
        page = allocator.next()
        scenario.update(project_ids=[project], configuration_ids=[config], revision_ids=[revision], expected_behavior="no_relationship", expected_relationship_order=[part], isolated_part=part, assigned_page_ids=[str(page.get("canonical_page_id") or "")])
        assignments.append(_page_assignment(scenario, None, page, f"SYNTHETIC BENCHMARK ONLY. Scenario {scenario['scenario_id']}. Part {part} is intentionally isolated and has no recorded NHA in project {project}, configuration {config}, revision {revision}."))
        questions.extend([
            _question(scenario, 1, category="no_nha", query=f"What is the direct NHA of isolated synthetic part {part}?", expected_behavior="no_relationship", expected_pages=[str(page.get("canonical_page_id") or "")], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision, must_not_claim=["A parent exists"]),
            _question(scenario, 2, category="negative_page_retrieval", query=f"Which benchmark page states that {part} has no recorded NHA?", expected_behavior="page_and_negative_answer", expected_pages=[str(page.get("canonical_page_id") or "")], expected_project_id=project, expected_configuration_id=config, expected_revision_id=revision, must_not_claim=["The physical TIFF contains the synthetic statement"]),
        ])

    return {
        "scenarios": scenarios,
        "relationships": relationships,
        "page_assignments": assignments,
        "questions": questions,
    }


def build_answer_key(
    scenarios: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
    questions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    relationships_by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in relationships:
        relationships_by_scenario[str(row.get("scenario_id") or "")].append(dict(row))
    scenarios_by_id = {str(row.get("scenario_id") or ""): dict(row) for row in scenarios}
    cases: list[dict[str, Any]] = []
    for question in questions:
        scenario_id = str(question.get("scenario_id") or "")
        cases.append({
            "answer_key_id": question.get("answer_key_id") or "",
            "question_id": question.get("question_id") or "",
            "scenario": scenarios_by_id.get(scenario_id, {}),
            "expected": dict(question),
            "source_relationships": relationships_by_scenario.get(scenario_id, []),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "truth_mode": "synthetic_benchmark",
        "case_count": len(cases),
        "cases": cases,
        **_synthetic_flags(),
    }


def build_graph_overlay(
    scenarios: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    def add_node(node_id: str, node_type: str, properties: Mapping[str, Any]) -> None:
        if not node_id or node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append({"node_id": node_id, "node_type": node_type, "properties": {**dict(properties), **_synthetic_flags()}})

    for scenario in scenarios:
        scenario_id = str(scenario.get("scenario_id") or "")
        add_node(f"synthetic_scenario:{scenario_id}", "SyntheticBenchmarkScenario", scenario)
        for project in scenario.get("project_ids") or []:
            add_node(f"synthetic_project:{project}", "SyntheticProject", {"project_id": project})
        for config in scenario.get("configuration_ids") or []:
            add_node(f"synthetic_configuration:{config}", "SyntheticConfiguration", {"configuration_id": config})
        for revision in scenario.get("revision_ids") or []:
            add_node(f"synthetic_revision:{revision}", "SyntheticRevision", {"revision_id": revision})
        isolated = str(scenario.get("isolated_part") or "")
        if isolated:
            add_node(f"synthetic_part:{isolated}", "SyntheticPart", {"part_number": isolated})

    for assignment in assignments:
        assignment_id = str(assignment.get("assignment_id") or "")
        add_node(assignment_id, "SyntheticPageTrait", assignment)
        edges.append({
            "edge_type": "BENCHMARK_ASSIGNED_TO_PAGE",
            "from": assignment_id,
            "to": f"page_reference:{assignment.get('page_id')}",
            "properties": {"physical_tiff_modified": False, **_synthetic_flags()},
        })
        add_node(f"page_reference:{assignment.get('page_id')}", "RealPageIdentifierReference", {"page_id": assignment.get("page_id"), "tiff_filename": assignment.get("tiff_filename"), "contains_synthetic_trait": False})

    for relation in relationships:
        child = str(relation.get("child_part") or "")
        parents = [str(value) for value in relation.get("parent_candidates") or []]
        membership = str(relation.get("relationship_id") or "")
        add_node(f"synthetic_part:{child}", "SyntheticPart", {"part_number": child})
        for parent in parents:
            add_node(f"synthetic_part:{parent}", "SyntheticPart", {"part_number": parent})
        add_node(membership, "SyntheticAssemblyMembership", relation)
        edges.append({"edge_type": "BENCHMARK_MEMBER_IN", "from": f"synthetic_part:{child}", "to": membership, "properties": _synthetic_flags()})
        for parent in parents:
            edges.append({"edge_type": "BENCHMARK_PARENT_ASSEMBLY", "from": membership, "to": f"synthetic_part:{parent}", "properties": {"conflict": relation.get("benchmark_truth_status") == "conflict", **_synthetic_flags()}})
        for prefix, value in (
            ("BENCHMARK_USED_IN_PROJECT", relation.get("project_id")),
            ("BENCHMARK_APPLIES_TO_CONFIGURATION", relation.get("configuration_id")),
            ("BENCHMARK_DEFINED_IN_REVISION", relation.get("revision_id")),
        ):
            target_type = "project" if "PROJECT" in prefix else "configuration" if "CONFIGURATION" in prefix else "revision"
            edges.append({"edge_type": prefix, "from": membership, "to": f"synthetic_{target_type}:{value}", "properties": _synthetic_flags()})
        assignment = next((row for row in assignments if row.get("relationship_id") == membership), None)
        if assignment:
            edges.append({"edge_type": "BENCHMARK_EVIDENCED_BY_SYNTHETIC_TRAIT", "from": membership, "to": assignment.get("assignment_id"), "properties": _synthetic_flags()})
        if relation.get("benchmark_truth_status") == "confirmed" and relation.get("direct_nha"):
            parent = str(relation.get("direct_nha"))
            props = {"relationship_id": membership, "hop_index": relation.get("hop_index"), **_synthetic_flags()}
            edges.append({"edge_type": "BENCHMARK_DIRECT_COMPONENT_OF", "from": f"synthetic_part:{child}", "to": f"synthetic_part:{parent}", "properties": props})
            edges.append({"edge_type": "BENCHMARK_HAS_DIRECT_COMPONENT", "from": f"synthetic_part:{parent}", "to": f"synthetic_part:{child}", "properties": props})

    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "overlay_enabled_by_default": False,
        "production_graph_compatible": False,
        "nodes": nodes,
        "edges": edges,
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        **_synthetic_flags(),
    }


def _detect_cycles(relationships: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    grouped: dict[tuple[str, str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in relationships:
        if row.get("benchmark_truth_status") != "confirmed":
            continue
        scope = (
            str(row.get("project_id") or ""),
            str(row.get("configuration_id") or ""),
            str(row.get("revision_id") or ""),
        )
        child, parent = str(row.get("child_part") or ""), str(row.get("direct_nha") or "")
        if child and parent:
            grouped[scope][child].add(parent)
    cycles: list[list[str]] = []
    for scope, graph in grouped.items():
        visiting: set[str] = set()
        visited: set[str] = set()
        stack: list[str] = []

        def visit(node: str) -> None:
            if node in visiting:
                start = stack.index(node) if node in stack else 0
                cycles.append([*scope, *stack[start:], node])
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


def validate_phase5(
    inventory: Sequence[Mapping[str, Any]],
    scenarios: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    questions: Sequence[Mapping[str, Any]],
    graph: Mapping[str, Any],
    *,
    expected_scenario_count: int = EXPECTED_SCENARIO_COUNT,
    expected_question_count: int = EXPECTED_QUESTION_COUNT,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    inventory_pages = {str(row.get("canonical_page_id") or "") for row in inventory}
    scenario_ids = [str(row.get("scenario_id") or "") for row in scenarios]
    relationship_ids = [str(row.get("relationship_id") or "") for row in relationships]
    assignment_ids = [str(row.get("assignment_id") or "") for row in assignments]
    question_ids = [str(row.get("question_id") or "") for row in questions]

    for label, values in (
        ("scenario", scenario_ids),
        ("relationship", relationship_ids),
        ("assignment", assignment_ids),
        ("question", question_ids),
    ):
        if len(values) != len(set(values)):
            failures.append(f"duplicate_{label}_id")

    if len(scenarios) != expected_scenario_count:
        failures.append(f"scenario_count expected={expected_scenario_count} actual={len(scenarios)}")
    if len(questions) != expected_question_count:
        failures.append(f"question_count expected={expected_question_count} actual={len(questions)}")
    counts = Counter(str(row.get("case_type") or "") for row in scenarios)
    if dict(counts) != CASE_COUNTS:
        failures.append(f"case_distribution_mismatch expected={CASE_COUNTS} actual={dict(counts)}")

    synthetic_records = [*scenarios, *relationships, *assignments, *questions]
    for row in synthetic_records:
        if row.get("truth_mode") != "synthetic_benchmark":
            failures.append("non_synthetic_truth_mode")
            break
        if row.get("source_truth") is not False or row.get("production_visible") is not False:
            failures.append("synthetic_record_visibility_contract_invalid")
            break
        if row.get("source_truth_mutation_allowed") is not False:
            failures.append("synthetic_record_source_mutation_allowed")
            break
        for key in ("answer_permission", "final_answer_allowed", "can_answer_directly", "can_prove_claims"):
            if row.get(key) is not False:
                failures.append(f"synthetic_record_safety_flag_true:{key}")
                break

    assigned_pages = [str(row.get("page_id") or "") for row in assignments]
    if len(assigned_pages) != len(set(assigned_pages)):
        failures.append("duplicate_synthetic_page_assignment")
    for row in assignments:
        page_id = str(row.get("page_id") or "")
        if page_id not in inventory_pages:
            failures.append(f"assigned_page_not_in_inventory:{page_id}")
        if row.get("physical_tiff_modified") or row.get("ocr_source_modified"):
            failures.append(f"source_page_modified:{row.get('assignment_id')}")

    for row in relationships:
        parts = [str(row.get("child_part") or ""), *[str(value) for value in row.get("parent_candidates") or []]]
        if any(part and not SYNTHETIC_PART_RE.fullmatch(part) for part in parts):
            failures.append(f"non_reserved_synthetic_part_number:{row.get('relationship_id')}")
        if row.get("benchmark_truth_status") == "confirmed":
            if not row.get("direct_nha") or len(row.get("parent_candidates") or []) != 1:
                failures.append(f"confirmed_synthetic_relationship_invalid:{row.get('relationship_id')}")
        if row.get("child_part") and row.get("direct_nha") and row.get("child_part") == row.get("direct_nha"):
            failures.append(f"synthetic_self_parent:{row.get('relationship_id')}")

    cycles = _detect_cycles(relationships)
    if cycles:
        failures.append(f"synthetic_cycle_count:{len(cycles)}")

    edge_types = [str(row.get("edge_type") or "") for row in graph.get("edges") or []]
    if any(not edge.startswith("BENCHMARK_") for edge in edge_types):
        failures.append("non_benchmark_edge_type_in_synthetic_overlay")
    forbidden = {"DIRECT_COMPONENT_OF", "HAS_DIRECT_COMPONENT", "PARENT_ASSEMBLY", "MEMBER_IN"}
    if any(edge in forbidden for edge in edge_types):
        failures.append("production_edge_type_in_synthetic_overlay")
    if graph.get("overlay_enabled_by_default") is not False or graph.get("production_graph_compatible") is not False:
        failures.append("synthetic_graph_default_or_compatibility_invalid")

    no_nha_scenarios = {str(row.get("scenario_id")) for row in scenarios if row.get("case_type") == "no_nha"}
    if any(row.get("scenario_id") in no_nha_scenarios for row in relationships):
        failures.append("no_nha_scenario_contains_relationship")
    contradiction_ids = {str(row.get("scenario_id")) for row in scenarios if row.get("case_type") == "contradiction"}
    for scenario_id in contradiction_ids:
        scoped = [row for row in relationships if row.get("scenario_id") == scenario_id]
        if len(scoped) != 2 or any(row.get("benchmark_truth_status") != "conflict" for row in scoped):
            failures.append(f"contradiction_scenario_contract_invalid:{scenario_id}")

    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "inventory_pages": len(inventory),
            "synthetic_scenarios": len(scenarios),
            "synthetic_relationships": len(relationships),
            "synthetic_page_assignments": len(assignments),
            "synthetic_questions": len(questions),
            "confirmed_benchmark_relationships": sum(row.get("benchmark_truth_status") == "confirmed" for row in relationships),
            "conflict_relationships": sum(row.get("benchmark_truth_status") == "conflict" for row in relationships),
            "no_nha_scenarios": len(no_nha_scenarios),
            "cycle_count": len(cycles),
            "production_graph_write_count": 0,
            "source_artifact_mutation_count": 0,
            "llm_call_count": 0,
        },
        "case_type_counts": dict(counts),
        "cycles": cycles,
        "safety_contract": {
            "read_only": True,
            "synthetic_overlay_enabled_by_default": False,
            "physical_tiff_modified": False,
            "ocr_source_modified": False,
            "phase0_3_artifacts_mutated": False,
            "phase4_artifacts_mutated": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "production_graph_write_attempt": False,
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "llm_call_count": 0,
            "reserved_synthetic_part_prefix": "990-",
            "all_graph_edges_benchmark_prefixed": True,
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


def build_phase5(
    *,
    phase0_3_dir: str | Path,
    phase4_dir: str | Path,
    output_dir: str | Path,
    seed: str = DEFAULT_SEED,
    expected_scenario_count: int = EXPECTED_SCENARIO_COUNT,
    expected_question_count: int = EXPECTED_QUESTION_COUNT,
) -> dict[str, Any]:
    source = load_inputs(phase0_3_dir, phase4_dir)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    built = build_synthetic_benchmark(source["inventory"], seed=seed)
    answer_key = build_answer_key(built["scenarios"], built["relationships"], built["questions"])
    graph = build_graph_overlay(built["scenarios"], built["relationships"], built["page_assignments"])
    validation = validate_phase5(
        source["inventory"],
        built["scenarios"],
        built["relationships"],
        built["page_assignments"],
        built["questions"],
        graph,
        expected_scenario_count=expected_scenario_count,
        expected_question_count=expected_question_count,
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "seed": seed,
        "phase0_3_dir": source["phase0_3_dir"],
        "phase4_dir": source["phase4_dir"],
        "inventory_sha256": source["inventory_sha256"],
        "phase4_relationships_sha256": source["phase4_relationships_sha256"],
        "real_phase4_relationship_count": len(source["real_phase4_relationships"]),
        "synthetic_overlay_enabled_by_default": False,
        **_synthetic_flags(),
    }

    write_json(output / "trace_net_nha_synthetic_scenarios_v1.json", {"records": built["scenarios"]})
    write_jsonl(output / "trace_net_nha_synthetic_scenarios_v1.jsonl", built["scenarios"])
    write_json(output / "trace_net_nha_synthetic_relationships_v1.json", {"records": built["relationships"]})
    write_jsonl(output / "trace_net_nha_synthetic_relationships_v1.jsonl", built["relationships"])
    write_json(output / "trace_net_nha_synthetic_page_assignments_v1.json", {"records": built["page_assignments"]})
    write_jsonl(output / "trace_net_nha_synthetic_page_assignments_v1.jsonl", built["page_assignments"])
    write_json(output / "trace_net_nha_synthetic_question_bank_v1.json", {"records": built["questions"]})
    write_json(output / "trace_net_nha_synthetic_answer_key_v1.json", answer_key)
    write_json(output / "trace_net_nha_synthetic_graph_overlay_v1.json", graph)
    write_json(output / "trace_net_nha_synthetic_manifest_v1.json", manifest)
    write_json(output / "trace_net_nha_phase5_quality_v1.json", validation)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "status": STATUS,
        "quality_status": validation["quality_status"],
        "seed": seed,
        "phase0_3_dir": source["phase0_3_dir"],
        "phase4_dir": source["phase4_dir"],
        "output_dir": str(output),
        "input_counts": {
            "inventory_pages": len(source["inventory"]),
            "real_phase4_relationships": len(source["real_phase4_relationships"]),
        },
        "phase5_counts": validation["counts"],
        "case_type_counts": validation["case_type_counts"],
        "failures": validation["failures"],
        "warnings": validation["warnings"],
        "artifacts": sorted(path.name for path in output.glob("trace_net_nha_*.json*")),
    }
    write_json(output / "trace_net_nha_phase5_summary_v1.json", summary)
    return summary
