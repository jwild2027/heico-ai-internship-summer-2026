from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_confidence_stage5_quality import (
    ConfidenceStage5QualityOptions,
    ConfidenceStage5QualityPaths,
    run_confidence_stage5_quality,
)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_stage5_quality_passes(tmp_path: Path) -> None:
    summary = {
        "status": "OK",
        "version": "trace_lc_stage5b_policy_control_v1",
        "records": 3,
        "pages": 2,
        "controlled_layers": ["source_trace", "part_catalog", "table_tile_text_refined"],
        "policy_controlled_records": 3,
        "rule_controlled_records": 0,
        "controlled_routing_changed_records": 0,
        "unsafe_final_rag_include_records": 0,
        "source_trace_final_A_records": 2,
        "part_catalog_final_A_records": 1,
        "table_candidate_direct_rag_records": 0,
        "visual_text_controlled_records": 0,
        "table_tile_text_refined_controlled_records": 1,
        "table_tile_text_refined_derived_context_records": 1,
        "table_tile_text_refined_direct_verified_records": 0,
    }
    summary_path = tmp_path / "summary.json"
    records_path = tmp_path / "records.jsonl"
    quality_path = tmp_path / "quality.json"
    _write_json(summary_path, summary)
    _write_jsonl(records_path, [{"x": 1}, {"x": 2}, {"x": 3}])

    result = run_confidence_stage5_quality(
        ConfidenceStage5QualityPaths(control_json=summary_path, control_records=records_path, quality_path=quality_path),
        ConfidenceStage5QualityOptions(
            min_records=3,
            min_pages=2,
            min_policy_controlled_records=3,
            min_source_trace_final_A_records=2,
            min_part_catalog_final_A_records=1,
            max_controlled_routing_changed_records=0,
            min_table_tile_text_refined_controlled_records=1,
            min_table_tile_text_refined_derived_context_records=1,
            max_table_tile_text_refined_direct_verified_records=0,
            write_json=True,
        ),
    )
    assert result["status"] == "OK"
    assert quality_path.exists()


def test_stage5_quality_fails_unsafe(tmp_path: Path) -> None:
    summary = {
        "status": "OK",
        "records": 1,
        "pages": 1,
        "controlled_layers": ["source_trace"],
        "policy_controlled_records": 1,
        "unsafe_final_rag_include_records": 1,
        "source_trace_final_A_records": 1,
        "part_catalog_final_A_records": 0,
        "table_candidate_direct_rag_records": 0,
        "visual_text_controlled_records": 0,
        "table_tile_text_refined_controlled_records": 1,
        "table_tile_text_refined_derived_context_records": 1,
        "table_tile_text_refined_direct_verified_records": 0,
    }
    summary_path = tmp_path / "summary.json"
    records_path = tmp_path / "records.jsonl"
    _write_json(summary_path, summary)
    _write_jsonl(records_path, [{"x": 1}])

    result = run_confidence_stage5_quality(
        ConfidenceStage5QualityPaths(control_json=summary_path, control_records=records_path),
        ConfidenceStage5QualityOptions(min_records=1, min_pages=1, max_unsafe_final_rag_include_records=0, require_controlled_layers=("source_trace",), min_part_catalog_final_A_records=0),
    )
    assert result["status"] == "FAIL"
