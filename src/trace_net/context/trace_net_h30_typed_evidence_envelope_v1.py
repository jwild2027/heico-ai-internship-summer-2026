"""TRACE-Net H30 Phase 4 canonical typed evidence envelope.

This layer creates a deterministic typed view over the existing evidence
envelope. It does not run retrieval, change ranking, select evidence, write an
answer, grant answer permission, or mutate source truth.

Legacy evidence lists remain unchanged for compatibility. The typed view makes
authority, source trace, proof eligibility, modality, claim scope, conflict
state, and resolution status explicit for later answer-mode and critic phases.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_typed_evidence_envelope_v1"
VERSION = "v1"
SCHEMA_VERSION = "trace_net_typed_evidence_envelope_v1"
STATUS = "TRACE_NET_TYPED_EVIDENCE_ENVELOPE_V1"

SOURCE_BUCKETS: Tuple[str, ...] = (
    "direct_evidence",
    "candidate_evidence",
    "visual_guidance",
    "semantic_guidance",
    "contradictions",
    "source_resolution",
)

GUIDANCE_BUCKETS = {
    "candidate_evidence",
    "visual_guidance",
    "semantic_guidance",
    "source_resolution",
}

AUTHORITY_HINTS = {
    "approval",
    "approved_replacement",
    "interchange",
    "interchangeability",
    "effectivity",
    "eligibility",
    "installation_authority",
    "applicability",
}

ROUTE_CLAIM_MAP = {
    "exact_identifier_lookup": "part_identity",
    "guided_part_discovery": "part_identity",
    "ata_system_discovery": "document_overview",
    "nomenclature_function_search": "nomenclature",
    "exact_table_ipl_lookup": "table_item",
    "visual_figure_callout_lookup": "figure_callout",
    "procedure_task_lookup": "procedure_step",
    "warning_caution_note_lookup": "warning_or_caution",
    "authority_eligibility_verification": "authority_approval",
    "document_page_navigation": "page_location",
    "graph_relationship_reasoning": "assembly_relationship",
    "semantic_discovery": "document_overview",
    "cross_source_comparison": "comparison",
    "contradiction_resolution": "contradiction",
    "ocr_scan_recovery": "ocr_text",
    "high_degree_entity_aggregation": "document_overview",
    "multi_question_research": "document_overview",
}

REQUIRED_TYPED_KEYS = {
    "record_id",
    "schema_version",
    "source_bucket",
    "source_index",
    "evidence_class",
    "modality",
    "authority_class",
    "proof_status",
    "resolution_status",
    "claim_types",
    "claim_support_allowed",
    "final_answer_eligible",
    "guidance_only",
    "conflicted",
    "source_trace",
    "identity",
    "excerpt",
}

SAFETY_CONTRACT = {
    "read_only": True,
    "legacy_evidence_preserved": True,
    "typed_view_is_metadata_not_new_evidence": True,
    "guidance_never_supports_final_claims": True,
    "conflicts_never_support_final_claims": True,
    "source_trace_required_for_claim_support": True,
    "answer_permission": False,
    "final_answer_allowed": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _compact(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "pass",
        "ready",
        "citation_ready",
    }


def _first(row: Mapping[str, Any], keys: Sequence[str], limit: int = 1200) -> str:
    for key in keys:
        value = _compact(row.get(key), limit)
        if value:
            return value
    return ""


def _stable_id(bucket: str, index: int, row: Mapping[str, Any]) -> str:
    identity = {
        "bucket": bucket,
        "index": index,
        "page_id": _first(row, ("page_id", "source_page_id", "page"), 300),
        "field_name": _first(row, ("field_name", "field", "claim_type"), 300),
        "value": _first(
            row,
            (
                "normalized_value",
                "value",
                "candidate_value",
                "candidate_part_number",
                "part_number",
                "snippet",
                "text",
            ),
            1200,
        ),
        "document": _first(
            row,
            ("document", "document_id", "manual", "source_file"),
            500,
        ),
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return "tev_" + digest[:20]


def _field_blob(row: Mapping[str, Any]) -> str:
    return " ".join(
        [
            _first(row, ("field_name", "field", "claim_type", "record_type", "candidate_type"), 500),
            _first(row, ("source_type", "proof_source", "source_path", "tunnel"), 800),
            " ".join(str(key) for key in row.keys()),
        ]
    ).lower()


def infer_modality(bucket: str, row: Mapping[str, Any]) -> str:
    blob = _field_blob(row)
    if bucket == "contradictions" or "conflict" in blob or "mismatch" in blob:
        return "conflict"
    if bucket == "visual_guidance" or any(
        token in blob for token in ("visual", "figure", "diagram", "llava", "callout")
    ):
        return "visual"
    if bucket == "semantic_guidance":
        if any(token in blob for token in ("graph", "leiden", "community", "relationship")):
            return "graph"
        if any(token in blob for token in ("summary", "v2", "v3", "context")):
            return "summary"
        return "semantic_vector"
    if any(token in blob for token in ("table", "ipl", "row", "cell", "item")):
        return "table"
    if "ocr" in blob:
        return "ocr"
    if any(token in blob for token in ("graph", "edge", "leiden", "community", "relationship")):
        return "graph"
    if bucket == "source_resolution":
        return "source_resolution"
    if any(token in blob for token in AUTHORITY_HINTS):
        return "authority_record"
    return "textual_source"


def infer_claim_types(
    *,
    route: str,
    bucket: str,
    row: Mapping[str, Any],
    modality: str,
) -> List[str]:
    claims: List[str] = []
    field = _first(
        row,
        ("field_name", "field", "claim_type", "record_type", "candidate_type"),
        500,
    ).lower()
    if bucket == "contradictions":
        claims.append("contradiction")
    if any(hint in field for hint in AUTHORITY_HINTS):
        claims.append("authority_approval")
    if any(token in field for token in ("part_number", "part number", "p/n", "pn")):
        claims.append("part_identity")
    if "nomenclature" in field or "description" in field:
        claims.append("nomenclature")
    if modality == "table" or any(token in field for token in ("table", "ipl", "item")):
        claims.append("table_item")
    if modality == "visual" or any(token in field for token in ("figure", "callout")):
        claims.append("figure_callout")
    if "procedure" in field or "step" in field:
        claims.append("procedure_step")
    if any(token in field for token in ("warning", "caution", "note")):
        claims.append("warning_or_caution")
    if modality == "ocr":
        claims.append("ocr_text")
    if modality == "graph":
        claims.append("assembly_relationship")
    route_claim = ROUTE_CLAIM_MAP.get(route)
    if route_claim:
        claims.append(route_claim)
    output: List[str] = []
    seen = set()
    for value in claims:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output[:8]


def _source_trace(row: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = _first(row, ("page_id", "source_page_id", "page", "trace_page_id"), 300)
    document = _first(
        row,
        ("document", "document_id", "source_document", "manual", "source_file", "filename"),
        600,
    )
    field_name = _first(
        row,
        ("field_name", "field", "claim_type", "record_type", "candidate_type"),
        400,
    )
    source_path = _first(row, ("source_path", "path", "artifact_path"), 1000)
    source_trace_ready = _truthy(row.get("source_trace_ready"))
    citation_ready = _truthy(row.get("citation_ready"))
    ready = bool(page_id and (source_trace_ready or citation_ready))
    return {
        "page_id": page_id,
        "document": document,
        "field_name": field_name,
        "source_path": source_path,
        "citation_ready": citation_ready,
        "source_trace_ready": source_trace_ready,
        "ready": ready,
    }


def _identity(row: Mapping[str, Any]) -> Dict[str, Any]:
    candidate = _first(
        row,
        (
            "candidate_value",
            "candidate_part_number",
            "part_number",
            "normalized_identifier",
            "matched_token",
        ),
        300,
    )
    part_numbers = row.get("part_numbers")
    if not isinstance(part_numbers, list):
        part_numbers = [candidate] if candidate else []
    return {
        "candidate": candidate,
        "part_numbers": [str(item) for item in part_numbers[:12] if str(item).strip()],
        "ata": _first(row, ("ata", "ata_reference", "ata_code"), 100),
        "figure_refs": list(row.get("figure_refs") or [])[:12]
        if isinstance(row.get("figure_refs"), list)
        else [],
        "item": _first(row, ("item", "item_number"), 100),
    }


def _excerpt(row: Mapping[str, Any]) -> str:
    return _first(
        row,
        (
            "normalized_value",
            "value",
            "snippet",
            "text",
            "content",
            "description",
            "summary",
            "v2_summary",
            "v3_summary",
            "candidate_value",
            "candidate_part_number",
        ),
        1200,
    )


def build_typed_record(
    *,
    route: str,
    bucket: str,
    index: int,
    row: Mapping[str, Any],
) -> Dict[str, Any]:
    value = dict(row)
    modality = infer_modality(bucket, value)
    trace = _source_trace(value)
    conflict = bool(
        bucket == "contradictions"
        or value.get("metadata_conflict")
        or value.get("conflict")
        or value.get("contradiction")
    )
    direct = bucket == "direct_evidence"
    guidance = bucket in GUIDANCE_BUCKETS or _truthy(value.get("guidance_only"))
    direct_authority = bool(
        _truthy(value.get("direct_proof_authority"))
        or trace.get("field_name")
    )
    support_allowed = bool(
        direct
        and not guidance
        and not conflict
        and trace.get("ready")
        and direct_authority
    )

    if conflict:
        evidence_class = "conflict"
        authority_class = "unresolved_conflict"
        proof_status = "conflict_unresolved"
        resolution_status = "conflict_unresolved"
    elif direct:
        evidence_class = "direct_source"
        authority_class = (
            "direct_source_authority"
            if any(hint in str(trace.get("field_name") or "").lower() for hint in AUTHORITY_HINTS)
            else "direct_source_record"
        )
        if support_allowed:
            proof_status = "claim_supporting_direct"
            resolution_status = "resolved_source"
        elif trace.get("ready"):
            proof_status = "citation_ready_direct"
            resolution_status = "resolved_source"
        else:
            proof_status = "direct_source_trace_incomplete"
            resolution_status = "source_trace_incomplete"
    elif bucket == "candidate_evidence":
        evidence_class = "candidate_guidance"
        authority_class = "guidance_candidate"
        proof_status = "guidance_only"
        resolution_status = "candidate_unresolved"
    elif bucket == "visual_guidance":
        evidence_class = "visual_guidance"
        authority_class = "guidance_visual"
        proof_status = "guidance_only"
        resolution_status = "guidance_unresolved"
    elif bucket == "semantic_guidance":
        evidence_class = "semantic_guidance"
        authority_class = (
            "guidance_graph"
            if modality == "graph"
            else "guidance_summary"
            if modality == "summary"
            else "guidance_semantic"
        )
        proof_status = "guidance_only"
        resolution_status = "guidance_unresolved"
    else:
        evidence_class = "resolution_metadata"
        authority_class = "resolution_trace_only"
        proof_status = "not_evidence"
        resolution_status = "resolution_trace"

    claim_types = infer_claim_types(
        route=route,
        bucket=bucket,
        row=value,
        modality=modality,
    )
    return {
        "record_id": _stable_id(bucket, index, value),
        "schema_version": SCHEMA_VERSION,
        "source_bucket": bucket,
        "source_index": index,
        "evidence_class": evidence_class,
        "modality": modality,
        "authority_class": authority_class,
        "proof_status": proof_status,
        "resolution_status": resolution_status,
        "claim_types": claim_types,
        "claim_support_allowed": support_allowed,
        "final_answer_eligible": support_allowed,
        "guidance_only": bool(not direct or guidance),
        "conflicted": conflict,
        "source_trace": trace,
        "identity": _identity(value),
        "excerpt": _excerpt(value),
        "quality_signals": {
            "confidence": _first(
                value,
                ("confidence", "score", "ocr_confidence", "mean_confidence"),
                100,
            ),
            "source_truth": _truthy(value.get("source_truth")),
            "citation_ready": _truthy(value.get("citation_ready")),
            "source_trace_ready": _truthy(value.get("source_trace_ready")),
            "direct_proof_authority": _truthy(value.get("direct_proof_authority")),
        },
    }


def validate_typed_evidence_view(
    *,
    records: Sequence[Mapping[str, Any]],
    source_counts: Mapping[str, int],
) -> Dict[str, Any]:
    failures: List[str] = []
    warnings: List[str] = []
    expected = sum(int(source_counts.get(bucket) or 0) for bucket in SOURCE_BUCKETS)
    if len(records) != expected:
        failures.append(f"typed_record_count_mismatch:{len(records)}!={expected}")

    ids = set()
    for index, raw in enumerate(records):
        record = dict(raw)
        missing = sorted(REQUIRED_TYPED_KEYS - set(record))
        if missing:
            failures.append(
                f"record_{index}_missing_fields:" + ",".join(missing)
            )
        record_id = str(record.get("record_id") or "")
        if record_id in ids:
            failures.append(f"duplicate_record_id:{record_id}")
        ids.add(record_id)
        if record.get("guidance_only") and record.get("claim_support_allowed"):
            failures.append(f"guidance_support_violation:{record_id}")
        if record.get("conflicted") and record.get("claim_support_allowed"):
            failures.append(f"conflict_support_violation:{record_id}")
        if record.get("claim_support_allowed"):
            trace = _mapping(record.get("source_trace"))
            if not trace.get("ready"):
                failures.append(f"support_without_source_trace:{record_id}")
            if record.get("source_bucket") != "direct_evidence":
                failures.append(f"support_from_non_direct_bucket:{record_id}")
        if (
            record.get("source_bucket") == "direct_evidence"
            and record.get("proof_status") == "direct_source_trace_incomplete"
        ):
            warnings.append(f"direct_source_trace_incomplete:{record_id}")

    failures = list(dict.fromkeys(failures))
    warnings = list(dict.fromkeys(warnings))
    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "record_count": len(records),
        "expected_record_count": expected,
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "failures": failures,
        "warnings": warnings,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }


def build_typed_evidence_view(
    envelope: Mapping[str, Any],
    *,
    route: Optional[str] = None,
) -> Dict[str, Any]:
    source = dict(envelope)
    effective_route = str(route or source.get("route") or "")
    source_counts = {
        bucket: len(_rows(source.get(bucket)))
        for bucket in SOURCE_BUCKETS
    }
    records: List[Dict[str, Any]] = []
    for bucket in SOURCE_BUCKETS:
        for index, row in enumerate(_rows(source.get(bucket))):
            records.append(
                build_typed_record(
                    route=effective_route,
                    bucket=bucket,
                    index=index,
                    row=row,
                )
            )

    validation = validate_typed_evidence_view(
        records=records,
        source_counts=source_counts,
    )
    class_counts: Dict[str, int] = {}
    modality_counts: Dict[str, int] = {}
    proof_counts: Dict[str, int] = {}
    for record in records:
        for target, key in (
            (class_counts, "evidence_class"),
            (modality_counts, "modality"),
            (proof_counts, "proof_status"),
        ):
            value = str(record.get(key) or "unknown")
            target[value] = target.get(value, 0) + 1

    support_records = [
        record for record in records
        if record.get("claim_support_allowed")
    ]
    guidance_records = [
        record for record in records
        if record.get("guidance_only")
    ]
    conflict_records = [
        record for record in records
        if record.get("conflicted")
    ]
    return {
        "status": STATUS,
        "module": MODULE,
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "quality_status": validation["quality_status"],
        "route": effective_route,
        "records": records,
        "coverage": {
            "source_bucket_counts": source_counts,
            "typed_record_count": len(records),
            "claim_support_allowed_count": len(support_records),
            "guidance_only_count": len(guidance_records),
            "conflict_count": len(conflict_records),
            "authority_reference_count": len(_rows(source.get("authority_evidence"))),
            "class_counts": class_counts,
            "modality_counts": modality_counts,
            "proof_status_counts": proof_counts,
            "legacy_lists_preserved": True,
        },
        "validation": validation,
        "contract": {
            "legacy_compatible": True,
            "typed_view_is_metadata_not_new_evidence": True,
            "claim_support_requires_direct_source_trace": True,
            "candidate_visual_semantic_graph_summary_are_guidance": True,
            "conflicts_block_claim_support": True,
            "executor_and_retrieval_unchanged": True,
            "answer_writer_unchanged": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        },
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def _bool_env(
    environ: Mapping[str, str],
    name: str,
    default: bool = False,
) -> bool:
    raw = str(
        environ.get(name, "1" if default else "0")
    ).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def load_typed_evidence_config(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    return {
        "enabled": _bool_env(
            env,
            "TRACE_NET_H30_TYPED_EVIDENCE_ENABLED",
            False,
        )
    }


def typed_evidence_health(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    config = load_typed_evidence_config(environ)
    return {
        "status": STATUS,
        "quality_status": "PASS",
        "enabled": bool(config.get("enabled")),
        "schema_version": SCHEMA_VERSION,
        "source_buckets": list(SOURCE_BUCKETS),
        "legacy_lists_preserved": True,
        "retrieval_changed": False,
        "ranking_changed": False,
        "answer_writer_changed": False,
        "claim_support_requires_direct_source_trace": True,
        "guidance_never_supports_final_claims": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def install_typed_evidence_envelope(
    module: MutableMapping[str, Any],
) -> None:
    marker = "_TRACE_NET_H30_TYPED_EVIDENCE_ENVELOPE_V1_INSTALLED"
    if module.get(marker):
        return

    runtime_cls = module["CognitiveRuntime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health

    def process_v2(
        self: Any,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        config = load_typed_evidence_config()
        result["typed_evidence_enabled"] = bool(config.get("enabled"))
        if not config.get("enabled"):
            result["typed_evidence_status"] = {
                "quality_status": "SKIPPED",
                "reason": "disabled_by_configuration",
                "schema_version": SCHEMA_VERSION,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            }
        else:
            envelope = result.get("evidence_envelope")
            if isinstance(envelope, Mapping):
                typed = build_typed_evidence_view(
                    envelope,
                    route=str(result.get("route") or ""),
                )
                updated = dict(envelope)
                updated["typed_evidence"] = typed["records"]
                updated["typed_evidence_coverage"] = typed["coverage"]
                updated["typed_evidence_validation"] = typed["validation"]
                updated["typed_evidence_contract"] = typed["contract"]
                result["evidence_envelope"] = updated
                result["typed_evidence_status"] = {
                    "quality_status": typed["quality_status"],
                    "schema_version": typed["schema_version"],
                    "record_count": len(typed["records"]),
                    "claim_support_allowed_count": typed["coverage"][
                        "claim_support_allowed_count"
                    ],
                    "guidance_only_count": typed["coverage"][
                        "guidance_only_count"
                    ],
                    "conflict_count": typed["coverage"]["conflict_count"],
                    "validation": typed["validation"],
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                }
            else:
                result["typed_evidence_status"] = {
                    "quality_status": "FAIL",
                    "reason": "evidence_envelope_missing_or_not_mapping",
                    "schema_version": SCHEMA_VERSION,
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                }

        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["can_answer_directly"] = False
        result["can_prove_claims"] = False
        result["source_truth_mutation_allowed"] = False
        safety = result.get("safety_contract")
        if isinstance(safety, MutableMapping):
            safety["answer_permission"] = False
            safety["final_answer_allowed"] = False
            safety["source_truth_mutation_allowed"] = False
            safety["typed_evidence_is_metadata_only"] = True
        return result

    def health_v2(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        result["typed_evidence_envelope"] = typed_evidence_health()
        result["typed_evidence_enabled"] = bool(
            result["typed_evidence_envelope"].get("enabled")
        )
        result["typed_evidence_schema_version"] = SCHEMA_VERSION
        result["typed_evidence_legacy_lists_preserved"] = True
        result["typed_evidence_changes_retrieval"] = False
        result["typed_evidence_changes_ranking"] = False
        result["typed_evidence_changes_answer_writer"] = False
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    runtime_cls.process = process_v2
    runtime_cls.health = health_v2
    module[marker] = True
