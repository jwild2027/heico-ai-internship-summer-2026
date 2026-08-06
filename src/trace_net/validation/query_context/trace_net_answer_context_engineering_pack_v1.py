from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODULE = "trace_net_answer_context_engineering_pack_v1"
VERSION = "v1"
STATUS = "TRACE_NET_ANSWER_CONTEXT_ENGINEERING_PACK_BUILT"

PART_RE = re.compile(r"\b\d{2,4}-\d{3,6}(?:-\d{2,4})?\b")


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
    keys: List[str] = []
    for record in records:
        for key in record.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for record in records:
            row: Dict[str, Any] = {}
            for key in keys:
                value = record.get(key)
                if isinstance(value, (dict, list)):
                    row[key] = json.dumps(value, sort_keys=True)
                else:
                    row[key] = value
            writer.writerow(row)


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _question_part_numbers(question: str) -> List[str]:
    seen: List[str] = []
    for match in PART_RE.findall(question or ""):
        if match not in seen:
            seen.append(match)
    return seen


def _record_text_blob(record: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in [
        "ocr_excerpt",
        "excerpt",
        "text",
        "chunk_text",
        "summary",
        "retrieval_reasons",
        "visible_text_or_labels",
        "part_numbers",
        "matched_terms",
    ]:
        value = record.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (list, dict)):
            parts.append(json.dumps(value, sort_keys=True))
    return "\n".join(parts)


