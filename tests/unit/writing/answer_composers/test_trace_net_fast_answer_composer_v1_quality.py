from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_fast_answer_composer_v1 import build_fast_answer_composer, check_fast_answer_composer_quality
from tests.unit.writing.answer_composers.test_trace_net_fast_answer_composer_v1 import _context


def test_quality_check_passes(tmp_path: Path) -> None:
    context = _context(tmp_path)
    build_fast_answer_composer(context_pack=context, output_dir=tmp_path / "out", require_source_quality_pass=True)
    result = check_fast_answer_composer_quality(
        report_path=tmp_path / "out" / "trace_net_fast_answer_composer_v1.json",
        write_json=True,
        min_records=1,
        min_citations=1,
        min_valid_citations=1,
        min_direct_exact_records=2,
        min_direct_exact_citations=2,
        max_invalid_citations=0,
        max_violations=0,
        require_source_quality_pass=True,
        require_fast_answer_ready=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"
    assert (tmp_path / "out" / "trace_net_fast_answer_composer_v1_quality_check.json").exists()


def test_quality_check_fails_on_invalid_citation(tmp_path: Path) -> None:
    context = _context(tmp_path)
    payload = build_fast_answer_composer(context_pack=context, output_dir=tmp_path / "out")
    payload["summary"]["invalid_answer_citation_count"] = 1
    path = tmp_path / "out" / "trace_net_fast_answer_composer_v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = check_fast_answer_composer_quality(report_path=path, max_invalid_citations=0)
    assert result["quality_status"] == "FAIL"
