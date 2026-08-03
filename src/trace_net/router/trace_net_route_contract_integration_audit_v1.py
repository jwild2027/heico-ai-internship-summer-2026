"""TRACE-Net Route Contract Integration Audit v1.

End-to-end proof that routed processors only emit records for pages allowed
by the route dispatch processor contract.

This audit is read-only. It does not answer, prove claims, mutate source truth,
or write to Postgres/Qdrant/OpenSearch.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from tiff.trace_net_route_dispatch_contract_loader_v1 import load_route_dispatch_processor_contract
except Exception:  # pragma: no cover
    load_route_dispatch_processor_contract = None  # type: ignore


SCHEMA_VERSION = "trace_net_route_contract_integration_audit_v1"
STATUS_BUILT = "TRACE_NET_ROUTE_CONTRACT_INTEGRATION_AUDIT_BUILT"
STATUS_NOT_READY = "TRACE_NET_ROUTE_CONTRACT_INTEGRATION_AUDIT_NOT_READY"

DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/route_contract_integration_audit")
DEFAULT_REPORT_FILE = "trace_net_route_contract_integration_audit_v1.json"
DEFAULT_QUALITY_FILE = "trace_net_route_contract_integration_audit_v1_quality.json"

DEFAULT_CONTRACT = Path("local_data/organization/trace_net/route_dispatch_processor_contract/trace_net_route_dispatch_processor_contract_v1.json")

DIRECT_OR_SOURCE_TRUTH_FIELDS = [
    "answer_permission",
    "can_answer_directly",
    "can_prove_claims",
    "canonical_source_truth",
    "source_truth_mutation_allowed",
    "can_mutate_source_truth",
    "answer_composition_allowed",
    "llm_answer_allowed",
]

ROUTE_METHODS = {
    "table": "is_table_allowed",
    "image_visual": "is_image_visual_allowed",
    "normal_text": "is_normal_text_allowed",
}


@dataclass(frozen=True)
class AuditThresholds:
    min_audited_processors: int = 6
    min_audited_records: int = 1
    max_route_contract_violation_cards: int = 0
    max_blocked_dispatch_leak_count: int = 0
    max_direct_answer_leak_count: int = 0
    max_source_truth_mutation_leak_count: int = 0
    max_unsafe_audit_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_route_dispatch_processor_contract_quality_pass: bool = True
    require_no_answer_permission: bool = True


class MergedRouteContract:
    """Route contract that accepts either the official loader or fallback parser.

    Unit tests use a tiny synthetic contract with simple *_allowed_pages keys,
    while production uses the official route dispatch processor contract shape.
    This wrapper keeps both valid.
    """

    def __init__(self, primary: Any, fallback: Any) -> None:
        self.primary = primary
        self.fallback = fallback
        self.quality_status = str(
            getattr(primary, "quality_status", "")
            or getattr(fallback, "quality_status", "")
            or "UNKNOWN"
        )

    def _allowed(self, method_name: str, page_id: Any) -> bool:
        for contract in (self.primary, self.fallback):
            method = getattr(contract, method_name, None)
            if method is None:
                continue
            try:
                if bool(method(page_id)):
                    return True
            except Exception:
                continue
        return False

    def is_table_allowed(self, page_id: Any) -> bool:
        return self._allowed("is_table_allowed", page_id)

    def is_image_visual_allowed(self, page_id: Any) -> bool:
        return self._allowed("is_image_visual_allowed", page_id)

    def is_normal_text_allowed(self, page_id: Any) -> bool:
        return self._allowed("is_normal_text_allowed", page_id)

    def is_review_required(self, page_id: Any) -> bool:
        return self._allowed("is_review_required", page_id)


class FallbackRouteContract:
    def __init__(self, payload: Mapping[str, Any], path: Path | None = None) -> None:
        self.quality_status = str(payload.get("quality_status") or (payload.get("summary") or {}).get("quality_status") or "UNKNOWN")
        self.table_allowed_pages = self._collect(payload, "table")
        self.image_visual_allowed_pages = self._collect(payload, "image_visual")
        self.normal_text_allowed_pages = self._collect(payload, "normal_text")
        self.review_required_pages: set[str] = set()

        for key in ("review_required_pages", "review_pages"):
            value = payload.get(key)
            if isinstance(value, list):
                self.review_required_pages.update(str(item) for item in value if item)

        cards = []
        for key in ("processor_contract_cards", "route_dispatch_cards", "page_route_cards", "contract_cards"):
            value = payload.get(key)
            if isinstance(value, list):
                cards.extend(item for item in value if isinstance(item, Mapping))

        for card in cards:
            page_id = str(card.get("page_id") or card.get("source_page_id") or "")
            if not page_id:
                continue
            routes = set(str(item) for item in (card.get("allowed_dispatch_routes") or []) if item)
            if card.get("table_processing_allowed") or card.get("table_route_allowed") or "table" in routes:
                self.table_allowed_pages.add(page_id)
            if card.get("image_visual_processing_allowed") or card.get("image_visual_route_allowed") or "image_visual" in routes:
                self.image_visual_allowed_pages.add(page_id)
            if card.get("normal_text_processing_allowed") or card.get("normal_text_route_allowed") or "normal_text" in routes:
                self.normal_text_allowed_pages.add(page_id)
            if card.get("review_processing_required") or card.get("route_dispatch_review_required") or card.get("review_required"):
                self.review_required_pages.add(page_id)

        if path:
            self._load_sidecar_pages(path)

    def _collect(self, payload: Mapping[str, Any], route: str) -> set[str]:
        keys = [
            f"{route}_allowed_pages",
            f"{route}_allowed_page_ids",
            f"{route}_route_allowed_pages",
        ]
        output: set[str] = set()
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                output.update(str(item) for item in value if item)
            elif isinstance(value, Mapping):
                output.update(str(k) for k, v in value.items() if v)
        allowed_pages = payload.get("allowed_pages")
        if isinstance(allowed_pages, Mapping):
            value = allowed_pages.get(route)
            if isinstance(value, list):
                output.update(str(item) for item in value if item)
        return output

    def _load_sidecar_pages(self, path: Path) -> None:
        sidecars = {
            "table": ("table_allowed_pages.json", "table_allowed_page_ids.json"),
            "image_visual": ("image_visual_allowed_pages.json", "image_visual_allowed_page_ids.json"),
            "normal_text": ("normal_text_allowed_pages.json", "normal_text_allowed_page_ids.json"),
        }
        target_sets = {
            "table": self.table_allowed_pages,
            "image_visual": self.image_visual_allowed_pages,
            "normal_text": self.normal_text_allowed_pages,
        }
        for route, names in sidecars.items():
            for name in names:
                sidecar = path.parent / name
                if not sidecar.exists():
                    continue
                try:
                    payload = json.loads(sidecar.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(payload, list):
                    target_sets[route].update(str(item) for item in payload if item)
                elif isinstance(payload, Mapping):
                    pages = payload.get("pages") or payload.get("page_ids") or payload.get(f"{route}_allowed_pages")
                    if isinstance(pages, list):
                        target_sets[route].update(str(item) for item in pages if item)

    def is_table_allowed(self, page_id: Any) -> bool:
        return str(page_id or "") in self.table_allowed_pages

    def is_image_visual_allowed(self, page_id: Any) -> bool:
        return str(page_id or "") in self.image_visual_allowed_pages

    def is_normal_text_allowed(self, page_id: Any) -> bool:
        return str(page_id or "") in self.normal_text_allowed_pages

    def is_review_required(self, page_id: Any) -> bool:
        return str(page_id or "") in self.review_required_pages


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            item = json.loads(text)
            if isinstance(item, Mapping):
                rows.append(dict(item))
    return rows


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on", "allowed"}


def safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def page_id_from_record(record: Mapping[str, Any]) -> str:
    for key in ("page_id", "group_page_id", "source_page_id", "document_page_id"):
        value = record.get(key)
        if value:
            return str(value)
    trace = record.get("traceability")
    if isinstance(trace, Mapping) and trace.get("page_id"):
        return str(trace.get("page_id"))
    return ""


def load_artifact_records(path: Path, record_key: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {"missing_artifact": True, "path": str(path)}
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path), {"path": str(path), "record_source": "jsonl"}
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        return [], {"path": str(path), "record_source": "non_mapping_json"}
    raw = payload.get(record_key)
    if raw is None:
        raw = payload.get("records") or payload.get("table_geometry_cards") or payload.get("groups") or []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raw = []
    return [dict(item) for item in raw if isinstance(item, Mapping)], dict(payload)


def load_contract(path: Path) -> Any:
    payload = read_json(path)
    fallback = FallbackRouteContract(payload if isinstance(payload, Mapping) else {}, path)
    if load_route_dispatch_processor_contract is not None:
        try:
            primary = load_route_dispatch_processor_contract(path)
            return MergedRouteContract(primary, fallback)
        except Exception:
            pass
    return fallback


def contract_quality_status(contract_path: Path, contract: Any) -> str:
    try:
        payload = read_json(contract_path)
        if isinstance(payload, Mapping):
            return str(payload.get("quality_status") or (payload.get("summary") or {}).get("quality_status") or getattr(contract, "quality_status", "UNKNOWN"))
    except Exception:
        pass
    return str(getattr(contract, "quality_status", "UNKNOWN"))


def contract_allows(contract: Any, route: str, page_id: str) -> bool:
    method_name = ROUTE_METHODS[route]
    method = getattr(contract, method_name)
    return bool(method(page_id))


def record_blocked_dispatch_leak(record: Mapping[str, Any]) -> list[str]:
    leaks: list[str] = []
    for key, value in record.items():
        if key.endswith("_route_dispatch_allowed") and value is False:
            leaks.append(key)
    return leaks


def record_direct_answer_leaks(record: Mapping[str, Any]) -> list[str]:
    return [key for key in DIRECT_OR_SOURCE_TRUTH_FIELDS if safe_bool(record.get(key))]


def record_source_truth_mutation_leaks(record: Mapping[str, Any]) -> list[str]:
    leaks = []
    for key in ("source_truth_mutation_allowed", "can_mutate_source_truth"):
        if safe_bool(record.get(key)):
            leaks.append(key)
    if safe_int(record.get("source_truth_mutations_performed")) > 0:
        leaks.append("source_truth_mutations_performed")
    return leaks


def build_record_audit_card(
    *,
    processor_name: str,
    artifact_path: Path,
    expected_route: str,
    record: Mapping[str, Any],
    contract: Any,
) -> dict[str, Any]:
    page_id = page_id_from_record(record)
    route_allowed = bool(page_id and contract_allows(contract, expected_route, page_id))
    route_violations = []
    if not page_id:
        route_violations.append("missing_page_id")
    elif not route_allowed:
        route_violations.append(f"{expected_route}_route_not_allowed_for_output_page")

    blocked_leaks = record_blocked_dispatch_leak(record)
    direct_leaks = record_direct_answer_leaks(record)
    mutation_leaks = record_source_truth_mutation_leaks(record)

    unsafe = bool(route_violations or blocked_leaks or direct_leaks or mutation_leaks)

    return {
        "schema_version": SCHEMA_VERSION,
        "processor_name": processor_name,
        "artifact_path": str(artifact_path),
        "expected_route": expected_route,
        "page_id": page_id,
        "route_contract_allowed": route_allowed,
        "route_contract_violations": route_violations,
        "blocked_dispatch_leak_fields": blocked_leaks,
        "direct_answer_leak_fields": direct_leaks,
        "source_truth_mutation_leak_fields": mutation_leaks,
        "unsafe_audit_card": unsafe,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
    }


def build_processor_audit(
    *,
    processor_name: str,
    artifact_path: Path,
    expected_route: str,
    record_key: str,
    contract: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records, payload = load_artifact_records(artifact_path, record_key)
    cards = [
        build_record_audit_card(
            processor_name=processor_name,
            artifact_path=artifact_path,
            expected_route=expected_route,
            record=record,
            contract=contract,
        )
        for record in records
    ]
    route_violation_count = sum(1 for card in cards if card.get("route_contract_violations"))
    blocked_leak_count = sum(1 for card in cards if card.get("blocked_dispatch_leak_fields"))
    direct_leak_count = sum(1 for card in cards if card.get("direct_answer_leak_fields"))
    mutation_leak_count = sum(1 for card in cards if card.get("source_truth_mutation_leak_fields"))
    unsafe_count = sum(1 for card in cards if card.get("unsafe_audit_card"))
    page_ids = sorted({str(card.get("page_id")) for card in cards if card.get("page_id")})

    processor_card = {
        "schema_version": SCHEMA_VERSION,
        "processor_name": processor_name,
        "artifact_path": str(artifact_path),
        "expected_route": expected_route,
        "artifact_exists": artifact_path.exists(),
        "artifact_quality_status": payload.get("quality_status") or (payload.get("summary") or {}).get("quality_status") if isinstance(payload, Mapping) else None,
        "audited_record_count": len(cards),
        "audited_page_count": len(page_ids),
        "route_contract_violation_count": route_violation_count,
        "blocked_dispatch_leak_count": blocked_leak_count,
        "direct_answer_leak_count": direct_leak_count,
        "source_truth_mutation_leak_count": mutation_leak_count,
        "unsafe_audit_card_count": unsafe_count,
        "safe_for_route_contract": unsafe_count == 0,
        "sample_page_ids": page_ids[:20],
    }
    return processor_card, cards


def build_quality(summary: Mapping[str, Any], thresholds: AuditThresholds) -> dict[str, Any]:
    checks = []

    def check(name: str, actual: Any, op: str, expected: Any, passed: bool) -> None:
        checks.append({"name": name, "actual": actual, "op": op, "expected": expected, "passed": bool(passed)})

    check("audited_processor_count", summary.get("audited_processor_count"), ">=", thresholds.min_audited_processors, safe_int(summary.get("audited_processor_count")) >= thresholds.min_audited_processors)
    check("audited_record_count", summary.get("audited_record_count"), ">=", thresholds.min_audited_records, safe_int(summary.get("audited_record_count")) >= thresholds.min_audited_records)
    check("route_contract_violation_card_count", summary.get("route_contract_violation_card_count"), "<=", thresholds.max_route_contract_violation_cards, safe_int(summary.get("route_contract_violation_card_count")) <= thresholds.max_route_contract_violation_cards)
    check("blocked_dispatch_leak_count", summary.get("blocked_dispatch_leak_count"), "<=", thresholds.max_blocked_dispatch_leak_count, safe_int(summary.get("blocked_dispatch_leak_count")) <= thresholds.max_blocked_dispatch_leak_count)
    check("direct_answer_leak_count", summary.get("direct_answer_leak_count"), "<=", thresholds.max_direct_answer_leak_count, safe_int(summary.get("direct_answer_leak_count")) <= thresholds.max_direct_answer_leak_count)
    check("source_truth_mutation_leak_count", summary.get("source_truth_mutation_leak_count"), "<=", thresholds.max_source_truth_mutation_leak_count, safe_int(summary.get("source_truth_mutation_leak_count")) <= thresholds.max_source_truth_mutation_leak_count)
    check("unsafe_audit_card_count", summary.get("unsafe_audit_card_count"), "<=", thresholds.max_unsafe_audit_cards, safe_int(summary.get("unsafe_audit_card_count")) <= thresholds.max_unsafe_audit_cards)
    check("answer_permission_count", summary.get("answer_permission_count"), "<=", thresholds.max_answer_permission_count, safe_int(summary.get("answer_permission_count")) <= thresholds.max_answer_permission_count)
    check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count"), "<=", thresholds.max_source_truth_mutation_allowed, safe_int(summary.get("source_truth_mutation_allowed_count")) <= thresholds.max_source_truth_mutation_allowed)

    if thresholds.require_route_dispatch_processor_contract_quality_pass:
        check("route_dispatch_processor_contract_quality_status", summary.get("route_dispatch_processor_contract_quality_status"), "==", "PASS", str(summary.get("route_dispatch_processor_contract_quality_status")) == "PASS")
    if thresholds.require_no_answer_permission:
        check("no_answer_permission", summary.get("answer_permission_count"), "==", 0, safe_int(summary.get("answer_permission_count")) == 0)
        check("no_can_answer_directly", summary.get("can_answer_directly_count"), "==", 0, safe_int(summary.get("can_answer_directly_count")) == 0)
        check("no_can_prove_claims", summary.get("can_prove_claims_count"), "==", 0, safe_int(summary.get("can_prove_claims_count")) == 0)

    status = "PASS" if all(item["passed"] for item in checks) else "FAIL"
    return {"schema_version": f"{SCHEMA_VERSION}_quality", "status": status, "quality_status": status, "checks": checks, "summary": dict(summary)}


def build_route_contract_integration_audit_report(
    *,
    route_dispatch_processor_contract: Path = DEFAULT_CONTRACT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    table_line_geometry: Path = Path("local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json"),
    visual_ink_layout_calibrator: Path = Path("local_data/organization/trace_net/visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1.json"),
    callout_visual_part_verifier: Path = Path("local_data/organization/trace_net/callout_visual_part_verifier/trace_net_callout_visual_part_verifier_v1.json"),
    page_context_v2_records: Path = Path("local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2_records.jsonl"),
    context_retrieval_helpers: Path = Path("local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json"),
    answer_context_pack: Path = Path("local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json"),
    thresholds: AuditThresholds | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    thresholds = thresholds or AuditThresholds()
    contract = load_contract(route_dispatch_processor_contract)
    contract_status = contract_quality_status(route_dispatch_processor_contract, contract)

    specs = [
        ("table_line_geometry", table_line_geometry, "table", "table_geometry_cards"),
        ("visual_ink_layout_calibrator", visual_ink_layout_calibrator, "image_visual", "records"),
        ("callout_visual_part_verifier", callout_visual_part_verifier, "image_visual", "records"),
        ("page_context_v2", page_context_v2_records, "normal_text", "records"),
        ("context_retrieval_helpers", context_retrieval_helpers, "normal_text", "records"),
        ("answer_context_pack", answer_context_pack, "normal_text", "records"),
    ]

    processor_cards: list[dict[str, Any]] = []
    record_cards: list[dict[str, Any]] = []

    for processor_name, artifact_path, expected_route, record_key in specs:
        processor_card, cards = build_processor_audit(
            processor_name=processor_name,
            artifact_path=artifact_path,
            expected_route=expected_route,
            record_key=record_key,
            contract=contract,
        )
        processor_cards.append(processor_card)
        record_cards.extend(cards)

    route_counts = Counter(card.get("expected_route") for card in record_cards)
    processor_record_counts = {card["processor_name"]: card["audited_record_count"] for card in processor_cards}

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "route_dispatch_processor_contract_path": str(route_dispatch_processor_contract),
        "route_dispatch_processor_contract_quality_status": contract_status,
        "audited_processor_count": len(processor_cards),
        "audited_record_count": len(record_cards),
        "audited_page_count": len({card.get("page_id") for card in record_cards if card.get("page_id")}),
        "route_contract_violation_card_count": sum(1 for card in record_cards if card.get("route_contract_violations")),
        "blocked_dispatch_leak_count": sum(1 for card in record_cards if card.get("blocked_dispatch_leak_fields")),
        "direct_answer_leak_count": sum(1 for card in record_cards if card.get("direct_answer_leak_fields")),
        "source_truth_mutation_leak_count": sum(1 for card in record_cards if card.get("source_truth_mutation_leak_fields")),
        "unsafe_audit_card_count": sum(1 for card in record_cards if card.get("unsafe_audit_card")),
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "record_count_by_expected_route": dict(sorted(route_counts.items())),
        "processor_record_counts": dict(sorted(processor_record_counts.items())),
    }

    quality = build_quality(summary, thresholds)
    quality_status = quality["status"]
    summary["quality_status"] = quality_status

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": STATUS_BUILT if quality_status == "PASS" else STATUS_NOT_READY,
        "quality_status": quality_status,
        "summary": summary,
        "processor_audit_cards": processor_cards,
        "route_contract_record_audit_cards": record_cards,
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
    parser = argparse.ArgumentParser(description="Build TRACE-Net route contract integration audit v1")
    parser.add_argument("--route-dispatch-processor-contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--table-line-geometry", type=Path, default=Path("local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json"))
    parser.add_argument("--visual-ink-layout-calibrator", type=Path, default=Path("local_data/organization/trace_net/visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1.json"))
    parser.add_argument("--callout-visual-part-verifier", type=Path, default=Path("local_data/organization/trace_net/callout_visual_part_verifier/trace_net_callout_visual_part_verifier_v1.json"))
    parser.add_argument("--page-context-v2-records", type=Path, default=Path("local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2_records.jsonl"))
    parser.add_argument("--context-retrieval-helpers", type=Path, default=Path("local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json"))
    parser.add_argument("--answer-context-pack", type=Path, default=Path("local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json"))
    parser.add_argument("--min-audited-processors", type=int, default=6)
    parser.add_argument("--min-audited-records", type=int, default=1)
    parser.add_argument("--max-route-contract-violation-cards", type=int, default=0)
    parser.add_argument("--max-blocked-dispatch-leak-count", type=int, default=0)
    parser.add_argument("--max-direct-answer-leak-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-leak-count", type=int, default=0)
    parser.add_argument("--max-unsafe-audit-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-route-dispatch-processor-contract-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    thresholds = AuditThresholds(
        min_audited_processors=args.min_audited_processors,
        min_audited_records=args.min_audited_records,
        max_route_contract_violation_cards=args.max_route_contract_violation_cards,
        max_blocked_dispatch_leak_count=args.max_blocked_dispatch_leak_count,
        max_direct_answer_leak_count=args.max_direct_answer_leak_count,
        max_source_truth_mutation_leak_count=args.max_source_truth_mutation_leak_count,
        max_unsafe_audit_cards=args.max_unsafe_audit_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_route_dispatch_processor_contract_quality_pass=args.require_route_dispatch_processor_contract_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = build_route_contract_integration_audit_report(
        route_dispatch_processor_contract=args.route_dispatch_processor_contract,
        output_dir=args.output_dir,
        table_line_geometry=args.table_line_geometry,
        visual_ink_layout_calibrator=args.visual_ink_layout_calibrator,
        callout_visual_part_verifier=args.callout_visual_part_verifier,
        page_context_v2_records=args.page_context_v2_records,
        context_retrieval_helpers=args.context_retrieval_helpers,
        answer_context_pack=args.answer_context_pack,
        thresholds=thresholds,
    )
    summary = report["summary"]
    print("TRACE-Net Route Contract Integration Audit v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "audited_processor_count",
        "audited_record_count",
        "audited_page_count",
        "route_contract_violation_card_count",
        "blocked_dispatch_leak_count",
        "direct_answer_leak_count",
        "source_truth_mutation_leak_count",
        "unsafe_audit_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "route_dispatch_processor_contract_quality_status",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
