from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path("scripts/serve_trace_net_full_gemma_cognitive_v1.py")


def load():
    spec = importlib.util.spec_from_file_location("gemma_cognitive_v1", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["gemma_cognitive_v1"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def base_result():
    return {
        "route": "exact_identifier_lookup",
        "evidence_envelope": {
            "direct_evidence": [{
                "page_id": "t_p_120_1176_p000202",
                "field_name": "part_number",
                "normalized_value": "120-41824-003",
            }],
            "authority_evidence": [],
            "candidate_evidence": [],
            "semantic_guidance": [],
            "visual_guidance": [],
            "contradictions": [],
        },
    }


def test_valid_supported_answer_is_accepted():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-41824-003 appears in the cited source field [1].",
        "Find part 120-41824-003",
        result,
    )
    assert check["accepted"] is True


def test_unknown_part_number_is_rejected():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-99999-001 is the answer [1].",
        "Find part 120-41824-003",
        result,
    )
    assert check["accepted"] is False
    assert any(item.startswith("unsupported_part_number") for item in check["failures"])


def test_missing_citation_is_rejected():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-41824-003 appears in the source.",
        "Find part 120-41824-003",
        result,
    )
    assert check["accepted"] is False
    assert "direct_answer_missing_citation" in check["failures"]


def test_approval_claim_without_authority_is_rejected():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-41824-003 is an approved replacement [1].",
        "Is part 120-41824-003 an approved replacement?",
        result,
    )
    assert check["accepted"] is False
    assert "dangerous_claim_without_explicit_authority" in check["failures"]


def test_uncited_factual_line_is_rejected_even_when_another_line_has_a_citation():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-41824-003 appears in the source [1].\nThe manual lists it as a locking ring.",
        "Find part 120-41824-003",
        result,
    )
    assert check["accepted"] is False
    assert "uncited_factual_line" in check["failures"]


PAGE = "t_p_120_1176_p000482"


def page_result():
    """A page-navigation result whose only evidence is exact-page content (no
    direct proof bucket) with OCR (supporting) and V1/V2 (guidance) records."""
    ocr = {
        "kind": "ocr", "authority": "supporting", "page_id": PAGE,
        "text": "Install the new leg structure (P/N 120-29074-005).",
        "nomenclature": [], "ata": "", "source_resolved": True,
    }
    v1 = {"kind": "v1_context", "authority": "guidance", "page_id": PAGE,
          "text": "Seat leg replacement procedure.", "nomenclature": [], "ata": ""}
    pack = {"page_id": PAGE, "ocr": [ocr], "tables": [], "v1_context": [v1],
            "v2_context": [], "v3_page_intelligence": [], "visuals": [], "parts": [], "conflicts": []}
    return {
        "route": "procedure_task_lookup",
        "evidence_envelope": {
            "direct_evidence": [], "authority_evidence": [], "candidate_evidence": [],
            "semantic_guidance": [], "visual_guidance": [], "contradictions": [],
            "coverage": {"page_content": {"available": True, "pages": [pack], "telemetry": {}}},
        },
    }


def test_page_content_records_become_separate_typed_citations():
    mod = load()
    result = page_result()
    registry = mod.citation_registry(result)
    page_entries = [e for e in registry if e.get("page_content")]
    classes = {e["class"] for e in page_entries}
    assert {"page_ocr_text", "page_v1_context"} <= classes
    ocr_entry = next(e for e in page_entries if e["class"] == "page_ocr_text")
    assert ocr_entry["authority"] == "supporting" and ocr_entry["can_prove_claims"] is False
    v1_entry = next(e for e in page_entries if e["class"] == "page_v1_context")
    assert v1_entry["guidance_only"] is True
    # Telemetry records which ids are page content.
    telem = result["evidence_envelope"]["coverage"]["page_content"]["telemetry"]
    assert telem["page_content_registry_count"] == len(page_entries)
    assert telem["page_content_citation_ids"] == [e["citation_id"] for e in page_entries]


def test_ocr_part_number_is_allowed_and_cited_answer_accepted():
    mod = load()
    result = page_result()
    registry = mod.citation_registry(result)
    ocr_id = next(e["citation_id"] for e in registry if e["class"] == "page_ocr_text")
    check = mod.validate_answer(
        f"The page describes installing the new leg structure (P/N 120-29074-005) [{ocr_id}].",
        "What procedure is on page t_p_120_1176_p000482?",
        result,
        registry=registry,
    )
    assert check["accepted"] is True, check["failures"]


def test_page_content_identifier_without_citation_is_rejected():
    mod = load()
    result = page_result()
    registry = mod.citation_registry(result)
    check = mod.validate_answer(
        "The page installs part 120-29074-005.",
        "What procedure is on page t_p_120_1176_p000482?",
        result,
        registry=registry,
    )
    assert check["accepted"] is False
    assert "uncited_page_content_identifier" in check["failures"]


def test_page_content_prompt_includes_supporting_tier_and_citation_ids():
    mod = load()
    result = page_result()
    registry = mod.citation_registry(result)
    prompt = mod.build_prompt("procedure on page", result, registry=registry)
    assert "SUPPORTING PAGE SOURCE" in prompt
    assert "EXACT PAGE CONTENT" in prompt
    ocr_id = next(e["citation_id"] for e in registry if e["class"] == "page_ocr_text")
    assert f"[{ocr_id}]" in prompt  # per-record id rendered into the page block

# TRACE_NET_H30_PHASE5_RESIDUAL_REPAIR_V1

def test_high_degree_aggregation_allows_explicit_coverage_telemetry_without_claim_citations():
    mod = load()
    result = base_result()
    result["route"] = "high_degree_entity_aggregation"
    check = mod.validate_answer(
        "Part 120-41824-003 appears in the source [1].\n"
        "- **Coverage telemetry — matching pages:** 6\n"
        "- **Coverage telemetry — page:** `t_p_120_1176_p000202`\n"
        "- **Coverage telemetry — scope:** Indexed artifacts only.",
        "Show every document mentioning part 120-41824-003.",
        result,
    )
    assert check["accepted"] is True, check["failures"]


def test_coverage_telemetry_exemption_is_not_available_to_other_routes():
    mod = load()
    result = base_result()
    check = mod.validate_answer(
        "Part 120-41824-003 appears in the source [1].\n"
        "- **Coverage telemetry — matching pages:** 6",
        "Find part 120-41824-003.",
        result,
    )
    assert check["accepted"] is False
    assert "uncited_factual_line" in check["failures"]
