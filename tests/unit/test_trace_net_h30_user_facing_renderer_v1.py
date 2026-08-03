from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path("src/trace_net/writing/trace_net_h30_user_facing_renderer_v1.py")
ROUTER_PATH = Path("scripts/operations/router/serve_trace_net_cognitive_router_v1.py")


def load_renderer():
    spec = importlib.util.spec_from_file_location("trace_net_h30_user_facing_renderer_v1", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_router():
    spec = importlib.util.spec_from_file_location("trace_net_cognitive_router_v1", ROUTER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def envelope(**kwargs):
    defaults = {
        "direct_evidence": [],
        "candidate_evidence": [],
        "visual_guidance": [],
        "semantic_guidance": [],
        "authority_evidence": [],
        "contradictions": [],
        "coverage": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_safe_to_install_authority_is_not_procedure_or_multi_question():
    mod = load_router()
    atoms = mod.extract_query_atoms(
        "Is part 120-41824-003 explicitly approved as an interchangeable replacement "
        "for 120-41824-007 and safe to install?"
    )
    plan = mod.plan_route(atoms)
    assert atoms.authority_requested is True
    assert atoms.procedure_requested is False
    assert "procedure" not in atoms.requested_claims
    assert atoms.multi_question is False
    assert plan.primary_route == "authority_eligibility_verification"


def test_explicit_installation_steps_remain_multi_question():
    mod = load_router()
    atoms = mod.extract_query_atoms(
        "Is part 120-41824-003 approved for installation and what are the installation steps?"
    )
    plan = mod.plan_route(atoms)
    assert atoms.authority_requested is True
    assert atoms.procedure_requested is True
    assert "procedure" in atoms.requested_claims
    assert atoms.multi_question is True
    assert plan.primary_route == "multi_question_research"


def test_claim_renderer_hides_internal_ids_and_hashes():
    mod = load_renderer()
    atoms = SimpleNamespace(latest_query="complex", exact_part_numbers=["120-41824-003"])
    env = envelope(
        coverage={
            "claim_results": {
                "table_value": {
                    "status": "GUIDANCE_ONLY",
                    "direct_evidence": [],
                    "guidance": [{
                        "document": "table_exact_search::t_p_120_1176_p000003::covered_part_number::ae28c8694c95f9d6",
                        "page_id": "t_p_120_1176_p000003",
                        "value": "120-41824-003",
                    }],
                }
            }
        }
    )
    text = mod.render_claims(atoms, env)
    assert "::" not in text
    assert "ae28c8694c95f9d6" not in text
    assert "t_p_120_1176_p000003" in text
    assert "120-41824-003" in text


def test_ocr_renderer_shows_missing_engine_confidence_and_text():
    mod = load_renderer()
    atoms = SimpleNamespace(exact_part_numbers=["120-41824-003"])
    env = envelope(
        coverage={
            "ocr_evidence": [{
                "page_id": "t_p_120_1176_p000084",
                "citation_ready": True,
                "engine": "",
                "confidence": "",
                "snippet": "",
            }]
        }
    )
    text = mod.render_ocr(atoms, env)
    assert "OCR engine" in text
    assert "Confidence" in text
    assert text.count("Not stored") >= 2
    assert "No readable text stored" in text


def test_ocr_renderer_collapses_duplicate_empty_rows_per_page():
    mod = load_renderer()
    atoms = SimpleNamespace(exact_part_numbers=["120-41824-003"])
    duplicate = {
        "page_id": "t_p_120_1176_p000084",
        "citation_ready": True,
        "engine": "",
        "confidence": "",
        "snippet": "",
    }
    env = envelope(coverage={"ocr_evidence": [duplicate, dict(duplicate)]})
    text = mod.render_ocr(atoms, env)
    assert text.count("t_p_120_1176_p000084") == 1


def test_navigation_renderer_dedupes_page_and_has_one_footer():
    mod = load_renderer()
    atoms = SimpleNamespace(exact_part_numbers=["120-41824-003"])
    env = envelope(
        visual_guidance=[{
            "page_id": "t_p_120_1176_p000084",
            "part_numbers": ["120-41824-003"],
            "figure_refs": ["figure 2 sheet 1"],
            "subject": "visual page associated with part number 120-41824-003",
            "source_type": "visual",
        }],
        coverage={
            "navigation_leads": [{
                "page_id": "t_p_120_1176_p000084",
                "part_numbers": ["120-41824-003"],
                "source_type": "ocr",
                "snippet": "",
            }]
        },
    )
    text = mod.render_navigation(atoms, env)
    assert text.count("t_p_120_1176_p000084") == 1
    assert "figure 2 sheet 1" in text
    assert text.count("**Evidence status:**") == 1


def test_authority_renderer_starts_with_direct_conclusion():
    mod = load_renderer()
    atoms = SimpleNamespace(
        latest_query=(
            "Is part 120-41824-003 an approved replacement for 120-41824-007 "
            "and safe to install?"
        )
    )
    text = mod.render_authority(atoms, envelope())
    assert text.startswith("## Result: Not confirmed")
    assert "Procedure" not in text
    assert "interchangeability" in text
    assert "installation approval or safety" in text
    assert text.count("**Evidence status:**") == 1


def test_finalize_content_removes_boundary_boilerplate_and_internal_tokens():
    mod = load_renderer()
    text = (
        "## Claim results\n"
        "table_exact_search::page::field::ae28c8694c95f9d6\n"
        + mod.PROOF_BOUNDARY
        + "\n"
        + mod.AUTHORITY_BOUNDARY
    )
    final = mod.finalize_content("multi_question_research", text, {})
    assert "::" not in final
    assert "ae28c8694c95f9d6" not in final
    assert mod.PROOF_BOUNDARY not in final
    assert mod.AUTHORITY_BOUNDARY not in final

# TRACE_NET_H30_PHASE5_RESIDUAL_REPAIR_V1

def test_aggregation_renderer_labels_uncited_index_counts_as_coverage_telemetry():
    mod = load_renderer()
    atoms = SimpleNamespace(exact_part_numbers=["120-36834-523"])
    env = envelope(coverage={
        "aggregate_records": [
            {"page_id": "t_p_120_1176_p000309", "document": "manual-a"},
            {"page_id": "t_p_120_1176_p000326", "document": "manual-a"},
        ],
        "retrieval_completion": {
            "scanned_file_count": 400,
            "matched_file_count": 107,
            "coverage_complete_for_candidate_files": False,
        },
    })
    text = mod.render_aggregation(atoms, env)
    assert "Coverage telemetry — matching pages" in text
    assert "Coverage telemetry — matching documents" in text
    assert "Coverage telemetry — page" in text
    assert "Coverage telemetry — scope" in text
