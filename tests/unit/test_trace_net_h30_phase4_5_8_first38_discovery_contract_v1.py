from __future__ import annotations
import importlib.util, sys
from pathlib import Path


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_visible_candidate_parser_ignores_nomenclature_tokens():
    guard = load("p458_guard", "tiff/trace_net_answer_quality_guard_v1.py")
    answer = (
        "TRACE-Net found candidate evidence, not a final identification:\n"
        "- MS4956 — ATA 25-21-00; WS4956 1\n"
    )
    failures = guard.evaluate_answer_quality(
        query="The P/N starts with MS49 and I cannot remember more",
        answer=answer,
        trace={"route": "guided_part_discovery", "follow_up_questions": []},
    )
    assert not any(x.startswith("strict_prefix_candidate_mismatch:") for x in failures), failures
    bad = answer.replace("- MS4956", "- WS4956")
    failures = guard.evaluate_answer_quality(
        query="The P/N starts with MS49 and I cannot remember more",
        answer=bad,
        trace={"route": "guided_part_discovery", "follow_up_questions": []},
    )
    assert "strict_prefix_candidate_mismatch:WS4956" in failures


def test_partial_item_number_overrides_table_but_real_item_does_not():
    router = load("p458_router_item", "scripts/operations/s6_retrieval/serve_trace_net_cognitive_router_v1.py")
    for query, mode, value in (
        ("The item number begins with PE13", "prefix", "PE13"),
        ("All I know is the item number contains 48024", "contains", "48024"),
    ):
        atoms = router.extract_query_atoms(query)
        plan = router.plan_route(atoms)
        assert atoms.identifier_mode == mode
        assert atoms.normalized_identifier == value
        assert plan.primary_route == "guided_part_discovery"
    atoms = router.extract_query_atoms("Search the IPL table for item 14")
    assert atoms.identifier_mode == "none"
    assert router.plan_route(atoms).primary_route == "exact_table_ipl_lookup"


def test_nas_and_descriptive_vocabulary_routes():
    router = load("p458_router_vocab", "scripts/operations/s6_retrieval/serve_trace_net_cognitive_router_v1.py")
    atoms = router.extract_query_atoms("The part starts with NAS and I am not sure of the rest")
    assert atoms.identifier_mode == "prefix" and atoms.part_prefix == "NAS"
    assert router.plan_route(atoms).primary_route == "guided_part_discovery"
    for query in (
        "I would like a part that is a ashtray", "I am looking for a bearing",
        "I would like a part that is a support rail", "Find me a buckle part",
        "I am looking for a actuator", "I would like a part that is a switch",
        "Find me a valve part", "I am looking for a hose", "Find me a clamp part",
    ):
        assert router.plan_route(router.extract_query_atoms(query)).primary_route == "nomenclature_function_search", query


def test_discovery_routes_have_five_complete_followups():
    router = load("p458_router_followups", "scripts/operations/s6_retrieval/serve_trace_net_cognitive_router_v1.py")
    cases = (
        ("I only remember the part contains 824", "guided_part_discovery"),
        ("I am looking for a hinge", "nomenclature_function_search"),
        ("Find pages about a bearing", "semantic_discovery"),
        ("Can you help me with this technical part?", "clarification_no_evidence"),
    )
    for query, route in cases:
        questions = router.build_follow_up_questions(router.extract_query_atoms(query), route)
        blob = " ".join(questions).lower()
        assert len(questions) == 5
        assert "part number" in blob and "manufacturer" in blob and "look like" in blob


def _response(route, tunnels, used, answer, followups, planner=None):
    trace = {
        "route": route,
        "route_plan": {"primary_route": route, "retrieval_tunnels": tunnels},
        "evidence_envelope": {"retrieval_tunnels_used": used, "direct_evidence": [], "candidate_evidence": [], "semantic_guidance": [{"page_id": "p1"}]},
        "follow_up_questions": followups,
        "writer_mode": "deterministic_fail_closed", "gemma_status": "SKIPPED_NO_DIRECT_EVIDENCE",
        "citation_count": 0, "answer_permission": False, "final_answer_allowed": False,
        "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False,
    }
    if planner:
        trace["planner_execution"] = planner
        trace["planner_plan_adopted"] = True
        trace["planner_route_applied"] = True
    return {"choices": [{"message": {"content": answer}}], "trace_net": trace}


