from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tiff.feedback_session import (
    AnswerRun,
    audit_source_zip,
    make_feedback_entry,
    normalize_rating,
    save_feedback,
    summarize_feedback,
)


def test_audit_source_zip_counts_tiffs_and_metadata(tmp_path: Path) -> None:
    zip_path = tmp_path / "metadata.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("metadata.xml", "<metadata />")
        zf.writestr("00000001.tif", b"fake")
        zf.writestr("00000002.tif", b"fake")

    audit = audit_source_zip(zip_path)

    assert audit.status == "ok"
    assert audit.tiff_files == 2
    assert audit.xml_files == 1
    assert audit.metadata_xml_present is True
    assert audit.ocr_text_files == 0
    assert any("no OCR" in warning for warning in audit.warnings)


def test_normalize_rating_accepts_common_inputs() -> None:
    assert normalize_rating("up") == ("thumbs_up", 1)
    assert normalize_rating("down") == ("thumbs_down", -1)
    assert normalize_rating("5") == ("thumbs_up", 5)
    assert normalize_rating("3") == ("neutral", 3)
    assert normalize_rating("1") == ("thumbs_down", 1)


def test_make_and_save_feedback_entry(tmp_path: Path) -> None:
    answer = AnswerRun(
        question="What is part 120-37313-001?",
        command=["python", "scripts/ask_tiff_rag.py"],
        returncode=0,
        elapsed_seconds=0.25,
        stdout="LLM used: False\nEmbeddings used: False\n120-37313-001 is HOLDER, MAGAZINE.",
        stderr="",
        llm_used=False,
        embeddings_used=False,
    )
    audit = audit_source_zip(None)
    entry = make_feedback_entry(
        session_id="test_session",
        question=answer.question,
        answer=answer,
        rating_value="up",
        reason="Correct answer and source shown.",
        category="useful",
        source_zip=audit,
        config="local_config.yaml",
    )

    output = tmp_path / "feedback.jsonl"
    summary_output = tmp_path / "summary.json"
    summary = save_feedback(entry, output, summary_output)

    assert output.exists()
    assert summary_output.exists()
    assert summary["total_feedback"] == 1
    assert summary["rating_counts"] == {"thumbs_up": 1}

    row = json.loads(output.read_text(encoding="utf-8").strip())
    assert row["question"] == answer.question
    assert row["rating"] == "thumbs_up"
    assert row["category"] == "useful"


def test_summarize_feedback_counts_categories() -> None:
    summary = summarize_feedback([
        {"rating": "thumbs_up", "category": "useful"},
        {"rating": "thumbs_down", "category": "wrong_source"},
        {"rating": "thumbs_down", "category": "wrong_source"},
    ])

    assert summary["total_feedback"] == 3
    assert summary["rating_counts"]["thumbs_down"] == 2
    assert summary["category_counts"]["wrong_source"] == 2
