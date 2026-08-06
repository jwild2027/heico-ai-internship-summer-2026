"""TRACE-Net Answer Context Anchor Injector v1.

Dry-run context-engineering module that injects exact part-number retrieval
anchors into the answer context before semantic, graph/Leiden, or Gemma drafting.

The injector consumes the part-number exact retrieval probe and produces a
ranked, citation-ready context seed where direct exact proof pages appear first,
reference/index hits appear second, and family/variant hits appear after that.
Existing graph/enriched context records can be retained as supporting evidence,
but they are never allowed to override exact-source anchors.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODULE = "trace_net_answer_context_anchor_injector_v1"
VERSION = "v1"

DIRECT_PROOF_ROLE = "direct_exact_match_proven"
REFERENCE_ROLES = {"exact_reference_candidate", "exact_metadata_candidate"}
FAMILY_ROLES = {"family_variant_candidate", "nearby_family_variant"}


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
        "anchor_role",
        "proof_role",
        "proof_strength",
        "source_name",
        "page_number",
        "page_id",
        "source_member",
        "matched_part_number",
        "context_priority",
        "anchor_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key, "") for key in fieldnames})


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _page_id(record: Dict[str, Any]) -> Optional[str]:
    value = record.get("page_id") or record.get("canonical_page_id") or record.get("source_page_id")
    return str(value) if value not in (None, "") else None


def _page_number(record: Dict[str, Any]) -> Optional[int]:
    return _as_int(record.get("page_number") or record.get("canonical_page_number") or record.get("page"))


def _source_member(record: Dict[str, Any]) -> Optional[str]:
    value = record.get("source_member") or record.get("raw_tiff_reference") or record.get("source_image_member")
    return str(value) if value not in (None, "") else None


def _dedupe_key(record: Dict[str, Any], *, include_source: bool = False) -> Tuple[Any, ...]:
    page_id = _page_id(record)
    page_number = _page_number(record)
    source_member = _source_member(record)
    source = record.get("source_name") if include_source else None
    field = record.get("field_path") if include_source else None
    matched = record.get("matched_part_number") or record.get("matched_query_part_number") or record.get("excerpt")
    if page_id:
        return ("page_id", page_id, source, field, matched if include_source else None)
    if page_number is not None:
        return ("page_number", page_number, source, field, matched if include_source else None)
    if source_member:
        return ("source_member", source_member, source, field, matched if include_source else None)
    return ("record", json.dumps(record, sort_keys=True)[:500], source, field)


def _records(payload: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    value = payload.get(key)
    return list(value) if isinstance(value, list) else []


def _extract_query_parts(payload: Dict[str, Any]) -> List[str]:
    summary = payload.get("summary") or {}
    parts = summary.get("query_part_numbers") or payload.get("query_part_numbers") or []
    return [str(part) for part in parts if part]


def _label_records(records: Sequence[Dict[str, Any]], *, prefix: str = "E") -> None:
    for idx, record in enumerate(records, start=1):
        record["citation_label"] = f"{prefix}{idx}"


def _direct_records(probe_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = _records(probe_payload, "direct_evidence_records")
    if not candidates:
        candidates = [r for r in _records(probe_payload, "records") if r.get("proof_role") == DIRECT_PROOF_ROLE]
    out: List[Dict[str, Any]] = []
    seen_pages: set[Tuple[Any, ...]] = set()
    for record in candidates:
        if record.get("proof_role") != DIRECT_PROOF_ROLE:
            continue
        # Prefer real page-level row/OCR/table proof for direct anchors. Page-less
        # table/index hits stay available as reference anchors instead.
        if _page_number(record) is None and not _source_member(record):
            continue
        key = _dedupe_key(record)
        if key in seen_pages:
            continue
        seen_pages.add(key)
        out.append(record)
    return out


def _reference_records(probe_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = _records(probe_payload, "reference_hit_records")
    if not candidates:
        candidates = [
            r
            for r in _records(probe_payload, "records")
            if r.get("proof_role") in REFERENCE_ROLES or r.get("hit_class") == "trusted_metadata_hit"
        ]
    out: List[Dict[str, Any]] = []
    seen: set[Tuple[Any, ...]] = set()
    for record in candidates:
        key = _dedupe_key(record, include_source=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _family_records(probe_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = _records(probe_payload, "family_variant_records") or _records(probe_payload, "family_variant_hit_records")
    if not candidates:
        candidates = [r for r in _records(probe_payload, "records") if r.get("hit_class") == "family_variant_hit"]
    out: List[Dict[str, Any]] = []
    seen: set[Tuple[Any, ...]] = set()
    for record in candidates:
        key = _dedupe_key(record, include_source=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _existing_context_records(path: Optional[Path | str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not path:
        return [], None
    payload = _read_json(path)
    status = payload.get("quality_status") or (payload.get("summary") or {}).get("quality_status")
    records = payload.get("records") or []
    return list(records) if isinstance(records, list) else [], status


def _make_anchor_record(
    source: Dict[str, Any],
    *,
    anchor_role: str,
    proof_strength: str,
    priority: float,
    query_parts: Sequence[str],
) -> Dict[str, Any]:
    excerpt = str(source.get("excerpt") or source.get("exact_row_text") or source.get("enriched_excerpt") or "")
    matched = source.get("matched_part_number") or source.get("matched_query_part_number")
    if not matched and query_parts:
        for part in query_parts:
            if part in excerpt:
                matched = part
                break
    return {
        "module": MODULE,
        "version": VERSION,
        "record_type": "answer_context_anchor_record",
        "anchor_status": "ANCHOR_INJECTED",
        "anchor_role": anchor_role,
        "proof_role": source.get("proof_role") or anchor_role,
        "proof_strength": proof_strength,
        "source_name": source.get("source_name"),
        "hit_class": source.get("hit_class"),
        "field_path": source.get("field_path"),
        "page_id": _page_id(source),
        "page_number": _page_number(source),
        "source_member": _source_member(source),
        "matched_part_number": matched,
        "query_part_numbers": list(query_parts),
        "excerpt": excerpt,
        "context_priority": priority,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "human_review_required": False,
        "manual_review_required": False,
        "unsafe_record": False,
    }


def _make_context_support_record(source: Dict[str, Any], *, priority: float, injected_page_keys: set[Tuple[Any, ...]]) -> Optional[Dict[str, Any]]:
    key = _dedupe_key(source)
    if key in injected_page_keys:
        return None
    excerpt = str(source.get("enriched_excerpt") or source.get("exact_row_text") or source.get("excerpt") or "")
    return {
        "module": MODULE,
        "version": VERSION,
        "record_type": "answer_context_anchor_record",
        "anchor_status": "RETAINED_SUPPORT_CONTEXT",
        "anchor_role": source.get("exact_row_context_role") or source.get("graph_context_role") or source.get("enriched_context_role") or "supporting_context",
        "proof_role": source.get("proof_role") or source.get("exact_row_proof_status") or source.get("graph_context_role"),
        "proof_strength": source.get("proof_strength") or "supporting_context",
        "source_name": source.get("source_name") or "existing_context",
        "hit_class": source.get("hit_class"),
        "field_path": source.get("field_path"),
        "page_id": _page_id(source),
        "page_number": _page_number(source),
        "source_member": _source_member(source),
        "matched_part_number": source.get("matched_part_number"),
        "query_part_numbers": source.get("query_part_numbers") or [],
        "excerpt": excerpt,
        "context_priority": priority,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "human_review_required": False,
        "manual_review_required": False,
        "unsafe_record": False,
    }


def _prompt(question: str, query_parts: Sequence[str], records: Sequence[Dict[str, Any]]) -> str:
    direct = [r for r in records if r.get("anchor_role") == "direct_exact_match_anchor"]
    refs = [r for r in records if r.get("anchor_role") == "exact_reference_anchor"]
    variants = [r for r in records if r.get("anchor_role") == "family_variant_anchor"]
    support = [r for r in records if r.get("anchor_status") == "RETAINED_SUPPORT_CONTEXT"]
    lines = [
        "You are TRACE-Net's context anchor injector for exact part-number questions.",
        "Use DIRECT EXACT ANCHORS before semantic retrieval, graph/Leiden, or similarity evidence.",
        "Graph/Leiden may rank nearby evidence, but exact source text proves part identity.",
        "Every factual claim in the final answer must cite the labels below.",
        "Do not invent effectivity, quantities, interchangeability, or applicability.",
        "",
        f"QUESTION: {question}",
        "QUERY_PART_NUMBERS: " + (", ".join(query_parts) if query_parts else "none"),
        "",
        "DIRECT EXACT ANCHORS:",
    ]
    if not direct:
        lines.append("None.")
    for record in direct:
        lines.append(
            f"{record['citation_label']}: role={record['anchor_role']}, proof={record['proof_strength']}, "
            f"page={record.get('page_number')}, page_id={record.get('page_id')}, "
            f"source={record.get('source_name')}, source_member={record.get('source_member')}. "
            f"Evidence: {record.get('excerpt', '')[:900]}"
        )
    lines.extend(["", "EXACT REFERENCE / INDEX ANCHORS:"])
    if not refs:
        lines.append("None.")
    for record in refs:
        lines.append(
            f"{record['citation_label']}: role={record['anchor_role']}, proof={record['proof_strength']}, "
            f"page={record.get('page_number')}, page_id={record.get('page_id')}, source={record.get('source_name')}. "
            f"Evidence: {record.get('excerpt', '')[:300]}"
        )
    lines.extend(["", "FAMILY / VARIANT ANCHORS:"])
    if not variants:
        lines.append("None.")
    for record in variants:
        lines.append(
            f"{record['citation_label']}: role={record['anchor_role']}, page={record.get('page_number')}, "
            f"page_id={record.get('page_id')}, source={record.get('source_name')}. Evidence: {record.get('excerpt', '')[:350]}"
        )
    lines.extend(["", "RETAINED SUPPORT CONTEXT:"])
    if not support:
        lines.append("None.")
    for record in support:
        lines.append(
            f"{record['citation_label']}: role={record['anchor_role']}, proof={record['proof_strength']}, "
            f"page={record.get('page_number')}, page_id={record.get('page_id')}. Evidence: {record.get('excerpt', '')[:350]}"
        )
    lines.extend([
        "",
        "SAFETY: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.",
    ])
    return "\n".join(lines)


def _citation_map(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "citation_label": r.get("citation_label"),
            "anchor_role": r.get("anchor_role"),
            "proof_strength": r.get("proof_strength"),
            "page_id": r.get("page_id"),
            "page_number": r.get("page_number"),
            "source_member": r.get("source_member"),
            "source_name": r.get("source_name"),
            "matched_part_number": r.get("matched_part_number"),
        }
        for r in records
    ]


def build_answer_context_anchor_injector(
    *,
    part_number_exact_retrieval_probe: Path | str,
    output_dir: Path | str,
    graph_leiden_expander: Optional[Path | str] = None,
    evidence_enricher: Optional[Path | str] = None,
    max_direct_anchors: int = 12,
    max_reference_anchors: int = 8,
    max_family_variants: int = 12,
    max_support_context: int = 8,
    require_source_quality_pass: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    probe_path = Path(part_number_exact_retrieval_probe)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    probe_payload = _read_json(probe_path)
    probe_summary = probe_payload.get("summary") or {}
    probe_status = probe_payload.get("quality_status")
    query_parts = _extract_query_parts(probe_payload)
    question = str(probe_summary.get("question") or probe_payload.get("question") or "")

    violations: List[Dict[str, Any]] = []
    if require_source_quality_pass and probe_status != "PASS":
        violations.append({"violation_type": "source_quality_not_pass", "source": str(probe_path), "quality_status": probe_status})

    direct_raw = _direct_records(probe_payload)[:max_direct_anchors]
    reference_raw = _reference_records(probe_payload)[:max_reference_anchors]
    family_raw = _family_records(probe_payload)[:max_family_variants]

    records: List[Dict[str, Any]] = []
    for record in direct_raw:
        records.append(
            _make_anchor_record(
                record,
                anchor_role="direct_exact_match_anchor",
                proof_strength="direct_exact_proof",
                priority=1000.0,
                query_parts=query_parts,
            )
        )
    for record in reference_raw:
        records.append(
            _make_anchor_record(
                record,
                anchor_role="exact_reference_anchor",
                proof_strength="exact_reference",
                priority=650.0,
                query_parts=query_parts,
            )
        )
    for record in family_raw:
        records.append(
            _make_anchor_record(
                record,
                anchor_role="family_variant_anchor",
                proof_strength="related_variant",
                priority=350.0,
                query_parts=query_parts,
            )
        )

    injected_page_keys = {_dedupe_key(r) for r in records if r.get("page_id") or r.get("page_number") or r.get("source_member")}
    support_source_statuses: Dict[str, Optional[str]] = {}
    support_raw: List[Dict[str, Any]] = []
    for name, path in [("graph_leiden_expander", graph_leiden_expander), ("evidence_enricher", evidence_enricher)]:
        source_records, source_status = _existing_context_records(path)
        if path:
            support_source_statuses[name] = source_status
            if require_source_quality_pass and source_status != "PASS":
                violations.append({"violation_type": "support_source_quality_not_pass", "source": str(path), "quality_status": source_status})
        support_raw.extend(source_records)

    retained_count = 0
    for record in support_raw:
        if retained_count >= max_support_context:
            break
        support = _make_context_support_record(record, priority=150.0, injected_page_keys=injected_page_keys)
        if support is None:
            continue
        records.append(support)
        retained_count += 1

    # Sort by priority, then page number for stable direct-first prompt.
    records.sort(key=lambda r: (-(r.get("context_priority") or 0), r.get("page_number") or 10**9, r.get("citation_label") or ""))
    _label_records(records)

    prompt = _prompt(question, query_parts, records)
    citations = _citation_map(records)
    direct_pages = sorted({r.get("page_number") for r in records if r.get("anchor_role") == "direct_exact_match_anchor" and r.get("page_number") is not None})
    direct_page_ids = sorted({r.get("page_id") for r in records if r.get("anchor_role") == "direct_exact_match_anchor" and r.get("page_id")})

    unsafe_count = sum(1 for r in records if r.get("unsafe_record"))
    answer_permission_count = sum(1 for r in records if r.get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for r in records if r.get("source_truth_mutation_allowed"))
    write_attempt_count = sum(
        1
        for r in records
        if r.get("postgres_write_attempt") or r.get("qdrant_write_attempt") or r.get("opensearch_write_attempt")
    )
    human_review_required_count = sum(1 for r in records if r.get("human_review_required") or r.get("manual_review_required"))

    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_part_number_exact_retrieval_probe": str(probe_path),
        "source_part_number_exact_retrieval_probe_quality_status": probe_status,
        "source_graph_leiden_expander": str(graph_leiden_expander) if graph_leiden_expander else None,
        "source_evidence_enricher": str(evidence_enricher) if evidence_enricher else None,
        "support_source_quality_statuses": support_source_statuses,
        "question": question,
        "query_part_numbers": query_parts,
        "query_part_number_count": len(query_parts),
        "anchor_injection_ready": len(direct_raw) > 0,
        "ready_for_graph_leiden_anchor_expansion": len(direct_raw) > 0,
        "ready_for_gemma_anchor_prompt": len(direct_raw) > 0 and len(prompt) > 0,
        "anchor_context_record_count": len(records),
        "direct_exact_anchor_count": sum(1 for r in records if r.get("anchor_role") == "direct_exact_match_anchor"),
        "direct_exact_anchor_page_count": len(direct_pages),
        "direct_exact_anchor_page_numbers": direct_pages,
        "direct_exact_anchor_page_ids": direct_page_ids,
        "exact_reference_anchor_count": sum(1 for r in records if r.get("anchor_role") == "exact_reference_anchor"),
        "family_variant_anchor_count": sum(1 for r in records if r.get("anchor_role") == "family_variant_anchor"),
        "retained_support_context_count": sum(1 for r in records if r.get("anchor_status") == "RETAINED_SUPPORT_CONTEXT"),
        "citation_count": len(citations),
        "context_anchor_prompt_char_count": len(prompt),
        "anchor_role_counts": dict(Counter(r.get("anchor_role") for r in records)),
        "proof_strength_counts": dict(Counter(r.get("proof_strength") for r in records)),
        "source_name_counts": dict(Counter(r.get("source_name") for r in records)),
        "source_probe_direct_exact_hit_count": probe_summary.get("exact_direct_hit_count"),
        "source_probe_exact_hit_count": probe_summary.get("exact_hit_count"),
        "source_probe_family_variant_hit_count": probe_summary.get("family_variant_hit_count"),
        "source_probe_direct_exact_page_numbers": probe_summary.get("direct_exact_page_numbers"),
        "dry_run_only": True,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "write_attempt_count": write_attempt_count,
        "human_review_required_count": human_review_required_count,
        "manual_review_required_count": 0,
        "unsafe_record_count": unsafe_count,
        "violation_record_count": len(violations),
    }

    quality_status = "PASS" if not violations and len(direct_raw) > 0 else "FAIL"
    payload = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "records": records,
        "citation_map": citations,
        "llm_context_prompt": prompt,
        "violation_records": violations,
    }

    report_path = output / f"{MODULE}.json"
    _write_json(report_path, payload)
    _write_json(output / f"{MODULE}_summary.json", summary)
    _write_jsonl(output / f"{MODULE}_records.jsonl", records)
    _write_jsonl(output / f"{MODULE}_citation_map.jsonl", citations)
    _write_csv(output / f"{MODULE}_records.csv", records)
    _write_csv(output / f"{MODULE}_violations.csv", violations)
    (output / f"{MODULE}_prompt.txt").write_text(prompt, encoding="utf-8")
    (output / f"{MODULE}.md").write_text(
        "# TRACE-Net Answer Context Anchor Injector v1\n\n"
        f"Quality status: {quality_status}\n\n"
        f"Direct exact anchor pages: {direct_pages}\n\n"
        f"Safety: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.\n",
        encoding="utf-8",
    )
    if quality:
        _write_json(output / f"{MODULE}_quality_check.json", {"quality_status": quality_status, "summary": summary, "failures": [] if quality_status == "PASS" else violations})

    print(f"Wrote: {output / f'{MODULE}_quality_check.json'}") if quality else None
    print("Status: TRACE_NET_ANSWER_CONTEXT_ANCHOR_INJECTOR_BUILT")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_answer_context_anchor_injector_quality(
    *,
    report_path: Path | str,
    write_json: bool = False,
    min_records: int = 0,
    min_direct_anchors: int = 0,
    min_direct_anchor_pages: int = 0,
    min_citations: int = 0,
    min_prompt_chars: int = 0,
    max_violation_records: Optional[int] = None,
    require_source_quality_pass: bool = False,
    require_anchor_injection_ready: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: Optional[int] = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> Dict[str, Any]:
    path = Path(report_path)
    payload = _read_json(path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    if len(payload.get("records") or []) < min_records:
        failures.append("min_records")
    if (summary.get("direct_exact_anchor_count") or 0) < min_direct_anchors:
        failures.append("min_direct_anchors")
    if (summary.get("direct_exact_anchor_page_count") or 0) < min_direct_anchor_pages:
        failures.append("min_direct_anchor_pages")
    if (summary.get("citation_count") or 0) < min_citations:
        failures.append("min_citations")
    if (summary.get("context_anchor_prompt_char_count") or 0) < min_prompt_chars:
        failures.append("min_prompt_chars")
    if max_violation_records is not None and (summary.get("violation_record_count") or 0) > max_violation_records:
        failures.append("max_violation_records")
    if require_source_quality_pass and summary.get("source_part_number_exact_retrieval_probe_quality_status") != "PASS":
        failures.append("require_source_quality_pass")
    if require_anchor_injection_ready and not summary.get("anchor_injection_ready"):
        failures.append("require_anchor_injection_ready")
    if require_no_human_review_required and (summary.get("human_review_required_count") or 0) > 0:
        failures.append("require_no_human_review_required")
    if max_unsafe is not None and (summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append("max_unsafe")
    if require_no_answer_permission and (summary.get("answer_permission_count") or 0) > 0:
        failures.append("require_no_answer_permission")
    if require_no_source_truth_mutation and (summary.get("source_truth_mutation_allowed_count") or 0) > 0:
        failures.append("require_no_source_truth_mutation")
    if require_no_write_attempts and (summary.get("write_attempt_count") or 0) > 0:
        failures.append("require_no_write_attempts")

    status = "PASS" if not failures else "FAIL"
    result = {"quality_status": status, "summary": summary, "failures": failures}
    if write_json:
        out = path.with_name(f"{MODULE}_quality_check.json")
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures))
    return result


def main_build(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net answer context anchor injector v1.")
    parser.add_argument("--part-number-exact-retrieval-probe", required=True, type=Path)
    parser.add_argument("--graph-leiden-expander", type=Path)
    parser.add_argument("--evidence-enricher", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-direct-anchors", type=int, default=12)
    parser.add_argument("--max-reference-anchors", type=int, default=8)
    parser.add_argument("--max-family-variants", type=int, default=12)
    parser.add_argument("--max-support-context", type=int, default=8)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_answer_context_anchor_injector(
        part_number_exact_retrieval_probe=args.part_number_exact_retrieval_probe,
        graph_leiden_expander=args.graph_leiden_expander,
        evidence_enricher=args.evidence_enricher,
        output_dir=args.output_dir,
        max_direct_anchors=args.max_direct_anchors,
        max_reference_anchors=args.max_reference_anchors,
        max_family_variants=args.max_family_variants,
        max_support_context=args.max_support_context,
        require_source_quality_pass=args.require_source_quality_pass,
        quality=args.quality,
    )


def main_check(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net answer context anchor injector v1 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=0)
    parser.add_argument("--min-direct-anchors", type=int, default=0)
    parser.add_argument("--min-direct-anchor-pages", type=int, default=0)
    parser.add_argument("--min-citations", type=int, default=0)
    parser.add_argument("--min-prompt-chars", type=int, default=0)
    parser.add_argument("--max-violation-records", type=int)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-anchor-injection-ready", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_answer_context_anchor_injector_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_direct_anchors=args.min_direct_anchors,
        min_direct_anchor_pages=args.min_direct_anchor_pages,
        min_citations=args.min_citations,
        min_prompt_chars=args.min_prompt_chars,
        max_violation_records=args.max_violation_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_anchor_injection_ready=args.require_anchor_injection_ready,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":  # pragma: no cover
    main_build()
