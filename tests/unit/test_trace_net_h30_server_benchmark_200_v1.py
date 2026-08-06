from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO / "scripts/benchmark/validation/run_trace_net_h30_server_benchmark_200_v1.py"
LAUNCHER_PATH = REPO / "scripts/benchmark/operations/launch_trace_net_h30_server_benchmark_200_v1.sh"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def safe_result(route: str, *, candidates=None, direct=None, authority=None, tunnels=None):
    return {
        "route": route,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "writer_mode": "deterministic_fail_closed" if not direct else "gemma_validated_direct_evidence",
        "post_answer_validation": {"accepted": True, "quality_status": "PASS", "failures": []},
        "evidence_envelope": {
            "candidate_evidence": candidates or [],
            "direct_evidence": direct or [],
            "authority_evidence": authority or [],
            "visual_guidance": [],
            "semantic_guidance": [],
            "retrieval_tunnels_used": tunnels or ["test_tunnel"],
        },
    }


def test_embedded_question_bank_has_exactly_200_unique_questions_and_all_routes():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_embedded_bank_test")
    bank = runner.load_question_bank("", REPO)
    questions = bank["questions"]
    assert bank["question_count"] == 200
    assert len(questions) == 200
    assert len({row["question_id"] for row in questions}) == 200
    assert [row["question_id"] for row in questions] == [f"q{index:03d}" for index in range(1, 201)]
    counts = {}
    for row in questions:
        counts[row["expected_route"]] = counts.get(row["expected_route"], 0) + 1
    assert set(counts) == set(bank["routes"])
    assert len(counts) == 19
    assert min(counts.values()) >= 10


def test_every_question_matches_the_live_h30_planner():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_planner_test")
    bank = runner.load_question_bank("", REPO)
    result = runner.preflight_question_bank(bank, REPO)
    assert result["quality_status"] == "PASS", result
    assert result["question_count"] == 200
    assert result["route_count"] == 19
    assert result["planner_mismatch_count"] == 0
    assert result["missing_routes"] == []
    assert result["routes_below_10_questions"] == []


def test_strict_alphanumeric_prefix_preservation_and_unrelated_fallback_rejection():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_prefix_test")
    good = safe_result(
        "guided_part_discovery",
        candidates=[{"candidate_value": "MS4956"}],
    )
    answer = "TRACE-Net found candidate evidence for the MS49 prefix, not a final identification."
    evaluation = runner.evaluate_answer_quality(
        "The part number starts with MS49",
        "guided_part_discovery",
        good,
        answer,
        [],
    )
    assert evaluation["passed"] is True, evaluation

    bad = safe_result(
        "guided_part_discovery",
        candidates=[{"candidate_value": "120-41824-003"}],
    )
    evaluation = runner.evaluate_answer_quality(
        "The part number starts with MS49",
        "guided_part_discovery",
        bad,
        answer,
        [],
    )
    assert evaluation["passed"] is False
    assert any(item.startswith("candidate_prefix_mismatch:") for item in evaluation["failures"])


def test_contains_and_suffix_candidate_fidelity():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_contains_suffix_test")
    contains = safe_result(
        "guided_part_discovery",
        candidates=[{"candidate_value": "120-41824-003"}],
    )
    result = runner.evaluate_answer_quality(
        "The P/N contains 41824",
        "guided_part_discovery",
        contains,
        "Candidate evidence includes 120-41824-003; this is not a final identification.",
        [],
    )
    assert result["passed"] is True, result

    suffix = safe_result(
        "guided_part_discovery",
        candidates=[{"candidate_value": "120-41824-007"}],
    )
    result = runner.evaluate_answer_quality(
        "The P/N suffix is 003",
        "guided_part_discovery",
        suffix,
        "Candidate evidence only; no final identification.",
        [],
    )
    assert "candidate_suffix_mismatch:120-41824-007" in result["failures"]


def test_navigation_and_ocr_noise_candidates_are_rejected():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_noise_test")
    result = safe_result(
        "guided_part_discovery",
        candidates=[
            {"candidate_value": "25-LIST"},
            {"candidate_value": "@@@"},
        ],
    )
    evaluation = runner.evaluate_answer_quality(
        "The P/N contains 25",
        "guided_part_discovery",
        result,
        "Candidate evidence only; not a final identification.",
        [],
    )
    assert evaluation["passed"] is False
    assert "navigation_garbage_candidate:25-LIST" in evaluation["failures"]
    assert "ocr_noise_candidate:@@@" in evaluation["failures"]


