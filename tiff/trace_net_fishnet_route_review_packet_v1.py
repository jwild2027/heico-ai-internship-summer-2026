"""TRACE-Net Fishnet Route Review Packet v1.

This module builds a read-only review packet from the fishnet route signal
workbench. It is intentionally not a router and never authorizes route changes.

Purpose
-------
The fishnet workbench can surface many disagreements between the current
TRACE-Net page route manifest and fishnet OCR/grid route candidates. This module
selects a compact review set:

* all high-confidence disagreements, up to a configurable cap;
* representative examples from important route-pair groups;
* optionally additional review-required records.

The output is designed for human/visual review and future route hardening. It
contains OCR snippets, scores, confidence, safety fields, route-pair labels, and
candidate overlay paths when available.

Safety contract
---------------
No Postgres writes. No Qdrant writes. No OpenSearch writes. No source-truth
mutation. No answer permission. No route changes authorized. The packet is
review-only classifier diagnostics.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

VERSION = "trace_net_fishnet_route_review_packet_v1"
STATUS_BUILT = "FISHNET_ROUTE_REVIEW_PACKET_BUILT"
STATUS_CHECKED = "FISHNET_ROUTE_REVIEW_PACKET_QUALITY_CHECKED"

DEFAULT_FOCUS_ROUTE_PAIRS = [
    "blank_candidate->normal_text",
    "blank_candidate->table",
    "table->review_required",
    "image_visual->normal_text",
    "image_visual->review_required",
]

SAFETY_CONTRACT = {
    "artifact_authority": "route_review_packet_only",
    "route_change_authorized": False,
    "route_change_recommendation": "review_only",
    "can_answer_directly": False,
    "can_prove_claims": False,
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_allowed": False,
    "qdrant_write_allowed": False,
    "opensearch_write_allowed": False,
    "raw_scan_query_time_allowed": False,
    "requires_downstream_source_truth_confirmation": True,
    "guidance_only": True,
}


@dataclass(frozen=True)
class ReviewSelectionConfig:
    high_confidence_limit: int = 50
    representative_per_pair: int = 5
    review_required_limit: int = 25
    focus_route_pairs: tuple[str, ...] = tuple(DEFAULT_FOCUS_ROUTE_PAIRS)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def normalize_route(route: Any) -> str:
    if route is None:
        return "missing"
    text = str(route).strip()
    return text or "missing"


def route_pair(current_route: Any, fishnet_route: Any) -> str:
    return f"{normalize_route(current_route)}->{normalize_route(fishnet_route)}"


def page_number_from_id(page_id: Any) -> int | None:
    text = str(page_id or "")
    m = re.search(r"p(\d{6})$", text)
    if not m:
        m = re.search(r"(\d{1,6})$", text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def overlay_candidates(page_id: Any, overlays_dir: Path | None) -> list[str]:
    if overlays_dir is None:
        return []
    n = page_number_from_id(page_id)
    text = str(page_id or "")
    candidates: list[Path] = []
    # Common names from our generated overlay attempts and likely future names.
    stems = []
    if text:
        stems.extend([
            text,
            f"{text}_fishnet_overlay",
            f"fishnet_{text}",
            f"fishnet_overlay_{text}",
        ])
    if n is not None:
        stems.extend([
            f"source_p{n:06d}",
            f"source_p{n:06d}_fishnet_overlay",
            f"fishnet_source_p{n:06d}",
            f"fishnet_overlay_source_p{n:06d}",
            f"page_{n:06d}",
            f"p{n:06d}",
        ])
    for stem in stems:
        for suffix in (".png", ".jpg", ".jpeg", ".webp"):
            candidates.append(overlays_dir / f"{stem}{suffix}")
    existing = [str(p.as_posix()) for p in candidates if p.exists()]
    if existing:
        return existing
    # Return the most likely PNG path even if it does not exist, so review tools
    # know what to look for after overlay export is widened.
    if n is not None:
        return [str((overlays_dir / f"source_p{n:06d}_fishnet_overlay.png").as_posix())]
    if text:
        return [str((overlays_dir / f"{text}_fishnet_overlay.png").as_posix())]
    return []


def severity_rank(record: dict[str, Any]) -> tuple[int, float, int]:
    status = str(record.get("agreement_status") or "")
    severity = str(record.get("review_severity") or "")
    confidence = float(record.get("fishnet_route_confidence") or 0.0)
    text_len = int(record.get("fishnet_ocr_text_length") or 0)
    base = 0
    if status == "high_confidence_disagreement" or severity == "high":
        base = 4
    elif status == "fishnet_review_required" or severity == "review":
        base = 3
    elif status == "disagree" or severity == "medium":
        base = 2
    elif status == "agree" or severity == "ok":
        base = 1
    return (base, confidence, text_len)


def make_review_record(
    record: dict[str, Any],
    *,
    selection_reason: str,
    selection_rank: int,
    overlays_dir: Path | None,
) -> dict[str, Any]:
    current = normalize_route(record.get("current_route"))
    fishnet = normalize_route(record.get("fishnet_route_candidate"))
    pair = route_pair(current, fishnet)
    review_record = {
        "review_packet_version": VERSION,
        "selection_reason": selection_reason,
        "selection_rank": selection_rank,
        "page_id": record.get("page_id"),
        "current_route_page_id": record.get("current_route_page_id"),
        "page_id_match_strategy": record.get("page_id_match_strategy"),
        "route_pair": pair,
        "current_route": current,
        "fishnet_route_candidate": fishnet,
        "fishnet_best_route_candidate_before_review": record.get("fishnet_best_route_candidate_before_review"),
        "agreement_status": record.get("agreement_status"),
        "review_severity": record.get("review_severity"),
        "reason_codes": list(record.get("reason_codes") or []),
        "fishnet_review_required": bool(record.get("fishnet_review_required")),
        "fishnet_review_reason_codes": list(record.get("fishnet_review_reason_codes") or []),
        "fishnet_route_confidence": float(record.get("fishnet_route_confidence") or 0.0),
        "fishnet_route_scores": record.get("fishnet_route_scores") or {},
        "fishnet_route_adjusted_scores": record.get("fishnet_route_adjusted_scores") or {},
        "fishnet_reason_counts": record.get("fishnet_reason_counts") or {},
        "fishnet_ocr_engine_status": record.get("fishnet_ocr_engine_status"),
        "fishnet_ocr_text_length": int(record.get("fishnet_ocr_text_length") or 0),
        "fishnet_ocr_word_count": int(record.get("fishnet_ocr_word_count") or 0),
        "fishnet_ocr_word_box_count": int(record.get("fishnet_ocr_word_box_count") or 0),
        "fishnet_ocr_sample_text": record.get("fishnet_ocr_sample_text") or "",
        "overlay_candidates": overlay_candidates(record.get("page_id"), overlays_dir),
        "route_change_authorized": False,
        "route_change_recommendation": "review_only",
        "safety_contract": dict(SAFETY_CONTRACT),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }
    return review_record


def select_review_records(
    records: list[dict[str, Any]],
    *,
    config: ReviewSelectionConfig,
    overlays_dir: Path | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_pages: set[str] = set()

    def add(record: dict[str, Any], reason: str) -> None:
        page_id = str(record.get("page_id") or "")
        if not page_id or page_id in seen_pages:
            return
        seen_pages.add(page_id)
        selected.append(
            make_review_record(
                record,
                selection_reason=reason,
                selection_rank=len(selected) + 1,
                overlays_dir=overlays_dir,
            )
        )

    high_conf = [
        r for r in records
        if r.get("agreement_status") == "high_confidence_disagreement"
    ]
    high_conf.sort(key=severity_rank, reverse=True)
    for record in high_conf[: max(0, config.high_confidence_limit)]:
        add(record, "high_confidence_disagreement")

    by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_pair[route_pair(record.get("current_route"), record.get("fishnet_route_candidate"))].append(record)

    for pair in config.focus_route_pairs:
        group = by_pair.get(pair, [])
        group.sort(key=severity_rank, reverse=True)
        for record in group[: max(0, config.representative_per_pair)]:
            add(record, f"representative_route_pair:{pair}")

    review_required = [r for r in records if r.get("agreement_status") == "fishnet_review_required"]
    review_required.sort(key=severity_rank, reverse=True)
    for record in review_required[: max(0, config.review_required_limit)]:
        add(record, "fishnet_review_required_sample")

    return selected


def summarize_packet(
    *,
    workbench_payload: dict[str, Any],
    selected_records: list[dict[str, Any]],
    workbench_path: Path,
) -> dict[str, Any]:
    src_summary = workbench_payload.get("summary") or {}
    route_pairs = Counter(r.get("route_pair") for r in selected_records)
    selection_reasons = Counter(r.get("selection_reason") for r in selected_records)
    current_routes = Counter(r.get("current_route") for r in selected_records)
    fishnet_routes = Counter(r.get("fishnet_route_candidate") for r in selected_records)
    agreement_statuses = Counter(r.get("agreement_status") for r in selected_records)
    review_severities = Counter(r.get("review_severity") for r in selected_records)

    high_conf = sum(1 for r in selected_records if r.get("agreement_status") == "high_confidence_disagreement")
    text_pages = sum(1 for r in selected_records if int(r.get("fishnet_ocr_text_length") or 0) > 0)
    overlay_candidate_records = sum(1 for r in selected_records if r.get("overlay_candidates"))

    summary = {
        "source_workbench_path": str(workbench_path.as_posix()),
        "source_workbench_quality_status": workbench_payload.get("quality_status"),
        "source_comparison_record_count": src_summary.get("comparison_record_count", len(workbench_payload.get("records") or [])),
        "source_agreement_count": src_summary.get("agreement_count"),
        "source_disagreement_count": src_summary.get("disagreement_count"),
        "source_high_confidence_disagreement_count": src_summary.get("high_confidence_disagreement_count"),
        "source_review_required_count": src_summary.get("review_required_count"),
        "source_total_fishnet_ocr_text_length": src_summary.get("total_fishnet_ocr_text_length"),
        "source_total_fishnet_ocr_word_box_count": src_summary.get("total_fishnet_ocr_word_box_count"),
        "review_record_count": len(selected_records),
        "high_confidence_review_record_count": high_conf,
        "review_records_with_ocr_text_count": text_pages,
        "review_records_with_overlay_candidates_count": overlay_candidate_records,
        "selection_reason_counts": dict(sorted(selection_reasons.items())),
        "selected_route_pair_counts": dict(sorted(route_pairs.items())),
        "selected_current_route_counts": dict(sorted(current_routes.items())),
        "selected_fishnet_route_counts": dict(sorted(fishnet_routes.items())),
        "selected_agreement_status_counts": dict(sorted(agreement_statuses.items())),
        "selected_review_severity_counts": dict(sorted(review_severities.items())),
        "route_change_authorized_count": 0,
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    return summary


def quality_status_from_summary(summary: dict[str, Any]) -> str:
    if summary.get("unsafe_record_count", 0) != 0:
        return "FAIL"
    if summary.get("answer_permission_count", 0) != 0:
        return "FAIL"
    if summary.get("can_answer_directly_count", 0) != 0:
        return "FAIL"
    if summary.get("can_prove_claims_count", 0) != 0:
        return "FAIL"
    if summary.get("source_truth_mutation_allowed_count", 0) != 0:
        return "FAIL"
    if summary.get("route_change_authorized_count", 0) != 0:
        return "FAIL"
    return "PASS"


def build_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    records = payload.get("records") or []
    lines = [
        "# TRACE-Net Fishnet Route Review Packet v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Review records: {summary.get('review_record_count')}",
        f"- High-confidence review records: {summary.get('high_confidence_review_record_count')}",
        f"- Source disagreements: {summary.get('source_disagreement_count')}",
        f"- Route changes authorized: {summary.get('route_change_authorized_count')}",
        "",
        "## Selected route pairs",
        "",
    ]
    for pair, count in (summary.get("selected_route_pair_counts") or {}).items():
        lines.append(f"- `{pair}`: {count}")
    lines.extend(["", "## Review records", ""])
    for record in records:
        sample = (record.get("fishnet_ocr_sample_text") or "").replace("\n", " ")[:300]
        lines.extend([
            f"### {record.get('page_id')} — {record.get('route_pair')}",
            "",
            f"- Selection: `{record.get('selection_reason')}`",
            f"- Current route: `{record.get('current_route')}`",
            f"- Fishnet route: `{record.get('fishnet_route_candidate')}`",
            f"- Best before review: `{record.get('fishnet_best_route_candidate_before_review')}`",
            f"- Confidence: `{record.get('fishnet_route_confidence')}`",
            f"- OCR text length: `{record.get('fishnet_ocr_text_length')}`",
            f"- OCR word boxes: `{record.get('fishnet_ocr_word_box_count')}`",
            f"- Review reasons: `{record.get('fishnet_review_reason_codes')}`",
            f"- Overlay candidates: `{record.get('overlay_candidates')}`",
            "",
            f"> {sample}",
            "",
        ])
    return "\n".join(lines)


def build_review_packet(
    *,
    workbench_report: Path,
    output_dir: Path,
    overlays_dir: Path | None = None,
    high_confidence_limit: int = 50,
    representative_per_pair: int = 5,
    review_required_limit: int = 25,
    focus_route_pairs: list[str] | None = None,
) -> dict[str, Any]:
    workbench_payload = read_json(workbench_report)
    records = list(workbench_payload.get("records") or [])
    if not records:
        raise ValueError("workbench report has no records")
    config = ReviewSelectionConfig(
        high_confidence_limit=high_confidence_limit,
        representative_per_pair=representative_per_pair,
        review_required_limit=review_required_limit,
        focus_route_pairs=tuple(focus_route_pairs or DEFAULT_FOCUS_ROUTE_PAIRS),
    )
    selected = select_review_records(records, config=config, overlays_dir=overlays_dir)
    summary = summarize_packet(
        workbench_payload=workbench_payload,
        selected_records=selected,
        workbench_path=workbench_report,
    )
    payload = {
        "status": STATUS_BUILT,
        "version": VERSION,
        "quality_status": quality_status_from_summary(summary),
        "summary": summary,
        "safety_contract": dict(SAFETY_CONTRACT),
        "records": selected,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_fishnet_route_review_packet_v1.json"
    jsonl_path = output_dir / "trace_net_fishnet_route_review_packet_v1_records.jsonl"
    summary_path = output_dir / "trace_net_fishnet_route_review_packet_v1_summary.json"
    quality_path = output_dir / "trace_net_fishnet_route_review_packet_v1_quality.json"
    markdown_path = output_dir / "trace_net_fishnet_route_review_packet_v1.md"
    write_json(report_path, payload)
    write_jsonl(jsonl_path, selected)
    write_json(summary_path, summary)
    write_json(quality_path, {"quality_status": payload["quality_status"], "summary": summary})
    markdown_path.write_text(build_markdown_report(payload), encoding="utf-8")
    return payload


def check_review_packet_quality(
    *,
    report_path: Path,
    require_review_record_count: int | None = None,
    min_high_confidence_records: int | None = None,
    min_selected_route_pairs: int | None = None,
    min_records_with_ocr_text: int | None = None,
    max_unsafe: int | None = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_route_change_authorization: bool = False,
    write_json_report: bool = False,
) -> dict[str, Any]:
    payload = read_json(report_path)
    summary = dict(payload.get("summary") or {})
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    if require_review_record_count is not None:
        require(summary.get("review_record_count", 0) >= require_review_record_count,
                f"review_record_count < {require_review_record_count}")
    if min_high_confidence_records is not None:
        require(summary.get("high_confidence_review_record_count", 0) >= min_high_confidence_records,
                f"high_confidence_review_record_count < {min_high_confidence_records}")
    if min_selected_route_pairs is not None:
        require(len(summary.get("selected_route_pair_counts") or {}) >= min_selected_route_pairs,
                f"selected route pair count < {min_selected_route_pairs}")
    if min_records_with_ocr_text is not None:
        require(summary.get("review_records_with_ocr_text_count", 0) >= min_records_with_ocr_text,
                f"review_records_with_ocr_text_count < {min_records_with_ocr_text}")
    if max_unsafe is not None:
        require(summary.get("unsafe_record_count", 0) <= max_unsafe,
                f"unsafe_record_count > {max_unsafe}")
    if require_no_answer_permission:
        require(summary.get("answer_permission_count", 0) == 0, "answer_permission_count != 0")
        require(summary.get("can_answer_directly_count", 0) == 0, "can_answer_directly_count != 0")
        require(summary.get("can_prove_claims_count", 0) == 0, "can_prove_claims_count != 0")
    if require_no_source_truth_mutation:
        require(summary.get("source_truth_mutation_allowed_count", 0) == 0,
                "source_truth_mutation_allowed_count != 0")
    if require_no_route_change_authorization:
        require(summary.get("route_change_authorized_count", 0) == 0,
                "route_change_authorized_count != 0")

    quality_status = "FAIL" if errors else "PASS"
    result = {
        "status": STATUS_CHECKED,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "errors": errors,
    }
    if write_json_report:
        out_path = report_path.with_name("trace_net_fishnet_route_review_packet_v1_quality_check.json")
        write_json(out_path, result)
    return result


def parse_route_pairs(raw: list[str] | None) -> list[str] | None:
    if not raw:
        return None
    pairs: list[str] = []
    for value in raw:
        for item in value.split(","):
            item = item.strip()
            if item:
                pairs.append(item)
    return pairs or None


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net fishnet route review packet v1")
    p.add_argument("--workbench-report", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--overlays-dir", default=None)
    p.add_argument("--high-confidence-limit", type=int, default=50)
    p.add_argument("--representative-per-pair", type=int, default=5)
    p.add_argument("--review-required-limit", type=int, default=25)
    p.add_argument("--focus-route-pair", action="append", default=None)
    p.add_argument("--quality", action="store_true")
    return p


def main_build(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = build_review_packet(
        workbench_report=Path(args.workbench_report),
        output_dir=Path(args.output_dir),
        overlays_dir=Path(args.overlays_dir) if args.overlays_dir else None,
        high_confidence_limit=args.high_confidence_limit,
        representative_per_pair=args.representative_per_pair,
        review_required_limit=args.review_required_limit,
        focus_route_pairs=parse_route_pairs(args.focus_route_pair),
    )
    print(f"Status: {payload['status']}")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def quality_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net fishnet route review packet v1 quality")
    p.add_argument("--report-path", required=True)
    p.add_argument("--write-json", action="store_true")
    p.add_argument("--min-review-records", type=int, default=None)
    p.add_argument("--min-high-confidence-records", type=int, default=None)
    p.add_argument("--min-selected-route-pairs", type=int, default=None)
    p.add_argument("--min-records-with-ocr-text", type=int, default=None)
    p.add_argument("--max-unsafe", type=int, default=None)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--require-no-source-truth-mutation", action="store_true")
    p.add_argument("--require-no-route-change-authorization", action="store_true")
    return p


def main_quality(argv: list[str] | None = None) -> int:
    args = quality_arg_parser().parse_args(argv)
    result = check_review_packet_quality(
        report_path=Path(args.report_path),
        require_review_record_count=args.min_review_records,
        min_high_confidence_records=args.min_high_confidence_records,
        min_selected_route_pairs=args.min_selected_route_pairs,
        min_records_with_ocr_text=args.min_records_with_ocr_text,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_route_change_authorization=args.require_no_route_change_authorization,
        write_json_report=args.write_json,
    )
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result.get("errors"):
        print("Errors:", json.dumps(result["errors"], sort_keys=True))
    if args.write_json:
        print("Wrote:", Path(args.report_path).with_name("trace_net_fishnet_route_review_packet_v1_quality_check.json"))
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
