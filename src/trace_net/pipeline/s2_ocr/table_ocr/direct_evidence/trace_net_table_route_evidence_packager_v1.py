"""TRACE-Net table-route evidence packager v1.

This module consumes the read-only table-route value-audit artifact and packages
search-ready table values into retrieval/search evidence documents. It does not
upload to Postgres, Qdrant, or OpenSearch, and it does not grant answer authority.

Safety contract:
- input: trace_net_table_route_value_audit_v1.json
- output: local JSON/JSONL/Markdown artifacts only
- table evidence is retrieval/search support only
- can_answer_directly=false, can_prove_claims=false, answer_permission=false
- source_truth_mutation_allowed=false
- no Postgres/Qdrant/OpenSearch writes
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


DEFAULT_AUDIT_REPORT_PATH = Path(
    "local_data/organization/trace_net/table_route_value_audit/"
    "trace_net_table_route_value_audit_v1.json"
)
DEFAULT_OUTPUT_DIR = Path(
    "local_data/organization/trace_net/table_route_evidence_packager"
)
DEFAULT_PACKAGE_REPORT_PATH = DEFAULT_OUTPUT_DIR / "trace_net_table_route_evidence_packager_v1.json"
DEFAULT_EVIDENCE_JSONL_PATH = DEFAULT_OUTPUT_DIR / "trace_net_table_route_evidence_documents_v1.jsonl"
DEFAULT_QUALITY_PATH = DEFAULT_OUTPUT_DIR / "trace_net_table_route_evidence_packager_v1_quality.json"
DEFAULT_INSPECT_MD_PATH = DEFAULT_OUTPUT_DIR / "trace_net_table_route_evidence_packager_v1_inspect.md"


@dataclass(frozen=True)
class EvidencePackagerThresholds:
    min_source_audit_records: int = 20
    min_source_search_ready_records: int = 1000
    min_evidence_documents: int = 1000
    min_pages_with_evidence: int = 1
    min_field_count: int = 4
    min_covered_part_number_documents: int = 100
    min_manual_page_reference_documents: int = 39
    min_ipl_part_number_documents: int = 100
    max_unsafe_records: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_source_audit_quality_pass: bool = True
    require_no_answer_permission: bool = True
    inspect_limit: int = 50

    def as_dict(self) -> dict[str, Any]:
        return {
            "min_source_audit_records": self.min_source_audit_records,
            "min_source_search_ready_records": self.min_source_search_ready_records,
            "min_evidence_documents": self.min_evidence_documents,
            "min_pages_with_evidence": self.min_pages_with_evidence,
            "min_field_count": self.min_field_count,
            "min_covered_part_number_documents": self.min_covered_part_number_documents,
            "min_manual_page_reference_documents": self.min_manual_page_reference_documents,
            "min_ipl_part_number_documents": self.min_ipl_part_number_documents,
            "max_unsafe_records": self.max_unsafe_records,
            "max_answer_permission_count": self.max_answer_permission_count,
            "max_source_truth_mutation_allowed": self.max_source_truth_mutation_allowed,
            "require_source_audit_quality_pass": self.require_source_audit_quality_pass,
            "require_no_answer_permission": self.require_no_answer_permission,
            "inspect_limit": self.inspect_limit,
        }


@dataclass
class QualityCheck:
    name: str
    observed: Any
    expected: str
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "observed": self.observed,
            "expected": self.expected,
            "passed": self.passed,
        }


COUNT_KEYS: dict[str, Sequence[str]] = {
    "source_audit_record_count": (
        "source_audit_record_count",
        "table_route_value_audit_record_count",
        "audit_record_count",
    ),
    "source_search_ready_evidence_record_count": (
        "source_search_ready_evidence_record_count",
        "search_ready_evidence_record_count",
    ),
    "source_promoted_table_value_evidence_record_count": (
        "source_promoted_table_value_evidence_record_count",
        "promoted_table_value_evidence_record_count",
        "promoted_evidence_record_count",
    ),
    "source_unsafe_record_count": (
        "source_unsafe_record_count",
        "unsafe_table_route_value_audit_record_count",
        "unsafe_record_count",
    ),
    "source_answer_permission_count": (
        "source_answer_permission_count",
        "answer_permission_count",
    ),
    "source_can_answer_directly_count": (
        "source_can_answer_directly_count",
        "can_answer_directly_count",
    ),
    "source_can_prove_claims_count": (
        "source_can_prove_claims_count",
        "can_prove_claims_count",
    ),
    "source_truth_mutation_allowed_count": (
        "source_truth_mutation_allowed_count",
    ),
    "source_postgres_write_attempt_count": (
        "source_postgres_write_attempt_count",
        "postgres_write_attempt_count",
    ),
    "source_qdrant_write_attempt_count": (
        "source_qdrant_write_attempt_count",
        "qdrant_write_attempt_count",
    ),
    "source_opensearch_write_attempt_count": (
        "source_opensearch_write_attempt_count",
        "opensearch_write_attempt_count",
    ),
}

FIELD_ALIASES = {
    "covered_part_number": "covered_part_number",
    "manual_page_reference": "manual_page_reference",
    "page_rev_or_sequence_value": "page_rev_or_sequence_value",
    "ipl_part_number": "ipl_part_number",
    "part_number": "ipl_part_number",
    "ipl_figure_item_or_quantity": "ipl_figure_item_or_quantity",
    "fig_item_or_quantity": "ipl_figure_item_or_quantity",
    "figure_item_or_quantity": "ipl_figure_item_or_quantity",
    "ipl_text": "ipl_text",
    "description": "ipl_text",
    "nomenclature": "ipl_text",
}


class EvidencePackagingError(ValueError):
    """Raised when evidence cannot be safely packaged."""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")


def iter_dicts(payload: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        yield payload
        for value in payload.values():
            yield from iter_dicts(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from iter_dicts(item)


def iter_dicts_with_path(payload: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[Mapping[str, Any], tuple[str, ...]]]:
    """Yield dictionaries with their JSON path.

    Some upstream audit artifacts place promoted/search-ready values inside a
    named list, for example ``search_ready_evidence_records`` or
    ``promoted_table_value_evidence_records``. Individual records in those
    lists may not repeat a ``search_ready=True`` flag. Keeping the parent path
    lets the packager safely recognize those values without guessing from the
    summary counters alone.
    """
    if isinstance(payload, Mapping):
        yield payload, path
        for key, value in payload.items():
            yield from iter_dicts_with_path(value, path + (str(key),))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            yield from iter_dicts_with_path(item, path + (str(index),))


def first_scalar_for_keys(payload: Any, keys: Sequence[str]) -> Any | None:
    for mapping in iter_dicts(payload):
        for key in keys:
            if key in mapping and not isinstance(mapping[key], (dict, list)):
                return mapping[key]
    return None


def first_int_for_keys(payload: Any, keys: Sequence[str], default: int = 0) -> int:
    value = first_scalar_for_keys(payload, keys)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return default
    return default


def collect_source_counts(payload: Any) -> dict[str, int]:
    return {
        canonical: first_int_for_keys(payload, possible_keys)
        for canonical, possible_keys in COUNT_KEYS.items()
    }


def status_values(payload: Any) -> list[str]:
    values: list[str] = []
    for mapping in iter_dicts(payload):
        for key, value in mapping.items():
            if "status" in str(key).lower() or "quality" in str(key).lower():
                if isinstance(value, str):
                    values.append(value.upper())
    return values


def has_quality_pass(payload: Any) -> bool:
    values = status_values(payload)
    return any(value == "PASS" or value.endswith("_PASS") for value in values)


def is_truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "allowed", "pass", "ready"}
    return False


def is_forbidden_truthy(mapping: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return any(is_truthy_flag(mapping.get(key)) for key in keys)


NEGATIVE_READINESS_TOKENS = (
    "context_only",
    "review_only",
    "review_required",
    "not_search_ready",
    "not_ready",
    "suppressed",
    "skip",
    "skipped",
    "reject",
    "rejected",
)

POSITIVE_READINESS_TOKENS = (
    "search_ready",
    "search-ready",
    "promoted",
    "promotion_ready",
    "evidence_ready",
    "ready_for_search",
    "packaging_candidate",
    "table_value_evidence",
)


def _readiness_blob(mapping: Mapping[str, Any]) -> str:
    keys = (
        "evidence_status",
        "promotion_status",
        "record_status",
        "audit_status",
        "readiness_status",
        "value_status",
        "packaging_status",
        "search_status",
        "route_value_status",
        "evidence_decision",
        "audit_decision",
        "promotion_decision",
        "decision",
        "record_type",
        "classification",
        "review_status",
    )
    return " ".join(str(mapping.get(key, "")) for key in keys).lower()


def _path_blob(path: Sequence[str] | None) -> str:
    return " ".join(str(part) for part in (path or ())).lower()


def is_blocked_by_status(mapping: Mapping[str, Any], path: Sequence[str] | None = None) -> bool:
    blob = f"{_readiness_blob(mapping)} {_path_blob(path)}"
    return any(token in blob for token in NEGATIVE_READINESS_TOKENS)


def is_search_ready_record(mapping: Mapping[str, Any], path: Sequence[str] | None = None) -> bool:
    flag_keys = (
        "search_ready",
        "is_search_ready",
        "search_ready_evidence",
        "promoted_to_search_ready",
        "promoted_as_evidence",
        "packaging_candidate",
        "ready_for_search",
        "is_promoted",
        "promoted",
        "evidence_ready",
    )
    if is_blocked_by_status(mapping, path):
        return False
    if any(is_truthy_flag(mapping.get(key)) for key in flag_keys):
        return True
    blob = f"{_readiness_blob(mapping)} {_path_blob(path)}"
    return any(token in blob for token in POSITIVE_READINESS_TOKENS)


def _first_value(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any | None:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "") and not isinstance(value, (dict, list)):
            return value
    return None


def normalize_field_name(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw = raw.replace(" ", "_").replace("-", "_")
    return FIELD_ALIASES.get(raw, raw)


def extract_field_name(mapping: Mapping[str, Any]) -> str:
    value = _first_value(
        mapping,
        (
            "field_name",
            "normalized_field",
            "normalized_field_name",
            "field",
            "role",
            "normalized_role",
            "template_role",
            "evidence_field",
            "field_role",
            "value_role",
            "normalized_value_role",
            "audit_field_name",
            "promoted_field_name",
            "table_field_name",
            "semantic_field",
            "value_type",
        ),
    )
    return normalize_field_name(value)


def extract_text_value(mapping: Mapping[str, Any]) -> str:
    value = _first_value(
        mapping,
        (
            "normalized_value",
            "value_normalized",
            "canonical_value",
            "raw_value",
            "cell_value",
            "cell_text",
            "text",
            "value",
            "promoted_value",
            "display_value",
            "evidence_value",
            "normalized_text",
            "value_text",
            "text_value",
            "cell_normalized_text",
            "ocr_text",
        ),
    )
    return str(value or "").strip()


def extract_raw_value(mapping: Mapping[str, Any]) -> str:
    value = _first_value(
        mapping,
        (
            "raw_value",
            "cell_text",
            "text",
            "value",
            "normalized_value",
            "display_value",
            "evidence_value",
            "normalized_text",
            "value_text",
            "text_value",
            "ocr_text",
        ),
    )
    return str(value or "").strip()


def extract_float(mapping: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    value = _first_value(mapping, keys)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def deterministic_evidence_id(record: Mapping[str, Any]) -> str:
    source = "|".join(
        str(record.get(key, ""))
        for key in (
            "page_id",
            "table_id",
            "field_name",
            "normalized_value",
            "row_index",
            "column_index",
            "source_value_id",
        )
    )
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]
    return f"table_value_evidence_{digest}"


def build_search_text(record: Mapping[str, Any]) -> str:
    parts = [
        "TRACE-Net table evidence",
        str(record.get("template_type") or ""),
        str(record.get("field_name") or ""),
        str(record.get("normalized_value") or ""),
        str(record.get("raw_value") or ""),
        str(record.get("page_id") or ""),
        str(record.get("table_id") or ""),
    ]
    return " ".join(part for part in parts if part).strip()


def package_one_record(mapping: Mapping[str, Any], path: Sequence[str] | None = None) -> dict[str, Any] | None:
    if not is_search_ready_record(mapping, path):
        return None
    if is_forbidden_truthy(mapping, ("answer_permission", "can_answer_directly", "can_prove_claims")):
        raise EvidencePackagingError("Search-ready input record tries to grant answer authority.")
    if is_forbidden_truthy(mapping, ("source_truth_mutation_allowed", "mutates_source_truth")):
        raise EvidencePackagingError("Search-ready input record tries to mutate source truth.")

    field_name = extract_field_name(mapping)
    normalized_value = extract_text_value(mapping)
    if not field_name or field_name in {"unknown", "none"}:
        return None
    if field_name in {
        "context",
        "lep_context",
        "context_only",
        "table_context",
        "header_context",
        "metadata_context",
    }:
        return None
    if not normalized_value:
        return None

    source_value_id = _first_value(
        mapping,
        (
            "evidence_id",
            "value_id",
            "normalized_value_id",
            "table_value_id",
            "cell_id",
            "source_record_id",
            "audit_record_id",
            "table_value_record_id",
            "source_table_value_record_id",
            "promoted_value_id",
            "evidence_record_id",
        ),
    )
    record: dict[str, Any] = {
        "schema_version": "trace_net_table_route_evidence_document_v1",
        "evidence_type": "table_route_value",
        "source_module": "trace_net_table_route_value_audit_v1",
        "route": "table",
        "source_value_id": source_value_id,
        "page_id": _first_value(mapping, ("page_id", "source_page_id", "page", "page_key", "page_ref")),
        "table_id": _first_value(mapping, ("table_id", "source_table_id", "table_record_id", "table_key", "source_table_key")),
        "template_type": _first_value(mapping, ("template_type", "detected_template", "table_template", "template_name")),
        "field_name": field_name,
        "normalized_value": normalized_value,
        "raw_value": extract_raw_value(mapping),
        "row_index": _first_value(mapping, ("row_index", "row", "source_row_index", "row_number")),
        "column_index": _first_value(mapping, ("column_index", "col", "column", "source_column_index", "column_number")),
        "confidence": extract_float(mapping, ("confidence", "promotion_confidence", "normalized_confidence")),
        "source_trace": mapping.get("source_trace"),
        "citation": mapping.get("citation"),
        "search_ready": True,
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }
    record["evidence_id"] = deterministic_evidence_id(record)
    record["search_text"] = build_search_text(record)
    return record


def package_evidence_records(audit_report: Any) -> list[dict[str, Any]]:
    packaged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mapping, path in iter_dicts_with_path(audit_report):
        record = package_one_record(mapping, path)
        if not record:
            continue
        evidence_id = str(record["evidence_id"])
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        packaged.append(record)
    return packaged


def count_fields(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        field_name = str(record.get("field_name") or "unknown")
        counts[field_name] = counts.get(field_name, 0) + 1
    return dict(sorted(counts.items()))


def count_pages(records: Sequence[Mapping[str, Any]]) -> int:
    return len({str(record.get("page_id")) for record in records if record.get("page_id")})


def count_tables(records: Sequence[Mapping[str, Any]]) -> int:
    return len({str(record.get("table_id")) for record in records if record.get("table_id")})


def safety_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "unsafe_evidence_document_count": 0,
        "answer_permission_count": sum(1 for record in records if is_truthy_flag(record.get("answer_permission"))),
        "can_answer_directly_count": sum(1 for record in records if is_truthy_flag(record.get("can_answer_directly"))),
        "can_prove_claims_count": sum(1 for record in records if is_truthy_flag(record.get("can_prove_claims"))),
        "source_truth_mutation_allowed_count": sum(
            1 for record in records if is_truthy_flag(record.get("source_truth_mutation_allowed"))
        ),
        "postgres_write_attempt_count": sum(1 for record in records if is_truthy_flag(record.get("postgres_write_attempt"))),
        "qdrant_write_attempt_count": sum(1 for record in records if is_truthy_flag(record.get("qdrant_write_attempt"))),
        "opensearch_write_attempt_count": sum(1 for record in records if is_truthy_flag(record.get("opensearch_write_attempt"))),
    }


def build_summary(audit_report: Any, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    source_counts = collect_source_counts(audit_report)
    field_counts = count_fields(records)
    safe_counts = safety_counts(records)
    return {
        "source_quality_pass": has_quality_pass(audit_report),
        **source_counts,
        "table_route_evidence_document_count": len(records),
        "page_with_evidence_count": count_pages(records),
        "table_with_evidence_count": count_tables(records),
        "field_count": len(field_counts),
        "field_counts": field_counts,
        **safe_counts,
    }


def build_quality_checks(summary: Mapping[str, Any], thresholds: EvidencePackagerThresholds) -> list[QualityCheck]:
    field_counts = summary.get("field_counts", {}) if isinstance(summary.get("field_counts"), Mapping) else {}
    checks = [
        QualityCheck(
            "source_audit_record_count",
            summary.get("source_audit_record_count", 0),
            f">= {thresholds.min_source_audit_records}",
            int(summary.get("source_audit_record_count", 0)) >= thresholds.min_source_audit_records,
        ),
        QualityCheck(
            "source_search_ready_evidence_record_count",
            summary.get("source_search_ready_evidence_record_count", 0),
            f">= {thresholds.min_source_search_ready_records}",
            int(summary.get("source_search_ready_evidence_record_count", 0))
            >= thresholds.min_source_search_ready_records,
        ),
        QualityCheck(
            "table_route_evidence_document_count",
            summary.get("table_route_evidence_document_count", 0),
            f">= {thresholds.min_evidence_documents}",
            int(summary.get("table_route_evidence_document_count", 0)) >= thresholds.min_evidence_documents,
        ),
        QualityCheck(
            "page_with_evidence_count",
            summary.get("page_with_evidence_count", 0),
            f">= {thresholds.min_pages_with_evidence}",
            int(summary.get("page_with_evidence_count", 0)) >= thresholds.min_pages_with_evidence,
        ),
        QualityCheck(
            "field_count",
            summary.get("field_count", 0),
            f">= {thresholds.min_field_count}",
            int(summary.get("field_count", 0)) >= thresholds.min_field_count,
        ),
        QualityCheck(
            "covered_part_number_documents",
            field_counts.get("covered_part_number", 0),
            f">= {thresholds.min_covered_part_number_documents}",
            int(field_counts.get("covered_part_number", 0)) >= thresholds.min_covered_part_number_documents,
        ),
        QualityCheck(
            "manual_page_reference_documents",
            field_counts.get("manual_page_reference", 0),
            f">= {thresholds.min_manual_page_reference_documents}",
            int(field_counts.get("manual_page_reference", 0)) >= thresholds.min_manual_page_reference_documents,
        ),
        QualityCheck(
            "ipl_part_number_documents",
            field_counts.get("ipl_part_number", 0),
            f">= {thresholds.min_ipl_part_number_documents}",
            int(field_counts.get("ipl_part_number", 0)) >= thresholds.min_ipl_part_number_documents,
        ),
        QualityCheck(
            "unsafe_evidence_document_count",
            summary.get("unsafe_evidence_document_count", 0),
            f"<= {thresholds.max_unsafe_records}",
            int(summary.get("unsafe_evidence_document_count", 0)) <= thresholds.max_unsafe_records,
        ),
        QualityCheck(
            "answer_permission_count",
            summary.get("answer_permission_count", 0),
            f"<= {thresholds.max_answer_permission_count}",
            int(summary.get("answer_permission_count", 0)) <= thresholds.max_answer_permission_count,
        ),
        QualityCheck(
            "source_truth_mutation_allowed_count",
            summary.get("source_truth_mutation_allowed_count", 0),
            f"<= {thresholds.max_source_truth_mutation_allowed}",
            int(summary.get("source_truth_mutation_allowed_count", 0))
            <= thresholds.max_source_truth_mutation_allowed,
        ),
        QualityCheck(
            "postgres_write_attempt_count",
            summary.get("postgres_write_attempt_count", 0),
            "== 0",
            int(summary.get("postgres_write_attempt_count", 0)) == 0,
        ),
        QualityCheck(
            "qdrant_write_attempt_count",
            summary.get("qdrant_write_attempt_count", 0),
            "== 0",
            int(summary.get("qdrant_write_attempt_count", 0)) == 0,
        ),
        QualityCheck(
            "opensearch_write_attempt_count",
            summary.get("opensearch_write_attempt_count", 0),
            "== 0",
            int(summary.get("opensearch_write_attempt_count", 0)) == 0,
        ),
    ]
    if thresholds.require_source_audit_quality_pass:
        checks.append(
            QualityCheck(
                "source_audit_quality_pass",
                summary.get("source_quality_pass", False),
                "is True",
                bool(summary.get("source_quality_pass", False)),
            )
        )
    if thresholds.require_no_answer_permission:
        checks.extend(
            [
                QualityCheck(
                    "can_answer_directly_count",
                    summary.get("can_answer_directly_count", 0),
                    "== 0",
                    int(summary.get("can_answer_directly_count", 0)) == 0,
                ),
                QualityCheck(
                    "can_prove_claims_count",
                    summary.get("can_prove_claims_count", 0),
                    "== 0",
                    int(summary.get("can_prove_claims_count", 0)) == 0,
                ),
            ]
        )
    return checks


def render_inspect_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    field_counts = summary.get("field_counts", {}) if isinstance(summary.get("field_counts"), Mapping) else {}
    records = report.get("evidence_documents", []) if isinstance(report.get("evidence_documents"), list) else []
    lines = [
        "# TRACE-Net Table Route Evidence Packager v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status', 'UNKNOWN')}**",
        "",
        "## Package counters",
        f"- source_search_ready_evidence_record_count: {summary.get('source_search_ready_evidence_record_count', 0)}",
        f"- table_route_evidence_document_count: {summary.get('table_route_evidence_document_count', 0)}",
        f"- page_with_evidence_count: {summary.get('page_with_evidence_count', 0)}",
        f"- table_with_evidence_count: {summary.get('table_with_evidence_count', 0)}",
        f"- field_count: {summary.get('field_count', 0)}",
        "",
        "## Field counts",
    ]
    if field_counts:
        for key, value in field_counts.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Safety/write counters",
            f"- unsafe_evidence_document_count: {summary.get('unsafe_evidence_document_count', 0)}",
            f"- answer_permission_count: {summary.get('answer_permission_count', 0)}",
            f"- can_answer_directly_count: {summary.get('can_answer_directly_count', 0)}",
            f"- can_prove_claims_count: {summary.get('can_prove_claims_count', 0)}",
            f"- source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count', 0)}",
            f"- postgres_write_attempt_count: {summary.get('postgres_write_attempt_count', 0)}",
            f"- qdrant_write_attempt_count: {summary.get('qdrant_write_attempt_count', 0)}",
            f"- opensearch_write_attempt_count: {summary.get('opensearch_write_attempt_count', 0)}",
            "",
            "## First evidence documents",
        ]
    )
    for index, record in enumerate(records[:50], start=1):
        page = record.get("page_id") or "unknown_page"
        field = record.get("field_name") or "unknown_field"
        value = record.get("normalized_value") or ""
        lines.append(f"{index}. `{page}` `{field}` = `{value}`")
    if not records:
        lines.append("No evidence documents packaged.")
    lines.append("")
    return "\n".join(lines)


def build_report(
    audit_report: Any,
    thresholds: EvidencePackagerThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or EvidencePackagerThresholds()
    evidence_documents = package_evidence_records(audit_report)
    summary = build_summary(audit_report, evidence_documents)
    checks = build_quality_checks(summary, thresholds)
    quality_pass = all(check.passed for check in checks)
    return {
        "schema_version": "trace_net_table_route_evidence_packager_v1",
        "quality_status": "PASS" if quality_pass else "FAIL",
        "thresholds": thresholds.as_dict(),
        "summary": summary,
        "checks": [check.to_dict() for check in checks],
        "evidence_documents": evidence_documents,
        "safety_contract": {
            "retrieval_only": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
        "notes": [
            "Packages audited table values into local retrieval/search evidence documents only.",
            "These documents can support candidate retrieval and exact search indexing later.",
            "They cannot prove final claims and grant no answer permission.",
        ],
    }


def write_packager_outputs(
    audit_report_path: Path,
    output_dir: Path,
    thresholds: EvidencePackagerThresholds | None = None,
) -> dict[str, Any]:
    audit_report = load_json(audit_report_path)
    report = build_report(audit_report, thresholds)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / DEFAULT_PACKAGE_REPORT_PATH.name
    evidence_jsonl_path = output_dir / DEFAULT_EVIDENCE_JSONL_PATH.name
    quality_path = output_dir / DEFAULT_QUALITY_PATH.name
    inspect_md_path = output_dir / DEFAULT_INSPECT_MD_PATH.name
    write_json(report_path, report)
    write_jsonl(evidence_jsonl_path, report["evidence_documents"])
    write_json(
        quality_path,
        {
            "schema_version": "trace_net_table_route_evidence_packager_quality_v1",
            "quality_status": report["quality_status"],
            "summary": report["summary"],
            "checks": report["checks"],
            "safety_contract": report["safety_contract"],
            "report_path": str(report_path),
            "evidence_jsonl_path": str(evidence_jsonl_path),
        },
    )
    inspect_md_path.write_text(render_inspect_markdown(report), encoding="utf-8")
    return report
