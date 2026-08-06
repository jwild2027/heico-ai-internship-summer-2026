import csv
import json
from pathlib import Path

from tiff.trace_net_gold_label_decision_merge_v1 import build_gold_label_decision_merge


def _seed(path: Path) -> Path:
    payload = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "p1",
                "page_number": 1,
                "suggested_canonical_route": "cover_or_title_page",
                "auto_seeded_gold_route_label": "cover_or_title_page",
                "review_priority": "low",
                "ocr_word_count": 50,
                "part_number_count": 0,
            },
            {
                "page_id": "p2",
                "page_number": 2,
                "suggested_canonical_route": "table_or_index",
                "auto_seeded_gold_route_label": "",
                "review_priority": "medium",
                "ocr_word_count": 80,
                "part_number_count": 0,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_merge_uses_seeded_and_human_review_labels(tmp_path):
    seed_path = _seed(tmp_path / "seed.json")
    review = tmp_path / "high.csv"
    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["page_id", "gold_route_label", "review_status", "review_notes"])
        writer.writeheader()
        writer.writerow({"page_id": "p2", "gold_route_label": "table_or_index", "review_status": "verified", "review_notes": "looks like index"})

    payload = build_gold_label_decision_merge(
        auto_review_seed_path=seed_path,
        high_priority_review_csv=review,
        output_dir=tmp_path / "out",
        quality=True,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["seed_record_count"] == 2
    assert payload["summary"]["final_gold_route_label_count"] == 2
    assert payload["summary"]["unresolved_human_review_count"] == 0
    assert payload["summary"]["decision_source_counts"] == {"auto_seeded": 1, "human_review": 1}
    labels = {r["page_id"]: r["final_gold_route_label"] for r in payload["records"]}
    assert labels == {"p1": "cover_or_title_page", "p2": "table_or_index"}
    assert (tmp_path / "out" / "trace_net_gold_label_decision_merge_v1_final_labels.csv").exists()
    assert (tmp_path / "out" / "trace_net_gold_label_decision_merge_v1_unresolved_review_queue.csv").exists()


def test_unreviewed_unseeded_pages_stay_unresolved(tmp_path):
    seed_path = _seed(tmp_path / "seed.json")
    payload = build_gold_label_decision_merge(
        auto_review_seed_path=seed_path,
        output_dir=tmp_path / "out",
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["final_gold_route_label_count"] == 1
    assert payload["summary"]["unresolved_human_review_count"] == 1
    unresolved = payload["unresolved_records"]
    assert unresolved[0]["page_id"] == "p2"


def test_invalid_human_label_fails_quality(tmp_path):
    seed_path = _seed(tmp_path / "seed.json")
    review = tmp_path / "bad.csv"
    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["page_id", "gold_route_label"])
        writer.writeheader()
        writer.writerow({"page_id": "p2", "gold_route_label": "not_a_route"})

    payload = build_gold_label_decision_merge(
        auto_review_seed_path=seed_path,
        high_priority_review_csv=review,
        output_dir=tmp_path / "out",
        quality=True,
    )
    assert payload["quality_status"] == "FAIL"
    assert payload["summary"]["invalid_human_label_count"] == 1
