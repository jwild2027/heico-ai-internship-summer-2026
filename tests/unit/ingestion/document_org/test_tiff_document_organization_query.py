from __future__ import annotations

import json
from pathlib import Path

from tiff.document_organization_query import (
    collect_ata_entries,
    format_ata,
    format_page,
    load_export,
    query_ata,
    query_page,
    query_part,
    summarize_export,
)


def _write_json(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_export(tmp_path: Path) -> Path:
    export = tmp_path / "export"
    export.mkdir()
    _write_json(
        export / "manual_ata_tree.json",
        {
            "manuals": [
                {
                    "manual_id": "t_p_120_1176",
                    "manual": "T.P. 120/1176",
                    "ata_groups": [
                        {
                            "ata_code": "25-21-00",
                            "manual": "T.P. 120/1176",
                            "page_count": 2,
                            "distinct_part_count": 1,
                            "pages": [
                                {"page_id": "p1", "ata": "25-21-00"},
                                {"page_id": "p2", "ata": "25-21-00"},
                            ],
                        }
                    ],
                }
            ]
        },
    )
    _write_json(
        export / "ata_tree.json",
        {
            "ata_groups": [
                {
                    "ata_code": "25-21-00",
                    "manual": "T.P. 120/1176",
                    "page_count": 2,
                    "distinct_part_count": 1,
                    "pages": [
                        {"page_id": "p1", "ata": "25-21-00", "page_label": "1056"},
                        {"page_id": "p2", "ata": "25-21-00", "page_label": "1059"},
                    ],
                }
            ]
        },
    )
    _write_json(
        export / "part_tree.json",
        {
            "parts": [
                {
                    "part_number": "120-37313-001",
                    "nomenclature": "HOLDER, MAGAZINE",
                    "mention_count": 28,
                    "page_count": 2,
                    "pages": [
                        {
                            "page_id": "p1",
                            "ata": "25-21-00",
                            "page_label": "1056",
                            "source_url": "http://example/source/p1",
                        }
                    ],
                }
            ]
        },
    )
    _write_json(
        export / "page_index.json",
        {
            "pages": [
                {
                    "page_id": "p1",
                    "ata": "25-21-00",
                    "page_label": "1056",
                    "source_url": "http://example/source/p1",
                    "tiff_path": "pages/p1.tif",
                    "ocr_text_path": "ocr/p1.txt",
                }
            ]
        },
    )
    _write_json(
        export / "organization_summary.json",
        {
            "manual_count": 1,
            "page_count": 1,
            "ata_group_count": 1,
            "part_count": 1,
            "part_mention_count": 28,
        },
    )
    return export


def test_load_export_and_summary(tmp_path: Path):
    export = load_export(_make_export(tmp_path))
    summary = summarize_export(export)
    assert summary["pages"] == 1
    assert summary["ata_groups"] == 1
    assert summary["parts"] == 1
    assert summary["part_mentions"] == 28
    assert summary["files_present"]["part_tree.json"] is True


def test_query_part(tmp_path: Path):
    export = load_export(_make_export(tmp_path))
    rows = query_part(export, "120-37313-001")
    assert len(rows) == 1
    assert rows[0]["nomenclature"] == "HOLDER, MAGAZINE"


def test_query_ata_does_not_collect_nested_pages(tmp_path: Path):
    export = load_export(_make_export(tmp_path))
    rows = query_ata(export, "25-21-00")
    assert len(rows) == 1
    assert rows[0]["ata_code"] == "25-21-00"
    assert "pages=2" in format_ata(rows[0])
    assert "parts=1" in format_ata(rows[0])
    assert len(collect_ata_entries(export)) == 1


def test_query_page_prints_ocr_text_path(tmp_path: Path):
    export = load_export(_make_export(tmp_path))
    rows = query_page(export, "1056")
    assert len(rows) == 1
    assert rows[0]["page_id"] == "p1"
    assert "OCR: ocr/p1.txt" in format_page(rows[0])


def test_missing_export_file_raises(tmp_path: Path):
    export = tmp_path / "export"
    export.mkdir()
    _write_json(export / "part_tree.json", {})
    try:
        load_export(export)
    except FileNotFoundError as exc:
        assert "manual_ata_tree.json" in str(exc)
    else:
        raise AssertionError("missing files should raise")
