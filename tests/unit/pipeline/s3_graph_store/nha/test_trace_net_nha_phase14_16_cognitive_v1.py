from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.trace_net.graph.trace_net_nha_phase14_16_cognitive_v1 import (
    build_gemma_messages,
    build_nha_writer_packet,
    load_nha_engram_bundle,
    parse_gemma_answer,
    render_final_answer,
    select_memory_atoms,
    validate_gemma_answer,
    write_nha_answer_with_gemma,
)
from scripts.operations.s3_graph_store.serve_trace_net_nha_phase16_gemma_proxy_v1 import decision_headers
from scripts.benchmark.s3_graph_store.run_trace_net_nha_phase16_gemma20_v1 import evaluate as evaluate_live_case


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


def test_two_part_parent_comparison_uses_second_identifier_as_child():
    packet = build_nha_writer_packet(
        query="Is 120-29067-001 the immediate parent of 120-20970-001 or only a higher ancestor?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    assert packet["eligible"] is True
    assert packet["part_number"] == "120-20970-001"
    assert packet["comparison_parent_part"] == "120-29067-001"
    assert packet["evidence"]["comparison_relation"] == "direct_parent"
    assert packet["evidence"]["direct_nha"] == "120-29067-001"
    ok, failures = validate_gemma_answer(
        "120-29067-001 is the immediate parent of 120-20970-001.",
        packet,
    )
    assert ok, failures


def test_manual_child_descendant_and_conflict_packets_are_eligible():
    cases = {
        "Which pieces are directly inside assembly 120-29067-001?": "direct_children",
        "Show everything below 120-29067-001, but separate immediate parts from deeper descendants.": "direct_vs_descendants",
        "Why are there several possible parents for 42952-10?": "scope_conflict_resolution",
    }
    for query, intent in cases.items():
        packet = build_nha_writer_packet(
            query=query,
            engine=FakeEngine(),
            engram_bundle=bundle(),
        )
        assert packet["recognized"] is True, (query, packet)
        assert packet["eligible"] is True, (query, packet)
        assert packet["intent"] == intent, (query, packet)
        assert packet["selected_memory_atom_ids"], query


def test_model_call_headers_distinguish_live_paths():
    packet = build_nha_writer_packet(
        query="What bigger assembly is 120-20970-001 installed inside?",
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    nha = decision_headers(
        packet,
        action="gemma_override",
        writer_source="gemma",
        gemma_calls=1,
        self_rag="PASS",
        model_calls=1,
        model_path="nha_constrained_gemma",
        upstream_calls=0,
        prompt_tokens=100,
        completion_tokens=20,
    )
    assert nha["X-Trace-Net-Model-Calls"] == "1"
    assert nha["X-Trace-Net-Model-Path"] == "nha_constrained_gemma"
    assert nha["X-Trace-Net-Upstream-Calls"] == "0"

    upstream = decision_headers(
        {"intent": "none"},
        action="passthrough",
        model_calls=1,
        model_path="upstream_cognitive",
        upstream_calls=1,
    )
    assert upstream["X-Trace-Net-Model-Calls"] == "1"
    assert upstream["X-Trace-Net-Model-Path"] == "upstream_cognitive"
    assert upstream["X-Trace-Net-Upstream-Calls"] == "1"

    blocked = decision_headers({}, action="synthetic_blocked")
    assert blocked["X-Trace-Net-Model-Calls"] == "0"
    assert blocked["X-Trace-Net-Model-Path"] == ""


def test_live_evaluator_rejects_zero_model_passthrough():
    case = {
        "case_id": "T",
        "kind": "non_nha_control",
        "query": "How do I install 120-20970-001?",
        "expected_action": "passthrough",
        "expected_packet": {},
        "stream": False,
    }
    response = {
        "http_status": 200,
        "headers": {
            "x-trace-net-nha-action": "passthrough",
            "x-trace-net-model-calls": "0",
            "x-trace-net-model-path": "",
            "x-trace-net-upstream-calls": "0",
        },
        "answer": "An upstream-looking answer.",
        "latency_seconds": 1.0,
    }
    result = evaluate_live_case(case, response)
    assert result["passed"] is False
    assert any("passthrough_model_call_count" in value for value in result["failures"])


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
        query="What is the NHA of benchmark part 990-91001-001?",
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


def test_two_part_parent_comparison_writer_renders_after_gemma():
    """Regression: the post-Gemma renderer must not crash on comparison metadata."""
    packet = build_nha_writer_packet(
        query=(
            "Is 120-29067-001 the immediate parent of "
            "120-20970-003 or only a higher ancestor?"
        ),
        engine=FakeEngine(),
        engram_bundle=bundle(),
    )
    assert packet["eligible"] is True
    assert packet["evidence"]["comparison_relation"] == "direct_parent"

    def model_call(**kwargs):
        return {
            "quality_status": "PASS",
            "content": json.dumps({
                "answer": (
                    "120-29067-001 is the immediate parent of "
                    "120-20970-003."
                )
            }),
            "prompt_eval_count": 120,
            "eval_count": 18,
        }

    result = write_nha_answer_with_gemma(packet, model_call=model_call)

    assert result.gemma_call_count == 1
    assert result.gemma_writer_accepted is True
    assert result.writer_source == "gemma"
    assert result.self_rag_pass is True
    assert "## Answer" in result.answer
    assert "120-29067-001" in result.answer
    assert "120-20970-003" in result.answer
    assert "t_p_120_1176_p000343" in result.answer

