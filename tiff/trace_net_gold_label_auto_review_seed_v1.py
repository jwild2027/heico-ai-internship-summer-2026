from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MODULE = "trace_net_gold_label_auto_review_seed_v1"
STATUS = "TRACE_NET_GOLD_LABEL_AUTO_REVIEW_SEED_BUILT"
VERSION = "v1"

CANONICAL_LABELS = {
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

SAFE_AUTO_SEED_LABELS = {
    "blank_candidate",
    "cover_or_title_page",
    "detailed_parts_list",
    "image_visual_diagram",
    "procedure_or_description",
    "table_or_index",
}

HEADER = [
    "page_number",
    "page_id",
    "legacy_route",
    "suggested_canonical_route",
    "suggested_route_confidence",
    "auto_seed_status",
    "auto_seeded_gold_route_label",
    "human_review_required",
    "seed_reasons",
    "review_priority",
    "ocr_word_count",
    "part_number_count",
    "source_image_path",
    "ocr_sample_text",
    "review_notes",
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["seed_reasons"] = "; ".join(record.get("seed_reasons") or [])
            row["ocr_sample_text"] = (record.get("ocr_sample_text") or "").replace("\r", " ").replace("\n", " ")
            writer.writerow(row)


def _write_markdown(path: Path, payload: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Gold Label Auto Review Seed v1",
        "",
        "This artifact auto-seeds only high-confidence obvious route labels. It does not mutate the source workbook.",
        "",
        "## Summary",
        "",
    ]
    for key in sorted(summary):
        lines.append(f"- **{key}**: `{summary[key]}`")
    lines.extend(["", "## First records", ""])
    for record in records[:20]:
        lines.append(
            f"- p{record.get('page_number')}: suggested=`{record.get('suggested_canonical_route')}`, "
            f"seed=`{record.get('auto_seeded_gold_route_label')}`, "
            f"status=`{record.get('auto_seed_status')}`, review=`{record.get('human_review_required')}`"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _contains_any(text: str, needles: Sequence[str]) -> bool:
    lower = text.lower()
    return any(needle.lower() in lower for needle in needles)


def _seed_decision(record: Mapping[str, Any], *, seed_medium_confidence_blanks: bool) -> tuple[str, str, bool, str, list[str]]:
    """Return status, seeded label, review flag, priority, reasons."""
    suggested = _text(record.get("suggested_canonical_route"))
    confidence = _text(record.get("suggested_route_confidence"))
    legacy = _text(record.get("legacy_route"))
    words = _safe_int(record.get("ocr_word_count"))
    parts = _safe_int(record.get("part_number_count"))
    sample = _text(record.get("ocr_sample_text"))
    reasons = [str(r) for r in (record.get("suggested_route_reasons") or [])]
    reason_text = " ".join(reasons + [sample])

    if suggested not in CANONICAL_LABELS:
        return "blocked_invalid_suggested_label", "", True, "critical", ["suggested_label_not_in_taxonomy"]

    # Never auto-seed mixed/review_required/normal_text until human confirms. These are often semantically subtle.
    if suggested in {"mixed_text_and_figure", "review_required", "normal_text"}:
        return "needs_human_review", "", True, "medium", ["semantic_or_mixed_route_requires_human_review"]

    if suggested == "blank_candidate":
        if words == 0 or (seed_medium_confidence_blanks and words <= 2):
            return "auto_seeded", "blank_candidate", False, "low", ["blank_candidate_empty_or_near_empty_ocr"]
        return "needs_human_review", "", True, "high", ["blank_candidate_has_ocr_text"]

    if suggested == "cover_or_title_page":
        if confidence == "high" and words <= 150 and parts == 0 and _contains_any(reason_text, ["publication", "cover", "title", "revision", "manual"]):
            return "auto_seeded", "cover_or_title_page", False, "low", ["high_confidence_publication_identity_page"]
        return "needs_human_review", "", True, "medium", ["front_matter_not_obvious_enough"]

    if suggested == "image_visual_diagram":
        if confidence == "high" and legacy == "image_visual" and words <= 120 and parts <= 2:
            return "auto_seeded", "image_visual_diagram", False, "low", ["legacy_image_visual_high_confidence_sparse_text"]
        return "needs_human_review", "", True, "high", ["visual_diagram_requires_manual_confirmation"]

    if suggested == "detailed_parts_list":
        if confidence == "high" and (parts >= 8 or _contains_any(reason_text, ["high_part_number_density", "detailed_parts_list_candidate", "nomenclature", "assy number", "part number"])):
            return "auto_seeded", "detailed_parts_list", False, "low", ["high_confidence_part_number_or_ipl_structure"]
        return "needs_human_review", "", True, "medium", ["detailed_parts_list_not_strong_enough"]

    if suggested == "table_or_index":
        if confidence == "high" and parts == 0 and _contains_any(reason_text, ["lep", "index", "issued", "inserted", "table_index_terms", "page date", "vendor"]):
            return "auto_seeded", "table_or_index", False, "low", ["high_confidence_index_or_table_page"]
        return "needs_human_review", "", True, "medium", ["table_or_index_medium_or_ambiguous"]

    if suggested == "procedure_or_description":
        if confidence == "high" and parts <= 1 and words >= 120 and _contains_any(reason_text, ["procedure", "description", "paragraph", "general", "operation", "installation", "removal", "inspection"]):
            return "auto_seeded", "procedure_or_description", False, "low", ["high_confidence_procedure_or_description_prose"]
        return "needs_human_review", "", True, "medium", ["procedure_or_description_not_strong_enough"]

    return "needs_human_review", "", True, "medium", ["no_auto_seed_rule_matched"]


def _seed_record(record: Mapping[str, Any], *, seed_medium_confidence_blanks: bool) -> dict[str, Any]:
    status, label, review, priority, seed_reasons = _seed_decision(record, seed_medium_confidence_blanks=seed_medium_confidence_blanks)
    out = dict(record)
    out["auto_seed_status"] = status
    out["auto_seeded_gold_route_label"] = label
    out["gold_route_label"] = label
    out["human_review_required"] = review
    out["review_status"] = "auto_seeded_verified_candidate" if status == "auto_seeded" else "needs_human_review"
    out["review_priority"] = priority
    out["seed_reasons"] = seed_reasons
    out["answer_permission"] = False
    out["can_answer_directly"] = False
    out["can_prove_claims"] = False
    out["source_truth_mutation_allowed"] = False
    out["unsafe_record"] = False
    return out


def _count(records: Sequence[Mapping[str, Any]], field: str, value: Any = None) -> int:
    if value is None:
        return sum(1 for r in records if r.get(field))
    return sum(1 for r in records if r.get(field) == value)


def _value_counts(records: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        value = str(r.get(field))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def build_gold_label_auto_review_seed(
    *,
    gold_label_workbook: str | Path,
    output_dir: str | Path,
    min_auto_seed_rows: int = 1,
    seed_medium_confidence_blanks: bool = True,
    quality: bool = False,
) -> dict[str, Any]:
    source_path = Path(gold_label_workbook)
    output_dir = Path(output_dir)
    source = _load_json(source_path)
    source_records = list(source.get("records") or [])

    records = [_seed_record(r, seed_medium_confidence_blanks=seed_medium_confidence_blanks) for r in source_records]
    auto_seeded = [r for r in records if r.get("auto_seed_status") == "auto_seeded"]
    human_review = [r for r in records if r.get("human_review_required")]

    unsafe_count = _count(records, "unsafe_record", True)
    answer_permission_count = _count(records, "answer_permission", True)
    can_answer_directly_count = _count(records, "can_answer_directly", True)
    can_prove_claims_count = _count(records, "can_prove_claims", True)
    source_truth_mutation_allowed_count = _count(records, "source_truth_mutation_allowed", True)

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_gold_label_workbook": str(source_path),
        "source_gold_label_workbook_quality_status": source.get("quality_status"),
        "source_review_row_count": len(source_records),
        "seed_record_count": len(records),
        "auto_seeded_gold_route_count": len(auto_seeded),
        "human_review_required_count": len(human_review),
        "auto_seed_status_counts": _value_counts(records, "auto_seed_status"),
        "auto_seeded_label_counts": _value_counts(auto_seeded, "auto_seeded_gold_route_label"),
        "suggested_route_counts": _value_counts(records, "suggested_canonical_route"),
        "review_priority_counts": _value_counts(records, "review_priority"),
        "ready_for_human_review_reduction": len(auto_seeded) >= min_auto_seed_rows,
        "workbook_path": str(output_dir / "trace_net_gold_label_auto_review_seed_v1.csv"),
        "unsafe_record_count": unsafe_count,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": can_answer_directly_count,
        "can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    failures: list[str] = []
    if source.get("quality_status") != "PASS":
        failures.append("source gold label workbook quality_status is not PASS")
    if not records:
        failures.append("no seed records built")
    if len(auto_seeded) < min_auto_seed_rows:
        failures.append("not enough auto-seeded rows")
    if unsafe_count:
        failures.append("unsafe records present")
    if answer_permission_count or can_answer_directly_count or can_prove_claims_count:
        failures.append("answer permission/direct answering/proof flags must remain false")
    if source_truth_mutation_allowed_count:
        failures.append("source truth mutation allowed")

    quality_status = "PASS" if not failures else "FAIL"
    payload = {
        "status": STATUS,
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "records": records,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "trace_net_gold_label_auto_review_seed_v1.json", payload)
    _write_jsonl(output_dir / "trace_net_gold_label_auto_review_seed_v1_records.jsonl", records)
    _write_csv(output_dir / "trace_net_gold_label_auto_review_seed_v1.csv", records)
    _write_markdown(output_dir / "trace_net_gold_label_auto_review_seed_v1.md", payload, records)
    _write_json(output_dir / "trace_net_gold_label_auto_review_seed_v1_summary.json", summary)
    if quality:
        _write_json(output_dir / "trace_net_gold_label_auto_review_seed_v1_quality_check.json", payload)

    print(f"Status: {STATUS}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return payload


def check_gold_label_auto_review_seed_quality(
    *,
    report_path: str | Path,
    min_seed_records: int = 1,
    min_auto_seeded: int = 1,
    max_human_review_required: int | None = None,
    require_source_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    max_unsafe: int | None = None,
    write_json: bool = False,
) -> dict[str, Any]:
    report_path = Path(report_path)
    payload = _load_json(report_path)
    summary = dict(payload.get("summary") or {})
    failures = list(payload.get("failures") or [])

    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if summary.get("seed_record_count", 0) < min_seed_records:
        failures.append("not enough seed records")
    if summary.get("auto_seeded_gold_route_count", 0) < min_auto_seeded:
        failures.append("not enough auto-seeded gold routes")
    if max_human_review_required is not None and summary.get("human_review_required_count", 0) > max_human_review_required:
        failures.append("too many human-review-required rows")
    if require_source_quality_pass and summary.get("source_gold_label_workbook_quality_status") != "PASS":
        failures.append("source gold label workbook quality_status is not PASS")
    if max_unsafe is not None and summary.get("unsafe_record_count", 0) > max_unsafe:
        failures.append("too many unsafe records")
    if require_no_answer_permission:
        if summary.get("answer_permission_count", 0) or summary.get("can_answer_directly_count", 0) or summary.get("can_prove_claims_count", 0):
            failures.append("answer permission/direct answer/proof flags are present")
    if require_no_source_truth_mutation and summary.get("source_truth_mutation_allowed_count", 0):
        failures.append("source truth mutation allowed")
    if require_no_write_attempts:
        for key in ["postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]:
            if summary.get(key, 0):
                failures.append(f"{key} is nonzero")

    quality_status = "PASS" if not failures else "FAIL"
    check = {
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
    }
    if write_json:
        out = report_path.with_name(report_path.stem + "_quality_check.json")
        _write_json(out, check)
        print("Wrote:", out)
    print("Quality status:", quality_status)
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return check


def main_build(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net gold label auto-review seed artifact.")
    parser.add_argument("--gold-label-workbook", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-auto-seed-rows", type=int, default=1)
    parser.add_argument("--no-seed-medium-confidence-blanks", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_gold_label_auto_review_seed(
        gold_label_workbook=args.gold_label_workbook,
        output_dir=args.output_dir,
        min_auto_seed_rows=args.min_auto_seed_rows,
        seed_medium_confidence_blanks=not args.no_seed_medium_confidence_blanks,
        quality=args.quality,
    )


def main_check(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net gold label auto-review seed quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-seed-records", type=int, default=1)
    parser.add_argument("--min-auto-seeded", type=int, default=1)
    parser.add_argument("--max-human-review-required", type=int)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    return check_gold_label_auto_review_seed_quality(
        report_path=args.report_path,
        min_seed_records=args.min_seed_records,
        min_auto_seeded=args.min_auto_seeded,
        max_human_review_required=args.max_human_review_required,
        require_source_quality_pass=args.require_source_quality_pass,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
        write_json=args.write_json,
    )


if __name__ == "__main__":
    main_build()
