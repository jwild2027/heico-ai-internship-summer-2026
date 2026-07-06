from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_h16c_llm_answer_reliability_v1 import (
    build_h16c_ollama_options,
    filter_question_records,
    looks_incomplete_llm_answer,
    merge_h16c_ollama_options,
    safety_contract_summary,
)


def test_h16c_detects_q18_style_truncation_tail() -> None:
    text = (
        "Answer:\nThe raw OCR nomenclature extractor added OCR-backed line-text evidence. "
        "Visual links establish figure-to-part identity [V6], while OCR nomenclature "
        "provides part-name proof [O1]. The nomenclature merger can then carry this OCR-backed"
    )
    assert looks_incomplete_llm_answer(text)


def test_h16c_accepts_complete_engineering_answer_shape() -> None:
    text = "\n".join(
        [
            "Answer: The raw OCR nomenclature extractor added line-text part-name evidence.",
            "Evidence: [V6] links Figure 69 to the part; [O1] supplies DOUBLE PASSENGER SEAT ASSY.",
            "Engineering confidence: High for the pipeline explanation because both route roles are cited.",
            "Limits: This proves nomenclature recovery behavior only; it does not prove fit, effectivity, interchangeability, replacement approval, or installation safety.",
        ]
    )
    assert not looks_incomplete_llm_answer(text)


def test_h16c_ollama_options_merge_preserves_existing_values() -> None:
    payload = {"model": "gemma4:26b", "prompt": "x", "stream": False, "options": {"temperature": 0.2}}
    out = merge_h16c_ollama_options(payload)
    assert out is payload
    assert out["options"]["temperature"] == 0.2
    assert out["options"]["num_predict"] == 900


def test_h16c_ollama_options_defaults() -> None:
    assert build_h16c_ollama_options() == {"num_predict": 900, "temperature": 0.1}


def test_h16c_question_filter_preserves_order_and_requires_all_ids() -> None:
    records = [
        {"question_id": "q17", "question": "a"},
        {"question_id": "q18", "question": "b"},
        {"question_id": "q19", "question": "c"},
    ]
    assert filter_question_records(records, ["q18"])[0]["question"] == "b"


def test_h16c_safety_contract_has_no_write_or_answer_authority() -> None:
    contract = safety_contract_summary()
    assert contract["source_truth_mutation_allowed"] is False
    assert contract["answer_permission"] is False
    assert contract["postgres_write_attempt"] is False
    assert contract["qdrant_write_attempt"] is False
    assert contract["opensearch_write_attempt"] is False
