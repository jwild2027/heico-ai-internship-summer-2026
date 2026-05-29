from __future__ import annotations

import json
from pathlib import Path
import subprocess

from tiff.streamlit_ui_backend import (
    ata_header,
    format_status_text,
    load_ui_status,
    page_header,
    page_table_rows,
    parse_rag_stdout,
    part_header,
    run_rag_question,
    search_ata,
    search_pages,
    search_parts,
    source_table_rows,
)
from tiff.document_organization_query import load_export


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_export(root: Path) -> Path:
    export_dir = root / "export"
    _write_json(
        export_dir / "part_tree.json",
        {
            "parts": [
                {
                    "part_number": "120-37313-001",
                    "nomenclature": "HOLDER, MAGAZINE",
                    "page_count": 2,
                    "mention_count": 2,
                    "pages": [
                        {
                            "page_id": "p1",
                            "ata": "25-21-00",
                            "page_label": "1056",
                            "source_url": "http://example/source/1",
                            "tiff_path": "pages/0001.tif",
                            "ocr_path": "ocr/0001.txt",
                        }
                    ],
                }
            ]
        },
    )
    _write_json(
        export_dir / "ata_tree.json",
        {
            "ata_groups": [
                {
                    "ata": "25-21-00",
                    "manual": "T.P. 120/1176",
                    "page_count": 10,
                    "distinct_part_count": 4,
                }
            ]
        },
    )
    _write_json(export_dir / "manual_ata_tree.json", {"manuals": []})
    _write_json(
        export_dir / "page_index.json",
        {
            "pages": [
                {
                    "page_id": "p1",
                    "ata": "25-21-00",
                    "page_label": "1056",
                    "source_url": "http://example/source/1",
                    "tiff_path": "pages/0001.tif",
                    "ocr_path": "ocr/0001.txt",
                }
            ]
        },
    )
    _write_json(
        export_dir / "organization_summary.json",
        {"counts": {"manuals": 1, "pages": 1, "ata_groups": 1, "parts": 1, "part_mentions": 2}},
    )
    return export_dir


def test_ui_status_ok_with_export_and_quality(tmp_path: Path) -> None:
    export_dir = _make_export(tmp_path)
    manifest = tmp_path / "manifest.json"
    quality = tmp_path / "quality.json"
    _write_json(manifest, {"pipeline_status": "ok"})
    _write_json(
        quality,
        {
            "status": "ok",
            "summary": {
                "source_local_review_ready": True,
                "source_real_rescarta_ready": False,
                "ocr_empty_files": 14,
                "incremental_smoke_ok": True,
            },
        },
    )

    status = load_ui_status(export_dir=export_dir, manifest_path=manifest, quality_path=quality)

    assert status.ok is True
    assert status.export_ready is True
    assert status.pages == 1
    assert status.parts == 1
    assert status.incremental_smoke_ok is True
    assert "Status: OK" in format_status_text(status)


def test_search_helpers_use_organization_export(tmp_path: Path) -> None:
    export = load_export(_make_export(tmp_path))

    parts = search_parts(export, "magazine")
    atas = search_ata(export, "25-21-00")
    pages = search_pages(export, "p1")

    assert parts[0]["part_number"] == "120-37313-001"
    assert atas[0]["ata"] == "25-21-00"
    assert pages[0]["page_id"] == "p1"


def test_display_helpers_create_structured_rows(tmp_path: Path) -> None:
    export = load_export(_make_export(tmp_path))
    part = search_parts(export, "120-37313-001")[0]
    ata = search_ata(export, "25-21-00")[0]
    page = search_pages(export, "p1")[0]

    assert part_header(part)["nomenclature"] == "HOLDER, MAGAZINE"
    assert ata_header(ata)["manual"] == "T.P. 120/1176"
    assert page_header(page)["ocr"] == "ocr/0001.txt"
    assert source_table_rows(part)[0]["source"] == "http://example/source/1"
    assert page_table_rows([page])[0]["tiff"] == "pages/0001.tif"


def test_parse_rag_stdout_splits_answer_and_sources() -> None:
    stdout = """Question: What is part number 120-37313-001?
LLM used: False
Embeddings used: False

Answer:

120-37313-001 is listed as HOLDER, MAGAZINE.

Sources:
1. Source row
"""
    parsed = parse_rag_stdout(stdout)

    assert parsed.question == "What is part number 120-37313-001?"
    assert parsed.llm_used is False
    assert parsed.embeddings_used is False
    assert "HOLDER, MAGAZINE" in parsed.answer
    assert "Source row" in parsed.sources


def test_run_rag_question_builds_existing_cli_command(tmp_path: Path) -> None:
    script = tmp_path / "ask.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    result = run_rag_question("What is part number 120-37313-001?", ask_script=script, config_path="local_config.yaml")

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0
    assert "ok" in result.stdout
