from tiff.streamlit_ui_backend import (
    ata_result_records,
    page_result_records,
    parse_rag_cli_stdout,
    part_result_records,
    part_source_records,
)


def test_parse_rag_cli_stdout_splits_answer_and_sources():
    stdout = """Question: What is part number 120-37313-001?
LLM used: False
Embeddings used: False

Answer:

120-37313-001 is listed as HOLDER, MAGAZINE.

Sources:
1. T.P. 120/1176 - ATA 25-21-00 - Page 1056
"""
    parsed = parse_rag_cli_stdout(stdout)
    assert parsed.question == "What is part number 120-37313-001?"
    assert parsed.llm_used == "False"
    assert parsed.embeddings_used == "False"
    assert "HOLDER, MAGAZINE" in parsed.answer
    assert "Page 1056" in parsed.sources


def test_part_result_records_and_nested_sources_are_table_ready():
    rows = [
        {
            "part_number": "120-37313-001",
            "nomenclature": "HOLDER, MAGAZINE",
            "page_count": 28,
            "mention_count": 28,
            "pages": [
                {
                    "page_id": "p1",
                    "ata": "25-21-00",
                    "page_label": "1056",
                    "source_url": "http://localhost/source",
                }
            ],
        }
    ]
    table = part_result_records(rows)
    assert table == [
        {
            "Part": "120-37313-001",
            "Nomenclature": "HOLDER, MAGAZINE",
            "Pages": 28,
            "Mentions": 28,
            "First source": "http://localhost/source",
        }
    ]
    sources = part_source_records(rows[0])
    assert sources[0]["Page ID"] == "p1"
    assert sources[0]["ATA"] == "25-21-00"


def test_ata_and_page_result_records_are_table_ready():
    ata_rows = [{"ata": "25-21-00", "manual": "T.P. 120/1176", "page_count": 501, "distinct_part_count": 382}]
    assert ata_result_records(ata_rows)[0] == {
        "ATA": "25-21-00",
        "Manual": "T.P. 120/1176",
        "Pages": 501,
        "Parts": 382,
    }
    page_rows = [
        {
            "page_id": "p1",
            "ata": "11-00-66",
            "page_label": "1021",
            "source_url": "http://localhost/source",
            "tiff_path": "page.tif",
            "ocr_text_path": "page.txt",
        }
    ]
    assert page_result_records(page_rows)[0]["OCR"] == "page.txt"
