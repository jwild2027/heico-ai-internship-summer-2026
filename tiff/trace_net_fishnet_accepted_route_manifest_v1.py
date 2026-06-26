
"""TRACE-Net Fishnet Accepted Route Manifest v1.

This module applies reviewed fishnet route-manifest overlay proposals into a new
accepted route manifest artifact.

Safety contract:
- Does not overwrite the official/current route manifest.
- Does not mutate source-truth artifacts.
- Does not write Postgres, Qdrant, or OpenSearch.
- Does not grant answer permission.
- Requires explicit --accept-reviewed-overlays to authorize the route changes.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


MODULE_VERSION = "trace_net_fishnet_accepted_route_manifest_v1"
REPORT_NAME = "trace_net_fishnet_accepted_route_manifest_v1.json"


ROUTE_KEYS = (
    "selected_route",
    "recommended_route",
    "primary_route",
    "route",
    "page_route",
    "current_route",
)

PAGE_ID_KEYS = (
    "page_id",
    "source_page_id",
    "current_route_page_id",
    "current_route_manifest_page_id",
)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _flatten_records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in (
        "records",
        "page_route_records",
        "page_route_cards",
        "route_records",
        "routes",
        "cards",
        "items",
        "pages",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    # Some manifests wrap route records in a shallow dict keyed by page id.
    by_page = payload.get("by_page") or payload.get("page_routes_by_id")
    if isinstance(by_page, dict):
        return [r for r in by_page.values() if isinstance(r, dict)]
    return []


def _recursive_get_first(obj: Any, keys: Sequence[str]) -> Optional[Any]:
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if value not in (None, ""):
                return value
        for value in obj.values():
            found = _recursive_get_first(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _recursive_get_first(value, keys)
            if found not in (None, ""):
                return found
    return None


def _extract_page_id(record: Mapping[str, Any]) -> Optional[str]:
    value = _recursive_get_first(record, PAGE_ID_KEYS)
    return str(value) if value not in (None, "") else None


def _extract_route(record: Mapping[str, Any]) -> Optional[str]:
    value = _recursive_get_first(record, ROUTE_KEYS)
    return str(value) if value not in (None, "") else None


def _source_aliases(page_id: str) -> List[str]:
    """Return conservative aliases for source_p000001 and canonical t_p_*_p000001 ids."""
    aliases = {page_id}
    text = str(page_id)
    # source_p000123 -> p000123 and canonical suffix matching.
    if text.startswith("source_p"):
        aliases.add(text.replace("source_", ""))
    # Any id with pNNNNNN suffix gets source_pNNNNNN alias.
    suffix = None
    for token in text.replace("-", "_").split("_"):
        if token.startswith("p") and token[1:].isdigit():
            suffix = token
    if suffix:
        aliases.add(suffix)
        aliases.add(f"source_{suffix}")
    return sorted(aliases)


@dataclass(frozen=True)
class RouteIndexEntry:
    index: int
    page_id: str
    route: str
    raw_record: Dict[str, Any]


def _build_route_index(route_records: Sequence[Mapping[str, Any]]) -> Dict[str, RouteIndexEntry]:
    index: Dict[str, RouteIndexEntry] = {}
    for idx, record in enumerate(route_records):
        page_id = _extract_page_id(record)
        route = _extract_route(record)
        if not page_id or not route:
            continue
        entry = RouteIndexEntry(index=idx, page_id=page_id, route=route, raw_record=dict(record))
        for alias in _source_aliases(page_id):
            index.setdefault(alias, entry)
        # Also support source_pNNNNNN from ordered index when canonical ids are missing.
        index.setdefault(f"source_p{idx+1:06d}", entry)
    return index


def _overlay_records(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return _flatten_records(payload)


def _safe_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def _safety_contract(*, route_change_authorized: bool) -> Dict[str, Any]:
    return {
        "artifact_authority": "accepted_route_manifest_artifact_only",
        "route_change_authorized": bool(route_change_authorized),
        "official_route_manifest_mutation_allowed": False,
        "official_route_manifest_write_allowed": False,
        "source_truth_mutation_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "answer_permission": False,
        "postgres_write_allowed": False,
        "qdrant_write_allowed": False,
        "opensearch_write_allowed": False,
        "requires_downstream_route_dispatch_to_use_this_manifest_explicitly": True,
    }


def _canonical_accepted_record(
    *,
    route_entry: RouteIndexEntry,
    overlay: Mapping[str, Any],
    accepted: bool,
) -> Dict[str, Any]:
    current_route = str(overlay.get("current_route") or route_entry.route)
    target_route = str(overlay.get("proposed_target_route") or overlay.get("recommended_target_route") or "")
    if not target_route:
        target_route = current_route
    accepted_route = target_route if accepted else current_route
    route_changed = accepted and accepted_route != current_route

    page_id = str(overlay.get("page_id") or route_entry.page_id)
    current_manifest_page_id = str(
        overlay.get("current_route_manifest_page_id")
        or overlay.get("current_route_page_id")
        or route_entry.page_id
    )

    return {
        "accepted_route_manifest_version": MODULE_VERSION,
        "page_id": page_id,
        "current_route_manifest_page_id": current_manifest_page_id,
        "source_route_manifest_index": route_entry.index,
        "original_route": current_route,
        "selected_route": accepted_route,
        "accepted_route": accepted_route,
        "proposed_target_route": target_route,
        "route_changed": route_changed,
        "route_pair": f"{current_route}->{accepted_route}",
        "policy_route_pair": overlay.get("route_pair") or f"{current_route}->{target_route}",
        "acceptance_status": "accepted_reviewed_overlay" if route_changed else "no_change",
        "acceptance_reason": "explicit_accept_reviewed_fishnet_overlay" if route_changed else "route_already_matches",
        "review_priority": overlay.get("review_priority"),
        "recommendation_type": overlay.get("recommendation_type"),
        "fishnet_route_confidence": overlay.get("fishnet_route_confidence"),
        "fishnet_ocr_text_length": overlay.get("fishnet_ocr_text_length"),
        "fishnet_ocr_word_box_count": overlay.get("fishnet_ocr_word_box_count"),
        "fishnet_ocr_sample_text": overlay.get("fishnet_ocr_sample_text"),
        "overlay_status": overlay.get("overlay_status"),
        "validation_status": overlay.get("validation_status"),
        "overlay_candidates": overlay.get("overlay_candidates") or [],
        "route_change_authorized": route_changed,
        "route_manifest_write_allowed": False,
        "official_route_manifest_mutated": False,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "safety_contract": _safety_contract(route_change_authorized=route_changed),
    }


def build_accepted_route_manifest(
    *,
    overlay_path: Path,
    current_route_manifest_path: Path,
    output_dir: Path,
    accept_reviewed_overlays: bool,
) -> Dict[str, Any]:
    if not accept_reviewed_overlays:
        raise ValueError(
            "Refusing to apply reviewed overlays without explicit --accept-reviewed-overlays."
        )

    overlay_payload = _read_json(overlay_path)
    current_payload = _read_json(current_route_manifest_path)

    overlay_quality = overlay_payload.get("quality_status")
    overlays = _overlay_records(overlay_payload)
    route_records = _flatten_records(current_payload)
    route_index = _build_route_index(route_records)

    accepted_delta_records: List[Dict[str, Any]] = []
    missing_current_route: List[Dict[str, Any]] = []

    for overlay in overlays:
        if overlay.get("overlay_status") not in (None, "proposed_review_only", "overlay_ready_for_review"):
            continue
        if overlay.get("validation_status") not in (None, "overlay_ready_for_review"):
            continue

        page_id = str(overlay.get("page_id") or "")
        candidates = []
        for key in ("current_route_manifest_page_id", "current_route_page_id", "page_id"):
            if overlay.get(key):
                candidates.extend(_source_aliases(str(overlay.get(key))))
        candidates.extend(_source_aliases(page_id))
        seen = set()
        entry = None
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate in route_index:
                entry = route_index[candidate]
                break
        if entry is None:
            missing_current_route.append({"page_id": page_id, "overlay": overlay})
            continue

        accepted_delta_records.append(
            _canonical_accepted_record(route_entry=entry, overlay=overlay, accepted=True)
        )

    # Build a complete accepted manifest from the current manifest plus explicit deltas.
    changes_by_manifest_page_id = {
        record["current_route_manifest_page_id"]: record for record in accepted_delta_records
    }
    changes_by_source_alias = {
        alias: record
        for record in accepted_delta_records
        for alias in _source_aliases(str(record["current_route_manifest_page_id"]))
    }

    accepted_page_records: List[Dict[str, Any]] = []
    for idx, original in enumerate(route_records):
        page_id = _extract_page_id(original) or f"source_p{idx+1:06d}"
        original_route = _extract_route(original) or "unknown"
        change = changes_by_manifest_page_id.get(page_id)
        if not change:
            for alias in _source_aliases(page_id):
                if alias in changes_by_source_alias:
                    change = changes_by_source_alias[alias]
                    break

        selected_route = change["accepted_route"] if change else original_route
        accepted_page_records.append(
            {
                "accepted_route_manifest_version": MODULE_VERSION,
                "page_id": page_id,
                "source_route_manifest_index": idx,
                "original_route": original_route,
                "selected_route": selected_route,
                "accepted_route": selected_route,
                "route_changed": bool(change),
                "route_change_authorized": bool(change),
                "route_change_source": "fishnet_route_manifest_overlay_v1" if change else "current_route_manifest",
                "change_record_page_id": change.get("page_id") if change else None,
                "fishnet_route_confidence": change.get("fishnet_route_confidence") if change else None,
                "review_priority": change.get("review_priority") if change else None,
                "route_manifest_write_allowed": False,
                "official_route_manifest_mutated": False,
                "source_truth_mutation_allowed": False,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "safety_contract": _safety_contract(route_change_authorized=bool(change)),
            }
        )

    original_counts = Counter(record["original_route"] for record in accepted_page_records)
    accepted_counts = Counter(record["accepted_route"] for record in accepted_page_records)
    changed_counts = Counter(record["accepted_route"] for record in accepted_page_records if record["route_changed"])
    route_pair_counts = Counter(
        f"{record['original_route']}->{record['accepted_route']}"
        for record in accepted_page_records
        if record["route_changed"]
    )

    summary = {
        "source_overlay_quality_status": overlay_quality,
        "source_overlay_record_count": len(overlays),
        "current_route_manifest_page_count": len(route_records),
        "accepted_route_manifest_page_count": len(accepted_page_records),
        "accepted_delta_record_count": len(accepted_delta_records),
        "route_change_authorized_count": sum(1 for r in accepted_page_records if r["route_change_authorized"]),
        "route_manifest_write_allowed_count": 0,
        "official_route_manifest_mutated_count": 0,
        "current_route_match_missing_count": len(missing_current_route),
        "original_route_counts": dict(sorted(original_counts.items())),
        "accepted_route_counts": dict(sorted(accepted_counts.items())),
        "changed_target_route_counts": dict(sorted(changed_counts.items())),
        "accepted_route_pair_counts": dict(sorted(route_pair_counts.items())),
        "normal_text_accepted_change_count": changed_counts.get("normal_text", 0),
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    quality_status = "PASS"
    if overlay_quality != "PASS":
        quality_status = "FAIL"
    if missing_current_route:
        quality_status = "FAIL"
    if len(accepted_page_records) != len(route_records):
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "FISHNET_ACCEPTED_ROUTE_MANIFEST_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_overlay_path": str(overlay_path),
        "source_current_route_manifest_path": str(current_route_manifest_path),
        "records": accepted_page_records,
        "accepted_delta_records": accepted_delta_records,
        "missing_current_route_records": missing_current_route,
        "safety_contract": _safety_contract(route_change_authorized=bool(accepted_delta_records)),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / "trace_net_fishnet_accepted_route_manifest_v1_records.jsonl", accepted_page_records)
    _write_jsonl(output_dir / "trace_net_fishnet_accepted_route_manifest_v1_deltas.jsonl", accepted_delta_records)
    _write_json(output_dir / "trace_net_fishnet_accepted_route_manifest_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_fishnet_accepted_route_manifest_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_fishnet_accepted_route_manifest_v1.md", payload)

    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    delta_records = payload.get("accepted_delta_records") or []
    lines = [
        "# TRACE-Net Fishnet Accepted Route Manifest v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Current manifest pages: {summary.get('current_route_manifest_page_count')}",
        f"- Accepted manifest pages: {summary.get('accepted_route_manifest_page_count')}",
        f"- Accepted route changes: {summary.get('accepted_delta_record_count')}",
        f"- Route changes authorized: {summary.get('route_change_authorized_count')}",
        f"- Official manifest mutated: {summary.get('official_route_manifest_mutated_count')}",
        f"- Route manifest write allowed: {summary.get('route_manifest_write_allowed_count')}",
        "",
        "## Route counts",
        "",
        f"- Original route counts: `{summary.get('original_route_counts')}`",
        f"- Accepted route counts: `{summary.get('accepted_route_counts')}`",
        f"- Accepted route-pair counts: `{summary.get('accepted_route_pair_counts')}`",
        "",
        "## Accepted deltas",
        "",
    ]
    for record in delta_records:
        lines.extend(
            [
                f"### {record.get('page_id')} — {record.get('original_route')}->{record.get('accepted_route')}",
                "",
                f"- Current manifest page id: `{record.get('current_route_manifest_page_id')}`",
                f"- Confidence: `{record.get('fishnet_route_confidence')}`",
                f"- OCR text length: `{record.get('fishnet_ocr_text_length')}`",
                f"- OCR word boxes: `{record.get('fishnet_ocr_word_box_count')}`",
                f"- Route change authorized: `{record.get('route_change_authorized')}`",
                f"- Official manifest mutated: `{record.get('official_route_manifest_mutated')}`",
                "",
                f"> {(record.get('fishnet_ocr_sample_text') or '')[:260]}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def check_accepted_route_manifest_quality(
    *,
    report_path: Path,
    require_source_overlay_quality_pass: bool = False,
    require_page_count: Optional[int] = None,
    min_accepted_route_changes: int = 0,
    min_normal_text_changes: int = 0,
    max_missing_current_routes: Optional[int] = None,
    max_unsafe: int = 0,
    max_official_manifest_mutated: int = 0,
    max_route_manifest_write_allowed: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_route_changes_authorized: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def fail_if(condition: bool, msg: str) -> None:
        if condition:
            failures.append(msg)

    if require_source_overlay_quality_pass:
        fail_if(summary.get("source_overlay_quality_status") != "PASS", "source overlay quality is not PASS")
    if require_page_count is not None:
        fail_if(summary.get("accepted_route_manifest_page_count") != require_page_count, "accepted page count mismatch")
    fail_if(summary.get("accepted_delta_record_count", 0) < min_accepted_route_changes, "not enough accepted route changes")
    fail_if(summary.get("normal_text_accepted_change_count", 0) < min_normal_text_changes, "not enough normal_text accepted changes")
    if max_missing_current_routes is not None:
        fail_if(summary.get("current_route_match_missing_count", 0) > max_missing_current_routes, "too many missing current route matches")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe count exceeded")
    fail_if(summary.get("official_route_manifest_mutated_count", 0) > max_official_manifest_mutated, "official manifest mutation count exceeded")
    fail_if(summary.get("route_manifest_write_allowed_count", 0) > max_route_manifest_write_allowed, "route manifest write allowed count exceeded")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")
    if require_route_changes_authorized:
        fail_if(summary.get("route_change_authorized_count", 0) < min_accepted_route_changes, "route changes not authorized")

    quality_status = "FAIL" if failures else "PASS"
    result = {
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }
    return result


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net fishnet accepted route manifest v1.")
    parser.add_argument("--overlay", required=True)
    parser.add_argument("--current-route-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--accept-reviewed-overlays", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_accepted_route_manifest(
        overlay_path=Path(args.overlay),
        current_route_manifest_path=Path(args.current_route_manifest),
        output_dir=Path(args.output_dir),
        accept_reviewed_overlays=args.accept_reviewed_overlays,
    )

    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net fishnet accepted route manifest v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-overlay-quality-pass", action="store_true")
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-accepted-route-changes", type=int, default=0)
    parser.add_argument("--min-normal-text-changes", type=int, default=0)
    parser.add_argument("--max-missing-current-routes", type=int)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-official-manifest-mutated", type=int, default=0)
    parser.add_argument("--max-route-manifest-write-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-route-changes-authorized", action="store_true")
    args = parser.parse_args(argv)

    result = check_accepted_route_manifest_quality(
        report_path=Path(args.report_path),
        require_source_overlay_quality_pass=args.require_source_overlay_quality_pass,
        require_page_count=args.require_page_count,
        min_accepted_route_changes=args.min_accepted_route_changes,
        min_normal_text_changes=args.min_normal_text_changes,
        max_missing_current_routes=args.max_missing_current_routes,
        max_unsafe=args.max_unsafe,
        max_official_manifest_mutated=args.max_official_manifest_mutated,
        max_route_manifest_write_allowed=args.max_route_manifest_write_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_route_changes_authorized=args.require_route_changes_authorized,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_fishnet_accepted_route_manifest_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
