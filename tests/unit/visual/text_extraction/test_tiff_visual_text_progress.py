from __future__ import annotations

import json
from pathlib import Path

from tiff.visual_text_extraction import (
    ExtractionOptions,
    MockVisualTextClient,
    VisualTextPaths,
    run_visual_text_extraction,
)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_two_page_fixture(tmp_path: Path) -> VisualTextPaths:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"mock image")
    cards_path = tmp_path / "page_character_cards.json"
    page_index_path = tmp_path / "page_index.json"
    output_dir = tmp_path / "visual_text"
    _write_json(
        cards_path,
        {
            "page_cards": [
                {
                    "page_id": "p001",
                    "context": {"page_role": "figure"},
                    "signals": {"image_classification": "likely_figure_or_diagram"},
                    "source": {"tiff_path": str(image_path)},
                },
                {
                    "page_id": "p002",
                    "context": {"page_role": "table"},
                    "signals": {"image_classification": "likely_table_or_grid"},
                    "source": {"tiff_path": str(image_path)},
                },
            ]
        },
    )
    _write_json(page_index_path, {"pages": []})
    return VisualTextPaths(page_cards_path=cards_path, page_index_path=page_index_path, output_dir=output_dir)


def test_visual_text_progress_prints_each_completed_page_and_checkpoints(tmp_path: Path, capsys) -> None:
    paths = _make_two_page_fixture(tmp_path)
    options = ExtractionOptions(
        provider="mock",
        max_pages=2,
        overwrite=True,
        progress=True,
        checkpoint_every=1,
    )

    result = run_visual_text_extraction(paths, options, client=MockVisualTextClient())
    captured = capsys.readouterr().out

    assert result.status == "OK"
    assert "Visual text extraction progress" in captured
    assert "[1/2] p001 -> ok" in captured
    assert "[2/2] p002 -> ok" in captured
    assert "chars=" in captured
    assert "eta=" in captured
    assert paths.records_path.exists()
    assert paths.corpus_md_path.exists()
    assert paths.graph_nodes_path.exists()
    assert paths.graph_edges_path.exists()
