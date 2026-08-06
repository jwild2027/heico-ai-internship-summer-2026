import csv
import json
from pathlib import Path

from tiff.trace_net_gold_label_decision_merge_v1 import (
    build_gold_label_decision_merge,
    check_gold_label_decision_merge_quality,
)


def test_quality_check_enforces_min_final_and_max_unresolved(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [
            {"page_id": "p1", "page_number": 1, "suggested_canonical_route": "blank_candidate", "auto_seeded_gold_route_label": "blank_candidate"},
            {"page_id": "p2", "page_number": 2, "suggested_canonical_route": "table_or_index", "auto_seeded_gold_route_label": ""},
        ],
    }), encoding="utf-8")
    payload = build_gold_label_decision_merge(auto_review_seed_path=seed, output_dir=tmp_path / "out", quality=True)
    report = tmp_path / "out" / "trace_net_gold_label_decision_merge_v1.json"

    result = check_gold_label_decision_merge_quality(
        report_path=report,
        min_seed_records=2,
        min_final_labels=1,
        max_unresolved=1,
        require_source_quality_pass=True,
        require_decision_files=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
        write_json=True,
    )
    assert result["quality_status"] == "PASS"

    fail = check_gold_label_decision_merge_quality(report_path=report, min_final_labels=2, max_unresolved=0)
    assert fail["quality_status"] == "FAIL"
