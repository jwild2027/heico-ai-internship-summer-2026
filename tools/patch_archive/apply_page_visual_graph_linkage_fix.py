#!/usr/bin/env python
from __future__ import annotations

from pathlib import Path

TARGET = Path("tiff/page_visual_object_audit.py")

NEW_BODY = r'''
def _load_graph_counts(graph_summary: Path | None) -> dict[str, int | None]:
    """Load page-context graph counts from graph_summary.json.

    The graph exporter has used a few JSON shapes while the project evolved:
    direct keys, nested ``summary`` keys, and sometimes type/count lists.  Keep
    this reader deliberately tolerant because this audit is a reporting layer,
    not the source of truth for the graph.
    """
    counts: dict[str, int | None] = {
        "page_context_nodes": None,
        "has_context_edges": None,
        "tagged_as_edges": None,
        "highlights_part_edges": None,
    }
    if graph_summary is None or not graph_summary.exists():
        return counts
    try:
        data = _read_json(graph_summary)
    except Exception:
        return counts

    def _to_int(value: Any) -> int | None:
        if value in (None, "", [], {}):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _type_count_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return {str(k): v for k, v in value.items()}
        if isinstance(value, list):
            out: dict[str, Any] = {}
            for item in value:
                if not isinstance(item, Mapping):
                    continue
                type_name = _first_nonempty(item, "type", "node_type", "edge_type", "name", "label")
                count = _first_nonempty(item, "count", "value", "total", "n")
                if type_name not in (None, "") and count not in (None, ""):
                    out[str(type_name)] = count
            return out
        return {}

    def _find_first_type_counts(value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
        if isinstance(value, Mapping):
            for key in keys:
                if key in value:
                    mapped = _type_count_mapping(value.get(key))
                    if mapped:
                        return mapped
            # Common summary wrapper first, then generic recursive search.
            for key in ("summary", "graph_summary", "counts"):
                if key in value:
                    mapped = _find_first_type_counts(value.get(key), keys)
                    if mapped:
                        return mapped
            for child in value.values():
                mapped = _find_first_type_counts(child, keys)
                if mapped:
                    return mapped
        elif isinstance(value, list):
            for child in value:
                mapped = _find_first_type_counts(child, keys)
                if mapped:
                    return mapped
        return {}

    node_types = _find_first_type_counts(
        data,
        (
            "node_types",
            "node_type_counts",
            "nodes_by_type",
            "node_counts_by_type",
            "by_node_type",
        ),
    )
    edge_types = _find_first_type_counts(
        data,
        (
            "edge_types",
            "edge_type_counts",
            "edges_by_type",
            "edge_counts_by_type",
            "by_edge_type",
        ),
    )

    page_context_nodes = _to_int(node_types.get("page_context"))
    if page_context_nodes is not None:
        counts["page_context_nodes"] = page_context_nodes

    for output_key, edge_type in (
        ("has_context_edges", "HAS_CONTEXT"),
        ("tagged_as_edges", "TAGGED_AS"),
        ("highlights_part_edges", "HIGHLIGHTS_PART"),
    ):
        value = _to_int(edge_types.get(edge_type) or edge_types.get(edge_type.lower()))
        if value is not None:
            counts[output_key] = value

    return counts
'''


def replace_function(text: str, name: str, new_body: str) -> str:
    marker = f"def {name}("
    start = text.find(marker)
    if start == -1:
        raise RuntimeError(f"Could not find function {name!r} in {TARGET}")
    next_marker = "\ndef audit_page_visual_objects("
    end = text.find(next_marker, start)
    if end == -1:
        raise RuntimeError(f"Could not find function boundary after {name!r} in {TARGET}")
    return text[:start] + new_body.lstrip("\n") + text[end:]


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"Missing target file: {TARGET}")
    original = TARGET.read_text(encoding="utf-8")
    updated = replace_function(original, "_load_graph_counts", NEW_BODY)
    if updated == original:
        print("No changes needed.")
    else:
        TARGET.write_text(updated, encoding="utf-8")
        print(f"Patched graph linkage count parser in {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
