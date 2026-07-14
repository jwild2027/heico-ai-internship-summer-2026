from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path("scripts/serve_trace_net_cognitive_router_v1.py")


def load():
    spec = importlib.util.spec_from_file_location("cognitive_router_v1", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["cognitive_router_v1"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_route_registry_contains_every_planned_route():
    mod = load()
    assert mod.ALL_ROUTES == (
        "safe_general_chat",
        "exact_identifier_lookup",
        "guided_part_discovery",
        "ata_system_discovery",
        "nomenclature_function_search",
        "exact_table_ipl_lookup",
        "visual_figure_callout_lookup",
        "procedure_task_lookup",
        "warning_caution_note_lookup",
        "authority_eligibility_verification",
        "document_page_navigation",
        "graph_relationship_reasoning",
        "semantic_discovery",
        "cross_source_comparison",
        "contradiction_resolution",
        "ocr_scan_recovery",
        "high_degree_entity_aggregation",
        "multi_question_research",
        "clarification_no_evidence",
    )


def test_every_route_has_a_reachable_planner_example():
    mod = load()
    examples = {
        "safe_general_chat": "hello",
        "exact_identifier_lookup": "Find part 120-41824-003",
        "guided_part_discovery": "The P/N contains 41824",
        "ata_system_discovery": "I have a part and the ATA number starts with 25",
        "nomenclature_function_search": "Find the locking ring near the seat",
        "exact_table_ipl_lookup": "Search the IPL table for item 14",
        "visual_figure_callout_lookup": "Show the diagram for this component",
        "procedure_task_lookup": "How do I remove this assembly?",
        "warning_caution_note_lookup": "What warning applies to this task?",
        "authority_eligibility_verification": "Is this an approved replacement?",
        "document_page_navigation": "Which page discusses the component?",
        "graph_relationship_reasoning": "What assembly contains this part?",
        "semantic_discovery": "Find pages about corrosion prevention topics",
        "cross_source_comparison": "Compare both manuals for the same topic",
        "contradiction_resolution": "These two sources disagree and show different numbers",
        "ocr_scan_recovery": "The scan is blurry; read the image",
        "high_degree_entity_aggregation": "Show every document mentioning this component",
        "multi_question_research": "Find part 120-41824-003 and determine whether it is approved",
        "clarification_no_evidence": "Can you help me with this?",
    }
    for expected, query in examples.items():
        atoms = mod.extract_query_atoms(query)
        plan = mod.plan_route(atoms)
        assert plan.primary_route == expected, (query, plan.primary_route, atoms)


def test_ata_prefix_never_becomes_part_prefix():
    mod = load()
    atoms = mod.extract_query_atoms("I have a part I want to find, ATA number starts with 25")
    assert atoms.ata_prefix == "25"
    assert atoms.part_prefix is None
    assert mod.plan_route(atoms).primary_route == "ata_system_discovery"


def test_partial_part_prefix_still_routes_guided():
    mod = load()
    atoms = mod.extract_query_atoms("The P/N starts with MS49 and I cannot remember more")
    assert atoms.ata_prefix is None
    assert atoms.part_prefix == "MS49"
    assert mod.plan_route(atoms).primary_route == "guided_part_discovery"


def test_garbage_navigation_candidates_are_rejected():
    mod = load()
    for value in ("25-Numerical", "25-LIST", "25-Vendors", "25-LEP", "25-21-00-112"):
        assert mod.is_garbage_candidate(value) is True
    assert mod.is_garbage_candidate("120-41824-003") is False
    assert mod.is_garbage_candidate("MS4956") is False


def test_contains_fidelity_only_allows_matching_candidates():
    mod = load()
    atoms = mod.extract_query_atoms("The P/N contains 41824")
    assert mod.candidate_matches_atoms("120-41824-003", atoms) is True
    assert mod.candidate_matches_atoms("120-99999-001", atoms) is False


class FakeRuntimeMixin:
    def call_unified(self, query: str, *, top_k: int = 8):
        if "diagram" in query.lower():
            return 200, {
                "quality_status": "PASS",
                "route": "gemma_confirmed_image_visual",
                "citations": [{
                    "page_id": "t_p_120_1176_p000202",
                    "subject": "seat assembly diagram",
                    "part_numbers": ["120-41824-003"],
                    "figure_refs": ["figure 69"],
                }],
                "qdrant_guidance": {"hits": []},
            }
        return 200, {
            "quality_status": "PASS",
            "route": "normal_ask",
            "content": "No direct evidence.",
            "citation_count": 0,
            "citations": [],
            "qdrant_guidance": {"hits": []},
        }

    def call_guided(self, query: str, *, top_k: int = 8):
        return 200, {
            "quality_status": "PASS",
            "candidate_routes": [
                {
                    "candidate_part_number": "120-41824-003",
                    "ata": "25-21-00",
                    "document": "EMB CMM ATA 25-21-00 REV.4",
                    "nomenclature": "RING, LOCKING",
                    "page_id": "t_p_120_1176_p000202",
                    "route_group": "contains_digits",
                },
                {
                    "candidate_part_number": "120-99999-001",
                    "ata": "25-21-00",
                    "document": "EMB CMM ATA 25-21-00 REV.4",
                    "page_id": "t_p_120_1176_p000203",
                    "route_group": "loose_contains",
                },
            ],
        }


def make_runtime(mod):
    class FakeRuntime(FakeRuntimeMixin, mod.CognitiveRuntime):
        pass

    return FakeRuntime(
        unified_base_url="http://127.0.0.1:8117",
        guided_base_url="http://127.0.0.1:8116",
        unified_api_key="key",
        api_key="public",
        timeout=5,
        max_request_bytes=100000,
        max_concurrency=1,
        queue_timeout=5,
    )


def test_exact_identifier_cross_route_recovery_uses_matching_candidate_only():
    mod = load()
    runtime = make_runtime(mod)
    result = runtime.process({"query": "Find part 120-41824-003"})
    assert result["route"] == "exact_identifier_lookup"
    candidates = result["evidence_envelope"]["candidate_evidence"]
    assert [row["candidate_value"] for row in candidates] == ["120-41824-003"]
    assert "candidate evidence" in result["content"].lower()
    assert result["self_rag_critic"]["quality_status"] == "PASS"


def test_safe_general_chat_is_deterministic_and_contains_no_fake_source_claim():
    mod = load()
    runtime = make_runtime(mod)
    result = runtime.process({"query": "hello"})
    assert result["route"] == "safe_general_chat"
    assert result["citation_count"] == 0
    assert "source-truth evidence for this query" not in result["content"]
    assert "Hello" in result["content"]


def test_metadata_conflict_is_not_promoted():
    mod = load()
    conflict = mod.metadata_conflict({
        "candidate_part_number": "120-41824-297",
        "ata": "21-00-85",
        "document": "EMB CMM ATA 25-21-00 REV.4",
    })
    assert conflict
    assert conflict["type"] == "ata_document_mismatch"
