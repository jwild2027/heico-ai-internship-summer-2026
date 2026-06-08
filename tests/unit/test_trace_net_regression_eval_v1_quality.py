from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_regression_eval_v1 import check_regression_eval_quality
from test_trace_net_regression_eval_v1 import fake_hybrid_report
from tiff.trace_net_regression_eval_v1 import run_regression_eval


def _make_report(tmp_path: Path) -> Path:
    hybrid_path = tmp_path / "hybrid.json"
    hybrid_path.write_text(json.dumps(fake_hybrid_report()), encoding="utf-8")
    result = run_regression_eval(
        hybrid_report_path=hybrid_path,
        output_dir=tmp_path / "out",
        min_regression_cases=5,
        min_cases_with_results=5,
        min_cases_with_candidate_hits=5,
        min_cases_with_page_profile_hits=5,
        min_total_ranked_groups=15,
        min_total_candidate_hits=15,
        min_total_page_profile_hits=15,
        require_all_cases_pass=True,
        require_hybrid_quality_pass=True,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
    )
    assert result["status"] == "PASS"
    return tmp_path / "out" / "trace_net_regression_eval_v1.json"


def test_check_regression_eval_quality_passes(tmp_path: Path) -> None:
    report_path = _make_report(tmp_path)
    result = check_regression_eval_quality(
        report_path=report_path,
        min_regression_cases=5,
        min_cases_with_results=5,
        min_cases_with_candidate_hits=5,
        min_cases_with_page_profile_hits=5,
        min_total_ranked_groups=15,
        min_total_candidate_hits=15,
        min_total_page_profile_hits=15,
        require_all_cases_pass=True,
        require_hybrid_quality_pass=True,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
    )
    assert result["status"] == "PASS"


def test_check_regression_eval_quality_writes_json(tmp_path: Path) -> None:
    report_path = _make_report(tmp_path)
    quality_path = tmp_path / "quality.json"
    result = check_regression_eval_quality(report_path=report_path, write_json_path=quality_path)
    assert result["status"] == "PASS"
    assert quality_path.exists()


def test_check_regression_eval_quality_fails_on_wrong_count(tmp_path: Path) -> None:
    report_path = _make_report(tmp_path)
    result = check_regression_eval_quality(report_path=report_path, require_candidate_count=999)
    assert result["status"] == "FAIL"
