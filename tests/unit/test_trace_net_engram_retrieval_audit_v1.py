from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path("scripts/benchmark/run_trace_net_engram_retrieval_audit_v1.py")
BANK = Path("tests/data/trace_net_engram_retrieval_question_bank_v1.json")


def load_module():
    spec = importlib.util.spec_from_file_location("engram_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_question_bank_covers_all_routes_skills_and_memory_layers() -> None:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    cases = bank["cases"]
    coverage = {tag for case in cases for tag in case.get("coverage", [])}
    routes = {tag.split(":", 1)[1] for tag in coverage if tag.startswith("route:")}
    skills = {tag.split(":", 1)[1] for tag in coverage if tag.startswith("skill:")}
    memory = {tag.split(":", 1)[1] for tag in coverage if tag.startswith("memory:")}

    assert len(routes) == 19
    assert skills == {
        "partial_identifier_discovery",
        "exact_identifier_lookup",
        "nomenclature_function_discovery",
        "ata_plus_description_discovery",
        "manufacturer_plus_description_discovery",
    }
    assert memory == {
        "working_memory",
        "semantic_memory",
        "procedural_memory",
        "episodic_memory",
        "trait_memory",
        "critic_memory",
    }


def test_selected_skill_finds_nested_skill() -> None:
    module = load_module()
    trace = {
        "final_engram_rollout": {
            "skill_selection": {
                "selected_skill_id": "partial_identifier_discovery",
                "selection_basis": "runtime_selected_engram_skill",
            }
        }
    }
    skill, basis, candidates = module.selected_skill(trace)
    assert skill == "partial_identifier_discovery"
    assert basis == "runtime_selected_engram_skill"
    assert candidates == ["partial_identifier_discovery"]


def test_build_record_passes_expected_route_and_skill() -> None:
    module = load_module()
    case = {
        "id": "X",
        "kind": "gate",
        "expected_route": "exact_identifier_lookup",
        "expected_skill": "exact_identifier_lookup",
        "coverage": [],
        "question": "Find part 120-20970-001",
    }
    payload = {
        "choices": [{"message": {"content": "Answer\nEvidence\nA supported result."}}],
        "trace_net": {
            "route": "exact_identifier_lookup",
            "post_answer_validation": {"accepted": True, "failures": []},
            "final_engram_rollout": {
                "selected_skill_id": "exact_identifier_lookup"
            },
        },
    }
    record = module.build_record(case, payload, 200, "", 1.25)
    assert record["passed"] is True
    assert record["selected_skill"] == "exact_identifier_lookup"
