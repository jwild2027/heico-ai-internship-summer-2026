from pathlib import Path
import json

from tiff.rag_ata_answer import build_ata_section_answer, extract_ata_code, looks_like_ata_query


def write_export(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manual_ata_tree.json").write_text("{}", encoding="utf-8")
    (root / "ata_tree.json").write_text(
        json.dumps(
            {
                "ata_groups": [
                    {
                        "ata": "25-21-00",
                        "manual": "T.P. 120/1176",
                        "page_count": 2,
                        "distinct_part_count": 3,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "part_tree.json").write_text('{"parts": []}', encoding="utf-8")
    (root / "page_index.json").write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "page_id": "p_front",
                        "ata": "25-21-00",
                        "page_sequence": 1,
                        "page_label": "1",
                        "source_url": "http://example/source/front",
                        "tiff_path": "pages/front.tif",
                        "ocr_text_path": "ocr/front.txt",
                        "part_numbers": [],
                    },
                    {
                        "page_id": "p_empty",
                        "ata": "25-21-00",
                        "page_sequence": 2,
                        "page_label": "2",
                        "source_url": "http://example/source/empty",
                        "tiff_path": "pages/empty.tif",
                        "ocr_text_path": "ocr/empty.txt",
                        "empty_ocr": True,
                        "part_numbers": ["120-00000-001"],
                    },
                    {
                        "page_id": "p_evidence",
                        "ata": "25-21-00",
                        "page_sequence": 1056,
                        "page_label": "1056",
                        "source_url": "http://example/source/evidence",
                        "tiff_path": "pages/evidence.tif",
                        "ocr_text_path": "ocr/evidence.txt",
                        "part_numbers": ["120-37313-001", "120-36843-001"],
                    },
                    {
                        "page_id": "p2",
                        "ata": "25-21-00",
                        "page_sequence": 1057,
                        "page_label": "1057",
                        "source_url": "http://example/source/2",
                        "tiff_path": "pages/2.tif",
                        "ocr_text_path": "ocr/2.txt",
                        "part_numbers": ["120-37313-001"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "organization_summary.json").write_text(
        json.dumps({"counts": {"manuals": 1, "pages": 2, "ata_groups": 1}}),
        encoding="utf-8",
    )


def test_extract_ata_code():
    assert extract_ata_code("Find evidence for ATA 25-21-00") == "25-21-00"
    assert extract_ata_code("show 25-21-00") == "25-21-00"
    assert extract_ata_code("part 120-37313-001") == ""


def test_looks_like_ata_query():
    assert looks_like_ata_query("Find evidence for ATA 25-21-00")
    assert looks_like_ata_query("show 25-21-00")
    assert not looks_like_ata_query("What is part number 120-37313-001?")


def test_build_ata_section_answer_from_export(tmp_path: Path):
    export_dir = tmp_path / "export"
    write_export(export_dir)
    result = build_ata_section_answer(export_dir, "Find evidence for ATA 25-21-00", page_limit=1)
    assert result is not None
    assert result.found is True
    assert result.ata_code == "25-21-00"
    assert "ATA 25-21-00 is present" in result.answer
    assert "Manual: T.P. 120/1176" in result.answer
    assert "Source: http://example/source/evidence" in result.answer
    assert "parts=2" in result.answer
    first_source_line = next(line for line in result.answer.splitlines() if line.startswith("   Source:"))
    assert first_source_line == "   Source: http://example/source/evidence"
    assert "LLM" in result.answer


def test_build_ata_section_answer_returns_none_for_non_ata(tmp_path: Path):
    export_dir = tmp_path / "export"
    write_export(export_dir)
    assert build_ata_section_answer(export_dir, "What is part number 120-37313-001?") is None


def test_ata_answer_prefers_nonempty_pages_with_parts(tmp_path: Path):
    export_dir = tmp_path / "export"
    write_export(export_dir)
    result = build_ata_section_answer(export_dir, "Find evidence for ATA 25-21-00", page_limit=3)
    assert result is not None
    lines = result.answer.splitlines()
    first_page = next(line for line in lines if line.startswith("1. page="))
    assert "page=p_evidence" in first_page
    assert "parts=2" in first_page
    assert "empty_ocr=True" not in first_page
