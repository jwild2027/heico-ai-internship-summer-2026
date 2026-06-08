from __future__ import annotations

from pathlib import Path

from tiff.trace_net_graph_baseline_checkpoint_v1 import (
    SCHEMA_VERSION,
    canonical_checkpoint_for_hash,
    checkpoint_summary,
    evaluate_checkpoint_quality,
    expected_page_id_aliases,
    extract_page_number,
    parse_page_range,
    required_page_coverage,
    sha256_json,
)


def test_parse_page_range_supports_ranges_commas_and_dedupes() -> None:
    assert parse_page_range("1-3, 3, 5") == [1, 2, 3, 5]


def test_extract_page_number_handles_trace_net_and_zip_aliases() -> None:
    assert extract_page_number("t_p_120_1176_p000001") == 1
    assert extract_page_number("zip_page_000050") == 50
    assert extract_page_number("page_12") == 12
    assert extract_page_number("no_digits") is None


def test_expected_page_id_aliases_include_current_trace_net_shape() -> None:
    aliases = expected_page_id_aliases(7)
    assert "t_p_120_1176_p000007" in aliases
    assert "zip_page_000007" in aliases


def test_required_page_coverage_matches_page_context_by_page_number() -> None:
    coverage = required_page_coverage(
        [1, 2, 3],
        page_ids=["t_p_120_1176_p000001", "t_p_120_1176_p000002", "t_p_120_1176_p000003"],
        context_page_ids=["t_p_120_1176_p000001", "zip_page_000002"],
    )
    assert coverage["covered_page_numbers"] == [1, 2]
    assert coverage["missing_page_numbers"] == [3]
    assert coverage["missing_page_count"] == 1


def test_checkpoint_hash_excludes_generated_at_and_hash_field() -> None:
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": "2026-06-08T00:00:00Z",
        "checkpoint_sha256": "old",
        "graph_baseline": {"page_count": 509},
    }
    first = sha256_json(canonical_checkpoint_for_hash(checkpoint))
    checkpoint["generated_at_utc"] = "2026-06-09T00:00:00Z"
    checkpoint["checkpoint_sha256"] = "new"
    second = sha256_json(canonical_checkpoint_for_hash(checkpoint))
    assert first == second


def test_checkpoint_summary_extracts_core_counts() -> None:
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_name": "demo",
        "generated_at_utc": "2026-06-08T00:00:00Z",
        "checkpoint_sha256": "abc",
        "read_only": True,
        "graph_baseline": {
            "page_count": 509,
            "part_node_count": 442,
            "nomenclature_node_count": 151,
            "has_nomenclature_edge_count": 386,
            "page_context_v2_page_count": 50,
            "has_context_v2_edge_count": 50,
            "required_context_v2_coverage": {"missing_page_count": 0},
        },
        "retrieval_safety_baseline": {
            "rag_candidate_count": 1426,
            "source_citation_count": 1426,
            "unsafe_embedding_candidate_count": 0,
        },
    }
    summary = checkpoint_summary(checkpoint)
    assert summary["page_count"] == 509
    assert summary["nomenclature_node_count"] == 151
    assert summary["required_context_v2_missing_page_count"] == 0
    assert summary["rag_candidate_count"] == 1426


def test_evaluate_checkpoint_quality_passes_synthetic_current_baseline() -> None:
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "read_only": True,
        "graph_baseline": {
            "page_count": 509,
            "part_node_count": 442,
            "nomenclature_node_count": 151,
            "has_nomenclature_edge_count": 386,
            "page_context_v2_page_count": 50,
            "has_context_v2_edge_count": 50,
            "required_context_v2_coverage": {"missing_page_numbers": [], "missing_page_count": 0},
        },
        "retrieval_safety_baseline": {
            "rag_candidate_count": 1426,
            "source_citation_count": 1426,
            "unsafe_embedding_candidate_count": 0,
        },
        "artifact_baseline": {
            "graph_explorer_v2_nomenclature_quality": {"status": "PASS"},
        },
    }
    quality = evaluate_checkpoint_quality(
        checkpoint,
        min_page_count=509,
        min_part_nodes=442,
        min_nomenclature_nodes=151,
        min_has_nomenclature_edges=386,
        min_context_v2_pages=50,
        min_has_context_v2_edges=50,
        min_rag_candidates=1426,
        min_source_citations=1426,
        require_graph_explorer_quality_pass=True,
    )
    assert quality.status == "PASS"
    assert quality.passed


def test_evaluate_checkpoint_quality_fails_when_context_v2_missing() -> None:
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "read_only": True,
        "graph_baseline": {
            "page_count": 509,
            "part_node_count": 442,
            "nomenclature_node_count": 151,
            "has_nomenclature_edge_count": 386,
            "page_context_v2_page_count": 49,
            "has_context_v2_edge_count": 49,
            "required_context_v2_coverage": {"missing_page_numbers": [50], "missing_page_count": 1},
        },
        "retrieval_safety_baseline": {
            "rag_candidate_count": 1426,
            "source_citation_count": 1426,
            "unsafe_embedding_candidate_count": 0,
        },
    }
    quality = evaluate_checkpoint_quality(checkpoint, min_context_v2_pages=50, min_has_context_v2_edges=50)
    assert quality.status == "FAIL"
    failed_names = {check["name"] for check in quality.checks if check["status"] == "FAIL"}
    assert "page_context_v2_page_count" in failed_names
    assert "required_context_v2_missing_pages" in failed_names
