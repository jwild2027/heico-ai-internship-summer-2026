import json

from tiff.rag_eval import load_eval_questions, question_from_dict
from tiff.rag_eval_questions import (
    EXPANDED_RAG_EVAL_QUESTIONS,
    summarize_question_set,
    write_expanded_rag_eval_questions,
)


def test_expanded_eval_has_at_least_twenty_questions():
    assert len(EXPANDED_RAG_EVAL_QUESTIONS) >= 20


def test_expanded_eval_ids_are_unique():
    ids = [row["id"] for row in EXPANDED_RAG_EVAL_QUESTIONS]
    assert len(ids) == len(set(ids))


def test_expanded_eval_keeps_only_one_manual_review_question():
    manual = [row for row in EXPANDED_RAG_EVAL_QUESTIONS if row.get("manual_review")]
    assert [row["id"] for row in manual] == ["broad_summary_passenger_seat_back_crack_reinforcement"]


def test_expanded_eval_first_smoke_questions_are_fast_path_checks():
    first_eight = EXPANDED_RAG_EVAL_QUESTIONS[:8]
    assert all(row.get("expected_llm_used") is False for row in first_eight)
    assert all(row.get("use_llm") is False for row in first_eight)
    assert not any(row.get("manual_review") for row in first_eight)


def test_expanded_eval_covers_core_backend_paths():
    ids = {row["id"] for row in EXPANDED_RAG_EVAL_QUESTIONS}
    assert "exact_part_120_37313_001" in ids
    assert "nomenclature_locate_magazine_holder" in ids
    assert "structured_summary_magazine_holder" in ids
    assert "retrieval_ata_25_21_00_no_llm" in ids
    assert "retrieval_passenger_seat_back_no_llm" in ids
    assert "broad_summary_passenger_seat_back_crack_reinforcement" in ids


def test_question_from_dict_accepts_expected_and_expect_aliases():
    q1 = question_from_dict({"question": "q", "expected_llm_used": False, "expected_embeddings_used": True})
    q2 = question_from_dict({"question": "q", "expect_llm_used": True, "expect_embeddings_used": False})
    assert q1.expected_llm_used is False
    assert q1.expected_embeddings_used is True
    assert q2.expected_llm_used is True
    assert q2.expected_embeddings_used is False


def test_load_eval_questions_uses_expanded_defaults():
    questions = load_eval_questions()
    assert len(questions) == len(EXPANDED_RAG_EVAL_QUESTIONS)
    assert questions[0].id == "exact_part_120_37313_001"
    assert sum(1 for question in questions if question.manual_review) == 1


def test_summarize_question_set_counts_are_command_line_friendly():
    summary = summarize_question_set()
    assert summary["questions"] == len(EXPANDED_RAG_EVAL_QUESTIONS)
    assert summary["manual_review"] == 1
    assert summary["expected_no_llm"] >= 15
    assert summary["expected_embeddings"] >= 3


def test_write_expanded_rag_eval_questions(tmp_path):
    out = tmp_path / "rag_eval_questions.json"
    written = write_expanded_rag_eval_questions(out)
    assert written == out
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "questions" in payload
    assert len(payload["questions"]) == len(EXPANDED_RAG_EVAL_QUESTIONS)
    assert payload["questions"][0]["id"] == "exact_part_120_37313_001"
