from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def candidate_response(*, include_followups: bool = True):
    questions = [
        "What additional part number characters do you remember after the prefix 123?",
        "Do you know the manufacturer, vendor, or supplier?",
        "What component, function, or assembly is the part associated with?",
        "Do you know the ATA chapter or aircraft system?",
    ] if include_followups else []
    answer = (
        "TRACE-Net found candidate evidence, not a final identification:\n"
        "- 1234567 — ATA 25-21-00; EMB CMM ATA 25-21-00 REV.4; PER NUMBER T\n"
        "Candidate, visual, graph, summary, and semantic results are guidance only "
        "until resolved to direct source evidence."
    )
    if questions:
        answer += "\n\nHelpful follow-up questions:\n" + "\n".join(
            f"- {question}" for question in questions
        )
    return {
        "choices": [{"message": {"content": answer}}],
        "trace_net": {
            "route": "guided_part_discovery",
            "route_plan": {
                "primary_route": "guided_part_discovery",
                "retrieval_tunnels": [
                    "guided_candidate_discovery",
                    "normal_source_resolution",
                    "phase4_3_candidate_source_resolution",
                    "qdrant_guidance",
                ],
            },
            "evidence_envelope": {
                "retrieval_tunnels_used": ["guided_candidate_discovery"],
                "direct_evidence": [],
                "candidate_evidence": [{"candidate_value": "1234567"}],
            },
            "follow_up_questions": questions,
            "clarification_required": True,
            "clarification_recommended": True,
            "writer_mode": "deterministic_fail_closed",
            "gemma_status": "SKIPPED_NO_DIRECT_EVIDENCE",
            "answer_model": "gemma4:26b",
            "citation_count": 0,
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        },
    }


def record():
    return {
        "question_id": "q001",
        "category": "partial_part_prefix",
        "query": "I only know the part starts with 123",
        "expected_execution_route": "guided_discovery",
        "expected_tunnel": "guided_candidate_discovery",
        "min_follow_up_questions": 4,
        "required_follow_up_topics": ["part_number", "manufacturer"],
        "retrieval_expectation": "not_checked",
    }


def test_router_builds_bounded_guided_followups():
    router = load(
        "phase455_router",
        "scripts/operations/s6_retrieval/serve_trace_net_cognitive_router_v1.py",
    )
    atoms = router.extract_query_atoms(record()["query"])
    questions = router.build_follow_up_questions(
        atoms,
        "guided_part_discovery",
    )
    assert len(questions) >= 4
    blob = " ".join(questions).lower()
    assert "part number" in blob
    assert "manufacturer" in blob or "vendor" in blob
    assert "component" in blob or "function" in blob
    assert "ata" in blob or "figure" in blob


def test_writer_appends_followups_once():
    writer = load(
        "phase455_writer",
        "scripts/operations/writing/serve_trace_net_full_gemma_cognitive_v1.py",
    )
    questions = [
        "What additional part number characters do you remember?",
        "Do you know the manufacturer or vendor?",
    ]
    first = writer.append_follow_up_questions(
        "Candidate evidence only.",
        questions,
        should_append=True,
    )
    second = writer.append_follow_up_questions(
        first,
        questions,
        should_append=True,
    )
    assert first == second
    assert first.count("Helpful follow-up questions:") == 1
    assert first.count(questions[0]) == 1
    assert first.count(questions[1]) == 1


def test_revision_metadata_is_not_a_noise_candidate():
    guard = load(
        "phase455_guard",
        "tiff/trace_net_answer_quality_guard_v1.py",
    )
    failures = guard.evaluate_answer_quality(
        query=record()["query"],
        answer=(
            "TRACE-Net found candidate evidence, not a final identification: "
            "1234567 — EMB CMM ATA 25-21-00 REV.4"
        ),
        trace={"route": "guided_part_discovery", "follow_up_questions": []},
    )
    assert "user_visible_noise_candidates:REV.4" not in failures
    assert not any(item.startswith("strict_prefix_candidate_mismatch") for item in failures)


