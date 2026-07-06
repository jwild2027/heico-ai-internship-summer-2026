from tiff.trace_net_h16d_llm_answer_reliability_v1 import (
    filter_question_records,
    looks_incomplete_llm_answer,
    looks_truncated_llm_answer,
    safety_contract_summary,
)


def test_h16d_truncation_detector_is_conservative():
    good = "Answer: Part 120-50645-005 is supported by exact evidence [E1].\nEvidence:\n- [E1] exact part record."
    assert looks_truncated_llm_answer(good) is False
    assert looks_incomplete_llm_answer(good, require_sections=True, min_chars=350) is False


def test_h16d_truncation_detector_catches_q18_style_tail():
    bad = "Answer: The OCR route lets the nomenclature merger can then carry this OCR-backed"
    assert looks_truncated_llm_answer(bad) is True


def test_h16d_truncation_detector_handles_non_string_without_crashing():
    assert looks_truncated_llm_answer({"manifest": True}) is False
    assert looks_incomplete_llm_answer(object()) is False


def test_filter_question_records_preserves_order():
    records = [
        {"question_id": "q01", "question": "a"},
        {"question_id": "q18", "question": "b"},
        {"question_id": "q25", "question": "c"},
    ]
    assert [r["question_id"] for r in filter_question_records(records, ["q18", "q25"])] == ["q18", "q25"]


def test_h16d_safety_contract_non_mutating():
    c = safety_contract_summary()
    assert c["answer_permission"] is False
    assert c["source_truth_mutation_allowed"] is False
    assert c["postgres_write_attempt"] is False
    assert c["qdrant_write_attempt"] is False
    assert c["opensearch_write_attempt"] is False
