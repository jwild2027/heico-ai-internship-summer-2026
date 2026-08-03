from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.trace_net.graph.trace_net_nha_phase4_hierarchy_v1 import (
    build_answer_key,
    build_graph_bundle,
    is_attaching_hardware,
    resolve_hierarchy,
    validate_phase4,
)


def inventory():
    return [
        {"canonical_page_id": "p1", "page_ordinal": 1},
        {"canonical_page_id": "p2", "page_ordinal": 2},
    ]


def anchors(single=True):
    variants = ["120-10000-001"] if single else ["120-10000-001", "120-10000-003"]
    printed = "120-10000-001" if single else "120-10000-001/003"
    return [{
        "anchor_id": "a1", "page_id": "p1", "figure": "10", "sheet": 1,
        "assembly_identifier_as_printed": printed,
        "assembly_part_variants": variants,
        "assembly_name": "Seat Structure",
    }]


def row(row_id, part, name, item, *, attach=False, line=1):
    return {
        "row_id": row_id, "page_id": "p1", "row_type": "component",
        "part_number": part, "nomenclature": name, "item_number": str(item),
        "quantity": "1", "indentation_level": 1,
        "attaching_parts_context": attach, "ocr_line_number": line,
    }


def test_hardware_classifier_is_narrow():
    assert is_attaching_hardware(row("r1", "MS21042L5", "NUT", 10, attach=True))
    assert is_attaching_hardware(row("r2", "42952-10", "FITTING, ATTACH", 20, attach=True))
    assert not is_attaching_hardware(row("r3", "120-20000-001", "SUPPORT, ATTACH", 30, attach=True))
    assert not is_attaching_hardware(row("r4", "120-20000-002", "STRUCTURE, ARMREST", 40, attach=True))


def test_sticky_attaching_region_closes_on_substantive_component():
    rows = [
        row("leg", "120-20000-001", "STRUCTURE, LATERAL LEG", 1, line=1),
        row("fit", "42952-10", "FITTING, ATTACH", 20, attach=True, line=2),
        row("nut", "MS21042L5", "NUT", 30, attach=True, line=3),
        row("protector", "120-30000-001", "PROTECTOR, LUGGAGE", 70, attach=True, line=4),
    ]
    hierarchy, relationships, groups = resolve_hierarchy(inventory(), anchors(), rows)
    by_child = {record["child_part"]: record for record in relationships}
    assert by_child["42952-10"]["direct_nha"] == "120-20000-001"
    assert by_child["42952-10"]["hierarchy_depth"] == 2
    assert by_child["MS21042L5"]["direct_nha"] == "120-20000-001"
    assert by_child["120-30000-001"]["direct_nha"] == "120-10000-001"
    assert by_child["120-30000-001"]["hierarchy_depth"] == 1
    assert len(groups) == 1
    assert groups[0]["child_parts"] == ["42952-10", "MS21042L5"]
    assert next(r for r in hierarchy if r["part_number"] == "120-30000-001")["boundary_resolution_method"] == "substantive_component_closes_sticky_attaching_region"


def test_contiguous_component_variants_make_attaching_parent_ambiguous():
    rows = [
        row("leg1", "120-20000-001", "STRUCTURE, LATERAL LEG", 1, line=1),
        row("leg2", "120-20000-005", "STRUCTURE, LATERAL LEG", 2, line=2),
        row("pin", "120-48023-001", "PIN, ATTACH", 11, attach=True, line=3),
    ]
    _, relationships, groups = resolve_hierarchy(inventory(), anchors(single=False), rows)
    pin = next(record for record in relationships if record["child_part"] == "120-48023-001")
    assert pin["relationship_status"] == "ambiguous"
    assert pin["direct_nha"] == ""
    assert pin["parent_candidates"] == ["120-20000-001", "120-20000-005"]
    assert groups[0]["resolution_status"] == "ambiguous"