def test_mature_candidate_response_passes_legacy_bank_adapter():
    benchmark = load(
        "phase455_benchmark",
        "scripts/benchmark/validation/run_trace_net_full_user_query_gemma_benchmark_v1.py",
    )
    result = benchmark.evaluate(
        record(),
        status_code=200,
        response=candidate_response(),
        latency_ms=1000,
        transport_error="",
    )
    assert result["quality_status"] == "PASS", result["failures"]
    assert result["contract"] == "h30_mature_cognitive"
    assert result["expected_route"] == "guided_part_discovery"
    assert result["writer_skipped_expected"] is True


def test_mature_candidate_response_still_fails_missing_followups():
    benchmark = load(
        "phase455_benchmark_missing_followups",
        "scripts/benchmark/validation/run_trace_net_full_user_query_gemma_benchmark_v1.py",
    )
    result = benchmark.evaluate(
        record(),
        status_code=200,
        response=candidate_response(include_followups=False),
        latency_ms=1000,
        transport_error="",
    )
    assert result["quality_status"] == "FAIL"
    assert "follow_up_count:0<4" in result["failures"]


def test_mature_direct_evidence_requires_validated_writer():
    benchmark = load(
        "phase455_benchmark_direct",
        "scripts/benchmark/validation/run_trace_net_full_user_query_gemma_benchmark_v1.py",
    )
    row = {
        "question_id": "qx",
        "category": "exact",
        "query": "Find part 120-41824-003",
        "expected_execution_route": "normal_ask",
        "expected_tunnel": "normal_source_truth",
        "min_follow_up_questions": 0,
    }
    response = {
        "choices": [{
            "message": {
                "content": "Part 120-41824-003 appears in the cited source field [1]."
            }
        }],
        "trace_net": {
            "route": "exact_identifier_lookup",
            "route_plan": {
                "retrieval_tunnels": [
                    "normal_source_truth",
                    "guided_exact_candidate",
                    "confirmed_visual",
                    "phase4_3_exact_source_resolution",
                    "qdrant_guidance",
                ]
            },
            "evidence_envelope": {
                "retrieval_tunnels_used": ["normal_source_truth"],
                "direct_evidence": [{
                    "page_id": "t_p_120_1176_p000202",
                    "field_name": "part_number",
                    "normalized_value": "120-41824-003",
                }],
                "candidate_evidence": [],
            },
            "follow_up_questions": [],
            "writer_mode": "gemma_validated_direct_evidence",
            "gemma_status": "LLM_CALL_SUCCEEDED_AND_VALIDATED",
            "answer_model": "gemma4:26b",
            "citation_count": 1,
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        },
    }
    result = benchmark.evaluate(
        row,
        status_code=200,
        response=response,
        latency_ms=1000,
        transport_error="",
    )
    assert result["quality_status"] == "PASS", result["failures"]
    assert result["writer_successful"] is True


def test_legacy_canary_contract_remains_supported():
    benchmark = load(
        "phase455_benchmark_legacy",
        "scripts/benchmark/validation/run_trace_net_full_user_query_gemma_benchmark_v1.py",
    )
    row = {
        "question_id": "legacy",
        "category": "legacy",
        "query": "I would like a part that is a hinge",
        "expected_execution_route": "guided_discovery",
        "expected_tunnel": "descriptive_part_discovery",
        "min_follow_up_questions": 2,
        "retrieval_expectation": "not_checked",
    }
    questions = [
        "Do you remember any part-number characters?",
        "Which company made it?",
    ]
    response = {
        "choices": [{
            "message": {
                "content": (
                    "I can help narrow that down. "
                    + " ".join(questions)
                )
            }
        }],
        "trace_net": {
            "route": "guided_discovery",
            "retrieval_tunnel": "descriptive_part_discovery",
            "follow_up_questions": questions,
            "response_composer_called": True,
            "response_composer_status": "LLM_CALL_SUCCEEDED",
            "response_composer_model": "gemma4:26b",
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "citation_count": 0,
        },
    }
    result = benchmark.evaluate(
        row,
        status_code=200,
        response=response,
        latency_ms=1000,
        transport_error="",
    )
    assert result["quality_status"] == "PASS", result["failures"]
