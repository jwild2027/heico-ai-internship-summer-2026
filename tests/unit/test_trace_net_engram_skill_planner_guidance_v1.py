import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(
    "src/trace_net/engram/trace_net_h30_engram_skill_planner_guidance_v1.py"
)
LIBRARY_PATH = Path(
    "local_data/organization/trace_net/engram_skill_cards_v1/"
    "trace_net_engram_skill_cards_v1.json"
)
SHADOW_PATH = Path(
    "src/trace_net/router/trace_net_h30_shadow_planner_v1.py"
)
VALIDATED_PATH = Path(
    "src/trace_net/router/trace_net_h30_validated_planner_execution_v1.py"
)
LAUNCHER_PATH = Path(
    "scripts/operations/launch_trace_net_cognitive_openwebui_v1.sh"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "trace_net_phase3_guidance_test",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def enabled_env():
    return {
        "TRACE_NET_H30_ENGRAM_SKILL_PLANNER_GUIDANCE_ENABLED": "1",
        "TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH": str(
            LIBRARY_PATH
        ),
    }


def q001_seed():
    return {
        "query": "I only know the part starts with 123",
        "deterministic_atoms": {
            "identifier_mode": "prefix",
            "normalized_identifier": "123",
            "part_prefix": "123",
            "manufacturer": None,
            "ata_prefix": None,
            "nomenclature_terms": [],
        },
        "deterministic_plan": {
            "primary_route": "guided_part_discovery",
            "retrieval_tunnels": [
                "guided_candidate_discovery",
                "normal_source_resolution",
                "phase4_3_candidate_source_resolution",
                "qdrant_guidance",
            ],
        },
        "retrieved_evidence_in_seed": False,
    }


def aligned_proposal():
    return {
        "identifier_mode": "prefix",
        "identifier": "123",
        "entity_type": "part_number",
        "requested_claims": ["part_identity"],
        "suggested_routes": ["guided_part_discovery"],
        "suggested_tunnels": [
            "guided_candidate_discovery",
            "normal_source_resolution",
        ],
        "uncertainties": [],
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def test_disabled_by_default():
    module = load_module()
    output = module.augment_shadow_planner_seed(
        q001_seed(),
        environ={},
    )
    guidance = output["engram_skill_planner_guidance"]
    assert guidance["applied"] is False
    assert guidance["reason"] == "disabled_by_configuration"


def test_q001_applies_only_reviewed_skill():
    module = load_module()
    output = module.augment_shadow_planner_seed(
        q001_seed(),
        environ=enabled_env(),
    )
    guidance = output["engram_skill_planner_guidance"]
    assert guidance["applied"] is True
    assert guidance["skill_id"] == (
        "partial_identifier_discovery"
    )
    assert guidance["required_primary_route"] == (
        "guided_part_discovery"
    )
    assert guidance["required_identifier_mode"] == "prefix"
    assert guidance["required_identifier"] == "123"
    assert guidance["answer_writer_influenced"] is False


def test_exact_identifier_remains_out_of_scope():
    module = load_module()
    seed = q001_seed()
    seed["query"] = "Find part 120-41824-003"
    seed["deterministic_atoms"] = {
        "identifier_mode": "exact",
        "normalized_identifier": "120-41824-003",
        "exact_part_numbers": ["120-41824-003"],
    }
    seed["deterministic_plan"] = {
        "primary_route": "exact_identifier_lookup"
    }
    output = module.augment_shadow_planner_seed(
        seed,
        environ=enabled_env(),
    )
    guidance = output["engram_skill_planner_guidance"]
    assert guidance["applied"] is False
    assert guidance["reason"] == "route_not_in_phase3_scope"


def test_aligned_proposal_passes():
    module = load_module()
    seed = module.augment_shadow_planner_seed(
        q001_seed(),
        environ=enabled_env(),
    )
    result = module.validate_skill_guided_planner_proposal(
        proposal=aligned_proposal(),
        seed=seed,
    )
    assert result["quality_status"] == "PASS"
    assert result["accepted"] is True


def test_route_change_fails_closed():
    module = load_module()
    seed = module.augment_shadow_planner_seed(
        q001_seed(),
        environ=enabled_env(),
    )
    proposal = aligned_proposal()
    proposal["suggested_routes"] = [
        "exact_identifier_lookup"
    ]
    result = module.validate_skill_guided_planner_proposal(
        proposal=proposal,
        seed=seed,
    )
    assert result["quality_status"] == "FAIL"
    assert "forbidden_route:exact_identifier_lookup" in (
        result["failures"]
    )


def test_identifier_and_mode_change_fail_closed():
    module = load_module()
    seed = module.augment_shadow_planner_seed(
        q001_seed(),
        environ=enabled_env(),
    )
    proposal = aligned_proposal()
    proposal["identifier_mode"] = "exact"
    proposal["identifier"] = "1234567"
    result = module.validate_skill_guided_planner_proposal(
        proposal=proposal,
        seed=seed,
    )
    assert result["quality_status"] == "FAIL"
    assert "grounded_identifier_changed" in result["failures"]
    assert any(
        item.startswith("identifier_mode_changed:")
        for item in result["failures"]
    )


def test_safety_remains_false():
    module = load_module()
    seed = module.augment_shadow_planner_seed(
        q001_seed(),
        environ=enabled_env(),
    )
    guidance = seed["engram_skill_planner_guidance"]
    for key in (
        "answer_permission",
        "final_answer_allowed",
        "can_answer_directly",
        "can_prove_claims",
        "source_truth_mutation_allowed",
    ):
        assert guidance[key] is False
    assert guidance["retrieval_execution_allowed"] is False
    assert guidance["planner_route_control_allowed"] is False


def test_runtime_files_are_wired():
    shadow = SHADOW_PATH.read_text(encoding="utf-8")
    validated = VALIDATED_PATH.read_text(encoding="utf-8")
    launcher = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "augment_shadow_planner_seed" in shadow
    assert (
        "validate_skill_guided_planner_proposal"
        in validated
    )
    assert (
        "engram_skill_planner_guidance_validation"
        in validated
    )
    assert (
        "TRACE_NET_H30_ENGRAM_SKILL_PLANNER_GUIDANCE_ENABLED"
        in launcher
    )