def test_follow_up_deduplication_detects_visible_duplicates_and_output_is_unique():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_followup_test")
    result = safe_result("clarification_no_evidence", tunnels=["targeted_clarification"])
    result["clarifying_questions"] = ["Which ATA chapter was involved?"]
    answer = """I need another clue.

Helpful follow-up questions:
- Which ATA chapter was involved?
- Which ATA chapter was involved?
"""
    followups = runner.extract_follow_up_questions(result, answer)
    assert followups == ["Which ATA chapter was involved?"]
    evaluation = runner.evaluate_answer_quality(
        "Can you assist me?",
        "clarification_no_evidence",
        result,
        answer,
        followups,
    )
    assert "duplicated_follow_up_questions" in evaluation["failures"]


def test_citation_alignment_requires_supported_direct_citation_ids():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_citation_test")
    direct = [{"page_id": "t_p_1", "field_name": "part_number", "normalized_value": "120-41824-003"}]
    result = safe_result("exact_identifier_lookup", direct=direct)
    good = runner.evaluate_answer_quality(
        "Find part 120-41824-003",
        "exact_identifier_lookup",
        result,
        "Part 120-41824-003 is listed in the direct record [1].",
        [],
    )
    assert good["passed"] is True, good

    bad = runner.evaluate_answer_quality(
        "Find part 120-41824-003",
        "exact_identifier_lookup",
        result,
        "Part 120-41824-003 is listed in the direct record [2].",
        [],
    )
    assert "citation_id_out_of_range" in bad["failures"]


def test_requested_field_and_route_tunnel_preservation_are_graded():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_field_tunnel_test")
    result = safe_result("exact_table_ipl_lookup", tunnels=[])
    result["evidence_envelope"]["retrieval_tunnels_used"] = []
    evaluation = runner.evaluate_answer_quality(
        "Search the IPL table for item 14",
        "exact_table_ipl_lookup",
        result,
        "TRACE-Net did not find direct citation-ready source evidence.",
        [],
    )
    assert "requested_field_not_addressed" in evaluation["failures"]
    assert "technical_route_missing_retrieval_tunnels" in evaluation["failures"]


def test_authority_claim_without_explicit_authority_fails_closed():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_authority_test")
    result = safe_result("authority_eligibility_verification")
    unsafe = runner.evaluate_answer_quality(
        "Is part 120-41824-003 an approved replacement?",
        "authority_eligibility_verification",
        result,
        "Part 120-41824-003 is an approved replacement.",
        [],
    )
    assert "safety_sensitive_claim_without_explicit_authority" in unsafe["failures"]

    safe = runner.evaluate_answer_quality(
        "Is part 120-41824-003 an approved replacement?",
        "authority_eligibility_verification",
        result,
        "TRACE-Net found no explicit approval authority for part 120-41824-003; approval is not established.",
        [],
    )
    assert safe["passed"] is True, safe


def test_all_safety_flags_must_remain_exactly_false():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_flags_test")
    result = safe_result("exact_identifier_lookup")
    result["can_prove_claims"] = None
    evaluation = runner.evaluate_answer_quality(
        "Find part 120-41824-003",
        "exact_identifier_lookup",
        result,
        "TRACE-Net did not find direct citation-ready proof for part 120-41824-003.",
        [],
    )
    assert "safety_flag_not_false:can_prove_claims" in evaluation["failures"]


def test_candidate_only_answer_cannot_use_gemma_writer():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_candidate_gemma_test")
    result = safe_result(
        "guided_part_discovery",
        candidates=[{"candidate_value": "120-41824-003"}],
    )
    result["writer_mode"] = "gemma_validated_direct_evidence"
    evaluation = runner.evaluate_safety(result, "Candidate evidence only.")
    assert evaluation["passed"] is False
    assert "gemma_used_without_direct_evidence" in evaluation["failures"]


def test_server_launcher_payload_is_git_bash_compatible_and_lf_only():
    raw = LAUNCHER_PATH.read_bytes()
    assert raw.startswith(b"#!/usr/bin/env bash\nset -euo pipefail\n")
    assert b"\x00" not in raw
    assert b"\r\n" not in raw
    text = raw.decode("utf-8")
    assert "run_trace_net_h30_server_benchmark_200_v1.py" in text
    assert "GEMMA_START/DONE" in text
    assert "TRACE_NET_BENCHMARK_GEMMA_MODEL" in text
    assert "gemma_required_for_every_question=true" in text



