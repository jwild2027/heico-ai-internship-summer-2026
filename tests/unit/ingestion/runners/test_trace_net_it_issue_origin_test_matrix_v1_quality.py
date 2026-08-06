from pathlib import Path

from tiff.trace_net_it_issue_origin_test_matrix_v1 import (
    build_it_issue_origin_test_matrix,
    check_it_issue_origin_test_matrix_quality,
)


def test_quality_check_passes_for_generated_matrix(tmp_path: Path) -> None:
    report = build_it_issue_origin_test_matrix(output_dir=tmp_path / "matrix")
    quality = check_it_issue_origin_test_matrix_quality(Path(report["report_path"]))
    assert quality["status"] == "PASS"
    assert quality["checks"]["scenario_count_meets_minimum"] is True
    assert quality["checks"]["origin_category_count_meets_minimum"] is True
    assert quality["checks"]["all_scenarios_detected_if_required"] is True


def test_quality_check_can_fail_strict_minimums(tmp_path: Path) -> None:
    report = build_it_issue_origin_test_matrix(output_dir=tmp_path / "matrix")
    quality = check_it_issue_origin_test_matrix_quality(
        Path(report["report_path"]),
        min_scenarios=999,
        min_origin_categories=999,
    )
    assert quality["status"] == "FAIL"
    assert quality["checks"]["scenario_count_meets_minimum"] is False
    assert quality["checks"]["origin_category_count_meets_minimum"] is False


def test_quality_check_writes_json(tmp_path: Path) -> None:
    report = build_it_issue_origin_test_matrix(output_dir=tmp_path / "matrix")
    quality = check_it_issue_origin_test_matrix_quality(
        Path(report["report_path"]),
        write_json_report=True,
    )
    assert quality["status"] == "PASS"
    assert Path(quality["quality_path"]).exists()
