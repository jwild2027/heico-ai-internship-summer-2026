from __future__ import annotations

from tiff.trace_net_opensearch_live_loader_v1 import normalize_mapping, smoke_query_body


def test_normalize_mapping_strips_adapter_metadata_for_create_index() -> None:
    mapping = {
        "index_name": "trace_net_safe_search_v1",
        "mappings": {"properties": {"text": {"type": "text"}}},
        "unexpected_adapter_metadata": {"not": "allowed in create-index body"},
    }
    body = normalize_mapping(mapping)
    assert body == {"mappings": {"properties": {"text": {"type": "text"}}}}
    assert "index_name" not in body
    assert "unexpected_adapter_metadata" not in body


def test_table_cell_smoke_query_uses_actual_text_schema_not_only_search_text() -> None:
    body = smoke_query_body("120-50648-001", "table_cell_exact")
    bool_query = body["query"]["bool"]
    assert bool_query["minimum_should_match"] == 1
    assert "filter" not in bool_query
    rendered = str(bool_query["should"])
    assert "table_cell_normalized" in rendered
    assert "table_row_normalized" in rendered
    assert "text" in rendered
    assert "title" in rendered
    assert "search_text" in rendered
    assert "120-50648-001" in rendered


def test_generic_smoke_query_searches_text_title_and_legacy_search_text() -> None:
    body = smoke_query_body("Part family community", "ocr_phrase_exact")
    rendered = str(body)
    assert "text" in rendered
    assert "title" in rendered
    assert "search_text" in rendered
    assert "Part family community" in rendered
