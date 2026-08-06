from __future__ import annotations

import json
from pathlib import Path

from tiff.entity_trait_graph import build_entity_trait_overlay, export_entity_trait_overlay


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_graph(tmp_path: Path) -> tuple[Path, Path, Path]:
    graph_dir = tmp_path / "graph"
    image_audit = tmp_path / "image" / "page_image_recognition_audit.json"
    visual_audit = tmp_path / "visual" / "page_visual_objects_audit.json"

    nodes = [
        {
            "id": "document:doc1",
            "type": "document",
            "label": "Manual One",
            "properties": {"manual_id": "doc1", "title": "Manual One"},
        },
        {
            "id": "ata_section:doc1_25_21_00",
            "type": "ata_section",
            "label": "ATA 25-21-00",
            "properties": {"ata_code": "25-21-00", "manual_id": "doc1"},
        },
        {
            "id": "page:doc1_p001",
            "type": "page",
            "label": "Manual One page 1",
            "properties": {
                "page_id": "doc1_p001",
                "page_label": "1",
                "manual_id": "doc1",
                "ata_code": "25-21-00",
                "source_url": "http://source/1",
                "tiff_path": "pages/001.tif",
                "ocr_path": "ocr/001.txt",
            },
        },
        {
            "id": "source_link:doc1_p001",
            "type": "source_link",
            "label": "source for doc1_p001",
            "properties": {"source_url": "http://source/1"},
        },
        {
            "id": "source_file:tiff_pages_001_tif",
            "type": "source_file",
            "label": "001.tif",
            "properties": {"role": "tiff", "path": "pages/001.tif"},
        },
        {
            "id": "source_file:ocr_001_txt",
            "type": "source_file",
            "label": "001.txt",
            "properties": {"role": "ocr", "path": "ocr/001.txt", "empty": False},
        },
        {
            "id": "page_context:doc1_p001",
            "type": "page_context",
            "label": "parts list for magazine holder",
            "properties": {
                "page_id": "doc1_p001",
                "short_summary": "Parts list for magazine holder.",
                "page_role": "parts_list",
                "topics": ["magazine holder"],
                "important_parts": ["120-37313-001"],
                "confidence": 0.95,
            },
        },
        {
            "id": "part:120_37313_001",
            "type": "part",
            "label": "120-37313-001",
            "properties": {"part_number": "120-37313-001", "nomenclature": "HOLDER, MAGAZINE"},
        },
        {
            "id": "nomenclature:holder_magazine",
            "type": "nomenclature",
            "label": "HOLDER, MAGAZINE",
            "properties": {"text": "HOLDER, MAGAZINE"},
        },
        {
            "id": "part_mention:120_37313_001_doc1_p001",
            "type": "part_mention",
            "label": "120-37313-001 on doc1_p001",
            "properties": {"part_number": "120-37313-001", "page_id": "doc1_p001"},
        },
    ]
    edges = [
        {"id": "e1", "type": "HAS_PAGE", "from": "document:doc1", "to": "page:doc1_p001"},
        {"id": "e2", "type": "BELONGS_TO_DOCUMENT", "from": "page:doc1_p001", "to": "document:doc1"},
        {"id": "e3", "type": "HAS_ATA_SECTION", "from": "document:doc1", "to": "ata_section:doc1_25_21_00"},
        {"id": "e4", "type": "BELONGS_TO_ATA", "from": "page:doc1_p001", "to": "ata_section:doc1_25_21_00"},
        {"id": "e5", "type": "CONTAINS_PAGE", "from": "ata_section:doc1_25_21_00", "to": "page:doc1_p001"},
        {"id": "e6", "type": "HAS_SOURCE_LINK", "from": "page:doc1_p001", "to": "source_link:doc1_p001"},
        {"id": "e7", "type": "HAS_TIFF", "from": "page:doc1_p001", "to": "source_file:tiff_pages_001_tif"},
        {"id": "e8", "type": "HAS_OCR", "from": "page:doc1_p001", "to": "source_file:ocr_001_txt"},
        {"id": "e9", "type": "HAS_CONTEXT", "from": "page:doc1_p001", "to": "page_context:doc1_p001"},
        {"id": "e10", "type": "APPEARS_ON", "from": "part:120_37313_001", "to": "page:doc1_p001"},
        {"id": "e11", "type": "MENTIONS_PART", "from": "page:doc1_p001", "to": "part:120_37313_001"},
        {"id": "e12", "type": "HAS_NOMENCLATURE", "from": "part:120_37313_001", "to": "nomenclature:holder_magazine"},
    ]
    write_json(graph_dir / "graph_nodes.json", {"nodes": nodes})
    write_json(graph_dir / "graph_edges.json", {"edges": edges})
    write_json(
        image_audit,
        {
            "summary": {"status": "OK", "pages_checked": 1},
            "records": [
                {
                    "page_id": "doc1_p001",
                    "readable": True,
                    "classification": "likely_table_or_grid",
                    "ink_ratio": 0.07,
                    "large_components": 12,
                    "confidence": 0.9,
                    "image_path": "pages/001.tif",
                }
            ],
        },
    )
    write_json(
        visual_audit,
        {
            "records": [
                {
                    "page_id": "doc1_p001",
                    "page_role": "parts_list",
                    "has_figure_ref": True,
                    "has_table_ref": True,
                }
            ]
        },
    )
    return graph_dir, image_audit, visual_audit


