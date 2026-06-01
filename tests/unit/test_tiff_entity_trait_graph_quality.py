from __future__ import annotations

from pathlib import Path

from tiff.entity_trait_graph import export_entity_trait_overlay
from tiff.entity_trait_graph_quality import build_entity_trait_quality_result

from tests.unit.test_tiff_entity_trait_graph import make_graph


def test_entity_trait_quality_passes_for_exported_overlay(tmp_path: Path) -> None:
    graph_dir, image_audit, visual_audit = make_graph(tmp_path)
    output_dir = tmp_path / "entity_traits"
    export_entity_trait_overlay(graph_dir, output_dir, image_audit, visual_audit)

    result = build_entity_trait_quality_result(output_dir)

    assert result.status == "ok"
    assert result.summary["entity_trait_assertions"] >= 1
    assert result.summary["entity_trait_page_cards"] == 1
    assert result.summary["entity_trait_derived_assertions"] >= 1


def test_entity_trait_quality_fails_when_missing(tmp_path: Path) -> None:
    result = build_entity_trait_quality_result(tmp_path / "missing")

    assert result.status == "fail"
    assert result.summary["entity_trait_assertions"] == 0
