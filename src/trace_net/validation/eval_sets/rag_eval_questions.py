"""Expanded command-line RAG eval question set for the TIFF backend.

Most questions are deterministic exact/retrieval checks. One broad LLM question
is intentionally marked manual_review so the normal quality gate stays useful.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


def _exact(qid: str, question: str, expected_terms: list[str], *, notes: str = "") -> dict[str, Any]:
    return {
        "id": qid,
        "question": question,
        "expected_terms": expected_terms,
        "answer_mode": "auto",
        "retrieval_mode": "auto",
        "use_llm": False,
        "use_embeddings": False,
        "expected_llm_used": False,
        "expected_embeddings_used": False,
        "notes": notes,
    }


EXPANDED_RAG_EVAL_QUESTIONS: list[dict[str, Any]] = [
    _exact("exact_part_120_37313_001", "What is part number 120-37313-001?", ["120-37313-001", "HOLDER, MAGAZINE"], notes="Golden exact part lookup; should avoid LLM/vector work."),
    _exact("exact_part_120_36843_001", "What is part number 120-36843-001?", ["120-36843-001", "HOLDER, MAGAZINE"], notes="Second known magazine-holder exact lookup."),
    _exact("exact_part_120_37313_535", "What is part number 120-37313-535?", ["120-37313-535", "HOLDER, MAGAZINE"], notes="Third known magazine-holder part from reverse lookup."),
    _exact("exact_part_am03078_22", "What is AM03078-22?", ["AM03078-22"], notes="Non-120-prefixed part/reference from the current eval set."),
    _exact("locate_am03078_22", "Which pages mention AM03078-22?", ["AM03078-22"], notes="Mention lookup should return source evidence without model generation."),
    _exact("source_pages_120_37313_001", "Which source pages mention part number 120-37313-001?", ["120-37313-001"], notes="Checks source-page lookup for the golden part."),
    _exact("exact_part_120_48023_001", "What is part number 120-48023-001?", ["120-48023-001"], notes="Real-looking catalog-review part; exact lookup should return source evidence."),
    _exact("exact_part_120_48024_001", "What is part number 120-48024-001?", ["120-48024-001"], notes="Companion catalog-review part."),
    _exact("exact_part_120_29068_001", "What is part number 120-29068-001?", ["120-29068-001"], notes="Common 120-29068 family exact lookup."),
    _exact("exact_part_120_36834_003", "What is part number 120-36834-003?", ["120-36834-003"], notes="Real part from the current QA review queue."),
    _exact("exact_part_120_50648_001", "What is part number 120-50648-001?", ["120-50648-001"], notes="Real part from the current QA review queue."),
    _exact("exact_part_120_61382_001", "What is part number 120-61382-001?", ["120-61382-001"], notes="Later catalog-page part family coverage."),
    _exact("exact_part_cr3523_5", "What is CR3523-5?", ["CR3523-5"], notes="Short vendor-style part/reference coverage."),
    _exact("exact_part_pe64005_1", "What is PE64005-1?", ["PE64005-1"], notes="PE-style part/reference coverage."),
    {
        "id": "nomenclature_locate_magazine_holder",
        "question": "Where is magazine holder shown?",
        "expected_terms": ["HOLDER, MAGAZINE", "120-37313-001", "120-36843-001"],
        "answer_mode": "auto",
        "retrieval_mode": "auto",
        "use_llm": False,
        "use_embeddings": False,
        "expected_llm_used": False,
        "expected_embeddings_used": False,
        "notes": "Reverse nomenclature lookup should stay deterministic and grouped by part number.",
    },
    {
        "id": "nomenclature_holder_magazine_exact",
        "question": "Which parts are related to HOLDER, MAGAZINE?",
        "expected_terms": ["HOLDER, MAGAZINE", "120-37313-001", "120-36843-001"],
        "answer_mode": "auto",
        "retrieval_mode": "auto",
        "use_llm": False,
        "use_embeddings": False,
        "expected_llm_used": False,
        "expected_embeddings_used": False,
        "notes": "Reverse part-name lookup using aircraft-style nomenclature order.",
    },
    {
        "id": "structured_summary_magazine_holder",
        "question": "Summarize the sources related to magazine holder parts.",
        "expected_terms": ["HOLDER, MAGAZINE", "120-37313-001", "120-36843-001"],
        "answer_mode": "summarize",
        "retrieval_mode": "hybrid",
        "use_llm": False,
        "expected_llm_used": False,
        "expected_embeddings_used": True,
        "notes": "Structured part summary should use retrieval but avoid open-ended LLM generation.",
    },
    {
        "id": "compare_magazine_holder_parts",
        "question": "Compare the magazine holder part numbers.",
        "expected_terms": ["HOLDER, MAGAZINE", "120-37313-001", "120-36843-001"],
        "answer_mode": "summarize",
        "retrieval_mode": "hybrid",
        "use_llm": False,
        "expected_llm_used": False,
        "expected_embeddings_used": True,
        "notes": "Comparison wording should still use citation-safe structured grouping.",
    },
    {
        "id": "retrieval_ata_25_21_00_no_llm",
        "question": "Find source evidence for ATA 25-21-00.",
        "expected_terms": ["25-21-00"],
        "answer_mode": "summarize",
        "retrieval_mode": "hybrid",
        "use_llm": False,
        "force_embeddings": True,
        "expected_llm_used": False,
        "expected_embeddings_used": True,
        "notes": "Retrieval-only ATA evidence check; avoids adding another manual-review LLM row.",
    },
    {
        "id": "retrieval_passenger_seat_back_no_llm",
        "question": "Find source pages about passenger seat back.",
        "expected_terms": ["passenger", "seat", "back"],
        "answer_mode": "summarize",
        "retrieval_mode": "hybrid",
        "use_llm": False,
        "force_embeddings": True,
        "expected_llm_used": False,
        "expected_embeddings_used": True,
        "notes": "Retrieval-only broad-topic check for passenger seat back evidence.",
    },
    {
        "id": "broad_summary_passenger_seat_back_crack_reinforcement",
        "question": "Which pages discuss passenger seat back crack reinforcement, and what do they say?",
        "expected_terms": ["passenger", "seat", "back"],
        "answer_mode": "auto",
        "retrieval_mode": "hybrid",
        "force_llm": True,
        "force_embeddings": True,
        "expected_llm_used": True,
        "expected_embeddings_used": True,
        "manual_review": True,
        "notes": "The one normal-pipeline broad LLM question. It should be reviewed, not auto-passed.",
    },
]


def write_expanded_rag_eval_questions(path: str | Path) -> Path:
    """Write the expanded question set as JSON and return the path."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"questions": EXPANDED_RAG_EVAL_QUESTIONS}
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out_path


def summarize_question_set(questions: Iterable[Mapping[str, Any]] = EXPANDED_RAG_EVAL_QUESTIONS) -> dict[str, Any]:
    """Return small CLI-friendly counts for a question set."""
    rows = list(questions)
    status = Counter()
    for row in rows:
        if row.get("manual_review"):
            status["manual_review"] += 1
        elif row.get("force_llm") or row.get("expected_llm_used") is True or row.get("expect_llm_used") is True:
            status["llm_checked"] += 1
        else:
            status["deterministic_or_retrieval"] += 1
    return {
        "questions": len(rows),
        "manual_review": status.get("manual_review", 0),
        "llm_checked": status.get("llm_checked", 0),
        "deterministic_or_retrieval": status.get("deterministic_or_retrieval", 0),
        "expected_no_llm": sum(1 for row in rows if row.get("expected_llm_used") is False or row.get("expect_llm_used") is False),
        "expected_embeddings": sum(1 for row in rows if row.get("expected_embeddings_used") is True or row.get("expect_embeddings_used") is True),
    }
