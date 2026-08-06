from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_cell_normalizer_v1 import (
    candidate_join_part,
    build_trace_net_table_cell_normalizer,
    extract_catalog_part_numbers,
    normalize_cell_value,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sample_table_payload() -> dict:
    return {
        "schema_version": "trace_net_table_understanding_v1",
        "quality_status": "PASS",
        "records": [
            {
                "table_id": "tbl_p3_001",
                "page_id": "t_p_120_1176_p000003",
                "page_number": 3,
                "table_type": "parts_list_table",
                "trust_tier": "B",
                "rag_bucket": "table_part_catalog_evidence",
                "answer_support_candidate": True,
                "citation_ids": ["cite:table_structured:t_p_120_1176_p000003:abc"],
                "rows": [
                    {"row_id": "r1", "row_index": 1},
                    {"row_id": "r2", "row_index": 2},
                ],
                "cells": [
                    {"row_id": "r1", "col_index": 0, "text": "120-46"},
                    {"row_id": "r1", "col_index": 1, "text": "137-001"},
                    {"row_id": "r1", "col_index": 2, "text": "HINGE ASSY"},
                    {"row_id": "r2", "col_index": 0, "text": "25-21-00"},
                    {"row_id": "r2", "col_index": 1, "text": "Sep 30/98"},
                ],
            }
        ],
    }


def sample_embedding_payload() -> dict:
    return {
        "schema_version": "trace_net_embedding_candidates_v1",
        "records": [
            {
                "embedding_candidate_id": "emb_1",
                "rag_bucket": "verified_part_evidence",
                "embedding_text": "Verified part 120-46137-001 appears on page 3.",
            }
        ],
    }


def test_candidate_join_part_repairs_split_part_number() -> None:
    assert candidate_join_part("120-46", "137-001") == "120-46137-001"
    assert candidate_join_part("ABC", "DEF") is None


def test_normalize_cell_value_preserves_part_hyphens() -> None:
    assert normalize_cell_value(" 120 - 46 ") == "120-46"


def test_extract_catalog_part_numbers_finds_verified_parts() -> None:
    parts = extract_catalog_part_numbers(sample_embedding_payload()["records"])
    assert "120-46137-001" in parts


def test_build_table_cell_normalizer_creates_repairs_and_safe_rows(tmp_path: Path) -> None:
    table_path = tmp_path / "table.json"
    emb_path = tmp_path / "emb.json"
    write_json(table_path, sample_table_payload())
    write_json(emb_path, sample_embedding_payload())

    report = build_trace_net_table_cell_normalizer(
        table_understanding_path=table_path,
        embedding_candidates_path=emb_path,
        output_dir=tmp_path / "out",
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["normalized_table_record_count"] == 1
    assert summary["normalized_row_count"] == 2
    assert summary["part_number_merge_candidate_count"] == 1
    assert summary["catalog_supported_merge_count"] == 1
    assert summary["uncited_answer_capable_row_count"] == 0
    assert summary["retrieval_only_answer_allowed_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0

    record = report["records"][0]
    assert record["can_answer_directly"] is False
    assert record["can_mutate_source_truth"] is False
    repaired_cells = [c for c in record["cells"] if c.get("repair_id")]
    assert repaired_cells[0]["normalized_text"] == "120-46137-001"
    assert repaired_cells[0]["catalog_supported"] is True
    assert record["rows"][0]["answer_support_candidate"] is True
    assert record["rows"][0]["can_answer_directly"] is False


def test_uncited_table_rows_are_not_answer_support(tmp_path: Path) -> None:
    payload = sample_table_payload()
    payload["records"][0]["citation_ids"] = []
    table_path = tmp_path / "table.json"
    emb_path = tmp_path / "emb.json"
    write_json(table_path, payload)
    write_json(emb_path, sample_embedding_payload())

    report = build_trace_net_table_cell_normalizer(
        table_understanding_path=table_path,
        embedding_candidates_path=emb_path,
        output_dir=tmp_path / "out",
    )
    assert report["summary"]["answer_support_row_count"] == 0
    assert report["summary"]["uncited_answer_capable_row_count"] == 0
    assert report["quality_status"] == "PASS"

def test_source_trace_provenance_paths_do_not_mark_clean_table_text_unsafe(tmp_path: Path) -> None:
    payload = sample_table_payload()
    payload["records"][0]["source_url"] = "https://example.test/source"
    payload["records"][0]["tiff_path"] = "local_data/rescarta_exports/t_p_120_1176/page_000003.tif"
    payload["records"][0]["ocr_path"] = "local_data/ocr/page_000003.txt"
    table_path = tmp_path / "table.json"
    emb_path = tmp_path / "emb.json"
    write_json(table_path, payload)
    write_json(emb_path, sample_embedding_payload())

    report = build_trace_net_table_cell_normalizer(
        table_understanding_path=table_path,
        embedding_candidates_path=emb_path,
        output_dir=tmp_path / "out",
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["unsafe_table_evidence_count"] == 0


def test_user_visible_table_text_leak_still_fails_quality(tmp_path: Path) -> None:
    payload = sample_table_payload()
    payload["records"][0]["cells"][0]["text"] = "local_data/rescarta_exports/leaked_path.tif"
    table_path = tmp_path / "table.json"
    emb_path = tmp_path / "emb.json"
    write_json(table_path, payload)
    write_json(emb_path, sample_embedding_payload())

    report = build_trace_net_table_cell_normalizer(
        table_understanding_path=table_path,
        embedding_candidates_path=emb_path,
        output_dir=tmp_path / "out",
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["unsafe_table_evidence_count"] == 1