def test_build_entity_trait_overlay_adds_assertions_traits_and_cards(tmp_path: Path) -> None:
    graph_dir, image_audit, visual_audit = make_graph(tmp_path)

    result = build_entity_trait_overlay(graph_dir, image_audit, visual_audit)

    assert result.status == "OK"
    node_types = result.summary["overlay_counts"]["node_types"]
    edge_types = result.summary["overlay_counts"]["edge_types"]
    assert node_types["trait"] >= 1
    assert node_types["trait_assertion"] >= 1
    assert node_types["evidence_source"] >= 1
    assert edge_types["HAS_TRAIT_ASSERTION"] >= 1
    assert edge_types["ASSERTS_TRAIT"] >= 1
    assert edge_types["DERIVED_FROM"] >= 1
    assert edge_types["HAS_TRAIT"] >= 1
    assert edge_types["INHERITS_TRAITS_FROM"] == 2

    page_card = result.page_cards[0]
    assert page_card["page_id"] == "doc1_p001"
    assert "quality:fully_traceable_page=true" in page_card["derived_traits"]
    assert "quality:high_confidence_parts_list_page=true" in page_card["derived_traits"]
    assert "context:page_role=parts_list" in page_card["direct_traits"]
    assert "image_recognition:image_class=likely_table_or_grid" in page_card["direct_traits"]
    assert page_card["source"]["tiff_path"] == "pages/001.tif"
    assert page_card["parts"] == ["120-37313-001"]

    part_card = result.part_cards[0]
    assert part_card["part_number"] == "120-37313-001"
    assert "quality:high_confidence_part=true" in part_card["derived_traits"]


def test_export_entity_trait_overlay_writes_expected_files(tmp_path: Path) -> None:
    graph_dir, image_audit, visual_audit = make_graph(tmp_path)
    output_dir = tmp_path / "entity_traits"

    result = export_entity_trait_overlay(graph_dir, output_dir, image_audit, visual_audit)

    assert result.status == "OK"
    assert (output_dir / "entity_traits.json").exists()
    assert (output_dir / "trait_graph_nodes.json").exists()
    assert (output_dir / "trait_graph_edges.json").exists()
    assert (output_dir / "page_character_cards.json").exists()
    assert (output_dir / "part_character_cards.json").exists()
    assert (output_dir / "trait_graph_summary.json").exists()
    assertions = json.loads((output_dir / "entity_traits.json").read_text(encoding="utf-8"))["assertions"]
    assert any(item["trait_key"] == "fully_traceable_page" for item in assertions)


def test_missing_graph_reports_needs_attention(tmp_path: Path) -> None:
    result = build_entity_trait_overlay(tmp_path / "missing", image_audit_path=None, page_visual_audit_path=None)

    assert result.status == "NEEDS_ATTENTION"
    assert result.warnings
