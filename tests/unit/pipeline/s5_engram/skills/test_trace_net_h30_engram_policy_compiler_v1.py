from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

COMPILER = Path("src/trace_net/pipeline/s5_engram/skills/trace_net_h30_engram_policy_compiler_v1.py")
PRECISION = Path("src/trace_net/pipeline/s5_engram/skills/trace_net_h30_cognitive_precision_v1.py")
RETRIEVAL = Path("src/trace_net/pipeline/s6_retrieval/search/trace_net_h30_retrieval_completion_v1.py")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def nav_memory():
    return {
        "atoms": [{
            "atom_id": "navigation_atom",
            "canonical_rule_id": "navigation_exact_entity_presentation",
            "policy_effects": {
                "retrieval_policy": {
                    "ranking_profile": "exact_entity_navigation",
                    "preferred_evidence_order": [
                        "source_citation", "visual", "table", "ocr",
                        "candidate", "semantic", "record",
                    ],
                    "group_by": "page_id",
                    "specialized_tunnel_first": True,
                    "direct_source_before_fallback": True,
                    "exact_entity_gate": True,
                },
                "critic_policy": {
                    "checks": [
                        "top_result_matches_exact_entity",
                        "no_token_level_ocr_spam",
                        "no_internal_identifier_exposure",
                    ]
                },
                "repair_policy": {
                    "hints": [
                        "rerank_exact_entity",
                        "collapse_page_rows",
                        "sanitize_internal_ids",
                    ]
                },
                "presentation_policy": {
                    "template": "strongest_then_supporting",
                    "primary_result_limit": 1,
                    "supporting_result_limit": 5,
                    "hide_internal_ids": True,
                    "collapse_by_page": True,
                },
            },
        }]
    }


def test_policy_compiler_builds_allowlisted_navigation_policy():
    mod = load(COMPILER, "engram_policy_compiler_a")
    policy = mod.compile_engram_policy(
        nav_memory(), "document_page_navigation", ["exact_identifier"]
    )
    assert policy["quality_status"] == "PASS"
    assert policy["retrieval_policy"]["specialized_tunnel_first"] is True
    assert policy["retrieval_policy"]["preferred_evidence_order"][1] == "visual"
    assert policy["presentation_policy"]["template"] == "strongest_then_supporting"
    assert policy["presentation_policy"]["primary_result_limit"] == 1
    assert policy["validated_against_allowlist"] is True
    assert policy["answer_permission"] is False


def test_policy_compiler_rejects_unknown_actions():
    mod = load(COMPILER, "engram_policy_compiler_b")
    memory = {"atoms": [{
        "atom_id": "bad",
        "policy_effects": {
            "retrieval_policy": {
                "preferred_evidence_order": ["source_citation", "DROP TABLE"],
                "ranking_profile": "execute_arbitrary_sql",
            },
            "critic_policy": {"checks": ["exact_entity_mismatch", "invent_proof"]},
            "repair_policy": {"hints": ["retry_specialized_tunnel", "delete_database"]},
        },
    }]}
    policy = mod.compile_engram_policy(
        memory, "exact_identifier_lookup", ["exact_identifier"]
    )
    assert "DROP TABLE" not in policy["retrieval_policy"]["preferred_evidence_order"]
    assert policy["retrieval_policy"]["ranking_profile"] == "route_default"
    assert policy["critic_policy"]["checks"] == ["exact_entity_mismatch"]
    assert policy["repair_policy"]["hints"] == ["retry_specialized_tunnel"]
    assert policy["rejected_effect_count"] >= 3


def test_authority_warning_only_for_authority_request():
    mod = load(COMPILER, "engram_policy_compiler_c")
    memory = {"atoms": [{
        "atom_id": "authority",
        "policy_effects": {"presentation_policy": {"show_authority_warning": True}},
    }]}
    navigation = mod.compile_engram_policy(
        memory, "document_page_navigation", ["exact_identifier"]
    )
    authority = mod.compile_engram_policy(
        memory, "authority_eligibility_verification", ["authority"]
    )
    assert navigation["presentation_policy"]["show_authority_warning"] is False
    assert authority["presentation_policy"]["show_authority_warning"] is True


