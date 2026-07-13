import json
import zipfile
from pathlib import Path

from scripts.run_trace_net_tiff_content_fixed50_qa_v1 import (
    _fixed_questions,
    build_content_index,
    run_fixed50,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_fixed_question_count_is_50():
    assert len(_fixed_questions()) == 50


def test_index_extracts_tiff_content_clues(tmp_path):
    root = tmp_path / "local_data" / "organization" / "trace_net"
    _write_json(
        root / "page_context_v2" / "p001.json",
        {
            "page_id": "t_p_demo_p000001",
            "page_number": 1,
            "page_type": "image_visual",
            "summary": "FIGURE 69 shows a PAPER TOWEL DISPENSER. ATA 25-21-00 is visible.",
            "nomenclature": "PAPER TOWEL DISPENSER",
        },
    )
    _write_json(
        root / "table" / "p002.json",
        {
            "page_id": "t_p_demo_p000002",
            "page_number": 2,
            "route": "table",
            "summary": "blank table detected for review",
        },
    )
    _write_json(
        root / "ocr" / "p003.json",
        {
            "page_id": "t_p_demo_p000003",
            "page_number": 3,
            "ocr_text": "WARNING: remove screw 120-36833-001 before installation.",
        },
    )
    zip_path = tmp_path / "metadata.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("page001.tif", b"fake")
        zf.writestr("page002.tif", b"fake")

    index = build_content_index(root, zip_path)

    assert index.metrics["content_record_count"] >= 3
    assert index.metrics["zip_tiff_count"] == 2
    assert "ATA 25-21-00" in index.all_text or "25-21-00" in index.all_text
    assert "PAPER TOWEL DISPENSER" in index.all_text
    assert "blank table" in index.all_text.lower()


def test_run_outputs_question_answer_format(tmp_path):
    root = tmp_path / "trace_net"
    _write_json(
        root / "visual" / "p001.json",
        {
            "page_id": "page_001",
            "page_number": 1,
            "summary": "FIGURE 69 contains visual nomenclature PAPER TOWEL DISPENSER and ATA 25-21-00.",
            "nomenclature": "PAPER TOWEL DISPENSER",
        },
    )
    _write_json(
        root / "table" / "p002.json",
        {"page_id": "page_002", "page_number": 2, "route": "table", "summary": "blank table candidate"},
    )
    index = build_content_index(root, None)
    out = tmp_path / "out"
    summary = run_fixed50(index, out)

    assert summary["quality_status"] == "PASS"
    qa_text = (out / "answers_question_answer.txt").read_text(encoding="utf-8")
    assert "Question 01:" in qa_text
    assert "Answer 01:" in qa_text
    assert "Question 50:" in qa_text
    assert "Answer 50:" in qa_text


def test_no_content_artifacts_fails_quality(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    index = build_content_index(root, None)
    out = tmp_path / "out"
    summary = run_fixed50(index, out)
    assert summary["quality_status"] == "FAIL"
    assert "no_tiff_derived_content_records_found" in summary["quality_failures"]
