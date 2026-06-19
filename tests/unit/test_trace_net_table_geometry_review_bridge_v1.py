import json
from pathlib import Path

from tiff.trace_net_table_geometry_review_bridge_v1 import (
    QualityThresholds,
    build_review_bridge_report,
    read_json,
)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sample_table_geometry_payload():
    return {
        "schema_version": "trace_net_table_line_geometry_v1",
        "quality_status": "PASS",
        "table_geometry_cards": [
            {
                "geometry_card_id": "table_geom_a",
                "page_id": "t_p_120_1176_p000003",
                "source_page_ids": ["t_p_120_1176_p000003"],
                "table_id": "normtable__abc",
                "table_type": "parts_list_table",
                "cell_record_count": 215,
                "row_record_count": 75,
                "row_count_estimate": 150,
                "column_count_estimate": 7,
                "geometry_inference_method": "normalizer_row_column_fallback",
                "image_line_detection_available": False,
                "horizontal_line_count": 0,
                "vertical_line_count": 0,
                "merged_cell_candidate_count": 0,
                "geometry_confidence": 0.70,
                "review_required": True,
                "review_flags": ["image_not_available_for_geometry_card", "line_detection_unavailable_or_empty"],
                "recommended_actions": ["run_or_expand_morphological_line_detection", "use_ocr_row_column_clustering_fallback"],
                "domain_validation": {
                    "domain_table_type_hints": ["parts_list_or_ipl_table"],
                    "part_number_count": 68,
                    "part_number_row_count": 64,
                    "part_numbers_sample": ["120-46137-001"],
                },
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        ],
    }


def test_builds_human_review_tasks_from_table_geometry(tmp_path: Path):
    src = tmp_path / "table_line_geometry.json"
    out = tmp_path / "out"
    write_json(src, sample_table_geometry_payload())

    report = build_review_bridge_report(
        table_line_geometry_path=src,
        output_dir=out,
        thresholds=QualityThresholds(
            min_review_tasks=1,
            min_source_cards=1,
            require_source_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["review_task_count"] == 1
    assert report["summary"]["part_number_table_review_task_count"] == 1
    task = report["review_tasks"][0]
    assert task["origin_category"] == "table_geometry"
    assert task["target_type"] == "table_geometry_card"
    assert task["page_id"] == "t_p_120_1176_p000003"
    assert task["table_id"] == "normtable__abc"
    assert task["priority"] == "HIGH"
    assert task["requires_human_review"] is True
    assert "verify_table_geometry_against_source_page" in task["recommended_actions"]
    assert task["can_answer_directly"] is False
    assert task["can_prove_claims"] is False
    assert task["source_truth_mutation_allowed"] is False
    assert task["postgres_write_attempt_count"] == 0
    assert (out / "trace_net_table_geometry_review_bridge_v1.json").exists()
    assert (out / "trace_net_table_geometry_review_bridge_v1_tasks.jsonl").exists()


def test_quality_fails_when_source_card_has_unsafe_authority(tmp_path: Path):
    payload = sample_table_geometry_payload()
    payload["table_geometry_cards"][0]["can_answer_directly"] = True
    src = tmp_path / "table_line_geometry.json"
    out = tmp_path / "out"
    write_json(src, payload)

    report = build_review_bridge_report(
        table_line_geometry_path=src,
        output_dir=out,
        thresholds=QualityThresholds(
            min_review_tasks=1,
            max_unsafe_source_cards=0,
            require_source_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["unsafe_source_card_count"] == 1
    # The bridge output itself still hardens task authority fields to false.
    assert report["review_tasks"][0]["can_answer_directly"] is False


def test_low_confidence_non_flagged_card_routes_to_review(tmp_path: Path):
    payload = sample_table_geometry_payload()
    card = payload["table_geometry_cards"][0]
    card["review_required"] = False
    card["review_flags"] = []
    card["image_line_detection_available"] = True
    card["geometry_confidence"] = 0.40
    src = tmp_path / "table_line_geometry.json"
    out = tmp_path / "out"
    write_json(src, payload)

    report = build_review_bridge_report(
        table_line_geometry_path=src,
        output_dir=out,
        thresholds=QualityThresholds(min_review_tasks=1, require_source_quality_pass=True),
        low_confidence_threshold=0.75,
    )

    task = report["review_tasks"][0]
    assert report["quality_status"] == "PASS"
    assert task["issue_type"] == "table_geometry_low_confidence"
    assert task["priority"] == "HIGH"
