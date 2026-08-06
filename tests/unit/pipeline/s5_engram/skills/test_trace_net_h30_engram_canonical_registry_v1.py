from __future__ import annotations

import json
from pathlib import Path

from src.trace_net.engram.trace_net_h30_engram_canonical_registry_v1 import (
    DEFAULT_REGISTRY_PATH,
    check_pack_inheritance,
    load_canonical_registry,
    resolve_atom_inheritance,
)
from src.trace_net.engram.trace_net_h30_cognitive_precision_v1 import (
    select_engram_memory,
)
from src.trace_net.engram.trace_net_h30_engram_policy_compiler_v1 import (
    compile_engram_policy,
)

V1 = Path(
    "local_data/organization/trace_net/"
    "cognitive_openwebui_regression_engram_v1/"
    "trace_net_cognitive_openwebui_regression_engram_v1.json"
)
V2 = Path(
    "local_data/organization/trace_net/"
    "cognitive_openwebui_regression_engram_v2/"
    "trace_net_cognitive_openwebui_regression_engram_v2.json"
)


def test_canonical_registry_has_unique_ids_and_meanings():
    load_canonical_registry.cache_clear()
    result = load_canonical_registry(str(DEFAULT_REGISTRY_PATH))
    assert result["quality_status"] == "PASS"
    assert result["canonical_rule_count"] == 13
    assert result["duplicate_rule_id_count"] == 0
    assert result["duplicate_normalized_meaning_count"] == 0
    assert result["answer_permission"] is False
    assert result["source_truth"] is False


def test_runtime_packs_use_inheritance_without_local_rule_copies():
    load_canonical_registry.cache_clear()
    registry = load_canonical_registry(str(DEFAULT_REGISTRY_PATH))
    for path in (V1, V2):
        pack = json.loads(path.read_text(encoding="utf-8"))
        check = check_pack_inheritance(pack, registry)
        assert check["quality_status"] == "PASS"
        assert check["unresolved_inheritance_count"] == 0
        assert check["local_policy_effect_count"] == 0
        assert check["local_rule_text_count"] == 0
        assert check["inherited_reference_count"] >= check["atom_count"]


def test_navigation_atom_inherits_shared_rules_and_compiles_same_policy():
    load_canonical_registry.cache_clear()
    memory = select_engram_memory(
        (
            "Which source document and page contain the strongest "
            "evidence for part 120-41824-003?"
        ),
        "document_page_navigation",
        ["exact_identifier"],
        maximum_atoms=6,
    )
    assert memory["quality_status"] == "PASS"
    assert memory["registry_quality_status"] == "PASS"
    assert memory["unresolved_inheritance_count"] == 0

    inherited = {
        rule_id
        for atom in memory["atoms"]
        for rule_id in atom.get("inherited_rule_ids", [])
    }
    assert {
        "navigation_exact_entity_presentation",
        "guidance_is_not_proof",
        "exact_entity_gate",
        "specialized_tunnel_first",
        "direct_source_before_fallback",
    }.issubset(inherited)

    policy = compile_engram_policy(
        memory,
        "document_page_navigation",
        ["exact_identifier"],
    )
    assert policy["retrieval_policy"]["ranking_profile"] == (
        "exact_entity_navigation"
    )
    assert policy["retrieval_policy"]["specialized_tunnel_first"] is True
    assert policy["retrieval_policy"]["direct_source_before_fallback"] is True
    assert policy["retrieval_policy"]["exact_entity_gate"] is True
    assert policy["presentation_policy"]["template"] == (
        "strongest_then_supporting"
    )
    assert policy["presentation_policy"]["primary_result_limit"] == 1
    assert policy["presentation_policy"]["supporting_result_limit"] == 5


def test_duplicate_shared_rule_references_are_consumed_once():
    load_canonical_registry.cache_clear()
    memory = select_engram_memory(
        (
            "Which source document and page contain the strongest "
            "evidence for part 120-41824-003?"
        ),
        "document_page_navigation",
        ["exact_identifier"],
        maximum_atoms=6,
    )
    resolved_ids = [
        rule_id
        for atom in memory["atoms"]
        for rule_id in atom.get("inherited_rule_ids", [])
    ]
    assert len(resolved_ids) == len(set(resolved_ids))
    assert memory["duplicate_rule_reference_count"] >= 1
    assert memory["resolved_rule_count"] == len(set(resolved_ids))


def test_unresolved_inheritance_fails_closed(tmp_path: Path):
    pack = {
        "memory_atoms": [{
            "atom_id": "broken_route_memory",
            "memory_layer": "procedural_memory",
            "routes": ["document_page_navigation"],
            "triggers": ["source document"],
            "inherits": ["missing_canonical_rule"],
            "activation_status": "active",
        }]
    }
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({
            "module": "unit_registry",
            "version": "v1",
            "canonical_rules": [],
        }),
        encoding="utf-8",
    )

    load_canonical_registry.cache_clear()
    memory = select_engram_memory(
        "Which source document contains this?",
        "document_page_navigation",
        ["exact_identifier"],
        path=str(pack_path),
        registry_path=str(registry_path),
    )
    assert memory["quality_status"] == "WARN"
    assert memory["atom_count"] == 0
    assert memory["unresolved_inheritance_count"] == 1
    assert memory["unresolved_inheritance"][0][
        "canonical_rule_id"
    ] == "missing_canonical_rule"


def test_policy_reports_every_inherited_canonical_rule():
    load_canonical_registry.cache_clear()
    memory = select_engram_memory(
        (
            "Which source document and page contain the strongest "
            "evidence for part 120-41824-003?"
        ),
        "document_page_navigation",
        ["exact_identifier"],
    )
    policy = compile_engram_policy(
        memory,
        "document_page_navigation",
        ["exact_identifier"],
    )
    inherited = {
        rule_id
        for atom in memory["atoms"]
        for rule_id in atom.get("inherited_rule_ids", [])
    }
    assert inherited.issubset(
        set(policy["source_canonical_rule_ids"])
    )
    assert policy["answer_permission"] is False
    assert policy["source_truth"] is False
