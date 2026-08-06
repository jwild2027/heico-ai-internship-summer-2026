from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

WRITER_PATH = Path("scripts/operations/writing/serve_trace_net_full_gemma_cognitive_v1.py")
OVERLAY_PATH = Path("src/trace_net/writing/answer_modes/trace_net_h30_exact_page_answer_mode_v1.py")
FINAL_PATH = Path("src/trace_net/validation/answer_quality/trace_net_h30_final_engram_rollout_v1.py")

PAGE = "t_p_120_1176_p000482"


def load_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def page_result(*, rejected: bool = False):
    ocr = {
        "kind": "ocr",
        "page_id": PAGE,
        "text": (
            "STEP 1 REMOVE PART 120-29074-005. "
            "STEP 2 CHECK 595-37778 AND 595-37038. "
            "STEP 3 INSTALL 120-29074-015 AND 120-29919-001. "
            "EFFECTIVITY: ALL."
        ),
        "origin": "artifact",
        "authority": "supporting",
        "guidance_only": False,
        "source_resolved": True,
        "nomenclature": [],
        "ata": "25-21-00",
    }
    visual = {
        "kind": "visual",
        "page_id": PAGE,
        "text": "The exact-page visual record shows the lateral leg structure.",
        "origin": "artifact",
        "authority": "guidance",
        "guidance_only": True,
        "source_resolved": False,
        "nomenclature": [],
        "ata": "25-21-00",
    }
    return {
        "route": "procedure_task_lookup",
        "content": (
            "TRACE-Net found semantic guidance on page t_p_120_1176_p000181.\n\n"
            "Helpful follow-up questions:\n"
            "- Are you trying to identify it, find its function, or verify approval?"
        ),
        "writer_mode": "deterministic_fallback_after_validation_failure" if rejected else "gemma_synthesis_guidance",
        "gemma_status": "LLM_OUTPUT_REJECTED" if rejected else "LLM_CALL_SUCCEEDED_AND_VALIDATED",
        "post_answer_validation": {
            "quality_status": "FAIL" if rejected else "PASS",
            "accepted": not rejected,
            "failures": ["unsupported_part_number:120-29074-005"] if rejected else [],
        },
        # Simulate the stale upstream registry that caused page registry count=0.
        "citation_registry": [
            {
                "citation_id": 1,
                "class": "semantic",
                "authority": "guidance",
                "can_prove_claims": False,
                "guidance_only": True,
                "claim_scope": "candidate_or_guidance",
                "candidate_value": "summary",
                "page_id": "t_p_120_1176_p000181",
                "page_ids": ["t_p_120_1176_p000181"],
                "ata": "",
                "ata_codes": [],
                "nomenclature": [],
                "source_resolved": False,
                "field_name": "summary",
                "value": "unrelated semantic lead",
            }
        ],
        "evidence_envelope": {
            "direct_evidence": [],
            "candidate_evidence": [],
            "visual_guidance": [],
            "semantic_guidance": [],
            "coverage": {
                "page_content": {
                    "available": True,
                    "page_count": 1,
                    "pages": [
                        {
                            "available": True,
                            "found": True,
                            "page_id": PAGE,
                            "ocr": [ocr],
                            "tables": [],
                            "visuals": [visual],
                            "v1_context": [],
                            "v2_context": [],
                            "v3_page_intelligence": [],
                            "parts": [],
                            "conflicts": [],
                            "source_trace": {"page_id": PAGE, "source_resolved": True},
                        }
                    ],
                    "telemetry": {
                        "exact_page_match": True,
                        "ocr_record_count": 1,
                        "visual_record_count": 1,
                        "cross_page_record_count": 0,
                        "page_content_record_count": 2,
                        "page_content_registry_count": 0,
                        "page_content_citation_ids": [],
                        "gemma_call_count_added": 0,
                    },
                }
            },
        },
        "follow_up_questions": [
            "Are you trying to identify it, find its function, or verify approval?"
        ],
        "answer_permission": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed": False,
    }


def test_final_registry_extends_stale_registry_with_page_records():
    writer = load_path(WRITER_PATH, "trace_net_exact_page_writer_registry_test")
    result = page_result(rejected=True)
    registry = writer.citation_registry(result)

    page_entries = [entry for entry in registry if entry.get("page_content")]
    assert len(page_entries) == 2
    assert page_entries[0]["authority"] == "supporting"
    assert "120-29074-005" in page_entries[0]["identifier_blob"]
    telemetry = result["evidence_envelope"]["coverage"]["page_content"]["telemetry"]
    assert telemetry["page_content_registry_count"] == 2
    assert len(telemetry["page_content_citation_ids"]) == 2
    assert result["citation_registry"] is registry


