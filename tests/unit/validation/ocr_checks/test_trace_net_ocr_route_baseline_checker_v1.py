"""Patch 0 — validate the frozen 509 baseline JSON and the regression checker."""
from pathlib import Path

from src.trace_net.validation.trace_net_ocr_route_baseline_checker_v1 import (
    COARSE_ROUTES,
    check_acceptance_gates,
    evaluate,
    load_baseline,
    to_coarse_route,
)

BASELINE = Path("tests/data/trace_net_ocr_route_baseline_509_v1.json")


def test_baseline_has_exactly_509_unique_pages_no_gaps():
    records = load_baseline(BASELINE)
    assert len(records) == 509
    pages = [r["page_number"] for r in records]
    ids = [r["page_id"] for r in records]
    assert sorted(pages) == list(range(1, 510))  # no missing, no gap
    assert len(set(pages)) == 509 and len(set(ids)) == 509  # no duplicates


def test_baseline_distribution_matches_manual_counts():
    records = load_baseline(BASELINE)
    counts = {}
    for r in records:
        counts[r["expected_coarse_route"]] = counts.get(r["expected_coarse_route"], 0) + 1
    assert counts == {"normal_text": 38, "blank_candidate": 14, "table": 298, "image_visual": 159}
    assert set(counts) <= set(COARSE_ROUTES)


def test_baseline_stores_labels_only_no_ocr_bytes():
    records = load_baseline(BASELINE)
    r = records[0]
    assert set(r) == {"page_number", "page_id", "expected_coarse_route", "expected_subtype"}


def test_fine_taxonomy_maps_to_coarse_routes():
    assert to_coarse_route("cover_or_title_page") == "normal_text"
    assert to_coarse_route("procedure_or_description") == "normal_text"
    assert to_coarse_route("detailed_parts_list") == "table"
    assert to_coarse_route("table_or_index") == "table"
    assert to_coarse_route("image_visual_diagram") == "image_visual"
    assert to_coarse_route("mixed_text_and_figure") == "image_visual"
    assert to_coarse_route("blank_candidate") == "blank_candidate"


def test_review_required_is_kept_visible_not_counted_as_success():
    assert to_coarse_route("review_required") == "review_required"
    baseline = [{"page_number": 1, "page_id": "p1", "expected_coarse_route": "table", "expected_subtype": ""}]
    report = evaluate(baseline, {1: "review_required"})
    assert report["exact_matches"] == 0
    assert report["review_required_count"] == 1
    assert report["overall_coarse_route_accuracy"] == 0.0


def test_evaluate_reports_targeted_misroute_rates_and_recall():
    baseline = [
        {"page_number": 1, "page_id": "p1", "expected_coarse_route": "image_visual", "expected_subtype": ""},
        {"page_number": 2, "page_id": "p2", "expected_coarse_route": "image_visual", "expected_subtype": ""},
        {"page_number": 3, "page_id": "p3", "expected_coarse_route": "normal_text", "expected_subtype": ""},
        {"page_number": 4, "page_id": "p4", "expected_coarse_route": "table", "expected_subtype": ""},
        {"page_number": 5, "page_id": "p5", "expected_coarse_route": "blank_candidate", "expected_subtype": ""},
    ]
    # p1 diagram misrouted to table; p2 correct; p3 prose misrouted to table; p4 table ok; p5 blank ok.
    preds = {1: "table", 2: "image_visual_diagram", 3: "detailed_parts_list", 4: "table_or_index", 5: "blank_candidate"}
    report = evaluate(baseline, preds)
    assert report["exact_matches"] == 3
    assert report["overall_coarse_route_accuracy"] == 0.6
    assert report["image_visual_to_table_count"] == 1
    assert report["image_visual_to_table_rate"] == 0.5
    assert report["normal_text_to_table_count"] == 1
    assert report["normal_text_to_table_rate"] == 1.0
    assert report["table_recall"] == 1.0
    assert report["blank_recall"] == 1.0
    assert report["confusion_matrix"]["image_visual"]["table"] == 1


def test_evaluate_counts_missing_and_extra_records():
    baseline = [
        {"page_number": 1, "page_id": "p1", "expected_coarse_route": "table", "expected_subtype": ""},
        {"page_number": 2, "page_id": "p2", "expected_coarse_route": "table", "expected_subtype": ""},
    ]
    report = evaluate(baseline, {1: "table", 3: "table"})  # page 2 missing, page 3 extra
    assert report["missing_page_records"] == 1 and 2 in report["missing_pages"]
    assert report["extra_or_duplicate_page_records"] == 1 and 3 in report["extra_pages"]


def test_acceptance_gates_helper():
    baseline = load_baseline(BASELINE)
    perfect = {r["page_number"]: r["expected_coarse_route"] for r in baseline}
    gates = check_acceptance_gates(evaluate(baseline, perfect))
    assert gates["all_passed"] is True
    assert gates["accuracy_at_least_95"] and gates["blank_recall_100"]