def test_benchmark_physical_topic_planner_adoption_and_specialized_labels():
    bench = load("p458_bench", "scripts/benchmark/validation/run_trace_net_full_user_query_gemma_benchmark_v1.py")
    qs = [
        "Do you remember any part number characters, digits, separators, or stamped markings?",
        "Do you know the manufacturer, vendor, or supplier?",
        "What function does the bearing perform, and what assembly or installation location is it associated with?",
        "What does the part look like, including its shape, color, size, markings, and nearby hardware?",
        "Do you know the ATA chapter, aircraft system, figure, diagram, IPL item, table, manual, or page?",
    ]
    assert bench.topic_visible("physical_description", qs)
    tunnels = ["qdrant_guidance", "v2_v3_summary_guidance", "graph_leiden_guidance", "normal_source_resolution"]
    answer = "Semantic guidance only; no source claim.\n\nHelpful follow-up questions:\n" + "\n".join(f"- {q}" for q in qs)
    planner = {
        "quality_status": "PASS", "planner_plan_adopted": True, "planner_route_applied": True,
        "retrieval_influenced": True, "selected_route": "semantic_discovery",
        "effective_route": "semantic_discovery", "effective_tunnels": tunnels,
        "executor_owns_tunnel_selection": True, "planner_validation": {"accepted": True},
    }
    row = {"question_id": "x", "category": "descriptive_part_nomenclature", "query": "I am looking for a bearing", "min_follow_up_questions": 4, "required_follow_up_topics": ["part_number", "manufacturer"]}
    result = bench.evaluate(row, status_code=200, response=_response("semantic_discovery", tunnels, ["qdrant_guidance"], answer, qs, planner), latency_ms=1, transport_error="")
    assert result["quality_status"] == "PASS", result["failures"]
    table_tunnels = ["normal_source_truth", "table_rows_cells", "ocr_fallback", "figure_item_linkage"]
    row = {"question_id": "t", "category": "table", "query": "Search the IPL table for item 14", "min_follow_up_questions": 0}
    result = bench.evaluate(row, status_code=200, response=_response("exact_table_ipl_lookup", table_tunnels, ["exact_table_ipl_lookup_specialized_1"], "Semantic guidance only; no claim.", []), latency_ms=1, transport_error="")
    assert result["quality_status"] == "PASS", result["failures"]


def test_native_wrapper_appends_nomenclature_followups():
    cold = load("p458_cold", "src/trace_net/serving/adapters/trace_net_h30_cold_start_streaming_v1.py")
    writer = load("p458_writer", "scripts/operations/writing/serve_trace_net_full_gemma_cognitive_v1.py")
    qs = [f"Question {i} with part number manufacturer look like detail?" for i in range(5)]
    upstream = {"route": "nomenclature_function_search", "content": "Candidate guidance only.", "follow_up_questions": qs, "evidence_envelope": {"direct_evidence": [], "candidate_evidence": []}, "answer_permission": False, "final_answer_allowed": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False}
    class Runtime:
        def health(self): return {"quality_status": "PASS"}
    module = {
        "Runtime": Runtime, "make_handler": lambda r: object,
        "http_json": lambda *a, **k: (200, dict(upstream)), "direct_evidence": lambda r: [],
        "validate_answer": lambda *a, **k: {"quality_status": "PASS", "failures": [], "accepted": True},
        "build_prompt": lambda *a, **k: "", "extract_latest_user": lambda p: "hinge",
        "error_payload": lambda *a, **k: {}, "openai_response": lambda *a, **k: {},
        "MODEL_ID": "m", "MODULE": "m", "clean_engineer_text": lambda x: x,
        "apply_engineer_answer_contract": lambda r: dict(r), "append_follow_up_questions": writer.append_follow_up_questions,
    }
    cold.install_gemma_latency_support(module)
    r = Runtime(); r.cognitive_base_url="x"; r.cognitive_api_key="x"; r.gemma_base_url="x"; r.gemma_model="g"; r.timeout=1
    result = r.process({"messages": [{"role": "user", "content": "hinge"}]})
    assert result["follow_up_questions_visible_count"] == 5
    assert result["content"].count("Helpful follow-up questions:") == 1
