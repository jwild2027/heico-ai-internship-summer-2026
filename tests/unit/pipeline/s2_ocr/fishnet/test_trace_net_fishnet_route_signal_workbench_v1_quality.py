import json
from pathlib import Path

from tiff.trace_net_fishnet_route_signal_workbench_v1 import (
    build_fishnet_route_signal_workbench,
    check_fishnet_route_signal_workbench_quality,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_report(tmp_path: Path) -> Path:
    fishnet = tmp_path / "fishnet.json"
    routes = tmp_path / "routes.json"
    out = tmp_path / "out"
    write_json(
        fishnet,
        {
            "records": [
                {"page_id": "p001", "recommended_route_candidate": "table", "route_confidence": 0.9},
                {"page_id": "p002", "recommended_route_candidate": "image_visual", "route_confidence": 0.9},
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
    build_fishnet_route_signal_workbench(
        fishnet_report=fishnet,
        current_route_manifest=routes,
        output_dir=out,
        high_confidence_threshold=0.85,
    )
    return out / "trace_net_fishnet_route_signal_workbench_v1.json"


def test_quality_passes_for_structural_coverage_and_safety(tmp_path):
    report = make_report(tmp_path)
    result = check_fishnet_route_signal_workbench_quality(
        report_path=report,
        require_page_count=2,
        min_comparison_records=2,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        max_missing_current_routes=0,
        write_json_report=True,
    )
    assert result["quality_status"] == "PASS"
    assert Path(result["wrote"]).exists()


def test_quality_can_fail_on_high_confidence_disagreement_threshold(tmp_path):
    report = make_report(tmp_path)
    result = check_fishnet_route_signal_workbench_quality(
        report_path=report,
        require_page_count=2,
        max_high_confidence_disagreements=0,
    )
    assert result["quality_status"] == "FAIL"
    assert "high_confidence_disagreement_count" in result["quality_reasons"][0]


def test_quality_can_require_fishnet_ocr_feature_carryover(tmp_path):
    fishnet = tmp_path / "fishnet.json"
    routes = tmp_path / "routes.json"
    out = tmp_path / "out"
    write_json(
        fishnet,
        {
            "records": [
                {
                    "page_id": "p001",
                    "recommended_route_candidate": "normal_text",
                    "route_confidence": 0.9,
                    "page_ocr_features": {"ocr_char_count": 500, "ocr_word_box_count": 75},
                    "cell_records": [{} for _ in range(4)],
                }
            ]
        },
    )
    write_json(routes, {"records": [{"page_id": "p001", "selected_route": "normal_text"}]})
    build_fishnet_route_signal_workbench(fishnet_report=fishnet, current_route_manifest=routes, output_dir=out)
    report = out / "trace_net_fishnet_route_signal_workbench_v1.json"

    result = check_fishnet_route_signal_workbench_quality(
        report_path=report,
        min_fishnet_ocr_text_chars=400,
        min_fishnet_ocr_word_boxes=50,
        min_pages_with_fishnet_ocr_text=1,
    )
    assert result["quality_status"] == "PASS"

    failed = check_fishnet_route_signal_workbench_quality(
        report_path=report,
        min_fishnet_ocr_text_chars=1000,
    )
    assert failed["quality_status"] == "FAIL"
    assert "total_fishnet_ocr_text_length" in failed["quality_reasons"][0]
