#!/usr/bin/env python3
"""TRACE-Net visual linked-part nomenclature enricher v1.

This module is intentionally evidence-only.  It does not call LLaVA, mutate
source truth, write to databases, or grant answer permission.  It takes the
already-built image visual evidence pack and tries to fill missing linked-part
nomenclature/description from trusted OCR/table evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STATUS = "TRACE_NET_VISUAL_PART_NOMENCLATURE_ENRICHER_BUILT"
CHECK_STATUS = "TRACE_NET_VISUAL_PART_NOMENCLATURE_ENRICHER_QUALITY_CHECKED"
SCHEMA_VERSION = "trace_net_visual_part_nomenclature_enricher_v1"

PART_RE = re.compile(r"\b\d{2,4}-\d{3,6}-\d{3,4}\b")
FILENAME_RE = re.compile(r"^\d{6,}\.(?:tif|tiff|png|jpg|jpeg)$", re.I)
MOSTLY_NUMERIC_RE = re.compile(r"^[\d\s\-./()]+$")

PART_FIELD_HINTS = (
    "part_number",
    "covered_part_number",
    "ipl_part_number",
    "partno",
    "part_no",
    "pn",
)
DESC_FIELD_HINTS = (
    "nomenclature",
    "description",
    "desc",
    "part_name",
    "item_name",
    "name",
    "title",
)
BAD_DESC_FIELD_HINTS = (
    "source_member",
    "tiff",
    "filename",
    "file_name",
    "member",
    "page_id",
    "page_number",
    "part_number",
    "figure",
    "quantity",
    "item",
)


def _as_path(value: Any) -> Path:
    if isinstance(value, Path):
        return value
    return Path(str(value))


def _load_json(path: Any, *, optional: bool = False) -> Dict[str, Any]:
    p = _as_path(path)
    if optional and (not str(path) or not p.exists()):
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = _as_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _iter_records(data: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for key in ("records", "evidence_documents", "exact_search_documents", "documents", "results"):
        value = data.get(key)
        if isinstance(value, list):
            for record in value:
                if isinstance(record, Mapping):
                    yield record


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_part(value: Any) -> str:
    text = str(value or "").upper().strip()
    match = PART_RE.search(text)
    return match.group(0) if match else ""


def _hash_record(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8", errors="ignore"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def _field_name(record: Mapping[str, Any]) -> str:
    return _normalize_text(record.get("field_name") or record.get("field") or record.get("key")).lower()


def _value(record: Mapping[str, Any]) -> str:
    for key in ("normalized_value", "raw_value", "value", "text", "content", "search_text"):
        if record.get(key) not in (None, ""):
            return _normalize_text(record.get(key))
    return ""


def _source_trace(record: Mapping[str, Any]) -> Dict[str, Any]:
    st = record.get("source_trace")
    if isinstance(st, Mapping):
        return dict(st)
    return {
        "page_id": record.get("page_id"),
        "table_id": record.get("table_id"),
        "row_index": record.get("row_index"),
        "source_module": record.get("source_module"),
        "evidence_id": record.get("evidence_id") or record.get("id"),
    }


def _looks_like_bad_description(value: str) -> bool:
    v = _normalize_text(value)
    if not v:
        return True
    if FILENAME_RE.match(v):
        return True
    if PART_RE.fullmatch(v.upper()):
        return True
    if MOSTLY_NUMERIC_RE.match(v):
        return True
    if len(v) < 3:
        return True
    if not re.search(r"[A-Za-z]", v):
        return True
    low = v.lower()
    if low in {"none", "null", "n/a", "na", "unknown"}:
        return True
    if low.endswith((".tif", ".tiff", ".png", ".jpg", ".jpeg")):
        return True
    return False


def _is_part_field(field_name: str, value: str) -> bool:
    if _normalize_part(value):
        return True
    return any(hint in field_name for hint in PART_FIELD_HINTS)


def _is_desc_field(field_name: str, value: str) -> bool:
    if _looks_like_bad_description(value):
        return False
    if any(bad in field_name for bad in BAD_DESC_FIELD_HINTS):
        return False
    return any(hint in field_name for hint in DESC_FIELD_HINTS)


def _desc_score(field_name: str, value: str, same_page: bool) -> Tuple[int, int, int]:
    score = 0
    if same_page:
        score += 20
    if "nomenclature" in field_name:
        score += 30
    if "description" in field_name or field_name == "desc":
        score += 25
    if "part_name" in field_name or "item_name" in field_name:
        score += 20
    if any(word in value.upper() for word in ("ASSY", "ASSEMBLY", "STRUCTURE", "BRACKET", "LEG", "SUPPORT", "PANEL", "COVER", "FITTING")):
        score += 8
    if len(value) >= 8:
        score += 5
    return (score, min(len(value), 120), -len(value))


@dataclass
class TrustedRow:
    row_key: str
    source_artifact: str
    page_id: str = ""
    page_number: Optional[int] = None
    table_id: str = ""
    row_index: Any = None
    part_numbers: List[str] = field(default_factory=list)
    descriptions: List[Dict[str, Any]] = field(default_factory=list)
    field_values: Dict[str, List[str]] = field(default_factory=dict)
    source_traces: List[Dict[str, Any]] = field(default_factory=list)

    def add_record(self, record: Mapping[str, Any], source_artifact: str) -> None:
        fname = _field_name(record)
        value = _value(record)
        if not value:
            return
        self.field_values.setdefault(fname or "value", []).append(value)
        self.source_traces.append(_source_trace(record))
        part = _normalize_part(value)
        if part and part not in self.part_numbers:
            self.part_numbers.append(part)
        if _is_desc_field(fname, value):
            self.descriptions.append({
                "field_name": fname,
                "value": value,
                "source_trace": _source_trace(record),
                "source_artifact": source_artifact,
            })


def _page_number_from_page_id(page_id: Any) -> Optional[int]:
    text = str(page_id or "")
    m = re.search(r"p(\d{3,6})$", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,6})", text)
    if m:
        return int(m.group(1))
    return None


def _trusted_rows_from_artifact(path: Path) -> List[TrustedRow]:
    if not path.exists():
        return []
    data = _load_json(path)
    grouped: Dict[Tuple[str, str, str], TrustedRow] = {}
    standalone: List[TrustedRow] = []
    source_artifact = str(path)
    for rec in _iter_records(data):
        page_id = _normalize_text(rec.get("page_id") or rec.get("source_trace", {}).get("page_id") if isinstance(rec.get("source_trace"), Mapping) else rec.get("page_id"))
        table_id = _normalize_text(rec.get("table_id") or (rec.get("source_trace", {}) or {}).get("table_id") if isinstance(rec.get("source_trace"), Mapping) else rec.get("table_id"))
        row_index = rec.get("row_index")
        page_number = rec.get("page_number")
        if page_number is None:
            page_number = _page_number_from_page_id(page_id)
        value = _value(rec)
        part = _normalize_part(value or json.dumps(rec, ensure_ascii=False))
        has_row_shape = bool(page_id or table_id or row_index is not None)
        if has_row_shape:
            key = (page_id, table_id, str(row_index))
            if key not in grouped:
                grouped[key] = TrustedRow(
                    row_key="row_" + _hash_record(source_artifact, page_id, table_id, row_index),
                    source_artifact=source_artifact,
                    page_id=page_id,
                    page_number=page_number,
                    table_id=table_id,
                    row_index=row_index,
                )
            grouped[key].add_record(rec, source_artifact)
        elif part:
            row = TrustedRow(
                row_key="standalone_" + _hash_record(source_artifact, part, value),
                source_artifact=source_artifact,
                page_id=page_id,
                page_number=page_number,
            )
            row.add_record(rec, source_artifact)
            standalone.append(row)
    rows = list(grouped.values()) + standalone
    return [r for r in rows if r.part_numbers]


def _candidate_rows(rows: Sequence[TrustedRow], part_number: str, visual_page_id: str, visual_page_number: Optional[int]) -> List[TrustedRow]:
    matches = [r for r in rows if part_number in r.part_numbers]
    if not matches:
        return []

    def key(row: TrustedRow) -> Tuple[int, int, str]:
        same_page_id = int(bool(visual_page_id and row.page_id == visual_page_id))
        same_page_no = int(bool(visual_page_number is not None and row.page_number == visual_page_number))
        has_desc = int(bool(row.descriptions))
        return (same_page_id + same_page_no, has_desc, row.row_key)

    return sorted(matches, key=key, reverse=True)


def _choose_description(rows: Sequence[TrustedRow], part_number: str, visual_page_id: str, visual_page_number: Optional[int]) -> Dict[str, Any]:
    candidates: List[Tuple[Tuple[int, int, int], TrustedRow, Dict[str, Any]]] = []
    for row in rows:
        same_page = bool((visual_page_id and row.page_id == visual_page_id) or (visual_page_number is not None and row.page_number == visual_page_number))
        for desc in row.descriptions:
            value = _normalize_text(desc.get("value"))
            if _looks_like_bad_description(value):
                continue
            candidates.append((_desc_score(desc.get("field_name", ""), value, same_page), row, desc))
    if not candidates:
        return {
            "description": "",
            "description_status": "missing",
            "description_quality": "missing",
            "description_source_trace": {},
            "description_source_artifact": "",
            "trusted_row_key": rows[0].row_key if rows else "",
        }
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, row, desc = candidates[0]
    return {
        "description": _normalize_text(desc.get("value")),
        "description_status": "enriched",
        "description_quality": "trusted_table_or_ocr_field",
        "description_source_trace": desc.get("source_trace") or {},
        "description_source_artifact": desc.get("source_artifact") or row.source_artifact,
        "trusted_row_key": row.row_key,
    }


def _safety_summary(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    keys = [
        "unsafe_record",
        "answer_permission",
        "source_truth_mutation_allowed",
        "postgres_write_attempt",
        "qdrant_write_attempt",
        "opensearch_write_attempt",
        "opensearch_upload_attempt",
    ]
    out: Dict[str, int] = {}
    for key in keys:
        out[key + "_count"] = sum(1 for r in records if bool(r.get(key)))
    out["write_attempt_count"] = (
        out["postgres_write_attempt_count"]
        + out["qdrant_write_attempt_count"]
        + out["opensearch_write_attempt_count"]
        + out["opensearch_upload_attempt_count"]
    )
    return out


def build_visual_part_nomenclature_enricher(
    *,
    image_visual_evidence_pack: Any,
    trusted_evidence_artifacts: Sequence[Any] = (),
    table_route_evidence_packager: Any = "",
    table_exact_search_adapter: Any = "",
    output_dir: Any,
    min_linked_visual_parts: int = 1,
    min_description_enriched: int = 0,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    out_dir = _as_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pack_path = _as_path(image_visual_evidence_pack)
    pack = _load_json(pack_path)

    artifact_paths: List[Path] = []
    for item in trusted_evidence_artifacts or []:
        if item:
            artifact_paths.append(_as_path(item))
    for item in (table_route_evidence_packager, table_exact_search_adapter):
        if item:
            p = _as_path(item)
            if p not in artifact_paths:
                artifact_paths.append(p)

    trusted_rows: List[TrustedRow] = []
    for artifact in artifact_paths:
        trusted_rows.extend(_trusted_rows_from_artifact(artifact))

    records: List[Dict[str, Any]] = []
    missing_records: List[Dict[str, Any]] = []
    pack_records = list(_iter_records(pack))
    for rec in pack_records:
        linked = bool(rec.get("linked") or rec.get("linked_part_number"))
        part_number = _normalize_part(rec.get("linked_part_number"))
        if not linked or not part_number:
            continue
        visual_page_id = _normalize_text(rec.get("page_id"))
        visual_page_number = rec.get("page_number")
        try:
            visual_page_number = int(visual_page_number) if visual_page_number not in (None, "") else None
        except Exception:
            visual_page_number = None
        candidates = _candidate_rows(trusted_rows, part_number, visual_page_id, visual_page_number)
        chosen = _choose_description(candidates, part_number, visual_page_id, visual_page_number)
        prior_description = _normalize_text(rec.get("linked_description"))
        final_description = chosen["description"] or ("" if _looks_like_bad_description(prior_description) else prior_description)
        description_status = chosen["description_status"] if final_description == chosen["description"] and final_description else ("existing" if final_description else "missing")
        enriched = dict(rec)
        enriched.update({
            "schema_version": SCHEMA_VERSION,
            "enrichment_id": "visual_part_nomenclature_enrichment_" + _hash_record(rec.get("citation_label"), part_number, final_description),
            "source_visual_evidence_pack": str(pack_path),
            "source_visual_citation_label": rec.get("citation_label", ""),
            "linked_part_number": part_number,
            "original_linked_description": prior_description,
            "enriched_description": final_description,
            "linked_description": final_description,
            "description_status": description_status,
            "description_quality": chosen.get("description_quality") if final_description else "missing",
            "description_source_trace": chosen.get("description_source_trace") if final_description else {},
            "description_source_artifact": chosen.get("description_source_artifact") if final_description else "",
            "trusted_candidate_row_count": len(candidates),
            "trusted_row_key": chosen.get("trusted_row_key", ""),
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "unsafe_record": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "retrieval_only": True,
        })
        records.append(enriched)
        if not final_description:
            missing_records.append({
                "citation_label": rec.get("citation_label"),
                "page_id": visual_page_id,
                "page_number": visual_page_number,
                "figure": rec.get("figure"),
                "callout": rec.get("callout"),
                "linked_part_number": part_number,
                "trusted_candidate_row_count": len(candidates),
                "reason": "no_trusted_description_field_found",
            })

    enriched_count = sum(1 for r in records if r.get("description_status") in {"enriched", "existing"})
    source_trace_ready_count = sum(1 for r in records if bool(r.get("source_trace_ready") or r.get("citation_ready")))
    summary: Dict[str, Any] = {
        "visual_part_nomenclature_record_count": len(records),
        "linked_visual_part_count": len(records),
        "trusted_evidence_artifact_count": len(artifact_paths),
        "trusted_row_count": len(trusted_rows),
        "description_enriched_count": sum(1 for r in records if r.get("description_status") == "enriched"),
        "description_existing_count": sum(1 for r in records if r.get("description_status") == "existing"),
        "description_available_count": enriched_count,
        "description_missing_count": sum(1 for r in records if not r.get("linked_description")),
        "source_trace_ready_count": source_trace_ready_count,
        "ready_for_visual_answer_upgrade": enriched_count >= min_description_enriched and len(records) >= min_linked_visual_parts,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": 0,
    }
    failures: List[str] = []
    if len(records) < min_linked_visual_parts:
        failures.append(f"linked visual part count below minimum: {len(records)} < {min_linked_visual_parts}")
    if summary["description_available_count"] < min_description_enriched:
        failures.append(f"description available count below minimum: {summary['description_available_count']} < {min_description_enriched}")
    if source_trace_ready_count < min_source_trace_ready:
        failures.append(f"source trace ready count below minimum: {source_trace_ready_count} < {min_source_trace_ready}")
    if summary["unsafe_record_count"] > max_unsafe:
        failures.append("unsafe record count above maximum")
    if summary["answer_permission_count"] > max_answer_permission:
        failures.append("answer permission count above maximum")
    if summary["source_truth_mutation_allowed_count"] > max_source_truth_mutation_allowed:
        failures.append("source truth mutation allowed count above maximum")
    if summary["write_attempt_count"] > max_write_attempts:
        failures.append("write attempt count above maximum")

    result: Dict[str, Any] = {
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "schema_version": SCHEMA_VERSION,
        "module": "trace_net_visual_part_nomenclature_enricher_v1",
        "inputs": {
            "image_visual_evidence_pack": str(pack_path),
            "trusted_evidence_artifacts": [str(p) for p in artifact_paths],
        },
        "summary": summary,
        "failures": failures,
        "records": records,
        "missing_description_records": missing_records,
        "safety_contract": {
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
        "notes": [
            "LLaVA observations are not used as proof for part identity.",
            "Descriptions are copied only from trusted table/OCR/exact evidence fields when field names and values pass safety filters.",
            "Missing descriptions do not mutate source truth; they remain reportable gaps for later extraction work.",
        ],
    }

    _write_json(out_dir / "trace_net_visual_part_nomenclature_enricher_v1.json", result)
    _write_json(out_dir / "trace_net_visual_part_nomenclature_missing_report_v1.json", {"records": missing_records, "summary": summary})
    _write_csv(out_dir / "trace_net_visual_part_nomenclature_enriched_records_v1.csv", records)
    check = check_visual_part_nomenclature_enricher(
        enricher=out_dir / "trace_net_visual_part_nomenclature_enricher_v1.json",
        output=out_dir / "trace_net_visual_part_nomenclature_enricher_v1_quality_check.json",
        require_quality_pass=False,
        min_linked_visual_parts=min_linked_visual_parts,
        min_description_enriched=min_description_enriched,
        min_source_trace_ready=min_source_trace_ready,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    result["paths"] = {
        "enricher": str(out_dir / "trace_net_visual_part_nomenclature_enricher_v1.json"),
        "quality_check": str(out_dir / "trace_net_visual_part_nomenclature_enricher_v1_quality_check.json"),
        "missing_report": str(out_dir / "trace_net_visual_part_nomenclature_missing_report_v1.json"),
        "records_csv": str(out_dir / "trace_net_visual_part_nomenclature_enriched_records_v1.csv"),
    }
    result["quality_check_summary"] = check.get("summary", {})
    _write_json(out_dir / "trace_net_visual_part_nomenclature_enricher_v1.json", result)
    return result


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "enrichment_id", "source_visual_citation_label", "page_number", "page_id", "figure", "callout",
        "linked_part_number", "linked_description", "description_status", "description_quality",
        "link_confidence", "proof_strength", "source_trace_ready", "citation_ready", "trusted_candidate_row_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, "") for k in fields})


def check_visual_part_nomenclature_enricher(
    *,
    enricher: Any,
    output: Any = "",
    require_quality_pass: bool = False,
    min_linked_visual_parts: int = 1,
    min_description_enriched: int = 0,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _load_json(enricher)
    s = data.get("summary", {}) if isinstance(data.get("summary"), Mapping) else {}
    failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_status is not PASS")
    if int(s.get("linked_visual_part_count", 0)) < min_linked_visual_parts:
        failures.append(f"linked visual part count below minimum: {s.get('linked_visual_part_count', 0)} < {min_linked_visual_parts}")
    if int(s.get("description_available_count", 0)) < min_description_enriched:
        failures.append(f"description available count below minimum: {s.get('description_available_count', 0)} < {min_description_enriched}")
    if int(s.get("source_trace_ready_count", 0)) < min_source_trace_ready:
        failures.append(f"source trace ready count below minimum: {s.get('source_trace_ready_count', 0)} < {min_source_trace_ready}")
    if int(s.get("unsafe_record_count", 0)) > max_unsafe:
        failures.append("unsafe record count above maximum")
    if int(s.get("answer_permission_count", 0)) > max_answer_permission:
        failures.append("answer permission count above maximum")
    if int(s.get("source_truth_mutation_allowed_count", 0)) > max_source_truth_mutation_allowed:
        failures.append("source truth mutation allowed count above maximum")
    if int(s.get("write_attempt_count", 0)) > max_write_attempts:
        failures.append("write attempt count above maximum")
    result = {
        "status": CHECK_STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "source_status": data.get("status"),
        "source_quality_status": data.get("quality_status"),
        "summary": dict(s),
        "failures": failures,
    }
    if output:
        _write_json(output, result)
    return result


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net visual part nomenclature enrichment v1")
    sub = parser.add_subparsers(dest="cmd")

    build = sub.add_parser("build")
    build.add_argument("--image-visual-evidence-pack", required=True)
    build.add_argument("--trusted-evidence-artifact", action="append", default=[])
    build.add_argument("--table-route-evidence-packager", default="")
    build.add_argument("--table-exact-search-adapter", default="")
    build.add_argument("--output-dir", required=True)
    build.add_argument("--min-linked-visual-parts", type=int, default=1)
    build.add_argument("--min-description-enriched", type=int, default=0)
    build.add_argument("--min-source-trace-ready", type=int, default=1)
    build.add_argument("--max-unsafe", type=int, default=0)
    build.add_argument("--max-answer-permission", type=int, default=0)
    build.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    build.add_argument("--max-write-attempts", type=int, default=0)

    check = sub.add_parser("check")
    check.add_argument("--enricher", required=True)
    check.add_argument("--output", required=True)
    check.add_argument("--require-quality-pass", action="store_true")
    check.add_argument("--min-linked-visual-parts", type=int, default=1)
    check.add_argument("--min-description-enriched", type=int, default=0)
    check.add_argument("--min-source-trace-ready", type=int, default=1)
    check.add_argument("--max-unsafe", type=int, default=0)
    check.add_argument("--max-answer-permission", type=int, default=0)
    check.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    check.add_argument("--max-write-attempts", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.cmd:
        args.cmd = "build"
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    if args.cmd == "check":
        result = check_visual_part_nomenclature_enricher(
            enricher=args.enricher,
            output=args.output,
            require_quality_pass=args.require_quality_pass,
            min_linked_visual_parts=args.min_linked_visual_parts,
            min_description_enriched=args.min_description_enriched,
            min_source_trace_ready=args.min_source_trace_ready,
            max_unsafe=args.max_unsafe,
            max_answer_permission=args.max_answer_permission,
            max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
            max_write_attempts=args.max_write_attempts,
        )
        s = result.get("summary", {})
        print(f"status={result.get('status')}")
        print(f"quality_status={result.get('quality_status')}")
        print(f"linked_visual_part_count={s.get('linked_visual_part_count', 0)}")
        print(f"description_available_count={s.get('description_available_count', 0)}")
        print(f"description_enriched_count={s.get('description_enriched_count', 0)}")
        print(f"source_trace_ready_count={s.get('source_trace_ready_count', 0)}")
        if result.get("quality_status") != "PASS":
            for failure in result.get("failures", []):
                print(f"failure={failure}")
        return 0 if result.get("quality_status") == "PASS" else 1

    result = build_visual_part_nomenclature_enricher(
        image_visual_evidence_pack=args.image_visual_evidence_pack,
        trusted_evidence_artifacts=args.trusted_evidence_artifact,
        table_route_evidence_packager=args.table_route_evidence_packager,
        table_exact_search_adapter=args.table_exact_search_adapter,
        output_dir=args.output_dir,
        min_linked_visual_parts=args.min_linked_visual_parts,
        min_description_enriched=args.min_description_enriched,
        min_source_trace_ready=args.min_source_trace_ready,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"linked_visual_part_count={s.get('linked_visual_part_count', 0)}")
    print(f"description_available_count={s.get('description_available_count', 0)}")
    print(f"description_enriched_count={s.get('description_enriched_count', 0)}")
    print(f"description_missing_count={s.get('description_missing_count', 0)}")
    print(f"source_trace_ready_count={s.get('source_trace_ready_count', 0)}")
    print(f"ready_for_visual_answer_upgrade={s.get('ready_for_visual_answer_upgrade')}")
    print(f"unsafe_record_count={s.get('unsafe_record_count', 0)}")
    print(f"answer_permission_count={s.get('answer_permission_count', 0)}")
    print(f"source_truth_mutation_allowed_count={s.get('source_truth_mutation_allowed_count', 0)}")
    print(f"write_attempt_count={s.get('write_attempt_count', 0)}")
    print(f"enricher={result.get('paths', {}).get('enricher')}")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
