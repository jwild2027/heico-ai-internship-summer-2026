from pathlib import Path

from tiff.rag_model_eval import (
    ModelEvalQuestion,
    default_model_eval_questions,
    evaluate_text,
    parse_ask_tiff_rag_output,
    summarize_results,
    write_questions,
    load_questions,
    ModelEvalResult,
)


def test_default_questions_include_deterministic_and_summary_cases():
    questions = default_model_eval_questions()
    ids = {q.id for q in questions}
    assert "part_lookup_120_37313_001" in ids
    assert "structured_summary_magazine_holder" in ids
    assert any(q.retrieval_mode == "hybrid" for q in questions)


def test_parse_ask_tiff_rag_output_extracts_flags_answer_and_sources():
    text = """Question: X
LLM used: True
Embeddings used: False

Answer:

Example answer.

Sources:
1. Source A
2. Source B
"""
    llm_used, embeddings_used, answer, source_count = parse_ask_tiff_rag_output(text)
    assert llm_used is True
    assert embeddings_used is False
    assert answer == "Example answer."
    assert source_count == 2


def test_evaluate_text_fails_on_missing_expected_terms():
    status, missing_terms, missing_sources = evaluate_text("HOLDER, MAGAZINE Page 1056", ["120-37313-001"], ["Page 1056"], 0)
    assert status == "fail"
    assert missing_terms == ["120-37313-001"]
    assert missing_sources == []


def test_question_round_trip(tmp_path: Path):
    path = tmp_path / "questions.json"
    questions = [ModelEvalQuestion(id="q1", question="What is 120-37313-001?", expected_terms=("HOLDER",))]
    write_questions(path, questions)
    loaded = load_questions(path)
    assert loaded == questions


def test_summarize_results_groups_by_model_and_status():
    results = [
        ModelEvalResult("q1", "Q1", "gemma3:12B", "auto", "auto", 8, "pass", 1.0, False, False, 1),
        ModelEvalResult("q2", "Q2", "gemma3:12B", "summarize", "hybrid", 8, "manual_review", 2.0, True, True, 3),
    ]
    summary = summarize_results(results)
    assert summary["total"] == 2
    assert summary["by_status"] == {"pass": 1, "manual_review": 1}
    assert summary["by_model"]["gemma3:12B"]["llm_used"] == 1
