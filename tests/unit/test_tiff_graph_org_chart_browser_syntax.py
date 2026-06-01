from __future__ import annotations

from pathlib import Path

from tiff.graph_org_chart_site import write_org_chart_site


def test_generated_org_chart_html_esc_attr_is_browser_safe(tmp_path: Path) -> None:
    data = {
        "status": "ok",
        "summary": {"documents": 1, "ata_sections": 1, "pages": 1, "parts": 0, "graph_nodes": 1, "graph_edges": 0, "trait_assertions": 0, "trait_nodes": 0},
        "counts": {"roles": {"figure": 1}, "ata_sections": {"25-21-00": 1}, "derived_traits": {}, "image_classes": {}},
        "quality": {},
        "documents": [
            {
                "document_id": "doc'with\\slash",
                "title": "Manual A",
                "page_count": 1,
                "part_count": 0,
                "role_counts": {"figure": 1},
                "ata_sections": [
                    {
                        "ata_code": "25-21-00",
                        "title": "Equipment",
                        "page_count": 1,
                        "part_count": 0,
                        "role_counts": {"figure": 1},
                        "pages": [
                            {
                                "page_id": "page'with\\slash",
                                "document": "Manual A",
                                "document_id": "doc'with\\slash",
                                "ata_code": "25-21-00",
                                "page_label": "1",
                                "role": "figure",
                                "parts": [],
                                "source": {},
                                "direct_traits": [],
                                "derived_traits": [],
                                "image_classes": [],
                                "summary": "Figure page",
                                "signals": {},
                            }
                        ],
                    }
                ],
            }
        ],
        "pages": [],
        "parts": [],
        "artifact_paths": {},
    }

    files = write_org_chart_site(data, tmp_path / "site")
    html = Path(files["index"]).read_text(encoding="utf-8")

    assert "String.fromCharCode(92)" in html
    assert "replace(/\\/g" not in html
    assert "function escAttr(value)" in html