def test_gemma_every_question_parser_accepts_strict_json_and_deduplicates_followups():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_gemma_parser_test")
    parsed = runner.parse_gemma_json('{\"answer\":\"Hello.\",\"follow_up_questions\":[\"What part?\",\"What part?\"],\"review\":{\"safety_boundary\":\"PASS\"}}')
    assert parsed["answer"] == "Hello."
    result = runner.call_gemma_every_question
    assert callable(result)


def test_gemma_every_question_prompt_preserves_fail_closed_contract():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_gemma_prompt_test")
    result = safe_result("guided_part_discovery", candidates=[{"candidate_value": "MS4956"}])
    prompt = runner.gemma_render_prompt(
        "The part number starts with MS49",
        "guided_part_discovery",
        result,
        "Candidate evidence only; this is not a final identification.",
    )
    assert "required for every benchmark question" in prompt
    assert "Candidate, visual, semantic, graph, and summary material is guidance only" in prompt
    assert "Return one JSON object only" in prompt


def test_gemma_every_question_rejects_unsupported_identifier():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_gemma_identifier_test")
    result = safe_result("guided_part_discovery", candidates=[{"candidate_value": "MS4956"}])
    gemma = {
        "http_status_code": 200,
        "model_requested": "gemma4:26b",
        "model_returned": "gemma4:26b",
        "answer": "The candidate is 120-99999-001.",
        "follow_up_questions": [],
    }
    evaluation = runner.evaluate_gemma_every_question(
        "The part number starts with MS49",
        "guided_part_discovery",
        result,
        "Candidate evidence only; this is not a final identification.",
        gemma,
    )
    assert evaluation["passed"] is False
    assert any(value.startswith("gemma_unsupported_identifier:") for value in evaluation["failures"])


def test_gemma_every_question_requires_boundary_for_candidate_only_technical_answer():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_gemma_boundary_test")
    result = safe_result("guided_part_discovery", candidates=[{"candidate_value": "MS4956"}])
    gemma = {
        "http_status_code": 200,
        "model_requested": "gemma4:26b",
        "model_returned": "gemma4:26b",
        "answer": "MS4956 is the identified part.",
        "follow_up_questions": [],
    }
    evaluation = runner.evaluate_gemma_every_question(
        "The part number starts with MS49",
        "guided_part_discovery",
        result,
        "Candidate evidence only; this is not a final identification.",
        gemma,
    )
    assert "gemma_missing_fail_closed_boundary_without_direct_evidence" in evaluation["failures"]


def test_gemma_every_question_accepts_safe_general_chat_answer():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_gemma_chat_test")
    result = safe_result("safe_general_chat", tunnels=["restricted_conversation_template"])
    gemma = {
        "http_status_code": 200,
        "model_requested": "gemma4:26b",
        "model_returned": "gemma4:26b",
        "answer": "Hello! I can help search TRACE-Net manuals.",
        "follow_up_questions": [],
    }
    evaluation = runner.evaluate_gemma_every_question(
        "hello", "safe_general_chat", result, "Hello!", gemma
    )
    assert evaluation["passed"] is True, evaluation


def test_call_gemma_every_question_invokes_gemma4_and_deduplicates_followups():
    runner = load_module(RUNNER_PATH, "trace_net_benchmark_200_gemma_call_test")
    captured = {}

    def fake_post(url, api_key, payload, timeout):
        captured["url"] = url
        captured["api_key"] = api_key
        captured["payload"] = payload
        captured["timeout"] = timeout
        return 200, {
            "model": "gemma4:26b",
            "message": {
                "content": json.dumps({
                    "answer": "Hello! I can help search TRACE-Net manuals.",
                    "follow_up_questions": ["What part?", "What part?"],
                    "review": {"safety_boundary": "PASS"},
                })
            },
        }

    runner.post_json = fake_post
    result = runner.call_gemma_every_question(
        gemma_url="http://127.0.0.1:11434/api/chat",
        gemma_model="gemma4:26b",
        gemma_timeout=1200,
        question="hello",
        expected_route="safe_general_chat",
        result=safe_result("safe_general_chat", tunnels=["restricted_conversation_template"]),
        safe_answer="Hello!",
    )
    assert captured["url"].endswith("/api/chat")
    assert captured["api_key"] == ""
    assert captured["payload"]["model"] == "gemma4:26b"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["format"] == "json"
    assert result["model_returned"] == "gemma4:26b"
    assert result["answer"].startswith("Hello!")
    assert result["follow_up_questions"] == ["What part?"]
