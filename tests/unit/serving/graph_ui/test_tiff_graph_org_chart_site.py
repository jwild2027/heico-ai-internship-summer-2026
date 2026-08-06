from __future__ import annotations

import json
from pathlib import Path

from tiff.graph_org_chart_site import OrgChartPaths, build_org_chart_data, write_org_chart_site


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_build_org_chart_data_from_page_character_cards(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    graph_dir = tmp_path / "graph"
    trait_dir = tmp_path / "traits"
    image_dir = tmp_path / "image"
    org_dir = tmp_path / "org"

    _write(
        trait_dir / "page_character_cards.json",
        [
            {
                "page_id": "page:doc_a_p000001",
                "document": "Manual A",
                "document_id": "doc_a",
                "ata_code": "25-21-00",
                "page_label": "1",
                "roles": {"context_role": "parts_list", "image_class": ["likely_table_or_grid"]},
                "source": {"source_url": "file:///page1.tif", "tiff_path": "page1.tif", "ocr_path": "page1.txt"},
                "parts": [{"part_number": "120-0001", "nomenclature": "TEST PART"}],
                "direct_traits": ["structure:entity_kind=page"],
                "derived_traits": ["quality:answer_ready_page=true", "quality:high_confidence_parts_list_page=true"],
                "summary": "A parts list page.",
            },
            {
                "page_id": "page:doc_a_p000002",
                "document": "Manual A",
                "document_id": "doc_a",
                "ata_code": "25-21-00",
                "page_label": "2",
                "role": "blank",
                "traits": ["visual:likely_blank=true"],
                "derived": ["quality:verified_blank_page=true"],
            },
        ],
    )
    _write(
        trait_dir / "part_character_cards.json",
        [
            {"part_number": "120-0001", "nomenclature": "TEST PART", "pages": ["doc_a_p000001"]},
            {"part_number": "120-0002", "nomenclature": "OTHER PART", "pages": []},
        ],
    )
    _write(trait_dir / "trait_graph_summary.json", {"status": "ok", "assertions": 8, "trait_nodes": 4})
    _write(graph_dir / "graph_nodes.json", [{"node_type": "page"}, {"node_type": "page_context"}])
    _write(graph_dir / "graph_edges.json", [{"edge_type": "HAS_CONTEXT"}])
    _write(image_dir / "page_image_recognition_quality.json", {"status": "OK", "summary": {"page_image_pages_checked": 2}})
    _write(org_dir / "page_visual_object_quality.json", {"status": "OK", "summary": {"page_visual_pages_checked": 2}})
    _write(export_dir / "organization_summary.json", {"status": "ok", "summary": {"pages": 2}})

    data = build_org_chart_data(
        OrgChartPaths(
            export_dir=export_dir,
            graph_dir=graph_dir,
            trait_dir=trait_dir,
            image_recognition_dir=image_dir,
            organization_dir=org_dir,
            output_dir=tmp_path / "site",
        )
    )

    assert data["status"] == "ok"
    assert data["summary"]["documents"] == 1
    assert data["summary"]["pages"] == 2
    assert data["summary"]["parts"] == 2
    assert data["summary"]["graph_nodes"] == 2
    assert data["summary"]["trait_assertions"] == 8
    assert data["counts"]["roles"]["parts_list"] == 1
    assert data["counts"]["roles"]["blank"] == 1
    assert data["documents"][0]["ata_sections"][0]["ata_code"] == "25-21-00"
    assert data["pages"][0]["parts"][0]["part_number"] == "120-0001"


def test_write_org_chart_site_contains_embedded_graph_data(tmp_path: Path) -> None:
    data = {
        "status": "ok",
        "summary": {"documents": 1, "ata_sections": 1, "pages": 1, "parts": 1, "graph_nodes": 2, "graph_edges": 1, "trait_assertions": 3, "trait_nodes": 2},
        "counts": {"roles": {"figure": 1}, "ata_sections": {"25-21-00": 1}, "derived_traits": {"quality:answer_ready_page=true": 1}, "image_classes": {"likely_figure_or_diagram": 1}},
        "quality": {},
        "documents": [
            {
                "document_id": "doc_a",
                "title": "Manual A",
                "page_count": 1,
                "part_count": 1,
                "role_counts": {"figure": 1},
                "ata_sections": [
                    {
                        "ata_code": "25-21-00",
                        "title": "Equipment",
                        "page_count": 1,
                        "part_count": 1,
                        "role_counts": {"figure": 1},
                        "pages": [
                            {
                                "page_id": "doc_a_p000001",
                                "document": "Manual A",
                                "document_id": "doc_a",
                                "ata_code": "25-21-00",
                                "page_label": "1",
                                "role": "figure",
                                "parts": [{"part_number": "ABC-1"}],
                                "source": {"source_url": "file:///page1.tif"},
                                "direct_traits": [],
                                "derived_traits": ["quality:answer_ready_page=true"],
                                "image_classes": ["likely_figure_or_diagram"],
                                "summary": "Figure page",
                                "signals": {},
                            }
                        ],
                    }
                ],
            }
        ],
        "pages": [],
        "parts": [{"part_number": "ABC-1", "pages": ["doc_a_p000001"]}],
        "artifact_paths": {},
    }

    files = write_org_chart_site(data, tmp_path / "site")
    index = Path(files["index"])
    assert index.exists()
    html = index.read_text(encoding="utf-8")
    assert "HEICO Graph Org Chart Viewer" in html
    assert "window.HEICO_GRAPH_DATA" in html
    assert "Manual A" in html
    assert "doc_a_p000001" in html
    assert Path(files["data_json"]).exists()
    assert Path(files["summary_json"]).exists()


def test_page_index_fallback_when_character_cards_are_missing(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    graph_dir = tmp_path / "graph"
    trait_dir = tmp_path / "traits"
    image_dir = tmp_path / "image"
    org_dir = tmp_path / "org"
    _write(
        export_dir / "page_index.json",
        {
            "pages": {
                "p1": {"page_id": "p1", "manual": "Manual Fallback", "ata_code": "11-00-66", "page_role": "front_matter"},
                "p2": {"page_id": "p2", "manual": "Manual Fallback", "ata_code": "11-00-66", "page_role": "figure"},
            }
        },
    )
    _write(graph_dir / "graph_nodes.json", [])
    _write(graph_dir / "graph_edges.json", [])

    data = build_org_chart_data(
        OrgChartPaths(
            export_dir=export_dir,
            graph_dir=graph_dir,
            trait_dir=trait_dir,
            image_recognition_dir=image_dir,
            organization_dir=org_dir,
            output_dir=tmp_path / "site",
        )
    )

    assert data["status"] == "ok"
    assert data["summary"]["pages"] == 2
    assert data["counts"]["roles"]["front_matter"] == 1
    assert data["documents"][0]["title"] == "Manual Fallback"
