from __future__ import annotations

import argparse
import csv
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODULE = "trace_net_fast_answer_composer_v1"
VERSION = "v1"
PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")


class FastAnswerComposerError(RuntimeError):
    pass


def _read_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8", errors="replace"))


def _write_json(path: str | Path, payload: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _label(record: Dict[str, Any]) -> str:
    return _safe_str(record.get("citation_label") or record.get("label") or "E?").strip() or "E?"


def _page(record: Dict[str, Any]) -> str:
    value = record.get("page_number") or record.get("canonical_page_number") or "?"
    return str(value)


def _excerpt(record: Dict[str, Any]) -> str:
    text = record.get("excerpt") or record.get("enriched_excerpt") or record.get("exact_row_text") or ""
    return re.sub(r"\s+", " ", str(text)).strip()


def _cit(label: str) -> str:
    if label.startswith("[") and label.endswith("]"):
        return label
    return f"[{label}]"


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for v in values:
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _query_parts_from_payload(payload: Dict[str, Any], question: Optional[str], part_number: Optional[str]) -> List[str]:
    parts: List[str] = []
    if part_number:
        parts.append(part_number)
    summary = payload.get("summary") or {}
    for value in summary.get("query_part_numbers") or payload.get("query_part_numbers") or []:
        if isinstance(value, str):
            parts.append(value)
    q = question or summary.get("question") or payload.get("question") or ""
    parts.extend(PART_RE.findall(str(q)))
    return _unique(parts)


def _source_quality_status(payload: Dict[str, Any]) -> str:
    return _safe_str(payload.get("quality_status") or (payload.get("summary") or {}).get("quality_status") or "UNKNOWN")


def _extract_direct_description(part_number: str, records: Sequence[Dict[str, Any]]) -> str:
    """Extract a short description following the exact part number in OCR/table text."""
    candidates: List[str] = []
    part_pattern = re.escape(part_number)
    # Capture text after the part until a stock/effectivity marker, figure item, or a long run of dots.
    patterns = [
        re.compile(part_pattern + r"\s*[\.\-–—|]*\s*([A-Z][A-Z0-9, /\-]{3,80}?)(?:\.{2,}|\s+VS\d|\s+\d{3}/\d{3}|\s+ATTACHING|\s+\d\s|\||$)", re.I),
        re.compile(part_pattern + r"\s*[\.\-–—|]*\s*([^|]{3,80})", re.I),
    ]
    for r in records:
        text = _excerpt(r)
        for pat in patterns:
            m = pat.search(text)
            if not m:
                continue
            raw = m.group(1)
            cleaned = re.sub(r"\s+", " ", raw)
            cleaned = re.sub(r"[\.·]{2,}.*$", "", cleaned)
            cleaned = cleaned.strip(" .;:,|-/")
            # Avoid OCR junk and short false captures.
            if len(cleaned) >= 4 and PART_RE.search(cleaned) is None:
                candidates.append(cleaned.upper())
    if not candidates:
        return "direct exact evidence"
    # Choose the most frequent normalized candidate; shortest helpful description wins ties.
    counts: Dict[str, int] = {}
    for c in candidates:
        counts[c] = counts.get(c, 0) + 1
    return sorted(counts, key=lambda x: (-counts[x], len(x), x))[0]


def _record_part_numbers(records: Sequence[Dict[str, Any]]) -> OrderedDict[str, List[str]]:
    variant_map: OrderedDict[str, List[str]] = OrderedDict()
    for r in records:
        text = _excerpt(r)
        for p in _unique(PART_RE.findall(text)):
            variant_map.setdefault(p, []).append(_label(r))
    return variant_map


def _csv_scalar(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def _write_records_csv(path: str | Path, records: Sequence[Dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "citation_label",
        "composer_role",
        "source_anchor_aware_role",
        "proof_strength",
        "anchor_relation_type",
        "page_number",
        "page_id",
        "source_member",
        "part_numbers",
        "sentence_use",
    ]
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow({k: _csv_scalar(r.get(k)) for k in fieldnames})


def _write_jsonl(path: str | Path, records: Sequence[Dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def _make_direct_sentence(part: str, description: str, direct_records: Sequence[Dict[str, Any]], max_direct: int) -> str:
    refs = [f"page {_page(r)} {_cit(_label(r))}" for r in direct_records[:max_direct]]
    if not refs:
        return f"TRACE-Net did not find a direct exact anchor for part number {part}."
    return (
        f"TRACE-Net found direct exact evidence for part number {part}; "
        f"the cited direct anchors list it as \u201c{description}\u201d on "
        + ", ".join(refs)
        + "."
    )


def _make_variant_sentence(part: str, variant_records: Sequence[Dict[str, Any]], max_variants: int, max_labels_per_variant: int) -> Tuple[str, Dict[str, List[str]]]:
    variant_map = _record_part_numbers(variant_records)
    variant_map.pop(part, None)
    # Keep in order discovered from source records.
    limited = OrderedDict()
    for vp, labels in variant_map.items():
        if len(limited) >= max_variants:
            break
        limited[vp] = _unique(labels)[:max_labels_per_variant]
    if not limited:
        return "", {}
    bits = []
    for vp, labels in limited.items():
        bits.append(f"{vp} ({', '.join(_cit(x) for x in labels)})")
    return "Nearby or family-related variants in the provided context include " + "; ".join(bits) + ".", dict(limited)


def _make_neighbor_sentence(neighbor_records: Sequence[Dict[str, Any]], max_neighbors: int) -> str:
    if not neighbor_records:
        return ""
    refs = [f"page {_page(r)} {_cit(_label(r))}" for r in neighbor_records[:max_neighbors]]
    if len(refs) == 1:
        return f"TRACE-Net retained one same-anchor Leiden-community neighbor as weak related context on {refs[0]}."
    return "TRACE-Net retained same-anchor Leiden-community neighbors as weak related context on " + ", ".join(refs) + "."


def _make_scope_sentence(part: str, direct_records: Sequence[Dict[str, Any]], max_direct: int) -> str:
    labels = ", ".join(_cit(_label(r)) for r in direct_records[:max_direct])
    if labels:
        return f"The related-variant and graph/Leiden evidence should be used only as nearby context for this answer; the cited direct anchors are the proof for {part} {labels}."
    return "The related-variant and graph/Leiden evidence should be used only as nearby context for this answer."


def _make_safety_sentence(direct_records: Sequence[Dict[str, Any]], max_direct: int) -> str:
    labels = ", ".join(_cit(_label(r)) for r in direct_records[:max_direct])
    suffix = f" {labels}" if labels else ""
    return f"Safety: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true{suffix}."


def _derive_composer_records(
    direct_records: Sequence[Dict[str, Any]],
    variant_records: Sequence[Dict[str, Any]],
    neighbor_records: Sequence[Dict[str, Any]],
    support_records: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    groups = [
        ("direct_exact_answer_evidence", direct_records, "direct proof sentence"),
        ("related_variant_answer_evidence", variant_records, "variant sentence"),
        ("weak_graph_context_evidence", neighbor_records, "weak related context sentence"),
        ("retained_low_priority_support", support_records, "not used in main answer"),
    ]
    for role, records, sentence_use in groups:
        for r in records:
            clone = dict(r)
            clone["composer_role"] = role
            clone["source_anchor_aware_role"] = r.get("anchor_aware_role")
            clone["part_numbers"] = _unique(PART_RE.findall(_excerpt(r)))
            clone["sentence_use"] = sentence_use
            out.append(clone)
    return out


def _find_violations(answer: str, summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []
    if summary.get("direct_exact_answer_label_count", 0) > 0 and summary.get("direct_exact_answer_citation_count", 0) <= 0:
        violations.append({"severity": "critical", "code": "missing_direct_citations", "message": "Direct proof labels exist but answer did not cite them."})
    if summary.get("query_part_number_count", 0) > 0:
        for part in summary.get("query_part_numbers") or []:
            if part not in answer:
                violations.append({"severity": "high", "code": "missing_query_part", "message": f"Answer does not mention queried part number {part}."})
    lower = answer.lower()
    # Avoid the words that the quality gate treats as risky unless future proof fields exist.
    for term in ["interchangeable", "replacement", "replacements", "substitute", "substitutes", "approved substitute", "approved replacement"]:
        if term in lower:
            violations.append({"severity": "medium", "code": "risky_substitution_word", "message": f"Answer contains risky unsupported term: {term}."})
    return violations


def build_fast_answer_composer(
    *,
    context_pack: str | Path,
    output_dir: str | Path,
    question: Optional[str] = None,
    part_number: Optional[str] = None,
    max_direct_anchors: int = 8,
    max_variants: int = 6,
    max_labels_per_variant: int = 3,
    max_neighbors: int = 1,
    require_source_quality_pass: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    context_payload = _read_json(context_pack)
    source_quality = _source_quality_status(context_payload)
    if require_source_quality_pass and source_quality != "PASS":
        raise FastAnswerComposerError(f"source context quality is {source_quality}, expected PASS")

    records = context_payload.get("records") or []
    if not isinstance(records, list):
        records = []
    context_summary = context_payload.get("summary") or {}
    question_text = question or context_summary.get("question") or context_payload.get("question") or ""
    query_parts = _query_parts_from_payload(context_payload, question_text, part_number)
    if not query_parts:
        # Preserve deterministic behavior for non-part-number queries, but mark as not exact-ready.
        query_parts = []
    part = query_parts[0] if query_parts else ""

    direct_records = [
        r for r in records
        if r.get("anchor_aware_role") == "direct_exact_match_anchor"
        and r.get("proof_strength") == "direct_exact_proof"
    ]
    variant_records = [
        r for r in records
        if r.get("anchor_aware_role") in {"same_anchor_community_variant", "family_variant_anchor"}
        and r.get("proof_strength") == "related_variant"
    ]
    neighbor_records = [
        r for r in records
        if r.get("anchor_aware_role") == "same_anchor_leiden_community_neighbor"
    ]
    support_records = [
        r for r in records
        if r.get("anchor_aware_role") in {"similar_table_candidate", "superseded_direct_candidate"}
    ]

    description = _extract_direct_description(part, direct_records) if part else "direct exact evidence"
    sentences: List[str] = []
    if part and direct_records:
        sentences.append(_make_direct_sentence(part, description, direct_records, max_direct_anchors))
    elif part:
        sentences.append(f"TRACE-Net did not find direct exact evidence for part number {part} in the provided context pack.")
    else:
        sentences.append("TRACE-Net could not identify a query part number for deterministic exact-answer composition.")

    variant_sentence, variant_map = _make_variant_sentence(part, variant_records, max_variants, max_labels_per_variant) if part else ("", {})
    if variant_sentence:
        sentences.append(variant_sentence)
    neighbor_sentence = _make_neighbor_sentence(neighbor_records, max_neighbors)
    if neighbor_sentence:
        sentences.append(neighbor_sentence)
    if part:
        sentences.append(_make_scope_sentence(part, direct_records, max_direct_anchors))
    sentences.append(_make_safety_sentence(direct_records, max_direct_anchors))
    answer_text = "\n\n".join(sentences).strip() + "\n"

    composer_records = _derive_composer_records(direct_records, variant_records, neighbor_records, support_records)
    answer_citations = re.findall(r"\[([A-Za-z0-9_\-]+)\]", answer_text)
    direct_labels = {_label(r) for r in direct_records[:max_direct_anchors]}
    variant_labels = {_label(r) for r in variant_records}
    context_labels = {_label(r) for r in records}

    summary: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "question": question_text,
        "source_context_pack": str(context_pack),
        "source_context_module": context_summary.get("module") or context_payload.get("module"),
        "source_context_quality_status": source_quality,
        "source_record_count": len(records),
        "composer_record_count": len(composer_records),
        "query_part_numbers": query_parts,
        "query_part_number_count": len(query_parts),
        "direct_exact_answer_record_count": len(direct_records),
        "direct_exact_answer_page_count": len(_unique(_page(r) for r in direct_records)),
        "direct_exact_answer_page_numbers": [r.get("page_number") for r in direct_records[:max_direct_anchors]],
        "direct_exact_answer_label_count": len(direct_labels),
        "variant_answer_record_count": len(variant_records),
        "variant_part_numbers": list(variant_map.keys()),
        "variant_part_number_count": len(variant_map),
        "weak_graph_context_record_count": len(neighbor_records),
        "retained_low_priority_support_count": len(support_records),
        "answer_char_count": len(answer_text),
        "answer_sentence_count": len(sentences),
        "answer_citation_count": len(answer_citations),
        "valid_answer_citation_count": sum(1 for c in answer_citations if c in context_labels),
        "invalid_answer_citation_count": sum(1 for c in answer_citations if c not in context_labels),
        "direct_exact_answer_citation_count": sum(1 for c in answer_citations if c in direct_labels),
        "variant_answer_citation_count": sum(1 for c in answer_citations if c in variant_labels),
        "fast_answer_composer_ready": bool(part and direct_records and answer_citations),
        "ready_for_answer_quality_gate": True,
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
    violations = _find_violations(answer_text, summary)
    if summary["invalid_answer_citation_count"]:
        violations.append({"severity": "critical", "code": "invalid_citation", "message": "Answer cites labels not present in context pack."})
    summary["violation_record_count"] = len(violations)
    severity_counts: Dict[str, int] = {}
    for v in violations:
        severity = v.get("severity", "unknown")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    summary["violation_severity_counts"] = severity_counts

    quality_status = "PASS" if summary["fast_answer_composer_ready"] and not violations else "FAIL"
    payload: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "summary": summary,
        "answer_text": answer_text,
        "records": composer_records,
        "violations": violations,
        "safety": {
            "dry_run_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{MODULE}.json"
    answer_path = out_dir / f"{MODULE}_answer.md"
    _write_json(report_path, payload)
    _write_json(out_dir / f"{MODULE}_summary.json", summary)
    _write_text(answer_path, answer_text)
    _write_records_csv(out_dir / f"{MODULE}_records.csv", composer_records)
    _write_jsonl(out_dir / f"{MODULE}_records.jsonl", composer_records)
    _write_jsonl(out_dir / f"{MODULE}_violations.jsonl", violations)
    _write_jsonl(
        out_dir / f"{MODULE}_citation_map.jsonl",
        [
            {
                "citation_label": _label(r),
                "page_number": r.get("page_number"),
                "page_id": r.get("page_id"),
                "composer_role": r.get("composer_role"),
                "proof_strength": r.get("proof_strength"),
                "anchor_relation_type": r.get("anchor_relation_type"),
            }
            for r in composer_records
        ],
    )

    if quality:
        check_path = out_dir / f"{MODULE}_quality_check.json"
        _write_json(check_path, {"quality_status": quality_status, "summary": summary, "violations": violations})
        print(f"Wrote: {check_path}")
    print("Status: TRACE_NET_FAST_ANSWER_COMPOSER_BUILT")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_fast_answer_composer_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_records: int = 1,
    min_citations: int = 1,
    min_valid_citations: int = 1,
    min_direct_exact_records: int = 0,
    min_direct_exact_citations: int = 0,
    max_invalid_citations: int = 0,
    max_violations: int = 0,
    require_source_quality_pass: bool = False,
    require_fast_answer_ready: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: Optional[int] = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def below(key: str, threshold: int) -> None:
        if int(summary.get(key, 0) or 0) < threshold:
            failures.append(f"{key} below {threshold}")

    def above(key: str, threshold: int) -> None:
        if int(summary.get(key, 0) or 0) > threshold:
            failures.append(f"{key} above {threshold}")

    below("composer_record_count", min_records)
    below("answer_citation_count", min_citations)
    below("valid_answer_citation_count", min_valid_citations)
    below("direct_exact_answer_record_count", min_direct_exact_records)
    below("direct_exact_answer_citation_count", min_direct_exact_citations)
    above("invalid_answer_citation_count", max_invalid_citations)
    above("violation_record_count", max_violations)

    if require_source_quality_pass and summary.get("source_context_quality_status") != "PASS":
        failures.append("source context quality did not PASS")
    if require_fast_answer_ready and not summary.get("fast_answer_composer_ready"):
        failures.append("fast_answer_composer_ready is not true")
    if require_no_human_review_required and (summary.get("human_review_required_count", 0) or summary.get("manual_review_required_count", 0)):
        failures.append("human/manual review required")
    if max_unsafe is not None and int(summary.get("unsafe_record_count", 0) or 0) > max_unsafe:
        failures.append(f"unsafe_record_count above {max_unsafe}")
    if require_no_answer_permission and int(summary.get("answer_permission_count", 0) or 0) != 0:
        failures.append("answer_permission_count is not 0")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count", 0) or 0) != 0:
        failures.append("source_truth_mutation_allowed_count is not 0")
    if require_no_write_attempts and int(summary.get("write_attempt_count", 0) or 0) != 0:
        failures.append("write_attempt_count is not 0")

    quality_status = "PASS" if not failures else "FAIL"
    result = {"quality_status": quality_status, "summary": summary, "failures": failures}
    if write_json:
        out = Path(report_path).with_name(f"{MODULE}_quality_check.json")
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, ensure_ascii=False))
    return result


def main_build(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net fast deterministic answer from anchor-aware context.")
    parser.add_argument("--context-pack", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--question")
    parser.add_argument("--part-number")
    parser.add_argument("--max-direct-anchors", type=int, default=8)
    parser.add_argument("--max-variants", type=int, default=6)
    parser.add_argument("--max-labels-per-variant", type=int, default=3)
    parser.add_argument("--max-neighbors", type=int, default=1)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_fast_answer_composer(
        context_pack=args.context_pack,
        output_dir=args.output_dir,
        question=args.question,
        part_number=args.part_number,
        max_direct_anchors=args.max_direct_anchors,
        max_variants=args.max_variants,
        max_labels_per_variant=args.max_labels_per_variant,
        max_neighbors=args.max_neighbors,
        require_source_quality_pass=args.require_source_quality_pass,
        quality=args.quality,
    )


def main_check(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net fast answer composer quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-valid-citations", type=int, default=1)
    parser.add_argument("--min-direct-exact-records", type=int, default=0)
    parser.add_argument("--min-direct-exact-citations", type=int, default=0)
    parser.add_argument("--max-invalid-citations", type=int, default=0)
    parser.add_argument("--max-violations", type=int, default=0)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-fast-answer-ready", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_fast_answer_composer_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_records=args.min_records,
        min_citations=args.min_citations,
        min_valid_citations=args.min_valid_citations,
        min_direct_exact_records=args.min_direct_exact_records,
        min_direct_exact_citations=args.min_direct_exact_citations,
        max_invalid_citations=args.max_invalid_citations,
        max_violations=args.max_violations,
        require_source_quality_pass=args.require_source_quality_pass,
        require_fast_answer_ready=args.require_fast_answer_ready,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":
    main_build()
