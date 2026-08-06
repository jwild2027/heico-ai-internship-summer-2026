"""TRACE-Net Gold Label Decision Merge v1.

Merge auto-seeded route labels with optional human review CSV decisions into a final
page-route gold label artifact. This module is artifact-only: it does not mutate
source truth and does not write to Postgres, Qdrant, or OpenSearch.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

VERSION = "v1"
MODULE = "trace_net_gold_label_decision_merge_v1"
STATUS = "TRACE_NET_GOLD_LABEL_DECISION_MERGE_BUILT"
REPORT_NAME = "trace_net_gold_label_decision_merge_v1.json"
RECORDS_JSONL_NAME = "trace_net_gold_label_decision_merge_v1_records.jsonl"
FINAL_CSV_NAME = "trace_net_gold_label_decision_merge_v1_final_labels.csv"
UNRESOLVED_CSV_NAME = "trace_net_gold_label_decision_merge_v1_unresolved_review_queue.csv"
SUMMARY_NAME = "trace_net_gold_label_decision_merge_v1_summary.json"
QUALITY_NAME = "trace_net_gold_label_decision_merge_v1_quality_check.json"
MARKDOWN_NAME = "trace_net_gold_label_decision_merge_v1.md"

CANONICAL_ROUTE_LABELS = {
    "blank_candidate",
    "cover_or_title_page",
    "normal_text",
    "procedure_or_description",
    "table_or_index",
    "detailed_parts_list",
    "image_visual_diagram",
    "mixed_text_and_figure",
    "review_required",
}

GOLD_LABEL_COLUMNS = (
    "final_gold_route_label",
    "corrected_gold_route_label",
    "gold_route_label",
    "auto_seeded_gold_route_label",
)

REVIEW_STATUS_COLUMNS = (
    "review_status",
    "gold_review_status",
    "final_review_status",
)

REVIEW_NOTES_COLUMNS = (
    "review_notes",
    "gold_review_notes",
    "final_review_notes",
    "notes",
)

SAFETY_FALSE_FIELDS = {
    "unsafe_record": False,
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: list[Mapping[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Gold Label Decision Merge v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
    ]
    for key in sorted(summary):
        lines.append(f"- `{key}`: `{summary[key]}`")
    lines.extend([
        "",
        "## Safety",
        "",
        "This artifact grants no answer permission, performs no database writes, and does not mutate source truth.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _first_nonempty(row: Mapping[str, Any], columns: Iterable[str]) -> str:
    for column in columns:
        value = row.get(column)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _page_key(row: Mapping[str, Any]) -> str:
    page_id = str(row.get("page_id") or "").strip()
    if page_id:
        return page_id
    page_number = str(row.get("page_number") or row.get("canonical_page_number") or "").strip()
    return f"page:{page_number}" if page_number else ""


def _read_review_csv(path: Path) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            key = _page_key(row)
            if not key:
                continue
            label = _first_nonempty(row, GOLD_LABEL_COLUMNS)
            status = _first_nonempty(row, REVIEW_STATUS_COLUMNS)
            notes = _first_nonempty(row, REVIEW_NOTES_COLUMNS)
            # Do not treat auto-seeded labels inside review CSVs as human decisions unless
            # there is a real gold/corrected/final label column or explicit review status/note.
            human_label = _first_nonempty(row, ("final_gold_route_label", "corrected_gold_route_label", "gold_route_label"))
            rows[key] = {
                "source_review_file": str(path),
                "human_gold_route_label": human_label,
                "review_status": status,
                "review_notes": notes,
                "raw_label_value": label,
            }
    return rows


def _merge_review_rows(review_paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for path in review_paths:
        if path:
            merged.update(_read_review_csv(path))
    return merged


def _source_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records") or []
    if not isinstance(records, list):
        return []
    return [dict(record) for record in records if isinstance(record, Mapping)]


def _decision_for_record(record: Mapping[str, Any], human: Mapping[str, Any] | None) -> dict[str, Any]:
    suggested = str(record.get("suggested_canonical_route") or "").strip()
    seeded = str(record.get("auto_seeded_gold_route_label") or "").strip()
    human_label = str((human or {}).get("human_gold_route_label") or "").strip()
    review_status = str((human or {}).get("review_status") or record.get("review_status") or "").strip()
    review_notes = str((human or {}).get("review_notes") or record.get("review_notes") or "").strip()
    source_review_file = str((human or {}).get("source_review_file") or "").strip()

    invalid_human_label = bool(human_label and human_label not in CANONICAL_ROUTE_LABELS)
    if human_label and not invalid_human_label:
        final_label = human_label
        decision_source = "human_review"
        final_status = review_status or "human_reviewed"
        human_review_required = False
    elif seeded:
        final_label = seeded
        decision_source = "auto_seeded"
        final_status = "auto_seeded_pending_audit"
        human_review_required = False
    else:
        final_label = ""
        decision_source = "unresolved_human_review_required"
        final_status = review_status or "needs_human_review"
        human_review_required = True

    invalid_final_label = bool(final_label and final_label not in CANONICAL_ROUTE_LABELS)

    return {
        "page_id": record.get("page_id"),
        "page_number": record.get("page_number") or record.get("canonical_page_number"),
        "source_member": record.get("source_member"),
        "source_image_path": record.get("source_image_path"),
        "source_image_sha256": record.get("source_image_sha256"),
        "legacy_route": record.get("legacy_route"),
        "suggested_canonical_route": suggested,
        "suggested_route_confidence": record.get("suggested_route_confidence"),
        "suggested_route_reasons": record.get("suggested_route_reasons") or [],
        "auto_seeded_gold_route_label": seeded,
        "human_gold_route_label": human_label,
        "final_gold_route_label": final_label,
        "decision_source": decision_source,
        "final_review_status": final_status,
        "human_review_required": human_review_required,
        "review_priority": record.get("review_priority"),
        "review_notes": review_notes,
        "source_review_file": source_review_file,
        "invalid_human_label": invalid_human_label,
        "invalid_final_label": invalid_final_label,
        "ocr_word_count": record.get("ocr_word_count"),
        "ocr_text_char_count": record.get("ocr_text_char_count"),
        "part_number_count": record.get("part_number_count"),
        "part_number_tokens": record.get("part_number_tokens") or [],
        "ocr_sample_text": record.get("ocr_sample_text"),
        **SAFETY_FALSE_FIELDS,
    }


def _count_bool(records: Iterable[Mapping[str, Any]], key: str) -> int:
    return sum(1 for record in records if bool(record.get(key)))


def _quality_status(summary: Mapping[str, Any]) -> str:
    failures = _quality_failures(summary)
    return "PASS" if not failures else "FAIL"


def _quality_failures(summary: Mapping[str, Any], *, min_final_labels: int = 0, max_unresolved: int | None = None) -> list[str]:
    failures: list[str] = []
    if summary.get("source_auto_review_seed_quality_status") != "PASS":
        failures.append("source auto-review seed quality_status is not PASS")
    if summary.get("seed_record_count", 0) <= 0:
        failures.append("no seed records")
    if summary.get("invalid_final_label_count", 0) > 0:
        failures.append("invalid final gold labels present")
    if summary.get("invalid_human_label_count", 0) > 0:
        failures.append("invalid human gold labels present")
    if summary.get("unsafe_record_count", 0) > 0:
        failures.append("unsafe records present")
    for key in (
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        if summary.get(key, 0) > 0:
            failures.append(f"{key} is non-zero")
    if min_final_labels and summary.get("final_gold_route_label_count", 0) < min_final_labels:
        failures.append("not enough final gold labels")
    if max_unresolved is not None and summary.get("unresolved_human_review_count", 0) > max_unresolved:
        failures.append("too many unresolved human-review records")
    return failures


def build_gold_label_decision_merge(
    *,
    auto_review_seed_path: Path,
    output_dir: Path,
    high_priority_review_csv: Path | None = None,
    medium_priority_review_csv: Path | None = None,
    low_priority_audit_csv: Path | None = None,
    additional_review_csvs: list[Path] | None = None,
    min_final_labels: int = 0,
    max_unresolved: int | None = None,
    quality: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source = _read_json(auto_review_seed_path)
    records = _source_records(source)

    review_paths = [p for p in [high_priority_review_csv, medium_priority_review_csv, low_priority_audit_csv] if p]
    review_paths.extend(additional_review_csvs or [])
    human_reviews = _merge_review_rows(review_paths)

    merged_records = []
    for record in records:
        key = _page_key(record)
        merged_records.append(_decision_for_record(record, human_reviews.get(key)))

    unresolved = [r for r in merged_records if r.get("human_review_required")]
    final_records = [r for r in merged_records if r.get("final_gold_route_label")]

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_auto_review_seed": str(auto_review_seed_path),
        "source_auto_review_seed_quality_status": source.get("quality_status"),
        "seed_record_count": len(records),
        "human_review_file_count": len(review_paths),
        "human_review_rows_loaded_count": len(human_reviews),
        "final_gold_route_label_count": len(final_records),
        "unresolved_human_review_count": len(unresolved),
        "decision_source_counts": dict(Counter(r.get("decision_source") for r in merged_records)),
        "final_gold_route_label_counts": dict(Counter(r.get("final_gold_route_label") for r in final_records)),
        "suggested_route_counts": dict(Counter(r.get("suggested_canonical_route") for r in merged_records)),
        "invalid_human_label_count": _count_bool(merged_records, "invalid_human_label"),
        "invalid_final_label_count": _count_bool(merged_records, "invalid_final_label"),
        "unsafe_record_count": _count_bool(merged_records, "unsafe_record"),
        "answer_permission_count": _count_bool(merged_records, "answer_permission"),
        "can_answer_directly_count": _count_bool(merged_records, "can_answer_directly"),
        "can_prove_claims_count": _count_bool(merged_records, "can_prove_claims"),
        "source_truth_mutation_allowed_count": _count_bool(merged_records, "source_truth_mutation_allowed"),
        "postgres_write_attempt_count": _count_bool(merged_records, "postgres_write_attempt"),
        "qdrant_write_attempt_count": _count_bool(merged_records, "qdrant_write_attempt"),
        "opensearch_write_attempt_count": _count_bool(merged_records, "opensearch_write_attempt"),
        "final_labels_csv_path": str(output_dir / FINAL_CSV_NAME),
        "unresolved_review_queue_csv_path": str(output_dir / UNRESOLVED_CSV_NAME),
        "ready_for_route_accuracy_scoring": len(final_records) > 0,
        "ready_for_full_gold_lock": len(unresolved) == 0,
    }
    summary["quality_failures"] = _quality_failures(
        summary,
        min_final_labels=min_final_labels,
        max_unresolved=max_unresolved,
    )
    quality_status = "PASS" if not summary["quality_failures"] else "FAIL"

    csv_fields = [
        "page_number",
        "page_id",
        "source_member",
        "legacy_route",
        "suggested_canonical_route",
        "suggested_route_confidence",
        "auto_seeded_gold_route_label",
        "human_gold_route_label",
        "final_gold_route_label",
        "decision_source",
        "final_review_status",
        "human_review_required",
        "review_priority",
        "review_notes",
        "source_review_file",
        "ocr_word_count",
        "part_number_count",
        "source_image_path",
        "ocr_sample_text",
    ]

    payload = {
        "status": STATUS,
        "quality_status": quality_status,
        "summary": summary,
        "records": merged_records,
        "unresolved_records": unresolved,
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "source_truth_mutation": False,
            "answer_permission": False,
        },
    }

    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / RECORDS_JSONL_NAME, merged_records)
    _write_csv(output_dir / FINAL_CSV_NAME, merged_records, csv_fields)
    _write_csv(output_dir / UNRESOLVED_CSV_NAME, unresolved, csv_fields)
    _write_json(output_dir / SUMMARY_NAME, summary)
    _write_markdown(output_dir / MARKDOWN_NAME, payload)
    if quality:
        _write_json(output_dir / QUALITY_NAME, {"quality_status": quality_status, "summary": summary, "failures": summary["quality_failures"]})

    print(f"Status: {STATUS}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_gold_label_decision_merge_quality(
    *,
    report_path: Path,
    write_json: bool = False,
    min_seed_records: int = 0,
    min_final_labels: int = 0,
    max_unresolved: int | None = None,
    require_source_quality_pass: bool = False,
    require_decision_files: bool = False,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    max_unsafe: int | None = None,
) -> dict[str, Any]:
    payload = _read_json(report_path)
    summary = dict(payload.get("summary") or {})
    failures = list(summary.get("quality_failures") or [])

    if min_seed_records and summary.get("seed_record_count", 0) < min_seed_records:
        failures.append("not enough seed records")
    if min_final_labels and summary.get("final_gold_route_label_count", 0) < min_final_labels:
        failures.append("not enough final gold labels")
    if max_unresolved is not None and summary.get("unresolved_human_review_count", 0) > max_unresolved:
        failures.append("too many unresolved human-review records")
    if require_source_quality_pass and summary.get("source_auto_review_seed_quality_status") != "PASS":
        failures.append("source auto-review seed quality_status is not PASS")
    if require_decision_files:
        for key in ("final_labels_csv_path", "unresolved_review_queue_csv_path"):
            value = summary.get(key)
            if not value or not Path(value).exists():
                failures.append(f"missing decision file: {key}")
    if max_unsafe is not None and summary.get("unsafe_record_count", 0) > max_unsafe:
        failures.append("too many unsafe records")
    if require_no_answer_permission:
        for key in ("answer_permission_count", "can_answer_directly_count", "can_prove_claims_count"):
            if summary.get(key, 0) > 0:
                failures.append(f"{key} is non-zero")
    if require_no_source_truth_mutation and summary.get("source_truth_mutation_allowed_count", 0) > 0:
        failures.append("source truth mutation allowed")
    if require_no_write_attempts:
        for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
            if summary.get(key, 0) > 0:
                failures.append(f"{key} is non-zero")

    result = {
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "failures": failures,
    }
    if write_json:
        _write_json(report_path.with_name(QUALITY_NAME), result)
        print(f"Wrote: {report_path.with_name(QUALITY_NAME)}")
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net gold label decision merge v1")
    parser.add_argument("--auto-review-seed", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--high-priority-review-csv", type=Path)
    parser.add_argument("--medium-priority-review-csv", type=Path)
    parser.add_argument("--low-priority-audit-csv", type=Path)
    parser.add_argument("--additional-review-csv", action="append", type=Path, default=[])
    parser.add_argument("--min-final-labels", type=int, default=0)
    parser.add_argument("--max-unresolved", type=int)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_gold_label_decision_merge(
        auto_review_seed_path=args.auto_review_seed,
        output_dir=args.output_dir,
        high_priority_review_csv=args.high_priority_review_csv,
        medium_priority_review_csv=args.medium_priority_review_csv,
        low_priority_audit_csv=args.low_priority_audit_csv,
        additional_review_csvs=args.additional_review_csv,
        min_final_labels=args.min_final_labels,
        max_unresolved=args.max_unresolved,
        quality=args.quality,
    )


def main_check(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net gold label decision merge v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-seed-records", type=int, default=0)
    parser.add_argument("--min-final-labels", type=int, default=0)
    parser.add_argument("--max-unresolved", type=int)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-decision-files", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_gold_label_decision_merge_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_seed_records=args.min_seed_records,
        min_final_labels=args.min_final_labels,
        max_unresolved=args.max_unresolved,
        require_source_quality_pass=args.require_source_quality_pass,
        require_decision_files=args.require_decision_files,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":
    main_build()
