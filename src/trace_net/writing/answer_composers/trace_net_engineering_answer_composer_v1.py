from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STATUS_BUILT = "TRACE_NET_ENGINEERING_ANSWER_COMPOSER_BUILT"
STATUS_CHECKED = "TRACE_NET_ENGINEERING_ANSWER_COMPOSER_QUALITY_CHECKED"
VERSION = "v1"
MODULE = "trace_net_engineering_answer_composer_v1"

_FORBIDDEN_CLAIMS = [
    "interchangeability",
    "effectivity",
    "fit",
    "installation safety",
    "replacement approval",
    "approved replacement",
    "safe to install",
]


def _load_json(path: Any) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return data


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _records_from_context_pack(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records = data.get("records") or []
    if isinstance(records, list):
        return [r for r in records if isinstance(r, dict)]
    return []


def _first_record(data: Mapping[str, Any]) -> Dict[str, Any]:
    records = _records_from_context_pack(data)
    if not records:
        raise ValueError("Engineering context pack has no records")
    return records[0]


def _proof_context(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    proof = record.get("proof_context") or []
    if not isinstance(proof, list):
        return []
    return [p for p in proof if isinstance(p, dict)]


def _guidance_context(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    guidance = record.get("guidance_context") or []
    if not isinstance(guidance, list):
        return []
    return [g for g in guidance if isinstance(g, dict)]


def _answer_constraints(record: Mapping[str, Any]) -> Dict[str, Any]:
    constraints = record.get("answer_constraints") or {}
    return constraints if isinstance(constraints, dict) else {}


def _citation_label(item: Mapping[str, Any]) -> str:
    return _safe_str(item.get("citation_label"))


def _is_source_trace_ready(item: Mapping[str, Any]) -> bool:
    return bool(item.get("source_trace_ready"))


def _is_proof_eligible(item: Mapping[str, Any]) -> bool:
    return bool(item.get("proof_eligible")) and not bool(item.get("guidance_only"))


def _proof_by_type(proof: Sequence[Mapping[str, Any]], context_type: str) -> Optional[Mapping[str, Any]]:
    for item in proof:
        if item.get("context_type") == context_type:
            return item
    return None


def _first_nonempty(items: Iterable[Mapping[str, Any]], key: str) -> str:
    for item in items:
        value = _safe_str(item.get(key))
        if value:
            return value
    return ""


def _citation(item: Optional[Mapping[str, Any]]) -> str:
    if not item:
        return ""
    label = _citation_label(item)
    return f"[{label}]" if label else ""


def _valid_citation_labels(proof: Sequence[Mapping[str, Any]]) -> List[str]:
    labels = []
    for item in proof:
        label = _citation_label(item)
        if label and _is_source_trace_ready(item) and _is_proof_eligible(item):
            labels.append(label)
    return labels


def _extract_answer_citations(answer_text: str) -> List[str]:
    return re.findall(r"\[([A-Z]+\d+)\]", answer_text or "")


def _unsupported_claim_count(answer_text: str) -> int:
    """Count unsafe engineering claims while allowing explicit negative limitations."""
    text = (answer_text or "").lower()
    count = 0
    for term in _FORBIDDEN_CLAIMS:
        term_l = term.lower()
        for match in re.finditer(re.escape(term_l), text):
            window = text[max(0, match.start() - 80):match.end() + 20]
            negated = any(phrase in window for phrase in [
                "does not prove",
                "do not prove",
                "not prove",
                "no proof",
                "unsupported",
                "may not claim",
                "does not establish",
                "cannot prove",
            ])
            if not negated:
                count += 1
    return count


def _llava_only_part_identity_claim_count(answer_text: str, proof: Sequence[Mapping[str, Any]]) -> int:
    text = (answer_text or "").lower()
    if "llava" not in text:
        return 0
    has_non_llava_proof = any(
        _is_proof_eligible(p)
        and _is_source_trace_ready(p)
        and _safe_str(p.get("context_type")) in {"visual_figure_link", "ocr_nomenclature", "table_ocr_proof", "exact_part_evidence"}
        for p in proof
    )
    # Only flag if the answer uses LLaVA as if it is proof and no eligible OCR/table/visual proof exists.
    if not has_non_llava_proof and re.search(r"llava.*(part|number|identity|shows)", text):
        return 1
    return 0


def compose_engineering_answer(record: Mapping[str, Any]) -> Dict[str, Any]:
    question = _safe_str(record.get("question"))
    task_type = _safe_str(record.get("task_type")) or "engineering_question"
    proof = _proof_context(record)
    guidance = _guidance_context(record)
    constraints = _answer_constraints(record)

    visual = _proof_by_type(proof, "visual_figure_link")
    ocr = _proof_by_type(proof, "ocr_nomenclature")
    exact = _proof_by_type(proof, "exact_part_evidence")
    table = _proof_by_type(proof, "table_ocr_proof")

    figure = _first_nonempty([p for p in [visual, ocr, exact, table] if p], "figure")
    part = _first_nonempty([p for p in [exact, visual, ocr, table] if p], "part_number")
    nomenclature = _first_nonempty([p for p in [ocr, visual, exact, table] if p], "nomenclature")
    confidence = _first_nonempty([p for p in [ocr, visual, exact] if p], "nomenclature_confidence") or "MEDIUM"

    visual_cite = _citation(visual)
    ocr_cite = _citation(ocr)
    exact_cite = _citation(exact)
    table_cite = _citation(table)

    answer_lines: List[str] = []
    if task_type == "exact_part_lookup" and part and nomenclature:
        citations = " ".join(x for x in [exact_cite, ocr_cite, table_cite, visual_cite] if x)
        answer_lines.append(f'Part number {part} is present in source-trace-ready evidence and is associated with "{nomenclature}" {citations}.'.strip())
    elif task_type == "exact_part_lookup" and part:
        citations = " ".join(x for x in [exact_cite, table_cite, visual_cite, ocr_cite] if x)
        answer_lines.append(f"Part number {part} is present in source-trace-ready evidence {citations}.".strip())
    elif figure and part and nomenclature:
        answer_lines.append(
            f'Figure {figure} is linked to part number {part}, "{nomenclature}" {visual_cite} {ocr_cite}.'.strip()
        )
    elif figure and part:
        answer_lines.append(f"Figure {figure} is linked to part number {part} {visual_cite}.".strip())
    elif part and nomenclature:
        answer_lines.append(f'Part number {part} is associated with "{nomenclature}" {ocr_cite or exact_cite or table_cite}.'.strip())
    else:
        answer_lines.append("TRACE-Net found source-trace-ready engineering evidence, but the direct claim is incomplete in the context pack.")

    evidence_lines: List[str] = []
    if exact:
        field = _safe_str(exact.get("field_name"))
        value = _safe_str(exact.get("value"))
        page = _safe_str(exact.get("page_number"))
        evidence_lines.append(
            f"- {exact_cite} Exact-part evidence contains part number {part or _safe_str(exact.get('part_number'))}"
            + (f" in field {field}" if field else "")
            + (f" on page {page}" if page else "")
            + (f": {value}." if value else ".")
        )
    if visual:
        page = _safe_str(visual.get("page_number"))
        evidence_lines.append(
            f"- {visual_cite} Visual evidence links figure {figure or _safe_str(visual.get('figure'))} "
            f"to part number {part or _safe_str(visual.get('part_number'))}"
            + (f" on page {page}." if page else ".")
        )
    if ocr:
        page = _safe_str(ocr.get("page_number"))
        line_text = _safe_str(ocr.get("line_text"))
        evidence_lines.append(
            f"- {ocr_cite} OCR-backed nomenclature gives \"{nomenclature or _safe_str(ocr.get('nomenclature'))}\""
            + (f" on page {page}." if page else ".")
        )
        if line_text:
            evidence_lines.append(f"  OCR line: {line_text}")
    if table:
        table_part = part or _safe_str(table.get("part_number"))
        evidence_lines.append(f"- {table_cite} Table/OCR proof supports part number {table_part}.".strip())

    confidence_bits = []
    if task_type == "exact_part_lookup" and exact and (ocr or table or visual):
        confidence_bits.append("HIGH for the exact part lookup because multiple source-trace-ready proof records support the part number.")
    elif visual and ocr and table:
        confidence_bits.append("HIGH for the figure-to-part and nomenclature claim because visual, OCR, and table/OCR proof are source-trace-ready.")
    elif visual and (ocr or table):
        confidence_bits.append("MEDIUM to HIGH because multiple source-trace-ready proof records support the claim.")
    else:
        confidence_bits.append("LOW to MEDIUM because the context pack has limited proof records.")
    if confidence:
        confidence_bits.append(f"Nomenclature confidence: {confidence}.")

    limits = [
        "This does not prove interchangeability, effectivity, fit, replacement approval, or installation safety.",
        "V2 summaries, when present, are guidance only and are not used as proof in this answer.",
    ]

    answer_text = "\n\n".join([
        "Answer:\n" + "\n".join(answer_lines),
        "Evidence:\n" + "\n".join(evidence_lines or ["- No proof context was available."]),
        "Engineering confidence:\n" + " ".join(confidence_bits),
        "Limits:\n" + "\n".join(f"- {x}" for x in limits),
    ])

    valid_labels = _valid_citation_labels(proof)
    cited_labels = _extract_answer_citations(answer_text)
    invalid_labels = sorted({c for c in cited_labels if c not in valid_labels})
    source_trace_ready_citations = sorted({c for c in cited_labels if c in valid_labels})

    return {
        "question": question,
        "task_type": task_type,
        "answer_text": answer_text,
        "answer_style": constraints.get("answer_style") or "engineering_brain",
        "selected_claim": {
            "figure": figure,
            "part_number": part,
            "nomenclature": nomenclature,
            "nomenclature_confidence": confidence,
        },
        "citations": cited_labels,
        "valid_citations": source_trace_ready_citations,
        "invalid_citations": invalid_labels,
        "proof_context_used_count": len([p for p in proof if _is_proof_eligible(p)]),
        "guidance_context_used_count": len(guidance),
        "summary_used_as_proof_count": len([p for p in proof if p.get("guidance_only")]),
        "answer_constraints": constraints,
        "forbidden_claims_checked": list(_FORBIDDEN_CLAIMS),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def quality_gate_answer(answer_record: Mapping[str, Any], source_record: Mapping[str, Any], *,
                        min_answer_citations: int = 1,
                        min_source_trace_ready_citations: int = 1,
                        max_unsupported_claims: int = 0,
                        max_summary_used_as_proof: int = 0,
                        max_invalid_citations: int = 0,
                        max_llava_only_part_identity_claims: int = 0) -> Dict[str, Any]:
    answer_text = _safe_str(answer_record.get("answer_text"))
    proof = _proof_context(source_record)
    citations = list(answer_record.get("citations") or [])
    valid_citations = list(answer_record.get("valid_citations") or [])
    invalid_citations = list(answer_record.get("invalid_citations") or [])

    unsupported_claim_count = _unsupported_claim_count(answer_text)
    llava_only_claim_count = _llava_only_part_identity_claim_count(answer_text, proof)
    summary_used_as_proof_count = int(answer_record.get("summary_used_as_proof_count") or 0)

    failures = []
    if len(citations) < min_answer_citations:
        failures.append(f"answer_citation_count below minimum: {len(citations)} < {min_answer_citations}")
    if len(valid_citations) < min_source_trace_ready_citations:
        failures.append(f"source_trace_ready_citation_count below minimum: {len(valid_citations)} < {min_source_trace_ready_citations}")
    if len(invalid_citations) > max_invalid_citations:
        failures.append(f"invalid_answer_citation_count above maximum: {len(invalid_citations)} > {max_invalid_citations}")
    if unsupported_claim_count > max_unsupported_claims:
        failures.append(f"unsupported_claim_count above maximum: {unsupported_claim_count} > {max_unsupported_claims}")
    if llava_only_claim_count > max_llava_only_part_identity_claims:
        failures.append(f"llava_only_part_identity_claim_count above maximum: {llava_only_claim_count} > {max_llava_only_part_identity_claims}")
    if summary_used_as_proof_count > max_summary_used_as_proof:
        failures.append(f"summary_used_as_proof_count above maximum: {summary_used_as_proof_count} > {max_summary_used_as_proof}")

    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "answer_citation_count": len(citations),
        "valid_answer_citation_count": len(valid_citations),
        "source_trace_ready_citation_count": len(valid_citations),
        "invalid_answer_citation_count": len(invalid_citations),
        "invalid_answer_citation_labels": invalid_citations,
        "unsupported_claim_count": unsupported_claim_count,
        "unsupported_interchangeability_claim_count": _unsupported_claim_count(answer_text) if "interchangeability" in answer_text.lower() and unsupported_claim_count else 0,
        "llava_only_part_identity_claim_count": llava_only_claim_count,
        "summary_used_as_proof_count": summary_used_as_proof_count,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": 0,
    }


def build_engineering_answer_composer(*,
                                      context_pack: Any,
                                      output_dir: Any,
                                      min_answer_citations: int = 1,
                                      min_source_trace_ready_citations: int = 1,
                                      max_unsupported_claims: int = 0,
                                      max_summary_used_as_proof: int = 0,
                                      max_invalid_citations: int = 0,
                                      max_llava_only_part_identity_claims: int = 0,
                                      max_unsafe: int = 0,
                                      max_answer_permission: int = 0,
                                      max_source_truth_mutation_allowed: int = 0,
                                      max_write_attempts: int = 0) -> Dict[str, Any]:
    source = _load_json(context_pack)
    record = _first_record(source)
    answer_record = compose_engineering_answer(record)
    gate = quality_gate_answer(
        answer_record,
        record,
        min_answer_citations=min_answer_citations,
        min_source_trace_ready_citations=min_source_trace_ready_citations,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
    )

    summary = {
        "engineering_answer_record_count": 1,
        "answer_char_count": len(answer_record.get("answer_text") or ""),
        "answer_citation_count": gate["answer_citation_count"],
        "valid_answer_citation_count": gate["valid_answer_citation_count"],
        "source_trace_ready_citation_count": gate["source_trace_ready_citation_count"],
        "invalid_answer_citation_count": gate["invalid_answer_citation_count"],
        "unsupported_claim_count": gate["unsupported_claim_count"],
        "llava_only_part_identity_claim_count": gate["llava_only_part_identity_claim_count"],
        "summary_used_as_proof_count": gate["summary_used_as_proof_count"],
        "proof_context_used_count": answer_record.get("proof_context_used_count", 0),
        "guidance_context_used_count": answer_record.get("guidance_context_used_count", 0),
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": 0,
        "ready_for_engineering_answer_delivery": gate["quality_status"] == "PASS",
    }

    # Enforce caller thresholds too.
    threshold_failures = list(gate.get("failures") or [])
    if summary["unsafe_record_count"] > max_unsafe:
        threshold_failures.append("unsafe_record_count above maximum")
    if summary["answer_permission_count"] > max_answer_permission:
        threshold_failures.append("answer_permission_count above maximum")
    if summary["source_truth_mutation_allowed_count"] > max_source_truth_mutation_allowed:
        threshold_failures.append("source_truth_mutation_allowed_count above maximum")
    if summary["write_attempt_count"] > max_write_attempts:
        threshold_failures.append("write_attempt_count above maximum")

    quality_status = "PASS" if not threshold_failures else "FAIL"
    result = {
        "status": STATUS_BUILT,
        "module": MODULE,
        "version": VERSION,
        "quality_status": quality_status,
        "source_context_pack": str(context_pack),
        "summary": summary,
        "records": [answer_record],
        "answer_text": answer_record.get("answer_text"),
        "quality_gate": gate,
        "failures": threshold_failures,
        "safety_contract": {
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
            "opensearch_upload_allowed": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
    }
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "trace_net_engineering_answer_composer_v1.json", result)
    _write_json(out_dir / "trace_net_engineering_answer_composer_v1_quality_gate.json", gate)
    return result


def check_engineering_answer_composer(*,
                                      composer: Any,
                                      output: Any,
                                      require_quality_pass: bool = False,
                                      min_answer_citations: int = 1,
                                      min_source_trace_ready_citations: int = 1,
                                      max_unsupported_claims: int = 0,
                                      max_summary_used_as_proof: int = 0,
                                      max_invalid_citations: int = 0,
                                      max_llava_only_part_identity_claims: int = 0,
                                      max_unsafe: int = 0,
                                      max_answer_permission: int = 0,
                                      max_source_truth_mutation_allowed: int = 0,
                                      max_write_attempts: int = 0) -> Dict[str, Any]:
    data = _load_json(composer)
    summary = data.get("summary") or {}
    failures: List[str] = []

    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_status is not PASS")
    if int(summary.get("answer_citation_count") or 0) < min_answer_citations:
        failures.append("answer_citation_count below minimum")
    if int(summary.get("source_trace_ready_citation_count") or 0) < min_source_trace_ready_citations:
        failures.append("source_trace_ready_citation_count below minimum")
    if int(summary.get("unsupported_claim_count") or 0) > max_unsupported_claims:
        failures.append("unsupported_claim_count above maximum")
    if int(summary.get("summary_used_as_proof_count") or 0) > max_summary_used_as_proof:
        failures.append("summary_used_as_proof_count above maximum")
    if int(summary.get("invalid_answer_citation_count") or 0) > max_invalid_citations:
        failures.append("invalid_answer_citation_count above maximum")
    if int(summary.get("llava_only_part_identity_claim_count") or 0) > max_llava_only_part_identity_claims:
        failures.append("llava_only_part_identity_claim_count above maximum")
    if int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append("unsafe_record_count above maximum")
    if int(summary.get("answer_permission_count") or 0) > max_answer_permission:
        failures.append("answer_permission_count above maximum")
    if int(summary.get("source_truth_mutation_allowed_count") or 0) > max_source_truth_mutation_allowed:
        failures.append("source_truth_mutation_allowed_count above maximum")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count above maximum")

    result = {
        "status": STATUS_CHECKED,
        "module": MODULE,
        "version": VERSION,
        "quality_status": "PASS" if not failures else "FAIL",
        "source_composer": str(composer),
        "summary": summary,
        "failures": failures,
    }
    _write_json(output, result)
    return result


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Build TRACE-Net engineering answer composer v1")
    ap.add_argument("--context-pack", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--min-answer-citations", type=int, default=1)
    ap.add_argument("--min-source-trace-ready-citations", type=int, default=1)
    ap.add_argument("--max-unsupported-claims", type=int, default=0)
    ap.add_argument("--max-summary-used-as-proof", type=int, default=0)
    ap.add_argument("--max-invalid-citations", type=int, default=0)
    ap.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    ap.add_argument("--max-unsafe", type=int, default=0)
    ap.add_argument("--max-answer-permission", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--max-write-attempts", type=int, default=0)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    result = build_engineering_answer_composer(**vars(args))
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"answer_citation_count={s.get('answer_citation_count')}")
    print(f"source_trace_ready_citation_count={s.get('source_trace_ready_citation_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    print(f"llava_only_part_identity_claim_count={s.get('llava_only_part_identity_claim_count')}")
    print(f"answer={result.get('answer_text')}")
    print(f"composer={Path(args.output_dir) / 'trace_net_engineering_answer_composer_v1.json'}")
    return 0 if result.get("quality_status") == "PASS" else 1


def _check_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Check TRACE-Net engineering answer composer v1")
    ap.add_argument("--composer", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--require-quality-pass", action="store_true")
    ap.add_argument("--min-answer-citations", type=int, default=1)
    ap.add_argument("--min-source-trace-ready-citations", type=int, default=1)
    ap.add_argument("--max-unsupported-claims", type=int, default=0)
    ap.add_argument("--max-summary-used-as-proof", type=int, default=0)
    ap.add_argument("--max-invalid-citations", type=int, default=0)
    ap.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    ap.add_argument("--max-unsafe", type=int, default=0)
    ap.add_argument("--max-answer-permission", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--max-write-attempts", type=int, default=0)
    return ap


def check_main(argv: Optional[List[str]] = None) -> int:
    args = _check_parser().parse_args(argv)
    result = check_engineering_answer_composer(**vars(args))
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"answer_citation_count={s.get('answer_citation_count')}")
    print(f"source_trace_ready_citation_count={s.get('source_trace_ready_citation_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    for failure in result.get("failures", []):
        print(f"failure={failure}")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
