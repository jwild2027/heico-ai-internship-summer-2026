"""TRACE-Net Fishnet Route Signal Workbench v1.

This module compares the new fishnet/grid OCR route signals against the
current TRACE-Net page route manifest, without changing route behavior.

Safety contract:
- read-only artifact comparison
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

The workbench is intentionally conservative. Fishnet route candidates are
review signals, not route authority. A high-confidence disagreement is not an
automatic route change; it is a review item for the next router hardening pass.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "trace_net_fishnet_route_signal_workbench_v1"
STATUS_BUILT = "FISHNET_ROUTE_SIGNAL_WORKBENCH_BUILT"

ROUTE_ORDER = ("blank_candidate", "normal_text", "table", "image_visual", "review_required", "unknown")
KNOWN_ROUTE_VALUES = set(ROUTE_ORDER)

SAFETY_CONTRACT: Dict[str, Any] = {
    "module": VERSION,
    "artifact_role": "route_signal_comparison_workbench",
    "fishnet_route_candidate_authority": "review_signal_only",
    "current_route_authority": "existing_route_manifest_only",
    "can_change_routes": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_allowed": False,
    "qdrant_write_allowed": False,
    "opensearch_write_allowed": False,
}

# Common fields used across previous TRACE-Net route/page artifacts.
PAGE_ID_KEYS = (
    "page_id",
    "source_page_id",
    "trace_page_id",
    "canonical_page_id",
    "page",
)
ROUTE_KEYS = (
    "route",
    "page_route",
    "selected_route",
    "assigned_route",
    "primary_route",
    "recommended_route",
    "recommended_route_candidate",
    "route_candidate",
    "processor_route",
)
CONFIDENCE_KEYS = (
    "route_confidence",
    "confidence",
    "recommended_route_confidence",
    "fishnet_route_confidence",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def normalize_route(value: Any) -> str:
    if value is None:
        return "unknown"
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "blank": "blank_candidate",
        "blank_page": "blank_candidate",
        "empty": "blank_candidate",
        "text": "normal_text",
        "plain_text": "normal_text",
        "normal": "normal_text",
        "ocr_text": "normal_text",
        "image": "image_visual",
        "visual": "image_visual",
        "diagram": "image_visual",
        "figure": "image_visual",
        "review": "review_required",
        "human_review": "review_required",
        "needs_review": "review_required",
    }
    text = aliases.get(text, text)
    return text if text in KNOWN_ROUTE_VALUES else text or "unknown"


def first_present(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in record and record.get(key) not in (None, ""):
            return record.get(key)
    return None


def first_present_deep(record: Mapping[str, Any], keys: Sequence[str], *, max_depth: int = 3) -> Any:
    """Find the first non-empty value for keys, including shallow nested card shapes.

    TRACE-Net artifacts have evolved across many patch generations. Some route
    manifests keep the page id and selected route at top level, while others put
    them under nested objects such as ``page_route_card`` or ``route_decision``.
    This helper keeps the workbench tolerant without making route changes.
    """
    top = first_present(record, keys)
    if top not in (None, ""):
        return top

    def walk(value: Any, depth: int) -> Any:
        if depth > max_depth:
            return None
        if isinstance(value, Mapping):
            direct = first_present(value, keys)
            if direct not in (None, ""):
                return direct
            for child_key in sorted(value.keys()):
                found = walk(value.get(child_key), depth + 1)
                if found not in (None, ""):
                    return found
        elif isinstance(value, list):
            for item in value[:10]:
                found = walk(item, depth + 1)
                if found not in (None, ""):
                    return found
        return None

    return walk(record, 0)


def page_id_aliases(value: Any) -> List[str]:
    """Return robust aliases for page IDs across source-package and TRACE-Net forms.

    Fishnet source-package discovery may emit ``source_p000001`` while existing
    TRACE-Net route manifests often use canonical IDs such as
    ``t_p_120_1176_p000001``. Both describe the same page ordinal. The workbench
    must compare those safely by normalized exact ID and by page ordinal alias.
    """
    if value in (None, ""):
        return []
    text = str(value).strip()
    if not text:
        return []
    norm = text.lower().replace("\\", "/")
    aliases = {norm, norm.replace("-", "_"), norm.replace(" ", "_")}

    # Prefer a trailing pNNNNNN page ordinal, but fall back to the last number.
    matches = re.findall(r"p(\d{1,6})(?!.*p\d)", norm)
    if matches:
        n = int(matches[-1])
        aliases.update({
            f"page:{n}",
            f"page:{n:06d}",
            f"p{n:06d}",
            f"source_p{n:06d}",
        })
    else:
        all_numbers = re.findall(r"\d+", norm)
        if all_numbers:
            n = int(all_numbers[-1])
            aliases.update({
                f"page:{n}",
                f"page:{n:06d}",
                f"p{n:06d}",
                f"source_p{n:06d}",
            })
    return sorted(aliases)


def coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "review", "required", "needs_review"}


def nested_mapping(record: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = record.get(key)
    return value if isinstance(value, Mapping) else {}


def nested_list(record: Mapping[str, Any], key: str) -> List[Mapping[str, Any]]:
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def text_length_from_fishnet_record(record: Mapping[str, Any]) -> int:
    """Return fishnet OCR text length from current and older card shapes.

    Fishnet v1.4+ stores OCR features below ``page_ocr_features`` rather
    than as top-level ``ocr_text``. Earlier workbench versions missed that
    nested shape and reported ``fishnet_ocr_text_length: 0`` even for pages
    that had healthy OCR. This helper treats nested ``ocr_char_count`` as the
    authoritative diagnostic count while still supporting older top-level
    fields.
    """
    page_ocr = nested_mapping(record, "page_ocr_features")
    for value in (
        record.get("ocr_text_length"),
        record.get("page_ocr_text_length"),
        page_ocr.get("ocr_char_count"),
        page_ocr.get("char_count"),
    ):
        n = coerce_int(value, -1)
        if n >= 0:
            return n
    for value in (
        record.get("ocr_text"),
        record.get("page_ocr_text"),
        page_ocr.get("sample_text"),
    ):
        if value not in (None, ""):
            return len(str(value))
    return 0


def word_box_count_from_fishnet_record(record: Mapping[str, Any]) -> int:
    page_ocr = nested_mapping(record, "page_ocr_features")
    for value in (
        record.get("ocr_word_box_count"),
        page_ocr.get("ocr_word_box_count"),
        page_ocr.get("word_box_count"),
    ):
        n = coerce_int(value, -1)
        if n >= 0:
            return n
    total = 0
    for cell in nested_list(record, "cell_records"):
        total += coerce_int(cell.get("ocr_word_box_count"), 0)
    return total


def word_count_from_fishnet_record(record: Mapping[str, Any]) -> int:
    page_ocr = nested_mapping(record, "page_ocr_features")
    for value in (record.get("ocr_word_count"), page_ocr.get("ocr_word_count"), page_ocr.get("word_count")):
        n = coerce_int(value, -1)
        if n >= 0:
            return n
    return 0


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def extract_records(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Extract records from common TRACE-Net payload shapes."""
    candidate_keys = (
        "records",
        "page_records",
        "route_cards",
        "page_route_cards",
        "cards",
        "workbench_records",
        "workbench_cards",
        "fishnet_records",
        "comparison_records",
        "route_manifest",
        "page_route_manifest",
        "dispatch_cards",
        "page_dispatch_cards",
    )
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]

    # Some reports nest the useful list below a report/result object.
    for wrapper_key in ("report", "payload", "result", "data"):
        wrapper = payload.get(wrapper_key)
        if isinstance(wrapper, Mapping):
            records = extract_records(wrapper)
            if records:
                return records
    return []


