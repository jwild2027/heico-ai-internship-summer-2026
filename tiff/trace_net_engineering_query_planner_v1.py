from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "v1"
MODULE = "trace_net_engineering_query_planner_v1"
STATUS_BUILT = "TRACE_NET_ENGINEERING_QUERY_PLANNER_BUILT"
STATUS_CHECKED = "TRACE_NET_ENGINEERING_QUERY_PLANNER_QUALITY_CHECKED"

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
FIG_RE = re.compile(r"\b(?:fig(?:ure)?\.?\s*|figure\s+)(\d{1,4}[A-Z]?)\b", re.IGNORECASE)
ITEM_RE = re.compile(r"\b(?:item|callout|call-out)\s*#?\s*(\d{1,4}[A-Z]?)\b", re.IGNORECASE)
FAMILY_RE = re.compile(r"\b\d{3}-\d{5}\b")
WORD_RE = re.compile(r"[a-z0-9][a-z0-9_\-]{1,}", re.IGNORECASE)

TOPIC_TERMS = [
    "illustrated parts list",
    "maintenance manual",
    "double passenger seat",
    "passenger seat",
    "armrest",
    "structure",
    "table",
    "figure",
    "diagram",
    "nomenclature",
    "effectivity",
    "interchangeability",
    "installation",
    "replacement",
]

FORBIDDEN_CLAIMS_DEFAULT = [
    "interchangeability",
    "effectivity",
    "fit",
    "replacement approval",
    "installation safety",
]

ROUTE_CAPABILITIES = {
    "exact_part_lookup": ["exact_part_number", "table_ocr_proof", "graph_leiden_neighbors", "answer_quality_gate"],
    "figure_item_lookup": ["figure_or_item", "table_ocr_proof", "multi_route_quality_gate"],
    "visual_part_identification": ["image_or_diagram", "table_ocr_proof", "raw_ocr_nomenclature", "image_route_quality_gate"],
    "part_family_expansion": ["part_family", "graph_leiden_neighbors", "table_ocr_proof", "multi_route_quality_gate"],
    "table_extraction_question": ["table_route", "ocr_table_proof", "table_quality_gate"],
    "troubleshooting_question": ["diagnostic_context", "route_quality_audit", "human_review_queue_optional"],
    "comparison_question": ["multi_entity_retrieval", "table_ocr_proof", "graph_leiden_neighbors", "engineering_quality_gate"],
    "procedure_question": ["manual_section_guidance", "ocr_text_support", "engineering_quality_gate"],
    "manual_section_summary": ["v2_summary_guidance", "ocr_text_support", "summary_not_proof_gate"],
    "general_engineering_question": ["v2_summary_guidance", "ocr_text_support", "engineering_quality_gate"],
    "unknown_or_insufficient_evidence": ["v2_summary_guidance", "clarify_or_retrieve_more", "engineering_quality_gate"],
}

TASK_INTENTS = {
    "exact_part_lookup": "identify or locate an exact part number using source-traced evidence",
    "figure_item_lookup": "identify a figure/item or callout using figure/table evidence",
    "visual_part_identification": "identify what a visual figure or diagram shows using image plus OCR/table proof",
    "part_family_expansion": "find related part-family context without claiming interchangeability",
    "table_extraction_question": "inspect or extract structured table/OCR records",
    "troubleshooting_question": "diagnose pipeline/evidence/routing behavior",
    "comparison_question": "compare entities or evidence strength with limits",
    "procedure_question": "produce a safe verification or workflow plan",
    "manual_section_summary": "summarize likely manual section context with proof separation",
    "general_engineering_question": "answer a broad engineering question with proof and limits",
    "unknown_or_insufficient_evidence": "plan retrieval because the evidence need is unclear or insufficient",
}


def _load_json(path: Any) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return data


