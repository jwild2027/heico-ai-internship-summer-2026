from __future__ import annotations

import json
from pathlib import Path

from tiff.page_context_inspector import inspect_page_contexts, load_context_rows


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_context_rows_accepts_contexts_key(tmp_path: Path) -> None:
    path = tmp_path / "page_contexts.json"
    write_json(
        path,
        {
            "contexts": [
                {
                    "page_id": "p1",
                    "page_role": "parts_list",
                    "confidence": "high",
                    "short_summary": "Parts page.",
                    "topics": ["parts"],
                    "important_parts": ["ABC-1"],
                }
            ]
        },
    )
    rows = load_context_rows(path)
    assert len(rows) == 1
    assert rows[0].page_id == "p1"
    assert rows[0].page_role == "parts_list"
    assert rows[0].topics == ("parts",)


def test_inspection_counts_warnings_roles_and_topics(tmp_path: Path) -> None:
    context_path = tmp_path / "page_contexts.json"
    graph_path = tmp_path / "graph_summary.json"
    write_json(
        context_path,
        [
            {
                "page_id": "p1",
                "role": "parts_list",
                "confidence": "high",
                "summary": "Parts page.",
                "topics": ["parts", "manual"],
                "important_parts": ["ABC-1"],
            },
            {
                "page_id": "p2",
                "role": "blank",
                "confidence": "low",
                "summary": "Blank page.",
                "warnings": ["empty_ocr"],
            },
        ],
    )
    write_json(
        graph_path,
        {
            "node_types": {"page_context": 2},
            "edge_types": {"HAS_CONTEXT": 2, "TAGGED_AS": 2, "HIGHLIGHTS_PART": 1},
        },
    )
    result = inspect_page_contexts(context_path, graph_path, strict=True)
    assert result.status == "OK"
    assert result.total_contexts == 2
    assert result.contexts_with_warnings == 1
    assert result.role_counts["parts_list"] == 1
    assert result.role_counts["blank"] == 1
    assert result.topic_counts["parts"] == 1
    assert result.graph_has_context_edges == 2


def test_strict_fails_missing_context_file(tmp_path: Path) -> None:
    result = inspect_page_contexts(tmp_path / "missing.json", None, strict=True)
    assert result.status == "FAIL"
    assert result.issues


def test_filters_selected_contexts(tmp_path: Path) -> None:
    context_path = tmp_path / "page_contexts.json"
    write_json(
        context_path,
        [
            {"page_id": "p1", "role": "procedure", "summary": "Repair page", "topics": ["repair"]},
            {"page_id": "p2", "role": "parts_list", "summary": "Parts page", "topics": ["parts"]},
        ],
    )
    result = inspect_page_contexts(context_path, None, roles=["procedure"], topics=["repair"], strict=False)
    assert result.status == "OK"
    assert len(result.selected_contexts) == 1
    assert result.selected_contexts[0]["page_id"] == "p1"


def test_inspection_reads_nested_graph_counts(tmp_path: Path) -> None:
    context_path = tmp_path / "page_contexts.json"
    graph_path = tmp_path / "graph_summary.json"
    write_json(context_path, [{"page_id": "p1", "role": "parts_list", "summary": "Parts page."}])
    write_json(
        graph_path,
        {
            "graph_counts": {
                "node_types": {"page_context": 1},
                "edge_types": {"HAS_CONTEXT": 1, "TAGGED_AS": 2, "HIGHLIGHTS_PART": 3},
            }
        },
    )

    result = inspect_page_contexts(context_path, graph_path, strict=True)

    assert result.status == "OK"
    assert result.graph_page_context_nodes == 1
    assert result.graph_has_context_edges == 1
    assert result.graph_tagged_as_edges == 2
    assert result.graph_highlights_part_edges == 3