def test_working_memory_is_request_local_and_refreshes():
    mod = load(COMPILER, "engram_policy_compiler_d")
    atoms = SimpleNamespace(
        requested_claims=["exact_identifier"],
        exact_part_numbers=["120-41824-003"],
    )
    plan = SimpleNamespace(
        primary_route="document_page_navigation", repair_budget=2
    )
    policy = mod.compile_engram_policy(
        nav_memory(), plan.primary_route, atoms.requested_claims
    )
    working = mod.build_working_memory(
        "Find the strongest page", atoms, plan, policy
    )
    envelope = SimpleNamespace(
        retrieval_tunnels_used=["navigation_visual_fallback"],
        direct_evidence=[], candidate_evidence=[],
        visual_guidance=[{
            "page_id": "t_p_120_1176_p000084",
            "subject": "part 120-41824-003; figure 2 sheet 1",
        }],
        semantic_guidance=[], authority_evidence=[], crag_repairs=[],
        coverage={"entity_mismatch_drop_count": 2},
    )
    refreshed = mod.refresh_working_memory(working, envelope, plan)
    assert refreshed["searches_attempted"] == ["navigation_visual_fallback"]
    assert refreshed["evidence_found"]["visual"] == 1
    assert refreshed["evidence_rejected_count"] == 2
    assert "t_p_120_1176_p000084" in refreshed["best_result"]
    assert refreshed["persist_source_truth"] is False


def test_selector_deduplicates_canonical_rules_and_preserves_effects(tmp_path):
    mod = load(PRECISION, "engram_policy_precision_a")
    pack = {"memory_atoms": [
        {
            "atom_id": "old_specialized",
            "canonical_rule_id": "specialized_tunnel_first",
            "memory_layer": "critic_memory",
            "routes": ["document_page_navigation"],
            "triggers": ["source document"],
            "rule": "Try the specialized tunnel.",
            "policy_effects": {
                "retrieval_policy": {"specialized_tunnel_first": True}
            },
        },
        {
            "atom_id": "new_specialized",
            "canonical_rule_id": "specialized_tunnel_first",
            "memory_layer": "procedural_memory",
            "routes": ["document_page_navigation"],
            "triggers": ["source document"],
            "rule": "A correct route needs its tunnel.",
            "policy_effects": {
                "retrieval_policy": {"specialized_tunnel_first": True}
            },
        },
    ]}
    path = tmp_path / "engram.json"
    path.write_text(json.dumps(pack), encoding="utf-8")
    selected = mod.select_engram_memory(
        "Which source document contains this?",
        "document_page_navigation",
        ["exact_identifier"],
        path=str(path), maximum_atoms=6,
    )
    assert selected["atom_count"] == 1
    assert selected["duplicate_atom_count"] == 1
    assert selected["atoms"][0]["canonical_rule_id"] == "specialized_tunnel_first"
    assert selected["atoms"][0]["policy_effects"]["retrieval_policy"]["specialized_tunnel_first"] is True


def test_navigation_renderer_uses_policy_grouping_and_hides_internal_ids():
    mod = load(RETRIEVAL, "engram_policy_retrieval_a")
    atoms = SimpleNamespace(exact_part_numbers=["120-41824-003"])
    policy_mod = load(COMPILER, "engram_policy_compiler_e")
    policy = policy_mod.compile_engram_policy(
        nav_memory(), "document_page_navigation", ["exact_identifier"]
    )
    envelope = SimpleNamespace(
        direct_evidence=[], candidate_evidence=[], semantic_guidance=[],
        visual_guidance=[{
            "page_id": "t_p_120_1176_p000084",
            "part_numbers": ["120-41824-003"],
            "figure_refs": ["figure 2 sheet 1"],
            "subject": "visual page associated with part 120-41824-003",
        }],
        coverage={
            "engram_policy": policy,
            "navigation_leads": [{
                "page_id": "t_p_120_1176_p000003",
                "document": "table_exact_search::t_p_120_1176_p000003::covered_part_number::ae28c8694c95f9d6",
                "source_type": "table",
                "part_numbers": ["120-41824-003"],
                "snippet": "120-41824-003",
            }],
        },
    )
    text = mod.render_navigation_answer(atoms, envelope, {"quality_status": "PASS"})
    assert "Strongest currently resolved navigation lead:" in text
    assert "Supporting page leads:" in text
    assert text.index("t_p_120_1176_p000084") < text.index("t_p_120_1176_p000003")
    assert "table_exact_search::" not in text
    assert "ae28c8694c95f9d6" not in text


def test_policy_evidence_order_controls_lead_ranking():
    mod = load(RETRIEVAL, "engram_policy_retrieval_b")
    envelope = SimpleNamespace(
        candidate_evidence=[], semantic_guidance=[],
        visual_guidance=[{
            "page_id": "t_p_120_1176_p000084",
            "source_type": "visual",
            "part_numbers": ["120-41824-003"],
            "subject": "visual",
        }],
        coverage={
            "engram_policy": {
                "retrieval_policy": {
                    "preferred_evidence_order": [
                        "source_citation", "table", "visual", "ocr",
                        "candidate", "semantic", "graph", "record",
                    ]
                },
                "presentation_policy": {"collapse_by_page": True},
            },
            "navigation_leads": [{
                "page_id": "t_p_120_1176_p000003",
                "source_type": "table",
                "part_numbers": ["120-41824-003"],
                "snippet": "table exact",
            }],
        },
    )
    rows = mod._lead_rows(envelope, ["120-41824-003"])
    assert rows[0]["source_type"] == "table"
