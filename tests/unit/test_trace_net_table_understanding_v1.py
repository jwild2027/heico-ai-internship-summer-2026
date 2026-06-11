from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_table_understanding_v1 import (
    build_table_understanding,
    grab_table_cells_from_text,
    infer_table_type,
    make_table_record,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def sample_registry() -> dict:
    return {
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "page_number": 3,
                "page_traits": ["source_trace_present", "table_candidate", "parts_list"],
                "detected_elements": [{"element_type": "table_candidate", "status": "available"}],
                "recommended_extraction_routes": ["table_candidate_route", "table_tile_text_refined_route"],
            },
            {
                "page_id": "t_p_120_1176_p000004",
                "page_number": 4,
                "page_traits": ["source_trace_present", "ocr_text_present"],
                "detected_elements": [{"element_type": "source_text", "status": "available"}],
                "recommended_extraction_routes": ["source_text_route"],
            },
        ]
    }


def sample_refined_record() -> dict:
    text = "120-45851-501 120-45851-503\n120-50645-007 120-50645-009\n25-APPLICABILITY\nPage i/ii"
    return {
        "page_id": "t_p_120_1176_p000003",
        "tile_id": "t_p_120_1176_p000003_tile_001",
        "classification_trust_tier": "B",
        "text": text,
        "source_url": "http://localhost:8080/rescarta/t_p_120_1176/000003",
        "ocr_path": "local_data/rescarta_exports/t_p_120_1176/ocr/000003_00000003.txt",
        "tiff_path": "local_data/rescarta_exports/t_p_120_1176/pages/000003_00000003.tif",
        "tile_path": "local_data/organization/table_extraction/tiles/t_p_120_1176_p000003/tile_001.png",
        "canonical_part_numbers": ["120-45851-501", "120-45851-503", "120-50645-007", "120-50645-009"],
        "catalog_supported_part_numbers": ["120-45851-501", "120-45851-503"],
        "ata_codes": [],
        "index_labels": ["25-APPLICABILITY"],
    }


def test_grab_table_cells_extracts_part_cells() -> None:
    result = grab_table_cells_from_text("120-45851-501 120-45851-503\n9-IPL 1338 Apr 10/06")
    assert result["row_count"] == 2
    assert result["cell_count"] >= 4
    assert result["token_type_counts"]["part_number"] == 2
    assert result["recognized_cell_count"] >= 3
    assert result["cell_grabber_algorithm"] == "trace_net_token_span_plus_whitespace_grid_v1"


def test_infer_table_type_parts_list() -> None:
    refined = sample_refined_record()
    cells = grab_table_cells_from_text(refined["text"])
    assert infer_table_type(refined, cells) == "parts_list_table"


def test_make_table_record_is_safe() -> None:
    record = make_table_record(sample_registry()["records"][0], [sample_refined_record()], {})
    assert record["page_id"] == "t_p_120_1176_p000003"
    assert record["table_type"] == "parts_list_table"
    assert record["cell_count"] >= 4
    assert record["answer_support_candidate"] is True
    assert record["can_answer_directly"] is False
    assert record["can_prove_claims"] is False
    assert record["can_mutate_source_truth"] is False
    assert record["requires_citation"] is True
    assert record["citation_ids"]


def test_build_table_understanding_outputs_artifacts(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    refined_path = tmp_path / "refined.jsonl"
    candidates_path = tmp_path / "candidates.json"
    output_dir = tmp_path / "out"
    write_json(registry_path, sample_registry())
    write_jsonl(refined_path, [sample_refined_record()])
    write_json(candidates_path, {"records": [{"page_id": "t_p_120_1176_p000003", "rag_bucket": "verified_part_evidence"}]})

    report = build_table_understanding(
        page_registry_path=registry_path,
        refined_records_path=refined_path,
        embedding_candidates_path=candidates_path,
        output_dir=output_dir,
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["table_understanding_record_count"] == 1
    assert report["summary"]["pages_with_structured_cells_count"] == 1
    assert (output_dir / "trace_net_table_understanding_v1.json").exists()
    assert (output_dir / "trace_net_table_understanding_v1_cells.jsonl").exists()


def test_build_includes_refined_page_even_if_registry_lacks_table_signal(tmp_path: Path) -> None:
    registry = {"records": [{"page_id": "t_p_120_1176_p000003", "page_traits": ["ocr_text_present"]}]}
    registry_path = tmp_path / "registry.json"
    refined_path = tmp_path / "refined.jsonl"
    write_json(registry_path, registry)
    write_jsonl(refined_path, [sample_refined_record()])
    report = build_table_understanding(page_registry_path=registry_path, refined_records_path=refined_path, output_dir=tmp_path / "out")
    assert report["summary"]["table_understanding_record_count"] == 1
