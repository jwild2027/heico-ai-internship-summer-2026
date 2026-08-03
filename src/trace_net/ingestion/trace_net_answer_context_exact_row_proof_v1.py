"""TRACE-Net answer context exact row proof v1.

This module verifies whether a graph-expanded answer-context evidence record actually
contains an exact queried part number in source-traceable text/table evidence.
It is intentionally conservative: graph/Leiden/community context may rank nearby
evidence, but only OCR/table/exact-evidence text can upgrade a candidate to proven.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MODULE = "trace_net_answer_context_exact_row_proof_v1"
STATUS = "TRACE_NET_ANSWER_CONTEXT_EXACT_ROW_PROOF_BUILT"

REPORT_NAME = "trace_net_answer_context_exact_row_proof_v1.json"
SUMMARY_NAME = "trace_net_answer_context_exact_row_proof_v1_summary.json"
RECORDS_JSONL_NAME = "trace_net_answer_context_exact_row_proof_v1_records.jsonl"
RECORDS_CSV_NAME = "trace_net_answer_context_exact_row_proof_v1_records.csv"
PROMPT_NAME = "trace_net_answer_context_exact_row_proof_v1_prompt.txt"
CITATION_MAP_NAME = "trace_net_answer_context_exact_row_proof_v1_citation_map.jsonl"
VIOLATIONS_CSV_NAME = "trace_net_answer_context_exact_row_proof_v1_violations.csv"
QUALITY_NAME = "trace_net_answer_context_exact_row_proof_v1_quality_check.json"
MARKDOWN_NAME = "trace_net_answer_context_exact_row_proof_v1.md"

SAFE_FALSE_KEYS = (
    "answer_permission",
    "can_answer_directly",
    "can_prove_claims",
    "source_truth_mutation_allowed",
    "postgres_write_attempt",
    "qdrant_write_attempt",
    "opensearch_write_attempt",
    "manual_review_required",
    "human_review_required",
    "unsafe_record",
)

TEXT_KEYS = (
    "exact_row_text",
    "row_text",
    "table_row_text",
    "value_text",
    "document_text",
    "chunk_text",
    "text",
    "ocr_text",
    "excerpt",
    "enriched_excerpt",
    "payload_text",
    "search_text",
    "description",
    "part_number",
    "covered_part_number",
    "ipl_part_number",
    "normalized_value",
    "value",
)

PAGE_ID_KEYS = ("page_id", "canonical_page_id", "source_page_id")
PAGE_NUMBER_KEYS = ("page_number", "canonical_page_number", "source_page_number", "manual_page_number")
SOURCE_MEMBER_KEYS = ("source_member", "raw_tiff_reference", "source_member_name")

RECORD_CONTAINER_KEYS = (
    "records",
    "exact_search_records",
    "exact_search_documents",
    "documents",
    "evidence_records",
    "promoted_table_value_evidence_records",
    "search_ready_evidence_records",
    "normalized_table_value_records",
    "source_normalized_table_value_records",
    "table_route_value_audit_records",
    "payload_records",
    "qdrant_payload_audit_records",
    "opensearch_payload_audit_records",
    "rows",
    "items",
)

# Only these artifacts may upgrade a record to exact proof. Graph/Leiden/enriched
# prompt records can carry useful OCR excerpts, but they also contain query metadata
# and role labels; they are therefore not trusted proof sources by themselves.
TRUSTED_EXACT_PROOF_SOURCES = {
    "ocr_route_scan_pack",
    "table_exact_search_adapter",
    "table_evidence_package",
    "normalized_table_values",
}

UNTRUSTED_PROOF_SOURCE_KEYS = {
    "question",
    "query",
    "query_part_number",
    "query_part_numbers",
    "llm_context_prompt",
    "llm_graph_context_prompt",
    "llm_exact_row_context_prompt",
    "prompt",
    "citation_map",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_part(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _part_regex(part: str) -> re.Pattern[str]:
    # Exact printable form, with loose whitespace around hyphens for OCR line breaks.
    pieces = [re.escape(p) for p in part.upper().split("-")]
    pattern = r"(?<![A-Z0-9])" + r"\s*[-–—]?\s*".join(pieces) + r"(?![A-Z0-9])"
    return re.compile(pattern, re.IGNORECASE)


def _contains_exact_part(text: str, part: str) -> bool:
    if not text or not part:
        return False
    if _part_regex(part).search(text):
        return True
    return _normalize_part(part) in _normalize_part(text)


def _snippet_around(text: str, part: str, window: int = 320) -> str:
    if not text:
        return ""
    match = _part_regex(part).search(text)
    if match:
        start = max(0, match.start() - window)
        end = min(len(text), match.end() + window)
        return _clean_text(text[start:end])
    ntext = _normalize_part(text)
    npart = _normalize_part(part)
    idx = ntext.find(npart)
    if idx >= 0:
        # Fall back to a broad leading snippet; normalized offsets do not map exactly.
        return _clean_text(text[: min(len(text), window * 2)])
    return _clean_text(text[: min(len(text), window * 2)])


def _clean_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _record_text(record: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in TEXT_KEYS:
        value = record.get(key)
        if isinstance(value, (str, int, float)):
            parts.append(str(value))
    # Include shallow dict/list scalar values because many TRACE-Net artifacts use varied field names.
    for key, value in record.items():
        if key in TEXT_KEYS:
            continue
        if key in UNTRUSTED_PROOF_SOURCE_KEYS:
            continue
        if isinstance(value, str) and ("part" in key.lower() or "text" in key.lower() or "value" in key.lower() or "row" in key.lower()):
            parts.append(value)
        elif isinstance(value, list) and ("part" in key.lower() or "value" in key.lower()) and not key.startswith("query"):
            parts.extend(str(x) for x in value[:12] if isinstance(x, (str, int, float)))
    return _clean_text(" ".join(parts))


def _untrusted_context_contains_query_part(record: dict[str, Any], query_parts: list[str]) -> bool:
    # Diagnostic only. This intentionally scans the context/prompt-ish record to
    # reveal when query metadata would have caused a false positive, but it must
    # never upgrade proof status.
    context_text = _record_text(record)
    metadata_bits: list[str] = []
    for key in UNTRUSTED_PROOF_SOURCE_KEYS:
        value = record.get(key)
        if isinstance(value, (str, int, float)):
            metadata_bits.append(str(value))
        elif isinstance(value, list):
            metadata_bits.extend(str(x) for x in value if isinstance(x, (str, int, float)))
    text = _clean_text(" ".join([context_text] + metadata_bits))
    return any(_contains_exact_part(text, part) for part in query_parts)


def _get_first(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if record.get(key) not in (None, ""):
            return record.get(key)
    return None


def _page_number_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        digits = re.findall(r"\d+", str(value))
        if digits:
            try:
                return int(digits[-1])
            except Exception:
                return None
    return None


def _extract_records_from_payload(payload: Any, *, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 5:
        return []
    records: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                records.append(item)
            records.extend(_extract_records_from_payload(item, depth=depth + 1))
        return records
    if not isinstance(payload, dict):
        return []
    for key in RECORD_CONTAINER_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    records.append(item)
        elif isinstance(value, dict):
            records.extend(_extract_records_from_payload(value, depth=depth + 1))
    # Some artifacts store maps of id -> record.
    for key, value in payload.items():
        if key in RECORD_CONTAINER_KEYS:
            continue
        if isinstance(value, dict) and depth < 3:
            if any(k in value for k in PAGE_ID_KEYS + PAGE_NUMBER_KEYS + SOURCE_MEMBER_KEYS) and any(k in value for k in TEXT_KEYS):
                records.append(value)
            else:
                records.extend(_extract_records_from_payload(value, depth=depth + 1))
        elif isinstance(value, list) and depth < 3:
            if key.endswith("records") or key.endswith("nodes") or key.endswith("documents") or key.endswith("values"):
                for item in value:
                    if isinstance(item, dict):
                        records.append(item)
    # Deduplicate by object content for small/medium artifacts.
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        try:
            sig = json.dumps(record, sort_keys=True, default=str)[:2000]
        except Exception:
            sig = str(id(record))
        if sig not in seen:
            seen.add(sig)
            deduped.append(record)
    return deduped


@dataclass
class EvidenceHit:
    source: str
    record_index: int
    match_part_number: str
    proof_text: str
    page_id: str | None
    page_number: int | None
    source_member: str | None


def _matches_page(source_record: dict[str, Any], context_record: dict[str, Any]) -> bool:
    src_page_id = _get_first(source_record, PAGE_ID_KEYS)
    ctx_page_id = _get_first(context_record, PAGE_ID_KEYS)
    if src_page_id and ctx_page_id and str(src_page_id) == str(ctx_page_id):
        return True
    src_page_number = _page_number_value(_get_first(source_record, PAGE_NUMBER_KEYS))
    ctx_page_number = _page_number_value(_get_first(context_record, PAGE_NUMBER_KEYS))
    if src_page_number is not None and ctx_page_number is not None and src_page_number == ctx_page_number:
        return True
    src_member = _get_first(source_record, SOURCE_MEMBER_KEYS)
    ctx_member = _get_first(context_record, SOURCE_MEMBER_KEYS)
    if src_member and ctx_member and str(src_member) == str(ctx_member):
        return True
    return False


def _collect_source_records(named_payloads: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    collected: dict[str, list[dict[str, Any]]] = {}
    for name, payload in named_payloads.items():
        if payload:
            collected[name] = _extract_records_from_payload(payload)
        else:
            collected[name] = []
    return collected


def _find_evidence_hits(
    context_record: dict[str, Any],
    query_parts: list[str],
    source_records: dict[str, list[dict[str, Any]]],
    *,
    excerpt_window_chars: int,
) -> list[EvidenceHit]:
    hits: list[EvidenceHit] = []

    # Do not prove from the graph/enricher context record itself. It includes
    # query_part_numbers and role metadata that can leak the requested part into
    # every citation. Only trusted source artifacts below may prove exact rows.
    for source_name, records in source_records.items():
        if source_name not in TRUSTED_EXACT_PROOF_SOURCES:
            continue
        for idx, record in enumerate(records):
            if not _matches_page(record, context_record):
                continue
            text = _record_text(record)
            if not text:
                continue
            for part in query_parts:
                if _contains_exact_part(text, part):
                    hits.append(
                        EvidenceHit(
                            source=source_name,
                            record_index=idx,
                            match_part_number=part,
                            proof_text=_snippet_around(text, part, window=excerpt_window_chars // 2),
                            page_id=_get_first(record, PAGE_ID_KEYS) or _get_first(context_record, PAGE_ID_KEYS),
                            page_number=_page_number_value(_get_first(record, PAGE_NUMBER_KEYS))
                            or _page_number_value(_get_first(context_record, PAGE_NUMBER_KEYS)),
                            source_member=_get_first(record, SOURCE_MEMBER_KEYS) or _get_first(context_record, SOURCE_MEMBER_KEYS),
                        )
                    )
    # Prefer exact table/evidence source hits over OCR/context if multiple exist.
    priority = {
        "table_exact_search_adapter": 0,
        "table_evidence_package": 1,
        "normalized_table_values": 2,
        "ocr_route_scan_pack": 3,
    }
    hits.sort(key=lambda h: (priority.get(h.source, 50), h.record_index))
    # Deduplicate by source + proof text prefix.
    seen: set[tuple[str, str, str]] = set()
    deduped: list[EvidenceHit] = []
    for hit in hits:
        key = (hit.source, hit.match_part_number, hit.proof_text[:240])
        if key not in seen:
            seen.add(key)
            deduped.append(hit)
    return deduped


def _build_prompt(question: str, query_parts: list[str], records: list[dict[str, Any]], citation_map: list[dict[str, Any]]) -> str:
    proven = [r for r in records if r.get("exact_row_proof_status") == "PROVEN"]
    candidates = [r for r in records if r.get("exact_row_proof_status") == "CANDIDATE"]
    related = [r for r in records if r.get("exact_row_proof_status") not in {"PROVEN", "CANDIDATE"}]

    lines: list[str] = []
    lines.append("You are TRACE-Net's final answer drafter for scanned technical manuals.")
    lines.append("Use only the provided evidence. Do not invent part numbers, pages, effectivity, quantities, or applicability.")
    lines.append("Every factual claim must cite one or more citation labels like [E1].")
    lines.append("Only records marked EXACT_ROW_PROOF=PROVEN may be described as found/proven direct matches.")
    lines.append("Graph and Leiden context may explain nearby/similar evidence, but cannot prove exact part identity or interchangeability by itself.")
    lines.append("If no direct exact row proof is present, say the requested part is not proven by the provided evidence and describe candidate/nearby evidence only.")
    lines.append("Keep the answer short and operational: direct proof, nearby/similar evidence, limitations, citations, and safety note.")
    lines.append("")
    lines.append(f"QUESTION: {question}")
    lines.append("QUERY_PART_NUMBERS: " + (", ".join(query_parts) if query_parts else "none"))
    lines.append("")

    def add_section(title: str, section_records: list[dict[str, Any]]) -> None:
        lines.append(title + ":")
        if not section_records:
            lines.append("None.")
        for r in section_records:
            label = r.get("citation_label") or "E?"
            page = r.get("page_number")
            role = r.get("exact_row_context_role") or r.get("graph_context_role")
            proof = r.get("exact_row_proof_status")
            sources = ",".join(r.get("exact_match_sources") or []) or "none"
            relation = r.get("graph_relation_type") or "none"
            comms = ",".join(r.get("leiden_community_ids") or []) or "none"
            text = r.get("exact_row_text") or r.get("enriched_excerpt") or "No excerpt available."
            lines.append(
                f"{label}: EXACT_ROW_PROOF={proof}, role={role}, page={page}, page_id={r.get('page_id')}, "
                f"route={r.get('route')}, match_sources={sources}, graph_relation={relation}, communities={comms}. Evidence: {text[:1400]}"
            )
        lines.append("")

    add_section("DIRECT EXACT ROW PROOF", proven)
    add_section("DIRECT CANDIDATES WITHOUT EXACT ROW PROOF", candidates)
    add_section("NEARBY / GRAPH / LEIDEN / SIMILAR EVIDENCE", related)

    lines.append("CITATION MAP:")
    for c in citation_map:
        lines.append(
            f"{c.get('citation_label')} => page_id={c.get('page_id')}, page={c.get('page_number')}, "
            f"source_member={c.get('source_member')}, sha256={c.get('source_image_sha256')}, "
            f"exact_row_proof_status={c.get('exact_row_proof_status')}, role={c.get('exact_row_context_role')}"
        )
    lines.append("")
    lines.append("SAFETY: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.")
    return "\n".join(lines)


def _summary_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "direct_exact_match_proven_count": sum(1 for r in records if r.get("exact_row_proof_status") == "PROVEN"),
        "direct_exact_match_candidate_count": sum(1 for r in records if r.get("exact_row_proof_status") == "CANDIDATE"),
        "nearby_or_related_evidence_count": sum(1 for r in records if r.get("exact_row_proof_status") == "RELATED"),
        "records_with_exact_row_text_count": sum(1 for r in records if r.get("exact_row_text")),
        "records_with_exact_match_source_count": sum(1 for r in records if r.get("exact_match_sources")),
    }


def build_answer_context_exact_row_proof(
    *,
    graph_leiden_expander: str | Path,
    output_dir: str | Path,
    ocr_route_scan_pack: str | Path | None = None,
    table_exact_search_adapter: str | Path | None = None,
    table_evidence_package: str | Path | None = None,
    normalized_table_values: str | Path | None = None,
    page_context_v2: str | Path | None = None,
    excerpt_window_chars: int = 1200,
    require_source_quality_pass: bool = False,
    quality: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    source_payload = _read_json(graph_leiden_expander)
    source_summary = source_payload.get("summary", {}) if isinstance(source_payload, dict) else {}
    source_quality = source_payload.get("quality_status") if isinstance(source_payload, dict) else None

    named_payloads = {
        "ocr_route_scan_pack": _read_json(ocr_route_scan_pack),
        "table_exact_search_adapter": _read_json(table_exact_search_adapter),
        "table_evidence_package": _read_json(table_evidence_package),
        "normalized_table_values": _read_json(normalized_table_values),
        "page_context_v2": _read_json(page_context_v2),
    }
    source_records = _collect_source_records(named_payloads)

    query_parts = list(source_summary.get("query_part_numbers") or source_payload.get("query_part_numbers") or [])
    if not query_parts:
        q = str(source_summary.get("question") or source_payload.get("question") or "")
        query_parts = re.findall(r"\b[A-Z0-9]{2,}-\d{2,}[A-Z0-9-]*\b", q.upper())
    query_parts = sorted(set(query_parts))

    source_records_context = source_payload.get("records") or []
    records: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []

    for idx, base in enumerate(source_records_context):
        record = dict(base)
        hits = _find_evidence_hits(record, query_parts, source_records, excerpt_window_chars=excerpt_window_chars)
        exact_sources = sorted(set(h.source for h in hits))
        matched_parts = sorted(set(h.match_part_number for h in hits))
        best_hit = hits[0] if hits else None
        untrusted_context_match = _untrusted_context_contains_query_part(record, query_parts)

        prior_role = str(record.get("graph_context_role") or record.get("enriched_context_role") or "")
        warning: list[str] = []
        if hits:
            proof_status = "PROVEN"
            proof_strength = "direct_proof"
            context_role = "direct_exact_match_proven"
        elif "direct" in prior_role:
            proof_status = "CANDIDATE"
            proof_strength = "direct_candidate_unproven"
            context_role = "direct_exact_match_candidate"
            warning.append("no_exact_part_text_found_in_trusted_sources")
        else:
            proof_status = "RELATED"
            proof_strength = record.get("proof_strength") or "related_candidate"
            context_role = record.get("graph_context_role") or "nearby_or_similar_evidence"
            warning.append("no_exact_part_text_found_in_trusted_sources")
        if untrusted_context_match and not hits:
            warning.append("query_part_found_only_in_untrusted_context_metadata_ignored")

        record.update(
            {
                "exact_row_proof_status": proof_status,
                "exact_row_context_role": context_role,
                "proof_strength": proof_strength,
                "query_part_numbers": query_parts,
                "matched_query_part_numbers": matched_parts,
                "exact_match_sources": exact_sources,
                "exact_match_hit_count": len(hits),
                "exact_row_text": best_hit.proof_text if best_hit else "",
                "exact_row_source": best_hit.source if best_hit else None,
                "exact_row_source_record_index": best_hit.record_index if best_hit else None,
                "untrusted_context_part_match_ignored": bool(untrusted_context_match and not hits),
                "trusted_exact_proof_sources": sorted(TRUSTED_EXACT_PROOF_SOURCES),
                "exact_row_proof_warnings": warning,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "postgres_write_attempt": False,
                "qdrant_write_attempt": False,
                "opensearch_write_attempt": False,
                "manual_review_required": False,
                "human_review_required": False,
                "unsafe_record": False,
            }
        )
        if proof_status == "PROVEN" and not record.get("exact_row_text"):
            violations.append(
                {
                    "citation_label": record.get("citation_label"),
                    "page_id": record.get("page_id"),
                    "violation": "proven_record_missing_exact_row_text",
                }
            )
        records.append(record)

    citation_map: list[dict[str, Any]] = []
    for r in records:
        citation_map.append(
            {
                "citation_label": r.get("citation_label"),
                "page_id": r.get("page_id"),
                "page_number": r.get("page_number"),
                "route": r.get("route"),
                "source_member": r.get("source_member") or r.get("raw_tiff_reference"),
                "raw_tiff_reference": r.get("raw_tiff_reference") or r.get("source_member"),
                "source_image_sha256": r.get("source_image_sha256"),
                "exact_row_proof_status": r.get("exact_row_proof_status"),
                "exact_row_context_role": r.get("exact_row_context_role"),
                "matched_query_part_numbers": r.get("matched_query_part_numbers"),
                "exact_match_sources": r.get("exact_match_sources"),
                "leiden_community_ids": r.get("leiden_community_ids") or [],
            }
        )

    question = str(source_summary.get("question") or source_payload.get("question") or "")
    prompt = _build_prompt(question, query_parts, records, citation_map)

    counts = _summary_counts(records)
    source_record_counts = {name: len(items) for name, items in source_records.items()}
    exact_source_counts: dict[str, int] = {}
    for r in records:
        for source in r.get("exact_match_sources") or []:
            exact_source_counts[source] = exact_source_counts.get(source, 0) + 1
    untrusted_context_part_match_ignored_count = sum(1 for r in records if r.get("untrusted_context_part_match_ignored"))

    summary = {
        "module": MODULE,
        "version": "v1",
        "source_graph_leiden_expander": str(graph_leiden_expander),
        "source_graph_leiden_expander_quality_status": source_quality,
        "source_record_count": len(source_records_context),
        "exact_row_proof_record_count": len(records),
        "citation_count": len(citation_map),
        "query_part_number_count": len(query_parts),
        "query_part_numbers": query_parts,
        "question": question,
        "context_prompt_char_count": len(prompt),
        "source_record_counts": source_record_counts,
        "exact_source_counts": exact_source_counts,
        "trusted_exact_proof_sources": sorted(TRUSTED_EXACT_PROOF_SOURCES),
        "untrusted_context_part_match_ignored_count": untrusted_context_part_match_ignored_count,
        "exact_row_proof_ready": True,
        "ready_for_gemma_exact_row_prompt": True,
        "dry_run_only": True,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "write_attempt_count": 0,
        "manual_review_required_count": 0,
        "human_review_required_count": 0,
        "unsafe_record_count": 0,
        "violation_record_count": len(violations),
        **counts,
    }

    failures: list[str] = []
    if require_source_quality_pass and source_quality != "PASS":
        failures.append("source_graph_leiden_expander_quality_not_pass")
    if len(violations) > 0:
        failures.append("violation_records_present")
    untrusted_proven_sources = [src for src in exact_source_counts if src not in TRUSTED_EXACT_PROOF_SOURCES]
    if untrusted_proven_sources:
        failures.append("untrusted_exact_proof_source_present")
        summary["untrusted_exact_proof_sources"] = sorted(untrusted_proven_sources)
    unsafe_count = sum(1 for r in records for key in SAFE_FALSE_KEYS if r.get(key) not in (False, 0, None))
    if unsafe_count:
        failures.append("unsafe_or_write_or_permission_flags_present")
        summary["unsafe_flag_value_count"] = unsafe_count

    quality_status = "PASS" if not failures else "FAIL"

    payload = {
        "schema_version": MODULE,
        "module": MODULE,
        "status": STATUS,
        "quality_status": quality_status,
        "created_at": _utc_now(),
        "summary": summary,
        "records": records,
        "citation_map": citation_map,
        "violations": violations,
        "llm_exact_row_context_prompt": prompt,
        "quality_failures": failures,
    }

    _write_json(output / REPORT_NAME, payload)
    _write_json(output / SUMMARY_NAME, summary)
    (output / PROMPT_NAME).write_text(prompt, encoding="utf-8")

    with (output / RECORDS_JSONL_NAME).open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    with (output / CITATION_MAP_NAME).open("w", encoding="utf-8") as f:
        for r in citation_map:
            f.write(json.dumps(r, sort_keys=True) + "\n")

    _write_csv(output / RECORDS_CSV_NAME, records)
    _write_csv(output / VIOLATIONS_CSV_NAME, violations)
    _write_markdown(output / MARKDOWN_NAME, payload)

    if quality:
        _write_json(output / QUALITY_NAME, {"quality_status": quality_status, "summary": summary, "failures": failures})
        print(f"Wrote: {output / QUALITY_NAME}")
    print(f"Status: {STATUS}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    keys: list[str] = []
    for r in records:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    if not keys:
        keys = ["empty"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (list, dict)) else v for k, v in r.items()})


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    s = payload["summary"]
    lines = [
        "# TRACE-Net Answer Context Exact Row Proof v1",
        "",
        f"Quality status: **{payload['quality_status']}**",
        "",
        "## Summary",
        "",
        f"- Records: {s.get('exact_row_proof_record_count')}",
        f"- Direct exact matches proven: {s.get('direct_exact_match_proven_count')}",
        f"- Direct candidates: {s.get('direct_exact_match_candidate_count')}",
        f"- Related/nearby evidence: {s.get('nearby_or_related_evidence_count')}",
        f"- Records with exact row text: {s.get('records_with_exact_row_text_count')}",
        f"- Violations: {s.get('violation_record_count')}",
        "",
        "Graph/Leiden context remains retrieval/ranking context only; exact row/text proof is required before a part-number claim may be treated as proven.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def check_answer_context_exact_row_proof_quality(
    *,
    report_path: str | Path,
    min_records: int = 1,
    min_citations: int = 1,
    min_prompt_chars: int = 500,
    min_direct_exact_proven: int | None = None,
    min_direct_candidates: int | None = None,
    max_violation_records: int = 0,
    require_source_quality_pass: bool = False,
    require_exact_row_prompt: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: int | None = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    write_json: bool = False,
) -> dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = payload.get("summary", {})
    failures: list[str] = []

    def fail_if(cond: bool, name: str) -> None:
        if cond:
            failures.append(name)

    fail_if(summary.get("exact_row_proof_record_count", 0) < min_records, "min_records")
    fail_if(summary.get("citation_count", 0) < min_citations, "min_citations")
    fail_if(summary.get("context_prompt_char_count", 0) < min_prompt_chars, "min_prompt_chars")
    if min_direct_exact_proven is not None:
        fail_if(summary.get("direct_exact_match_proven_count", 0) < min_direct_exact_proven, "min_direct_exact_proven")
    if min_direct_candidates is not None:
        fail_if(summary.get("direct_exact_match_candidate_count", 0) < min_direct_candidates, "min_direct_candidates")
    fail_if(summary.get("violation_record_count", 0) > max_violation_records, "max_violation_records")
    if require_source_quality_pass:
        fail_if(summary.get("source_graph_leiden_expander_quality_status") != "PASS", "source_quality_pass")
    if require_exact_row_prompt:
        fail_if(not payload.get("llm_exact_row_context_prompt"), "require_exact_row_prompt")
    if require_no_human_review_required:
        fail_if(summary.get("human_review_required_count", 0) != 0 or summary.get("manual_review_required_count", 0) != 0, "human_review_required")
    if max_unsafe is not None:
        fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "max_unsafe")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0 or summary.get("can_answer_directly_count", 0) != 0 or summary.get("can_prove_claims_count", 0) != 0, "answer_permission")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source_truth_mutation")
    if require_no_write_attempts:
        fail_if(summary.get("write_attempt_count", 0) != 0 or summary.get("postgres_write_attempt_count", 0) != 0 or summary.get("qdrant_write_attempt_count", 0) != 0 or summary.get("opensearch_write_attempt_count", 0) != 0, "write_attempts")

    quality_status = "PASS" if not failures else "FAIL"
    result = {"quality_status": quality_status, "summary": summary, "failures": failures}
    if write_json:
        out = path.with_name(QUALITY_NAME)
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net answer context exact row proof v1")
    parser.add_argument("--graph-leiden-expander", required=True)
    parser.add_argument("--ocr-route-scan-pack")
    parser.add_argument("--table-exact-search-adapter")
    parser.add_argument("--table-evidence-package")
    parser.add_argument("--normalized-table-values")
    parser.add_argument("--page-context-v2")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--excerpt-window-chars", type=int, default=1200)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_answer_context_exact_row_proof(
        graph_leiden_expander=args.graph_leiden_expander,
        ocr_route_scan_pack=args.ocr_route_scan_pack,
        table_exact_search_adapter=args.table_exact_search_adapter,
        table_evidence_package=args.table_evidence_package,
        normalized_table_values=args.normalized_table_values,
        page_context_v2=args.page_context_v2,
        output_dir=args.output_dir,
        excerpt_window_chars=args.excerpt_window_chars,
        require_source_quality_pass=args.require_source_quality_pass,
        quality=args.quality,
    )


def main_check(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net answer context exact row proof v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-prompt-chars", type=int, default=500)
    parser.add_argument("--min-direct-exact-proven", type=int)
    parser.add_argument("--min-direct-candidates", type=int)
    parser.add_argument("--max-violation-records", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-exact-row-prompt", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_answer_context_exact_row_proof_quality(**vars(args))


if __name__ == "__main__":
    main_build()
