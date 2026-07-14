from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
BOUNDARY_PATH = REPO / "scripts" / "trace_net_h30_answer_boundary_v1.py"
RUNNER_PATH = REPO / "scripts" / "run_trace_net_h30_server_benchmark_200_v1.py"
ROUTER_PATH = REPO / "scripts" / "serve_trace_net_cognitive_router_v1.py"
LAUNCHER_PATH = REPO / "scripts" / "launch_trace_net_h30_server_benchmark_200_v1.sh"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def result_for(route: str, query_atoms: dict, *, contradictions=None):
    return {
        "route": route,
        "query_atoms": query_atoms,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "writer_mode": "deterministic_fail_closed",
        "post_answer_validation": {"accepted": True, "quality_status": "PASS", "failures": []},
        "evidence_envelope": {
            "direct_evidence": [],
            "candidate_evidence": [],
            "visual_guidance": [],
            "semantic_guidance": [],
            "authority_evidence": [],
            "contradictions": contradictions or [],
            "uncertainties": [],
            "retrieval_tunnels_used": ["test_tunnel"],
        },
    }


def test_canonical_boundaries_fix_every_observed_no_evidence_route_family():
    boundary = load(BOUNDARY_PATH, "h30_boundary_all_routes")
    runner = load(RUNNER_PATH, "h30_runner_all_routes")

    cases = [
        ("exact_identifier_lookup", "Find part 120-41824-003", {"exact_part_numbers": ["120-41824-003"]}),
        ("guided_part_discovery", "The part number starts with MS49", {"part_prefix": "MS49"}),
        ("ata_system_discovery", "Search ATA 25", {"ata_prefix": "25"}),
        ("nomenclature_function_search", "Find the locking ring near the seat", {"nomenclature_terms": ["locking ring"]}),
        ("exact_table_ipl_lookup", "Search the IPL table for item 14", {"items": ["14"]}),
        ("visual_figure_callout_lookup", "Find figure 2 sheet 1", {"figures": ["figure 2 sheet 1"]}),
        ("procedure_task_lookup", "What are the installation steps?", {}),
        ("warning_caution_note_lookup", "What warning applies to this task?", {}),
        ("authority_eligibility_verification", "Is part 120-41824-003 an approved replacement?", {"exact_part_numbers": ["120-41824-003"]}),
        ("document_page_navigation", "Open page t_p_120_1176_p000084", {"page_ids": ["t_p_120_1176_p000084"]}),
        ("graph_relationship_reasoning", "What assembly contains this part?", {}),
        ("semantic_discovery", "Find pages about corrosion prevention", {}),
        ("cross_source_comparison", "Compare both manuals", {}),
        ("contradiction_resolution", "Resolve the conflict between revisions", {}),
        ("ocr_scan_recovery", "The scan is blurry; read the image", {}),
        ("high_degree_entity_aggregation", "Show every document mentioning this component", {}),
        ("multi_question_research", "Find part 120-41824-003 and determine whether it is approved", {"exact_part_numbers": ["120-41824-003"]}),
    ]

    for route, question, atoms in cases:
        result = result_for(route, atoms)
        answer = boundary.enforce_h30_answer_boundaries(
            route=route,
            query=question,
            query_atoms=atoms,
            evidence_envelope=result["evidence_envelope"],
            answer="TRACE-Net did not recover a stronger answer.",
        )
        evaluation = runner.evaluate_answer_quality(question, route, result, answer, [])
        assert evaluation["passed"] is True, (route, answer, evaluation)
        assert boundary.PROOF_BOUNDARY in answer


def test_authority_boundary_is_explicitly_negative_and_preserves_identifier():
    boundary = load(BOUNDARY_PATH, "h30_boundary_authority")
    atoms = {"exact_part_numbers": ["120-41824-003"]}
    result = result_for("authority_eligibility_verification", atoms)
    answer = boundary.enforce_h30_answer_boundaries(
        route="authority_eligibility_verification",
        query="Is part 120-41824-003 interchangeable and approved for installation?",
        query_atoms=atoms,
        evidence_envelope=result["evidence_envelope"],
        answer="TRACE-Net could not resolve the request.",
    )
    assert "120-41824-003" in answer
    assert "No explicit authority was found" in answer
    assert "None of those claims is confirmed" in answer


