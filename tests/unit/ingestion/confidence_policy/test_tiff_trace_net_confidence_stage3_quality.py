from __future__ import annotations

from pathlib import Path

from tiff.trace_net_confidence_stage3_policy import ConfidencePolicyPaths, build_confidence_policy
from tiff.trace_net_confidence_stage3_quality import (
    ConfidencePolicyQualityOptions,
    build_confidence_policy_quality,
    write_confidence_policy_quality,
)


def test_confidence_policy_quality_accepts_valid_policy(tmp_path: Path) -> None:
    paths = ConfidencePolicyPaths(stage2_eval_path=tmp_path / "missing.json", output_dir=tmp_path / "out")
    build_confidence_policy(paths)

    report = build_confidence_policy_quality(paths.policy, ConfidencePolicyQualityOptions(min_layers=6))

    assert report.status == "OK"
    assert report.summary["trace_lc_policy_layers"] == 6
    assert report.summary["trace_lc_policy_source_trace_max_tier"] == "A"
    assert report.summary["trace_lc_policy_visual_text_max_tier"] == "B"
    assert all(check.ok for check in report.checks)


def test_write_confidence_policy_quality_writes_json(tmp_path: Path) -> None:
    paths = ConfidencePolicyPaths(stage2_eval_path=tmp_path / "missing.json", output_dir=tmp_path / "out")
    build_confidence_policy(paths)
    quality_path = tmp_path / "quality.json"

    report = write_confidence_policy_quality(quality_path, paths.policy)

    assert report.status == "OK"
    assert quality_path.exists()
    assert "source_trace_policy" in {check.name for check in report.checks}
