"""TRACE-Net Fishnet Route Manifest Overlay v1.

Builds a read-only overlay of proposed route changes from fishnet router
hardening policy records. This module never mutates the official route
manifest. It validates policy recommendations against the current manifest
and writes an overlay artifact that downstream reviewers can inspect.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_fishnet_route_manifest_overlay_v1"
STATUS_BUILT = "FISHNET_ROUTE_MANIFEST_OVERLAY_BUILT"
STATUS_NOT_READY = "FISHNET_ROUTE_MANIFEST_OVERLAY_NOT_READY"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

ROUTE_CHANGE_AUTHORIZED = False
ROUTE_MANIFEST_WRITE_ALLOWED = False
CAN_ANSWER_DIRECTLY = False
CAN_PROVE_CLAIMS = False
ANSWER_PERMISSION = False
SOURCE_TRUTH_MUTATION_ALLOWED = False
POSTGRES_WRITE_ATTEMPT = False
QDRANT_WRITE_ATTEMPT = False
OPENSEARCH_WRITE_ATTEMPT = False

ALLOWED_CURRENT_ROUTES_DEFAULT = {"blank_candidate", "image_visual"}
ALLOWED_TARGET_ROUTE_DEFAULT = "normal_text"

PAGE_SUFFIX_RE = re.compile(r"p(\d{6})", re.IGNORECASE)
SOURCE_PAGE_RE = re.compile(r"source_p(\d{6})", re.IGNORECASE)


def safety_contract() -> Dict[str, Any]:
    return {
        "artifact_authority": "route_manifest_overlay_review_only",
        "official_route_manifest_mutated": False,
        "route_change_authorized": ROUTE_CHANGE_AUTHORIZED,
        "route_manifest_write_allowed": ROUTE_MANIFEST_WRITE_ALLOWED,
        "can_answer_directly": CAN_ANSWER_DIRECTLY,
        "can_prove_claims": CAN_PROVE_CLAIMS,
        "answer_permission": ANSWER_PERMISSION,
        "source_truth_mutation_allowed": SOURCE_TRUTH_MUTATION_ALLOWED,
        "postgres_write_allowed": False,
        "qdrant_write_allowed": False,
        "opensearch_write_allowed": False,
        "requires_human_or_downstream_review": True,
        "guidance_only": True,
    }


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")


def page_suffix(page_id: Any) -> Optional[str]:
    if page_id is None:
        return None
    text = str(page_id)
    m = SOURCE_PAGE_RE.search(text)
    if m:
        return f"p{m.group(1)}"
    m = PAGE_SUFFIX_RE.search(text)
    if m:
        return f"p{m.group(1)}"
    return None


def canonical_aliases(page_id: Any) -> List[str]:
    aliases: List[str] = []
    if page_id is None:
        return aliases
    text = str(page_id)
    aliases.append(text)
    suffix = page_suffix(text)
    if suffix:
        aliases.append(suffix)
        aliases.append(f"source_{suffix}")
    # Ordered de-duplication.
    out: List[str] = []
    seen = set()
    for alias in aliases:
        if alias not in seen:
            out.append(alias)
            seen.add(alias)
    return out


def _looks_like_route(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value in {"blank_candidate", "normal_text", "table", "image_visual", "review_required"}


def _candidate_page_id_keys() -> Tuple[str, ...]:
    return (
        "page_id",
        "current_route_page_id",
        "source_page_id",
        "trace_net_page_id",
        "canonical_page_id",
        "id",
    )


def _candidate_route_keys() -> Tuple[str, ...]:
    return (
        "selected_route",
        "route",
        "current_route",
        "recommended_route",
        "page_route",
        "primary_route",
        "route_candidate",
        "route_name",
    )


def _extract_page_route_from_mapping(obj: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
    page_id: Optional[str] = None
    route: Optional[str] = None

    for key in _candidate_page_id_keys():
        value = obj.get(key)
        if isinstance(value, (str, int)):
            text = str(value)
            if page_suffix(text) or key in {"page_id", "id"}:
                page_id = text
                break

    for key in _candidate_route_keys():
        value = obj.get(key)
        if _looks_like_route(value):
            route = str(value)
            break

    # Common nested card shapes.
    for nested_key in ("page_route_card", "route_card", "card", "page"):
        nested = obj.get(nested_key)
        if isinstance(nested, Mapping):
            nested_result = _extract_page_route_from_mapping(nested)
            if nested_result:
                nested_page_id, nested_route = nested_result
                page_id = page_id or nested_page_id
                route = route or nested_route

    if page_id and route:
        return page_id, route
    return None


def _walk_mappings(obj: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(obj, Mapping):
        yield obj
        for value in obj.values():
            yield from _walk_mappings(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_mappings(item)


def extract_current_routes(manifest_payload: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract route records from many possible route-manifest shapes.

    Returns a dict keyed by exact page id and aliases. Each value contains the
    canonical page id and route. Alias records point at the same value object.
    """
    by_alias: Dict[str, Dict[str, Any]] = {}
    page_records: Dict[str, Dict[str, Any]] = {}

    for mapping in _walk_mappings(manifest_payload):
        result = _extract_page_route_from_mapping(mapping)
        if not result:
            continue
        pid, route = result
        suffix = page_suffix(pid)
        canonical_id = pid
        if suffix and len(pid) <= 8:
            canonical_id = pid
        record = {
            "current_route_page_id": canonical_id,
            "current_route": route,
            "page_suffix": suffix,
        }
        dedupe_key = suffix or canonical_id
        if dedupe_key in page_records:
            # Prefer a more descriptive canonical id if available.
            existing = page_records[dedupe_key]
            if len(canonical_id) > len(str(existing.get("current_route_page_id", ""))):
                existing.update(record)
            continue
        page_records[dedupe_key] = record

    for record in page_records.values():
        pid = record["current_route_page_id"]
        for alias in canonical_aliases(pid):
            by_alias[alias] = record
        suffix = record.get("page_suffix")
        if suffix:
            by_alias[str(suffix)] = record
            by_alias[f"source_{suffix}"] = record
    return by_alias


