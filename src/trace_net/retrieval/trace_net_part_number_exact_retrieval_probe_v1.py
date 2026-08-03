"""TRACE-Net Part Number Exact Retrieval Probe v1.

Dry-run audit/probe for part-number questions. The probe searches trusted local
artifacts directly before semantic retrieval so exact part-number evidence can be
anchored first, then graph/Leiden and semantic expansion can happen around those
exact-hit pages.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODULE = "trace_net_part_number_exact_retrieval_probe_v1"
VERSION = "v1"
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")

TEXT_FIELD_HINTS = (
    "ocr_text",
    "ocr_sample_text",
    "page_text",
    "text",
    "excerpt",
    "snippet",
    "row_text",
    "evidence_text",
    "field_value",
    "value",
    "summary_text",
)
IGNORED_PROOF_FIELD_HINTS = (
    "question",
    "query_part_numbers",
    "query_part_number",
    "llm_context_prompt",
    "prompt",
    "citation_map",
    "answer",
    "answer_draft",
    "safety_contract",
)

SOURCE_ARG_MAP = {
    "ocr_route_scan_pack": "ocr_route_scan_pack",
    "table_exact_search_adapter": "table_exact_search_adapter",
    "table_evidence_package": "table_evidence_package",
    "page_context_v2": "page_context_v2",
    "normalized_table_values": "normalized_table_values",
}


def _read_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "citation_label",
        "source_name",
        "hit_class",
        "proof_role",
        "page_number",
        "page_id",
        "source_member",
        "matched_part_number",
        "field_path",
        "route",
        "source_quality_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key, "") for key in fieldnames})


def _canonical_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()


def _part_family(value: str) -> str:
    parts = (value or "").split("-")
    if len(parts) >= 2:
        return "-".join(parts[:2])
    canonical = _canonical_part(value)
    return canonical[:8]


def _extract_query_parts(question: str | None, part_numbers: Sequence[str] | None = None) -> List[str]:
    out: List[str] = []
    for part in part_numbers or []:
        if part and part not in out:
            out.append(part)
    for match in PART_RE.findall(question or ""):
        if match not in out:
            out.append(match)
    return out


def _first_scalar(record: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in record and isinstance(record[key], (str, int, float, bool)):
            return record[key]
    # Shallow recursive search is enough for common nested metadata while avoiding
    # expensive full traversal for large OCR text containers.
    for value in record.values():
        if isinstance(value, dict):
            found = _first_scalar(value, keys)
            if found is not None:
                return found
    return None


def _page_number(record: Dict[str, Any]) -> Optional[int]:
    value = _first_scalar(record, ["page_number", "canonical_page_number", "page", "source_page_number"])
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _page_id(record: Dict[str, Any]) -> Optional[str]:
    value = _first_scalar(record, ["page_id", "canonical_page_id", "source_page_id"])
    return str(value) if value is not None else None


def _source_member(record: Dict[str, Any]) -> Optional[str]:
    value = _first_scalar(record, ["source_member", "raw_tiff_reference", "source_image_member", "image_member"])
    return str(value) if value is not None else None


def _route(record: Dict[str, Any]) -> Optional[str]:
    value = _first_scalar(record, ["route", "final_validated_operational_route", "primary_route", "operational_route"])
    return str(value) if value is not None else None


def _is_record_like(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    keys = set(obj)
    record_keys = {
        "page_id",
        "canonical_page_id",
        "page_number",
        "canonical_page_number",
        "source_member",
        "raw_tiff_reference",
        "record_type",
        "field_name",
        "field_value",
        "evidence_value",
        "ocr_text",
        "ocr_sample_text",
        "text",
        "row_text",
        "document_id",
    }
    return bool(keys & record_keys)


def _walk_record_like(obj: Any, depth: int = 0, max_depth: int = 8) -> Iterable[Dict[str, Any]]:
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        if _is_record_like(obj):
            yield obj
        for value in obj.values():
            if isinstance(value, (dict, list)):
                yield from _walk_record_like(value, depth + 1, max_depth)
    elif isinstance(obj, list):
        for value in obj:
            if isinstance(value, (dict, list)):
                yield from _walk_record_like(value, depth + 1, max_depth)


def _extract_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Prefer explicit top-level record containers but also fall back to a recursive
    # scan because several TRACE-Net graph/table artifacts store nodes outside
    # top-level records.
    records: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for key in [
        "records",
        "documents",
        "items",
        "payloads",
        "evidence_documents",
        "search_documents",
        "graph_nodes",
        "nodes",
        "data",
    ]:
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and id(item) not in seen:
                    records.append(item)
                    seen.add(id(item))
    for record in _walk_record_like(payload):
        if id(record) not in seen:
            records.append(record)
            seen.add(id(record))
    return records


def _iter_strings(obj: Any, prefix: str = "") -> Iterable[Tuple[str, str]]:
    if isinstance(obj, str):
        yield prefix, obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            new_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from _iter_strings(value, new_prefix)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            new_prefix = f"{prefix}[{idx}]"
            yield from _iter_strings(value, new_prefix)


def _field_is_ignored_for_proof(path: str) -> bool:
    lower = path.lower()
    return any(hint in lower for hint in IGNORED_PROOF_FIELD_HINTS)


def _field_is_text_like(path: str) -> bool:
    lower = path.lower()
    return any(hint in lower for hint in TEXT_FIELD_HINTS)


def _excerpt_around(text: str, query: str, window: int) -> str:
    lower = text.lower()
    idx = lower.find(query.lower())
    if idx < 0:
        # Try finding the middle token (e.g. 29073) for OCR strings that split
        # or wrap a part number. This excerpt is not used as exact proof unless
        # the exact normalized part is also found.
        pieces = [piece for piece in re.split(r"[-\s]+", query) if piece]
        for piece in sorted(pieces, key=len, reverse=True):
            idx = lower.find(piece.lower())
            if idx >= 0:
                break
    if idx < 0:
        idx = 0
    half = max(40, window // 2)
    start = max(0, idx - half)
    end = min(len(text), idx + len(query) + half)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _contains_exact_part(text: str, part_number: str) -> bool:
    if not text:
        return False
    if part_number.lower() in text.lower():
        return True
    return _canonical_part(part_number) in _canonical_part(text)


def _contains_family_variant(text: str, part_number: str) -> bool:
    family = _part_family(part_number)
    if not family:
        return False
    # Family hit should contain family but not the exact part.
    return family.lower() in text.lower() and not _contains_exact_part(text, part_number)


def _hit_class(source_name: str, field_path: str) -> str:
    lower = field_path.lower()
    if "extracted_part_numbers" in lower or "part_number_candidates" in lower:
        return "part_number_list_reference"
    if source_name == "ocr_route_scan_pack" and _field_is_text_like(field_path):
        return "trusted_ocr_text_hit"
    if source_name == "table_exact_search_adapter":
        return "trusted_table_exact_hit"
    if source_name == "table_evidence_package":
        return "trusted_table_evidence_hit"
    if source_name == "normalized_table_values":
        return "trusted_normalized_table_value_hit"
    if source_name == "page_context_v2" and _field_is_text_like(field_path):
        return "trusted_page_context_hit"
    return "trusted_metadata_hit"


def _proof_role(hit_class: str) -> str:
    if hit_class in {
        "trusted_ocr_text_hit",
        "trusted_table_exact_hit",
        "trusted_table_evidence_hit",
        "trusted_normalized_table_value_hit",
        "trusted_page_context_hit",
    }:
        return "direct_exact_match_proven"
    if hit_class == "part_number_list_reference":
        return "exact_reference_candidate"
    return "exact_metadata_candidate"


def _source_status(payload: Dict[str, Any]) -> str:
    return str(payload.get("quality_status") or payload.get("summary", {}).get("quality_status") or "UNKNOWN")


def _build_hit_record(
    *,
    source_name: str,
    source_path: Path,
    source_quality_status: str,
    record: Dict[str, Any],
    query_part: str,
    field_path: str,
    text: str,
    hit_kind: str,
    excerpt_window_chars: int,
) -> Dict[str, Any]:
    hit_class = _hit_class(source_name, field_path) if hit_kind == "exact" else "family_variant_hit"
    proof_role = _proof_role(hit_class) if hit_kind == "exact" else "nearby_or_related_part_family_candidate"
    return {
        "module": MODULE,
        "version": VERSION,
        "source_name": source_name,
        "source_path": str(source_path),
        "source_quality_status": source_quality_status,
        "matched_part_number": query_part,
        "hit_kind": hit_kind,
        "hit_class": hit_class,
        "proof_role": proof_role,
        "page_id": _page_id(record),
        "page_number": _page_number(record),
        "source_member": _source_member(record),
        "route": _route(record),
        "field_path": field_path,
        "field_is_ignored_for_proof": _field_is_ignored_for_proof(field_path),
        "field_is_text_like": _field_is_text_like(field_path),
        "excerpt": _excerpt_around(text, query_part, excerpt_window_chars),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "unsafe": False,
    }


def _dedupe_hits(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[Tuple[Any, ...]] = set()
    for record in records:
        key = (
            record.get("source_name"),
            record.get("hit_kind"),
            record.get("hit_class"),
            record.get("page_id"),
            record.get("page_number"),
            record.get("source_member"),
            record.get("field_path"),
            record.get("matched_part_number"),
            record.get("excerpt")[:180],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _citation_records(direct_records: Sequence[Dict[str, Any]], reference_records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, record in enumerate(list(direct_records) + list(reference_records), start=1):
        copy = dict(record)
        copy["citation_label"] = f"E{idx}"
        out.append(copy)
    return out


def _seed_prompt(question: str, query_parts: Sequence[str], citation_records: Sequence[Dict[str, Any]], family_records: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "You are TRACE-Net's context seed builder for exact part-number questions.",
        "Use direct exact hits before semantic, graph, or Leiden expansion.",
        "Graph/Leiden may rank nearby evidence, but exact source text proves part identity.",
        "",
        f"QUESTION: {question}",
        "QUERY_PART_NUMBERS: " + ", ".join(query_parts),
        "",
        "DIRECT EXACT / REFERENCE HITS:",
    ]
    if not citation_records:
        lines.append("None found in trusted artifacts.")
    for record in citation_records:
        lines.append(
            f"{record['citation_label']}: role={record.get('proof_role')}, source={record.get('source_name')}, "
            f"page={record.get('page_number')}, page_id={record.get('page_id')}, source_member={record.get('source_member')}. "
            f"Excerpt: {record.get('excerpt') or ''}"
        )
    lines.extend(["", "FAMILY / NEARBY VARIANT HITS:"])
    for idx, record in enumerate(family_records[:12], start=1):
        lines.append(
            f"F{idx}: source={record.get('source_name')}, page={record.get('page_number')}, "
            f"page_id={record.get('page_id')}. Excerpt: {record.get('excerpt') or ''}"
        )
    if not family_records:
        lines.append("None.")
    lines.extend(["", "SAFETY: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true."])
    return "\n".join(lines)


def build_part_number_exact_retrieval_probe(
    *,
    output_dir: Path | str,
    question: str = "",
    part_numbers: Sequence[str] | None = None,
    ocr_route_scan_pack: Path | str | None = None,
    table_exact_search_adapter: Path | str | None = None,
    table_evidence_package: Path | str | None = None,
    page_context_v2: Path | str | None = None,
    normalized_table_values: Path | str | None = None,
    excerpt_window_chars: int = 900,
    require_source_quality_pass: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    query_parts = _extract_query_parts(question, part_numbers)

    source_paths = {
        "ocr_route_scan_pack": ocr_route_scan_pack,
        "table_exact_search_adapter": table_exact_search_adapter,
        "table_evidence_package": table_evidence_package,
        "page_context_v2": page_context_v2,
        "normalized_table_values": normalized_table_values,
    }

    all_hits: List[Dict[str, Any]] = []
    family_hits: List[Dict[str, Any]] = []
    source_summaries: List[Dict[str, Any]] = []
    violations: List[Dict[str, Any]] = []

    for source_name, source_path_raw in source_paths.items():
        if not source_path_raw:
            continue
        source_path = Path(source_path_raw)
        if not source_path.exists():
            violations.append({"violation_type": "missing_source_file", "source_name": source_name, "source_path": str(source_path)})
            source_summaries.append({"source_name": source_name, "source_path": str(source_path), "status": "MISSING", "record_count": 0})
            continue
        payload = _read_json(source_path)
        status = _source_status(payload)
        records = _extract_records(payload)
        if require_source_quality_pass and status != "PASS":
            violations.append({"violation_type": "source_quality_not_pass", "source_name": source_name, "quality_status": status})
        source_summaries.append(
            {"source_name": source_name, "source_path": str(source_path), "quality_status": status, "record_count": len(records)}
        )
        for record in records:
            for field_path, text in _iter_strings(record):
                if not text:
                    continue
                for part in query_parts:
                    if _field_is_ignored_for_proof(field_path):
                        # Ignore query/citation/prompt metadata. This module is a
                        # retrieval probe, so it should only trust artifact text.
                        continue
                    if _contains_exact_part(text, part):
                        all_hits.append(
                            _build_hit_record(
                                source_name=source_name,
                                source_path=source_path,
                                source_quality_status=status,
                                record=record,
                                query_part=part,
                                field_path=field_path,
                                text=text,
                                hit_kind="exact",
                                excerpt_window_chars=excerpt_window_chars,
                            )
                        )
                    elif _contains_family_variant(text, part):
                        family_hits.append(
                            _build_hit_record(
                                source_name=source_name,
                                source_path=source_path,
                                source_quality_status=status,
                                record=record,
                                query_part=part,
                                field_path=field_path,
                                text=text,
                                hit_kind="family_variant",
                                excerpt_window_chars=excerpt_window_chars,
                            )
                        )

    all_hits = _dedupe_hits(all_hits)
    family_hits = _dedupe_hits(family_hits)

    direct_hits = [r for r in all_hits if r.get("proof_role") == "direct_exact_match_proven"]
    reference_hits = [r for r in all_hits if r.get("proof_role") != "direct_exact_match_proven"]
    # Stable ordering: direct proof first, then reference candidates, then source/page order.
    direct_hits.sort(key=lambda r: (r.get("page_number") is None, r.get("page_number") or 10**9, r.get("source_name") or ""))
    reference_hits.sort(key=lambda r: (r.get("page_number") is None, r.get("page_number") or 10**9, r.get("source_name") or ""))
    family_hits.sort(key=lambda r: (r.get("page_number") is None, r.get("page_number") or 10**9, r.get("source_name") or ""))

    citation_records = _citation_records(direct_hits, reference_hits)
    prompt = _seed_prompt(question, query_parts, citation_records[:24], family_hits[:12])

    exact_page_ids = sorted({r.get("page_id") for r in all_hits if r.get("page_id")})
    direct_page_ids = sorted({r.get("page_id") for r in direct_hits if r.get("page_id")})
    exact_page_numbers = sorted({r.get("page_number") for r in all_hits if r.get("page_number") is not None})
    direct_page_numbers = sorted({r.get("page_number") for r in direct_hits if r.get("page_number") is not None})

    summary: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "question": question,
        "query_part_number_count": len(query_parts),
        "query_part_numbers": list(query_parts),
        "source_file_count": len(source_summaries),
        "source_record_counts": {s["source_name"]: s.get("record_count", 0) for s in source_summaries},
        "source_quality_statuses": {s["source_name"]: s.get("quality_status") or s.get("status") for s in source_summaries},
        "exact_hit_count": len(all_hits),
        "exact_direct_hit_count": len(direct_hits),
        "exact_reference_hit_count": len(reference_hits),
        "family_variant_hit_count": len(family_hits),
        "exact_page_count": len(exact_page_ids),
        "direct_exact_page_count": len(direct_page_ids),
        "exact_page_ids": exact_page_ids,
        "direct_exact_page_ids": direct_page_ids,
        "exact_page_numbers": exact_page_numbers,
        "direct_exact_page_numbers": direct_page_numbers,
        "hit_class_counts": dict(Counter(r.get("hit_class") for r in all_hits)),
        "proof_role_counts": dict(Counter(r.get("proof_role") for r in all_hits)),
        "citation_count": len(citation_records),
        "context_seed_prompt_char_count": len(prompt),
        "exact_retrieval_probe_ready": bool(query_parts),
        "ready_for_context_anchor_injection": bool(direct_hits or reference_hits),
        "dry_run_only": True,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "unsafe_record_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "write_attempt_count": 0,
        "violation_record_count": len(violations),
    }
    if not query_parts:
        violations.append({"violation_type": "missing_query_part_number", "message": "Provide --part-number or a question containing a part number."})
        summary["violation_record_count"] = len(violations)

    quality_status = "PASS" if not violations else "FAIL"
    payload_out: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "source_summaries": source_summaries,
        "records": citation_records,
        "exact_hit_records": all_hits,
        "direct_evidence_records": direct_hits,
        "reference_hit_records": reference_hits,
        "family_variant_hit_records": family_hits,
        "violation_records": violations,
        "context_seed_prompt": prompt,
    }

    report_path = out_dir / f"{MODULE}.json"
    _write_json(report_path, payload_out)
    _write_json(out_dir / f"{MODULE}_summary.json", summary)
    _write_jsonl(out_dir / f"{MODULE}_records.jsonl", citation_records)
    _write_jsonl(out_dir / f"{MODULE}_exact_hits.jsonl", all_hits)
    _write_jsonl(out_dir / f"{MODULE}_family_variant_hits.jsonl", family_hits)
    _write_csv(out_dir / f"{MODULE}_records.csv", citation_records)
    _write_csv(out_dir / f"{MODULE}_violations.csv", violations)
    (out_dir / f"{MODULE}_prompt.txt").write_text(prompt, encoding="utf-8")

    if quality:
        _write_json(out_dir / f"{MODULE}_quality_check.json", payload_out)
        print(f"Wrote: {out_dir / f'{MODULE}_quality_check.json'}")
    print(f"Status: TRACE_NET_PART_NUMBER_EXACT_RETRIEVAL_PROBE_BUILT")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload_out


def check_part_number_exact_retrieval_probe_quality(
    *,
    report_path: Path | str,
    write_json: bool = False,
    min_records: int = 0,
    min_exact_hits: int = 0,
    min_exact_pages: int = 0,
    min_direct_exact_hits: int = 0,
    min_direct_exact_pages: int = 0,
    min_prompt_chars: int = 0,
    max_violation_records: Optional[int] = None,
    require_source_quality_pass: bool = False,
    require_exact_retrieval_probe_ready: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: Optional[int] = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> Dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = payload.get("summary", {})
    failures: List[str] = []

    if payload.get("quality_status") != "PASS":
        failures.append("source_report_quality_not_pass")
    if len(payload.get("records") or []) < min_records:
        failures.append("min_records")
    if summary.get("exact_hit_count", 0) < min_exact_hits:
        failures.append("min_exact_hits")
    if summary.get("exact_page_count", 0) < min_exact_pages:
        failures.append("min_exact_pages")
    if summary.get("exact_direct_hit_count", 0) < min_direct_exact_hits:
        failures.append("min_direct_exact_hits")
    if summary.get("direct_exact_page_count", 0) < min_direct_exact_pages:
        failures.append("min_direct_exact_pages")
    if summary.get("context_seed_prompt_char_count", 0) < min_prompt_chars:
        failures.append("min_prompt_chars")
    if max_violation_records is not None and summary.get("violation_record_count", 0) > max_violation_records:
        failures.append("max_violation_records")
    if require_source_quality_pass:
        statuses = summary.get("source_quality_statuses") or {}
        bad = {name: status for name, status in statuses.items() if status not in {"PASS", None}}
        if bad:
            failures.append("require_source_quality_pass")
    if require_exact_retrieval_probe_ready and not summary.get("exact_retrieval_probe_ready"):
        failures.append("require_exact_retrieval_probe_ready")
    if require_no_human_review_required and (summary.get("human_review_required_count", 0) or summary.get("manual_review_required_count", 0)):
        failures.append("require_no_human_review_required")
    if max_unsafe is not None and summary.get("unsafe_record_count", 0) > max_unsafe:
        failures.append("max_unsafe")
    if require_no_answer_permission and summary.get("answer_permission_count", 0):
        failures.append("require_no_answer_permission")
    if require_no_source_truth_mutation and summary.get("source_truth_mutation_allowed_count", 0):
        failures.append("require_no_source_truth_mutation")
    if require_no_write_attempts and summary.get("write_attempt_count", 0):
        failures.append("require_no_write_attempts")

    check_payload = {
        "module": f"{MODULE}_quality_check",
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "failures": failures,
        "source_report": str(path),
    }
    if write_json:
        out = path.with_name(f"{MODULE}_quality_check.json")
        _write_json(out, check_payload)
        print(f"Wrote: {out}")
    print(f"Quality status: {check_payload['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return check_payload


def main_build(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net part-number exact retrieval probe v1.")
    parser.add_argument("--question", default="")
    parser.add_argument("--part-number", action="append", default=[])
    parser.add_argument("--ocr-route-scan-pack")
    parser.add_argument("--table-exact-search-adapter")
    parser.add_argument("--table-evidence-package")
    parser.add_argument("--page-context-v2")
    parser.add_argument("--normalized-table-values")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--excerpt-window-chars", type=int, default=900)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_part_number_exact_retrieval_probe(
        output_dir=args.output_dir,
        question=args.question,
        part_numbers=args.part_number,
        ocr_route_scan_pack=args.ocr_route_scan_pack,
        table_exact_search_adapter=args.table_exact_search_adapter,
        table_evidence_package=args.table_evidence_package,
        page_context_v2=args.page_context_v2,
        normalized_table_values=args.normalized_table_values,
        excerpt_window_chars=args.excerpt_window_chars,
        require_source_quality_pass=args.require_source_quality_pass,
        quality=args.quality,
    )


def main_check(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net part-number exact retrieval probe v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=0)
    parser.add_argument("--min-exact-hits", type=int, default=0)
    parser.add_argument("--min-exact-pages", type=int, default=0)
    parser.add_argument("--min-direct-exact-hits", type=int, default=0)
    parser.add_argument("--min-direct-exact-pages", type=int, default=0)
    parser.add_argument("--min-prompt-chars", type=int, default=0)
    parser.add_argument("--max-violation-records", type=int)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-exact-retrieval-probe-ready", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_part_number_exact_retrieval_probe_quality(**vars(args))


if __name__ == "__main__":  # pragma: no cover
    main_build()
