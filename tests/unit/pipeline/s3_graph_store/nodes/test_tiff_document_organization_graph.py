from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiff.document_organization_graph import build_graph_from_export, export_graph


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_export(tmp_path: Path) -> Path:
    export_dir = tmp_path / "export"
    write_json(
        export_dir / "organization_summary.json",
        {"manuals": 1, "pages": 2, "parts": 1, "part_mentions": 1},
    )
    write_json(
        export_dir / "page_index.json",
        {
            "pages": [
                {
                    "page_id": "doc1_p001",
                    "manual_id": "doc1",
                    "manual": "Manual One",
                    "ata_code": "25-21-00",
                    "page_label": "1",
                    "source_url": "http://source/1",
                    "tiff_path": "pages/001.tif",
                    "ocr_path": "ocr/001.txt",
                },
                {
                    "page_id": "doc1_p002",
                    "manual_id": "doc1",
                    "manual": "Manual One",
                    "ata_code": "25-21-00",
                    "page_label": "2",
                    "source_url": "http://source/2",
                    "tiff_path": "pages/002.tif",
                    "ocr_path": "ocr/002.txt",
                    "empty_ocr": True,
                },
            ]
        },
    )
    write_json(
        export_dir / "part_tree.json",
        {
            "parts": [
                {
                    "part_number": "120-37313-001",
                    "nomenclature": "HOLDER, MAGAZINE",
                    "page_count": 1,
                    "mention_count": 1,
                    "pages": [
                        {
                            "page_id": "doc1_p001",
                            "source_url": "http://source/1",
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        export_dir / "ata_tree.json",
        {
            "ata_groups": [
                {
                    "ata_code": "25-21-00",
                    "manual_id": "doc1",
                    "manual": "Manual One",
                    "page_count": 2,
                    "part_count": 1,
                }
            ]
        },
    )
    write_json(export_dir / "manual_ata_tree.json", {"manuals": [{"manual_id": "doc1", "manual": "Manual One"}]})
    return export_dir


def test_build_graph_contains_expected_nodes_and_edges(tmp_path: Path) -> None:
    export_dir = make_export(tmp_path)
    result = build_graph_from_export(export_dir, strict=True)

    assert result.status == "OK"
    node_types = result.summary["graph_counts"]["node_types"]
    edge_types = result.summary["graph_counts"]["edge_types"]

    assert node_types["document"] == 1
    assert node_types["page"] == 2
    assert node_types["ata_section"] == 1
    assert node_types["part"] == 1
    assert node_types["part_mention"] == 1
    assert node_types["source_link"] == 2
    assert node_types["source_file"] == 4

    assert edge_types["HAS_PAGE"] == 2
    assert edge_types["BELONGS_TO_ATA"] == 2
    assert edge_types["MENTIONS_PART"] == 1
    assert edge_types["HAS_TIFF"] == 2
    assert edge_types["HAS_OCR"] == 2
    assert edge_types["OPENS"] == 2


def test_export_graph_writes_three_files(tmp_path: Path) -> None:
    export_dir = make_export(tmp_path)
    output_dir = tmp_path / "graph"
    result = export_graph(export_dir, output_dir, strict=True)

    assert result.status == "OK"
    assert (output_dir / "graph_nodes.json").exists()
    assert (output_dir / "graph_edges.json").exists()
    assert (output_dir / "graph_summary.json").exists()

    nodes = json.loads((output_dir / "graph_nodes.json").read_text(encoding="utf-8"))["nodes"]
    edges = json.loads((output_dir / "graph_edges.json").read_text(encoding="utf-8"))["edges"]
    assert any(node["type"] == "part" for node in nodes)
    assert any(edge["type"] == "APPEARS_ON" for edge in edges)


def test_strict_mode_requires_page_index(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    write_json(export_dir / "organization_summary.json", {})
    write_json(export_dir / "part_tree.json", {"parts": []})
    write_json(export_dir / "ata_tree.json", {"ata_groups": []})
    write_json(export_dir / "manual_ata_tree.json", {"manuals": []})

    with pytest.raises(FileNotFoundError):
        build_graph_from_export(export_dir, strict=True)


def test_non_strict_mode_reports_missing_files(tmp_path: Path) -> None:
    result = build_graph_from_export(tmp_path / "missing", strict=False)
    assert result.status == "NEEDS_ATTENTION"
    assert result.warnings
