from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_engineering_answer_context_pack_v1"
VERSION = "v1"
STATUS = "TRACE_NET_ENGINEERING_ANSWER_CONTEXT_PACK_BUILT"
CHECK_STATUS = "TRACE_NET_ENGINEERING_ANSWER_CONTEXT_PACK_QUALITY_CHECKED"

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
FIGURE_RE = re.compile(r"\bfig(?:ure)?\.?\s*([0-9]{1,4}[A-Z]?)\b", re.IGNORECASE)

FORBIDDEN_DEFAULTS = [
    "LLaVA-only part identity",
    "effectivity",
    "fit",
    "installation safety",
    "interchangeability",
    "replacement approval",
    "summary-only figure proof",
]


def _path(p: Any) -> Path:
    return p if isinstance(p, Path) else Path(str(p))


def _load_json(path: Any) -> Dict[str, Any]:
    p = _path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {p}")
    return data


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _norm_str(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm_str(value).lower()


def _first_record(data: Mapping[str, Any]) -> Dict[str, Any]:
    records = data.get("records")
    if isinstance(records, list) and records:
        r = records[0]
        return dict(r) if isinstance(r, dict) else {}
    # tolerate direct planner-shaped JSON in tests / future wrappers
    return dict(data) if isinstance(data, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _entity_sets(planner_record: Mapping[str, Any]) -> Tuple[set, set, set]:
    entities = planner_record.get("entities") or {}
    if not isinstance(entities, dict):
        entities = {}
    figures = {str(x).strip().lstrip("0") or "0" for x in _as_list(entities.get("figures")) if str(x).strip()}
    parts = {str(x).strip().upper() for x in _as_list(entities.get("part_numbers")) if str(x).strip()}
    items = {str(x).strip().lstrip("0") or "0" for x in _as_list(entities.get("items")) if str(x).strip()}
    return figures, parts, items


def _record_matches_visual(record: Mapping[str, Any], figures: set, parts: set, items: set) -> bool:
    rec_figure = _norm_str(record.get("figure")).lstrip("0") or _norm_str(record.get("figure"))
    rec_part = _norm_str(record.get("linked_part_number") or record.get("part_number")).upper()
    rec_callout = _norm_str(record.get("callout") or record.get("item")).lstrip("0") or _norm_str(record.get("callout") or record.get("item"))
    if figures and rec_figure in figures:
        if items:
            return rec_callout in items or not rec_callout
        return True
    if parts and rec_part in parts:
        return True
    if not figures and not parts and not items:
        return bool(record.get("linked") and rec_part)
    return False


def _record_matches_ocr(record: Mapping[str, Any], figures: set, parts: set, visual_parts: set) -> bool:
    rec_figure = _norm_str(record.get("figure")).lstrip("0") or _norm_str(record.get("figure"))
    rec_part = _norm_str(record.get("linked_part_number") or record.get("part_number")).upper()
    all_parts = set(parts) | set(visual_parts)
    if figures and rec_figure in figures:
        return True
    if all_parts and rec_part in all_parts:
        return True
    return False


def _truthy(value: Any) -> bool:
    return bool(value is True or str(value).lower() == "true")


def _citation_label(prefix: str, value: Any, index: int) -> str:
    val = _norm_str(value)
    if val:
        return val
    return f"{prefix}{index}"


def _dedupe_context(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for r in records:
        key = (
            r.get("context_type"),
            r.get("citation_label"),
            r.get("page_id"),
            r.get("page_number"),
            r.get("figure"),
            r.get("part_number"),
            r.get("nomenclature"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _guidance_context_from_planner(planner_record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, g in enumerate(_as_list(planner_record.get("guidance_pages")), 1):
        if not isinstance(g, dict):
            continue
        out.append({
            "context_type": "v2_summary_guidance",
            "guidance_id": f"G{i}",
            "page_id": g.get("page_id"),
            "page_number": g.get("page_number"),
            "route_label": g.get("route_label"),
            "summary_text": g.get("summary_text", ""),
            "detected_figures": g.get("detected_figures", []),
            "detected_part_numbers": g.get("detected_part_numbers", []),
            "detected_topics": g.get("detected_topics", []),
            "guidance_score": g.get("guidance_score", 0),
            "guidance_reasons": g.get("guidance_reasons", []),
            "guidance_only": True,
            "proof_eligible": False,
            "source_trace_ready": bool(g.get("source_trace_ready", True)),
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        })
    return out


def _visual_proof_context(image_pack: Optional[Mapping[str, Any]], figures: set, parts: set, items: set) -> Tuple[List[Dict[str, Any]], set]:
    if not image_pack:
        return [], set()
    records = image_pack.get("records") or []
    out: List[Dict[str, Any]] = []
    visual_parts: set = set()
    for idx, r in enumerate(records, 1):
        if not isinstance(r, dict):
            continue
        if not _record_matches_visual(r, figures, parts, items):
            continue
        part = _norm_str(r.get("linked_part_number") or r.get("part_number")).upper()
        if part:
            visual_parts.add(part)
        nomenclature = _norm_str(r.get("linked_nomenclature") or r.get("linked_description"))
        out.append({
            "context_type": "visual_figure_link",
            "citation_label": _citation_label("V", r.get("citation_label"), idx),
            "page_id": r.get("page_id"),
            "page_number": r.get("page_number"),
            "figure": r.get("figure"),
            "callout": r.get("callout", ""),
            "part_number": part,
            "nomenclature": nomenclature,
            "nomenclature_confidence": r.get("linked_nomenclature_confidence") or r.get("linked_description_quality"),
            "proof_source": r.get("proof_source") or "image_visual_evidence_pack",
            "proof_strength": r.get("proof_strength") or "linked_visual_evidence",
            "source_trace_ready": bool(r.get("source_trace_ready")),
            "citation_ready": bool(r.get("citation_ready", r.get("source_trace_ready"))),
            "limitations": r.get("limitations", []),
            "guidance_only": False,
            "proof_eligible": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        })
    return _dedupe_context(out), visual_parts


def _ocr_nomenclature_context(ocr_pack: Optional[Mapping[str, Any]], figures: set, parts: set, visual_parts: set) -> List[Dict[str, Any]]:
    if not ocr_pack:
        return []
    records = ocr_pack.get("records") or []
    out: List[Dict[str, Any]] = []
    for idx, r in enumerate(records, 1):
        if not isinstance(r, dict):
            continue
        if not _record_matches_ocr(r, figures, parts, visual_parts):
            continue
        nomenclature = _norm_str(r.get("selected_nomenclature") or r.get("nomenclature"))
        if not nomenclature:
            continue
        part = _norm_str(r.get("linked_part_number") or r.get("part_number")).upper()
        out.append({
            "context_type": "ocr_nomenclature",
            "citation_label": f"O{idx}",
            "source_visual_citation_label": r.get("source_visual_citation_label"),
            "page_id": r.get("selected_ocr_page_id") or r.get("ocr_page_id") or r.get("page_id"),
            "page_number": r.get("selected_ocr_page_number") or r.get("ocr_page_number") or r.get("page_number"),
            "figure": r.get("figure"),
            "part_number": part,
            "nomenclature": nomenclature,
            "nomenclature_confidence": r.get("selected_nomenclature_confidence") or r.get("confidence"),
            "extraction_rule": r.get("selected_extraction_rule"),
            "score_reason": r.get("selected_score_reason"),
            "line_text": r.get("selected_line_text") or r.get("line_text"),
            "proof_source": "raw_ocr_nomenclature_window_extractor",
            "proof_strength": "ocr_backed_nomenclature",
            "source_trace_ready": bool(r.get("source_trace_ready")),
            "citation_ready": bool(r.get("source_trace_ready")),
            "guidance_only": False,
            "proof_eligible": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        })
    return _dedupe_context(out)


def _maybe_table_context(table_pack: Optional[Mapping[str, Any]], figures: set, parts: set, visual_parts: set, max_records: int = 12) -> List[Dict[str, Any]]:
    if not table_pack:
        return []
    records = table_pack.get("records") or table_pack.get("evidence_documents") or table_pack.get("exact_search_documents") or []
    wanted_parts = set(parts) | set(visual_parts)
    if not wanted_parts:
        return []
    out: List[Dict[str, Any]] = []
    for idx, r in enumerate(records, 1):
        if not isinstance(r, dict):
            continue
        blob = json.dumps(r, ensure_ascii=False).upper()
        matched = [p for p in wanted_parts if p and p in blob]
        if not matched:
            continue
        field = r.get("field_name") or r.get("field_role") or r.get("field") or "table_field"
        value = r.get("normalized_value") or r.get("raw_value") or r.get("display_value") or r.get("search_text") or ""
        out.append({
            "context_type": "table_ocr_proof",
            "citation_label": f"T{len(out)+1}",
            "page_id": r.get("page_id") or r.get("source_page_id"),
            "page_number": r.get("page_number") or r.get("source_page_number"),
            "table_id": r.get("table_id") or (r.get("source_trace") or {}).get("table_id"),
            "row_index": r.get("row_index"),
            "field_name": field,
            "value": value,
            "part_number": matched[0],
            "proof_source": "trusted_table_or_exact_search_artifact",
            "proof_strength": "trusted_table_ocr_evidence",
            "source_trace_ready": bool(r.get("source_trace_ready", r.get("citation_ready", True))),
            "citation_ready": bool(r.get("citation_ready", r.get("source_trace_ready", True))),
            "guidance_only": False,
            "proof_eligible": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        })
        if len(out) >= max_records:
            break
    return _dedupe_context(out)



def _exact_part_context(source_pack: Optional[Mapping[str, Any]], parts: set, *, source_name: str, prefix: str, max_records: int = 8) -> List[Dict[str, Any]]:
    """Build direct exact-part lookup proof from trusted table/exact artifacts.

    This is intentionally conservative: it only creates proof records when the exact
    requested part number appears in a trusted artifact record. It does not infer
    effectivity, fit, interchangeability, or installation approval.
    """
    if not source_pack or not parts:
        return []
    records = source_pack.get("records") or source_pack.get("evidence_documents") or source_pack.get("exact_search_documents") or []
    out: List[Dict[str, Any]] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        blob = json.dumps(r, ensure_ascii=False).upper()
        matched = [part for part in parts if part and part in blob]
        if not matched:
            continue
        value = r.get("normalized_value") or r.get("raw_value") or r.get("display_value") or r.get("search_text") or r.get("value") or ""
        field = r.get("field_name") or r.get("field_role") or r.get("field") or "exact_part_match"
        source_trace = r.get("source_trace") if isinstance(r.get("source_trace"), dict) else {}
        out.append({
            "context_type": "exact_part_evidence",
            "citation_label": f"{prefix}{len(out)+1}",
            "page_id": r.get("page_id") or r.get("source_page_id") or source_trace.get("page_id"),
            "page_number": r.get("page_number") or r.get("source_page_number") or source_trace.get("page_number"),
            "table_id": r.get("table_id") or source_trace.get("table_id"),
            "row_index": r.get("row_index") or source_trace.get("row_index"),
            "field_name": field,
            "value": value,
            "part_number": matched[0],
            "nomenclature": r.get("nomenclature") or r.get("description") or r.get("part_description") or "",
            "proof_source": source_name,
            "proof_strength": "exact_part_source_match",
            "source_trace_ready": bool(r.get("source_trace_ready", r.get("citation_ready", True))),
            "citation_ready": bool(r.get("citation_ready", r.get("source_trace_ready", True))),
            "guidance_only": False,
            "proof_eligible": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        })
        if len(out) >= max_records:
            break
    return _dedupe_context(out)

def _answer_constraints(planner_record: Mapping[str, Any]) -> Dict[str, Any]:
    task = planner_record.get("task_type") or "unknown"
    may_claim = []
    if task == "visual_part_identification":
        may_claim = [
            "figure/page link when supported by visual evidence",
            "linked part number when supported by OCR/table/figure proof",
            "OCR-backed nomenclature when source-trace-ready OCR evidence is present",
        ]
    elif task == "exact_part_lookup":
        may_claim = [
            "part number appears in source evidence",
            "source page/citation locations",
            "nomenclature only when OCR/table evidence supports it",
        ]
    else:
        may_claim = [
            "claims supported by source-trace-ready proof_context records",
            "guidance summaries may frame the search but not prove facts",
        ]
    forbidden = planner_record.get("forbidden_claims") or FORBIDDEN_DEFAULTS
    return {
        "answer_style": planner_record.get("answer_style") or "engineering_brain",
        "may_claim": may_claim,
        "may_not_claim": list(dict.fromkeys([str(x) for x in forbidden] + [
            "summary-only proof",
            "unsupported effectivity",
            "unsupported interchangeability",
            "unsupported installation or safety approval",
        ])),
        "summary_guidance_policy": planner_record.get("summary_guidance_policy") or "v2 summaries may guide route planning and answer framing, but must not be used as proof",
    }


def _quality_status(summary: Mapping[str, Any], *, require_quality_pass: bool = False, min_guidance_context: int = 0,
                    min_proof_context: int = 1, min_source_trace_ready: int = 1, max_unsafe: int = 0,
                    max_answer_permission: int = 0, max_source_truth_mutation_allowed: int = 0,
                    max_write_attempts: int = 0) -> Tuple[str, List[str]]:
    failures: List[str] = []
    if _safe_int(summary.get("guidance_context_count")) < min_guidance_context:
        failures.append(f"guidance_context_count below minimum: {summary.get('guidance_context_count')} < {min_guidance_context}")
    if _safe_int(summary.get("proof_context_count")) < min_proof_context:
        failures.append(f"proof_context_count below minimum: {summary.get('proof_context_count')} < {min_proof_context}")
    if _safe_int(summary.get("source_trace_ready_count")) < min_source_trace_ready:
        failures.append(f"source_trace_ready_count below minimum: {summary.get('source_trace_ready_count')} < {min_source_trace_ready}")
    if _safe_int(summary.get("summary_used_as_proof_count")) != 0:
        failures.append("summary_used_as_proof_count is not zero")
    if _safe_int(summary.get("unsafe_record_count")) > max_unsafe:
        failures.append("unsafe_record_count above maximum")
    if _safe_int(summary.get("answer_permission_count")) > max_answer_permission:
        failures.append("answer_permission_count above maximum")
    if _safe_int(summary.get("source_truth_mutation_allowed_count")) > max_source_truth_mutation_allowed:
        failures.append("source_truth_mutation_allowed_count above maximum")
    if _safe_int(summary.get("write_attempt_count")) > max_write_attempts:
        failures.append("write_attempt_count above maximum")
    if require_quality_pass and failures:
        pass
    return ("PASS" if not failures else "FAIL"), failures


def build_engineering_answer_context_pack(
    *,
    engineering_query_planner: Any,
    output_dir: Any,
    v2_summary_guidance_index: Optional[Any] = None,
    image_visual_evidence_pack: Optional[Any] = None,
    raw_ocr_nomenclature_extractor: Optional[Any] = None,
    table_route_evidence_packager: Optional[Any] = None,
    table_exact_search_adapter: Optional[Any] = None,
    min_guidance_context: int = 0,
    min_proof_context: int = 1,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    planner_data = _load_json(engineering_query_planner)
    planner_record = _first_record(planner_data)
    figures, parts, items = _entity_sets(planner_record)

    image_pack = _load_json(image_visual_evidence_pack) if image_visual_evidence_pack else None
    ocr_pack = _load_json(raw_ocr_nomenclature_extractor) if raw_ocr_nomenclature_extractor else None
    table_pack = _load_json(table_route_evidence_packager) if table_route_evidence_packager else None
    exact_pack = _load_json(table_exact_search_adapter) if table_exact_search_adapter else None

    task_type = _norm_str(planner_record.get("task_type"))
    guidance_context = _guidance_context_from_planner(planner_record)
    visual_context, visual_parts = _visual_proof_context(image_pack, figures, parts, items)
    ocr_context = _ocr_nomenclature_context(ocr_pack, figures, parts, visual_parts)
    exact_part_context: List[Dict[str, Any]] = []
    if task_type == "exact_part_lookup" or parts:
        exact_part_context.extend(_exact_part_context(exact_pack, parts, source_name="table_exact_search_adapter", prefix="E"))
        exact_part_context.extend(_exact_part_context(table_pack, parts, source_name="table_route_evidence_packager", prefix="E"))
        exact_part_context = _dedupe_context(exact_part_context)
    table_context = []
    table_context.extend(_maybe_table_context(table_pack, figures, parts, visual_parts))
    table_context.extend(_maybe_table_context(exact_pack, figures, parts, visual_parts))
    table_context = _dedupe_context(table_context)

    proof_context = _dedupe_context([*visual_context, *ocr_context, *exact_part_context, *table_context])
    summary_used_as_proof_count = sum(1 for r in proof_context if r.get("context_type") == "v2_summary_guidance" or r.get("guidance_only"))
    source_trace_ready_count = sum(1 for r in proof_context if bool(r.get("source_trace_ready")))

    unsafe_record_count = 0
    answer_permission_count = 0
    source_truth_mutation_allowed_count = 0
    for r in [*guidance_context, *proof_context]:
        if bool(r.get("unsafe")):
            unsafe_record_count += 1
        if bool(r.get("answer_permission")):
            answer_permission_count += 1
        if bool(r.get("source_truth_mutation_allowed")):
            source_truth_mutation_allowed_count += 1

    summary = {
        "engineering_answer_context_pack_record_count": 1,
        "guidance_context_count": len(guidance_context),
        "proof_context_count": len(proof_context),
        "visual_proof_context_count": len(visual_context),
        "ocr_nomenclature_context_count": len(ocr_context),
        "table_ocr_context_count": len(table_context),
        "exact_part_context_count": len(exact_part_context),
        "source_trace_ready_count": source_trace_ready_count,
        "summary_used_as_proof_count": summary_used_as_proof_count,
        "can_answer_from_summaries_only_count": 0,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": unsafe_record_count,
        "ready_for_engineering_answer_composer": len(proof_context) >= min_proof_context and source_trace_ready_count >= min_source_trace_ready and summary_used_as_proof_count == 0,
    }
    quality, failures = _quality_status(
        summary,
        min_guidance_context=min_guidance_context,
        min_proof_context=min_proof_context,
        min_source_trace_ready=min_source_trace_ready,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )

    record = {
        "question": planner_record.get("question"),
        "task_type": planner_record.get("task_type"),
        "engineering_intent": planner_record.get("engineering_intent"),
        "entities": planner_record.get("entities", {}),
        "required_routes": planner_record.get("required_routes", []),
        "optional_routes": planner_record.get("optional_routes", []),
        "proof_requirements": planner_record.get("proof_requirements", []),
        "guidance_context": guidance_context,
        "proof_context": proof_context,
        "answer_constraints": _answer_constraints(planner_record),
        "guidance_context_policy": "Guidance summaries may help choose routes and frame investigation, but cannot prove answer claims.",
        "proof_context_policy": "Only source-trace-ready proof_context records may support factual answer claims.",
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "unsafe": False,
    }

    out_dir = _path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{MODULE}.json"
    qc_path = out_dir / f"{MODULE}_quality_check.json"
    csv_path = out_dir / f"{MODULE}_proof_records.csv"

    result = {
        "status": STATUS,
        "quality_status": quality,
        "module": MODULE,
        "version": VERSION,
        "source_engineering_query_planner": str(engineering_query_planner),
        "source_v2_summary_guidance_index": str(v2_summary_guidance_index) if v2_summary_guidance_index else "",
        "source_image_visual_evidence_pack": str(image_visual_evidence_pack) if image_visual_evidence_pack else "",
        "source_raw_ocr_nomenclature_extractor": str(raw_ocr_nomenclature_extractor) if raw_ocr_nomenclature_extractor else "",
        "summary": summary,
        "failures": failures,
        "records": [record],
        "paths": {
            "context_pack": str(out_path),
            "quality_check": str(qc_path),
            "proof_records_csv": str(csv_path),
        },
    }

    qc = {
        "status": CHECK_STATUS,
        "quality_status": quality,
        "module": MODULE,
        "version": VERSION,
        "summary": summary,
        "failures": failures,
    }
    _write_json(out_path, result)
    _write_json(qc_path, qc)
    _write_proof_csv(csv_path, proof_context)
    return result


def _write_proof_csv(path: Any, proof_context: Sequence[Mapping[str, Any]]) -> None:
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "context_type", "citation_label", "page_id", "page_number", "figure", "callout", "part_number",
        "nomenclature", "nomenclature_confidence", "proof_source", "proof_strength", "source_trace_ready",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in proof_context:
            w.writerow({k: r.get(k, "") for k in fields})


def check_engineering_answer_context_pack(
    *,
    context_pack: Any,
    output: Optional[Any] = None,
    require_quality_pass: bool = False,
    min_guidance_context: int = 0,
    min_proof_context: int = 1,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _load_json(context_pack)
    summary = data.get("summary") or {}
    quality, failures = _quality_status(
        summary,
        require_quality_pass=require_quality_pass,
        min_guidance_context=min_guidance_context,
        min_proof_context=min_proof_context,
        min_source_trace_ready=min_source_trace_ready,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.insert(0, "quality_status is not PASS")
        quality = "FAIL"
    result = {
        "status": CHECK_STATUS,
        "quality_status": quality,
        "module": MODULE,
        "version": VERSION,
        "summary": summary,
        "failures": failures,
    }
    if output:
        _write_json(output, result)
    return result


def _build_parser(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build TRACE-Net engineering answer context pack v1")
    ap.add_argument("--engineering-query-planner", required=True)
    ap.add_argument("--v2-summary-guidance-index")
    ap.add_argument("--image-visual-evidence-pack")
    ap.add_argument("--raw-ocr-nomenclature-extractor")
    ap.add_argument("--table-route-evidence-packager")
    ap.add_argument("--table-exact-search-adapter")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--min-guidance-context", type=int, default=0)
    ap.add_argument("--min-proof-context", type=int, default=1)
    ap.add_argument("--min-source-trace-ready", type=int, default=1)
    ap.add_argument("--max-unsafe", type=int, default=0)
    ap.add_argument("--max-answer-permission", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--max-write-attempts", type=int, default=0)
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser(argv)
    result = build_engineering_answer_context_pack(
        engineering_query_planner=args.engineering_query_planner,
        v2_summary_guidance_index=args.v2_summary_guidance_index,
        image_visual_evidence_pack=args.image_visual_evidence_pack,
        raw_ocr_nomenclature_extractor=args.raw_ocr_nomenclature_extractor,
        table_route_evidence_packager=args.table_route_evidence_packager,
        table_exact_search_adapter=args.table_exact_search_adapter,
        output_dir=args.output_dir,
        min_guidance_context=args.min_guidance_context,
        min_proof_context=args.min_proof_context,
        min_source_trace_ready=args.min_source_trace_ready,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"guidance_context_count={s.get('guidance_context_count')}")
    print(f"proof_context_count={s.get('proof_context_count')}")
    print(f"visual_proof_context_count={s.get('visual_proof_context_count')}")
    print(f"ocr_nomenclature_context_count={s.get('ocr_nomenclature_context_count')}")
    print(f"source_trace_ready_count={s.get('source_trace_ready_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print(f"unsafe_record_count={s.get('unsafe_record_count')}")
    print(f"answer_permission_count={s.get('answer_permission_count')}")
    print(f"source_truth_mutation_allowed_count={s.get('source_truth_mutation_allowed_count')}")
    print(f"write_attempt_count={s.get('write_attempt_count')}")
    print(f"context_pack={result.get('paths', {}).get('context_pack')}")
    return 0 if result.get("quality_status") == "PASS" else 1


def check_main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Check TRACE-Net engineering answer context pack v1")
    ap.add_argument("--context-pack", required=True)
    ap.add_argument("--output")
    ap.add_argument("--require-quality-pass", action="store_true")
    ap.add_argument("--min-guidance-context", type=int, default=0)
    ap.add_argument("--min-proof-context", type=int, default=1)
    ap.add_argument("--min-source-trace-ready", type=int, default=1)
    ap.add_argument("--max-unsafe", type=int, default=0)
    ap.add_argument("--max-answer-permission", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--max-write-attempts", type=int, default=0)
    args = ap.parse_args(argv)
    result = check_engineering_answer_context_pack(
        context_pack=args.context_pack,
        output=args.output,
        require_quality_pass=args.require_quality_pass,
        min_guidance_context=args.min_guidance_context,
        min_proof_context=args.min_proof_context,
        min_source_trace_ready=args.min_source_trace_ready,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"guidance_context_count={s.get('guidance_context_count')}")
    print(f"proof_context_count={s.get('proof_context_count')}")
    print(f"source_trace_ready_count={s.get('source_trace_ready_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print(f"unsafe_record_count={s.get('unsafe_record_count')}")
    print(f"answer_permission_count={s.get('answer_permission_count')}")
    print(f"source_truth_mutation_allowed_count={s.get('source_truth_mutation_allowed_count')}")
    print(f"write_attempt_count={s.get('write_attempt_count')}")
    for failure in result.get("failures", []):
        print(f"failure={failure}")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