def discover_route_manifest(base_dir: Path) -> Optional[Path]:
    """Find a likely existing route manifest under local_data/organization/trace_net."""
    if not base_dir.exists():
        return None
    patterns = (
        "*page*route*manifest*.json",
        "*route*manifest*.json",
        "*page*route*.json",
    )
    matches: List[Path] = []
    for pattern in patterns:
        matches.extend(p for p in base_dir.rglob(pattern) if p.is_file())
    if not matches:
        return None

    def score(path: Path) -> Tuple[int, int, str]:
        text = str(path).lower()
        s = 0
        if "page_route_manifest" in text:
            s += 100
        if "dispatch" in text:
            s -= 20
        if "quality" in text or "check" in text:
            s -= 10
        if "fishnet" in text:
            s -= 30
        return (s, -len(path.parts), str(path))

    return sorted(matches, key=score, reverse=True)[0]


def load_current_routes(path: Optional[Path], trace_net_root: Path) -> Tuple[Dict[str, Dict[str, Any]], Optional[str], int]:
    """Load current route manifest with robust page-id aliases.

    Returns ``(route_by_alias, loaded_path_string_or_none, unique_page_count)``.
    Alias matching handles canonical TRACE-Net IDs like
    ``t_p_120_1176_p000001`` and source-package IDs like ``source_p000001``.
    Missing matches remain review-only; this function never authorizes a route
    change.
    """
    resolved_path = path
    if resolved_path and not resolved_path.exists():
        resolved_path = None
    if resolved_path is None:
        resolved_path = discover_route_manifest(trace_net_root)
    if resolved_path is None:
        return {}, None, 0

    payload = read_json(resolved_path)
    records = extract_records(payload)
    route_by_alias: Dict[str, Dict[str, Any]] = {}
    unique_pages: Dict[str, None] = {}
    for record in records:
        page_id = first_present_deep(record, PAGE_ID_KEYS)
        if not page_id:
            continue
        route_raw = first_present_deep(record, ROUTE_KEYS)
        route = normalize_route(route_raw)
        canonical = str(page_id)
        unique_pages[canonical] = None
        route_record = {
            "page_id": canonical,
            "current_route": route,
            "current_route_raw": route_raw,
            "current_route_record": record,
            "page_id_aliases": page_id_aliases(canonical),
        }
        for alias in page_id_aliases(canonical):
            route_by_alias.setdefault(alias, route_record)
    return route_by_alias, str(resolved_path), len(unique_pages)