def _load_retrieval_evidence(raw_payload: Dict[str, Any], report_path: Path) -> List[Dict[str, Any]]:
    candidates = [
        raw_payload.get("retrieval_evidence_records"),
        raw_payload.get("retrieval_records"),
        raw_payload.get("evidence_records"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [r for r in candidate if isinstance(r, dict)]

    # Fall back to sibling JSONL emitted by the raw-to-answer smoke runner.
    for name in [
        "trace_net_raw_to_answer_e2e_smoke_native_v1_retrieval_evidence.jsonl",
        "trace_net_raw_to_answer_e2e_smoke_v1_retrieval_evidence.jsonl",
    ]:
        path = report_path.parent / name
        if path.exists():
            records: List[Dict[str, Any]] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    if isinstance(item, dict):
                        records.append(item)
            return records
    return []


def _source_quality_pass(summary: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    if payload.get("quality_status") == "PASS":
        return True
    if summary.get("all_stage_quality_pass") is True:
        return True
    return False


def _classify_question_intent(question: str) -> Dict[str, Any]:
    part_numbers = _question_part_numbers(question)
    lower = question.lower()
    if part_numbers and any(word in lower for word in ["nearby", "similar", "around", "related"]):
        intent = "part_number_with_nearby_similarity"
    elif part_numbers:
        intent = "part_number_lookup"
    elif any(word in lower for word in ["figure", "diagram", "image", "callout"]):
        intent = "visual_or_callout_lookup"
    elif any(word in lower for word in ["table", "list", "index"]):
        intent = "table_or_index_lookup"
    else:
        intent = "general_manual_lookup"
    return {
        "question_intent": intent,
        "query_part_numbers": part_numbers,
        "query_part_number_count": len(part_numbers),
    }


def _normalize_evidence_record(record: Dict[str, Any], index: int, query_part_numbers: Sequence[str]) -> Dict[str, Any]:
    page_number = _to_int(record.get("page_number") or record.get("page"), 0)
    route = _first_text(record.get("route"), record.get("final_validated_operational_route"), record.get("source_route"))
    targets = record.get("targets") or record.get("loader_targets") or record.get("contract_ready_targets") or []
    if isinstance(targets, str):
        targets_list = [x.strip() for x in re.split(r"[,;]", targets) if x.strip()]
    elif isinstance(targets, list):
        targets_list = [str(x) for x in targets]
    else:
        targets_list = []
    text_blob = _record_text_blob(record)
    evidence_part_numbers = list(dict.fromkeys(PART_RE.findall(text_blob)))
    direct_part_numbers = [p for p in query_part_numbers if p in text_blob]
    score = _to_float(record.get("retrieval_score") or record.get("score"), 0.0)
    citation_label = f"E{index + 1}"
    return {
        "citation_label": citation_label,
        "source_rank": index + 1,
        "page_id": record.get("page_id"),
        "page_number": page_number,
        "route": route,
        "targets": targets_list,
        "retrieval_score": score,
        "source_member": record.get("source_member"),
        "raw_tiff_reference": record.get("raw_tiff_reference") or record.get("source_member"),
        "source_image_sha256": record.get("source_image_sha256"),
        "ocr_excerpt": _first_text(record.get("ocr_excerpt"), record.get("excerpt"), record.get("text")),
        "retrieval_reasons": record.get("retrieval_reasons") or record.get("reasons") or [],
        "evidence_part_numbers": evidence_part_numbers,
        "direct_part_numbers": direct_part_numbers,
        "has_direct_part_number_match": bool(direct_part_numbers),
        "lineage_ready": bool(record.get("page_id") and (record.get("source_member") or record.get("raw_tiff_reference")) and record.get("source_image_sha256")),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "dry_run_only": True,
    }


def _assign_context_roles(records: List[Dict[str, Any]], query_part_numbers: Sequence[str], max_direct: int, max_nearby: int) -> List[Dict[str, Any]]:
    direct_pages = {r["page_number"] for r in records if r.get("has_direct_part_number_match") and r.get("page_number")}
    table_records = [r for r in records if r.get("route") == "table"]
    for record in records:
        role = "supporting_evidence"
        reasons: List[str] = []
        if record.get("has_direct_part_number_match"):
            role = "direct_match_evidence"
            reasons.append("query_part_number_found_in_evidence_text")
        elif direct_pages and record.get("page_number"):
            distance = min(abs(record["page_number"] - page) for page in direct_pages)
            if distance <= 15 and record.get("route") == "table":
                role = "nearby_table_evidence"
                reasons.append(f"table_page_within_{distance}_pages_of_direct_match")
        elif query_part_numbers and record.get("route") == "table":
            role = "similar_table_evidence"
            reasons.append("table_evidence_ranked_for_part_number_query")
        elif record.get("route") == "image":
            role = "visual_observation_evidence"
            reasons.append("image_route_evidence_is_observation_not_source_truth")
        elif record.get("route") == "plain_text":
            role = "plain_text_context_evidence"
            reasons.append("plain_text_context_support")
        record["context_role"] = role
        record["context_role_reasons"] = reasons

    # If no exact direct match exists, reserve the highest-ranked table evidence as direct candidate.
    if not any(r.get("context_role") == "direct_match_evidence" for r in records) and records:
        best = sorted(table_records or records, key=lambda r: (-_to_float(r.get("retrieval_score")), r.get("source_rank") or 9999))[0]
        best["context_role"] = "direct_evidence_candidate"
        best["context_role_reasons"] = ["no_exact_part_number_match_found_in_payload_excerpt_top_ranked_candidate"]

    direct_seen = 0
    nearby_seen = 0
    for record in records:
        if record["context_role"] in {"direct_match_evidence", "direct_evidence_candidate"}:
            direct_seen += 1
            if direct_seen > max_direct:
                record["context_role"] = "overflow_supporting_evidence"
                record.setdefault("context_role_reasons", []).append("max_direct_evidence_limit_exceeded")
        elif record["context_role"] in {"nearby_table_evidence", "similar_table_evidence", "supporting_evidence"}:
            nearby_seen += 1
            if nearby_seen > max_nearby:
                record["context_role"] = "overflow_supporting_evidence"
                record.setdefault("context_role_reasons", []).append("max_nearby_evidence_limit_exceeded")
    return records


def _citation_map(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    citations: List[Dict[str, Any]] = []
    for record in records:
        citations.append({
            "citation_label": record.get("citation_label"),
            "page_id": record.get("page_id"),
            "page_number": record.get("page_number"),
            "source_member": record.get("source_member"),
            "raw_tiff_reference": record.get("raw_tiff_reference"),
            "source_image_sha256": record.get("source_image_sha256"),
            "route": record.get("route"),
            "targets": record.get("targets"),
            "retrieval_score": record.get("retrieval_score"),
            "context_role": record.get("context_role"),
        })
    return citations


def _format_evidence_line(record: Dict[str, Any]) -> str:
    excerpt = (record.get("ocr_excerpt") or "").replace("\n", " ").strip()
    if len(excerpt) > 260:
        excerpt = excerpt[:257] + "..."
    if not excerpt:
        excerpt = "No text excerpt available in payload; use citation metadata only."
    return (
        f"{record.get('citation_label')}: page={record.get('page_number')}, "
        f"page_id={record.get('page_id')}, route={record.get('route')}, "
        f"targets={','.join(record.get('targets') or [])}, score={record.get('retrieval_score')}. "
        f"Excerpt: {excerpt}"
    )


def _build_prompt(question: str, intent: Dict[str, Any], records: Sequence[Dict[str, Any]], citation_map: Sequence[Dict[str, Any]]) -> str:
    direct = [r for r in records if r.get("context_role") in {"direct_match_evidence", "direct_evidence_candidate"}]
    nearby = [r for r in records if r.get("context_role") in {"nearby_table_evidence", "similar_table_evidence"}]
    support = [r for r in records if r.get("context_role") not in {"direct_match_evidence", "direct_evidence_candidate", "nearby_table_evidence", "similar_table_evidence", "overflow_supporting_evidence"}]

    lines = [
        "You are TRACE-Net's final answer drafter for scanned technical manuals.",
        "Use only the provided evidence. Do not invent part numbers, pages, effectivity, quantities, or applicability.",
        "Every factual claim must cite one or more citation labels like [E1].",
        "If direct evidence does not prove the requested part, say that the result is a candidate and explain the limitation.",
        "Keep the answer short and operational: direct finding, nearby/similar evidence, citations, and safety note.",
        "",
        f"QUESTION: {question}",
        f"QUESTION_INTENT: {intent.get('question_intent')}",
        f"QUERY_PART_NUMBERS: {', '.join(intent.get('query_part_numbers') or []) or 'none'}",
        "",
        "DIRECT EVIDENCE:",
    ]
    lines.extend([_format_evidence_line(r) for r in direct] or ["None."])
    lines.append("")
    lines.append("NEARBY / SIMILAR EVIDENCE:")
    lines.extend([_format_evidence_line(r) for r in nearby] or ["None."])
    lines.append("")
    lines.append("OTHER SUPPORTING EVIDENCE:")
    lines.extend([_format_evidence_line(r) for r in support[:5]] or ["None."])
    lines.append("")
    lines.append("CITATION MAP:")
    for citation in citation_map:
        lines.append(
            f"{citation.get('citation_label')} => page_id={citation.get('page_id')}, "
            f"page={citation.get('page_number')}, source_member={citation.get('source_member')}, "
            f"sha256={citation.get('source_image_sha256')}"
        )
    lines.append("")
    lines.append("SAFETY: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.")
    return "\n".join(lines)


def _build_markdown(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# TRACE-Net Answer Context Engineering Pack v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Question intent: `{summary.get('question_intent')}`",
        f"- Retrieval evidence records: `{summary.get('retrieval_evidence_count')}`",
        f"- Direct evidence records: `{summary.get('direct_evidence_count')}`",
        f"- Nearby/similar evidence records: `{summary.get('nearby_or_similar_evidence_count')}`",
        f"- Citation count: `{summary.get('citation_count')}`",
        f"- Prompt chars: `{summary.get('context_prompt_char_count')}`",
        f"- Violations: `{summary.get('violation_record_count')}`",
        "",
        "## Prompt Preview",
        "",
        "```text",
        (payload.get("llm_context_prompt") or "")[:5000],
        "```",
    ]
    return "\n".join(lines)


def build_answer_context_engineering_pack(
    *,
    raw_to_answer_report: Path | str,
    output_dir: Path | str,
    max_direct_evidence: int = 5,
    max_nearby_evidence: int = 8,
    require_source_quality_pass: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    report_path = Path(raw_to_answer_report)
    out = Path(output_dir)
    raw_payload = _read_json(report_path)
    raw_summary = raw_payload.get("summary") or {}
    question = _first_text(raw_summary.get("question"), raw_payload.get("question"))
    intent = _classify_question_intent(question)

    evidence = _load_retrieval_evidence(raw_payload, report_path)
    normalized = [_normalize_evidence_record(record, i, intent["query_part_numbers"]) for i, record in enumerate(evidence)]
    normalized.sort(key=lambda r: (r.get("source_rank") or 999999))
    normalized = _assign_context_roles(normalized, intent["query_part_numbers"], max_direct_evidence, max_nearby_evidence)

    citations = _citation_map(normalized)
    prompt = _build_prompt(question, intent, normalized, citations)

    violation_records: List[Dict[str, Any]] = []
    for record in normalized:
        violations: List[str] = []
        if not record.get("lineage_ready"):
            violations.append("missing_source_lineage")
        if record.get("answer_permission") is not False:
            violations.append("answer_permission_not_false")
        if record.get("source_truth_mutation_allowed") is not False:
            violations.append("source_truth_mutation_not_false")
        if record.get("route") == "blank":
            violations.append("blank_route_in_answer_context")
        if violations:
            bad = dict(record)
            bad["context_violations"] = violations
            violation_records.append(bad)

    source_quality_pass = _source_quality_pass(raw_summary, raw_payload)
    direct_count = sum(1 for r in normalized if r.get("context_role") in {"direct_match_evidence", "direct_evidence_candidate"})
    nearby_count = sum(1 for r in normalized if r.get("context_role") in {"nearby_table_evidence", "similar_table_evidence"})
    citation_count = len(citations)
    unsafe_count = _to_int(raw_summary.get("unsafe_record_count"), 0)
    answer_permission_count = 0
    source_truth_mutation_allowed_count = 0
    write_attempt_count = _to_int(raw_summary.get("write_attempt_count"), 0)
    human_review_required_count = _to_int(raw_summary.get("human_review_required_count"), 0)

    failures: List[str] = []
    if require_source_quality_pass and not source_quality_pass:
        failures.append("source raw-to-answer report is not quality PASS")
    if not question:
        failures.append("missing question")
    if not normalized:
        failures.append("no retrieval evidence records available")
    if citation_count == 0:
        failures.append("no citation map records")
    if violation_records:
        failures.append("context violation records present")
    if not prompt.strip():
        failures.append("empty context prompt")
    if unsafe_count:
        failures.append("unsafe records present")
    if answer_permission_count:
        failures.append("answer permission present")
    if source_truth_mutation_allowed_count:
        failures.append("source-truth mutation allowed")
    if write_attempt_count:
        failures.append("write attempts present")
    if human_review_required_count:
        failures.append("human review required")

    quality_status = "FAIL" if failures else "PASS"
    summary = {
        "module": MODULE,
        "version": VERSION,
        "source_raw_to_answer_report": str(report_path),
        "source_raw_to_answer_quality_status": raw_payload.get("quality_status"),
        "source_all_stage_quality_pass": raw_summary.get("all_stage_quality_pass"),
        "question": question,
        "question_intent": intent["question_intent"],
        "query_part_number_count": intent["query_part_number_count"],
        "query_part_numbers": intent["query_part_numbers"],
        "retrieval_evidence_count": len(evidence),
        "context_pack_record_count": len(normalized),
        "direct_evidence_count": direct_count,
        "nearby_or_similar_evidence_count": nearby_count,
        "citation_count": citation_count,
        "context_prompt_char_count": len(prompt),
        "lineage_ready_count": sum(1 for r in normalized if r.get("lineage_ready")),
        "missing_lineage_count": sum(1 for r in normalized if not r.get("lineage_ready")),
        "violation_record_count": len(violation_records),
        "unsafe_record_count": unsafe_count,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "write_attempt_count": write_attempt_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "human_review_required_count": human_review_required_count,
        "manual_review_required_count": 0,
        "dry_run_only": True,
        "answer_context_ready": quality_status == "PASS",
        "ready_for_gemma_context_prompt": quality_status == "PASS",
        "max_direct_evidence": max_direct_evidence,
        "max_nearby_evidence": max_nearby_evidence,
    }

    payload = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS,
        "quality_status": quality_status,
        "failures": failures,
        "summary": summary,
        "question_analysis": intent,
        "records": normalized,
        "citation_map": citations,
        "violation_records": violation_records,
        "llm_context_prompt": prompt,
        "answer_constraints": {
            "use_only_provided_evidence": True,
            "cite_every_factual_claim": True,
            "do_not_use_blocked_or_blank_pages": True,
            "state_limitations_for_candidates": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "dry_run_only": True,
        },
    }

    out.mkdir(parents=True, exist_ok=True)
    report = out / "trace_net_answer_context_engineering_pack_v1.json"
    _write_json(report, payload)
    _write_json(out / "trace_net_answer_context_engineering_pack_v1_summary.json", summary)
    _write_jsonl(out / "trace_net_answer_context_engineering_pack_v1_records.jsonl", normalized)
    _write_csv(out / "trace_net_answer_context_engineering_pack_v1_records.csv", normalized)
    _write_jsonl(out / "trace_net_answer_context_engineering_pack_v1_citation_map.jsonl", citations)
    _write_csv(out / "trace_net_answer_context_engineering_pack_v1_violations.csv", violation_records)
    (out / "trace_net_answer_context_engineering_pack_v1_prompt.txt").write_text(prompt, encoding="utf-8")
    (out / "trace_net_answer_context_engineering_pack_v1.md").write_text(_build_markdown(payload), encoding="utf-8")

    if quality:
        quality_path = out / "trace_net_answer_context_engineering_pack_v1_quality_check.json"
        _write_json(quality_path, {"quality_status": quality_status, "summary": summary, "failures": failures})
        print(f"Wrote: {quality_path}")

    print(f"Status: {STATUS}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return payload


def check_quality(
    *,
    report_path: Path | str,
    write_json: bool = False,
    min_records: int = 1,
    min_retrieval_evidence: int = 1,
    min_citations: int = 1,
    min_direct_evidence: int = 0,
    min_prompt_chars: int = 200,
    max_violation_records: int = 0,
    require_source_quality_pass: bool = False,
    require_context_prompt: bool = False,
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

    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if _to_int(summary.get("context_pack_record_count"), 0) < min_records:
        failures.append("not enough context pack records")
    if _to_int(summary.get("retrieval_evidence_count"), 0) < min_retrieval_evidence:
        failures.append("not enough retrieval evidence")
    if _to_int(summary.get("citation_count"), 0) < min_citations:
        failures.append("not enough citations")
    if _to_int(summary.get("direct_evidence_count"), 0) < min_direct_evidence:
        failures.append("not enough direct evidence")
    if _to_int(summary.get("context_prompt_char_count"), 0) < min_prompt_chars:
        failures.append("context prompt is too short")
    if _to_int(summary.get("violation_record_count"), 0) > max_violation_records:
        failures.append("too many violation records")
    if require_source_quality_pass:
        if summary.get("source_raw_to_answer_quality_status") != "PASS" and summary.get("source_all_stage_quality_pass") is not True:
            failures.append("source quality pass required")
    if require_context_prompt and not payload.get("llm_context_prompt"):
        failures.append("context prompt required")
    if require_no_human_review_required and _to_int(summary.get("human_review_required_count"), 0) != 0:
        failures.append("human review required")
    if max_unsafe is not None and _to_int(summary.get("unsafe_record_count"), 0) > max_unsafe:
        failures.append("unsafe record count exceeds maximum")
    if require_no_answer_permission and _to_int(summary.get("answer_permission_count"), 0) != 0:
        failures.append("answer permission count is not zero")
    if require_no_source_truth_mutation and _to_int(summary.get("source_truth_mutation_allowed_count"), 0) != 0:
        failures.append("source truth mutation allowed count is not zero")
    if require_no_write_attempts:
        for key in ["write_attempt_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]:
            if _to_int(summary.get(key), 0) != 0:
                failures.append(f"{key} is not zero")

    quality_status = "FAIL" if failures else "PASS"
    result = {"quality_status": quality_status, "summary": summary, "failures": failures}
    if write_json:
        out = path.with_name("trace_net_answer_context_engineering_pack_v1_quality_check.json")
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net answer context engineering pack v1")
    parser.add_argument("--raw-to-answer-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-direct-evidence", type=int, default=5)
    parser.add_argument("--max-nearby-evidence", type=int, default=8)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_answer_context_engineering_pack(
        raw_to_answer_report=args.raw_to_answer_report,
        output_dir=args.output_dir,
        max_direct_evidence=args.max_direct_evidence,
        max_nearby_evidence=args.max_nearby_evidence,
        require_source_quality_pass=args.require_source_quality_pass,
        quality=args.quality,
    )


def main_check(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net answer context engineering pack v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-retrieval-evidence", type=int, default=1)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-direct-evidence", type=int, default=0)
    parser.add_argument("--min-prompt-chars", type=int, default=200)
    parser.add_argument("--max-violation-records", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-context-prompt", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=None)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_retrieval_evidence=args.min_retrieval_evidence,
        min_citations=args.min_citations,
        min_direct_evidence=args.min_direct_evidence,
        min_prompt_chars=args.min_prompt_chars,
        max_violation_records=args.max_violation_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_context_prompt=args.require_context_prompt,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":  # pragma: no cover
    main_build()
