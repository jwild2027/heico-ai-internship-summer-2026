from __future__ import annotations

import json
from pathlib import Path

from tiff.visual_text_extraction import (
    ExtractionOptions,
    MockVisualTextClient,
    PlannedVisualTextClient,
    VisualTextPaths,
    build_visual_text_prompt,
    load_page_cards,
    run_visual_text_extraction,
    select_candidate_cards,
)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_fixture(tmp_path: Path) -> VisualTextPaths:
    image_path = tmp_path / "page_001.png"
    image_path.write_bytes(b"not-real-image-but-mock-client-does-not-read")
    cards_path = tmp_path / "page_character_cards.json"
    page_index_path = tmp_path / "page_index.json"
    output_dir = tmp_path / "visual_text"
    _write_json(
        cards_path,
        {
            "page_cards": [
                {
                    "page_id": "t_p_120_1176_p000001",
                    "entity_id": "page:t_p_120_1176_p000001",
                    "parents": {
                        "document_label": "T.P. 120/1176",
                        "ata_code": "25-21-00",
                    },
                    "context": {
                        "page_role": "table",
                        "summary": "A table with part numbers and quantities.",
                    },
                    "signals": {
                        "image_classification": "likely_table_or_grid",
                    },
                    "source": {
                        "source_url": "file:///page_001.tif",
                        "tiff_path": str(image_path),
                        "ocr_path": str(tmp_path / "page_001.txt"),
                    },
                    "parts": [
                        {"part_number": "120-1", "nomenclature": "BRACKET"},
                    ],
                    "derived_traits": ["quality:answer_ready_page=true"],
                },
                {
                    "page_id": "t_p_120_1176_p000002",
                    "parents": {"document_label": "T.P. 120/1176", "ata_code": "25-21-00"},
                    "context": {"page_role": "blank"},
                    "signals": {"image_classification": "likely_blank"},
                    "source": {"tiff_path": str(image_path)},
                },
            ]
        },
    )
    _write_json(page_index_path, {"pages": []})
    return VisualTextPaths(page_cards_path=cards_path, page_index_path=page_index_path, output_dir=output_dir)


def test_load_page_cards_and_select_visual_candidates(tmp_path: Path) -> None:
    paths = _make_fixture(tmp_path)
    cards = load_page_cards(paths.page_cards_path, paths.page_index_path)
    selected = select_candidate_cards(cards, max_pages=None)

    assert len(cards) == 2
    assert len(selected) == 1
    assert selected[0]["page_id"] == "t_p_120_1176_p000001"


def test_visual_text_prompt_mentions_tables_charts_diagrams_and_no_guessing(tmp_path: Path) -> None:
    paths = _make_fixture(tmp_path)
    card = load_page_cards(paths.page_cards_path, paths.page_index_path)[0]

    prompt = build_visual_text_prompt(card)

    lowered = prompt.lower()
    assert "tables" in lowered
    assert "charts" in lowered
    assert "diagrams" in lowered
    assert "do not invent" in lowered
    assert "120-1" in prompt
    assert "25-21-00" in prompt


def test_run_visual_text_extraction_with_mock_client_writes_records_and_graph_overlay(tmp_path: Path) -> None:
    paths = _make_fixture(tmp_path)
    options = ExtractionOptions(provider="mock", max_pages=None, overwrite=True)
    result = run_visual_text_extraction(paths, options, client=MockVisualTextClient())

    assert result.status == "OK"
    assert result.summary["selected_pages"] == 1
    assert result.summary["ok_records"] == 1
    assert result.summary["pages_with_visual_text"] == 1
    assert result.summary["graph_overlay_nodes"] >= 2
    assert result.summary["graph_overlay_edges"] >= 2
    assert paths.records_path.exists()
    assert paths.summary_path.exists()
    assert paths.corpus_md_path.exists()
    assert paths.graph_nodes_path.exists()
    assert paths.graph_edges_path.exists()
    assert "Mock visual extraction" in paths.corpus_md_path.read_text(encoding="utf-8")


def test_run_visual_text_extraction_planned_provider_is_safe_for_no_model_pilot(tmp_path: Path) -> None:
    paths = _make_fixture(tmp_path)
    options = ExtractionOptions(provider="planned", max_pages=1, overwrite=True)
    result = run_visual_text_extraction(paths, options, client=PlannedVisualTextClient())

    assert result.status == "OK"
    assert result.summary["planned_records"] == 1
    assert result.records[0]["status"] == "planned"
