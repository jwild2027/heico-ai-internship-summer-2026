from pathlib import Path
import json

from tiff.trace_net_page_context_overlay import (
    canonical_page_id,
    load_context_records,
    normalize_context_record,
    page_aliases,
    parse_page_number,
)


def test_parse_page_number_variants():
    assert parse_page_number("t_p_120_1176_p000003") == 3
    assert parse_page_number("zip_page_000003") == 3
    assert parse_page_number("page:zip_page_000509") == 509


def test_canonical_page_id_from_zip_page():
    assert canonical_page_id("zip_page_000003") == "t_p_120_1176_p000003"
    assert canonical_page_id("t_p_120_1176_p000004") == "t_p_120_1176_p000004"


def test_page_aliases_include_zip_and_trace_net():
    aliases = page_aliases("t_p_120_1176_p000003")
    assert "t_p_120_1176_p000003" in aliases
    assert "zip_page_000003" in aliases
    assert "page:t_p_120_1176_p000003" in aliases


def test_normalize_context_record_marks_not_source_truth():
    rec = normalize_context_record({
        "page_id": "zip_page_000003",
        "summary": "Parts list page",
        "role": "parts_list",
        "topics": ["parts list", "applicability"],
        "highlighted_parts": ["120-50645-009"],
        "confidence": "high",
    })
    assert rec["page_id"] == "t_p_120_1176_p000003"
    assert rec["can_answer_directly"] is False
    assert rec["can_support_answer"] is True
    assert rec["canonical_source_truth"] is False
    assert rec["requires_citation"] is True


def test_load_context_records_from_mapping(tmp_path: Path):
    path = tmp_path / "contexts.json"
    path.write_text(json.dumps({
        "t_p_120_1176_p000001": {"summary": "Front matter", "role": "front_matter", "topics": "manual,title"},
        "t_p_120_1176_p000002": {"summary": "Blank", "role": "blank", "topics": []},
    }), encoding="utf-8")
    records = load_context_records(path)
    assert len(records) == 2
    assert records[0]["context_id"].startswith("page_context:")
    assert any(r["role"] == "blank" for r in records)


def test_normalize_context_extracts_nested_highlighted_parts():
    rec = normalize_context_record({
        "page_id": "t_p_120_1176_p000003",
        "summary": "Applicability page",
        "entities": {"parts": [{"part_number": "120-50645-009"}, {"id": "120-50648-003"}]},
    })
    assert "120-50645-009" in rec["highlighted_parts"]
    assert "120-50648-003" in rec["highlighted_parts"]
