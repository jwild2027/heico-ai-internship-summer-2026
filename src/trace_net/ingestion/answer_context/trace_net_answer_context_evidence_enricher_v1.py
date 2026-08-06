"""TRACE-Net answer context evidence enricher v1.

This module enriches an already-built answer context engineering pack with
source-traceable OCR/table/page/image excerpts. It is intentionally dry-run only:
it prepares richer context for an LLM but never writes to Postgres, Qdrant, or
OpenSearch and never grants answer permission.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable

MODULE = "trace_net_answer_context_evidence_enricher_v1"
VERSION = "v1"

PART_RE = re.compile(r"\b\d{2,4}-\d{3,6}(?:-\d{2,4})?\b")

TEXT_KEYS = (
    "ocr_text",
    "best_ocr_text",
    "text",
    "page_text",
    "raw_text",
    "raw_ocr_text",
    "normalized_ocr_text",
    "extracted_text",
    "tesseract_text",
    "visible_text",
    "summary_text",
    "page_summary_text",
    "visual_summary_text",
    "evidence_text",
    "search_text",
    "chunk_text",
    "payload_text",
    "value_text",
    "field_value",
    "normalized_value",
    "description",
)

SIDECAR_KEYS = (
    "ocr_text_path",
    "text_path",
    "text_sidecar_path",
    "best_ocr_text_path",
    "best_text_path",
    "ocr_sidecar_path",
)

SAFETY_ZERO_KEYS = (
    "answer_permission_count",
    "source_truth_mutation_allowed_count",
    "unsafe_record_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "write_attempt_count",
)


def _read_json(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for record in records:
        for key in record:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({k: _csv_value(record.get(k)) for k in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return value


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _path_candidates(raw_path: str, anchor_file: Path | None = None) -> list[Path]:
    normalized = raw_path.replace("\\", "/")
    candidates = [Path(normalized)]
    if anchor_file is not None:
        candidates.append(anchor_file.parent / normalized)
        candidates.append(anchor_file.parent.parent / normalized)
    candidates.append(Path.cwd() / normalized)
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _read_sidecar(raw_path: str, anchor_file: Path | None = None) -> str:
    for candidate in _path_candidates(raw_path, anchor_file):
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return ""


def _collect_text(value: Any, *, anchor_file: Path | None = None, depth: int = 0) -> list[str]:
    if value is None or depth > 5:
        return []
    if isinstance(value, str):
        return [value] if len(value.strip()) >= 8 else []
    texts: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in TEXT_KEYS:
                texts.extend(_collect_text(child, anchor_file=anchor_file, depth=depth + 1))
            elif key in SIDECAR_KEYS and isinstance(child, str):
                sidecar = _read_sidecar(child, anchor_file)
                if sidecar:
                    texts.append(sidecar)
            elif isinstance(child, (dict, list)):
                texts.extend(_collect_text(child, anchor_file=anchor_file, depth=depth + 1))
    elif isinstance(value, list):
        for child in value:
            texts.extend(_collect_text(child, anchor_file=anchor_file, depth=depth + 1))
    return texts


def _best_text(record: dict[str, Any], *, anchor_file: Path | None = None) -> str:
    parts: list[str] = []
    for key in TEXT_KEYS:
        if key in record:
            parts.extend(_collect_text(record.get(key), anchor_file=anchor_file))
    for key in SIDECAR_KEYS:
        if isinstance(record.get(key), str):
            sidecar = _read_sidecar(record[key], anchor_file)
            if sidecar:
                parts.append(sidecar)
    # As a fallback, recursively collect text from nested OCR payloads only.
    for key in ("tesseract_payload", "ocr_payload", "ocr_by_psm", "ocr_results", "visual_observation"):
        if key in record:
            parts.extend(_collect_text(record.get(key), anchor_file=anchor_file))
    clean_parts = [_normalize_text(p) for p in parts if _normalize_text(p)]
    if not clean_parts:
        return ""
    # Prefer the longest text because it is usually the page-level OCR output.
    return max(clean_parts, key=len)


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records")
    if isinstance(records, list):
        return [r for r in records if isinstance(r, dict)]
    return []


def _page_id(record: dict[str, Any]) -> str:
    for key in ("page_id", "source_page_id", "canonical_page_id"):
        if record.get(key):
            return str(record[key])
    return ""


def _page_number(record: dict[str, Any]) -> int | None:
    for key in ("page_number", "canonical_page_number", "page"):
        value = record.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _make_index(payload: dict[str, Any], *, anchor_file: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for record in _records(payload):
        pid = _page_id(record)
        if not pid:
            continue
        record_copy = dict(record)
        record_copy["_joined_text"] = _best_text(record, anchor_file=anchor_file)
        index.setdefault(pid, []).append(record_copy)
    return index


def _citation_records(context_payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = _records(context_payload)
    if records:
        return records
    citation_map = context_payload.get("citation_map") or []
    if isinstance(citation_map, list):
        return [r for r in citation_map if isinstance(r, dict)]
    return []


def _query_part_numbers(context_payload: dict[str, Any]) -> list[str]:
    summary = context_payload.get("summary") or {}
    values = summary.get("query_part_numbers") or context_payload.get("query_part_numbers") or []
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in values:
        value_s = str(value).strip()
        if value_s and value_s not in out:
            out.append(value_s)
    # Also mine question text as a fallback.
    question = str(summary.get("question") or context_payload.get("question") or "")
    for match in PART_RE.findall(question):
        if match not in out:
            out.append(match)
    return out


def _extract_window(text: str, queries: list[str], *, window_chars: int) -> tuple[str, bool, str | None]:
    text = _normalize_text(text)
    if not text:
        return "", False, None
    lower = text.lower()
    for query in queries:
        idx = lower.find(query.lower())
        if idx >= 0:
            half = max(120, window_chars // 2)
            start = max(0, idx - half)
            end = min(len(text), idx + len(query) + half)
            return _normalize_text(text[start:end]), True, query
    part_match = PART_RE.search(text)
    if part_match:
        idx = part_match.start()
        half = max(120, window_chars // 2)
        start = max(0, idx - half)
        end = min(len(text), idx + len(part_match.group(0)) + half)
        return _normalize_text(text[start:end]), False, part_match.group(0)
    return _normalize_text(text[:window_chars]), False, None


def _table_text_for_page(
    page_id: str,
    table_index: dict[str, list[dict[str, Any]]],
    queries: list[str],
    *,
    window_chars: int,
) -> tuple[str, bool, str | None]:
    snippets: list[str] = []
    query_hit = False
    matched: str | None = None
    for record in table_index.get(page_id, []):
        text = record.get("_joined_text") or _best_text(record)
        if not text:
            # Build a compact row-like string from scalar fields.
            scalar_parts = []
            for key, value in record.items():
                if key.startswith("_") or isinstance(value, (dict, list)) or value in (None, ""):
                    continue
                if key in {"page_id", "page_number", "canonical_page_number"}:
                    continue
                scalar_parts.append(f"{key}={value}")
            text = " | ".join(scalar_parts)
        snippet, hit, local_match = _extract_window(text, queries, window_chars=window_chars)
        if snippet:
            snippets.append(snippet)
            query_hit = query_hit or hit
            matched = matched or local_match
        if query_hit:
            break
    return _normalize_text("\n".join(snippets)[:window_chars]), query_hit, matched


def _source_trace(record: dict[str, Any], ocr_record: dict[str, Any] | None) -> dict[str, Any]:
    src = ocr_record or {}
    def first(*keys: str) -> Any:
        for key in keys:
            if record.get(key) not in (None, ""):
                return record.get(key)
            if src.get(key) not in (None, ""):
                return src.get(key)
        return None
    return {
        "source_member": first("source_member", "raw_tiff_reference", "source_member_name"),
        "raw_tiff_reference": first("raw_tiff_reference", "source_member", "image_member"),
        "source_image_sha256": first("source_image_sha256", "raw_image_sha256", "image_sha256", "source_sha256"),
    }


def _role(record: dict[str, Any], route: str, direct_hit: bool, original_role: str) -> str:
    if direct_hit:
        return "direct_exact_match_proven"
    if original_role.startswith("direct"):
        return "direct_exact_match_candidate"
    if route == "table":
        return "nearby_or_similar_table_evidence"
    if route == "plain_text":
        return "plain_text_support"
    if route == "image":
        return "visual_observation_support"
    return original_role or "supporting_evidence"


def _build_prompt(
    *,
    question: str,
    query_part_numbers: list[str],
    records: list[dict[str, Any]],
    citation_map: list[dict[str, Any]],
) -> str:
    direct = [r for r in records if str(r.get("enriched_context_role", "")).startswith("direct")]
    nearby = [r for r in records if r.get("enriched_context_role") == "nearby_or_similar_table_evidence"]
    support = [r for r in records if r not in direct and r not in nearby]

    lines: list[str] = [
        "You are TRACE-Net's final answer drafter for scanned technical manuals.",
        "Use only the provided evidence. Do not invent part numbers, pages, effectivity, quantities, or applicability.",
        "Every factual claim must cite one or more citation labels like [E1].",
        "If direct evidence is candidate-level or lacks row text, say that clearly.",
        "Keep the answer short and operational: direct finding, nearby/similar evidence, citations, and safety note.",
        "",
        f"QUESTION: {question}",
        f"QUERY_PART_NUMBERS: {', '.join(query_part_numbers) if query_part_numbers else 'None detected'}",
        "",
        "DIRECT EVIDENCE:",
    ]
    if direct:
        for r in direct:
            lines.append(_prompt_line(r))
    else:
        lines.append("None.")
    lines.append("")
    lines.append("NEARBY / SIMILAR EVIDENCE:")
    if nearby:
        for r in nearby:
            lines.append(_prompt_line(r))
    else:
        lines.append("None.")
    lines.append("")
    lines.append("OTHER SUPPORTING EVIDENCE:")
    if support:
        for r in support:
            lines.append(_prompt_line(r))
    else:
        lines.append("None.")
    lines.append("")
    lines.append("CITATION MAP:")
    for c in citation_map:
        lines.append(
            f"{c.get('citation_label')} => page_id={c.get('page_id')}, page={c.get('page_number')}, "
            f"source_member={c.get('source_member')}, sha256={c.get('source_image_sha256')}"
        )
    lines.append("")
    lines.append("SAFETY: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.")
    return "\n".join(lines)


def _prompt_line(record: dict[str, Any]) -> str:
    excerpt = record.get("enriched_excerpt") or "No enriched excerpt available."
    excerpt = excerpt.replace("\n", " ")
    if len(excerpt) > 900:
        excerpt = excerpt[:897] + "..."
    label = record.get("citation_label") or "E?"
    return (
        f"{label}: role={record.get('enriched_context_role')}, page={record.get('page_number')}, "
        f"page_id={record.get('page_id')}, route={record.get('route')}, score={record.get('retrieval_score')}. "
        f"Evidence: {excerpt}"
    )


def build_answer_context_evidence_enricher(
    *,
    context_pack: str | Path,
    ocr_route_scan_pack: str | Path,
    output_dir: str | Path,
    table_exact_search_adapter: str | Path | None = None,
    page_context_v2: str | Path | None = None,
    image_visual_summary: str | Path | None = None,
    excerpt_window_chars: int = 1200,
    require_source_quality_pass: bool = False,
    quality: bool = False,
) -> dict[str, Any]:
    context_path = Path(context_pack)
    ocr_path = Path(ocr_route_scan_pack)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    context_payload = _read_json(context_path)
    ocr_payload = _read_json(ocr_path)
    table_payload = _read_json(table_exact_search_adapter) if table_exact_search_adapter else {"records": []}
    page_context_payload = _read_json(page_context_v2) if page_context_v2 else {"records": []}
    image_payload = _read_json(image_visual_summary) if image_visual_summary else {"records": []}

    ocr_index = _make_index(ocr_payload, anchor_file=ocr_path)
    table_index = _make_index(table_payload, anchor_file=Path(table_exact_search_adapter) if table_exact_search_adapter else None)
    page_context_index = _make_index(page_context_payload, anchor_file=Path(page_context_v2) if page_context_v2 else None)
    image_index = _make_index(image_payload, anchor_file=Path(image_visual_summary) if image_visual_summary else None)

    source_quality_ok = context_payload.get("quality_status") == "PASS"
    source_ocr_quality_ok = ocr_payload.get("quality_status") == "PASS"
    question = str((context_payload.get("summary") or {}).get("question") or context_payload.get("question") or "")
    queries = _query_part_numbers(context_payload)

    enriched_records: list[dict[str, Any]] = []
    violation_records: list[dict[str, Any]] = []

    for idx, record in enumerate(_citation_records(context_payload), start=1):
        pid = _page_id(record)
        page_no = _page_number(record)
        route = str(record.get("route") or record.get("final_validated_operational_route") or "")
        citation_label = str(record.get("citation_label") or f"E{idx}")
        ocr_record = (ocr_index.get(pid) or [{}])[0]
        trace = _source_trace(record, ocr_record if ocr_record else None)

        table_excerpt, table_hit, table_match = _table_text_for_page(pid, table_index, queries, window_chars=excerpt_window_chars)
        ocr_text = ocr_record.get("_joined_text") or ""
        ocr_excerpt, ocr_hit, ocr_match = _extract_window(ocr_text, queries, window_chars=excerpt_window_chars)
        page_summary_text = "\n".join(r.get("_joined_text", "") for r in page_context_index.get(pid, []) if r.get("_joined_text"))
        summary_excerpt, _, _ = _extract_window(page_summary_text, queries, window_chars=excerpt_window_chars)
        image_text = "\n".join(r.get("_joined_text", "") for r in image_index.get(pid, []) if r.get("_joined_text"))
        image_excerpt, _, _ = _extract_window(image_text, queries, window_chars=excerpt_window_chars)

        source_kind = "none"
        direct_hit = False
        matched_query = None
        excerpt = ""
        if table_excerpt:
            excerpt = table_excerpt
            source_kind = "table_exact_or_table_artifact"
            direct_hit = table_hit
            matched_query = table_match
        elif ocr_excerpt:
            excerpt = ocr_excerpt
            source_kind = "ocr_route_scan_pack"
            direct_hit = ocr_hit
            matched_query = ocr_match
        elif summary_excerpt:
            excerpt = summary_excerpt
            source_kind = "page_context_v2"
        elif image_excerpt:
            excerpt = image_excerpt
            source_kind = "image_visual_summary"

        original_role = str(record.get("context_role") or "")
        enriched_role = _role(record, route, direct_hit, original_role)
        lineage_ready = all(trace.values()) and bool(pid) and page_no is not None
        warnings: list[str] = []
        if not excerpt:
            warnings.append("no_enriched_excerpt_found")
        if not direct_hit and original_role.startswith("direct"):
            warnings.append("direct_evidence_not_text_proven")
        if not lineage_ready:
            warnings.append("missing_lineage")

        enriched = {
            "citation_label": citation_label,
            "page_id": pid,
            "page_number": page_no,
            "route": route,
            "context_role": original_role,
            "enriched_context_role": enriched_role,
            "retrieval_score": record.get("retrieval_score"),
            "targets": record.get("targets") or [],
            "query_part_numbers": queries,
            "matched_query_part_number": matched_query if direct_hit else None,
            "direct_text_match": direct_hit,
            "enriched_excerpt_source": source_kind,
            "enriched_excerpt": excerpt,
            "enriched_excerpt_char_count": len(excerpt),
            "lineage_ready": lineage_ready,
            "source_member": trace["source_member"],
            "raw_tiff_reference": trace["raw_tiff_reference"],
            "source_image_sha256": trace["source_image_sha256"],
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "dry_run_only": True,
            "human_review_required": False,
            "manual_review_required": False,
            "unsafe_record": False,
            "enrichment_warnings": warnings,
            "enrichment_status": "PASS" if lineage_ready and excerpt else "WARNING",
        }
        enriched_records.append(enriched)
        if not lineage_ready:
            violation_records.append({**enriched, "violation_reason": "missing_lineage"})

    citation_map = [
        {
            "citation_label": r.get("citation_label"),
            "enriched_context_role": r.get("enriched_context_role"),
            "page_id": r.get("page_id"),
            "page_number": r.get("page_number"),
            "route": r.get("route"),
            "source_member": r.get("source_member"),
            "raw_tiff_reference": r.get("raw_tiff_reference"),
            "source_image_sha256": r.get("source_image_sha256"),
            "direct_text_match": r.get("direct_text_match"),
            "enriched_excerpt_source": r.get("enriched_excerpt_source"),
        }
        for r in enriched_records
    ]
    prompt = _build_prompt(question=question, query_part_numbers=queries, records=enriched_records, citation_map=citation_map)

    enriched_excerpt_count = sum(1 for r in enriched_records if r.get("enriched_excerpt"))
    direct_text_match_count = sum(1 for r in enriched_records if r.get("direct_text_match"))
    warning_count = sum(1 for r in enriched_records if r.get("enrichment_status") == "WARNING")
    source_excerpt_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for r in enriched_records:
        source_excerpt_counts[str(r.get("enriched_excerpt_source"))] = source_excerpt_counts.get(str(r.get("enriched_excerpt_source")), 0) + 1
        role_counts[str(r.get("enriched_context_role"))] = role_counts.get(str(r.get("enriched_context_role")), 0) + 1

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_context_pack": str(context_path),
        "source_context_pack_quality_status": context_payload.get("quality_status"),
        "source_ocr_route_scan_pack": str(ocr_path),
        "source_ocr_route_scan_pack_quality_status": ocr_payload.get("quality_status"),
        "question": question,
        "query_part_numbers": queries,
        "query_part_number_count": len(queries),
        "enriched_context_record_count": len(enriched_records),
        "context_pack_record_count": len(enriched_records),
        "citation_count": len(citation_map),
        "enriched_excerpt_count": enriched_excerpt_count,
        "records_with_enriched_excerpt_count": enriched_excerpt_count,
        "direct_text_match_count": direct_text_match_count,
        "enrichment_warning_count": warning_count,
        "source_excerpt_counts": source_excerpt_counts,
        "enriched_context_role_counts": role_counts,
        "context_prompt_char_count": len(prompt),
        "answer_context_enriched": enriched_excerpt_count > 0,
        "ready_for_gemma_context_prompt": enriched_excerpt_count > 0 and not violation_records,
        "violation_record_count": len(violation_records),
        "lineage_ready_count": sum(1 for r in enriched_records if r.get("lineage_ready")),
        "missing_lineage_count": sum(1 for r in enriched_records if not r.get("lineage_ready")),
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
    }
    quality_status = "PASS"
    if require_source_quality_pass and not (source_quality_ok and source_ocr_quality_ok):
        quality_status = "FAIL"
    if violation_records:
        quality_status = "FAIL"
    if quality and enriched_excerpt_count == 0:
        quality_status = "FAIL"

    payload = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "records": enriched_records,
        "citation_map": citation_map,
        "violation_records": violation_records,
        "llm_context_prompt": prompt,
    }

    report_path = output / "trace_net_answer_context_evidence_enricher_v1.json"
    _write_json(report_path, payload)
    _write_json(output / "trace_net_answer_context_evidence_enricher_v1_summary.json", summary)
    _write_jsonl(output / "trace_net_answer_context_evidence_enricher_v1_records.jsonl", enriched_records)
    _write_csv(output / "trace_net_answer_context_evidence_enricher_v1_records.csv", enriched_records)
    _write_jsonl(output / "trace_net_answer_context_evidence_enricher_v1_citation_map.jsonl", citation_map)
    _write_csv(output / "trace_net_answer_context_evidence_enricher_v1_violations.csv", violation_records)
    (output / "trace_net_answer_context_evidence_enricher_v1_prompt.txt").write_text(prompt, encoding="utf-8")
    (output / "trace_net_answer_context_evidence_enricher_v1.md").write_text(_markdown_report(payload), encoding="utf-8")
    if quality:
        _write_json(output / "trace_net_answer_context_evidence_enricher_v1_quality_check.json", payload)
        print(f"Wrote: {output / 'trace_net_answer_context_evidence_enricher_v1_quality_check.json'}")
    print("Status: TRACE_NET_ANSWER_CONTEXT_EVIDENCE_ENRICHER_BUILT")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def _markdown_report(payload: dict[str, Any]) -> str:
    s = payload.get("summary", {})
    lines = [
        "# TRACE-Net Answer Context Evidence Enricher v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "enriched_context_record_count",
        "enriched_excerpt_count",
        "direct_text_match_count",
        "enrichment_warning_count",
        "citation_count",
        "context_prompt_char_count",
        "violation_record_count",
        "lineage_ready_count",
        "missing_lineage_count",
    ):
        lines.append(f"- {key}: {s.get(key)}")
    lines.extend(["", "## Safety", "", "Dry-run only; no DB writes; no answer permission; no source-truth mutation."])
    return "\n".join(lines) + "\n"


def check_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_records: int = 1,
    min_enriched_excerpts: int = 1,
    min_citations: int = 1,
    min_prompt_chars: int = 200,
    max_violation_records: int = 0,
    require_source_quality_pass: bool = False,
    require_enriched_prompt: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: int | None = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = payload.get("summary", {})
    failures: list[str] = []

    def count(key: str) -> int:
        try:
            return int(summary.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    if payload.get("quality_status") != "PASS":
        failures.append("source_report_quality_not_pass")
    if count("enriched_context_record_count") < min_records:
        failures.append("min_records")
    if count("enriched_excerpt_count") < min_enriched_excerpts:
        failures.append("min_enriched_excerpts")
    if count("citation_count") < min_citations:
        failures.append("min_citations")
    if count("context_prompt_char_count") < min_prompt_chars:
        failures.append("min_prompt_chars")
    if count("violation_record_count") > max_violation_records:
        failures.append("max_violation_records")
    if require_source_quality_pass and (
        summary.get("source_context_pack_quality_status") != "PASS"
        or summary.get("source_ocr_route_scan_pack_quality_status") != "PASS"
    ):
        failures.append("source_quality_not_pass")
    if require_enriched_prompt and not payload.get("llm_context_prompt"):
        failures.append("missing_enriched_prompt")
    if require_no_human_review_required and (count("human_review_required_count") or count("manual_review_required_count")):
        failures.append("human_review_required")
    if max_unsafe is not None and count("unsafe_record_count") > max_unsafe:
        failures.append("unsafe_record_count")
    if require_no_answer_permission and count("answer_permission_count"):
        failures.append("answer_permission_count")
    if require_no_source_truth_mutation and count("source_truth_mutation_allowed_count"):
        failures.append("source_truth_mutation_allowed_count")
    if require_no_write_attempts:
        for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count", "write_attempt_count"):
            if count(key):
                failures.append(key)

    result = dict(payload)
    result["quality_status"] = "FAIL" if failures else "PASS"
    result["quality_check_failures"] = failures
    if write_json:
        out_path = path.with_name(path.stem + "_quality_check.json")
        _write_json(out_path, result)
        print(f"Wrote: {out_path}")
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures))
    return result


def main_build(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net answer context evidence enricher v1")
    parser.add_argument("--context-pack", required=True)
    parser.add_argument("--ocr-route-scan-pack", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--table-exact-search-adapter")
    parser.add_argument("--page-context-v2")
    parser.add_argument("--image-visual-summary")
    parser.add_argument("--excerpt-window-chars", type=int, default=1200)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_answer_context_evidence_enricher(
        context_pack=args.context_pack,
        ocr_route_scan_pack=args.ocr_route_scan_pack,
        output_dir=args.output_dir,
        table_exact_search_adapter=args.table_exact_search_adapter,
        page_context_v2=args.page_context_v2,
        image_visual_summary=args.image_visual_summary,
        excerpt_window_chars=args.excerpt_window_chars,
        require_source_quality_pass=args.require_source_quality_pass,
        quality=args.quality,
    )


def main_check(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net answer context evidence enricher v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-enriched-excerpts", type=int, default=1)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-prompt-chars", type=int, default=200)
    parser.add_argument("--max-violation-records", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-enriched-prompt", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_enriched_excerpts=args.min_enriched_excerpts,
        min_citations=args.min_citations,
        min_prompt_chars=args.min_prompt_chars,
        max_violation_records=args.max_violation_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_enriched_prompt=args.require_enriched_prompt,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":
    main_build()
