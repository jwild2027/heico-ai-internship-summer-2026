from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.trace_net_nha_phase14_16_cognitive_v1 import (
    build_gemma_messages,
    build_nha_writer_packet,
    load_nha_engram_bundle,
    parse_gemma_answer,
    render_final_answer,
    select_memory_atoms,
    validate_gemma_answer,
    write_nha_answer_with_gemma,
)


class FakeEngine:
    def direct_nha(self, part):
        if part == "42952-10":
            return {
                "behavior": "conflict_limited",
                "child": part,
                "parent_candidates": ["120-29073-001", "120-29073-005"],
                "pages": ["t_p_120_1176_p000349"],
            }
        return {
            "behavior": "direct_answer",
            "child": part,
            "direct_nha": "120-29067-001",
            "pages": ["t_p_120_1176_p000343"],
        }

    def ancestor_chain(self, part):
        return {
            "behavior": "ordered_chain_answer",
            "child": part,
            "chain": [part, "120-29073-001", "120-29067-001"],
            "pages": ["t_p_120_1176_p000343", "t_p_120_1176_p000342"],
        }

    def direct_children(self, part):
        return {
            "behavior": "direct_children_answer",
            "parent": part,
            "direct_children": ["120-20970-001", "120-29073-001"],
            "pages": ["t_p_120_1176_p000343"],
        }

    def descendants(self, part):
        return {
            "behavior": "tree_answer",
            "parent": part,
            "direct_children": ["120-29073-001"],
            "descendants": ["42952-10"],
            "pages": ["t_p_120_1176_p000343", "t_p_120_1176_p000349"],
        }

    def page_evidence(self, part):
        return {
            "behavior": "page_and_trait_answer",
            "child": part,
            "direct_nha": "120-29067-001",
            "pages": ["t_p_120_1176_p000343"],
        }


def bundle():
    skill_ids = [
        "nha_direct_parent_lookup",
        "nha_ancestor_chain_reasoning",
        "nha_children_descendants_reasoning",
        "nha_relationship_evidence",
        "nha_scope_conflict_resolution",
    ]
    return {
        "quality_status": "PASS",
        "nha_memory_atom_count": 15,
        "nha_skill_card_count": 5,
        "skill_cards": [
            {
                "skill_id": skill_id,
                "title": skill_id,
                "reasoning_goal": "Use deterministic evidence.",
                "ranking_policy": ["Source supported first."],
                "answer_requirements": ["Preserve identifiers."],
                "follow_up_policy": ["Ask only for missing scope."],
            }
            for skill_id in skill_ids
        ],
        "memory_atoms": [
            {
                "engram_id": atom_id,
                "rule": "Behavior guidance only.",
                "triggers": ["NHA"],
            }
            for atom_id in (
                "policy_nha_direct_parent_one_hop_v1",
                "policy_nha_source_page_required_v1",
                "semantic_nha_synonyms_v1",
                "critic_nha_no_grandparent_as_direct_v1",
                "style_nha_answer_shape_v1",
                "policy_nha_ordered_chain_no_skip_v1",
                "route_nha_assembly_relationship_reasoning_v1",
                "policy_nha_children_not_descendants_v1",
                "policy_nha_guidance_not_proof_v1",
                "policy_nha_scope_before_candidate_choice_v1",
                "semantic_nha_scope_vocabulary_v1",
                "critic_nha_no_candidate_collapse_v1",
                "repair_nha_request_scope_v1",
                "policy_nha_synthetic_never_production_v1",
                "policy_nha_attaching_nearest_component_v1",
            )
        ],
    }


def test_load_bundle(tmp_path: Path):
    atoms = {"records": bundle()["memory_atoms"]}
    cards = {"skill_cards": bundle()["skill_cards"]}
    quality = {"quality_status": "PASS"}
    (tmp_path / "trace_net_nha_engram_memory_atoms_v1.json").write_text(json.dumps(atoms))
    (tmp_path / "trace_net_nha_engram_skill_cards_v1.json").write_text(json.dumps(cards))
    (tmp_path / "trace_net_nha_engram_quality_v1.json").write_text(json.dumps(quality))
    loaded = load_nha_engram_bundle(tmp_path)
    assert loaded["quality_status"] == "PASS"
    assert loaded["nha_memory_atom_count"] == 15
    assert loaded["nha_skill_card_count"] == 5


