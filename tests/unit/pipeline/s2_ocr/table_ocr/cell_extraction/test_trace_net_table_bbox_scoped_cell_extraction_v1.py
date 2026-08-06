import json
from pathlib import Path

from tiff.trace_net_table_bbox_scoped_cell_extraction_v1 import (
    build_report,
    choose_enrichment_bbox,
    normalize_bbox,
)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def thresholds(**overrides):
    base = {
        "min_source_table_records": 1,
        "min_scoped_table_records": 1,
        "min_bbox_consumed_records": 1,
        "min_scoped_cells": 1,
        "min_scoped_value_records": 1,
        "max_unsafe_scoped_table_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_understanding_quality_pass": True,
        "require_table_ocr_bbox_enrichment_quality_pass": True,
        "require_all_records_bbox_scoped": True,
    }
    base.update(overrides)
    return base


def sample_table_understanding():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "table_understanding_id": "tu1",
                "page_id": "t_p_120_1176_p000003",
                "table_id": "table__legacy_id_that_does_not_match_enrichment",
                "table_type": "parts_list_table",
                "rag_bucket": "table_structured_evidence",
                "trust_tier": "B",
                "citation_ids": ["cite:1"],
                "rows": [
                    {"row_id": "r1", "source_line_index": 0, "cell_ids": ["c1", "c2"]},
                ],
                "cells": [
                    {"cell_id": "c1", "row_id": "r1", "col_index": 1, "text": "120-46137-001", "normalized_text": "120-46137-001", "token_type": "part_number"},
                    {"cell_id": "c2", "row_id": "r1", "col_index": 2, "text": "BRACKET", "normalized_text": "BRACKET", "token_type": "text"},
                ],
            }
        ],
    }


def sample_enrichment():
    return {
        "quality_status": "PASS",
        "table_ocr_bbox_enrichment_cards": [
            {
                "ocr_bbox_enrichment_card_id": "ocr1",
                "page_id": "t_p_120_1176_p000003",
                "table_id": "normtable__different_id",
                "crop_candidate_ready": True,
                "bbox_source": "table_extraction_bbox_preferred",
                "table_extraction_bbox_preferred": True,
                "table_extraction_bbox_source": "table_paddle_style_bbox_resolver",
                "table_extraction_bbox_source_key": "table_extraction_bbox",
                "table_extraction_bbox_coverage_ratio": 0.55,
                "ocr_bbox_source": "ocr_part_number_token_match",
                "inferred_table_region_bbox": {"x0": 100, "y0": 200, "x1": 800, "y1": 900, "coordinate_system": "pixels"},
            }
        ],
    }


def sample_table_understanding_with_legacy_extra():
    payload = sample_table_understanding()
    extra = {
        "table_understanding_id": "tu_legacy",
        "page_id": "t_p_120_1176_p000404",
        "table_id": "legacy_table_without_route_bbox",
        "table_type": "legacy_table_candidate",
        "rows": [{"row_id": "legacy_r1", "source_line_index": 0, "cell_ids": ["legacy_c1"]}],
        "cells": [{"cell_id": "legacy_c1", "row_id": "legacy_r1", "col_index": 1, "text": "legacy", "normalized_text": "legacy"}],
    }
    payload["records"] = list(payload["records"]) + [extra]
    return payload


def test_normalize_bbox_from_mapping():
    box = normalize_bbox({"left": 10, "top": 20, "right": 40, "bottom": 70})
    assert box == {"x0": 10.0, "y0": 20.0, "x1": 40.0, "y1": 70.0, "width": 30.0, "height": 50.0, "coordinate_system": "pixels"}


def test_choose_enrichment_bbox_requires_preferred_candidate():
    card = sample_enrichment()["table_ocr_bbox_enrichment_cards"][0]
    box, key, diagnostics = choose_enrichment_bbox(card)
    assert key == "inferred_table_region_bbox"
    assert box["x0"] == 100
    assert diagnostics["bbox_consume_rejection_reason"] is None

    non_preferred = dict(card, bbox_source="ocr_table_text_token_match", table_extraction_bbox_preferred=False)
    box, key, diagnostics = choose_enrichment_bbox(non_preferred)
    assert box is None
    assert key is None
    assert diagnostics["bbox_consume_rejection_reason"] == "preferred_table_extraction_bbox_not_selected"


def test_build_report_scopes_cells_by_page_id_when_table_ids_differ(tmp_path):
    table_path = tmp_path / "table_understanding.json"
    bbox_path = tmp_path / "bbox_enrichment.json"
    out_dir = tmp_path / "out"
    write_json(table_path, sample_table_understanding())
    write_json(bbox_path, sample_enrichment())

    report = build_report(
        table_understanding_path=table_path,
        table_ocr_bbox_enrichment_path=bbox_path,
        output_dir=out_dir,
        thresholds=thresholds(),
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["source_table_record_count"] == 1
    assert summary["table_extraction_bbox_consumed_record_count"] == 1
    assert summary["scoped_cell_count"] == 2
    assert summary["scoped_value_record_count"] == 2
    assert summary["answer_permission_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0

    record = report["scoped_table_records"][0]
    assert record["bbox_match_method"] == "page_id_single_card"
    assert record["bbox_consumed_by_row_cell_extraction"] is True
    assert record["row_cell_extraction_scope"] == "table_extraction_bbox_crop"
    assert record["table_extraction_bbox"]["x1"] == 800
    assert record["cells"][0]["bbox_scoped_extraction_ready"] is True
    assert record["value_records"][0]["table_bbox_scope_id"] == record["table_bbox_scope_id"]


def test_build_report_scopes_only_bbox_target_records_and_keeps_legacy_count(tmp_path):
    table_path = tmp_path / "table_understanding.json"
    bbox_path = tmp_path / "bbox_enrichment.json"
    out_dir = tmp_path / "out"
    write_json(table_path, sample_table_understanding_with_legacy_extra())
    write_json(bbox_path, sample_enrichment())

    report = build_report(
        table_understanding_path=table_path,
        table_ocr_bbox_enrichment_path=bbox_path,
        output_dir=out_dir,
        thresholds=thresholds(min_source_table_records=2),
        write_quality=True,
    )

    summary = report["summary"]
    assert report["quality_status"] == "PASS"
    assert summary["source_table_record_count"] == 2
    assert summary["bbox_scope_target_record_count"] == 1
    assert summary["legacy_unscoped_table_record_count"] == 1
    assert summary["scoped_table_record_count"] == 1
    assert summary["table_extraction_bbox_missing_or_invalid_record_count"] == 0
    assert summary["scoped_cell_count"] == 2
    assert len(report["scoped_table_records"]) == 1


def test_build_report_fails_all_records_scoped_when_bbox_missing(tmp_path):
    table_path = tmp_path / "table_understanding.json"
    bbox_path = tmp_path / "bbox_enrichment.json"
    out_dir = tmp_path / "out"
    write_json(table_path, sample_table_understanding())
    write_json(bbox_path, {"quality_status": "PASS", "table_ocr_bbox_enrichment_cards": []})

    report = build_report(
        table_understanding_path=table_path,
        table_ocr_bbox_enrichment_path=bbox_path,
        output_dir=out_dir,
        thresholds=thresholds(min_bbox_consumed_records=0),
        write_quality=True,
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["scoped_table_record_count"] == 0
    assert report["summary"]["legacy_unscoped_table_record_count"] == 1
    assert report["summary"]["table_extraction_bbox_missing_or_invalid_record_count"] == 0
    assert report["scoped_table_records"] == []
