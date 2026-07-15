from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

HELPER = Path("scripts/trace_net_h30_retrieval_completion_v1.py")
BOUNDARY = Path("scripts/trace_net_h30_answer_boundary_v1.py")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_exact_navigation_seed_excludes_semantic_noise():
    mod = load(HELPER, "navigation_rank_v3_seed")
    envelope = SimpleNamespace(
        direct_evidence=[],
        candidate_evidence=[],
        visual_guidance=[{
            "page_id": "t_p_120_1176_p000084",
            "part_numbers": ["120-41824-003"],
        }],
        semantic_guidance=[{
            "page_id": "t_p_120_1176_p000003",
            "part_numbers": [],
        }],
    )
    assert mod._seed_pages(
        envelope,
        ["120-41824-003"],
    ) == ["t_p_120_1176_p000084"]


def test_visual_exact_page_outranks_ocr_token_noise():
    mod = load(HELPER, "navigation_rank_v3_lead")
    envelope = SimpleNamespace(
        direct_evidence=[],
        candidate_evidence=[],
        semantic_guidance=[],
        visual_guidance=[{
            "page_id": "t_p_120_1176_p000084",
            "part_numbers": ["120-41824-003"],
            "figure_refs": ["figure 2 sheet 1"],
            "subject": "visual page associated with part number(s): 120-41824-003",
        }],
        coverage={
            "navigation_leads": [
                {
                    "page_id": "t_p_120_1176_p000003",
                    "source_type": "ocr",
                    "snippet": "EMBRAER",
                    "part_numbers": [],
                },
                {
                    "page_id": "t_p_120_1176_p000003",
                    "source_type": "ocr",
                    "snippet": "MAINTENANCE",
                    "part_numbers": [],
                },
            ]
        },
    )
    rows = mod._lead_rows(envelope, ["120-41824-003"])
    assert len(rows) == 1
    assert rows[0]["page_id"] == "t_p_120_1176_p000084"
    assert rows[0]["source_type"] == "visual"


def test_navigation_renderer_emits_page_84_once_without_ocr_tokens():
    mod = load(HELPER, "navigation_rank_v3_render")
    atoms = SimpleNamespace(exact_part_numbers=["120-41824-003"])
    envelope = SimpleNamespace(
        direct_evidence=[],
        candidate_evidence=[],
        semantic_guidance=[],
        visual_guidance=[{
            "page_id": "t_p_120_1176_p000084",
            "part_numbers": ["120-41824-003"],
            "figure_refs": ["figure 2 sheet 1"],
            "subject": "visual page associated with part number(s): 120-41824-003",
        }],
        coverage={
            "navigation_leads": [{
                "page_id": "t_p_120_1176_p000003",
                "source_type": "ocr",
                "snippet": "EMBRAER",
                "part_numbers": [],
            }]
        },
    )
    text = mod.render_navigation_answer(
        atoms,
        envelope,
        {"quality_status": "PASS"},
    )
    assert text.count("t_p_120_1176_p000084") == 1
    assert "t_p_120_1176_p000003" not in text
    assert "EMBRAER" not in text
    assert "figure 2 sheet 1" in text


def test_navigation_disclaimer_does_not_trigger_authority_boundary():
    boundary = load(BOUNDARY, "navigation_rank_v3_boundary")
    answer = (
        "Strongest currently resolved navigation lead(s):\\n"
        "- page t_p_120_1176_p000084 — visual guidance\\n"
        "These page locations are navigation guidance only. "
        "They identify where to inspect next but do not establish any technical claim."
    )
    text = boundary.enforce_h30_answer_boundaries(
        route="document_page_navigation",
        query=(
            "Which source document and page contain the strongest evidence "
            "for part 120-41824-003?"
        ),
        query_atoms={
            "exact_part_numbers": ["120-41824-003"],
            "requested_claims": ["exact_identifier"],
        },
        evidence_envelope={
            "direct_evidence": [],
            "authority_evidence": [],
            "contradictions": [],
        },
        answer=answer,
    )
    assert "No explicit authority was found" not in text
    assert "t_p_120_1176_p000084" in text
