#!/usr/bin/env python
"""
TRACE-Net Leiden Representative Label Tightening v1.

Read-only refinement layer for hydrated Leiden communities. It converts noisy
community category counts into navigation-safe community profiles, selects
representative pages/parts, and emits review recommendations for mixed or
unresolved communities.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_leiden_representative_label_tightening_v1"
STATUS_BUILT = "LEIDEN_REPRESENTATIVE_LABELS_REFINED"

PROOF_ZERO_COUNTERS = {
    "community_as_proof_count": 0,
    "category_as_proof_count": 0,
    "retrieval_only_answer_allowed_count": 0,
    "can_answer_directly_count": 0,
    "can_prove_claims_count": 0,
    "source_truth_mutation_allowed_count": 0,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
}

PART_RE = re.compile(r"\b\d{3}-\d{5}(?:-\d{3})?\b")

NOISE_MACROS = {
    "helper",
    "community_navigation",
    "routing",
    "ops",
    "unknown",
}


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected top-level JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def clean_strings(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            nested = clean_strings(value)
            for n in nested:
                if n not in seen:
                    out.append(n)
                    seen.add(n)
            continue
        text = str(value).strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out


def quality_status(payload: dict[str, Any]) -> str | None:
    status = payload.get("quality_status") or payload.get("status")
    if status is None:
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        status = summary.get("quality_status") or summary.get("status")
    if status is None:
        return None
    return str(status)


def is_quality_pass(payload: dict[str, Any]) -> bool:
    return str(quality_status(payload)).upper() == "PASS"


def extract_hydration_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "community_hydration_records",
        "hydrated_community_records",
        "community_audit_records",
        "records",
        "communities",
        "traversal_plans",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    value = summary.get("community_hydration_records")
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def extract_dublin_page_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key in ("page_records", "records", "pages", "dublin_core_page_records"):
        value = payload.get(key)
        if isinstance(value, list):
            records = [x for x in value if isinstance(x, dict)]
            break
    by_page: dict[str, dict[str, Any]] = {}
    for record in records:
        page_id = record.get("page_id") or record.get("id") or record.get("source_page_id")
        if isinstance(page_id, str) and page_id:
            by_page[page_id] = record
    return by_page


def extract_page_ids(record: dict[str, Any]) -> list[str]:
    candidates: list[Any] = []
    for key in (
        "page_ids",
        "sample_page_ids",
        "member_page_ids",
        "source_page_ids",
        "pages",
        "page_members",
    ):
        if key in record:
            candidates.extend(as_list(record.get(key)))
    # Some records include nested page membership summaries.
    membership = record.get("page_membership")
    if isinstance(membership, dict):
        for key in ("page_ids", "sample_page_ids", "member_page_ids"):
            candidates.extend(as_list(membership.get(key)))
    out: list[str] = []
    for item in candidates:
        if isinstance(item, dict):
            for key in ("page_id", "id", "source_page_id"):
                value = item.get(key)
                if isinstance(value, str) and value.startswith("t_p_"):
                    out.append(value)
        elif isinstance(item, str) and item.startswith("t_p_"):
            out.append(item)
    return clean_strings(out)


def extract_part_numbers(record: dict[str, Any]) -> list[str]:
    candidates: list[Any] = []
    for key in ("sample_part_numbers", "part_numbers", "parts", "canonical_part_numbers"):
        if key in record:
            candidates.extend(as_list(record.get(key)))
    text_bits = [record.get("label"), record.get("summary"), record.get("text_preview")]
    category_summary = record.get("category_summary")
    if isinstance(category_summary, dict):
        text_bits.extend([category_summary.get("label"), category_summary.get("summary")])
    for bit in text_bits:
        if isinstance(bit, str):
            candidates.extend(PART_RE.findall(bit))
    return clean_strings(candidates)


def part_family(part_number: str) -> str | None:
    m = re.match(r"^(\d{3}-\d{5})", part_number or "")
    return m.group(1) if m else None


def macro_category(raw_key: str) -> str:
    key = str(raw_key).lower()
    if "visual" in key or "diagram" in key or "figure" in key or "chart" in key or "callout" in key:
        return "visual_evidence"
    if "table" in key or "cell" in key or "row" in key:
        return "table_evidence"
    if "part" in key or "catalog" in key or "nomenclature" in key:
        return "part_evidence"
    if "citation" in key or "cite" in key:
        return "citation_evidence"
    if "source" in key or "dublin" in key or "page_node" in key:
        return "source_identity"
    if "review" in key or "triage" in key:
        return "review_signal"
    if "text" in key or "ocr" in key:
        return "text_source_page"
    if "community_navigation" in key:
        return "community_navigation"
    if "context" in key or "retrieval" in key or "opensearch" in key or "embedding" in key:
        return "helper"
    if "fishnet" in key or "route" in key or "extraction" in key:
        return "routing"
    if "uncategorized" in key or "random" in key or "old_type" in key or "derived" in key:
        return "helper"
    return "unknown"


def normalize_category_counts(category_counts: dict[str, Any]) -> dict[str, int]:
    macro: Counter[str] = Counter()
    for raw_key, raw_value in (category_counts or {}).items():
        try:
            value = int(raw_value)
        except Exception:
            continue
        if value <= 0:
            continue
        macro[macro_category(raw_key)] += value
    return dict(sorted(macro.items()))


def evidence_counts(macro_counts: dict[str, int]) -> dict[str, int]:
    return {
        k: v
        for k, v in macro_counts.items()
        if k not in NOISE_MACROS and v > 0
    }


def dominant_macro(macro_counts: dict[str, int]) -> tuple[str | None, int, float]:
    ev = evidence_counts(macro_counts)
    total = sum(ev.values())
    if total <= 0:
        return None, 0, 0.0
    dom, count = max(ev.items(), key=lambda kv: (kv[1], kv[0]))
    return dom, count, round(count / total, 6)


def navigation_intent(record: dict[str, Any], dominant: str | None, part_numbers: list[str]) -> str:
    existing = record.get("navigation_intent")
    if isinstance(existing, str) and existing and existing != "mixed_evidence_navigation":
        # Keep a good existing specific intent, but still recalculate generic mixed labels.
        return existing
    if part_numbers:
        return "part_family_navigation"
    if dominant == "table_evidence":
        return "table_evidence_navigation"
    if dominant == "visual_evidence":
        return "visual_evidence_navigation"
    if dominant == "text_source_page":
        return "text_source_navigation"
    return "mixed_evidence_navigation"


def refined_label(record: dict[str, Any], dominant: str | None, part_numbers: list[str], page_count: int) -> str:
    families = clean_strings(part_family(p) for p in part_numbers if part_family(p))
    if families:
        first = families[0]
        return f"Part family community {first}"
    if dominant == "table_evidence":
        return f"Table evidence community ({page_count} page(s))"
    if dominant == "visual_evidence":
        return f"Visual evidence community ({page_count} page(s))"
    if dominant == "text_source_page":
        return f"Text/source page community ({page_count} page(s))"
    return str(record.get("label") or "TRACE-Net graph community")


def choose_representative_pages(
    page_ids: list[str],
    dublin_pages: dict[str, dict[str, Any]],
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    reps: list[dict[str, Any]] = []
    for idx, page_id in enumerate(page_ids[:max_pages]):
        record = dublin_pages.get(page_id, {})
        dc = record.get("dc") if isinstance(record.get("dc"), dict) else {}
        page_number = record.get("page_number") or record.get("page_label") or dc.get("dc:identifier")
        dc_type = dc.get("dc:type") or record.get("dc_type") or record.get("type")
        reps.append(
            {
                "page_id": page_id,
                "rank": idx + 1,
                "page_number": page_number,
                "dc_type": dc_type,
                "source_identity_available": bool(record),
            }
        )
    return reps


def confidence_label(ratio: float, has_pages: bool, has_summary: bool) -> str:
    if not has_pages or not has_summary:
        return "REVIEW_ONLY"
    if ratio >= 0.55:
        return "HIGH_NAVIGATION_CONFIDENCE"
    if ratio >= 0.35:
        return "MODERATE_NAVIGATION_CONFIDENCE"
    return "LOW_NAVIGATION_CONFIDENCE"


def build_profile_record(record: dict[str, Any], dublin_pages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    community_id = str(record.get("community_id") or record.get("id") or record.get("node_id") or "unknown_community")
    page_ids = extract_page_ids(record)
    part_numbers = extract_part_numbers(record)
    category_counts_raw = record.get("category_counts") if isinstance(record.get("category_counts"), dict) else {}
    if not category_counts_raw:
        summary_obj = record.get("category_summary")
        if isinstance(summary_obj, dict) and isinstance(summary_obj.get("category_counts"), dict):
            category_counts_raw = summary_obj.get("category_counts")

    macro_counts = normalize_category_counts(category_counts_raw)
    ev_counts = evidence_counts(macro_counts)
    dominant, dominant_count, dominant_ratio = dominant_macro(macro_counts)
    has_category_summary = bool(category_counts_raw) and bool(ev_counts)
    nav_intent = navigation_intent(record, dominant, part_numbers)
    page_count = int(record.get("page_count") or len(page_ids) or 0)
    if page_count == 0 and page_ids:
        page_count = len(page_ids)
    label = refined_label(record, dominant, part_numbers, page_count)
    representative_pages = choose_representative_pages(page_ids, dublin_pages, max_pages=5)
    families = clean_strings(part_family(p) for p in part_numbers if part_family(p))

    risk_flags: list[str] = []
    review_reasons: list[str] = []
    if not page_ids:
        risk_flags.append("missing_page_membership")
        review_reasons.append("community_has_no_page_membership_signal")
    if not has_category_summary:
        risk_flags.append("missing_category_summary")
        review_reasons.append("community_missing_category_distribution")
    if dominant_ratio and dominant_ratio < 0.35:
        risk_flags.append("low_normalized_category_coherence")
        review_reasons.append("community_normalized_evidence_distribution_is_mixed")
    if nav_intent == "mixed_evidence_navigation":
        risk_flags.append("mixed_navigation_intent")
        review_reasons.append("community_needs_human_label_review")

    conf = confidence_label(dominant_ratio, bool(page_ids), has_category_summary)
    if conf in {"LOW_NAVIGATION_CONFIDENCE", "REVIEW_ONLY"} and "community_needs_human_label_review" not in review_reasons:
        review_reasons.append("navigation_profile_confidence_requires_review")

    return {
        "schema_version": SCHEMA_VERSION,
        "community_id": community_id,
        "source_label": record.get("label"),
        "refined_label": label,
        "page_count": page_count,
        "page_ids": page_ids,
        "representative_pages": representative_pages,
        "representative_page_ids": [p["page_id"] for p in representative_pages],
        "part_numbers": part_numbers,
        "representative_part_numbers": part_numbers[:10],
        "part_families": families,
        "representative_part_family": families[0] if families else None,
        "raw_category_counts": dict(category_counts_raw or {}),
        "macro_category_counts": macro_counts,
        "evidence_category_counts": ev_counts,
        "dominant_evidence_category": dominant,
        "dominant_evidence_count": dominant_count,
        "dominant_evidence_ratio": dominant_ratio,
        "navigation_intent": nav_intent,
        "navigation_confidence": conf,
        "category_summary_hydrated": has_category_summary,
        "community_as_proof": False,
        "category_as_proof": False,
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "risk_flags": risk_flags,
        "review_recommended": bool(review_reasons),
        "review_reasons": review_reasons,
    }


def build_report(
    *,
    leiden_category_summary_hydrator: str | Path,
    dublin_core_refined: str | Path | None = None,
    output_dir: str | Path,
    thresholds: dict[str, Any] | None = None,
    write_markdown: bool = True,
) -> dict[str, Any]:
    thresholds = thresholds or {}
    hydrator_payload = load_json(leiden_category_summary_hydrator)
    dublin_payload = load_json(dublin_core_refined) if dublin_core_refined else {}
    dublin_pages = extract_dublin_page_records(dublin_payload) if dublin_payload else {}
    records = extract_hydration_records(hydrator_payload)

    profile_records = [build_profile_record(r, dublin_pages) for r in records]
    review_records = [r for r in profile_records if r.get("review_recommended")]

    conf_counter = Counter(r.get("navigation_confidence") for r in profile_records)
    intent_counter = Counter(r.get("navigation_intent") for r in profile_records)
    dom_counter = Counter(r.get("dominant_evidence_category") or "none" for r in profile_records)
    risk_counter: Counter[str] = Counter()
    for r in profile_records:
        risk_counter.update(r.get("risk_flags") or [])

    with_representatives = sum(1 for r in profile_records if r.get("representative_page_ids"))
    with_refined_labels = sum(1 for r in profile_records if r.get("refined_label"))
    missing_page_membership = sum(1 for r in profile_records if "missing_page_membership" in (r.get("risk_flags") or []))
    missing_category_summary = sum(1 for r in profile_records if not r.get("category_summary_hydrated"))
    low_confidence = sum(1 for r in profile_records if r.get("navigation_confidence") == "LOW_NAVIGATION_CONFIDENCE")
    review_only = sum(1 for r in profile_records if r.get("navigation_confidence") == "REVIEW_ONLY")

    source_statuses = {
        "leiden_category_summary_hydrator": quality_status(hydrator_payload),
        "dublin_core_refined": quality_status(dublin_payload) if dublin_payload else None,
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "source_hydrator_quality_status": source_statuses["leiden_category_summary_hydrator"],
        "source_dublin_core_quality_status": source_statuses["dublin_core_refined"],
        "community_profile_record_count": len(profile_records),
        "refined_label_count": with_refined_labels,
        "communities_with_representative_pages_count": with_representatives,
        "missing_page_membership_count": missing_page_membership,
        "missing_category_summary_count": missing_category_summary,
        "low_navigation_confidence_count": low_confidence,
        "review_only_community_count": review_only,
        "review_recommended_community_count": len(review_records),
        "navigation_confidence_counts": dict(conf_counter),
        "navigation_intent_counts": dict(intent_counter),
        "dominant_evidence_category_counts": dict(dom_counter),
        "risk_flag_counts": dict(risk_counter),
        "source_quality_statuses": source_statuses,
        **PROOF_ZERO_COUNTERS,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": "PASS",
        "summary": summary,
        "community_profile_records": profile_records,
        "review_recommended_records": review_records,
    }

    quality = evaluate_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    report["summary"]["status"] = quality["quality_status"]
    report["quality_failures"] = quality.get("failures", [])

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "trace_net_leiden_representative_label_tightening_v1.json"
    quality_path = out_dir / "trace_net_leiden_representative_label_tightening_v1_quality.json"
    records_path = out_dir / "trace_net_leiden_representative_label_tightening_v1_records.jsonl"
    review_path = out_dir / "trace_net_leiden_representative_label_tightening_v1_review_records.jsonl"
    write_json(report_path, report)
    write_json(quality_path, quality)
    write_jsonl(records_path, profile_records)
    write_jsonl(review_path, review_records)

    if write_markdown:
        md = render_markdown(report)
        (out_dir / "trace_net_leiden_representative_label_tightening_v1.md").write_text(md, encoding="utf-8")

    report["report_path"] = str(report_path)
    report["quality_path"] = str(quality_path)
    return report


def evaluate_quality(report: dict[str, Any], thresholds: dict[str, Any] | None = None) -> dict[str, Any]:
    thresholds = thresholds or {}
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    failures: list[str] = []

    def require_min(key: str, threshold_key: str) -> None:
        value = int(summary.get(key) or 0)
        required = thresholds.get(threshold_key)
        if required is not None and value < int(required):
            failures.append(f"{key}={value} below required {required}")

    def require_max(key: str, threshold_key: str) -> None:
        value = int(summary.get(key) or 0)
        limit = thresholds.get(threshold_key)
        if limit is not None and value > int(limit):
            failures.append(f"{key}={value} above allowed {limit}")

    require_min("community_profile_record_count", "min_communities")
    require_min("refined_label_count", "min_refined_labels")
    require_min("communities_with_representative_pages_count", "min_communities_with_representative_pages")
    require_max("missing_page_membership_count", "max_missing_page_membership")
    require_max("missing_category_summary_count", "max_missing_category_summary")
    require_max("low_navigation_confidence_count", "max_low_navigation_confidence")

    if thresholds.get("require_hydrator_quality_pass"):
        if str(summary.get("source_hydrator_quality_status")).upper() != "PASS":
            failures.append("source_hydrator_quality_status is not PASS")
    if thresholds.get("require_dublin_core_quality_pass"):
        if str(summary.get("source_dublin_core_quality_status")).upper() != "PASS":
            failures.append("source_dublin_core_quality_status is not PASS")

    for key in PROOF_ZERO_COUNTERS:
        limit_key = f"max_{key}"
        if limit_key in thresholds:
            require_max(key, limit_key)
        elif int(summary.get(key) or 0) != 0:
            failures.append(f"{key} must stay 0")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": "FAIL" if failures else "PASS",
        "summary": dict(summary),
        "failures": failures,
    }


def check_quality(
    *,
    report_path: str | Path,
    thresholds: dict[str, Any] | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = load_json(report_path)
    quality = evaluate_quality(report, thresholds)
    if write_json_report:
        p = Path(report_path)
        quality_path = p.with_name("trace_net_leiden_representative_label_tightening_v1_quality.json")
        write_json(quality_path, quality)
    return quality


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Leiden Representative Label Tightening v1",
        "",
        f"Quality status: {report.get('quality_status')}",
        f"Status: {report.get('status')}",
        "",
        "## Summary",
    ]
    for key in [
        "community_profile_record_count",
        "refined_label_count",
        "communities_with_representative_pages_count",
        "missing_page_membership_count",
        "missing_category_summary_count",
        "low_navigation_confidence_count",
        "review_recommended_community_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend([
        "",
        "## Safety",
        "This artifact is navigation-only. Community labels and categories remain advisory and cannot prove claims or authorize answers.",
    ])
    return "\n".join(lines) + "\n"


def print_report(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print("TRACE-Net Leiden Representative Label Tightening v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "community_profile_record_count",
        "refined_label_count",
        "communities_with_representative_pages_count",
        "missing_page_membership_count",
        "missing_category_summary_count",
        "low_navigation_confidence_count",
        "review_recommended_community_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if report.get("report_path"):
        print(f" report_path: {report.get('report_path')}")
    if report.get("quality_path"):
        print(f" quality_path: {report.get('quality_path')}")


def add_common_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-communities", type=int, default=None)
    parser.add_argument("--min-refined-labels", type=int, default=None)
    parser.add_argument("--min-communities-with-representative-pages", type=int, default=None)
    parser.add_argument("--max-missing-page-membership", type=int, default=None)
    parser.add_argument("--max-missing-category-summary", type=int, default=None)
    parser.add_argument("--max-low-navigation-confidence", type=int, default=None)
    parser.add_argument("--max-community-as-proof", dest="max_community_as_proof_count", type=int, default=None)
    parser.add_argument("--max-category-as-proof", dest="max_category_as_proof_count", type=int, default=None)
    parser.add_argument("--max-retrieval-only-answer-allowed", dest="max_retrieval_only_answer_allowed_count", type=int, default=None)
    parser.add_argument("--max-source-truth-mutation-allowed", dest="max_source_truth_mutation_allowed_count", type=int, default=None)
    parser.add_argument("--require-hydrator-quality-pass", action="store_true")
    parser.add_argument("--require-dublin-core-quality-pass", action="store_true")


def thresholds_from_args(args: argparse.Namespace) -> dict[str, Any]:
    keys = [
        "min_communities",
        "min_refined_labels",
        "min_communities_with_representative_pages",
        "max_missing_page_membership",
        "max_missing_category_summary",
        "max_low_navigation_confidence",
        "max_community_as_proof_count",
        "max_category_as_proof_count",
        "max_retrieval_only_answer_allowed_count",
        "max_source_truth_mutation_allowed_count",
        "require_hydrator_quality_pass",
        "require_dublin_core_quality_pass",
    ]
    return {key: getattr(args, key) for key in keys if hasattr(args, key) and getattr(args, key) is not None}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Leiden Representative Label Tightening v1")
    parser.add_argument("--leiden-category-summary-hydrator", required=True)
    parser.add_argument("--dublin-core-refined", required=False)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    add_common_threshold_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(
        leiden_category_summary_hydrator=args.leiden_category_summary_hydrator,
        dublin_core_refined=args.dublin_core_refined,
        output_dir=args.output_dir,
        thresholds=thresholds_from_args(args) if args.quality else {},
    )
    print_report(report)
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
