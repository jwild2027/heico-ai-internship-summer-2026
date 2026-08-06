from __future__ import annotations

import json
from pathlib import Path

from tiff.graph_visualization import export_graph_visualizations, format_graph_visualization_result


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_export_graph_visualizations_writes_html_files(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graph"
    trait_dir = tmp_path / "entity_traits"
    out_dir = tmp_path / "visualizations"

    _write(
        graph_dir / "graph_nodes.json",
        {
            "nodes": [
                {"id": "document:tp120", "type": "document", "label": "T.P. 120/1176"},
                {"id": "ata:25-21-00", "type": "ata_section", "properties": {"ata_code": "25-21-00"}},
                {"id": "page:p000001", "type": "page", "properties": {"page_id": "p000001"}},
                {"id": "page_context:p000001", "type": "page_context", "properties": {"page_role": "parts_list"}},
                {"id": "source_link:p000001", "type": "source_link"},
            ]
        },
    )
    _write(
        graph_dir / "graph_edges.json",
        {
            "edges": [
                {"type": "BELONGS_TO_DOCUMENT", "from": "page:p000001", "to": "document:tp120"},
                {"type": "BELONGS_TO_ATA", "from": "page:p000001", "to": "ata:25-21-00"},
                {"type": "HAS_CONTEXT", "from": "page:p000001", "to": "page_context:p000001"},
                {"type": "HAS_SOURCE_LINK", "from": "page:p000001", "to": "source_link:p000001"},
            ]
        },
    )
    _write(
        trait_dir / "page_character_cards.json",
        {
            "pages": [
                {
                    "entity_id": "page:p000001",
                    "entity_type": "page",
                    "page_id": "p000001",
                    "label": "Page 1",
                    "parents": {"document_label": "T.P. 120/1176", "ata_code": "25-21-00"},
                    "source": {"source_url": "local://p000001", "tiff_path": "p000001.tif", "ocr_path": "p000001.txt"},
                    "context": {"page_role": "parts_list", "summary": "Parts list page", "topics": ["seat"]},
                    "signals": {"image_classification": "likely_table_or_grid", "ink_ratio": 0.07, "large_components": 12},
                    "parts": ["120-37313-001"],
                    "direct_traits": ["context:page_role=parts_list"],
                    "derived_traits": ["quality:answer_ready_page=true"],
                    "traits": ["context:page_role=parts_list", "quality:answer_ready_page=true"],
                }
            ]
        },
    )
    _write(
        trait_dir / "part_character_cards.json",
        {
            "parts": [
                {
                    "entity_id": "part:120-37313-001",
                    "part_number": "120-37313-001",
                    "nomenclature": "HOLDER, MAGAZINE",
                    "page_count": 1,
                }
            ]
        },
    )
    _write(
        trait_dir / "entity_traits.json",
        {
            "assertions": [
                {
                    "entity_id": "page:p000001",
                    "entity_type": "page",
                    "trait_type": "context",
                    "trait_key": "page_role",
                    "trait_value": "parts_list",
                    "scope": "direct",
                },
                {
                    "entity_id": "page:p000001",
                    "entity_type": "page",
                    "trait_type": "quality",
                    "trait_key": "answer_ready_page",
                    "trait_value": "true",
                    "scope": "derived",
                },
            ]
        },
    )
    _write(
        trait_dir / "trait_graph_summary.json",
        {
            "status": "ok",
            "overlay_counts": {
                "nodes": 8,
                "edges": 12,
                "assertions": 2,
                "trait_nodes": 2,
                "trait_assertion_nodes": 2,
                "evidence_source_nodes": 1,
                "derived_assertions": 1,
                "page_cards": 1,
                "part_cards": 1,
            },
        },
    )

    result = export_graph_visualizations(graph_dir=graph_dir, trait_dir=trait_dir, output_dir=out_dir, sample_limit=1)

    assert result.status == "ok"
    assert result.summary["processed_corpus"]["pages"] == 1
    assert result.summary["processed_corpus"]["documents"] == 1
    assert Path(result.files["index"]).exists()
    assert Path(result.files["page_grid"]).exists()
    assert Path(result.files["trait_overlay"]).exists()
    assert Path(result.files["neighborhoods"]).exists()

    page_grid = Path(result.files["page_grid"]).read_text(encoding="utf-8")
    assert "p000001" in page_grid
    assert "parts_list" in page_grid
    assert "120-37313-001" in page_grid

    text = format_graph_visualization_result(result)
    assert "Current graph visualizations" in text
    assert "pages: 1" in text
    assert "index:" in text


def test_export_graph_visualizations_falls_back_to_graph_pages(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graph"
    trait_dir = tmp_path / "missing_traits"
    out_dir = tmp_path / "visualizations"

    _write(
        graph_dir / "graph_nodes.json",
        {
            "nodes": [
                {"id": "document:tp120", "type": "document", "label": "T.P. 120/1176"},
                {"id": "ata:25-21-00", "type": "ata_section", "properties": {"ata_code": "25-21-00"}},
                {"id": "page:p000002", "type": "page", "properties": {"page_id": "p000002"}},
                {"id": "page_context:p000002", "type": "page_context", "properties": {"page_role": "blank"}},
            ]
        },
    )
    _write(
        graph_dir / "graph_edges.json",
        {
            "edges": [
                {"type": "BELONGS_TO_DOCUMENT", "from": "page:p000002", "to": "document:tp120"},
                {"type": "BELONGS_TO_ATA", "from": "page:p000002", "to": "ata:25-21-00"},
                {"type": "HAS_CONTEXT", "from": "page:p000002", "to": "page_context:p000002"},
            ]
        },
    )

    result = export_graph_visualizations(graph_dir=graph_dir, trait_dir=trait_dir, output_dir=out_dir)

    assert result.status == "ok"
    assert result.summary["processed_corpus"]["pages"] == 1
    assert result.warnings
    assert "p000002" in Path(result.files["page_grid"]).read_text(encoding="utf-8")
