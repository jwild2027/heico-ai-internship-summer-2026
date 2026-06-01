from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.page_image_recognition import (
    analyze_page_image,
    build_image_recognition_graph_overlay,
    load_page_image_sources,
    run_page_image_recognition_audit,
    PageImageSource,
)


def _save_blank(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (300, 400), "white").save(path)


def _save_table(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (300, 400), "white")
    draw = ImageDraw.Draw(img)
    for y in range(40, 360, 40):
        draw.line((20, y, 280, y), fill="black", width=3)
    for x in range(20, 281, 65):
        draw.line((x, 40, x, 360), fill="black", width=3)
    img.save(path)


def _save_figure(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (300, 400), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((50, 80, 250, 260), outline="black", width=5)
    draw.ellipse((80, 120, 220, 240), outline="black", width=5)
    draw.line((40, 320, 260, 320), fill="black", width=3)
    img.save(path)


def test_analyze_blank_table_and_figure(tmp_path: Path) -> None:
    blank = tmp_path / "blank.tif"
    table = tmp_path / "table.tif"
    figure = tmp_path / "figure.tif"
    _save_blank(blank)
    _save_table(table)
    _save_figure(figure)

    blank_rec = analyze_page_image(PageImageSource(page_id="p_blank", image_path=str(blank)), repo_root=tmp_path)
    table_rec = analyze_page_image(PageImageSource(page_id="p_table", image_path=str(table), role="table"), repo_root=tmp_path)
    figure_rec = analyze_page_image(PageImageSource(page_id="p_figure", image_path=str(figure), role="figure"), repo_root=tmp_path)

    assert blank_rec.likely_blank
    assert blank_rec.classification == "likely_blank"
    assert table_rec.likely_table_grid
    assert table_rec.classification == "likely_table_or_grid"
    assert figure_rec.likely_figure_or_diagram


def test_run_audit_from_page_index_and_overlay(tmp_path: Path) -> None:
    export = tmp_path / "export"
    export.mkdir()
    table = tmp_path / "table.tif"
    figure = tmp_path / "figure.tif"
    _save_table(table)
    _save_figure(figure)
    page_index = {
        "pages": [
            {"page_id": "p1", "source_image_path": str(table), "page_label": "1"},
            {"page_id": "p2", "source_image_path": str(figure), "page_label": "2"},
        ]
    }
    (export / "page_index.json").write_text(json.dumps(page_index), encoding="utf-8")
    contexts = {"contexts": [{"page_id": "p1", "role": "table", "summary": "Table page"}, {"page_id": "p2", "role": "figure", "summary": "Figure page"}]}
    context_file = tmp_path / "contexts.json"
    context_file.write_text(json.dumps(contexts), encoding="utf-8")

    sources = load_page_image_sources(export, context_file, repo_root=tmp_path)
    assert len(sources) == 2
    assert sources[0].role == "table"

    summary, records = run_page_image_recognition_audit(export, context_file, repo_root=tmp_path, sample_limit=5)
    assert summary.status == "OK"
    assert summary.pages_checked == 2
    assert summary.images_readable == 2
    assert summary.likely_visual_pages >= 1

    nodes, edges = build_image_recognition_graph_overlay(records)
    assert any(n["type"] == "page_image_analysis" for n in nodes)
    assert any(e["type"] == "HAS_IMAGE_ANALYSIS" for e in edges)
