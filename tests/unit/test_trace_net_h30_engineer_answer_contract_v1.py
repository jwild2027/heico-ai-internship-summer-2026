from __future__ import annotations

import importlib.util
import py_compile
import sys
from pathlib import Path

MODULE_PATH = Path("src/trace_net/writing/trace_net_h30_engineer_answer_contract_v1.py")
WRITER_PATH = Path("scripts/operations/serving/serve_trace_net_full_gemma_cognitive_v1.py")
COLD_PATH = Path("src/trace_net/serving/adapters/trace_net_h30_cold_start_streaming_v1.py")


def load_contract():
    spec = importlib.util.spec_from_file_location("trace_net_h30_engineer_answer_contract_v1", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def result_with(*, route="exact_identifier_lookup", direct=None, visual=None, authority=None, contradictions=None):
    return {
        "route": route,
        "selected_tunnel": route,
        "content": "Part AB12C-120-41824-003 appears in the cited source field [1].",
        "query_atoms": {"authority_requested": route == "authority_eligibility_verification"},
        "route_plan": {"authority_required": route == "authority_eligibility_verification"},
        "evidence_envelope": {
            "direct_evidence": direct or [],
            "candidate_evidence": [],
            "semantic_guidance": [],
            "visual_guidance": visual or [],
            "authority_evidence": authority or [],
            "contradictions": contradictions or [],
            "uncertainties": [],
            "coverage": {},
        },
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def test_strict_alphanumeric_prefix_is_preserved_exactly():
    mod = load_contract()
    value = mod.clean_engineer_text("Part AB12C-120-41824-003 is a visual-guidance match.")
    assert "AB12C-120-41824-003" in value


def test_no_unrelated_fallback_candidate_is_added():
    mod = load_contract()
    output = mod.apply_engineer_answer_contract(result_with(visual=[{"part_numbers": ["AB12C-120-41824-003"]}]))
    assert "120-99999-001" not in output["content"]
    assert output["content"].count("AB12C-120-41824-003") == 1


def test_obvious_ocr_noise_line_is_rejected():
    mod = load_contract()
    value = mod.clean_engineer_text("Useful source line [1].\n||||~~~~^^^^\nPart AB12C-120-41824-003.")
    assert "||||~~~~^^^^" not in value
    assert "Useful source line [1]." in value
    assert "AB12C-120-41824-003" in value


def test_duplicate_follow_up_line_is_removed_once():
    mod = load_contract()
    value = mod.clean_engineer_text("Provide another identifying clue.\nProvide another identifying clue.")
    assert value.count("Provide another identifying clue.") == 1


def test_cleaner_removes_confirmed_visual_wording_without_changing_identifier():
    mod = load_contract()
    value = mod.clean_engineer_text("TRACE-Net found confirmed visual guidance for AB12C-120-41824-003.")
    assert "confirmed visual guidance" not in value.lower()
    assert "visual guidance" in value.lower()
    assert "AB12C-120-41824-003" in value


def test_direct_source_answer_uses_contract_and_preserves_citation():
    mod = load_contract()
    output = mod.apply_engineer_answer_contract(result_with(direct=[{
        "page_id": "t_p_120_1176_p000202",
        "field_name": "part_number",
        "normalized_value": "AB12C-120-41824-003",
        "citation_ready": True,
    }]))
    text = output["content"]
    assert text.startswith("## Answer")
    assert "## Evidence" in text
    assert "## Engineering confidence" in text
    assert "## Limits" in text
    assert "[1]" in text
    assert "Source-backed for the specifically cited claims only." in text
    assert output["engineer_answer_contract"]["evidence_mode"] == "direct_source"


def test_guidance_only_answer_stays_explicitly_non_proof():
    mod = load_contract()
    result = result_with(visual=[{"page_id": "t_p_120_1176_p000084", "part_numbers": ["AB12C-120-41824-003"]}])
    result["content"] = "TRACE-Net found confirmed visual guidance for AB12C-120-41824-003."
    output = mod.apply_engineer_answer_contract(result)
    assert "confirmed visual guidance" not in output["content"].lower()
    assert "does not prove the requested claim" in output["content"]
    assert output["engineer_answer_contract"]["evidence_mode"] == "guidance_only"


def test_authority_request_without_authority_evidence_fails_closed():
    mod = load_contract()
    result = result_with(route="authority_eligibility_verification")
    result["content"] = "No citation-ready authority evidence was found."
    text = mod.apply_engineer_answer_contract(result)["content"]
    assert "No explicit authority was found" in text
    assert "installation" in text


def test_contradictions_are_not_silently_resolved():
    mod = load_contract()
    output = mod.apply_engineer_answer_contract(result_with(
        direct=[{"page_id": "p1", "normalized_value": "A"}],
        contradictions=[{"left": "A", "right": "B"}],
    ))
    assert output["engineer_answer_contract"]["evidence_mode"] == "contradictory"
    assert "conflict is surfaced rather than silently resolved" in output["content"]


def test_route_and_tunnel_are_preserved():
    mod = load_contract()
    result = result_with(route="document_page_navigation")
    result["selected_tunnel"] = "navigation_fastpath"
    output = mod.apply_engineer_answer_contract(result)
    assert output["route"] == "document_page_navigation"
    assert output["selected_tunnel"] == "navigation_fastpath"


def test_general_chat_is_not_wrapped():
    mod = load_contract()
    result = result_with(route="safe_general_chat")
    result["content"] = "Hello!"
    assert mod.apply_engineer_answer_contract(result)["content"] == "Hello!"


def test_all_safety_flags_are_reasserted_false():
    mod = load_contract()
    result = result_with()
    result.update({
        "answer_permission": True,
        "final_answer_allowed": True,
        "can_answer_directly": True,
        "can_prove_claims": True,
        "source_truth_mutation_allowed": True,
    })
    output = mod.apply_engineer_answer_contract(result)
    assert output["answer_permission"] is False
    assert output["final_answer_allowed"] is False
    assert output["can_answer_directly"] is False
    assert output["can_prove_claims"] is False
    assert output["source_truth_mutation_allowed"] is False


def test_prompt_rules_cover_answer_quality_contract():
    rules = load_contract().engineer_answer_contract_prompt_rules().lower()
    assert "strict alphanumeric identifier prefix" in rules
    assert "unrelated fallback candidates" in rules
    assert "ocr garbage" in rules
    assert "repeat identical follow-up" in rules
    assert "matching citation" in rules
    assert "confirmed proof" in rules


def test_writer_and_cold_streaming_integration_markers_are_present():
    writer = WRITER_PATH.read_text(encoding="utf-8")
    cold = COLD_PATH.read_text(encoding="utf-8")
    assert "trace_net_h30_engineer_answer_contract_v1" in writer
    assert "engineer_answer_contract_prompt_rules()" in writer
    assert "apply_engineer_answer_contract" in writer
    assert 'module.get("apply_engineer_answer_contract")' in cold
    assert 'module.get("engineer_answer_contract_health")' in cold


def test_syntax_and_import_integrity():
    py_compile.compile(str(MODULE_PATH), doraise=True)
    assert load_contract().MODULE == "trace_net_h30_engineer_answer_contract_v1"
