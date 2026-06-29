import json
from pathlib import Path

from tiff.trace_net_gold_label_review_reduction_v1 import build_gold_label_review_reduction, check_quality


def test_quality_check_passes(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {},
        "records": [
            {"page_number": 1, "page_id": "p1", "human_review_required": False, "review_priority": "low", "auto_seed_status": "auto_seeded", "auto_seeded_gold_route_label": "blank_candidate"},
            {"page_number": 2, "page_id": "p2", "human_review_required": True, "review_priority": "high", "auto_seed_status": "needs_human_review"},
        ],
    }), encoding="utf-8")
    out = tmp_path / "out"
    build_gold_label_review_reduction(auto_review_seed_path=seed, output_dir=out, quality=True)
    result = check_quality(
        report_path=out / "trace_net_gold_label_review_reduction_v1.json",
        min_seed_records=2,
        min_human_review_records=1,
        min_auto_seeded=1,
        require_source_quality_pass=True,
        require_priority_files=True,
        require_review_plan=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"
