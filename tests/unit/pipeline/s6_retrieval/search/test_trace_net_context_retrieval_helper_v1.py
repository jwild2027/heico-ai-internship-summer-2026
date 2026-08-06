from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_context_retrieval_helper_v1 import (
    SCHEMA_VERSION,
    build_helper_bundle,
    build_helper_record,
    build_helper_records,
    expected_page_id_aliases,
    extract_page_number,
    load_helper_records_from_path,
    parse_page_range,
    required_page_coverage,
    sha256_json,
    write_helper_outputs,
)


def make_row(page: int) -> dict:
    return {
        "context_id": f"ctx-{page}",
        "page_id": f"t_p_120_1176_p{page:06d}",
        "role": "parts catalog page",
        "summary": f"Page {page} summarizes manual content.",
        "retrieval_cues": [f"cue {page}", "placard", "part lookup"],
        "answerable_questions": [f"Which items are on page {page}?"],
        "important_entities": [f"ENTITY-{page:03d}"],
        "component_families": ["manual page"],
        "source_grounding_phrases": [f"page {page}"],
        "not_good_for_guardrails": "Do not answer without source evidence.",
    }


def test_parse_page_range_supports_ranges_commas_and_dedupes() -> None:
    assert parse_page_range("1-3,3,5") == [1, 2, 3, 5]


def test_extract_page_number_and_aliases() -> None:
    assert extract_page_number("t_p_120_1176_p000050") == 50
    assert extract_page_number("zip_page_000007") == 7
    aliases = expected_page_id_aliases(7)
    assert "t_p_120_1176_p000007" in aliases
    assert "zip_page_000007" in aliases


def test_build_helper_record_is_retrieval_only() -> None:
    row = make_row(1)
    record = build_helper_record(row)
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["record_type"] == "context_retrieval_helper"
    assert record["safety_bucket"] == "context_retrieval_helper"
    assert record["authority"] == "retrieval_helper_only"
    assert record["can_answer_directly"] is False
    assert record["can_prove_claims"] is False
    assert record["canonical_source_truth"] is False
    assert record["can_mutate_source_truth"] is False
    assert record["requires_source_resolution"] is True
    assert record["requires_citation"] is True
    assert record["embedding_answer_authority_allowed"] is False
    assert "placard" in record["query_tunnel_terms"]
    assert "Do not use as direct answer proof" in record["helper_text"]


def test_build_helper_record_reads_json_payload_fields() -> None:
    row = {
        "record_id": "payload-ctx",
        "page_id": "zip_page_000002",
        "payload": json.dumps(
            {
                "summary": "Payload summary",
                "retrieval_cues": "labels; placards; warnings",
                "important_entities": ["LABEL", "PLACARD"],
            }
        ),
    }
    record = build_helper_record(row)
    assert record["page_id"] == "t_p_120_1176_p000002"
    assert record["summary"] == "Payload summary"
    assert "labels" in record["retrieval_cues"]
    assert "PLACARD" in record["query_tunnel_terms"]


def test_build_helper_records_sorts_by_page_number() -> None:
    records = build_helper_records([make_row(3), make_row(1), make_row(2)])
    assert [record["page_number"] for record in records] == [1, 2, 3]


def test_required_page_coverage_detects_missing_pages() -> None:
    records = build_helper_records([make_row(1), make_row(3)])
    coverage = required_page_coverage([1, 2, 3], records)
    assert coverage["covered_page_numbers"] == [1, 3]
    assert coverage["missing_page_numbers"] == [2]
    assert coverage["missing_page_count"] == 1


def test_build_bundle_and_write_outputs_roundtrip(tmp_path: Path) -> None:
    rows = [make_row(i) for i in range(1, 4)]
    bundle = build_helper_bundle(rows, require_pages=[1, 2, 3])
    assert bundle["record_count"] == 3
    assert bundle["trace_net_boundary_rules"]["context_can_answer_directly"] is False
    paths = write_helper_outputs(bundle, tmp_path)
    assert paths["helpers_path"].exists()
    assert paths["jsonl_path"].exists()
    records, payload = load_helper_records_from_path(paths["helpers_path"])
    assert len(records) == 3
    assert payload["schema_version"] == SCHEMA_VERSION
    jsonl_records, _ = load_helper_records_from_path(paths["jsonl_path"])
    assert len(jsonl_records) == 3


def test_sha256_json_is_order_stable() -> None:
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})
