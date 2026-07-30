from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_nha_engram_v1 import (
    NHA_SKILL_IDS,
    build_100_question_bank,
    build_engram_core_overlay,
    build_nha_engram_artifacts,
    build_nha_memory_atoms,
    build_nha_skill_library,
    build_skill_library_overlay,
    check_nha_engram_artifacts,
    evaluate_question_bank,
    extract_nha_query_atoms,
    select_nha_skills,
)
from tiff.trace_net_engram_skill_cards_v1 import validate_skill_library


def base_library() -> dict:
    # Five existing-style cards keep the overlay regression realistic while
    # tests remain independent of the repository's generated JSON artifact.
    cards = []
    for index in range(5):
        cards.append({
            "skill_id": f"base_skill_{index}",
            "version": "1.0.0",
            "title": f"Base skill {index}",
            "description": "Existing behavior guidance.",
            "memory_layers": ["procedural_memory", "critic_memory"],
            "applies_when": ["A matching base query is present."],
            "does_not_apply_when": ["The query is outside the skill."],
            "selection": {
                "primary_routes": [f"base_route_{index}"],
                "required_any_atoms": [f"base_atom_{index}"],
                "required_all_atoms": [],
                "optional_atoms": [],
                "exclude_atoms": [],
                "trigger_terms": [f"base term {index}"],
                "priority": 10,
            },
            "reasoning_goal": "Preserve existing behavior.",
            "required_first_searches": ["Use the existing deterministic search."],
            "allowed_tunnels": ["base_tunnel"],
            "forbidden_tunnels": ["Unsafe tunnel."],
            "ranking_policy": ["Prefer source-backed evidence."],
            "evidence_sufficiency": {"direct_answer_requires": "Source evidence.", "candidate_mode_when": "Ambiguous.", "guidance_mode_when": "Guidance only."},
            "answer_mode_rules": {"default": "candidate", "direct_if": "Supported.", "fail_closed_if": "Unsupported."},
            "answer_requirements": ["Cite evidence."],
            "follow_up_policy": ["Ask only discriminating questions."],
            "positive_examples": [f"Positive {j}" for j in range(5)],
            "negative_examples": [f"Negative {j}" for j in range(3)],
            "known_failure_lessons": [f"Lesson {j}" for j in range(3)],
            "safety_contract": {
                "engram_guidance_only": True,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "can_be_used_as_proof": False,
                "retrieval_execution_allowed": False,
                "postgres_write_attempt": False,
                "qdrant_write_attempt": False,
                "opensearch_write_attempt": False,
            },
        })
    return {
        "module": "trace_net_engram_skill_cards_v1",
        "version": "v1",
        "status": "BASE",
        "skill_card_count": 5,
        "skill_cards": cards,
        "safety_contract": {
            "engram_guidance_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "can_be_used_as_proof": False,
            "retrieval_execution_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }


def base_core() -> dict:
    return {
        "module": "trace_net_engineering_engram_core_v1",
        "version": "v1",
        "status": "BASE",
        "quality_status": "PASS",
        "summary": {"engram_atom_count": 2},
        "records": [
            {"engram_id": "base_a", "memory_type": "policy_trait", "priority": "high", "trait": "base", "triggers": ["a"], "trigger_text": "a", "rule": "a", "good_behavior": "a", "bad_behavior": "a", "source": "base", "status": "active"},
            {"engram_id": "base_b", "memory_type": "critic_trait", "priority": "high", "trait": "base", "triggers": ["b"], "trigger_text": "b", "rule": "b", "good_behavior": "b", "bad_behavior": "b", "source": "base", "status": "active"},
        ],
    }


def test_direct_and_conversational_atoms():
    for query in (
        "What is the direct NHA of part 120-20970-001?",
        "Which assembly immediately contains 120-20970-001?",
        "What larger unit contains 120-20970-001?",
        "Where does 120-20970-001 sit in the assembly hierarchy?",
    ):
        atoms = extract_nha_query_atoms(query)
        assert atoms["nha_candidate"] is True
        assert atoms["intent"] == "direct_nha"
        assert "direct_nha_intent" in atoms["query_atom_tokens"]


def test_chain_children_descendants_and_evidence_atoms():
    expectations = {
        "Show the complete assembly chain above 42952-10.": "ancestor_chain",
        "List the direct children of assembly 120-29067-001.": "direct_children",
        "Show direct versus lower descendants below assembly 120-29067-001.": "direct_vs_descendants",
        "Which page proves the NHA relationship for 120-20970-001?": "relationship_evidence",
    }
    for query, intent in expectations.items():
        atoms = extract_nha_query_atoms(query)
        assert atoms["intent"] == intent
        assert atoms["nha_candidate"] is True


def test_scope_and_attaching_atoms():
    scope = extract_nha_query_atoms("Does the NHA of 42952-10 change by project and revision?")
    assert scope["intent"] == "scope_conflict_resolution"
    assert "project_scope" in scope["query_atom_tokens"]
    assert "revision_scope" in scope["query_atom_tokens"]
    attaching = extract_nha_query_atoms("Which component group is the attaching part 42952-10 directly under?")
    assert attaching["intent"] == "direct_nha"
    assert "attaching_parts" in attaching["query_atom_tokens"]
    assert "nearest_supported_component" in attaching["query_atom_tokens"]


def test_procedure_exact_and_authority_queries_do_not_false_route():
    for query in (
        "Find part 120-20970-001.",
        "Where is part 120-20970-001 listed in the manual?",
        "How do I install 120-20970-001?",
        "What torque applies to bolt 42952-10?",
        "Is 120-20970-001 an approved replacement?",
    ):
        assert extract_nha_query_atoms(query)["nha_candidate"] is False
        assert select_nha_skills(query)["selected_skill_ids"] == []


def test_synthetic_identifier_is_blocked_before_selection():
    result = select_nha_skills("What is the direct NHA of synthetic part 990-91001-001?")
    assert result["blocked"] is True
    assert result["selected_skill_ids"] == []
    assert result["atoms"]["synthetic_blocked"] is True


def test_five_nha_skill_cards_validate_under_existing_schema():
    library = build_nha_skill_library()
    assert tuple(card["skill_id"] for card in library["skill_cards"]) == NHA_SKILL_IDS
    validation = validate_skill_library(library)
    assert validation["quality_status"] == "PASS", validation


def test_skill_overlay_preserves_base_and_adds_five_nha_cards():
    overlay = build_skill_library_overlay(base_library())
    assert overlay["skill_card_count"] == 10
    ids = {card["skill_id"] for card in overlay["skill_cards"]}
    assert set(NHA_SKILL_IDS).issubset(ids)
    assert {f"base_skill_{index}" for index in range(5)}.issubset(ids)
    assert validate_skill_library(overlay)["quality_status"] == "PASS"


def test_memory_overlay_preserves_base_and_adds_fifteen_atoms():
    atoms = build_nha_memory_atoms()
    assert len(atoms) == 15
    overlay = build_engram_core_overlay(base_core())
    assert len(overlay["records"]) == 17
    assert overlay["summary"]["nha_atom_count"] == 15
    assert overlay["summary"]["answer_permission_count"] == 0
    assert overlay["summary"]["write_attempt_count"] == 0


def test_primary_skill_selection_per_intent():
    cases = {
        "What is the direct NHA of part 120-20970-001?": "nha_direct_parent_lookup",
        "Show the complete assembly chain above 42952-10.": "nha_ancestor_chain_reasoning",
        "List the direct children of assembly 120-29067-001.": "nha_children_descendants_reasoning",
        "Which page proves the NHA relationship for 120-20970-001?": "nha_relationship_evidence",
        "Does the NHA of 42952-10 change by project?": "nha_scope_conflict_resolution",
    }
    for query, skill in cases.items():
        result = select_nha_skills(query)
        assert result["selected_skill_ids"][0] == skill, result


def test_100_question_bank_is_exact_and_has_core20():
    bank = build_100_question_bank()
    assert len(bank) == 100
    assert len({row["question_id"] for row in bank}) == 100
    assert len({row["query"] for row in bank}) == 100
    assert sum(row["core20"] for row in bank) == 20


def test_100_question_and_core20_benchmark_pass():
    bank = build_100_question_bank()
    results = evaluate_question_bank(bank)
    assert len(results) == 100
    assert sum(row["passed"] for row in results) == 100, [row for row in results if not row["passed"]][:5]
    core = [row for row in results if row["core20"]]
    assert len(core) == 20
    assert sum(row["passed"] for row in core) == 20


def test_build_and_independent_check_round_trip(tmp_path: Path):
    base_core_path = tmp_path / "base_core.json"
    base_library_path = tmp_path / "base_library.json"
    base_core_path.write_text(json.dumps(base_core()), encoding="utf-8")
    base_library_path.write_text(json.dumps(base_library()), encoding="utf-8")
    output = tmp_path / "out"
    summary = build_nha_engram_artifacts(
        base_engram_core_path=base_core_path,
        base_skill_library_path=base_library_path,
        output_dir=output,
    )
    assert summary["quality_status"] == "PASS", summary
    checked = check_nha_engram_artifacts(output)
    assert checked["quality_status"] == "PASS", checked
    assert checked["counts"]["question_count"] == 100
    assert checked["counts"]["core20_pass_count"] == 20
    assert checked["counts"]["llm_call_count"] == 0
