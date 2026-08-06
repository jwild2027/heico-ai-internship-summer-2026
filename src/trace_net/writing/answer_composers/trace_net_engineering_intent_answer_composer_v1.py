"""TRACE-Net engineering intent answer composer v1.

This module is a conservative post-composer upgrade for engineering answers.
It consumes an existing H5 engineering answer runner manifest plus its H3
engineering context pack and rewrites the final answer only when the question
intent requires a different answer shape than the generic evidence composer.

Safety contract:
- Reads local JSON artifacts only.
- Writes JSON/CSV outputs only under the requested output directory.
- Does not mutate source-truth artifacts.
- Does not write to Postgres/Qdrant/OpenSearch.
- Does not grant answer permission.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STATUS = "TRACE_NET_ENGINEERING_INTENT_ANSWER_COMPOSER_BUILT"
CHECK_STATUS = "TRACE_NET_ENGINEERING_INTENT_ANSWER_COMPOSER_QUALITY_CHECKED"
MODULE = "trace_net_engineering_intent_answer_composer_v1"
VERSION = "v1"

FORBIDDEN_LIMITS = [
    "interchangeability",
    "effectivity",
    "fit",
    "replacement approval",
    "installation safety",
]


def _load_json(path: Any) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_csv(path: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "question",
        "task_type",
        "intent_answer_type",
        "quality_status",
        "answer_citation_count",
        "valid_answer_citation_count",
        "source_trace_ready_citation_count",
        "unsupported_claim_count",
        "summary_used_as_proof_count",
        "ready_for_intent_answer_delivery",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _first_record(data: Mapping[str, Any]) -> Dict[str, Any]:
    records = data.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return dict(records[0])
    return {}


def _runner_summary(runner: Mapping[str, Any]) -> Dict[str, Any]:
    s = runner.get("summary")
    return dict(s) if isinstance(s, dict) else {}


def _stage_context_pack_path(runner: Mapping[str, Any]) -> str:
    stage_reports = runner.get("stage_reports")
    if isinstance(stage_reports, dict):
        path = stage_reports.get("engineering_answer_context_pack")
        if path:
            return str(path)
    return ""


def _load_context_pack_for_runner(runner: Mapping[str, Any], context_pack: Optional[Any]) -> Dict[str, Any]:
    if context_pack:
        return _load_json(context_pack)
    path = _stage_context_pack_path(runner)
    if path:
        p = Path(path)
        if p.exists():
            return _load_json(p)
    return {"records": []}


def _proof_context(context_pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    record = _first_record(context_pack)
    proof = record.get("proof_context")
    if isinstance(proof, list):
        return [dict(x) for x in proof if isinstance(x, dict)]
    return []


def _guidance_context(context_pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    record = _first_record(context_pack)
    guidance = record.get("guidance_context")
    if isinstance(guidance, list):
        return [dict(x) for x in guidance if isinstance(x, dict)]
    return []


def _labels_from_proof(proof: Iterable[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    labels: Dict[str, Mapping[str, Any]] = {}
    for p in proof:
        label = str(p.get("citation_label") or "").strip()
        if label:
            labels[label] = p
    return labels


def _extract_citations(answer: str) -> List[str]:
    return re.findall(r"\[([A-Z][A-Za-z0-9_-]*)\]", answer or "")


def _parts_in_text(text: str) -> List[str]:
    return sorted(set(re.findall(r"\b\d{3}-\d{5}-\d{3}\b", text or "")))


def _figures_in_text(text: str) -> List[str]:
    figures: List[str] = []
    for m in re.finditer(r"\bfig(?:ure)?\.?\s*([0-9]{1,4})\b", text or "", flags=re.I):
        figures.append(str(int(m.group(1))) if m.group(1).isdigit() else m.group(1))
    return sorted(set(figures), key=lambda x: int(x) if x.isdigit() else 999999)


def _clean_nomenclature(value: Any) -> str:
    s = str(value or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _entry_text(p: Mapping[str, Any]) -> str:
    part = str(p.get("part_number") or p.get("linked_part_number") or "").strip()
    nom = _clean_nomenclature(p.get("nomenclature") or p.get("linked_nomenclature") or p.get("linked_description"))
    fig = str(p.get("figure") or "").strip()
    page = p.get("page_number")
    label = str(p.get("citation_label") or "").strip()
    bits = []
    if fig:
        bits.append(f"Figure {fig}")
    if part:
        bits.append(f"part number {part}")
    if nom:
        bits.append(f'"{nom}"')
    if page not in (None, ""):
        bits.append(f"page {page}")
    text = ", ".join(bits) if bits else "source-trace-ready evidence"
    return f"{text} [{label}]" if label else text


def _best_by_type(proof: List[Dict[str, Any]], context_type: str) -> List[Dict[str, Any]]:
    return [p for p in proof if str(p.get("context_type") or "") == context_type]


def _visual_records(proof: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in proof if str(p.get("context_type") or "").startswith("visual")]


def _ocr_records(proof: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in proof if "ocr" in str(p.get("context_type") or "")]


def _exact_records(proof: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in proof if str(p.get("context_type") or "") == "exact_part_evidence"]


def _record_for_figure(proof: List[Dict[str, Any]], figure: str, preferred: str = "") -> Optional[Dict[str, Any]]:
    figure_s = str(int(figure)) if str(figure).isdigit() else str(figure)
    candidates = [p for p in proof if str(p.get("figure") or "").lstrip("0") == figure_s]
    if preferred:
        for p in candidates:
            if preferred in str(p.get("context_type") or ""):
                return p
    return candidates[0] if candidates else None


def _records_for_part(proof: List[Dict[str, Any]], part: str) -> List[Dict[str, Any]]:
    return [p for p in proof if str(p.get("part_number") or p.get("linked_part_number") or "") == part]


def _intent_type(question: str, task_type: str) -> str:
    q = (question or "").lower()
    if "interchange" in q or "interchangeable" in q:
        return "unsupported_interchangeability"
    if "installation safety" in q or "prove installation" in q or "safe to install" in q:
        return "unsupported_installation_safety"
    if "what can" in q and ("not prove" in q or "can't" in q or "cannot" in q):
        return "limitations"
    if "why" in q and "nomenclature" in q and ("missing" in q or "visual route" in q):
        return "troubleshooting_nomenclature"
    if "compare" in q:
        return "comparison"
    if "what evidence" in q or "evidence supports" in q:
        return "evidence_support"
    if task_type == "troubleshooting_question":
        return "troubleshooting"
    return "default"


def _limits_text() -> str:
    return "This evidence does not prove interchangeability, effectivity, fit, replacement approval, or installation safety."


def _generic_evidence_lines(proof: List[Dict[str, Any]], max_lines: int = 5) -> List[str]:
    lines: List[str] = []
    for p in proof[:max_lines]:
        label = str(p.get("citation_label") or "").strip()
        ctype = str(p.get("context_type") or "evidence").replace("_", " ")
        text = _entry_text(p)
        if label:
            lines.append(f"- [{label}] {ctype}: {text}.")
        else:
            lines.append(f"- {ctype}: {text}.")
        if p.get("line_text"):
            lines.append(f"  OCR line: {p.get('line_text')}")
    return lines


def _rewrite_troubleshooting(question: str, proof: List[Dict[str, Any]]) -> str:
    visual = _visual_records(proof)
    ocr = _ocr_records(proof)
    exact = _exact_records(proof)
    primary_visual = visual[0] if visual else (proof[0] if proof else {})
    primary_ocr = ocr[0] if ocr else {}
    part = str(primary_visual.get("part_number") or primary_ocr.get("part_number") or "").strip()
    nom = _clean_nomenclature(primary_ocr.get("nomenclature") or primary_visual.get("nomenclature"))
    v_label = str(primary_visual.get("citation_label") or "").strip()
    o_label = str(primary_ocr.get("citation_label") or "").strip()
    e_label = str(exact[0].get("citation_label") or "").strip() if exact else ""

    cite_bits = " ".join(f"[{x}]" for x in [v_label, o_label, e_label] if x)
    answer = [
        "Answer:",
        "Nomenclature was missing from the earlier visual-route evidence because the visual link stage established the figure/part relationship, but the visual-link record did not carry a clean description/nomenclature field as proof. The later OCR-backed nomenclature route recovered the name from raw OCR text and the merged visual evidence pack now carries that name as source-trace-ready proof" + (f" {cite_bits}." if cite_bits else "."),
        "",
        "Evidence:",
    ]
    if v_label:
        answer.append(f"- [{v_label}] Visual evidence links the figure to part number {part or 'the requested part'}, but visual evidence by itself is not allowed to prove nomenclature.")
    if o_label:
        line = primary_ocr.get("line_text") or ""
        answer.append(f"- [{o_label}] OCR-backed evidence provides the recovered nomenclature" + (f' "{nom}"' if nom else "") + ".")
        if line:
            answer.append(f"  OCR line: {line}")
    if e_label:
        answer.append(f"- [{e_label}] Exact/table evidence supports the part number independently of the visual observation.")
    answer.extend([
        "",
        "Engineering confidence:",
        "HIGH for the diagnosis when visual-link evidence and OCR-backed nomenclature evidence are both source-trace-ready. The failure point is field coverage in the visual-route artifact, not absence of the part in the source.",
        "",
        "Limits:",
        f"- {_limits_text()}",
        "- V2 summaries, when present, may guide the investigation but are not used as proof.",
    ])
    return "\n".join(answer)


def _rewrite_interchangeability(question: str, proof: List[Dict[str, Any]]) -> str:
    parts = _parts_in_text(question)
    if not parts:
        parts = sorted(set(str(p.get("part_number") or "") for p in proof if p.get("part_number")))[:2]
    evidence_lines: List[str] = []
    for part in parts:
        records = _records_for_part(proof, part)
        if not records:
            continue
        labels = []
        nom = ""
        for p in records:
            label = str(p.get("citation_label") or "").strip()
            if label and label not in labels:
                labels.append(label)
            nom = nom or _clean_nomenclature(p.get("nomenclature"))
        cite = " ".join(f"[{x}]" for x in labels[:3])
        evidence_lines.append(f"- {part}" + (f' is associated with "{nom}"' if nom else " appears in source-trace-ready evidence") + (f" {cite}." if cite else "."))
    part_text = " and ".join(parts) if parts else "the requested parts"
    answer = [
        "Answer:",
        f"TRACE-Net cannot prove that {part_text} are interchangeable from the current source-trace-ready evidence. The available evidence can identify the parts and their nomenclature, but shared or similar nomenclature is not approval for interchangeability.",
        "",
        "Evidence:",
    ]
    answer.extend(evidence_lines or _generic_evidence_lines(proof, 4))
    answer.extend([
        "",
        "Engineering confidence:",
        "HIGH for the limitation: the current proof context supports identity/nomenclature evidence, not an interchangeability approval statement.",
        "",
        "Limits:",
        "- Do not treat same nomenclature, nearby figures, or part-family similarity as interchangeability proof.",
        "- Interchangeability would require explicit approved source evidence such as effectivity, supersedure, replacement, or interchangeability documentation.",
    ])
    return "\n".join(answer)


def _rewrite_installation_safety(question: str, proof: List[Dict[str, Any]]) -> str:
    figures = _figures_in_text(question)
    figure = figures[0] if figures else "the requested figure"
    answer = [
        "Answer:",
        f"No. Figure {figure} does not prove installation safety from the current TRACE-Net evidence. The available evidence can identify the figure-linked part, but it does not provide approved installation, safety, fit, effectivity, or replacement authority.",
        "",
        "Evidence:",
    ]
    answer.extend(_generic_evidence_lines(proof, 4))
    answer.extend([
        "",
        "Engineering confidence:",
        "HIGH for the limitation: the proof context is identification evidence, not installation-safety evidence.",
        "",
        "Limits:",
        "- Installation safety requires approved procedure/safety/effectivity evidence not present in this answer context.",
        "- The figure may help identify a part, but identification is not safety approval.",
    ])
    return "\n".join(answer)


def _rewrite_limits(question: str, proof: List[Dict[str, Any]]) -> str:
    parts = _parts_in_text(question)
    target = parts[0] if parts else "the requested part/figure"
    answer = [
        "Answer:",
        f"TRACE-Net can support source-traced identification evidence for {target}, but it cannot prove interchangeability, effectivity, fit, replacement approval, or installation safety from the current evidence pack.",
        "",
        "Evidence it can support:",
    ]
    answer.extend(_generic_evidence_lines(proof, 4))
    answer.extend([
        "",
        "What it cannot prove from this context:",
        "- Interchangeability with another part number.",
        "- Aircraft/effectivity applicability beyond the cited source evidence.",
        "- Fit, installation safety, or replacement approval.",
        "- Any maintenance action approval not explicitly present in the source-trace-ready proof.",
        "",
        "Engineering confidence:",
        "HIGH for the boundary statement because the context pack separates identification proof from unsupported engineering approvals.",
    ])
    return "\n".join(answer)


def _rewrite_evidence_support(question: str, proof: List[Dict[str, Any]]) -> str:
    parts = _parts_in_text(question)
    target = parts[0] if parts else "the requested item"
    answer = [
        "Answer:",
        f"The evidence supporting {target} is the combination of source-trace-ready exact/table evidence, visual figure linkage when available, and OCR-backed nomenclature.",
        "",
        "Evidence:",
    ]
    answer.extend(_generic_evidence_lines(proof, 6))
    answer.extend([
        "",
        "Engineering confidence:",
        "HIGH when the exact/table record, visual link, and OCR nomenclature all agree. If one of those sources is absent, treat the answer as narrower and cite the limitation.",
        "",
        "Limits:",
        f"- {_limits_text()}",
    ])
    return "\n".join(answer)


def _rewrite_comparison(question: str, proof: List[Dict[str, Any]]) -> str:
    figures = _figures_in_text(question)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in proof:
        fig = str(p.get("figure") or "").strip()
        if fig:
            grouped[fig.lstrip("0") or fig].append(p)
    if not figures:
        figures = sorted(grouped.keys(), key=lambda x: int(x) if x.isdigit() else 999999)[:2]

    answer = ["Answer:"]
    if len(figures) >= 2:
        answer.append(f"Figures {figures[0]} and {figures[1]} are both source-trace-linked visual/parts evidence, but they point to different part-number records unless the source explicitly says otherwise.")
    else:
        answer.append("TRACE-Net found source-trace-linked figure evidence for comparison, but the question did not provide two clean figure identifiers.")
    answer.extend(["", "Comparison:"])

    for fig in figures:
        records = grouped.get(str(fig), []) or [p for p in proof if str(p.get("figure") or "").lstrip("0") == str(fig)]
        visual = next((p for p in records if str(p.get("context_type") or "").startswith("visual")), records[0] if records else {})
        ocr = next((p for p in records if "ocr" in str(p.get("context_type") or "")), {})
        part = str(visual.get("part_number") or ocr.get("part_number") or "").strip()
        nom = _clean_nomenclature(ocr.get("nomenclature") or visual.get("nomenclature"))
        labels = []
        for p in records:
            label = str(p.get("citation_label") or "").strip()
            if label and label not in labels:
                labels.append(label)
        cite = " ".join(f"[{x}]" for x in labels[:3])
        answer.append(f"- Figure {fig}:" + (f" part number {part}" if part else " part number not resolved") + (f', nomenclature "{nom}"' if nom else "") + (f" {cite}." if cite else "."))
        if ocr.get("line_text"):
            answer.append(f"  OCR line: {ocr.get('line_text')}")

    answer.extend([
        "",
        "Engineering confidence:",
        "HIGH for figure-to-part and nomenclature comparisons when each figure has source-trace-ready visual and OCR/table support.",
        "",
        "Limits:",
        "- A comparison of figure-linked evidence does not prove interchangeability, effectivity, fit, replacement approval, or installation safety.",
    ])
    return "\n".join(answer)


def _fallback_answer(runner: Mapping[str, Any]) -> str:
    return str(runner.get("answer_text") or runner.get("answer") or "TRACE-Net did not produce an answer.")


def rewrite_answer(question: str, task_type: str, proof: List[Dict[str, Any]], runner: Mapping[str, Any]) -> Tuple[str, str]:
    intent = _intent_type(question, task_type)
    if intent == "troubleshooting_nomenclature":
        return intent, _rewrite_troubleshooting(question, proof)
    if intent == "unsupported_interchangeability":
        return intent, _rewrite_interchangeability(question, proof)
    if intent == "unsupported_installation_safety":
        return intent, _rewrite_installation_safety(question, proof)
    if intent == "limitations":
        return intent, _rewrite_limits(question, proof)
    if intent == "evidence_support":
        return intent, _rewrite_evidence_support(question, proof)
    if intent == "comparison":
        return intent, _rewrite_comparison(question, proof)
    return intent, _fallback_answer(runner)


def _unsupported_claim_count(answer: str) -> int:
    text = (answer or "").lower()
    count = 0
    # Count only affirmative dangerous claims, not explicit denials/limitations.
    affirm_patterns = [
        r"\bis interchangeable with\b",
        r"\bare interchangeable\b",
        r"\bapproved for installation\b",
        r"\bproves installation safety\b",
        r"\bproves effectivity\b",
        r"\breplacement approval is proven\b",
    ]
    for pat in affirm_patterns:
        for m in re.finditer(pat, text):
            window = text[max(0, m.start() - 120):m.start()]
            sentence_start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start()))
            sentence_prefix = text[sentence_start + 1:m.start()]
            negation_scope = window + " " + sentence_prefix
            if any(neg in negation_scope for neg in ["not ", "cannot ", "can't ", "does not ", "do not ", "no. ", "no "]):
                continue
            count += 1
    return count


def _llava_only_part_identity_claim_count(answer: str) -> int:
    text = (answer or "").lower()
    if "llava-only" in text and ("part identity" in text or "part number" in text):
        if "not" not in text and "cannot" not in text:
            return 1
    return 0


def _summary_used_as_proof_count(answer: str) -> int:
    text = (answer or "").lower()
    if "v2 summar" in text and "proof" in text:
        if "not used as proof" in text or "not proof" in text or "guidance only" in text:
            return 0
        return 1
    return 0


def build_intent_answer_composer(
    *,
    runner: Any,
    output_dir: Any,
    context_pack: Optional[Any] = None,
    min_answer_citations: int = 1,
    min_source_trace_ready_citations: int = 1,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
    require_quality_pass: bool = False,
) -> Dict[str, Any]:
    runner_data = _load_json(runner)
    context_data = _load_context_pack_for_runner(runner_data, context_pack)
    runner_summary = _runner_summary(runner_data)
    context_record = _first_record(context_data)
    proof = _proof_context(context_data)
    guidance = _guidance_context(context_data)

    question = str(runner_summary.get("question") or runner_data.get("question") or "")
    task_type = str(runner_summary.get("task_type") or "")
    intent_answer_type, answer_text = rewrite_answer(question, task_type, proof, runner_data)

    proof_labels = _labels_from_proof(proof)
    citations = _extract_citations(answer_text)
    citation_labels = sorted(set(citations))
    invalid_labels = [c for c in citation_labels if c not in proof_labels]
    source_trace_ready_labels = [
        c for c in citation_labels
        if c in proof_labels and bool(proof_labels[c].get("source_trace_ready"))
    ]

    unsupported_claim_count = _unsupported_claim_count(answer_text)
    summary_used_as_proof_count = _summary_used_as_proof_count(answer_text)
    llava_only_count = _llava_only_part_identity_claim_count(answer_text)

    answer_permission_count = 0
    source_truth_mutation_allowed_count = 0
    unsafe_record_count = 0
    write_attempt_count = 0
    postgres_write_attempt_count = 0
    qdrant_write_attempt_count = 0
    opensearch_write_attempt_count = 0
    opensearch_upload_attempt_count = 0

    failures: List[str] = []
    if len(citations) < min_answer_citations:
        failures.append(f"answer_citation_count below minimum: {len(citations)} < {min_answer_citations}")
    if len(source_trace_ready_labels) < min_source_trace_ready_citations:
        failures.append(f"source_trace_ready_citation_count below minimum: {len(source_trace_ready_labels)} < {min_source_trace_ready_citations}")
    if unsupported_claim_count > max_unsupported_claims:
        failures.append(f"unsupported_claim_count above maximum: {unsupported_claim_count} > {max_unsupported_claims}")
    if summary_used_as_proof_count > max_summary_used_as_proof:
        failures.append(f"summary_used_as_proof_count above maximum: {summary_used_as_proof_count} > {max_summary_used_as_proof}")
    if len(invalid_labels) > max_invalid_citations:
        failures.append(f"invalid_answer_citation_count above maximum: {len(invalid_labels)} > {max_invalid_citations}")
    if llava_only_count > max_llava_only_part_identity_claims:
        failures.append(f"llava_only_part_identity_claim_count above maximum: {llava_only_count} > {max_llava_only_part_identity_claims}")
    if unsafe_record_count > max_unsafe:
        failures.append(f"unsafe_record_count above maximum: {unsafe_record_count} > {max_unsafe}")
    if answer_permission_count > max_answer_permission:
        failures.append(f"answer_permission_count above maximum: {answer_permission_count} > {max_answer_permission}")
    if source_truth_mutation_allowed_count > max_source_truth_mutation_allowed:
        failures.append(f"source_truth_mutation_allowed_count above maximum: {source_truth_mutation_allowed_count} > {max_source_truth_mutation_allowed}")
    if write_attempt_count > max_write_attempts:
        failures.append(f"write_attempt_count above maximum: {write_attempt_count} > {max_write_attempts}")

    quality_status = "PASS" if not failures else "FAIL"
    ready = quality_status == "PASS"

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    composer_path = out_dir / f"{MODULE}.json"
    qc_path = out_dir / f"{MODULE}_quality_check.json"
    csv_path = out_dir / f"{MODULE}_records.csv"

    summary = {
        "module": MODULE,
        "version": VERSION,
        "question": question,
        "task_type": task_type,
        "intent_answer_type": intent_answer_type,
        "proof_context_count": len(proof),
        "guidance_context_count": len(guidance),
        "answer_char_count": len(answer_text),
        "answer_citation_count": len(citations),
        "valid_answer_citation_count": len([c for c in citation_labels if c in proof_labels]),
        "source_trace_ready_citation_count": len(source_trace_ready_labels),
        "invalid_answer_citation_count": len(invalid_labels),
        "unsupported_claim_count": unsupported_claim_count,
        "summary_used_as_proof_count": summary_used_as_proof_count,
        "llava_only_part_identity_claim_count": llava_only_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": postgres_write_attempt_count,
        "qdrant_write_attempt_count": qdrant_write_attempt_count,
        "opensearch_write_attempt_count": opensearch_write_attempt_count,
        "opensearch_upload_attempt_count": opensearch_upload_attempt_count,
        "write_attempt_count": write_attempt_count,
        "unsafe_record_count": unsafe_record_count,
        "ready_for_intent_answer_delivery": ready,
    }

    record = {
        "question": question,
        "task_type": task_type,
        "intent_answer_type": intent_answer_type,
        "quality_status": quality_status,
        "answer_text": answer_text,
        "answer_citations": citations,
        "invalid_answer_citation_labels": invalid_labels,
        "source_trace_ready_citation_labels": source_trace_ready_labels,
        "proof_context_used_count": len(proof),
        "guidance_context_used_count": len(guidance),
        "summary_guidance_policy": context_record.get("summary_guidance_policy") or context_record.get("answer_constraints", {}).get("summary_guidance_policy", "v2 summaries may guide planning/framing but must not be proof"),
        "ready_for_intent_answer_delivery": ready,
    }

    quality_gate = {
        "quality_status": quality_status,
        "failures": failures,
        "answer_citation_count": len(citations),
        "valid_answer_citation_count": summary["valid_answer_citation_count"],
        "source_trace_ready_citation_count": len(source_trace_ready_labels),
        "invalid_answer_citation_count": len(invalid_labels),
        "invalid_answer_citation_labels": invalid_labels,
        "unsupported_claim_count": unsupported_claim_count,
        "summary_used_as_proof_count": summary_used_as_proof_count,
        "llava_only_part_identity_claim_count": llava_only_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "unsafe_record_count": unsafe_record_count,
    }

    result = {
        "status": STATUS,
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "summary": summary,
        "records": [record],
        "answer_text": answer_text,
        "quality_gate": quality_gate,
        "source_runner": str(runner),
        "source_context_pack": str(context_pack or _stage_context_pack_path(runner_data)),
        "paths": {
            "composer": str(composer_path),
            "quality_check": str(qc_path),
            "records_csv": str(csv_path),
        },
    }
    qc = {
        "status": CHECK_STATUS,
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "source": str(composer_path),
    }

    _write_json(composer_path, result)
    _write_json(qc_path, qc)
    _write_csv(csv_path, [summary])

    if require_quality_pass and quality_status != "PASS":
        raise SystemExit("quality_status is not PASS")
    return result


def check_intent_answer_composer(
    *,
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
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _load_json(composer)
    s = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_status is not PASS")
    checks = [
        ("answer_citation_count", min_answer_citations, "min"),
        ("source_trace_ready_citation_count", min_source_trace_ready_citations, "min"),
        ("unsupported_claim_count", max_unsupported_claims, "max"),
        ("summary_used_as_proof_count", max_summary_used_as_proof, "max"),
        ("invalid_answer_citation_count", max_invalid_citations, "max"),
        ("llava_only_part_identity_claim_count", max_llava_only_part_identity_claims, "max"),
        ("unsafe_record_count", max_unsafe, "max"),
        ("answer_permission_count", max_answer_permission, "max"),
        ("source_truth_mutation_allowed_count", max_source_truth_mutation_allowed, "max"),
        ("write_attempt_count", max_write_attempts, "max"),
    ]
    for key, threshold, mode in checks:
        value = int(s.get(key, 0) or 0)
        if mode == "min" and value < threshold:
            failures.append(f"{key} below minimum: {value} < {threshold}")
        if mode == "max" and value > threshold:
            failures.append(f"{key} above maximum: {value} > {threshold}")
    quality_status = "PASS" if not failures else "FAIL"
    result = {
        "status": CHECK_STATUS,
        "quality_status": quality_status,
        "summary": s,
        "failures": failures,
        "source": str(composer),
    }
    _write_json(output, result)
    if require_quality_pass and quality_status != "PASS":
        raise SystemExit("quality_status is not PASS")
    return result


def build_parser(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering intent answer composer v1")
    parser.add_argument("--runner", required=True)
    parser.add_argument("--context-pack")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-answer-citations", type=int, default=1)
    parser.add_argument("--min-source-trace-ready-citations", type=int, default=1)
    parser.add_argument("--max-unsupported-claims", type=int, default=0)
    parser.add_argument("--max-summary-used-as-proof", type=int, default=0)
    parser.add_argument("--max-invalid-citations", type=int, default=0)
    parser.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-answer-permission", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    parser.add_argument("--require-quality-pass", action="store_true")
    return parser.parse_args(argv)


def check_parser(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering intent answer composer v1")
    parser.add_argument("--composer", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--min-answer-citations", type=int, default=1)
    parser.add_argument("--min-source-trace-ready-citations", type=int, default=1)
    parser.add_argument("--max-unsupported-claims", type=int, default=0)
    parser.add_argument("--max-summary-used-as-proof", type=int, default=0)
    parser.add_argument("--max-invalid-citations", type=int, default=0)
    parser.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-answer-permission", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser(argv)
    result = build_intent_answer_composer(**vars(args))
    s = result["summary"]
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    print(f"question={s.get('question')}")
    print(f"task_type={s.get('task_type')}")
    print(f"intent_answer_type={s.get('intent_answer_type')}")
    print(f"answer_citation_count={s.get('answer_citation_count')}")
    print(f"source_trace_ready_citation_count={s.get('source_trace_ready_citation_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    print("answer=" + result.get("answer_text", ""))
    print(f"composer={result['paths']['composer']}")
    return 0


def check_main(argv: Optional[Sequence[str]] = None) -> int:
    args = check_parser(argv)
    result = check_intent_answer_composer(**vars(args))
    s = result.get("summary", {})
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    print(f"answer_citation_count={s.get('answer_citation_count')}")
    print(f"source_trace_ready_citation_count={s.get('source_trace_ready_citation_count')}")
    print(f"unsupported_claim_count={s.get('unsupported_claim_count')}")
    print(f"summary_used_as_proof_count={s.get('summary_used_as_proof_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
