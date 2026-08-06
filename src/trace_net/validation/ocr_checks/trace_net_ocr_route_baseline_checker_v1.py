"""Patch 0 — compact 509-page OCR route regression checker.

Compares predicted page routes against the frozen manual baseline
(``tests/data/trace_net_ocr_route_baseline_509_v1.json``) and reports coverage,
accuracy, a confusion matrix, and the specific error rates the OCR patch targets
(image_visual -> table, normal_text -> table, table recall, blank recall).

The active resolver uses a finer taxonomy; this checker maps it to the four
coarse baseline routes for comparison ONLY. ``review_required`` is kept visible
as its own class and is never silently counted as a success.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

COARSE_ROUTES: tuple[str, ...] = ("blank_candidate", "normal_text", "table", "image_visual")
REVIEW_REQUIRED = "review_required"

# Finer resolver taxonomy -> coarse baseline route (comparison only).
_FINE_TO_COARSE: dict[str, str] = {
    "blank_candidate": "blank_candidate",
    "cover_or_title_page": "normal_text",
    "normal_text": "normal_text",
    "procedure_or_description": "normal_text",
    "table_or_index": "table",
    "detailed_parts_list": "table",
    "table": "table",
    "image_visual_diagram": "image_visual",
    "mixed_text_and_figure": "image_visual",
    "image_visual": "image_visual",
}


def to_coarse_route(route: Any) -> str:
    """Map a (fine or coarse) route to a coarse baseline route.

    ``review_required`` stays visible as itself; any other/unknown label is
    returned unchanged so it appears distinctly in the confusion matrix rather
    than being hidden inside a success bucket.
    """
    key = str(route or "").strip()
    if not key:
        return "missing"
    if key == REVIEW_REQUIRED:
        return REVIEW_REQUIRED
    return _FINE_TO_COARSE.get(key, key)


def load_baseline(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = data["records"] if isinstance(data, Mapping) else data
    return [dict(r) for r in records]


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def evaluate(
    baseline_records: list[dict[str, Any]],
    predictions: Mapping[int, Any],
) -> dict[str, Any]:
    """Compare a {page_number: predicted_route} mapping to the baseline.

    Returns coverage, exact-match accuracy, per-class prediction counts, a coarse
    confusion matrix, the targeted misroute rates, per-class recall, and the
    missing / duplicate / review-required bookkeeping.
    """
    total = len(baseline_records)
    expected_by_page = {int(r["page_number"]): str(r["expected_coarse_route"]) for r in baseline_records}

    confusion: dict[str, Counter] = {r: Counter() for r in COARSE_ROUTES}
    prediction_counts: Counter = Counter()
    matched = 0
    missing_pages: list[int] = []
    review_pages: list[int] = []

    for page, expected in expected_by_page.items():
        if page not in predictions:
            missing_pages.append(page)
            confusion[expected]["missing"] += 1
            prediction_counts["missing"] += 1
            continue
        pred_coarse = to_coarse_route(predictions[page])
        prediction_counts[pred_coarse] += 1
        if pred_coarse == REVIEW_REQUIRED:
            review_pages.append(page)
        confusion[expected][pred_coarse] += 1
        if pred_coarse == expected:
            matched += 1

    # predictions supplied for pages not in the baseline (duplicates/extras)
    extra_pages = sorted(set(int(p) for p in predictions) - set(expected_by_page))
    baseline_counts = Counter(expected_by_page.values())

    def _confused(expected: str, predicted: str) -> int:
        return int(confusion.get(expected, Counter()).get(predicted, 0))

    return {
        "total_pages": total,
        "pages_with_prediction": total - len(missing_pages),
        "missing_page_records": len(missing_pages),
        "missing_pages": missing_pages[:50],
        "extra_or_duplicate_page_records": len(extra_pages),
        "extra_pages": extra_pages[:50],
        "exact_matches": matched,
        "overall_coarse_route_accuracy": _rate(matched, total),
        "baseline_counts": dict(baseline_counts),
        "prediction_counts": dict(prediction_counts),
        "confusion_matrix": {exp: dict(row) for exp, row in confusion.items()},
        "image_visual_to_table_count": _confused("image_visual", "table"),
        "image_visual_to_table_rate": _rate(_confused("image_visual", "table"), baseline_counts.get("image_visual", 0)),
        "normal_text_to_table_count": _confused("normal_text", "table"),
        "normal_text_to_table_rate": _rate(_confused("normal_text", "table"), baseline_counts.get("normal_text", 0)),
        "table_recall": _rate(_confused("table", "table"), baseline_counts.get("table", 0)),
        "blank_recall": _rate(_confused("blank_candidate", "blank_candidate"), baseline_counts.get("blank_candidate", 0)),
        "review_required_count": len(review_pages),
        "review_required_pages": review_pages[:50],
    }


def check_acceptance_gates(report: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate the Patch acceptance gates against an ``evaluate`` report."""
    gates = {
        "page_coverage_full": report["pages_with_prediction"] == report["total_pages"],
        "no_missing_records": report["missing_page_records"] == 0,
        "no_duplicate_records": report["extra_or_duplicate_page_records"] == 0,
        "blank_recall_100": report["blank_recall"] >= 1.0,
        "accuracy_at_least_95": report["overall_coarse_route_accuracy"] >= 0.95,
        "image_to_table_at_most_5": report["image_visual_to_table_rate"] <= 0.05,
        "normal_to_table_at_most_5": report["normal_text_to_table_rate"] <= 0.05,
        "table_recall_at_least_95": report["table_recall"] >= 0.95,
    }
    gates["all_passed"] = all(gates.values())
    return gates
