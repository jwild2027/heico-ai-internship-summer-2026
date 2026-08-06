from pathlib import Path

from tiff.trace_net_route_label_taxonomy_v1 import build_route_label_taxonomy
from scripts.maintenance.benchmark.check_trace_net_route_label_taxonomy_v1_quality import check_quality


def test_quality_check_passes_with_required_labels(tmp_path):
    build_route_label_taxonomy(tmp_path, quality=True)
    result = check_quality(
        report_path=tmp_path / "trace_net_route_label_taxonomy_v1.json",
        min_route_labels=9,
        require_label=["blank_candidate", "detailed_parts_list", "image_visual_diagram", "review_required"],
        require_legacy_alias=["blank_candidate", "normal_text", "table", "image_visual"],
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        max_unsafe=0,
        write_json=True,
    )
    assert result["quality_status"] == "PASS"
    assert (tmp_path / "trace_net_route_label_taxonomy_v1_quality_check.json").exists()


def test_quality_check_fails_missing_required_label(tmp_path):
    build_route_label_taxonomy(tmp_path)
    result = check_quality(
        report_path=tmp_path / "trace_net_route_label_taxonomy_v1.json",
        require_label=["not_a_real_label"],
    )
    assert result["quality_status"] == "FAIL"
    assert any("not_a_real_label" in failure for failure in result["failures"])
