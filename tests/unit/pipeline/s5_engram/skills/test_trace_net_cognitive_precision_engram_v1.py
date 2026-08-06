from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROUTER = Path("scripts/operations/s6_retrieval/serve_trace_net_cognitive_router_v1.py")
WRITER = Path("scripts/operations/writing/serve_trace_net_full_gemma_cognitive_v1.py")
HELPER = Path("src/trace_net/pipeline/s5_engram/skills/trace_net_h30_cognitive_precision_v1.py")
ENGRAM = Path(
    "local_data/organization/trace_net/cognitive_openwebui_regression_engram_v1/"
    "trace_net_cognitive_openwebui_regression_engram_v1.json"
)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_identifier_fragment_rejects_prose_but_accepts_real_clues():
    helper = load(HELPER, "cognitive_precision_helper_v1_a")
    assert helper.valid_identifier_fragment("THE") is False
    assert helper.valid_identifier_fragment("41824") is True
    assert helper.valid_identifier_fragment("MS49") is True


def test_contain_the_strongest_evidence_does_not_extract_the():
    router = load(ROUTER, "cognitive_router_precision_v1_a")
    atoms = router.extract_query_atoms(
        "Which source document and page contain the strongest evidence for part 120-41824-003?"
    )
    assert atoms.part_contains is None
    assert atoms.exact_part_numbers == ["120-41824-003"]
    assert router.plan_route(atoms).primary_route == "document_page_navigation"


def test_cover_does_not_match_inside_recover_or_coverage():
    router = load(ROUTER, "cognitive_router_precision_v1_b")
    recover = router.extract_query_atoms(
        "Use OCR to recover readable labels for part 120-41824-003"
    )
    coverage = router.extract_query_atoms(
        "Summarize coverage for part 120-41824-003 across every page"
    )
    assert "cover" not in recover.nomenclature_terms
    assert "cover" not in coverage.nomenclature_terms
    assert router.plan_route(recover).primary_route == "ocr_scan_recovery"
    assert router.plan_route(coverage).primary_route == "high_degree_entity_aggregation"


def test_explicit_topic_discovery_precedes_incidental_seat_noun():
    router = load(ROUTER, "cognitive_router_precision_v1_c")
    atoms = router.extract_query_atoms(
        "Find pages about corrosion prevention for passenger seat components, even when the exact phrase is not used."
    )
    assert "seat" in atoms.nomenclature_terms
    assert router.plan_route(atoms).primary_route == "semantic_discovery"


def test_entity_gate_removes_visual_for_different_part():
    helper = load(HELPER, "cognitive_precision_helper_v1_b")
    rows = [
        {"page_id": "p1", "part_numbers": ["120-41824-003"], "figure_refs": ["figure 2"]},
        {"page_id": "p2", "part_numbers": ["120-41824-217"], "figure_refs": ["figure 8a"]},
        {"page_id": "p3", "subject": "context with no explicit identifier"},
    ]
    kept, dropped = helper.filter_entity_consistent(rows, ["120-41824-003"])
    assert [row["page_id"] for row in kept] == ["p1", "p3"]
    assert [row["page_id"] for row in dropped] == ["p2"]


def test_multi_question_is_decomposed_by_claim_type():
    router = load(ROUTER, "cognitive_router_precision_v1_d")
    helper = load(HELPER, "cognitive_precision_helper_v1_c")
    atoms = router.extract_query_atoms(
        "Find part 120-41824-003, identify its nomenclature and parent assembly, locate its figure and IPL row, and determine whether 120-41824-007 is explicitly approved as a replacement."
    )
    queries = helper.decompose_claim_queries(atoms.latest_query, atoms)
    assert router.plan_route(atoms).primary_route == "multi_question_research"
    assert any("exact citation-ready" in query for query in queries)
    assert any("illustrated parts list" in query for query in queries)
    assert any("figure, drawing" in query for query in queries)
    assert any("explicit approval" in query for query in queries)


def test_specialized_routes_generate_typed_retrieval_attempts():
    helper = load(HELPER, "cognitive_precision_helper_v1_specialized")
    class Atoms:
        exact_part_numbers = ["120-41824-003"]
        items = ["14"]
    table_queries = helper.specialized_route_queries(
        "exact_table_ipl_lookup", "Search the IPL for item 14", Atoms()
    )
    ocr_queries = helper.specialized_route_queries(
        "ocr_scan_recovery", "The scan is blurry", Atoms()
    )
    assert any("rows and cells" in query for query in table_queries)
    assert any("OCR recovery" in query for query in ocr_queries)


def test_runtime_selects_small_relevant_engram_pack():
    helper = load(HELPER, "cognitive_precision_helper_v1_d")
    memory = helper.select_engram_memory(
        "Is 120-41824-007 approved as a replacement for 120-41824-003?",
        "authority_eligibility_verification",
        ["exact_identifier", "authority"],
        path=str(ENGRAM),
        maximum_atoms=6,
    )
    assert memory["quality_status"] == "PASS"
    assert 1 <= memory["atom_count"] <= 6
    assert memory["proof_role"] == "guidance_only"
    assert memory["citable"] is False
    assert "h30_openwebui_authority_boundary_v1" in memory["atom_ids"]


def test_writer_prompt_receives_engram_as_uncitable_behavior_guidance():
    writer = load(WRITER, "gemma_cognitive_precision_v1")
    result = {
        "route": "exact_identifier_lookup",
        "content": "Safe draft",
        "engram_memory": {
            "proof_role": "guidance_only",
            "citable": False,
            "atoms": [{"atom_id": "x", "rule": "Do not promote guidance to proof."}],
        },
        "evidence_envelope": {
            "direct_evidence": [{
                "page_id": "t_p_120_1176_p000202",
                "field_name": "part_number",
                "normalized_value": "120-41824-003",
            }],
            "authority_evidence": [],
            "contradictions": [],
        },
    }
    prompt = writer.build_prompt("Find part 120-41824-003", result)
    assert "ENGRAM BEHAVIOR MEMORY" in prompt
    assert "NEVER CITE" in prompt
    assert "Do not promote guidance to proof" in prompt


def test_engram_artifact_is_guidance_only():
    value = json.loads(ENGRAM.read_text(encoding="utf-8"))
    assert value["quality_status"] == "PASS"
    assert len(value["memory_atoms"]) >= 8
    assert all(atom["proof_role"] == "guidance_only" for atom in value["memory_atoms"])