def test_literal_page_identifiers_validate_with_numeric_page_citation():
    writer = load_path(WRITER_PATH, "trace_net_exact_page_writer_validation_test")
    result = page_result(rejected=True)
    registry = writer.citation_registry(result)
    ocr_entry = next(
        entry
        for entry in registry
        if entry.get("page_content_kind") == "ocr"
    )
    citation = ocr_entry["citation_id"]
    answer = (
        f"Page `{PAGE}` prints part numbers 120-29074-005, 595-37778, "
        f"595-37038, 120-29074-015, and 120-29919-001 [{citation}]."
    )
    validation = writer.validate_answer(
        answer,
        f"What procedure is described on page {PAGE}?",
        result,
        registry=registry,
    )
    assert validation["accepted"], validation


def test_cited_exact_page_ocr_may_report_literal_effectivity_text():
    writer = load_path(WRITER_PATH, "trace_net_exact_page_writer_literal_authority_test")
    result = page_result(rejected=True)
    registry = writer.citation_registry(result)
    citation = next(
        entry["citation_id"]
        for entry in registry
        if entry.get("page_content_kind") == "ocr"
    )
    answer = (
        f"- **OCR text:** The page text reads: EFFECTIVITY: ALL [{citation}]"
    )
    validation = writer.validate_answer(
        answer,
        f"Explain page {PAGE}.",
        result,
        registry=registry,
    )
    assert validation["accepted"], validation


def test_unframed_effectivity_conclusion_still_requires_authority():
    writer = load_path(WRITER_PATH, "trace_net_exact_page_writer_effectivity_guard_test")
    result = page_result(rejected=True)
    registry = writer.citation_registry(result)
    citation = next(
        entry["citation_id"]
        for entry in registry
        if entry.get("page_content_kind") == "ocr"
    )
    validation = writer.validate_answer(
        f"Effectivity is ALL [{citation}].",
        f"Explain page {PAGE}.",
        result,
        registry=registry,
    )
    assert not validation["accepted"]
    assert "dangerous_claim_without_explicit_authority" in validation["failures"]


def test_authority_claim_still_fails_even_with_page_citation():
    writer = load_path(WRITER_PATH, "trace_net_exact_page_writer_authority_test")
    result = page_result(rejected=True)
    registry = writer.citation_registry(result)
    citation = next(
        entry["citation_id"]
        for entry in registry
        if entry.get("page_content_kind") == "ocr"
    )
    answer = f"Part 120-29074-005 is an approved replacement [{citation}]."
    validation = writer.validate_answer(
        answer,
        f"What procedure is described on page {PAGE}?",
        result,
        registry=registry,
    )
    assert not validation["accepted"]
    assert "dangerous_claim_without_explicit_authority" in validation["failures"]


def test_dangerous_matcher_does_not_treat_fittings_as_fits():
    writer = load_path(WRITER_PATH, "trace_net_exact_page_writer_danger_test")
    assert writer.contains_dangerous_claim("The diagram labels two fittings.") is False
    assert writer.contains_dangerous_claim("The part fits this installation.") is True


def test_rejected_gemma_uses_only_exact_page_fallback():
    writer = load_path(WRITER_PATH, "trace_net_exact_page_writer_overlay_test")
    overlay = load_path(OVERLAY_PATH, "trace_net_exact_page_overlay_test")
    sample = page_result(rejected=True)

    class FakeRuntime:
        def process(self, payload):
            return copy.deepcopy(sample)

        def health(self):
            return {"quality_status": "PASS"}

    module = {
        "Runtime": FakeRuntime,
        "citation_registry": writer.citation_registry,
        "citation_registry_digest": writer.citation_registry_digest,
        "validate_answer": writer.validate_answer,
        "extract_latest_user": writer.extract_latest_user,
        "synthesis_allowed_identifiers": writer.synthesis_allowed_identifiers,
    }
    overlay.install_exact_page_answer_mode(module)
    result = FakeRuntime().process({
        "messages": [{"role": "user", "content": f"Explain page {PAGE}."}]
    })

    assert result["post_answer_validation"]["accepted"], result["post_answer_validation"]
    assert result["answer_mode"]["mode"] == overlay.MODE_EXACT_PAGE
    assert PAGE in result["content"]
    assert "120-29074-005" in result["content"]
    assert "t_p_120_1176_p000181" not in result["content"]
    assert "Helpful follow-up questions:" not in result["content"]
    assert result["follow_up_questions"] == []
    assert result["exact_page_answer_mode"]["gemma_call_count_added"] == 0


def test_final_engram_generates_no_followup_for_found_exact_page():
    final = load_path(FINAL_PATH, "trace_net_exact_page_final_engram_test")
    result = page_result(rejected=True)
    result["answer_mode"] = {"mode": "exact_page_content", "candidate_count": 0}
    plan = final.build_information_gain_followups(result, maximum=3)
    assert plan["questions"] == []
    assert plan["suppression_reason"] == "exact_page_already_supplied_and_found"
