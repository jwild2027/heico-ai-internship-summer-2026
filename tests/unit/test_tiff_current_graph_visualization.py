from __future__ import annotations

from pathlib import Path

import pytest

from tiff.graph_visualization import export_graph_visualizations, format_graph_visualization_result


def test_current_509_page_graph_visualization_outputs_printable_summary() -> None:
    graph_dir = Path("local_data/organization/graph")
    trait_dir = Path("local_data/organization/entity_traits")
    if not (graph_dir / "graph_nodes.json").exists() or not (graph_dir / "graph_edges.json").exists():
        pytest.skip("local graph artifacts are not present")
    if not (trait_dir / "page_character_cards.json").exists():
        pytest.skip("entity-trait page character cards are not present; run scripts/export_entity_trait_graph.py first")

    result = export_graph_visualizations(
        graph_dir=graph_dir,
        trait_dir=trait_dir,
        output_dir="local_data/organization/visualizations",
        sample_limit=12,
    )
    print("\n" + format_graph_visualization_result(result))

    assert result.status == "ok"
    assert result.summary["processed_corpus"]["documents"] == 1
    assert result.summary["processed_corpus"]["pages"] == 509
    assert result.summary["trait_overlay"]["page_cards"] == 509
    assert Path(result.files["index"]).exists()
    assert Path(result.files["page_grid"]).exists()