def _write_json(path: Any, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_csv(path: Any, records: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "question",
        "task_type",
        "engineering_intent",
        "entities_json",
        "required_routes_json",
        "optional_routes_json",
        "guidance_page_count",
        "can_answer_from_summaries_only",
        "answer_permission",
        "source_truth_mutation_allowed",
    ]
    lines = [",".join(columns)]
    for r in records:
        row = []
        for c in columns:
            value = r.get(c, "")
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            s = str(value).replace('"', '""')
            row.append(f'"{s}"')
        lines.append(",".join(row))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def extract_entities(question: str) -> Dict[str, Any]:
    q = _norm_text(question)
    part_numbers = sorted(set(PART_RE.findall(q)))
    figures = sorted(set(m.group(1).upper() for m in FIG_RE.finditer(q)), key=lambda x: (len(x), x))
    items = sorted(set(m.group(1).upper() for m in ITEM_RE.finditer(q)), key=lambda x: (len(x), x))
    families = sorted(set(FAMILY_RE.findall(q)) - {p[:9] for p in part_numbers})

    words = [w.lower() for w in WORD_RE.findall(q)]
    stop = {
        "what", "does", "show", "find", "the", "this", "that", "with", "from", "use", "trace", "net",
        "and", "or", "for", "can", "you", "how", "why", "are", "is", "a", "an", "to", "of", "in",
    }
    topics = []
    low = q.lower()
    for term in TOPIC_TERMS:
        if term in low:
            topics.append(term)
    for w in words:
        if w not in stop and not PART_RE.fullmatch(w) and len(w) >= 4 and w not in topics:
            if w in {"figure", "diagram", "table", "route", "summary", "part", "family", "engineer", "evidence"}:
                topics.append(w)
    return {
        "part_numbers": part_numbers,
        "figures": figures,
        "items": items,
        "part_families": families,
        "topics": topics[:12],
    }


def classify_task(question: str, entities: Mapping[str, Any]) -> str:
    q = _norm_text(question).lower()
    figures = entities.get("figures") or []
    items = entities.get("items") or []
    parts = entities.get("part_numbers") or []
    families = entities.get("part_families") or []

    if any(w in q for w in ["why", "error", "fail", "failing", "issue", "bug", "low confidence", "not working", "broken"]):
        return "troubleshooting_question"
    if any(w in q for w in ["compare", "difference", "versus", " vs ", "better", "which route", "stronger evidence"]):
        return "comparison_question"
    if any(w in q for w in ["steps", "procedure", "how do i", "how should", "verify", "inspect", "run next"]):
        return "procedure_question"
    if any(w in q for w in ["table", "row", "column", "extract", "cell", "csv"]):
        return "table_extraction_question"
    if any(w in q for w in ["family", "nearby", "similar", "related parts", "variants"]):
        return "part_family_expansion"
    if figures and items:
        return "figure_item_lookup"
    if figures and any(w in q for w in ["show", "figure", "diagram", "visual", "callout", "looks", "what does"]):
        return "visual_part_identification"
    if parts:
        return "exact_part_lookup"
    if any(w in q for w in ["summary", "summarize", "section", "about", "overview"]):
        return "manual_section_summary"
    if families:
        return "part_family_expansion"
    return "general_engineering_question"


def _guidance_records(index: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records = index.get("records", [])
    if not isinstance(records, list):
        return []
    out = []
    for r in records:
        if isinstance(r, dict) and r.get("guidance_only") is True:
            out.append(dict(r))
    return out


def _tokenize(s: str) -> List[str]:
    stop = {"this", "that", "page", "from", "with", "what", "does", "show", "find", "part", "figure", "manual"}
    return [w.lower() for w in WORD_RE.findall(s) if len(w) >= 3 and w.lower() not in stop]


def score_guidance_record(record: Mapping[str, Any], question: str, entities: Mapping[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []
    text = " ".join([
        _norm_text(record.get("summary_text")),
        " ".join(record.get("detected_topics") or []),
        " ".join(record.get("detected_figures") or []),
        " ".join(record.get("detected_part_numbers") or []),
        _norm_text(record.get("manual_section_hint")),
    ]).lower()

    for fig in entities.get("figures") or []:
        if fig.lower() in {str(x).lower() for x in record.get("detected_figures") or []} or f"figure {fig.lower()}" in text or f"fig. {fig.lower()}" in text:
            score += 50
            reasons.append(f"figure_hint:{fig}")
    for part in entities.get("part_numbers") or []:
        if part.lower() in text:
            score += 60
            reasons.append(f"part_hint:{part}")
    for fam in entities.get("part_families") or []:
        if fam.lower() in text:
            score += 25
            reasons.append(f"family_hint:{fam}")

    q_tokens = set(_tokenize(question))
    r_tokens = set(_tokenize(text))
    overlap = sorted(q_tokens & r_tokens)
    if overlap:
        add = min(20, 4 * len(overlap))
        score += add
        reasons.append("topic_overlap:" + "/".join(overlap[:6]))

    manual_hint = _norm_text(record.get("manual_section_hint"))
    if manual_hint and manual_hint != "unknown":
        score += 3
        reasons.append(f"manual_section:{manual_hint}")

    return score, reasons


def _is_specific_entity_query(entities: Mapping[str, Any], task_type: Optional[str] = None) -> bool:
    """Return true when generic v2 summary pages would be misleading.

    For specific part/figure/family questions, v2 summaries should only guide planning
    when they mention the exact requested entity. Otherwise the planner should return
    no guidance pages instead of filling the context with generic IPL/manual pages.
    """
    if entities.get("figures") or entities.get("part_numbers") or entities.get("items") or entities.get("part_families"):
        return True
    return task_type in {"visual_part_identification", "figure_item_lookup", "exact_part_lookup", "part_family_expansion"}


def _has_strong_entity_reason(reasons: Sequence[str]) -> bool:
    prefixes = ("figure_hint:", "part_hint:", "family_hint:")
    return any(str(reason).startswith(prefixes) for reason in reasons)


def select_guidance_pages(
    index: Mapping[str, Any],
    question: str,
    entities: Mapping[str, Any],
    max_guidance_pages: int = 8,
    task_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    strict_entity_guidance = _is_specific_entity_query(entities, task_type=task_type)
    scored = []
    for r in _guidance_records(index):
        score, reasons = score_guidance_record(r, question, entities)
        if score <= 0:
            continue

        if strict_entity_guidance and not _has_strong_entity_reason(reasons):
            # Do not use generic IPL/maintenance summaries for specific entity questions.
            # They can steer the planner away from the real proof artifacts.
            continue

        scored.append((score, r.get("page_number"), r.get("page_id"), r, reasons))
    scored.sort(key=lambda x: (-x[0], str(x[1]), str(x[2])))

    seen_pages = set()
    selected: List[Dict[str, Any]] = []
    for score, _, _, r, reasons in scored:
        page_key = r.get("page_id") or r.get("page_number")
        if page_key in seen_pages:
            continue
        seen_pages.add(page_key)
        selected.append({
            "page_id": r.get("page_id"),
            "page_number": r.get("page_number"),
            "summary_text": r.get("summary_text"),
            "detected_figures": r.get("detected_figures") or [],
            "detected_part_numbers": r.get("detected_part_numbers") or [],
            "detected_topics": r.get("detected_topics") or [],
            "manual_section_hint": r.get("manual_section_hint"),
            "guidance_score": score,
            "guidance_reasons": reasons,
            "guidance_only": True,
            "source_trace_ready": bool(r.get("source_trace_ready")),
        })
        if len(selected) >= max_guidance_pages:
            break
    return selected


def _proof_requirements(task_type: str, entities: Mapping[str, Any]) -> List[str]:
    if task_type == "visual_part_identification":
        return ["visual figure/page evidence", "linked part number proof", "OCR/table nomenclature evidence", "source-trace-ready citation"]
    if task_type == "figure_item_lookup":
        return ["figure/item table record", "linked part number record", "source-trace-ready citation"]
    if task_type == "exact_part_lookup":
        return ["exact part-number evidence", "OCR/table source trace", "citation-backed result"]
    if task_type == "part_family_expansion":
        return ["part-prefix evidence", "graph/Leiden context", "explicit non-interchangeability limit"]
    if task_type == "table_extraction_question":
        return ["table/OCR cell or row evidence", "source cell/page trace", "quality-check status"]
    if task_type == "troubleshooting_question":
        return ["error log or artifact status", "affected module", "reproducible command or quality counters"]
    if task_type == "manual_section_summary":
        return ["OCR/page evidence supporting summary", "summary guidance marked guidance-only"]
    return ["source-trace-ready evidence", "explicit assumptions and limits"]


def _optional_routes(task_type: str) -> List[str]:
    if task_type in {"visual_part_identification", "figure_item_lookup"}:
        return ["graph_leiden_neighbors", "part_family"]
    if task_type == "exact_part_lookup":
        return ["part_family", "image_or_diagram"]
    if task_type == "troubleshooting_question":
        return ["human_review_queue", "artifact_lineage_audit"]
    return ["graph_leiden_neighbors"]



def _unique_preserve_order(values: Sequence[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.upper()
        if key not in seen:
            seen.add(key)
            out.append(text)
    return out



def _extract_engineer_part_number_candidates(question: str) -> List[str]:
    """Extract loose engineering part-number candidates from messy prompts."""
    out: List[str] = []

    # Strong explicit PN pattern: "PN DF250040-501"
    for match in re.finditer(r"\bPN\s+([A-Z0-9][A-Z0-9-]{4,})\b", question, flags=re.IGNORECASE):
        out.append(match.group(1).upper())

    # Mixed alpha/digit engineering IDs, with or without hyphens.
    for match in re.finditer(r"\b[A-Z0-9]*[A-Z][A-Z0-9-]*[0-9][A-Z0-9-]*\b|\b[A-Z0-9]*[0-9][A-Z0-9-]*[A-Z][A-Z0-9-]*\b", question, flags=re.IGNORECASE):
        raw_value = match.group(0).strip("-")
        value = raw_value.upper()

        # Messy prompts often write "2312M87G01-sealFace"; keep the real PN
        # and drop obvious English/nomenclature suffixes.
        if "-" in raw_value:
            first, rest = raw_value.split("-", 1)
            if re.search(r"[0-9]", first) and re.search(r"[A-Za-z]", first) and rest.isalpha():
                value = first.upper()

        if len(value) < 6:
            continue
        if value.startswith("GENX"):
            continue
        if value in {"BOEING"}:
            continue

        # Aircraft/platform strings are filters, not part numbers.
        if re.fullmatch(r"A3[0-9]{2}|B?7[0-9]{2}", value):
            continue
        if re.fullmatch(r"A3[0-9]{2}-[0-9]{3}", value):
            continue
        if re.fullmatch(r"A3[0-9]{2}-A?3[0-9]{2}", value):
            continue
        if re.fullmatch(r"B?7[0-9]{2}-B?7[0-9]{2}", value):
            continue

        out.append(value)

    return _unique_preserve_order(out)

def _extract_requested_doc_types(question: str) -> List[str]:
    q = _norm_text(question).upper()
    doc_types: List[str] = []
    for doc_type in ("IPC", "CMM", "SB", "AMM", "SRM", "WDM", "IPL"):
        if doc_type in q.replace("/", " ").replace(",", " ").split() or f"/{doc_type}" in q or f"{doc_type}/" in q:
            doc_types.append(doc_type)
    if "SERVICE BULLETIN" in q:
        doc_types.append("SB")
    if "ILLUSTRATED PARTS" in q:
        doc_types.append("IPC")
    if "COMPONENT MAINTENANCE" in q:
        doc_types.append("CMM")
    return _unique_preserve_order(doc_types)


def _extract_partial_identifier_candidates(question: str) -> List[str]:
    out: List[str] = []
    for match in re.finditer(r"\b([A-Z0-9]{3,}[A-Z][A-Z0-9]*)\s*(?:\.\.\.|…)", question, flags=re.IGNORECASE):
        out.append(match.group(1).upper())
    return _unique_preserve_order(out)


def _extract_engine_candidates(question: str) -> List[str]:
    out: List[str] = []
    for match in re.finditer(r"\bGEnx[-\s]*[0-9][A-Za-z0-9-]*\b", question, flags=re.IGNORECASE):
        value = match.group(0).replace(" ", "-")
        value = value[:4] + value[4:].upper() if value.lower().startswith("genx") else value
        out.append(value)
    return _unique_preserve_order(out)


def _extract_fleet_candidates(question: str) -> List[str]:
    q = _norm_text(question)
    out: List[str] = []

    for match in re.finditer(r"\bA(3[0-9]{2})\s*[-–]\s*(?:A)?(3[0-9]{2})\b", q, flags=re.IGNORECASE):
        start = int(match.group(1))
        end = int(match.group(2))
        if start <= end and end - start <= 10:
            out.extend([f"A{i}" for i in range(start, end + 1)])

    for match in re.finditer(r"\b(?:B|BOEING\s*)?(7[0-9]{2})\b", q, flags=re.IGNORECASE):
        value = match.group(1)
        out.append(f"B{value}" if "boeing" in q.lower() or value in {"737", "747", "757", "767", "777", "787"} else value)

    for match in re.finditer(r"\bA3[0-9]{2}\b", q, flags=re.IGNORECASE):
        out.append(match.group(0).upper())

    return _unique_preserve_order(out)


def _extract_part_description_candidates(question: str) -> List[str]:
    q = _norm_text(question)
    lowered = q.lower()
    descriptions: List[str] = []

    known_phrases = [
        "paper towel dispenser",
        "seal face",
        "sealface",
        "gearbox assy",
        "gearbox assembly",
        "module assy",
        "access gearbox",
        "accessory gearbox",
    ]
    for phrase in known_phrases:
        if phrase in lowered:
            descriptions.append("seal face" if phrase == "sealface" else phrase)

    pn_match = re.search(r"\bPN\s+[A-Z0-9-]+\s+([A-Za-z][A-Za-z0-9 /-]{3,80})", q, flags=re.IGNORECASE)
    if pn_match:
        candidate = pn_match.group(1).strip(" ?.!,;:")
        candidate = re.split(r"\bLikely\b|\bUsed\b|\bFleet\b", candidate, flags=re.IGNORECASE)[0].strip(" ?.!,;:")
        if candidate:
            descriptions.append(candidate)

    return _unique_preserve_order(descriptions)


def _infer_ata_candidates(question: str, descriptions: Sequence[str]) -> List[str]:
    q = _norm_text(question).lower()
    joined = " ".join(descriptions).lower()
    candidates: List[str] = []

    explicit = re.findall(r"\bATA\s*([0-9]{2}(?:-[0-9]{2})?)\b", question, flags=re.IGNORECASE)
    candidates.extend(explicit)

    if any(term in q or term in joined for term in ["paper towel", "dispenser", "cabin", "interior", "lavatory", "galley"]):
        candidates.append("25")

    return _unique_preserve_order(candidates)


def build_engineer_clarification_profile(question: str, entities: Mapping[str, Any], task_type: str) -> Dict[str, Any]:
    """Build engineer-facing narrowing filters and follow-up questions.

    This is guidance only. It does not execute retrieval, call an LLM, mutate
    source truth, or grant answer permission.
    """
    q = _norm_text(question)
    lowered = q.lower()

    part_numbers = _unique_preserve_order(
        [str(x) for x in entities.get("part_numbers") or []]
        + _extract_engineer_part_number_candidates(question)
    )
    partial_ids = _extract_partial_identifier_candidates(question)
    doc_types = _extract_requested_doc_types(question)
    engines = _extract_engine_candidates(question)
    fleets = _extract_fleet_candidates(question)
    descriptions = _extract_part_description_candidates(question)
    ata_candidates = _infer_ata_candidates(question, descriptions)

    eligibility_intent = any(w in lowered for w in ["eligib", "elegib", "applicab", "effectiv", "approved", "approval", "interchange", "installation authorization"])
    nha_intent = "nha" in lowered or "next higher" in lowered

    extracted = {
        "part_number_candidates": part_numbers,
        "partial_identifier_candidates": partial_ids,
        "nha_candidates": partial_ids if nha_intent else [],
        "requested_doc_types": doc_types,
        "engine_candidates": engines,
        "fleet_candidates": fleets,
        "ata_candidates": ata_candidates,
        "part_description_candidates": descriptions,
        "eligibility_or_applicability_intent": eligibility_intent,
        "nha_intent": nha_intent,
    }

    facet_filters = {
        "part_number": part_numbers,
        "partial_identifier": partial_ids,
        "nha": partial_ids if nha_intent else [],
        "document_type": doc_types,
        "engine": engines,
        "fleet_or_aircraft": fleets,
        "ata": ata_candidates,
        "description": descriptions,
        "evidence_language": (
            ["eligibility", "applicability", "effectivity", "approved installation", "interchangeability"]
            if eligibility_intent else []
        ),
    }

    risk_flags: List[str] = ["source_evidence_required"]
    if partial_ids:
        risk_flags.append("partial_identifier_requires_clarification")
    if len(doc_types) > 1:
        risk_flags.append("multiple_document_types_requested")
    if eligibility_intent:
        risk_flags.append("eligibility_requires_authority_not_mention_only")
    if fleets:
        risk_flags.append("fleet_or_platform_filter_required")
    if nha_intent:
        risk_flags.append("nha_filter_required")
    if not part_numbers and partial_ids:
        risk_flags.append("no_complete_part_number_detected")

    questions: List[str] = []
    if len(doc_types) > 1:
        questions.append("Which document type should I prioritize first: " + ", ".join(doc_types) + "?")
    if partial_ids:
        questions.append("Can you confirm the full NHA or partial identifier that starts with " + ", ".join(partial_ids) + "?")
    if eligibility_intent:
        questions.append("Do you need eligibility by aircraft platform, document type, or approval/effectivity proof?")
    if fleets:
        questions.append("Should I narrow by fleet/platform first: " + ", ".join(fleets) + "?")
    if not questions:
        questions.append("Should I prioritize exact part matches, ATA/manual family, or source-proof evidence first?")

    return {
        "profile_type": "engineer_query_clarification_profile_v1",
        "memory_layer": "working_memory",
        "secondary_memory_layers": [
            "procedural_memory",
            "semantic_memory",
            "critic_memory",
        ],
        "proof_role": "guidance_only",
        "can_be_used_as_proof": False,
        "guidance_only": True,
        "extracted_engineer_clues": extracted,
        "facet_filters": facet_filters,
        "clarifying_questions": _unique_preserve_order(questions)[:4],
        "risk_flags": _unique_preserve_order(risk_flags),
        "recommended_first_pass": [
            "use exact part number when available",
            "use partial/NHA filters only as narrowing hints",
            "use V2/V3 summaries as routing guidance only",
            "resolve candidate result back to OCR/table/visual/source-trace evidence before answering",
        ],
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }

def build_plan_record(question: str, index: Mapping[str, Any], max_guidance_pages: int = 8) -> Dict[str, Any]:
    entities = extract_entities(question)
    task_type = classify_task(question, entities)
    required_routes = list(ROUTE_CAPABILITIES.get(task_type, ROUTE_CAPABILITIES["general_engineering_question"]))
    guidance_pages = select_guidance_pages(index, question, entities, max_guidance_pages=max_guidance_pages, task_type=task_type)

    forbidden = list(FORBIDDEN_CLAIMS_DEFAULT)
    if task_type in {"manual_section_summary", "procedure_question", "troubleshooting_question"}:
        forbidden.extend(["summary-only proof", "unsupported source-truth mutation"])
    if task_type == "visual_part_identification":
        forbidden.extend(["LLaVA-only part identity", "summary-only figure proof"])

    can_answer_from_summaries_only = False
    engineer_clarification_profile = build_engineer_clarification_profile(question, entities, task_type)

    record = {
        "module": MODULE,
        "version": VERSION,
        "question": question,
        "task_type": task_type,
        "engineering_intent": TASK_INTENTS.get(task_type, TASK_INTENTS["general_engineering_question"]),
        "entities": entities,
        "engineer_clarification_profile": engineer_clarification_profile,
        "extracted_engineer_clues": engineer_clarification_profile.get("extracted_engineer_clues", {}),
        "facet_filters": engineer_clarification_profile.get("facet_filters", {}),
        "clarifying_questions": engineer_clarification_profile.get("clarifying_questions", []),
        "risk_flags": engineer_clarification_profile.get("risk_flags", []),
        "guidance_pages": guidance_pages,
        "guidance_page_count": len(guidance_pages),
        "required_routes": required_routes,
        "required_route_count": len(required_routes),
        "optional_routes": _optional_routes(task_type),
        "proof_requirements": _proof_requirements(task_type, entities),
        "forbidden_claims": sorted(set(forbidden)),
        "answer_style": "engineering_brain",
        "can_answer_from_summaries_only": can_answer_from_summaries_only,
        "summary_guidance_policy": "v2 summaries may guide route planning and answer framing, but must not be used as proof",
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "opensearch_upload_attempt": False,
        "unsafe_record": False,
    }
    record["entities_json"] = json.dumps(entities, ensure_ascii=False)
    record["engineer_clarification_profile_json"] = json.dumps(engineer_clarification_profile, ensure_ascii=False)
    record["facet_filters_json"] = json.dumps(record["facet_filters"], ensure_ascii=False)
    record["clarifying_questions_json"] = json.dumps(record["clarifying_questions"], ensure_ascii=False)
    record["risk_flags_json"] = json.dumps(record["risk_flags"], ensure_ascii=False)
    record["required_routes_json"] = json.dumps(required_routes, ensure_ascii=False)
    record["optional_routes_json"] = json.dumps(record["optional_routes"], ensure_ascii=False)
    return record


def summarize(records: Sequence[Mapping[str, Any]], source_index: Mapping[str, Any]) -> Dict[str, Any]:
    planner_record_count = len(records)
    required_route_count = sum(int(r.get("required_route_count") or 0) for r in records)
    selected_guidance_page_count = sum(int(r.get("guidance_page_count") or 0) for r in records)
    guidance_only_summary_count = 0
    for r in records:
        for g in r.get("guidance_pages") or []:
            if isinstance(g, dict) and g.get("guidance_only") is True:
                guidance_only_summary_count += 1
    source_summary = source_index.get("summary", {}) if isinstance(source_index.get("summary"), dict) else {}
    return {
        "planner_record_count": planner_record_count,
        "task_type_count": len({r.get("task_type") for r in records}),
        "required_route_count": required_route_count,
        "selected_guidance_page_count": selected_guidance_page_count,
        "guidance_only_summary_count": guidance_only_summary_count,
        "source_guidance_summary_record_count": source_summary.get("summary_record_count", len(_guidance_records(source_index))),
        "can_answer_from_summaries_only_count": sum(1 for r in records if r.get("can_answer_from_summaries_only")),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
        "opensearch_upload_attempt_count": sum(1 for r in records if r.get("opensearch_upload_attempt")),
        "write_attempt_count": 0,
        "unsafe_record_count": sum(1 for r in records if r.get("unsafe_record")),
        "ready_for_engineering_context_pack": True,
    }


def _quality(summary: Mapping[str, Any], *, min_planner_records: int, min_required_routes: int, max_unsafe: int, max_answer_permission: int, max_source_truth_mutation_allowed: int, max_write_attempts: int, require_no_summary_only_answer: bool = True) -> Tuple[str, List[str]]:
    failures: List[str] = []
    if int(summary.get("planner_record_count") or 0) < min_planner_records:
        failures.append(f"planner_record_count below minimum: {summary.get('planner_record_count')} < {min_planner_records}")
    if int(summary.get("required_route_count") or 0) < min_required_routes:
        failures.append(f"required_route_count below minimum: {summary.get('required_route_count')} < {min_required_routes}")
    if int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append("unsafe_record_count above maximum")
    if int(summary.get("answer_permission_count") or 0) > max_answer_permission:
        failures.append("answer_permission_count above maximum")
    if int(summary.get("source_truth_mutation_allowed_count") or 0) > max_source_truth_mutation_allowed:
        failures.append("source_truth_mutation_allowed_count above maximum")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count above maximum")
    if require_no_summary_only_answer and int(summary.get("can_answer_from_summaries_only_count") or 0) != 0:
        failures.append("summaries are being allowed as proof")
    return ("PASS" if not failures else "FAIL", failures)


def build_engineering_query_planner(
    *,
    question: str,
    v2_summary_guidance_index: Any,
    output_dir: Any,
    max_guidance_pages: int = 8,
    min_planner_records: int = 1,
    min_required_routes: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    index = _load_json(v2_summary_guidance_index)
    record = build_plan_record(question, index, max_guidance_pages=max_guidance_pages)
    records = [record]
    summary = summarize(records, index)
    quality_status, failures = _quality(
        summary,
        min_planner_records=min_planner_records,
        min_required_routes=min_required_routes,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    out_dir = Path(output_dir)
    manifest_path = out_dir / "trace_net_engineering_query_planner_v1.json"
    quality_path = out_dir / "trace_net_engineering_query_planner_v1_quality_check.json"
    records_csv_path = out_dir / "trace_net_engineering_query_planner_v1_records.csv"

    manifest = {
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "question": question,
        "source_v2_summary_guidance_index": str(v2_summary_guidance_index),
        "summary": summary,
        "failures": failures,
        "records": records,
        "paths": {
            "planner": str(manifest_path),
            "quality_check": str(quality_path),
            "records_csv": str(records_csv_path),
        },
    }
    _write_json(manifest_path, manifest)
    _write_json(quality_path, {
        "status": STATUS_CHECKED,
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
    })
    _write_csv(records_csv_path, records)
    return manifest


def check_engineering_query_planner(
    *,
    planner: Any,
    output: Any,
    require_quality_pass: bool = False,
    min_planner_records: int = 1,
    min_required_routes: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _load_json(planner)
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else summarize(data.get("records") or [], {})
    quality_status, failures = _quality(
        summary,
        min_planner_records=min_planner_records,
        min_required_routes=min_required_routes,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("source planner quality_status is not PASS")
    if require_quality_pass and quality_status != "PASS":
        failures.append("quality check status is not PASS")
    final_status = "PASS" if not failures else "FAIL"
    result = {
        "status": STATUS_CHECKED,
        "quality_status": final_status,
        "summary": summary,
        "failures": failures,
        "source_planner": str(planner),
    }
    _write_json(output, result)
    return result


def _parse_build_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build TRACE-Net engineering query planner v1")
    ap.add_argument("--question", required=True)
    ap.add_argument("--v2-summary-guidance-index", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-guidance-pages", type=int, default=8)
    ap.add_argument("--min-planner-records", type=int, default=1)
    ap.add_argument("--min-required-routes", type=int, default=1)
    ap.add_argument("--max-unsafe", type=int, default=0)
    ap.add_argument("--max-answer-permission", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--max-write-attempts", type=int, default=0)
    return ap.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_build_args(argv)
    result = build_engineering_query_planner(
        question=args.question,
        v2_summary_guidance_index=args.v2_summary_guidance_index,
        output_dir=args.output_dir,
        max_guidance_pages=args.max_guidance_pages,
        min_planner_records=args.min_planner_records,
        min_required_routes=args.min_required_routes,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    summary = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    rec = (result.get("records") or [{}])[0]
    print(f"task_type={rec.get('task_type')}")
    print(f"required_route_count={summary.get('required_route_count')}")
    print(f"selected_guidance_page_count={summary.get('selected_guidance_page_count')}")
    print(f"can_answer_from_summaries_only_count={summary.get('can_answer_from_summaries_only_count')}")
    print(f"unsafe_record_count={summary.get('unsafe_record_count')}")
    print(f"answer_permission_count={summary.get('answer_permission_count')}")
    print(f"source_truth_mutation_allowed_count={summary.get('source_truth_mutation_allowed_count')}")
    print(f"write_attempt_count={summary.get('write_attempt_count')}")
    print(f"planner={result.get('paths', {}).get('planner')}")
    return 0 if result.get("quality_status") == "PASS" else 1


def _parse_check_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Check TRACE-Net engineering query planner v1")
    ap.add_argument("--planner", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--require-quality-pass", action="store_true")
    ap.add_argument("--min-planner-records", type=int, default=1)
    ap.add_argument("--min-required-routes", type=int, default=1)
    ap.add_argument("--max-unsafe", type=int, default=0)
    ap.add_argument("--max-answer-permission", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--max-write-attempts", type=int, default=0)
    return ap.parse_args(argv)


def check_main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_check_args(argv)
    result = check_engineering_query_planner(
        planner=args.planner,
        output=args.output,
        require_quality_pass=args.require_quality_pass,
        min_planner_records=args.min_planner_records,
        min_required_routes=args.min_required_routes,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    summary = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"planner_record_count={summary.get('planner_record_count')}")
    print(f"required_route_count={summary.get('required_route_count')}")
    print(f"selected_guidance_page_count={summary.get('selected_guidance_page_count')}")
    print(f"unsafe_record_count={summary.get('unsafe_record_count')}")
    print(f"answer_permission_count={summary.get('answer_permission_count')}")
    print(f"source_truth_mutation_allowed_count={summary.get('source_truth_mutation_allowed_count')}")
    print(f"write_attempt_count={summary.get('write_attempt_count')}")
    return 0 if result.get("quality_status") == "PASS" else 1



# Compatibility aliases for older scripts/tests.
# Keep these names because the script wrapper and unit tests import them directly.
def check_engineering_query_planner_quality(
    *,
    report_path,
    output=None,
    require_no_llm_calls=False,
    require_no_retrieval_execution=False,
    require_no_answer_permission=False,
    require_no_source_truth_mutation=True,
    require_no_unsafe=True,
):
    """Compatibility quality checker for older tests/scripts.

    This checks a planner/report JSON summary without executing retrieval,
    calling an LLM, mutating source truth, or granting answer permission.
    """
    data = _load_json(report_path)
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else data

    failures = []

    if require_no_unsafe and int(summary.get("unsafe_record_count") or 0) != 0:
        failures.append("unsafe_record_count must be 0")

    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count must be 0")

    if require_no_answer_permission and int(summary.get("can_answer_directly_count") or 0) != 0:
        failures.append("can_answer_directly_count must be 0")

    if require_no_answer_permission and int(summary.get("can_prove_claims_count") or 0) != 0:
        failures.append("can_prove_claims_count must be 0")

    if require_no_llm_calls and int(summary.get("llm_call_allowed_count") or 0) != 0:
        failures.append("llm_call_allowed_count must be 0")

    if require_no_retrieval_execution and int(summary.get("retrieval_execution_allowed_count") or 0) != 0:
        failures.append("retrieval_execution_allowed_count must be 0")

    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source_truth_mutation_allowed_count must be 0")

    result = {
        "status": STATUS_CHECKED,
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "failures": failures,
        "source_report": str(report_path),
    }

    if output is not None:
        _write_json(output, result)

    return result


def main_check(argv=None):
    return check_main(argv)

if __name__ == "__main__":
    raise SystemExit(main())