def test_rejected_raw_gemma_output_is_transparently_replaced_by_safe_draft():
    boundary = load(BOUNDARY_PATH, "h30_boundary_fallback")
    runner = load(RUNNER_PATH, "h30_runner_fallback")
    atoms = {"page_ids": ["t_p_120_1176_p000084"]}
    result = result_for("document_page_navigation", atoms)
    safe_answer = boundary.enforce_h30_answer_boundaries(
        route="document_page_navigation",
        query="Open page t_p_120_1176_p000084",
        query_atoms=atoms,
        evidence_envelope=result["evidence_envelope"],
        answer="TRACE-Net did not locate a citation-ready page record.",
    )
    raw = {
        "http_status_code": 200,
        "model_requested": "gemma4:26b",
        "model_returned": "gemma4:26b",
        "answer": "Use page t_p_12_1176_p000321; it is approved for installation.",
        "follow_up_questions": [],
        "review": {},
    }
    raw_eval = runner.evaluate_gemma_every_question(
        "Open page t_p_120_1176_p000084",
        "document_page_navigation",
        result,
        safe_answer,
        raw,
    )
    assert raw_eval["passed"] is False

    repaired = boundary.apply_bounded_gemma_fallback(
        raw,
        safe_answer=safe_answer,
        failures=raw_eval["failures"],
        follow_up_questions=[],
    )
    final_eval = runner.evaluate_gemma_every_question(
        "Open page t_p_120_1176_p000084",
        "document_page_navigation",
        result,
        safe_answer,
        repaired,
    )
    assert final_eval["passed"] is True, final_eval
    assert repaired["repair_applied"] is True
    assert repaired["raw_model_answer"] == raw["answer"]
    assert repaired["answer"] == safe_answer


def test_empty_raw_gemma_answer_uses_bounded_fallback_without_hiding_raw_failure():
    boundary = load(BOUNDARY_PATH, "h30_boundary_empty")
    raw = {"answer": "", "follow_up_questions": [], "review": {}}
    repaired = boundary.apply_bounded_gemma_fallback(
        raw,
        safe_answer="No direct citation-ready source evidence was found.",
        failures=["gemma_empty_answer"],
        follow_up_questions=[],
    )
    assert repaired["raw_model_answer"] == ""
    assert repaired["answer"].startswith("No direct")
    assert repaired["repair_reasons"] == ["gemma_empty_answer"]


def test_general_chat_and_clarification_are_not_overwritten():
    boundary = load(BOUNDARY_PATH, "h30_boundary_nontechnical")
    for route, answer in (
        ("safe_general_chat", "Hello!"),
        ("clarification_no_evidence", "Please provide one technical clue."),
    ):
        assert boundary.enforce_h30_answer_boundaries(
            route=route,
            query="hello",
            query_atoms={},
            evidence_envelope={},
            answer=answer,
        ) == answer


def test_router_benchmark_and_launcher_are_wired_to_failure_repair_contract():
    router_text = ROUTER_PATH.read_text(encoding="utf-8")
    runner_text = RUNNER_PATH.read_text(encoding="utf-8")
    launcher_text = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "enforce_h30_answer_boundaries" in router_text
    assert "apply_bounded_gemma_fallback" in runner_text
    assert "benchmark_gemma_raw_pass" in runner_text
    assert "cognitive_benchmark_200_failure_repair_v1" in launcher_text
    assert "test_trace_net_h30_benchmark_failure_repair_v1.py" in launcher_text


def test_all_200_embedded_questions_pass_semantic_checks_with_canonical_no_evidence_boundaries():
    boundary = load(BOUNDARY_PATH, "h30_boundary_all_200")
    runner = load(RUNNER_PATH, "h30_runner_all_200")
    router = load(ROUTER_PATH, "h30_router_all_200")
    bank = runner.load_question_bank("", REPO)
    failures = []

    for row in bank["questions"]:
        question = row["question"]
        route = row["expected_route"]
        atoms = router.extract_query_atoms(question)
        atom_map = vars(atoms)
        result = result_for(route, atom_map)

        if route == "safe_general_chat":
            base_answer = "Hello! I can help search TRACE-Net manuals."
        elif route == "clarification_no_evidence":
            base_answer = (
                "I need one technical clue such as a part, ATA chapter, manufacturer, "
                "figure, table, page, or component description."
            )
        else:
            base_answer = "TRACE-Net did not recover a stronger source-backed answer."

        answer = boundary.enforce_h30_answer_boundaries(
            route=route,
            query=question,
            query_atoms=atom_map,
            evidence_envelope=result["evidence_envelope"],
            answer=base_answer,
        )
        evaluation = runner.evaluate_answer_quality(question, route, result, answer, [])
        if not evaluation["passed"]:
            failures.append((row["question_id"], route, evaluation["failures"], answer))

    assert failures == []
