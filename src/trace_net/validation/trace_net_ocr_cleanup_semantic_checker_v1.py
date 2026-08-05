"""TRACE-Net OCR Patch 5.1 semantic cleanup acceptance checker."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

INDEX_SUBTYPES = frozenset({"vendor_index", "numerical_index", "table_of_contents"})
LEP_SUBTYPE = "list_of_effective_pages"
REVISION_SUBTYPE = "revision_or_service_record"
VISUAL_ROUTES = frozenset({"image_visual", "mixed_text_and_figure"})
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0


def _precision_recall(expected: set[int], predicted: set[int]) -> dict[str, Any]:
    true_positive = len(expected & predicted)
    false_positive = len(predicted - expected)
    false_negative = len(expected - predicted)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": _rate(true_positive, true_positive + false_positive),
        "recall": _rate(true_positive, true_positive + false_negative),
        "false_positive_pages": sorted(predicted - expected),
        "false_negative_pages": sorted(expected - predicted),
    }


def evaluate_cleanup_semantics(
    cleanup_records: Iterable[Mapping[str, Any]],
    baseline_records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [dict(row) for row in cleanup_records]
    baseline = [dict(row) for row in baseline_records]
    baseline_by_page = {int(row["page_number"]): row for row in baseline}

    expected_index = {
        page for page, row in baseline_by_page.items()
        if row.get("expected_subtype") in INDEX_SUBTYPES
    }
    expected_lep = {
        page for page, row in baseline_by_page.items()
        if row.get("expected_subtype") == LEP_SUBTYPE
    }
    expected_revision = {
        page for page, row in baseline_by_page.items()
        if row.get("expected_subtype") == REVISION_SUBTYPE
    }

    predicted_index: set[int] = set()
    predicted_lep: set[int] = set()
    predicted_revision: set[int] = set()
    raw_mismatch_pages: list[int] = []
    part_loss_pages: list[int] = []
    suspicious_removal_pages: set[int] = set()
    retained_nonvisual_pages: set[int] = set()
    invalid_blank_sidecar_pages: set[int] = set()
    safety_violation_pages: set[int] = set()

    for row in rows:
        page = int(row.get("canonical_page_number") or row.get("page_number") or 0)
        cleanup = row.get("cleanup_extraction") or {}
        route = str(
            row.get("canonical_final_route")
            or cleanup.get("final_route_for_cleanup")
            or row.get("accepted_route")
            or ""
        )
        raw = str(row.get("primary_ocr_text") or "")
        cleanup_raw = str(cleanup.get("raw_ocr_text") or "")
        cleaned = str(cleanup.get("cleaned_ocr_text") or "")
        if raw != cleanup_raw:
            raw_mismatch_pages.append(page)
        if not set(PART_RE.findall(raw)).issubset(set(PART_RE.findall(cleaned))):
            part_loss_pages.append(page)

        if cleanup.get("is_index_or_toc") is True:
            predicted_index.add(page)
        if cleanup.get("is_list_of_effective_pages") is True:
            predicted_lep.add(page)
        if (cleanup.get("revision_grid_extraction") or {}).get("is_revision_grid") is True:
            predicted_revision.add(page)

        for operation in cleanup.get("cleanup_operations_applied") or []:
            if (
                isinstance(operation, Mapping)
                and operation.get("operation") == "remove_repeated_header_footer"
                and operation.get("confirmed_boilerplate") is not True
            ):
                suspicious_removal_pages.add(page)

        retained = int(cleanup.get("retained_callout_candidate_count") or 0)
        if retained and route not in VISUAL_ROUTES:
            retained_nonvisual_pages.add(page)

        sidecar_status = str(row.get("ocr_sidecar_status") or "")
        expected_route = str((baseline_by_page.get(page) or {}).get("expected_coarse_route") or "")
        if sidecar_status.startswith("missing") and not (expected_route == "blank_candidate" and raw == ""):
            invalid_blank_sidecar_pages.add(page)

        if any(
            bool(cleanup.get(key))
            for key in ("answer_permission", "can_prove_claims", "source_truth_mutation_allowed")
        ):
            safety_violation_pages.add(page)
        if any(
            int(cleanup.get(key) or 0) != 0
            for key in (
                "postgres_write_attempt_count",
                "qdrant_write_attempt_count",
                "opensearch_write_attempt_count",
            )
        ):
            safety_violation_pages.add(page)

    index_metrics = _precision_recall(expected_index, predicted_index)
    lep_metrics = _precision_recall(expected_lep, predicted_lep)
    revision_metrics = _precision_recall(expected_revision, predicted_revision)

    metrics = {
        "record_count": len(rows),
        "baseline_count": len(baseline),
        "index": index_metrics,
        "list_of_effective_pages": lep_metrics,
        "revision_grid": revision_metrics,
        "raw_mismatch_pages": sorted(raw_mismatch_pages),
        "part_loss_pages": sorted(part_loss_pages),
        "suspicious_removal_pages": sorted(suspicious_removal_pages),
        "retained_nonvisual_pages": sorted(retained_nonvisual_pages),
        "invalid_blank_sidecar_pages": sorted(invalid_blank_sidecar_pages),
        "safety_violation_pages": sorted(safety_violation_pages),
    }
    gates = {
        "coverage_matches_baseline": len(rows) == len(baseline),
        "index_precision_at_least_98": index_metrics["precision"] >= 0.98,
        "index_recall_at_least_98": index_metrics["recall"] >= 0.98,
        "lep_precision_100": lep_metrics["precision"] >= 1.0,
        "lep_recall_100": lep_metrics["recall"] >= 1.0,
        "revision_precision_100": revision_metrics["precision"] >= 1.0,
        "revision_recall_100": revision_metrics["recall"] >= 1.0,
        "raw_ocr_preserved_all": not raw_mismatch_pages,
        "part_numbers_preserved_all": not part_loss_pages,
        "only_confirmed_boilerplate_removed": not suspicious_removal_pages,
        "no_retained_callouts_on_nonvisual_routes": not retained_nonvisual_pages,
        "blank_sidecar_exception_valid": not invalid_blank_sidecar_pages,
        "safety_contract_clean": not safety_violation_pages,
    }
    gates["all_passed"] = all(gates.values())
    return {"quality_status": "PASS" if gates["all_passed"] else "FAIL", "metrics": metrics, "gates": gates}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup-records", type=Path, required=True)
    parser.add_argument("--baseline-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    cleanup = _read_jsonl(args.cleanup_records)
    baseline_payload = json.loads(args.baseline_json.read_text(encoding="utf-8"))
    baseline = baseline_payload.get("records", baseline_payload)
    result = evaluate_cleanup_semantics(cleanup, baseline)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Quality status:", result["quality_status"])
    print(json.dumps(result["gates"], indent=2, sort_keys=True))
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
