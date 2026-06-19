"""TRACE-Net Route Enforcement Mission Gate v1.

Final read-only gate for the page routing system.

It proves:
- pages were classified,
- route dispatch contract exists,
- downstream processors obey that contract,
- no unsafe/direct-answer/source-truth mutation permissions leaked.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "trace_net_route_enforcement_mission_gate_v1"
STATUS_READY = "TRACE_NET_ROUTE_ENFORCEMENT_READY"
STATUS_NOT_READY = "TRACE_NET_ROUTE_ENFORCEMENT_NOT_READY"

DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/route_enforcement_mission_gate")
DEFAULT_REPORT_FILE = "trace_net_route_enforcement_mission_gate_v1.json"
DEFAULT_QUALITY_FILE = "trace_net_route_enforcement_mission_gate_v1_quality.json"


@dataclass(frozen=True)
class MissionGateThresholds:
    min_required_artifacts: int = 7
    max_failed_required_artifacts: int = 0
    max_route_contract_violation_cards: int = 0
    max_blocked_dispatch_leak_count: int = 0
    max_direct_answer_leak_count: int = 0
    max_source_truth_mutation_leak_count: int = 0
    max_unsafe_audit_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_no_answer_permission: bool = True


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return dict(payload) if isinstance(payload, Mapping) else {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def quality_status(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    quality = payload.get("quality") if isinstance(payload.get("quality"), Mapping) else {}
    return str(
        payload.get("quality_status")
        or quality.get("status")
        or quality.get("quality_status")
        or summary.get("quality_status")
        or summary.get("status")
        or payload.get("status")
        or "UNKNOWN"
    )


def artifact_card(name: str, path: Path, *, required: bool = True) -> dict[str, Any]:
    exists = path.exists()
    payload = read_json(path) if exists else {}
    q_status = quality_status(payload) if exists else "MISSING"
    passed = exists and q_status == "PASS"
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_name": name,
        "artifact_path": str(path),
        "required": bool(required),
        "exists": exists,
        "quality_status": q_status,
        "passed": passed if required else True,
        "summary": {
            key: summary.get(key)
            for key in [
                "page_route_card_count",
                "route_dispatch_card_count",
                "processor_contract_card_count",
                "dispatch_coverage_card_count",
                "audited_processor_count",
                "audited_record_count",
                "route_contract_violation_card_count",
                "blocked_dispatch_leak_count",
                "direct_answer_leak_count",
                "source_truth_mutation_leak_count",
                "unsafe_audit_card_count",
                "answer_permission_count",
                "source_truth_mutation_allowed_count",
            ]
            if key in summary
        },
    }


def build_quality(summary: Mapping[str, Any], thresholds: MissionGateThresholds) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, actual: Any, op: str, expected: Any, passed: bool) -> None:
        checks.append({"name": name, "actual": actual, "op": op, "expected": expected, "passed": bool(passed)})

    check("required_artifact_count", summary.get("required_artifact_count"), ">=", thresholds.min_required_artifacts, safe_int(summary.get("required_artifact_count")) >= thresholds.min_required_artifacts)
    check("failed_required_artifact_count", summary.get("failed_required_artifact_count"), "<=", thresholds.max_failed_required_artifacts, safe_int(summary.get("failed_required_artifact_count")) <= thresholds.max_failed_required_artifacts)
    check("route_contract_violation_card_count", summary.get("route_contract_violation_card_count"), "<=", thresholds.max_route_contract_violation_cards, safe_int(summary.get("route_contract_violation_card_count")) <= thresholds.max_route_contract_violation_cards)
    check("blocked_dispatch_leak_count", summary.get("blocked_dispatch_leak_count"), "<=", thresholds.max_blocked_dispatch_leak_count, safe_int(summary.get("blocked_dispatch_leak_count")) <= thresholds.max_blocked_dispatch_leak_count)
    check("direct_answer_leak_count", summary.get("direct_answer_leak_count"), "<=", thresholds.max_direct_answer_leak_count, safe_int(summary.get("direct_answer_leak_count")) <= thresholds.max_direct_answer_leak_count)
    check("source_truth_mutation_leak_count", summary.get("source_truth_mutation_leak_count"), "<=", thresholds.max_source_truth_mutation_leak_count, safe_int(summary.get("source_truth_mutation_leak_count")) <= thresholds.max_source_truth_mutation_leak_count)
    check("unsafe_audit_card_count", summary.get("unsafe_audit_card_count"), "<=", thresholds.max_unsafe_audit_cards, safe_int(summary.get("unsafe_audit_card_count")) <= thresholds.max_unsafe_audit_cards)
    check("answer_permission_count", summary.get("answer_permission_count"), "<=", thresholds.max_answer_permission_count, safe_int(summary.get("answer_permission_count")) <= thresholds.max_answer_permission_count)
    check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count"), "<=", thresholds.max_source_truth_mutation_allowed, safe_int(summary.get("source_truth_mutation_allowed_count")) <= thresholds.max_source_truth_mutation_allowed)

    if thresholds.require_no_answer_permission:
        check("no_answer_permission", summary.get("answer_permission_count"), "==", 0, safe_int(summary.get("answer_permission_count")) == 0)
        check("no_direct_answer_leak", summary.get("direct_answer_leak_count"), "==", 0, safe_int(summary.get("direct_answer_leak_count")) == 0)
        check("no_source_truth_mutation", summary.get("source_truth_mutation_leak_count"), "==", 0, safe_int(summary.get("source_truth_mutation_leak_count")) == 0)

    status = "PASS" if all(item["passed"] for item in checks) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "quality_status": status,
        "checks": checks,
        "summary": dict(summary),
    }


def build_route_enforcement_mission_gate_report(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    artifact_detector: Path = Path("local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json"),
    page_ink_route_evidence: Path = Path("local_data/organization/trace_net/page_ink_route_evidence/trace_net_page_ink_route_evidence_v1.json"),
    page_route_manifest: Path = Path("local_data/organization/trace_net/page_route_manifest/trace_net_page_route_manifest_v1.json"),
    route_dispatch_manifest: Path = Path("local_data/organization/trace_net/route_dispatch_manifest/trace_net_route_dispatch_manifest_v1.json"),
    route_dispatch_processor_contract: Path = Path("local_data/organization/trace_net/route_dispatch_processor_contract/trace_net_route_dispatch_processor_contract_v1.json"),
    route_dispatch_coverage_audit: Path = Path("local_data/organization/trace_net/route_dispatch_coverage_audit/trace_net_route_dispatch_coverage_audit_v1.json"),
    route_contract_integration_audit: Path = Path("local_data/organization/trace_net/route_contract_integration_audit/trace_net_route_contract_integration_audit_v1.json"),
    thresholds: MissionGateThresholds | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    thresholds = thresholds or MissionGateThresholds()

    artifact_cards = [
        artifact_card("artifact_detector", artifact_detector),
        artifact_card("page_ink_route_evidence", page_ink_route_evidence),
        artifact_card("page_route_manifest", page_route_manifest),
        artifact_card("route_dispatch_manifest", route_dispatch_manifest),
        artifact_card("route_dispatch_processor_contract", route_dispatch_processor_contract),
        artifact_card("route_dispatch_coverage_audit", route_dispatch_coverage_audit),
        artifact_card("route_contract_integration_audit", route_contract_integration_audit),
    ]

    integration_payload = read_json(route_contract_integration_audit) if route_contract_integration_audit.exists() else {}
    integration_summary = integration_payload.get("summary") if isinstance(integration_payload.get("summary"), Mapping) else {}

    required_cards = [card for card in artifact_cards if card.get("required")]
    failed_required = [card for card in required_cards if not card.get("passed")]

    summary = {
        "schema_version": SCHEMA_VERSION,
        "required_artifact_count": len(required_cards),
        "failed_required_artifact_count": len(failed_required),
        "passed_required_artifact_count": len(required_cards) - len(failed_required),
        "route_contract_violation_card_count": safe_int(integration_summary.get("route_contract_violation_card_count")),
        "blocked_dispatch_leak_count": safe_int(integration_summary.get("blocked_dispatch_leak_count")),
        "direct_answer_leak_count": safe_int(integration_summary.get("direct_answer_leak_count")),
        "source_truth_mutation_leak_count": safe_int(integration_summary.get("source_truth_mutation_leak_count")),
        "unsafe_audit_card_count": safe_int(integration_summary.get("unsafe_audit_card_count")),
        "answer_permission_count": safe_int(integration_summary.get("answer_permission_count")),
        "can_answer_directly_count": safe_int(integration_summary.get("can_answer_directly_count")),
        "can_prove_claims_count": safe_int(integration_summary.get("can_prove_claims_count")),
        "source_truth_mutation_allowed_count": safe_int(integration_summary.get("source_truth_mutation_allowed_count")),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "failed_required_artifacts": [card["artifact_name"] for card in failed_required],
    }

    quality = build_quality(summary, thresholds)
    summary["quality_status"] = quality["status"]

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": STATUS_READY if quality["status"] == "PASS" else STATUS_NOT_READY,
        "quality_status": quality["status"],
        "summary": summary,
        "route_artifact_cards": artifact_cards,
        "quality": quality,
    }

    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / DEFAULT_REPORT_FILE
        quality_path = output_dir / DEFAULT_QUALITY_FILE
        write_json(report_path, report)
        write_json(quality_path, quality)
        report["report_path"] = str(report_path)
        report["quality_path"] = str(quality_path)

    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net route enforcement mission gate v1")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--artifact-detector", type=Path, default=Path("local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json"))
    parser.add_argument("--page-ink-route-evidence", type=Path, default=Path("local_data/organization/trace_net/page_ink_route_evidence/trace_net_page_ink_route_evidence_v1.json"))
    parser.add_argument("--page-route-manifest", type=Path, default=Path("local_data/organization/trace_net/page_route_manifest/trace_net_page_route_manifest_v1.json"))
    parser.add_argument("--route-dispatch-manifest", type=Path, default=Path("local_data/organization/trace_net/route_dispatch_manifest/trace_net_route_dispatch_manifest_v1.json"))
    parser.add_argument("--route-dispatch-processor-contract", type=Path, default=Path("local_data/organization/trace_net/route_dispatch_processor_contract/trace_net_route_dispatch_processor_contract_v1.json"))
    parser.add_argument("--route-dispatch-coverage-audit", type=Path, default=Path("local_data/organization/trace_net/route_dispatch_coverage_audit/trace_net_route_dispatch_coverage_audit_v1.json"))
    parser.add_argument("--route-contract-integration-audit", type=Path, default=Path("local_data/organization/trace_net/route_contract_integration_audit/trace_net_route_contract_integration_audit_v1.json"))
    parser.add_argument("--min-required-artifacts", type=int, default=7)
    parser.add_argument("--max-failed-required-artifacts", type=int, default=0)
    parser.add_argument("--max-route-contract-violation-cards", type=int, default=0)
    parser.add_argument("--max-blocked-dispatch-leak-count", type=int, default=0)
    parser.add_argument("--max-direct-answer-leak-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-leak-count", type=int, default=0)
    parser.add_argument("--max-unsafe-audit-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    thresholds = MissionGateThresholds(
        min_required_artifacts=args.min_required_artifacts,
        max_failed_required_artifacts=args.max_failed_required_artifacts,
        max_route_contract_violation_cards=args.max_route_contract_violation_cards,
        max_blocked_dispatch_leak_count=args.max_blocked_dispatch_leak_count,
        max_direct_answer_leak_count=args.max_direct_answer_leak_count,
        max_source_truth_mutation_leak_count=args.max_source_truth_mutation_leak_count,
        max_unsafe_audit_cards=args.max_unsafe_audit_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = build_route_enforcement_mission_gate_report(
        output_dir=args.output_dir,
        artifact_detector=args.artifact_detector,
        page_ink_route_evidence=args.page_ink_route_evidence,
        page_route_manifest=args.page_route_manifest,
        route_dispatch_manifest=args.route_dispatch_manifest,
        route_dispatch_processor_contract=args.route_dispatch_processor_contract,
        route_dispatch_coverage_audit=args.route_dispatch_coverage_audit,
        route_contract_integration_audit=args.route_contract_integration_audit,
        thresholds=thresholds,
    )
    summary = report["summary"]
    print("TRACE-Net Route Enforcement Mission Gate v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "required_artifact_count",
        "passed_required_artifact_count",
        "failed_required_artifact_count",
        "route_contract_violation_card_count",
        "blocked_dispatch_leak_count",
        "direct_answer_leak_count",
        "source_truth_mutation_leak_count",
        "unsafe_audit_card_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
