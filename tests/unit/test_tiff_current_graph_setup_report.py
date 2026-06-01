from __future__ import annotations

from pathlib import Path

import pytest

from tiff.graph_setup_report import build_current_graph_setup_report, format_current_graph_setup_report


def _has_current_local_graph() -> bool:
    return (
        Path("local_data/organization/graph/graph_nodes.json").exists()
        and Path("local_data/organization/graph/graph_edges.json").exists()
    )


def test_print_current_509_page_graph_setup_from_local_artifacts() -> None:
    """Print the real current graph layout when local_data artifacts are present.

    Run with -s to see the report:
        python -m pytest tests/unit/test_tiff_current_graph_setup_report.py -q -s
    """
    if not _has_current_local_graph():
        pytest.skip("local graph artifacts are not present; run the backend graph export first")

    report = build_current_graph_setup_report(
        expected_pages=509,
        expected_documents=1,
        sample_limit=10,
    )

    print("\n" + format_current_graph_setup_report(report, sample_limit=10, top_edge_types=30))

    assert report["status"] == "OK"
    assert report["processed_corpus"]["documents"] == 1
    assert report["processed_corpus"]["pages"] == 509
    assert report["processed_corpus"]["source_link_nodes"] == 509
    assert report["processed_corpus"]["page_context_nodes"] == 509
    assert report["page_coverage"]["belongs_to_document"]["count"] == 509
    assert report["page_coverage"]["belongs_to_ata"]["count"] == 509
    assert report["page_coverage"]["has_source_link"]["count"] == 509
    assert report["page_coverage"]["has_context"]["count"] == 509


def test_print_current_entity_trait_overlay_from_local_artifacts() -> None:
    """Print the trait-overlay summary for the current 509-page corpus."""
    if not _has_current_local_graph():
        pytest.skip("local graph artifacts are not present; run the backend graph export first")
    if not Path("local_data/organization/entity_traits/trait_graph_summary.json").exists():
        pytest.skip("entity-trait overlay artifacts are not present; run scripts/export_entity_trait_graph.py first")

    report = build_current_graph_setup_report(
        expected_pages=509,
        expected_documents=1,
        sample_limit=5,
    )
    trait = report["trait_overlay"]

    print("\nEntity-trait overlay summary")
    print(f"  Status: {trait['status']}")
    print(f"  Nodes: {trait['nodes']}")
    print(f"  Edges: {trait['edges']}")
    print(f"  Assertions: {trait['assertions']}")
    print(f"  Trait nodes: {trait['trait_nodes']}")
    print(f"  Trait assertion nodes: {trait['trait_assertion_nodes']}")
    print(f"  Evidence source nodes: {trait['evidence_source_nodes']}")
    print(f"  Derived assertions: {trait['derived_assertions']}")
    print(f"  Page cards: {trait['page_cards']}")
    print(f"  Part cards: {trait['part_cards']}")
    print(f"  Pages without traits: {trait['pages_without_traits']}")
    print("  Trait categories:")
    for key, value in list(trait.get("trait_categories", {}).items())[:20]:
        print(f"    {key}: {value}")

    assert trait["present"] is True
    assert trait["assertions"] >= 1
    assert trait["page_cards"] == 509
    assert trait["part_cards"] == 386
    assert trait["pages_without_traits"] == 0
