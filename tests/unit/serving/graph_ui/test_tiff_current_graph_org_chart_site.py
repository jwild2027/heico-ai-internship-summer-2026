from __future__ import annotations

from pathlib import Path

import pytest

from tiff.graph_org_chart_site import OrgChartPaths, build_and_write_org_chart_site


@pytest.mark.skipif(
    not Path("local_data/organization/entity_traits/page_character_cards.json").exists()
    and not Path("local_data/organization/export/page_index.json").exists(),
    reason="local graph artifacts are ignored and not available in this checkout",
)
def test_current_509_page_graph_org_chart_site_builds(capsys: pytest.CaptureFixture[str]) -> None:
    report = build_and_write_org_chart_site(OrgChartPaths())
    summary = report["summary"]
    print("\nCurrent interactive graph org-chart site")
    print(f"  Status: {report['status']}")
    print(f"  Documents: {summary.get('documents')}")
    print(f"  ATA sections: {summary.get('ata_sections')}")
    print(f"  Pages: {summary.get('pages')}")
    print(f"  Parts: {summary.get('parts')}")
    print(f"  Graph nodes: {summary.get('graph_nodes')}")
    print(f"  Graph edges: {summary.get('graph_edges')}")
    print(f"  Trait assertions: {summary.get('trait_assertions')}")
    print("  Files:")
    for label, path in report["files"].items():
        print(f"    {label}: {path}")
    assert report["status"] == "ok"
    assert summary.get("documents") == 1
    assert summary.get("pages") == 509
    assert Path(report["files"]["index"]).exists()
