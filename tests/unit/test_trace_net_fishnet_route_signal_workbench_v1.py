import json
from pathlib import Path

from tiff.trace_net_fishnet_route_signal_workbench_v1 import (
    build_fishnet_route_signal_workbench,
    normalize_route,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_normalize_route_aliases():
    assert normalize_route("blank") == "blank_candidate"
    assert normalize_route("plain text") == "normal_text"
    assert normalize_route("diagram") == "image_visual"
    assert normalize_route("table") == "table"


def test_build_workbench_detects_agreement_and_disagreement(tmp_path):
    fishnet = tmp_path / "fishnet.json"
    routes = tmp_path / "routes.json"
    out = tmp_path / "out"

    write_json(
        fishnet,
        {
            "records": [
                {
                    "page_id": "p001",
                    "recommended_route_candidate": "table",
                    "route_confidence": 0.91,
                    "review_required": False,
                    "ocr_engine_status": "ok",
                    "cell_records": [{} for _ in range(4)],
                },
                {
                    "page_id": "p002",
                    "recommended_route_candidate": "image_visual",
                    "route_confidence": 0.92,
                    "review_required": False,
                    "ocr_engine_status": "ok",
                    "cell_records": [{} for _ in range(4)],
                },
            ]
        },
    )
    write_json(
        routes,
        {
            "records": [
                {"page_id": "p001", "selected_route": "table"},
                {"page_id": "p002", "selected_route": "table"},
            ]
        },
    )

    payload = build_fishnet_route_signal_workbench(
        fishnet_report=fishnet,
        current_route_manifest=routes,
        output_dir=out,
        high_confidence_threshold=0.85,
        quality=True,
    )

    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["comparison_record_count"] == 2
    assert summary["agreement_count"] == 1
    assert summary["high_confidence_disagreement_count"] == 1
    assert summary["answer_permission_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0
    assert (out / "trace_net_fishnet_route_signal_workbench_v1.json").exists()
    assert (out / "trace_net_fishnet_route_signal_workbench_v1_records.jsonl").exists()


def test_build_workbench_handles_missing_current_routes_as_review(tmp_path):
    fishnet = tmp_path / "fishnet.json"
    out = tmp_path / "out"
    write_json(
        fishnet,
        {
            "records": [
                {
                    "page_id": "p001",
                    "recommended_route_candidate": "normal_text",
                    "route_confidence": 0.5,
                    "review_required": True,
                    "ocr_engine_status": "failed",
                    "cell_records": [{}],
                }
            ]
        },
    )

    payload = build_fishnet_route_signal_workbench(fishnet_report=fishnet, output_dir=out)
    record = payload["records"][0]
    assert payload["quality_status"] == "PASS"
    assert record["agreement_status"] == "missing_current_route"
    assert record["route_change_authorized"] is False
    assert payload["summary"]["current_route_missing_count"] == 1


def test_build_workbench_matches_source_package_ids_to_canonical_trace_page_ids(tmp_path):
    fishnet = tmp_path / "fishnet.json"
    routes = tmp_path / "routes.json"
    out = tmp_path / "out"

    write_json(
        fishnet,
        {
            "records": [
                {
                    "page_id": "source_p000001",
                    "recommended_route_candidate": "image_visual",
                    "route_confidence": 0.7,
                    "review_required": False,
                    "ocr_engine_status": "ok",
                    "cell_records": [{} for _ in range(48)],
                }
            ]
        },
    )
    write_json(
        routes,
        {
            "records": [
                {
                    "page_route_card": {
                        "page_id": "t_p_120_1176_p000001",
                        "selected_route": "image_visual",
                    }
                }
            ]
        },
    )

    payload = build_fishnet_route_signal_workbench(
        fishnet_report=fishnet,
        current_route_manifest=routes,
        output_dir=out,
        high_confidence_threshold=0.85,
    )

    record = payload["records"][0]
    assert payload["summary"]["current_route_missing_count"] == 0
    assert payload["summary"]["matched_page_count"] == 1
    assert record["current_route_page_id"] == "t_p_120_1176_p000001"
    assert record["page_id_match_strategy"] == "alias"
    assert record["agreement_status"] == "agree"


def test_workbench_carries_nested_fishnet_ocr_features_and_best_route(tmp_path):
    fishnet = tmp_path / "fishnet.json"
    routes = tmp_path / "routes.json"
    out = tmp_path / "out"
    write_json(
        fishnet,
        {
            "records": [
                {
                    "page_id": "source_p000004",
                    "recommended_route_candidate": "review_required",
                    "best_route_candidate_before_review": "normal_text",
                    "route_confidence": 0.0,
                    "review_required": True,
                    "route_review_reason_codes": ["low_margin_table_text"],
                    "ocr_engine_status": "ok",
                    "page_ocr_features": {
                        "ocr_char_count": 892,
                        "ocr_word_count": 128,
                        "ocr_word_box_count": 129,
                        "sample_text": "INTRODUCTION This manual presents all operations",
                    },
                    "route_adjusted_scores": {"normal_text": 1.0, "table": 0.42},
                    "reason_counts": {"ocr_cell_count": 17},
                    "cell_records": [{} for _ in range(48)],
                }
            ]
        },
    )
    write_json(
        routes,
        {"records": [{"page_id": "t_p_120_1176_p000004", "selected_route": "image_visual"}]},
    )

    payload = build_fishnet_route_signal_workbench(
        fishnet_report=fishnet,
        current_route_manifest=routes,
        output_dir=out,
    )

    record = payload["records"][0]
    assert record["fishnet_ocr_text_length"] == 892
    assert record["fishnet_ocr_word_count"] == 128
    assert record["fishnet_ocr_word_box_count"] == 129
    assert record["fishnet_best_route_candidate_before_review"] == "normal_text"
    assert record["fishnet_review_reason_codes"] == ["low_margin_table_text"]
    assert record["fishnet_route_adjusted_scores"] == {"normal_text": 1.0, "table": 0.42}
    assert payload["summary"]["total_fishnet_ocr_text_length"] == 892
    assert payload["summary"]["total_fishnet_ocr_word_box_count"] == 129
    assert payload["summary"]["pages_with_fishnet_ocr_text_count"] == 1
    assert payload["summary"]["fishnet_best_route_candidate_before_review_counts"] == {"normal_text": 1}
