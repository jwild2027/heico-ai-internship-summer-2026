from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_trace_net_fixed50_trace_server_gemma_engram_progress_v1.py"
FIXTURE = ROOT / "tests" / "fixtures" / "trace_net_fixed50_questions_v1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("fixed50_runner", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fixed50_fixture_has_exactly_50_ordered_questions():
    mod = load_module()
    questions = mod.load_questions(FIXTURE)
    assert len(questions) == 50
    assert questions[0]["question_id"] == "q01"
    assert questions[-1]["question_id"] == "q50"
    assert questions[0]["question"] == "What does figure 69 show?"


def test_prompt_marks_engram_as_guidance_not_source_proof():
    mod = load_module()
    prompt = mod.build_work_order_prompt(
        "q40",
        "What evidence should be treated as guidance only, not proof?",
        {"answer": "draft"},
        [],
        1000,
    )
    assert "ENGRAM OVERLAY — BEHAVIOR GUIDANCE ONLY" in prompt
    assert "Never list Engram text" in prompt
    assert "runtime-policy-ready" in prompt
    assert "No citation/proof_context records returned" in prompt


def test_grade_catches_source_trace_ready_without_citations():
    mod = load_module()
    grade = mod.grade_answer(
        "- Source-trace status: Source-trace-ready\n- Evidence used: Engram overlay", 0
    )
    assert grade["source_trace_ready_without_citation"] is True
    assert grade["engram_policy_used_as_source_proof"] is True


def test_grade_allows_not_source_trace_ready_without_citations():
    mod = load_module()
    grade = mod.grade_answer(
        "- Source-trace status: Not source-trace-ready\n- Evidence used: None", 0
    )
    assert grade["source_trace_ready_without_citation"] is False
    assert grade["engram_policy_used_as_source_proof"] is False
