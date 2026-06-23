"""TRACE-Net table-route value-audit LEP-v4 preset utilities.

This module does not replace ``trace_net_table_route_value_audit_v1``.
It pins the post-LEP-v4 rerun thresholds and provides a small deterministic
quality/inspection layer for the current table-route audit handoff.

Safety contract:
- read-only JSON artifact inspection
- no Postgres/Qdrant/OpenSearch writes
- no answer permission or source-truth mutation grants
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


DEFAULT_NORMALIZER_PATH = Path(
    "local_data/organization/trace_net/table_route_value_normalizer/"
    "trace_net_table_route_value_normalizer_v1.json"
)
DEFAULT_AUDIT_OUTPUT_DIR = Path(
    "local_data/organization/trace_net/table_route_value_audit"
)
DEFAULT_AUDIT_REPORT_PATH = DEFAULT_AUDIT_OUTPUT_DIR / "trace_net_table_route_value_audit_v1.json"
DEFAULT_PRESET_MANIFEST_PATH = DEFAULT_AUDIT_OUTPUT_DIR / (
    "trace_net_table_route_value_audit_lep_v4_preset_v1_manifest.json"
)
DEFAULT_PRESET_QUALITY_PATH = DEFAULT_AUDIT_OUTPUT_DIR / (
    "trace_net_table_route_value_audit_lep_v4_preset_v1_quality.json"
)
DEFAULT_PRESET_INSPECT_PATH = DEFAULT_AUDIT_OUTPUT_DIR / (
    "trace_net_table_route_value_audit_lep_v4_preset_v1_inspect.json"
)
DEFAULT_PRESET_INSPECT_MD_PATH = DEFAULT_AUDIT_OUTPUT_DIR / (
    "trace_net_table_route_value_audit_lep_v4_preset_v1_inspect.md"
)

BUILD_SCRIPT = Path("scripts/build_trace_net_table_route_value_audit_v1.py")
CHECK_SCRIPT = Path("scripts/check_trace_net_table_route_value_audit_v1_quality.py")


@dataclass(frozen=True)
class LepV4AuditPreset:
    """Pinned thresholds for the post-LEP-v4 table value audit rerun."""

    min_promote_confidence: float = 0.60
    max_context_ratio: float = 0.75
    min_source_normalizer_records: int = 20
    min_source_normalized_records: int = 1800
    min_audit_records: int = 20
    min_audited_tables: int = 19
    min_promoted_evidence_records: int = 1000
    min_search_ready_evidence_records: int = 1000
    min_covered_part_number_promoted: int = 100
    min_manual_page_reference_promoted: int = 39
    min_ipl_part_number_promoted: int = 100
    max_unsafe_records: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_table_route_value_normalizer_quality_pass: bool = True
    require_no_answer_permission: bool = True
    inspect_limit: int = 50

    def build_args(self, normalizer_path: Path, output_dir: Path) -> list[str]:
        """Return argv for the existing audit builder with LEP-v4 thresholds."""
        args = [
            "python",
            str(BUILD_SCRIPT),
            "--table-route-value-normalizer",
            str(normalizer_path),
            "--output-dir",
            str(output_dir),
            "--min-promote-confidence",
            f"{self.min_promote_confidence:.2f}",
            "--max-context-ratio",
            f"{self.max_context_ratio:.2f}",
            "--min-source-normalizer-records",
            str(self.min_source_normalizer_records),
            "--min-source-normalized-records",
            str(self.min_source_normalized_records),
            "--min-audit-records",
            str(self.min_audit_records),
            "--min-audited-tables",
            str(self.min_audited_tables),
            "--min-promoted-evidence-records",
            str(self.min_promoted_evidence_records),
            "--min-search-ready-evidence-records",
            str(self.min_search_ready_evidence_records),
            "--min-covered-part-number-promoted",
            str(self.min_covered_part_number_promoted),
            "--min-manual-page-reference-promoted",
            str(self.min_manual_page_reference_promoted),
            "--min-ipl-part-number-promoted",
            str(self.min_ipl_part_number_promoted),
            "--max-unsafe-records",
            str(self.max_unsafe_records),
            "--max-answer-permission-count",
            str(self.max_answer_permission_count),
            "--max-source-truth-mutation-allowed",
            str(self.max_source_truth_mutation_allowed),
        ]
        if self.require_table_route_value_normalizer_quality_pass:
            args.append("--require-table-route-value-normalizer-quality-pass")
        if self.require_no_answer_permission:
            args.append("--require-no-answer-permission")
        args.append("--quality")
        return args

    def upstream_check_args(self, report_path: Path) -> list[str]:
        """Return argv for the existing audit quality checker."""
        args = [
            "python",
            str(CHECK_SCRIPT),
            "--report-path",
            str(report_path),
            "--min-source-normalizer-records",
            str(self.min_source_normalizer_records),
            "--min-source-normalized-records",
            str(self.min_source_normalized_records),
            "--min-audit-records",
            str(self.min_audit_records),
            "--min-audited-tables",
            str(self.min_audited_tables),
            "--min-promoted-evidence-records",
            str(self.min_promoted_evidence_records),
            "--min-search-ready-evidence-records",
            str(self.min_search_ready_evidence_records),
            "--min-covered-part-number-promoted",
            str(self.min_covered_part_number_promoted),
            "--min-manual-page-reference-promoted",
            str(self.min_manual_page_reference_promoted),
            "--min-ipl-part-number-promoted",
            str(self.min_ipl_part_number_promoted),
            "--max-unsafe-records",
            str(self.max_unsafe_records),
            "--max-answer-permission-count",
            str(self.max_answer_permission_count),
            "--max-source-truth-mutation-allowed",
            str(self.max_source_truth_mutation_allowed),
        ]
        if self.require_table_route_value_normalizer_quality_pass:
            args.append("--require-table-route-value-normalizer-quality-pass")
        if self.require_no_answer_permission:
            args.append("--require-no-answer-permission")
        args.append("--write-json")
        return args

    def as_dict(self) -> dict[str, Any]:
        return {
            "min_promote_confidence": self.min_promote_confidence,
            "max_context_ratio": self.max_context_ratio,
            "min_source_normalizer_records": self.min_source_normalizer_records,
            "min_source_normalized_records": self.min_source_normalized_records,
            "min_audit_records": self.min_audit_records,
            "min_audited_tables": self.min_audited_tables,
            "min_promoted_evidence_records": self.min_promoted_evidence_records,
            "min_search_ready_evidence_records": self.min_search_ready_evidence_records,
            "min_covered_part_number_promoted": self.min_covered_part_number_promoted,
            "min_manual_page_reference_promoted": self.min_manual_page_reference_promoted,
            "min_ipl_part_number_promoted": self.min_ipl_part_number_promoted,
            "max_unsafe_records": self.max_unsafe_records,
            "max_answer_permission_count": self.max_answer_permission_count,
            "max_source_truth_mutation_allowed": self.max_source_truth_mutation_allowed,
            "require_table_route_value_normalizer_quality_pass": (
                self.require_table_route_value_normalizer_quality_pass
            ),
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


COUNT_KEYS = {
    "source_normalizer_record_count": ("source_normalizer_record_count", "source_table_route_value_normalizer_record_count"),
    "source_normalized_table_value_record_count": (
        "source_normalized_table_value_record_count",
        "source_normalized_record_count",
        "normalized_table_value_record_count",
    ),
    "table_route_value_audit_record_count": ("table_route_value_audit_record_count", "audit_record_count"),
    "audited_table_count": ("audited_table_count",),
    "evidence_ready_table_count": ("evidence_ready_table_count",),
    "review_required_table_count": ("review_required_table_count",),
    "high_context_ratio_table_count": ("high_context_ratio_table_count",),
    "promoted_table_value_evidence_record_count": (
        "promoted_table_value_evidence_record_count",
        "promoted_evidence_record_count",
    ),
    "search_ready_evidence_record_count": ("search_ready_evidence_record_count",),
    "context_only_record_count": ("context_only_record_count",),
    "covered_part_number_promoted_count": ("covered_part_number_promoted_count",),
    "manual_page_reference_promoted_count": ("manual_page_reference_promoted_count",),
    "page_rev_or_sequence_value_promoted_count": ("page_rev_or_sequence_value_promoted_count",),
    "ipl_part_number_promoted_count": ("ipl_part_number_promoted_count",),
    "ipl_figure_item_or_quantity_promoted_count": ("ipl_figure_item_or_quantity_promoted_count",),
    "ipl_text_promoted_count": ("ipl_text_promoted_count",),
    "unsafe_record_count": (
        "unsafe_record_count",
        "unsafe_table_route_value_audit_record_count",
    ),
    "answer_permission_count": ("answer_permission_count",),
    "can_answer_directly_count": ("can_answer_directly_count",),
    "can_prove_claims_count": ("can_prove_claims_count",),
    "source_truth_mutation_allowed_count": ("source_truth_mutation_allowed_count",),
    "postgres_write_attempt_count": ("postgres_write_attempt_count",),
    "qdrant_write_attempt_count": ("qdrant_write_attempt_count",),
    "opensearch_write_attempt_count": ("opensearch_write_attempt_count",),
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def iter_dicts(payload: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        yield payload
        for value in payload.values():
            yield from iter_dicts(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from iter_dicts(item)


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


def collect_counts(payload: Any) -> dict[str, int]:
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
        return value.strip().lower() in {"true", "yes", "1", "allowed", "pass"}
    return False


def is_search_ready_record(mapping: Mapping[str, Any]) -> bool:
    flag_keys = (
        "search_ready",
        "is_search_ready",
        "search_ready_evidence",
        "promoted_to_search_ready",
        "promoted_as_evidence",
    )
    if any(is_truthy_flag(mapping.get(key)) for key in flag_keys):
        return True
    status_blob = " ".join(
        str(mapping.get(key, ""))
        for key in ("evidence_status", "promotion_status", "record_status", "audit_status")
    ).lower()
    return "search_ready" in status_blob or "promoted" in status_blob


def compact_value_record(mapping: Mapping[str, Any]) -> dict[str, Any]:
    wanted_keys = [
        "evidence_id",
        "value_id",
        "normalized_value_id",
        "page_id",
        "table_id",
        "template_type",
        "field_name",
        "normalized_field",
        "field",
        "normalized_value",
        "raw_value",
        "text",
        "confidence",
        "row_index",
        "column_index",
        "source_trace",
        "review_status",
        "evidence_status",
        "promotion_status",
    ]
    compact = {key: mapping.get(key) for key in wanted_keys if key in mapping}
    # Keep the output useful even if upstream naming differs.
    if not compact:
        for key, value in list(mapping.items())[:12]:
            if not isinstance(value, (dict, list)):
                compact[str(key)] = value
    return compact


def first_search_ready_values(payload: Any, limit: int = 50) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for mapping in iter_dicts(payload):
        if is_search_ready_record(mapping):
            records.append(compact_value_record(mapping))
            if len(records) >= limit:
                break
    return records


def build_quality_checks(
    counts: Mapping[str, int],
    preset: LepV4AuditPreset,
    normalizer_quality_pass: bool | None = None,
) -> list[QualityCheck]:
    checks = [
        QualityCheck(
            "source_normalizer_record_count",
            counts["source_normalizer_record_count"],
            f">= {preset.min_source_normalizer_records}",
            counts["source_normalizer_record_count"] >= preset.min_source_normalizer_records,
        ),
        QualityCheck(
            "source_normalized_table_value_record_count",
            counts["source_normalized_table_value_record_count"],
            f">= {preset.min_source_normalized_records}",
            counts["source_normalized_table_value_record_count"] >= preset.min_source_normalized_records,
        ),
        QualityCheck(
            "table_route_value_audit_record_count",
            counts["table_route_value_audit_record_count"],
            f">= {preset.min_audit_records}",
            counts["table_route_value_audit_record_count"] >= preset.min_audit_records,
        ),
        QualityCheck(
            "audited_table_count",
            counts["audited_table_count"],
            f">= {preset.min_audited_tables}",
            counts["audited_table_count"] >= preset.min_audited_tables,
        ),
        QualityCheck(
            "promoted_table_value_evidence_record_count",
            counts["promoted_table_value_evidence_record_count"],
            f">= {preset.min_promoted_evidence_records}",
            counts["promoted_table_value_evidence_record_count"] >= preset.min_promoted_evidence_records,
        ),
        QualityCheck(
            "search_ready_evidence_record_count",
            counts["search_ready_evidence_record_count"],
            f">= {preset.min_search_ready_evidence_records}",
            counts["search_ready_evidence_record_count"] >= preset.min_search_ready_evidence_records,
        ),
        QualityCheck(
            "covered_part_number_promoted_count",
            counts["covered_part_number_promoted_count"],
            f">= {preset.min_covered_part_number_promoted}",
            counts["covered_part_number_promoted_count"] >= preset.min_covered_part_number_promoted,
        ),
        QualityCheck(
            "manual_page_reference_promoted_count",
            counts["manual_page_reference_promoted_count"],
            f">= {preset.min_manual_page_reference_promoted}",
            counts["manual_page_reference_promoted_count"] >= preset.min_manual_page_reference_promoted,
        ),
        QualityCheck(
            "ipl_part_number_promoted_count",
            counts["ipl_part_number_promoted_count"],
            f">= {preset.min_ipl_part_number_promoted}",
            counts["ipl_part_number_promoted_count"] >= preset.min_ipl_part_number_promoted,
        ),
        QualityCheck(
            "unsafe_record_count",
            counts["unsafe_record_count"],
            f"<= {preset.max_unsafe_records}",
            counts["unsafe_record_count"] <= preset.max_unsafe_records,
        ),
        QualityCheck(
            "answer_permission_count",
            counts["answer_permission_count"],
            f"<= {preset.max_answer_permission_count}",
            counts["answer_permission_count"] <= preset.max_answer_permission_count,
        ),
        QualityCheck(
            "source_truth_mutation_allowed_count",
            counts["source_truth_mutation_allowed_count"],
            f"<= {preset.max_source_truth_mutation_allowed}",
            counts["source_truth_mutation_allowed_count"]
            <= preset.max_source_truth_mutation_allowed,
        ),
        QualityCheck(
            "postgres_write_attempt_count",
            counts["postgres_write_attempt_count"],
            "== 0",
            counts["postgres_write_attempt_count"] == 0,
        ),
        QualityCheck(
            "qdrant_write_attempt_count",
            counts["qdrant_write_attempt_count"],
            "== 0",
            counts["qdrant_write_attempt_count"] == 0,
        ),
        QualityCheck(
            "opensearch_write_attempt_count",
            counts["opensearch_write_attempt_count"],
            "== 0",
            counts["opensearch_write_attempt_count"] == 0,
        ),
    ]
    if preset.require_no_answer_permission:
        checks.extend(
            [
                QualityCheck(
                    "can_answer_directly_count",
                    counts["can_answer_directly_count"],
                    "== 0",
                    counts["can_answer_directly_count"] == 0,
                ),
                QualityCheck(
                    "can_prove_claims_count",
                    counts["can_prove_claims_count"],
                    "== 0",
                    counts["can_prove_claims_count"] == 0,
                ),
            ]
        )
    if preset.require_table_route_value_normalizer_quality_pass:
        checks.append(
            QualityCheck(
                "table_route_value_normalizer_quality_pass",
                normalizer_quality_pass,
                "is True",
                bool(normalizer_quality_pass),
            )
        )
    return checks


def inspect_report(
    audit_report: Any,
    preset: LepV4AuditPreset,
    normalizer_report: Any | None = None,
) -> dict[str, Any]:
    counts = collect_counts(audit_report)
    normalizer_quality_pass = None
    if normalizer_report is not None:
        normalizer_quality_pass = has_quality_pass(normalizer_report)
    elif has_quality_pass(audit_report):
        # Existing audit reports often embed source-quality status.
        normalizer_quality_pass = True
    checks = build_quality_checks(counts, preset, normalizer_quality_pass)
    quality_pass = all(check.passed for check in checks)
    first_values = first_search_ready_values(audit_report, preset.inspect_limit)
    return {
        "schema_version": "trace_net_table_route_value_audit_lep_v4_preset_v1",
        "quality_status": "PASS" if quality_pass else "FAIL",
        "preset": preset.as_dict(),
        "counts": counts,
        "checks": [check.to_dict() for check in checks],
        "watch_counters": {
            "high_context_ratio_table_count": counts["high_context_ratio_table_count"],
            "review_required_table_count": counts["review_required_table_count"],
            "evidence_ready_table_count": counts["evidence_ready_table_count"],
            "search_ready_evidence_record_count": counts["search_ready_evidence_record_count"],
            "context_only_record_count": counts["context_only_record_count"],
        },
        "promoted_fields": {
            "covered_part_number": counts["covered_part_number_promoted_count"],
            "manual_page_reference": counts["manual_page_reference_promoted_count"],
            "page_rev_or_sequence_value": counts["page_rev_or_sequence_value_promoted_count"],
            "ipl_part_number": counts["ipl_part_number_promoted_count"],
            "ipl_figure_item_or_quantity": counts["ipl_figure_item_or_quantity_promoted_count"],
            "ipl_text": counts["ipl_text_promoted_count"],
        },
        "first_search_ready_values": first_values,
        "notes": [
            "LEP v4 intentionally reduced normalized value count by suppressing noisy context.",
            "This preset therefore gates min_source_normalized_records at 1800 instead of 3000.",
            "Search-ready table evidence remains retrieval/search support only; it grants no answer authority.",
        ],
    }


def render_markdown_inspect(inspection: Mapping[str, Any]) -> str:
    counts = inspection.get("counts", {})
    watch = inspection.get("watch_counters", {})
    promoted = inspection.get("promoted_fields", {})
    lines = [
        "# TRACE-Net Table Route Value Audit LEP v4 Preset Inspect",
        "",
        f"Quality status: **{inspection.get('quality_status', 'UNKNOWN')}**",
        "",
        "## Watch counters",
    ]
    for key in [
        "high_context_ratio_table_count",
        "review_required_table_count",
        "evidence_ready_table_count",
        "search_ready_evidence_record_count",
        "context_only_record_count",
    ]:
        lines.append(f"- {key}: {watch.get(key, counts.get(key, 0))}")
    lines.extend(["", "## Promoted fields"])
    for key, value in promoted.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Safety/write counters"])
    for key in [
        "unsafe_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        lines.append(f"- {key}: {counts.get(key, 0)}")
    lines.extend(["", "## First search-ready values"])
    first_values = inspection.get("first_search_ready_values", [])
    if not first_values:
        lines.append("No compact search-ready records were found in the report body; use counts above.")
    else:
        for index, record in enumerate(first_values, start=1):
            page = record.get("page_id", "unknown_page")
            field = record.get("field_name") or record.get("normalized_field") or record.get("field", "unknown_field")
            value = record.get("normalized_value") or record.get("raw_value") or record.get("text", "")
            lines.append(f"{index}. `{page}` `{field}` = `{value}`")
    lines.append("")
    return "\n".join(lines)


def write_inspection_outputs(
    audit_report_path: Path,
    output_dir: Path,
    preset: LepV4AuditPreset,
    normalizer_path: Path | None = None,
) -> dict[str, Any]:
    audit_report = load_json(audit_report_path)
    normalizer_report = load_json(normalizer_path) if normalizer_path and normalizer_path.exists() else None
    inspection = inspect_report(audit_report, preset, normalizer_report)
    inspect_path = output_dir / DEFAULT_PRESET_INSPECT_PATH.name
    quality_path = output_dir / DEFAULT_PRESET_QUALITY_PATH.name
    inspect_md_path = output_dir / DEFAULT_PRESET_INSPECT_MD_PATH.name
    write_json(inspect_path, inspection)
    write_json(
        quality_path,
        {
            "schema_version": "trace_net_table_route_value_audit_lep_v4_preset_quality_v1",
            "quality_status": inspection["quality_status"],
            "checks": inspection["checks"],
            "counts": inspection["counts"],
            "watch_counters": inspection["watch_counters"],
            "promoted_fields": inspection["promoted_fields"],
        },
    )
    inspect_md_path.parent.mkdir(parents=True, exist_ok=True)
    inspect_md_path.write_text(render_markdown_inspect(inspection), encoding="utf-8")
    return inspection
