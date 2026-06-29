import json
from pathlib import Path

from tiff.trace_net_gold_label_auto_review_seed_v1 import (
    build_gold_label_auto_review_seed,
    check_gold_label_auto_review_seed_quality,
)


def test_quality_check_passes_with_expected_thresholds(tmp_path):
    source = tmp_path / "gold.json"
    source.write_text(json.dumps({"quality_status": "PASS", "records": [
        {"page_id": "p", "suggested_canonical_route": "blank_candidate", "suggested_route_confidence": "high", "ocr_word_count": 0}
    ]}), encoding="utf-8")
    out = tmp_path / "out"
    build_gold_label_auto_review_seed(gold_label_workbook=source, output_dir=out, quality=True)
    check = check_gold_label_auto_review_seed_quality(
        report_path=out / "trace_net_gold_label_auto_review_seed_v1.json",
        min_seed_records=1,
        min_auto_seeded=1,
        require_source_quality_pass=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        write_json=True,
    )
    assert check["quality_status"] == "PASS"
    assert (out / "trace_net_gold_label_auto_review_seed_v1_quality_check.json").exists()


def test_quality_check_fails_when_auto_seeded_too_low(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"quality_status": "PASS", "summary": {"seed_record_count": 10, "auto_seeded_gold_route_count": 0}}), encoding="utf-8")
    check = check_gold_label_auto_review_seed_quality(report_path=report, min_seed_records=1, min_auto_seeded=1)
    assert check["quality_status"] == "FAIL"
