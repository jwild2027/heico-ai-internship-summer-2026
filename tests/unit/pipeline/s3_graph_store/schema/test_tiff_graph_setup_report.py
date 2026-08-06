from __future__ import annotations

import json
from pathlib import Path

from tiff.graph_setup_report import (
    build_current_graph_setup_report,
    format_current_graph_setup_report,
    write_graph_setup_report_json,
)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_graph_setup_report_summarizes_core_and_trait_overlay(tmp_path: Path) -> None:
    export_dir = tmp_path / "local_data" / "organization" / "export"
    graph_dir = tmp_path / "local_data" / "organization" / "graph"
    trait_dir = tmp_path / "local_data" / "organization" / "entity_traits"
    image_quality = tmp_path / "local_data" / "organization" / "image_recognition" / "page_image_recognition_quality.json"
    visual_quality = tmp_path / "local_data" / "organization" / "page_visual_object_quality.json"

    _write(
        graph_dir / "graph_nodes.json",
        {
            "nodes": [
                {"id": "document:tp_120_1176", "type": "document", "label": "T.P. 120/1176"},
                {"id": "ata_section:tp_120_1176_25_21_00", "type": "ata_section", "label": "ATA 25-21-00"},
                {"id": "page:t_p_120_1176_p000001", "type": "page", "label": "page 1"},
                {"id": "page:t_p_120_1176_p000002", "type": "page", "label": "page 2"},
                {"id": "source_link:t_p_120_1176_p000001", "type": "source_link"},
                {"id": "source_link:t_p_120_1176_p000002", "type": "source_link"},
                {"id": "source_file:tiff_1", "type": "source_file"},
                {"id": "source_file:ocr_1", "type": "source_file"},
                {"id": "page_context:t_p_120_1176_p000001", "type": "page_context"},
                {"id": "part:120_37313_001", "type": "part", "label": "120-37313-001"},
                {"id": "part_mention:120_37313_001_p1", "type": "part_mention"},
            ]
        },
    )
    _write(
        graph_dir / "graph_edges.json",
        {
            "edges": [
                {"id": "e1", "type": "HAS_PAGE", "from": "document:tp_120_1176", "to": "page:t_p_120_1176_p000001"},
                {"id": "e2", "type": "HAS_PAGE", "from": "document:tp_120_1176", "to": "page:t_p_120_1176_p000002"},
                {"id": "e3", "type": "BELONGS_TO_DOCUMENT", "from": "page:t_p_120_1176_p000001", "to": "document:tp_120_1176"},
                {"id": "e4", "type": "BELONGS_TO_DOCUMENT", "from": "page:t_p_120_1176_p000002", "to": "document:tp_120_1176"},
                {"id": "e5", "type": "HAS_ATA_SECTION", "from": "document:tp_120_1176", "to": "ata_section:tp_120_1176_25_21_00"},
                {"id": "e6", "type": "CONTAINS_PAGE", "from": "ata_section:tp_120_1176_25_21_00", "to": "page:t_p_120_1176_p000001"},
                {"id": "e7", "type": "BELONGS_TO_ATA", "from": "page:t_p_120_1176_p000001", "to": "ata_section:tp_120_1176_25_21_00"},
                {"id": "e8", "type": "HAS_SOURCE_LINK", "from": "page:t_p_120_1176_p000001", "to": "source_link:t_p_120_1176_p000001"},
                {"id": "e9", "type": "HAS_SOURCE_LINK", "from": "page:t_p_120_1176_p000002", "to": "source_link:t_p_120_1176_p000002"},
                {"id": "e10", "type": "HAS_TIFF", "from": "page:t_p_120_1176_p000001", "to": "source_file:tiff_1"},
                {"id": "e11", "type": "HAS_OCR", "from": "page:t_p_120_1176_p000001", "to": "source_file:ocr_1"},
                {"id": "e12", "type": "HAS_CONTEXT", "from": "page:t_p_120_1176_p000001", "to": "page_context:t_p_120_1176_p000001"},
                {"id": "e13", "type": "MENTIONS_PART", "from": "page:t_p_120_1176_p000001", "to": "part:120_37313_001"},
                {"id": "e14", "type": "HAS_PART_MENTION", "from": "page:t_p_120_1176_p000001", "to": "part_mention:120_37313_001_p1"},
            ]
        },
    )
    _write(graph_dir / "graph_summary.json", {"status": "OK"})
    _write(export_dir / "page_index.json", {"pages": [{"page_id": "t_p_120_1176_p000001"}, {"page_id": "t_p_120_1176_p000002"}]})
    _write(export_dir / "part_tree.json", {"parts": [{"part_number": "120-37313-001"}]})
    _write(export_dir / "ata_tree.json", {"ata_groups": [{"ata_code": "25-21-00"}]})
    _write(export_dir / "organization_summary.json", {"status": "OK"})

    _write(
        trait_dir / "entity_traits.json",
        {
            "assertions": [
                {
                    "entity_id": "page:t_p_120_1176_p000001",
                    "trait_key": "quality",
                    "trait_value": "answer_ready_page",
                    "assertion_kind": "derived",
                },
                {
                    "entity_id": "page:t_p_120_1176_p000001",
                    "trait_key": "page_role",
                    "trait_value": "parts_list",
                    "assertion_kind": "direct",
                },
            ]
        },
    )
    _write(
        trait_dir / "trait_graph_summary.json",
        {
            "status": "ok",
            "overlay_counts": {
                "nodes": 5,
                "edges": 8,
                "assertions": 2,
                "trait_nodes": 2,
                "trait_assertion_nodes": 2,
                "evidence_source_nodes": 1,
                "derived_assertions": 1,
            },
        },
    )
    _write(trait_dir / "trait_graph_nodes.json", {"nodes": []})
    _write(trait_dir / "trait_graph_edges.json", {"edges": []})
    _write(
        trait_dir / "page_character_cards.json",
        {
            "cards": [
                {
                    "entity_id": "page:t_p_120_1176_p000001",
                    "direct_traits": ["page_role=parts_list"],
                    "derived_traits": ["quality:answer_ready_page=true"],
                }
            ]
        },
    )
    _write(trait_dir / "part_character_cards.json", {"cards": [{"entity_id": "part:120_37313_001"}]})
    _write(image_quality, {"status": "OK", "summary": {"page_image_pages_checked": 2, "page_image_readable_images": 2}})
    _write(visual_quality, {"status": "OK", "summary": {"page_visual_pages_checked": 2, "page_visual_pages_with_context": 1}})

    report = build_current_graph_setup_report(
        export_dir=export_dir,
        graph_dir=graph_dir,
        trait_dir=trait_dir,
        image_quality_path=image_quality,
        visual_quality_path=visual_quality,
        expected_pages=2,
        expected_documents=1,
    )

    assert report["status"] == "OK"
    assert report["processed_corpus"]["documents"] == 1
    assert report["processed_corpus"]["pages"] == 2
    assert report["processed_corpus"]["ata_sections"] == 1
    assert report["processed_corpus"]["parts"] == 1
    assert report["page_coverage"]["belongs_to_document"]["count"] == 2
    assert report["page_coverage"]["has_context"]["count"] == 1
    assert report["trait_overlay"]["assertions"] == 2
    assert report["trait_overlay"]["derived_assertions"] == 1
    assert report["quality_signals"]["image_pages_checked"] == 2

    text = format_current_graph_setup_report(report)
    assert "Current TIFF document graph setup" in text
    assert "Processed corpus:" in text
    assert "Entity-trait overlay:" in text
    assert "Sample page character sheets" in text


def test_graph_setup_report_writes_json(tmp_path: Path) -> None:
    report = {"status": "OK", "processed_corpus": {"pages": 2}}
    output = tmp_path / "report.json"
    path = write_graph_setup_report_json(report, output)
    assert path == output
    assert json.loads(output.read_text(encoding="utf-8"))["processed_corpus"]["pages"] == 2