def test_direct_packet_uses_atoms_skill_and_evidence():
    packet = build_nha_writer_packet(
        query="What larger unit contains 120-20970-001?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    assert packet["eligible"] is True
    assert packet["intent"] == "direct_nha"
    assert packet["selected_skill_ids"] == ["nha_direct_parent_lookup"]
    assert packet["selected_memory_atom_ids"]
    assert packet["evidence"]["direct_nha"] == "120-29067-001"


def test_directional_larger_assembly_phrase_routes_to_direct_parent():
    packet = build_nha_writer_packet(
        query="Which larger assembly directly contains 120-29074-001?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    assert packet["recognized"] is True
    assert packet["eligible"] is True
    assert packet["intent"] == "direct_nha"
    assert packet["selected_skill_ids"] == ["nha_direct_parent_lookup"]


def test_procedure_query_is_not_nha():
    packet = build_nha_writer_packet(
        query="How do I install 120-20970-001?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    assert packet["recognized"] is False
    assert packet["eligible"] is False


def test_synthetic_query_is_blocked_before_evidence():
    packet = build_nha_writer_packet(
        query="What larger unit contains 990-91001-001?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    assert packet["synthetic_blocked"] is True
    assert packet["eligible"] is False
    assert packet["evidence"] == {}


def test_messages_contain_engram_and_evidence_but_no_pages():
    packet = build_nha_writer_packet(
        query="What larger unit contains 120-20970-001?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    messages = build_gemma_messages(packet)
    assert "Behavior guidance only" in messages[1]["content"]
    assert "120-29067-001" in messages[1]["content"]
    assert "t_p_120_1176" not in messages[1]["content"]


def test_parse_json_answer():
    assert parse_gemma_answer('{"answer":"The direct parent is 120-29067-001."}') == "The direct parent is 120-29067-001."
    assert parse_gemma_answer("not json") == ""


def test_valid_gemma_direct_answer():
    packet = build_nha_writer_packet(
        query="What larger unit contains 120-20970-001?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    ok, failures = validate_gemma_answer(
        "Part 120-20970-001 has direct next higher assembly 120-29067-001.",
        packet,
    )
    assert ok, failures


def test_unsupported_identifier_is_rejected():
    packet = build_nha_writer_packet(
        query="What larger unit contains 120-20970-001?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    ok, failures = validate_gemma_answer(
        "Part 120-20970-001 has parent 120-99999-001.",
        packet,
    )
    assert not ok
    assert any("unsupported_identifiers" in value for value in failures)


def test_single_gemma_call_is_accepted_and_rendered():
    packet = build_nha_writer_packet(
        query="What larger unit contains 120-20970-001?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )

    def model_call(**kwargs):
        return {
            "quality_status": "PASS",
            "content": json.dumps({
                "answer": "Part 120-20970-001 has direct next higher assembly 120-29067-001."
            }),
            "prompt_eval_count": 100,
            "eval_count": 20,
        }

    result = write_nha_answer_with_gemma(packet, model_call=model_call)
    assert result.gemma_call_count == 1
    assert result.gemma_writer_accepted is True
    assert result.writer_source == "gemma"
    assert result.self_rag_pass is True
    assert "## Answer" in result.answer
    assert "t_p_120_1176_p000343" in result.answer


def test_invalid_model_output_falls_back_after_one_call():
    packet = build_nha_writer_packet(
        query="What larger unit contains 120-20970-001?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )

    def model_call(**kwargs):
        return {"quality_status": "PASS", "content": "not json"}

    result = write_nha_answer_with_gemma(packet, model_call=model_call)
    assert result.gemma_call_count == 1
    assert result.gemma_writer_accepted is False
    assert result.writer_source == "deterministic_fallback"
    assert result.self_rag_pass is True
    assert "120-29067-001" in result.answer


def test_conflict_answer_must_preserve_all_candidates():
    packet = build_nha_writer_packet(
        query="Does the NHA of 42952-10 depend on project or revision?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    ok, failures = validate_gemma_answer(
        "No single direct NHA can be confirmed for 42952-10; candidates are 120-29073-001 and 120-29073-005.",
        packet,
    )
    assert ok, failures


def test_final_renderer_keeps_evidence_deterministic():
    packet = build_nha_writer_packet(
        query="What larger unit contains 120-20970-001?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    answer = render_final_answer(
        "Part 120-20970-001 has direct next higher assembly 120-29067-001.",
        packet,
    )
    assert answer.count("## Evidence") == 1
    assert "[1]" in answer
    assert "Engram atoms and skill cards guide behavior but are not evidence" in answer
