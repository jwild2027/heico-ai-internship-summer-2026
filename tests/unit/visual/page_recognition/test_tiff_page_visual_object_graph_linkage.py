from __future__ import annotations

import json
from pathlib import Path

from tiff.page_visual_object_audit import _load_graph_counts


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_graph_counts_from_nested_summary(tmp_path: Path) -> None:
    path = tmp_path / "graph_summary.json"
    _write(
        path,
        {
            "status": "OK",
            "summary": {
                "node_type_counts": {"page": 509, "page_context": 509},
                "edge_type_counts": {"HAS_CONTEXT": 509, "TAGGED_AS": 1706, "HIGHLIGHTS_PART": 1070},
            },
        },
    )
    counts = _load_graph_counts(path)
    assert counts["page_context_nodes"] == 509
    assert counts["has_context_edges"] == 509
    assert counts["tagged_as_edges"] == 1706
    assert counts["highlights_part_edges"] == 1070


def test_load_graph_counts_from_type_count_lists(tmp_path: Path) -> None:
    path = tmp_path / "graph_summary.json"
    _write(
        path,
        {
            "nodes_by_type": [{"type": "page_context", "count": 12}],
            "edges_by_type": [
                {"type": "HAS_CONTEXT", "count": 12},
                {"type": "TAGGED_AS", "count": 30},
                {"type": "HIGHLIGHTS_PART", "count": 8},
            ],
        },
    )
    counts = _load_graph_counts(path)
    assert counts["page_context_nodes"] == 12
    assert counts["has_context_edges"] == 12
    assert counts["tagged_as_edges"] == 30
    assert counts["highlights_part_edges"] == 8
