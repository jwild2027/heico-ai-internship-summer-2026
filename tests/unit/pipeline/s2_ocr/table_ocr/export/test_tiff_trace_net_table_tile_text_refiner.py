from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_tile_text_refiner import (
    TableTileTextRefinerOptions,
    TableTileTextRefinerPaths,
    classify_token,
    refine_table_tile_text_records,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_classify_token_filters_index_labels_and_ata() -> None:
    catalog = {"12050645009"}
    assert classify_token("25-Numerical", catalog).token_type == "index_label"
    assert classify_token("25-Vendors", catalog).token_type == "index_label"
    assert classify_token("25-21-00", catalog).token_type == "ata_code"
    supported = classify_token("120-50645-009", catalog)
    assert supported.token_type == "catalog_supported_part_number"
    assert supported.catalog_supported is True
    unsupported = classify_token("120-99999-001", catalog)
    assert unsupported.token_type == "unsupported_part_candidate"


def test_refine_records_classifies_parts_and_non_parts(tmp_path: Path) -> None:
    input_path = tmp_path / "table_tile_text_records.jsonl"
    part_tree = tmp_path / "part_tree.json"
    out_dir = tmp_path / "out"
    part_tree.write_text(json.dumps({"parts": {"120-50645-009": {"nomenclature": "TEST"}}}), encoding="utf-8")
    write_jsonl(
        input_path,
        [
            {
                "page_id": "p1",
                "tile_id": "p1_tile_001",
                "tile_index": 1,
                "status": "ok",
                "provider": "page_ocr",
                "model": "page-ocr-baseline",
                "text": "25-21-00 25-Numerical Index 120-50645-009 120-99999-001",
                "part_numbers": ["25-Numerical", "120-50645-009", "120-99999-001"],
            }
        ],
    )
    result = refine_table_tile_text_records(
        TableTileTextRefinerPaths(input_records_path=input_path, part_tree_path=part_tree, output_dir=out_dir),
        TableTileTextRefinerOptions(),
    )
    summary = result["summary"]
    assert summary["records"] == 1
    assert summary["records_with_catalog_supported_parts"] == 1
    assert summary["records_with_filtered_non_part_tokens"] == 1
    rows = [json.loads(line) for line in (out_dir / "table_tile_text_refined_records.jsonl").read_text().splitlines()]
    row = rows[0]
    assert row["catalog_supported_part_numbers"] == ["120-50645-009"]
    assert "120-99999-001" in row["unsupported_part_candidates"]
    assert "25-Numerical" in row["index_labels"]
    assert "25-21-00" in row["ata_codes"]
    assert "25-Numerical" not in row["canonical_part_numbers"]
    assert row["classification_trust_tier"] == "B"
