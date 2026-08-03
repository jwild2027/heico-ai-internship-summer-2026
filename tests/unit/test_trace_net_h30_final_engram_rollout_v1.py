import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(
    "src/trace_net/validation/trace_net_h30_final_engram_rollout_v1.py"
)
WRITER_PATH = Path(
    "scripts/operations/serving/serve_trace_net_full_gemma_cognitive_v1.py"
)
LAUNCHER_PATH = Path(
    "scripts/operations/launch_trace_net_cognitive_openwebui_v1.sh"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "trace_net_final_rollout_test",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def result(mode, route, *, atoms=None, candidates=0):
    content = {
        "candidate_discovery": (
            "TRACE-Net found candidate matches, not a final identification."
        ),
        "visual_guidance": (
            "TRACE-Net found visual guidance, but no citation-ready direct "
            "source proof."
        ),
        "semantic_graph_summary_guidance": (
            "These records can guide the next search, but they cannot prove "
            "the requested claim."
        ),
        "conflict_limited": (
            "No positive technical conclusion is allowed."
        ),
        "authority_not_found": (
            "TRACE-Net did not find direct authority evidence."
        ),
        "no_evidence": "No technical conclusion is provided.",
    }.get(mode, "")
    return {
        "route": route,
        "query_atoms": dict(atoms or {}),
        "answer_mode": {
            "mode": mode,
            "candidate_count": candidates,
            "claim_support_allowed_count": 0,
        },
        "answer_mode_validation": {"quality_status": "PASS"},
        "evidence_envelope": {
            "typed_evidence": [],
            "typed_evidence_validation": {"quality_status": "PASS"},
        },
        "content": content,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def test_disabled_by_default():
    module = load_module()
    assert module.load_final_rollout_config({})["enabled"] is False


def test_config_caps_repairs_at_one():
    module = load_module()
    config = module.load_final_rollout_config({
        "TRACE_NET_H30_FINAL_ENGRAM_MAX_REPAIRS": "9",
    })
    assert config["max_repairs"] == 1


def test_partial_skill_fallback():
    module = load_module()
    sample = result(
        "candidate_discovery",
        "guided_part_discovery",
    )
    selected = module.select_primary_skill(sample)
    assert selected["skill_id"] == "partial_identifier_discovery"


def test_manufacturer_atom_selects_manufacturer_skill():
    module = load_module()
    sample = result(
        "no_evidence",
        "nomenclature_function_search",
        atoms={"manufacturer_terms": ["ACME"]},
    )
    selected = module.select_primary_skill(sample)
    assert (
        selected["skill_id"]
        == "manufacturer_plus_description_discovery"
    )


def test_partial_followups_prioritize_adjacent_characters():
    module = load_module()
    sample = result(
        "candidate_discovery",
        "guided_part_discovery",
        atoms={
            "identifier_mode": "contains",
            "normalized_identifier": "41824",
        },
        candidates=8,
    )
    plan = module.build_information_gain_followups(
        sample,
        maximum=3,
    )
    assert plan["records"][0]["topic"] == (
        "adjacent_identifier_characters"
    )


def test_known_manufacturer_is_not_reasked():
    module = load_module()
    sample = result(
        "candidate_discovery",
        "guided_part_discovery",
        atoms={
            "identifier_mode": "prefix",
            "part_prefix": "123",
            "manufacturer_terms": ["ACME"],
        },
        candidates=6,
    )
    plan = module.build_information_gain_followups(
        sample,
        maximum=3,
    )
    assert "manufacturer" not in [
        row["topic"] for row in plan["records"]
    ]


def test_exact_page_supplied_suppresses_which_page_followups():
    module = load_module()
    sample = result(
        "semantic_graph_summary_guidance",
        "document_page_navigation",
    )
    # The exact-page content bridge found the requested page.
    sample["evidence_envelope"]["coverage"] = {
        "page_content": {
            "available": True,
            "pages": [{"page_id": "t_p_120_1176_p000018"}],
        }
    }
    plan = module.build_information_gain_followups(sample, maximum=3)
    topics = [row["topic"] for row in plan["records"]]
    assert "exact_source_location" not in topics
    assert "figure_table_item" not in topics
    assert "document_family" not in topics


def test_conflict_questions_request_source_resolution():
    module = load_module()
    sample = result(
        "conflict_limited",
        "guided_part_discovery",
        candidates=4,
    )
    plan = module.build_information_gain_followups(
        sample,
        maximum=3,
    )
    topics = [row["topic"] for row in plan["records"]]
    assert "manual_revision" in topics
    assert "exact_source_location" in topics


def test_authority_questions_request_authority_context():
    module = load_module()
    sample = result(
        "authority_not_found",
        "authority_eligibility_verification",
        atoms={
            "identifier_mode": "exact",
            "normalized_identifier": "120-41824-003",
        },
    )
    plan = module.build_information_gain_followups(
        sample,
        maximum=3,
    )
    topics = [row["topic"] for row in plan["records"]]
    assert "authority_document" in topics
    assert "effectivity" in topics


def test_followup_section_is_replaced_not_duplicated():
    module = load_module()
    text = (
        "Safe answer.\n\nHelpful follow-up questions:\n"
        "- Old question?"
    )
    updated = module.apply_followup_section(
        text,
        ["New question?"],
    )
    assert updated.count(module.FOLLOWUP_MARKER) == 1
    assert "Old question?" not in updated


def test_critic_passes_safe_candidate():
    module = load_module()
    sample = result(
        "candidate_discovery",
        "guided_part_discovery",
        atoms={
            "identifier_mode": "contains",
            "normalized_identifier": "41824",
        },
        candidates=3,
    )
    plan = module.build_information_gain_followups(
        sample,
        maximum=3,
    )
    sample["content"] = module.apply_followup_section(
        sample["content"],
        plan["questions"],
    )
    critic = module.run_final_self_rag_critic(
        sample,
        maximum_followups=3,
    )
    assert critic["quality_status"] == "PASS"


def test_critic_rejects_positive_claim_in_candidate_mode():
    module = load_module()
    sample = result(
        "candidate_discovery",
        "guided_part_discovery",
        candidates=3,
    )
    sample["content"] = (
        "The part number is 120-41824-003 and it is confirmed."
    )
    critic = module.run_final_self_rag_critic(
        sample,
        maximum_followups=3,
    )
    assert critic["quality_status"] == "FAIL"
    assert "non_direct_positive_proof_claim" in critic["failures"]


def test_repair_is_bounded_and_recovers_candidate_mode():
    module = load_module()
    sample = result(
        "candidate_discovery",
        "guided_part_discovery",
        atoms={
            "identifier_mode": "contains",
            "normalized_identifier": "41824",
        },
        candidates=3,
    )
    sample["content"] = "The part number is 120-41824-003."
    plan = module.build_information_gain_followups(
        sample,
        maximum=3,
    )
    repair = module.run_bounded_final_repair(
        sample,
        followup_plan=plan,
        maximum_repairs=1,
        maximum_followups=3,
    )
    assert repair["repair_count"] == 1
    assert repair["final_critic"]["quality_status"] == "PASS"
    assert repair["retrieval_reexecuted"] is False


def test_no_repair_can_select_new_evidence():
    module = load_module()
    assert (
        module.SAFETY_CONTRACT["repair_can_select_new_evidence"]
        is False
    )


def test_health_closes_phases_6_through_10():
    module = load_module()
    health = module.final_rollout_health({
        "TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_ENABLED": "1",
    })
    assert health["completed_roadmap_phases"] == [6, 7, 8, 9, 10]
    assert health["quality_status"] == "PASS"
    assert health["answer_permission"] is False


def test_all_five_skills_are_supported():
    module = load_module()
    assert len(module.SUPPORTED_SKILL_IDS) == 5


def test_runtime_wiring_and_skip_switch_present():
    writer = WRITER_PATH.read_text(encoding="utf-8")
    launcher = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "install_final_engram_rollout" in writer
    assert "TRACE_NET_RUN_CRITICAL_LIVE_ROUTE_SMOKE" in launcher
    assert "SKIPPING FIVE CRITICAL LIVE ROUTE TESTS" in launcher
    assert "TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_ENABLED" in launcher
