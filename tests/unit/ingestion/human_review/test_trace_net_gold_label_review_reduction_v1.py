import json
from pathlib import Path

from tiff.trace_net_gold_label_review_reduction_v1 import build_gold_label_review_reduction


def _seed(path: Path):
    records = []
    for i in range(1, 7):
        human = i in {2, 3, 4}
        records.append({
            "page_number": i,
            "page_id": f"p{i}",
            "human_review_required": human,
            "review_priority": "high" if i == 2 else ("medium" if human else "low"),
            "auto_seed_status": "needs_human_review" if human else "auto_seeded",
            "suggested_canonical_route": "table_or_index" if human else "blank_candidate",
            "auto_seeded_gold_route_label": "" if human else "blank_candidate",
            "seed_reasons": ["x"],
            "ocr_word_count": 0,
            "part_number_count": 0,
        })
    payload = {"quality_status": "PASS", "summary": {"seed_record_count": 6}, "records": records}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_reduction_outputs_priority_files(tmp_path):
    seed = tmp_path / "seed.json"
    _seed(seed)
    out = tmp_path / "out"
    payload = build_gold_label_review_reduction(auto_review_seed_path=seed, output_dir=out, quality=True)
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["seed_record_count"] == 6
    assert payload["summary"]["high_priority_review_count"] == 1
    assert payload["summary"]["medium_priority_review_count"] == 2
    assert (out / "high_priority_review.csv").exists()
    assert (out / "medium_priority_review.csv").exists()
    assert (out / "low_priority_auto_seeded_audit_sample.csv").exists()
    assert (out / "page_range_review_plan.md").exists()