def match_current_route(policy_record: Mapping[str, Any], route_index: Mapping[str, Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    candidates = [
        policy_record.get("current_route_page_id"),
        policy_record.get("page_id"),
        policy_record.get("source_page_id"),
        policy_record.get("trace_net_page_id"),
    ]
    for candidate in candidates:
        for alias in canonical_aliases(candidate):
            if alias in route_index:
                strategy = "exact" if str(candidate) == alias else "alias"
                return route_index[alias], strategy
    suffix = page_suffix(policy_record.get("page_id"))
    if suffix and suffix in route_index:
        return route_index[suffix], "suffix"
    return None, "missing"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_overlay_record(
    idx: int,
    policy_record: Mapping[str, Any],
    current_match: Optional[Mapping[str, Any]],
    match_strategy: str,
) -> Dict[str, Any]:
    source_page_id = str(policy_record.get("page_id") or f"unknown_{idx:06d}")
    current_route = policy_record.get("current_route")
    current_route_page_id = policy_record.get("current_route_page_id")
    current_route_manifest_route = None
    current_route_manifest_page_id = None
    current_route_match_ok = False

    if current_match:
        current_route_manifest_route = current_match.get("current_route")
        current_route_manifest_page_id = current_match.get("current_route_page_id")
        current_route_match_ok = (current_route_manifest_route == current_route) or current_route is None

    target = str(policy_record.get("recommended_target_route") or "normal_text")
    route_pair = f"{current_route}->{target}"
    evidence = {
        "fishnet_route_confidence": _safe_float(policy_record.get("fishnet_route_confidence")),
        "fishnet_ocr_text_length": _safe_int(policy_record.get("fishnet_ocr_text_length")),
        "fishnet_ocr_word_box_count": _safe_int(policy_record.get("fishnet_ocr_word_box_count")),
        "fishnet_ocr_sample_text": policy_record.get("fishnet_ocr_sample_text") or "",
        "overlay_candidates": policy_record.get("overlay_candidates") or [],
        "recommendation_type": policy_record.get("recommendation_type"),
        "source_review_priority": policy_record.get("review_priority"),
    }

    validation_reasons: List[str] = []
    if not current_match:
        validation_reasons.append("current_route_manifest_match_missing")
    elif not current_route_match_ok:
        validation_reasons.append("current_route_manifest_route_mismatch")
    if policy_record.get("route_change_authorized"):
        validation_reasons.append("source_policy_authorized_route_change_unexpected")
    if policy_record.get("route_manifest_write_allowed"):
        validation_reasons.append("source_policy_route_manifest_write_allowed_unexpected")

    validation_status = "overlay_ready_for_review" if not validation_reasons else "overlay_requires_review"

    return {
        "overlay_record_id": f"fishnet_route_overlay_{idx:06d}",
        "module_version": MODULE_NAME,
        "page_id": source_page_id,
        "page_suffix": page_suffix(source_page_id),
        "current_route_page_id": current_route_page_id,
        "current_route_manifest_page_id": current_route_manifest_page_id,
        "current_route": current_route,
        "current_route_manifest_route": current_route_manifest_route,
        "current_route_match_strategy": match_strategy,
        "current_route_match_ok": current_route_match_ok,
        "proposed_target_route": target,
        "recommended_target_route": target,
        "route_pair": route_pair,
        "overlay_action": "propose_route_review_overlay",
        "overlay_status": "proposed_review_only",
        "validation_status": validation_status,
        "validation_reason_codes": validation_reasons,
        "recommendation_type": policy_record.get("recommendation_type"),
        "recommendation_status": policy_record.get("recommendation_status"),
        "review_priority": policy_record.get("review_priority") or "high",
        "fishnet_route_confidence": evidence["fishnet_route_confidence"],
        "fishnet_ocr_text_length": evidence["fishnet_ocr_text_length"],
        "fishnet_ocr_word_box_count": evidence["fishnet_ocr_word_box_count"],
        "fishnet_ocr_sample_text": evidence["fishnet_ocr_sample_text"],
        "overlay_candidates": evidence["overlay_candidates"],
        "evidence": evidence,
        "route_change_authorized": ROUTE_CHANGE_AUTHORIZED,
        "route_manifest_write_allowed": ROUTE_MANIFEST_WRITE_ALLOWED,
        "official_route_manifest_mutated": False,
        "answer_permission": ANSWER_PERMISSION,
        "can_answer_directly": CAN_ANSWER_DIRECTLY,
        "can_prove_claims": CAN_PROVE_CLAIMS,
        "source_truth_mutation_allowed": SOURCE_TRUTH_MUTATION_ALLOWED,
        "postgres_write_attempt": POSTGRES_WRITE_ATTEMPT,
        "qdrant_write_attempt": QDRANT_WRITE_ATTEMPT,
        "opensearch_write_attempt": OPENSEARCH_WRITE_ATTEMPT,
        "safety_contract": safety_contract(),
    }


def summarize(records: Sequence[Mapping[str, Any]], policy_payload: Mapping[str, Any], current_route_count: int) -> Dict[str, Any]:
    def count_by(key: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for r in records:
            value = str(r.get(key))
            out[value] = out.get(value, 0) + 1
        return out

    return {
        "overlay_record_count": len(records),
        "source_policy_quality_status": policy_payload.get("quality_status"),
        "source_policy_record_count": len(policy_payload.get("records") or []),
        "current_route_manifest_page_count": current_route_count,
        "proposed_route_counts": count_by("proposed_target_route"),
        "current_route_counts": count_by("current_route"),
        "route_pair_counts": count_by("route_pair"),
        "overlay_status_counts": count_by("overlay_status"),
        "validation_status_counts": count_by("validation_status"),
        "review_priority_counts": count_by("review_priority"),
        "current_route_match_strategy_counts": count_by("current_route_match_strategy"),
        "current_route_match_ok_count": sum(1 for r in records if r.get("current_route_match_ok")),
        "current_route_match_missing_count": sum(1 for r in records if r.get("current_route_match_strategy") == "missing"),
        "normal_text_overlay_proposal_count": sum(1 for r in records if r.get("proposed_target_route") == "normal_text"),
        "review_required_before_manifest_change_count": sum(1 for r in records if r.get("recommendation_status") == "review_required_before_route_manifest_change"),
        "route_change_authorized_count": sum(1 for r in records if r.get("route_change_authorized")),
        "route_manifest_write_allowed_count": sum(1 for r in records if r.get("route_manifest_write_allowed")),
        "official_route_manifest_mutated_count": sum(1 for r in records if r.get("official_route_manifest_mutated")),
        "unsafe_record_count": 0,
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
    }


def evaluate_quality(
    payload: Mapping[str, Any],
    *,
    min_overlay_records: int = 1,
    min_normal_text_overlay_proposals: int = 1,
    require_source_policy_quality_pass: bool = False,
    require_all_current_routes_matched: bool = False,
    max_route_change_authorized: int = 0,
    max_route_manifest_write_allowed: int = 0,
    max_official_manifest_mutated: int = 0,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
) -> Tuple[str, List[str]]:
    summary = dict(payload.get("summary") or {})
    failures: List[str] = []

    def check_min(key: str, minimum: int) -> None:
        if int(summary.get(key, 0) or 0) < minimum:
            failures.append(f"{key} below minimum {minimum}: {summary.get(key)}")

    def check_max(key: str, maximum: int) -> None:
        if int(summary.get(key, 0) or 0) > maximum:
            failures.append(f"{key} above maximum {maximum}: {summary.get(key)}")

    check_min("overlay_record_count", min_overlay_records)
    check_min("normal_text_overlay_proposal_count", min_normal_text_overlay_proposals)
    check_max("unsafe_record_count", max_unsafe)
    check_max("route_change_authorized_count", max_route_change_authorized)
    check_max("route_manifest_write_allowed_count", max_route_manifest_write_allowed)
    check_max("official_route_manifest_mutated_count", max_official_manifest_mutated)

    if require_source_policy_quality_pass and summary.get("source_policy_quality_status") != QUALITY_PASS:
        failures.append("source_policy_quality_status is not PASS")
    if require_all_current_routes_matched and int(summary.get("current_route_match_missing_count", 0) or 0) != 0:
        failures.append("current_route_match_missing_count is not 0")
    if require_no_answer_permission:
        check_max("answer_permission_count", 0)
        check_max("can_answer_directly_count", 0)
        check_max("can_prove_claims_count", 0)
    if require_no_source_truth_mutation:
        check_max("source_truth_mutation_allowed_count", 0)

    return (QUALITY_FAIL if failures else QUALITY_PASS), failures


def build_route_manifest_overlay(
    *,
    policy_path: Path,
    current_route_manifest_path: Path,
    output_dir: Path,
    quality: bool = True,
) -> Dict[str, Any]:
    policy_payload = read_json(policy_path)
    current_payload = read_json(current_route_manifest_path)
    route_index = extract_current_routes(current_payload)
    unique_current_pages = {
        (v.get("page_suffix") or v.get("current_route_page_id")): v for v in route_index.values()
    }

    source_records = policy_payload.get("records") or []
    overlay_records: List[Dict[str, Any]] = []
    for idx, policy_record in enumerate(source_records, start=1):
        current_match, strategy = match_current_route(policy_record, route_index)
        overlay_records.append(build_overlay_record(idx, policy_record, current_match, strategy))

    payload: Dict[str, Any] = {
        "module": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": QUALITY_PASS,
        "source_policy_path": str(policy_path),
        "current_route_manifest_path": str(current_route_manifest_path),
        "safety_contract": safety_contract(),
        "records": overlay_records,
    }
    payload["summary"] = summarize(overlay_records, policy_payload, len(unique_current_pages))

    if quality:
        q_status, failures = evaluate_quality(
            payload,
            min_overlay_records=1,
            min_normal_text_overlay_proposals=1,
            require_source_policy_quality_pass=True,
            max_route_change_authorized=0,
            max_route_manifest_write_allowed=0,
            max_official_manifest_mutated=0,
            max_unsafe=0,
            require_no_answer_permission=True,
            require_no_source_truth_mutation=True,
        )
        payload["quality_status"] = q_status
        payload["quality_failures"] = failures

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_fishnet_route_manifest_overlay_v1.json"
    write_json(report_path, payload)
    write_jsonl(output_dir / "trace_net_fishnet_route_manifest_overlay_v1_records.jsonl", overlay_records)
    write_json(output_dir / "trace_net_fishnet_route_manifest_overlay_v1_summary.json", payload["summary"])
    write_markdown(output_dir / "trace_net_fishnet_route_manifest_overlay_v1.md", payload)
    if quality:
        write_json(output_dir / "trace_net_fishnet_route_manifest_overlay_v1_quality.json", {
            "quality_status": payload["quality_status"],
            "summary": payload["summary"],
            "quality_failures": payload.get("quality_failures", []),
        })
    return payload


def write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    records = payload.get("records") or []
    summary = payload.get("summary") or {}
    lines: List[str] = []
    lines.append("# TRACE-Net Fishnet Route Manifest Overlay v1")
    lines.append("")
    lines.append(f"Quality status: **{payload.get('quality_status')}**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Overlay records: {summary.get('overlay_record_count')}")
    lines.append(f"- Normal-text overlay proposals: {summary.get('normal_text_overlay_proposal_count')}")
    lines.append(f"- Route changes authorized: {summary.get('route_change_authorized_count')}")
    lines.append(f"- Route manifest writes allowed: {summary.get('route_manifest_write_allowed_count')}")
    lines.append(f"- Official route manifest mutated: {summary.get('official_route_manifest_mutated_count')}")
    lines.append("")
    lines.append("## Route pairs")
    lines.append("")
    for key, value in sorted((summary.get("route_pair_counts") or {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Overlay records")
    for record in records:
        lines.append("")
        lines.append(f"### {record.get('page_id')} — {record.get('route_pair')}")
        lines.append("")
        lines.append(f"- Overlay status: `{record.get('overlay_status')}`")
        lines.append(f"- Validation status: `{record.get('validation_status')}`")
        lines.append(f"- Current route page id: `{record.get('current_route_manifest_page_id') or record.get('current_route_page_id')}`")
        lines.append(f"- Current route: `{record.get('current_route')}`")
        lines.append(f"- Proposed target route: `{record.get('proposed_target_route')}`")
        lines.append(f"- Recommendation type: `{record.get('recommendation_type')}`")
        lines.append(f"- Review priority: `{record.get('review_priority')}`")
        lines.append(f"- Confidence: `{record.get('fishnet_route_confidence')}`")
        lines.append(f"- OCR text length: `{record.get('fishnet_ocr_text_length')}`")
        lines.append(f"- OCR word boxes: `{record.get('fishnet_ocr_word_box_count')}`")
        lines.append(f"- Route change authorized: `{record.get('route_change_authorized')}`")
        lines.append(f"- Route manifest write allowed: `{record.get('route_manifest_write_allowed')}`")
        lines.append(f"- Overlay candidates: `{record.get('overlay_candidates')}`")
        sample = str(record.get("fishnet_ocr_sample_text") or "").strip()
        if sample:
            lines.append("")
            lines.append(f"> {sample[:500]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net fishnet route manifest overlay v1")
    parser.add_argument("--policy", required=True, help="Fishnet router hardening policy JSON path")
    parser.add_argument("--current-route-manifest", required=True, help="Current official route manifest JSON path")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--quality", action="store_true", help="Evaluate quality during build")
    args = parser.parse_args(argv)

    payload = build_route_manifest_overlay(
        policy_path=Path(args.policy),
        current_route_manifest_path=Path(args.current_route_manifest),
        output_dir=Path(args.output_dir),
        quality=args.quality,
    )
    print(f"Status: {payload['status']}")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == QUALITY_PASS else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net fishnet route manifest overlay v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-overlay-records", type=int, default=1)
    parser.add_argument("--min-normal-text-overlay-proposals", type=int, default=1)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-route-change-authorized", type=int, default=0)
    parser.add_argument("--max-route-manifest-write-allowed", type=int, default=0)
    parser.add_argument("--max-official-manifest-mutated", type=int, default=0)
    parser.add_argument("--require-source-policy-quality-pass", action="store_true")
    parser.add_argument("--require-all-current-routes-matched", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    report_path = Path(args.report_path)
    payload = read_json(report_path)
    status, failures = evaluate_quality(
        payload,
        min_overlay_records=args.min_overlay_records,
        min_normal_text_overlay_proposals=args.min_normal_text_overlay_proposals,
        require_source_policy_quality_pass=args.require_source_policy_quality_pass,
        require_all_current_routes_matched=args.require_all_current_routes_matched,
        max_route_change_authorized=args.max_route_change_authorized,
        max_route_manifest_write_allowed=args.max_route_manifest_write_allowed,
        max_official_manifest_mutated=args.max_official_manifest_mutated,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
    )
    print(f"Quality status: {status}")
    print("Summary:", json.dumps(payload.get("summary") or {}, sort_keys=True))
    if failures:
        print("Failures:")
        for failure in failures:
            print(f"- {failure}")
    if args.write_json:
        out = report_path.with_name("trace_net_fishnet_route_manifest_overlay_v1_quality_check.json")
        write_json(out, {"quality_status": status, "summary": payload.get("summary") or {}, "quality_failures": failures})
        print(f"Wrote: {out}")
    return 0 if status == QUALITY_PASS else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