def test_supported_attaching_part_is_not_flattened_to_top_assembly():
    rows = [
        row("seat", "120-29077-001", "SEAT", 110, line=1),
        row("fit", "42952-10", "FITTING, ATTACH", 120, attach=True, line=2),
    ]
    _, relationships, _ = resolve_hierarchy(inventory(), anchors(), rows)
    fitting = next(record for record in relationships if record["child_part"] == "42952-10")
    assert fitting["direct_nha"] == "120-29077-001"
    assert fitting["top_assembly_part"] == "120-10000-001"
    assert fitting["direct_child_of_top_assembly"] is False
    assert fitting["lower_descendant_of_top_assembly"] is True
    graph = build_graph_bundle(inventory(), relationships)
    direct = [edge for edge in graph["edges"] if edge["edge_type"] == "DIRECT_COMPONENT_OF" and edge["from"] == "part:42952-10"]
    assert direct[0]["to"] == "part:120-29077-001"
    lower = [edge for edge in graph["edges"] if edge["edge_type"] == "LOWER_DESCENDANT_OF"]
    assert lower[0]["to"] == "part:120-10000-001"
    assert lower[0]["properties"]["direct_relationship"] is False


def test_multi_top_assembly_keeps_direct_components_ambiguous():
    rows = [row("leg", "120-20000-001", "STRUCTURE, LATERAL LEG", 1)]
    _, relationships, _ = resolve_hierarchy(inventory(), anchors(single=False), rows)
    relation = relationships[0]
    assert relation["relationship_status"] == "ambiguous"
    assert relation["direct_nha"] == ""
    assert relation["parent_candidates"] == ["120-10000-001", "120-10000-003"]
    assert relation["can_prove_direct_nha"] is False


def test_validation_and_answer_key_contract():
    rows = [
        row("leg", "120-20000-001", "STRUCTURE, LATERAL LEG", 1, line=1),
        row("fit", "42952-10", "FITTING, ATTACH", 20, attach=True, line=2),
    ]
    hierarchy, relationships, groups = resolve_hierarchy(inventory(), anchors(), rows)
    result = validate_phase4(hierarchy, relationships, groups, minimum_supported=2, minimum_attaching_supported=1)
    assert result["quality_status"] == "PASS"
    assert result["counts"]["source_supported_attaching_relationships"] == 1
    answer_key = build_answer_key(relationships)
    assert answer_key["direct_component_case_count"] == 1
    assert answer_key["lower_descendant_case_count"] == 1
    attaching_case = next(case for case in answer_key["cases"] if case["child_part"] == "42952-10")
    assert attaching_case["expected_direct_nha"] == "120-20000-001"
    assert "An attaching part is a direct child of the top assembly" in attaching_case["must_not_claim"]


def test_validation_rejects_flattening_and_cycle():
    hierarchy = [{"truth_mode": "real_source", "source_truth": True}]
    relationships = [
        {
            "relationship_id": "r1", "truth_mode": "real_source", "source_truth": True,
            "child_part": "A", "direct_nha": "B", "parent_candidates": ["B"],
            "relationship_status": "source_supported", "guidance_only": False,
            "can_prove_direct_nha": True, "hierarchy_depth": 2,
            "direct_child_of_top_assembly": True, "lower_descendant_of_top_assembly": True,
        },
        {
            "relationship_id": "r2", "truth_mode": "real_source", "source_truth": True,
            "child_part": "B", "direct_nha": "A", "parent_candidates": ["A"],
            "relationship_status": "source_supported", "guidance_only": False,
            "can_prove_direct_nha": True, "hierarchy_depth": 1,
            "direct_child_of_top_assembly": True, "lower_descendant_of_top_assembly": False,
        },
    ]
    result = validate_phase4(hierarchy, relationships, [], minimum_supported=0, minimum_attaching_supported=0)
    assert result["quality_status"] == "FAIL"
    assert any("flattened" in failure for failure in result["failures"])
    assert any("cycle" in failure for failure in result["failures"])


def test_cli_entrypoints_bootstrap_repo_root(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    for relative in (
        "scripts/build/graph/build_trace_net_nha_phase4_hierarchy_v1.py",
        "scripts/maintenance/graph/check_trace_net_nha_phase4_hierarchy_v1.py",
    ):
        completed = subprocess.run(
            [sys.executable, "-B", str(repo_root / relative), "--help"],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "usage:" in completed.stdout.lower()
