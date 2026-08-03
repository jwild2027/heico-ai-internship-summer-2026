
"""TRACE-Net Fishnet Route Dispatch Handoff v1.

Reads an accepted route manifest and emits route-specific handoff queues for:
- normal_text
- blank_candidate
- table
- image_visual

Safety contract:
- artifact-only handoff; does not execute processors.
- no Postgres, Qdrant, or OpenSearch writes.
- no source-truth mutation.
- no answer permission.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


MODULE_VERSION = "trace_net_fishnet_route_dispatch_handoff_v1"
REPORT_NAME = "trace_net_fishnet_route_dispatch_handoff_v1.json"

SUPPORTED_ROUTES = ("normal_text", "blank_candidate", "table", "image_visual")

ROUTE_PROCESSOR_CONTRACTS = {
    "normal_text": {
        "handoff_name": "normal_text_handoff",
        "processor_family": "normal_text_page_context_route",
        "primary_processor_contract": "page_context_v2_and_text_retrieval_helpers",
        "dispatch_status": "ready_for_normal_text_route",
        "route_outputs": [
            "page_context_v2 guidance",
            "normal text retrieval helpers",
            "Dublin Core/source metadata enrichment",
        ],
        "safety_note": "normal_text handoff creates context artifacts only; no answer permission.",
    },
    "blank_candidate": {
        "handoff_name": "blank_candidate_handoff",
        "processor_family": "blank_confirmation_route",
        "primary_processor_contract": "blank_source_trace_confirmation_and_review_queue",
        "dispatch_status": "ready_for_blank_confirmation_route",
        "route_outputs": [
            "blank candidate confirmation",
            "blank-source trace review signal",
            "review queue item if OCR/ink conflict exists",
        ],
        "safety_note": "blank handoff does not delete pages or suppress source truth.",
    },
    "table": {
        "handoff_name": "table_handoff",
        "processor_family": "table_extraction_route",
        "primary_processor_contract": "table_line_geometry_and_table_value_extraction",
        "dispatch_status": "ready_for_table_route",
        "route_outputs": [
            "table line geometry",
            "table value extraction",
            "table evidence packaging",
            "exact table search adapter",
        ],
        "safety_note": "table handoff creates reviewable evidence; no direct answer permission.",
    },
    "image_visual": {
        "handoff_name": "image_visual_handoff",
        "processor_family": "image_visual_observer_route",
        "primary_processor_contract": "visual_observer_callout_and_diagram_route",
        "dispatch_status": "ready_for_image_visual_route",
        "route_outputs": [
            "visual observer route",
            "callout detection",
            "visual part/callout review signals",
        ],
        "safety_note": "image handoff is visual guidance/review only; source-truth citations still required.",
    },
}


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
        "accepted_route_records",
        "accepted_records",
        "page_route_records",
        "routes",
        "pages",
        "items",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def _selected_route(record: Mapping[str, Any]) -> str:
    for key in ("accepted_route", "selected_route", "route", "primary_route", "recommended_route"):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return "unknown"


def _page_id(record: Mapping[str, Any], index: int) -> str:
    for key in ("page_id", "current_route_manifest_page_id", "source_page_id"):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return f"unknown_page_{index+1:06d}"


def _source_page_id(record: Mapping[str, Any]) -> Optional[str]:
    value = record.get("change_record_page_id") or record.get("source_page_id")
    return str(value) if value not in (None, "") else None


def _safety_contract(route: str, route_changed: bool) -> Dict[str, Any]:
    return {
        "artifact_authority": "route_dispatch_handoff_only",
        "processor_execution_allowed": False,
        "route_handoff_allowed": True,
        "route": route,
        "route_change_authorized": bool(route_changed),
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "postgres_write_allowed": False,
        "qdrant_write_allowed": False,
        "opensearch_write_allowed": False,
        "official_route_manifest_mutation_allowed": False,
    }


def _handoff_record(
    *,
    record: Mapping[str, Any],
    index: int,
    accepted_manifest_path: Path,
) -> Dict[str, Any]:
    route = _selected_route(record)
    contract = ROUTE_PROCESSOR_CONTRACTS.get(route, {
        "handoff_name": "unknown_route_handoff",
        "processor_family": "unknown_route_review",
        "primary_processor_contract": "manual_review_required",
        "dispatch_status": "unknown_route_review_required",
        "route_outputs": ["manual route triage"],
        "safety_note": "unsupported route must be reviewed before dispatch.",
    })
    route_changed = bool(record.get("route_changed") or record.get("route_change_authorized"))
    original_route = record.get("original_route")
    page_id = _page_id(record, index)
    source_page_id = _source_page_id(record)

    return {
        "route_dispatch_handoff_version": MODULE_VERSION,
        "page_id": page_id,
        "source_page_id": source_page_id,
        "source_route_manifest_index": record.get("source_route_manifest_index", index),
        "accepted_route": route,
        "selected_route": route,
        "original_route": original_route,
        "route_changed": route_changed,
        "route_change_authorized": bool(record.get("route_change_authorized")),
        "route_change_source": record.get("route_change_source"),
        "route_dispatch_handoff": contract["handoff_name"],
        "processor_family": contract["processor_family"],
        "primary_processor_contract": contract["primary_processor_contract"],
        "dispatch_status": contract["dispatch_status"],
        "route_outputs_expected": contract["route_outputs"],
        "safety_note": contract["safety_note"],
        "source_accepted_route_manifest_path": str(accepted_manifest_path),
        "fishnet_route_confidence": record.get("fishnet_route_confidence"),
        "review_priority": record.get("review_priority"),
        "handoff_reason": (
            "accepted_fishnet_route_change" if route_changed else "accepted_manifest_route"
        ),
        "processor_execution_allowed": False,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "unsafe": route not in SUPPORTED_ROUTES,
        "safety_contract": _safety_contract(route=route, route_changed=route_changed),
    }


def build_route_dispatch_handoff(
    *,
    accepted_route_manifest_path: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    accepted_payload = _read_json(accepted_route_manifest_path)
    source_quality = accepted_payload.get("quality_status")
    source_summary = accepted_payload.get("summary") or {}
    source_records = _flatten_records(accepted_payload)

    handoff_records = [
        _handoff_record(record=record, index=index, accepted_manifest_path=accepted_route_manifest_path)
        for index, record in enumerate(source_records)
    ]

    by_route: Dict[str, List[Dict[str, Any]]] = {route: [] for route in SUPPORTED_ROUTES}
    unknown_records: List[Dict[str, Any]] = []
    for record in handoff_records:
        route = record["accepted_route"]
        if route in by_route:
            by_route[route].append(record)
        else:
            unknown_records.append(record)

    route_counts = Counter(record["accepted_route"] for record in handoff_records)
    changed_route_counts = Counter(
        record["accepted_route"] for record in handoff_records if record.get("route_changed")
    )
    route_change_pair_counts = Counter(
        f"{record.get('original_route')}->{record.get('accepted_route')}"
        for record in handoff_records
        if record.get("route_changed")
    )

    summary = {
        "source_accepted_route_manifest_quality_status": source_quality,
        "source_accepted_route_manifest_page_count": source_summary.get("accepted_route_manifest_page_count"),
        "dispatch_record_count": len(handoff_records),
        "route_handoff_counts": dict(sorted(route_counts.items())),
        "normal_text_handoff_count": route_counts.get("normal_text", 0),
        "blank_candidate_handoff_count": route_counts.get("blank_candidate", 0),
        "table_handoff_count": route_counts.get("table", 0),
        "image_visual_handoff_count": route_counts.get("image_visual", 0),
        "unknown_route_handoff_count": len(unknown_records),
        "changed_route_handoff_count": sum(1 for record in handoff_records if record.get("route_changed")),
        "changed_route_target_counts": dict(sorted(changed_route_counts.items())),
        "changed_route_pair_counts": dict(sorted(route_change_pair_counts.items())),
        "route_change_authorized_count": sum(1 for record in handoff_records if record.get("route_change_authorized")),
        "processor_execution_allowed_count": sum(1 for record in handoff_records if record.get("processor_execution_allowed")),
        "unsafe_record_count": sum(1 for record in handoff_records if record.get("unsafe")),
        "answer_permission_count": sum(1 for record in handoff_records if record.get("answer_permission")),
        "can_answer_directly_count": sum(1 for record in handoff_records if record.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for record in handoff_records if record.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for record in handoff_records if record.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for record in handoff_records if record.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for record in handoff_records if record.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for record in handoff_records if record.get("opensearch_write_attempt")),
    }

    quality_status = "PASS"
    if source_quality != "PASS":
        quality_status = "FAIL"
    if len(handoff_records) == 0:
        quality_status = "FAIL"
    if summary["unknown_route_handoff_count"] != 0:
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"
    if source_summary.get("accepted_route_manifest_page_count") is not None:
        if source_summary.get("accepted_route_manifest_page_count") != len(handoff_records):
            quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "FISHNET_ROUTE_DISPATCH_HANDOFF_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_accepted_route_manifest_path": str(accepted_route_manifest_path),
        "route_processor_contracts": ROUTE_PROCESSOR_CONTRACTS,
        "records": handoff_records,
        "route_handoffs": {route: records for route, records in by_route.items()},
        "unknown_route_records": unknown_records,
        "safety_contract": {
            "artifact_authority": "route_dispatch_handoff_only",
            "processor_execution_allowed": False,
            "route_handoff_allowed": True,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / "trace_net_fishnet_route_dispatch_handoff_v1_records.jsonl", handoff_records)
    _write_json(output_dir / "trace_net_fishnet_route_dispatch_handoff_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_fishnet_route_dispatch_handoff_v1_quality.json", {"quality_status": quality_status, "summary": summary})

    for route, records in by_route.items():
        route_dir = output_dir / route
        route_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            route_dir / f"trace_net_fishnet_route_dispatch_handoff_v1_{route}.json",
            {
                "module": MODULE_VERSION,
                "route": route,
                "quality_status": "PASS",
                "processor_contract": ROUTE_PROCESSOR_CONTRACTS[route],
                "record_count": len(records),
                "records": records,
            },
        )
        _write_jsonl(
            route_dir / f"trace_net_fishnet_route_dispatch_handoff_v1_{route}.jsonl",
            records,
        )

    if unknown_records:
        unknown_dir = output_dir / "unknown_route"
        unknown_dir.mkdir(parents=True, exist_ok=True)
        _write_json(unknown_dir / "trace_net_fishnet_route_dispatch_handoff_v1_unknown_route.json", {"records": unknown_records})
        _write_jsonl(unknown_dir / "trace_net_fishnet_route_dispatch_handoff_v1_unknown_route.jsonl", unknown_records)

    _write_markdown(output_dir / "trace_net_fishnet_route_dispatch_handoff_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    contracts = payload.get("route_processor_contracts") or {}
    lines = [
        "# TRACE-Net Fishnet Route Dispatch Handoff v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Dispatch records: {summary.get('dispatch_record_count')}",
        f"- Normal text: {summary.get('normal_text_handoff_count')}",
        f"- Blank candidates: {summary.get('blank_candidate_handoff_count')}",
        f"- Tables: {summary.get('table_handoff_count')}",
        f"- Image/visual: {summary.get('image_visual_handoff_count')}",
        f"- Changed route handoffs: {summary.get('changed_route_handoff_count')}",
        f"- Processor execution allowed: {summary.get('processor_execution_allowed_count')}",
        "",
        "## Route handoffs",
        "",
    ]
    for route in SUPPORTED_ROUTES:
        contract = contracts.get(route) or {}
        lines.extend(
            [
                f"### {route}",
                "",
                f"- Count: `{summary.get(route + '_handoff_count')}`",
                f"- Processor family: `{contract.get('processor_family')}`",
                f"- Primary contract: `{contract.get('primary_processor_contract')}`",
                f"- Dispatch status: `{contract.get('dispatch_status')}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def check_route_dispatch_handoff_quality(
    *,
    report_path: Path,
    require_source_accepted_manifest_quality_pass: bool = False,
    require_page_count: Optional[int] = None,
    min_normal_text_handoffs: int = 0,
    min_blank_candidate_handoffs: int = 0,
    min_table_handoffs: int = 0,
    min_image_visual_handoffs: int = 0,
    min_changed_route_handoffs: int = 0,
    max_unknown_routes: int = 0,
    max_unsafe: int = 0,
    max_processor_execution_allowed: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def fail_if(condition: bool, msg: str) -> None:
        if condition:
            failures.append(msg)

    if require_source_accepted_manifest_quality_pass:
        fail_if(summary.get("source_accepted_route_manifest_quality_status") != "PASS", "source accepted manifest quality is not PASS")
    if require_page_count is not None:
        fail_if(summary.get("dispatch_record_count") != require_page_count, "dispatch record count mismatch")
    fail_if(summary.get("normal_text_handoff_count", 0) < min_normal_text_handoffs, "not enough normal_text handoffs")
    fail_if(summary.get("blank_candidate_handoff_count", 0) < min_blank_candidate_handoffs, "not enough blank_candidate handoffs")
    fail_if(summary.get("table_handoff_count", 0) < min_table_handoffs, "not enough table handoffs")
    fail_if(summary.get("image_visual_handoff_count", 0) < min_image_visual_handoffs, "not enough image_visual handoffs")
    fail_if(summary.get("changed_route_handoff_count", 0) < min_changed_route_handoffs, "not enough changed route handoffs")
    fail_if(summary.get("unknown_route_handoff_count", 0) > max_unknown_routes, "too many unknown route handoffs")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    fail_if(summary.get("processor_execution_allowed_count", 0) > max_processor_execution_allowed, "processor execution allowed count exceeded")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")

    quality_status = "FAIL" if failures else "PASS"
    return {
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net fishnet route dispatch handoff v1.")
    parser.add_argument("--accepted-route-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_route_dispatch_handoff(
        accepted_route_manifest_path=Path(args.accepted_route_manifest),
        output_dir=Path(args.output_dir),
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net fishnet route dispatch handoff v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-accepted-manifest-quality-pass", action="store_true")
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-normal-text-handoffs", type=int, default=0)
    parser.add_argument("--min-blank-candidate-handoffs", type=int, default=0)
    parser.add_argument("--min-table-handoffs", type=int, default=0)
    parser.add_argument("--min-image-visual-handoffs", type=int, default=0)
    parser.add_argument("--min-changed-route-handoffs", type=int, default=0)
    parser.add_argument("--max-unknown-routes", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-processor-execution-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_route_dispatch_handoff_quality(
        report_path=Path(args.report_path),
        require_source_accepted_manifest_quality_pass=args.require_source_accepted_manifest_quality_pass,
        require_page_count=args.require_page_count,
        min_normal_text_handoffs=args.min_normal_text_handoffs,
        min_blank_candidate_handoffs=args.min_blank_candidate_handoffs,
        min_table_handoffs=args.min_table_handoffs,
        min_image_visual_handoffs=args.min_image_visual_handoffs,
        min_changed_route_handoffs=args.min_changed_route_handoffs,
        max_unknown_routes=args.max_unknown_routes,
        max_unsafe=args.max_unsafe,
        max_processor_execution_allowed=args.max_processor_execution_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_fishnet_route_dispatch_handoff_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
