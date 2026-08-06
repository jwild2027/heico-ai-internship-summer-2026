import json
from pathlib import Path

from tiff.trace_net_gold_label_auto_review_seed_v1 import build_gold_label_auto_review_seed


def _source(path: Path):
    payload = {
        "quality_status": "PASS",
        "records": [
            {
                "page_number": 1,
                "page_id": "p1",
                "legacy_route": "table",
                "suggested_canonical_route": "cover_or_title_page",
                "suggested_route_confidence": "high",
                "suggested_route_reasons": ["publication_identity_terms"],
                "ocr_word_count": 60,
                "part_number_count": 0,
                "ocr_sample_text": "COMPONENT MAINTENANCE MANUAL REVISION 4",
            },
            {
                "page_number": 2,
                "page_id": "p2",
                "legacy_route": "blank_candidate",
                "suggested_canonical_route": "blank_candidate",
                "suggested_route_confidence": "high",
                "suggested_route_reasons": ["empty_or_near_empty_ocr"],
                "ocr_word_count": 0,
                "part_number_count": 0,
            },
            {
                "page_number": 17,
                "page_id": "p17",
                "legacy_route": "image_visual",
                "suggested_canonical_route": "image_visual_diagram",
                "suggested_route_confidence": "high",
                "suggested_route_reasons": ["figure_or_visual_label_signal"],
                "ocr_word_count": 39,
                "part_number_count": 0,
            },
            {
                "page_number": 99,
                "page_id": "p99",
                "legacy_route": "table",
                "suggested_canonical_route": "mixed_text_and_figure",
                "suggested_route_confidence": "medium",
                "suggested_route_reasons": ["visual_signal_present", "meaningful_prose_present"],
                "ocr_word_count": 200,
                "part_number_count": 0,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_auto_seeds_only_safe_high_confidence_rows(tmp_path):
    source = tmp_path / "gold.json"
    _source(source)
    out = tmp_path / "out"
    payload = build_gold_label_auto_review_seed(
        gold_label_workbook=source,
        output_dir=out,
        min_auto_seed_rows=3,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["seed_record_count"] == 4
    assert summary["auto_seeded_gold_route_count"] == 3
    assert summary["human_review_required_count"] == 1
    labels = {r["page_id"]: r["auto_seeded_gold_route_label"] for r in payload["records"]}
    assert labels["p1"] == "cover_or_title_page"
    assert labels["p2"] == "blank_candidate"
    assert labels["p17"] == "image_visual_diagram"
    assert labels["p99"] == ""
    assert (out / "trace_net_gold_label_auto_review_seed_v1.json").exists()
    assert (out / "trace_net_gold_label_auto_review_seed_v1.csv").exists()


def test_invalid_suggested_label_blocks_auto_seed(tmp_path):
    source = tmp_path / "gold.json"
    source.write_text(json.dumps({"quality_status": "PASS", "records": [{"page_id": "bad", "suggested_canonical_route": "not_a_label"}]}), encoding="utf-8")
    payload = build_gold_label_auto_review_seed(gold_label_workbook=source, output_dir=tmp_path / "out")
    assert payload["quality_status"] == "FAIL"
    assert payload["records"][0]["auto_seed_status"] == "blocked_invalid_suggested_label"
    assert payload["records"][0]["human_review_required"] is True