def extract_fishnet_records(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records = extract_records(payload)
    fishnet_records: List[Dict[str, Any]] = []
    for record in records:
        page_id = first_present_deep(record, PAGE_ID_KEYS)
        if not page_id:
            continue
        fishnet_route_raw = first_non_empty(
            record.get("recommended_route_candidate"),
            record.get("fishnet_route_candidate"),
            first_present_deep(record, ROUTE_KEYS),
        )
        fishnet_route = normalize_route(fishnet_route_raw)
        best_before_review_raw = first_non_empty(
            record.get("best_route_candidate_before_review"),
            record.get("best_route_before_review"),
            record.get("best_route_candidate"),
        )
        confidence = coerce_float(
            record.get("route_confidence")
            if "route_confidence" in record
            else first_present_deep(record, CONFIDENCE_KEYS),
            0.0,
        )
        page_ocr = nested_mapping(record, "page_ocr_features")
        review_reasons = record.get("route_review_reason_codes") or record.get("review_reason_codes") or []
        if not isinstance(review_reasons, list):
            review_reasons = [str(review_reasons)]
        fishnet_records.append(
            {
                "page_id": str(page_id),
                "fishnet_route_candidate": fishnet_route,
                "fishnet_route_candidate_raw": fishnet_route_raw,
                "fishnet_best_route_candidate_before_review": normalize_route(best_before_review_raw),
                "fishnet_best_route_candidate_before_review_raw": best_before_review_raw,
                "fishnet_route_confidence": round(confidence, 4),
                "fishnet_review_required": coerce_bool(record.get("review_required")),
                "fishnet_review_reason_codes": [str(item) for item in review_reasons],
                "fishnet_ocr_engine_status": record.get("ocr_engine_status", "unknown"),
                "fishnet_ocr_text_length": text_length_from_fishnet_record(record),
                "fishnet_ocr_word_count": word_count_from_fishnet_record(record),
                "fishnet_ocr_word_box_count": word_box_count_from_fishnet_record(record),
                "fishnet_ocr_sample_text": str(page_ocr.get("sample_text") or record.get("ocr_sample_text") or "")[:240],
                "fishnet_cell_count": coerce_int(record.get("cell_count"), 0)
                or len(record.get("cell_records") or []),
                "fishnet_route_scores": record.get("route_scores")
                or record.get("route_candidate_scores")
                or {},
                "fishnet_route_adjusted_scores": record.get("route_adjusted_scores") or {},
                "fishnet_reason_counts": record.get("reason_counts") or {},
                "fishnet_record": record,
            }
        )
    return fishnet_records


def classify_comparison(
    *,
    current_route: str,
    fishnet_route: str,
    fishnet_confidence: float,
    fishnet_review_required: bool,
    high_confidence_threshold: float,
) -> Tuple[str, str, List[str]]:
    reasons: List[str] = []

    if current_route == "missing_current_route":
        return "missing_current_route", "review", ["current_route_missing"]

    if fishnet_review_required:
        reasons.append("fishnet_review_required")
        return "fishnet_review_required", "review", reasons

    if fishnet_route in {"unknown", "review_required"}:
        reasons.append("fishnet_route_uncertain")
        return "fishnet_uncertain", "review", reasons

    if current_route == fishnet_route:
        return "agree", "ok", ["routes_match"]

    reasons.append(f"current_{current_route}_vs_fishnet_{fishnet_route}")
    if fishnet_confidence >= high_confidence_threshold:
        reasons.append("high_confidence_fishnet_disagreement")
        return "high_confidence_disagreement", "high", reasons
    return "disagree", "medium", reasons


def count_safety(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counters = Counter()
    for record in records:
        if coerce_bool(record.get("answer_permission")):
            counters["answer_permission_count"] += 1
        if coerce_bool(record.get("can_answer_directly")):
            counters["can_answer_directly_count"] += 1
        if coerce_bool(record.get("can_prove_claims")):
            counters["can_prove_claims_count"] += 1
        if coerce_bool(record.get("source_truth_mutation_allowed")):
            counters["source_truth_mutation_allowed_count"] += 1
        if coerce_bool(record.get("postgres_write_attempt")) or coerce_bool(record.get("postgres_write_allowed")):
            counters["postgres_write_attempt_count"] += 1
        if coerce_bool(record.get("qdrant_write_attempt")) or coerce_bool(record.get("qdrant_write_allowed")):
            counters["qdrant_write_attempt_count"] += 1
        if coerce_bool(record.get("opensearch_write_attempt")) or coerce_bool(record.get("opensearch_write_allowed")):
            counters["opensearch_write_attempt_count"] += 1
        if coerce_bool(record.get("unsafe")) or coerce_bool(record.get("unsafe_record")):
            counters["unsafe_record_count"] += 1
    for key in (
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "unsafe_record_count",
    ):
        counters.setdefault(key, 0)
    return dict(counters)


def build_fishnet_route_signal_workbench(
    *,
    fishnet_report: Path,
    output_dir: Path,
    current_route_manifest: Optional[Path] = None,
    trace_net_root: Path = Path("local_data/organization/trace_net"),
    high_confidence_threshold: float = 0.85,
    quality: bool = False,
) -> Dict[str, Any]:
    if not fishnet_report.exists():
        raise FileNotFoundError(f"fishnet report not found: {fishnet_report}")

    fishnet_payload = read_json(fishnet_report)
    fishnet_records = extract_fishnet_records(fishnet_payload)
    current_route_by_page, loaded_current_route_manifest, current_route_unique_page_count = load_current_routes(current_route_manifest, trace_net_root)

    comparison_records: List[Dict[str, Any]] = []
    raw_records_for_safety: List[Mapping[str, Any]] = []

    for fishnet in sorted(fishnet_records, key=lambda r: r["page_id"]):
        page_id = fishnet["page_id"]
        current = None
        for alias in page_id_aliases(page_id):
            current = current_route_by_page.get(alias)
            if current:
                break
        current_route = current["current_route"] if current else "missing_current_route"
        status, severity, reason_codes = classify_comparison(
            current_route=current_route,
            fishnet_route=fishnet["fishnet_route_candidate"],
            fishnet_confidence=fishnet["fishnet_route_confidence"],
            fishnet_review_required=fishnet["fishnet_review_required"],
            high_confidence_threshold=high_confidence_threshold,
        )
        raw_records_for_safety.append(fishnet.get("fishnet_record", {}))
        if current and isinstance(current.get("current_route_record"), Mapping):
            raw_records_for_safety.append(current["current_route_record"])

        comparison_records.append(
            {
                "workbench_version": VERSION,
                "page_id": page_id,
                "current_route_page_id": current.get("page_id") if current else None,
                "page_id_match_strategy": "alias" if current and current.get("page_id") != page_id else ("exact" if current else "missing"),
                "current_route": current_route,
                "fishnet_route_candidate": fishnet["fishnet_route_candidate"],
                "fishnet_best_route_candidate_before_review": fishnet["fishnet_best_route_candidate_before_review"],
                "fishnet_route_confidence": fishnet["fishnet_route_confidence"],
                "fishnet_review_required": fishnet["fishnet_review_required"],
                "fishnet_review_reason_codes": fishnet["fishnet_review_reason_codes"],
                "fishnet_ocr_engine_status": fishnet["fishnet_ocr_engine_status"],
                "fishnet_ocr_text_length": fishnet["fishnet_ocr_text_length"],
                "fishnet_ocr_word_count": fishnet["fishnet_ocr_word_count"],
                "fishnet_ocr_word_box_count": fishnet["fishnet_ocr_word_box_count"],
                "fishnet_ocr_sample_text": fishnet["fishnet_ocr_sample_text"],
                "fishnet_cell_count": fishnet["fishnet_cell_count"],
                "fishnet_route_scores": fishnet["fishnet_route_scores"],
                "fishnet_route_adjusted_scores": fishnet["fishnet_route_adjusted_scores"],
                "fishnet_reason_counts": fishnet["fishnet_reason_counts"],
                "agreement_status": status,
                "review_severity": severity,
                "reason_codes": reason_codes,
                "route_change_authorized": False,
                "route_change_recommendation": "review_only",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            }
        )

    route_pair_counter = Counter(
        f"{r['current_route']}->{r['fishnet_route_candidate']}" for r in comparison_records
    )
    status_counter = Counter(r["agreement_status"] for r in comparison_records)
    severity_counter = Counter(r["review_severity"] for r in comparison_records)
    current_counter = Counter(r["current_route"] for r in comparison_records)
    fishnet_counter = Counter(r["fishnet_route_candidate"] for r in comparison_records)
    fishnet_best_before_review_counter = Counter(
        r.get("fishnet_best_route_candidate_before_review") or "unknown" for r in comparison_records
    )
    ocr_counter = Counter(r["fishnet_ocr_engine_status"] for r in comparison_records)
    total_fishnet_ocr_text_length = sum(int(r.get("fishnet_ocr_text_length") or 0) for r in comparison_records)
    total_fishnet_ocr_word_box_count = sum(int(r.get("fishnet_ocr_word_box_count") or 0) for r in comparison_records)
    pages_with_fishnet_ocr_text_count = sum(1 for r in comparison_records if int(r.get("fishnet_ocr_text_length") or 0) > 0)
    pages_with_fishnet_ocr_word_boxes_count = sum(1 for r in comparison_records if int(r.get("fishnet_ocr_word_box_count") or 0) > 0)

    safety_counts = count_safety(raw_records_for_safety + comparison_records)
    comparison_count = len(comparison_records)
    agreement_count = status_counter.get("agree", 0)
    disagreement_count = (
        status_counter.get("disagree", 0) + status_counter.get("high_confidence_disagreement", 0)
    )
    current_route_missing_count = status_counter.get("missing_current_route", 0)
    high_confidence_disagreement_count = status_counter.get("high_confidence_disagreement", 0)
    review_required_count = comparison_count - agreement_count

    summary: Dict[str, Any] = {
        "fishnet_report_path": str(fishnet_report),
        "current_route_manifest_path": loaded_current_route_manifest,
        "comparison_record_count": comparison_count,
        "fishnet_page_count": len(fishnet_records),
        "current_route_page_count": current_route_unique_page_count,
        "current_route_alias_count": len(current_route_by_page),
        "matched_page_count": comparison_count - current_route_missing_count,
        "agreement_count": agreement_count,
        "disagreement_count": disagreement_count,
        "high_confidence_disagreement_count": high_confidence_disagreement_count,
        "current_route_missing_count": current_route_missing_count,
        "review_required_count": review_required_count,
        "agreement_ratio": round(agreement_count / comparison_count, 4) if comparison_count else 0.0,
        "high_confidence_threshold": high_confidence_threshold,
        "current_route_counts": dict(sorted(current_counter.items())),
        "fishnet_route_candidate_counts": dict(sorted(fishnet_counter.items())),
        "fishnet_best_route_candidate_before_review_counts": dict(sorted(fishnet_best_before_review_counter.items())),
        "total_fishnet_ocr_text_length": total_fishnet_ocr_text_length,
        "total_fishnet_ocr_word_box_count": total_fishnet_ocr_word_box_count,
        "pages_with_fishnet_ocr_text_count": pages_with_fishnet_ocr_text_count,
        "pages_with_fishnet_ocr_word_boxes_count": pages_with_fishnet_ocr_word_boxes_count,
        "agreement_status_counts": dict(sorted(status_counter.items())),
        "review_severity_counts": dict(sorted(severity_counter.items())),
        "route_pair_counts": dict(route_pair_counter.most_common()),
        "fishnet_ocr_engine_status_counts": dict(sorted(ocr_counter.items())),
        **safety_counts,
    }

    quality_status = "PASS"
    quality_reasons: List[str] = []
    if not comparison_records:
        quality_status = "FAIL"
        quality_reasons.append("no_comparison_records")
    for key, value in safety_counts.items():
        if value:
            quality_status = "FAIL"
            quality_reasons.append(f"{key}_nonzero")

    payload: Dict[str, Any] = {
        "module": VERSION,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "quality_reasons": quality_reasons,
        "created_at": utc_now_iso(),
        "safety_contract": SAFETY_CONTRACT,
        "summary": summary,
        "records": comparison_records,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{VERSION}.json"
    cards_path = output_dir / f"{VERSION}_records.jsonl"
    summary_path = output_dir / f"{VERSION}_summary.json"
    write_json(report_path, payload)
    write_jsonl(cards_path, comparison_records)
    write_json(summary_path, {"quality_status": quality_status, "summary": summary})
    if quality:
        write_json(output_dir / f"{VERSION}_quality.json", {"quality_status": quality_status, "summary": summary, "quality_reasons": quality_reasons})

    return payload


def check_fishnet_route_signal_workbench_quality(
    *,
    report_path: Path,
    write_json_report: bool = False,
    require_page_count: Optional[int] = None,
    min_comparison_records: Optional[int] = None,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_current_routes: bool = False,
    max_missing_current_routes: Optional[int] = None,
    max_high_confidence_disagreements: Optional[int] = None,
    min_fishnet_ocr_text_chars: Optional[int] = None,
    min_fishnet_ocr_word_boxes: Optional[int] = None,
    min_pages_with_fishnet_ocr_text: Optional[int] = None,
) -> Dict[str, Any]:
    payload = read_json(report_path)
    summary = dict(payload.get("summary") or {})
    records = extract_records(payload)
    reasons: List[str] = []

    comparison_record_count = int(summary.get("comparison_record_count") or len(records))
    unsafe_count = int(summary.get("unsafe_record_count") or 0)
    missing_current_count = int(summary.get("current_route_missing_count") or 0)
    high_conf_disagree_count = int(summary.get("high_confidence_disagreement_count") or 0)
    total_fishnet_ocr_text_length = int(summary.get("total_fishnet_ocr_text_length") or 0)
    total_fishnet_ocr_word_box_count = int(summary.get("total_fishnet_ocr_word_box_count") or 0)
    pages_with_fishnet_ocr_text_count = int(summary.get("pages_with_fishnet_ocr_text_count") or 0)

    if require_page_count is not None and comparison_record_count != require_page_count:
        reasons.append(f"comparison_record_count {comparison_record_count} != required {require_page_count}")
    if min_comparison_records is not None and comparison_record_count < min_comparison_records:
        reasons.append(f"comparison_record_count {comparison_record_count} < min {min_comparison_records}")
    if unsafe_count > max_unsafe:
        reasons.append(f"unsafe_record_count {unsafe_count} > max {max_unsafe}")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        reasons.append("answer_permission_count must be 0")
    if require_no_answer_permission and int(summary.get("can_answer_directly_count") or 0) != 0:
        reasons.append("can_answer_directly_count must be 0")
    if require_no_answer_permission and int(summary.get("can_prove_claims_count") or 0) != 0:
        reasons.append("can_prove_claims_count must be 0")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        reasons.append("source_truth_mutation_allowed_count must be 0")
    if require_current_routes and missing_current_count:
        reasons.append(f"current_route_missing_count {missing_current_count} must be 0")
    if max_missing_current_routes is not None and missing_current_count > max_missing_current_routes:
        reasons.append(f"current_route_missing_count {missing_current_count} > max {max_missing_current_routes}")
    if max_high_confidence_disagreements is not None and high_conf_disagree_count > max_high_confidence_disagreements:
        reasons.append(
            f"high_confidence_disagreement_count {high_conf_disagree_count} > max {max_high_confidence_disagreements}"
        )
    if min_fishnet_ocr_text_chars is not None and total_fishnet_ocr_text_length < min_fishnet_ocr_text_chars:
        reasons.append(
            f"total_fishnet_ocr_text_length {total_fishnet_ocr_text_length} < min {min_fishnet_ocr_text_chars}"
        )
    if min_fishnet_ocr_word_boxes is not None and total_fishnet_ocr_word_box_count < min_fishnet_ocr_word_boxes:
        reasons.append(
            f"total_fishnet_ocr_word_box_count {total_fishnet_ocr_word_box_count} < min {min_fishnet_ocr_word_boxes}"
        )
    if min_pages_with_fishnet_ocr_text is not None and pages_with_fishnet_ocr_text_count < min_pages_with_fishnet_ocr_text:
        reasons.append(
            f"pages_with_fishnet_ocr_text_count {pages_with_fishnet_ocr_text_count} < min {min_pages_with_fishnet_ocr_text}"
        )

    quality_status = "FAIL" if reasons else "PASS"
    result = {
        "module": f"{VERSION}_quality_check",
        "quality_status": quality_status,
        "quality_reasons": reasons,
        "summary": summary,
        "record_count": comparison_record_count,
        "checked_at": utc_now_iso(),
    }
    if write_json_report:
        out = report_path.with_name(f"{VERSION}_quality_check.json")
        write_json(out, result)
        result["wrote"] = str(out)
    return result


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net fishnet route signal workbench v1")
    parser.add_argument("--fishnet-report", required=True)
    parser.add_argument("--current-route-manifest", default=None)
    parser.add_argument("--trace-net-root", default="local_data/organization/trace_net")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--high-confidence-threshold", type=float, default=0.85)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_fishnet_route_signal_workbench(
        fishnet_report=Path(args.fishnet_report),
        current_route_manifest=Path(args.current_route_manifest) if args.current_route_manifest else None,
        trace_net_root=Path(args.trace_net_root),
        output_dir=Path(args.output_dir),
        high_confidence_threshold=args.high_confidence_threshold,
        quality=args.quality,
    )
    print(f"Status: {payload['status']}")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net fishnet route signal workbench v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-comparison-records", type=int, default=None)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-current-routes", action="store_true")
    parser.add_argument("--max-missing-current-routes", type=int, default=None)
    parser.add_argument("--max-high-confidence-disagreements", type=int, default=None)
    parser.add_argument("--min-fishnet-ocr-text-chars", type=int, default=None)
    parser.add_argument("--min-fishnet-ocr-word-boxes", type=int, default=None)
    parser.add_argument("--min-pages-with-fishnet-ocr-text", type=int, default=None)
    args = parser.parse_args(argv)

    result = check_fishnet_route_signal_workbench_quality(
        report_path=Path(args.report_path),
        write_json_report=args.write_json,
        require_page_count=args.require_page_count,
        min_comparison_records=args.min_comparison_records,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_current_routes=args.require_current_routes,
        max_missing_current_routes=args.max_missing_current_routes,
        max_high_confidence_disagreements=args.max_high_confidence_disagreements,
        min_fishnet_ocr_text_chars=args.min_fishnet_ocr_text_chars,
        min_fishnet_ocr_word_boxes=args.min_fishnet_ocr_word_boxes,
        min_pages_with_fishnet_ocr_text=args.min_pages_with_fishnet_ocr_text,
    )
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result.get("quality_reasons"):
        print("Reasons:", json.dumps(result["quality_reasons"], sort_keys=True))
    if result.get("wrote"):
        print(f"Wrote: {result['wrote']}")
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
