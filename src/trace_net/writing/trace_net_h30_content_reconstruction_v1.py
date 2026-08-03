#!/usr/bin/env python3
"""TRACE-Net H30 Phase 3 content-specific evidence reconstruction.

This final writer overlay improves the meaning reconstructed from already-selected
claim-ready evidence. It does not retrieve, rerank, select a route, call an LLM,
grant answer authority, or mutate source truth.

Targeted behavior:
* ATA routes classify cited page leads by content role and separate navigation
  guidance from direct part/table proof.
* IPL/table routes reconstruct only explicit same-row fields around the requested
  part number.
* Procedure routes preserve lettered sequence boundaries and detect resets.
* Visual routes add callout-to-part mappings only when an explicit cited record
  contains both the callout and part number.

All output is revalidated against the existing citation registry. A previously
valid answer is retained whenever the reconstructed answer is not accepted.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_content_reconstruction_v1"
VERSION = "v1"
STATUS = "TRACE_NET_H30_CONTENT_RECONSTRUCTION_V1"
PATCH_ID = "trace_net_h30_phase3_content_reconstruction_v1"

TARGET_ROUTES = {
    "ata_system_discovery",
    "exact_table_ipl_lookup",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
}

PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
PART_RE = re.compile(
    r"\b(?:\d{2,4}-\d{4,6}(?:-\d{3})?(?:/\d{3})?|"
    r"[A-Z]{2,}\d{4,}(?:[-./][A-Z0-9]+)*)\b",
    re.I,
)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
FIGURE_RE = re.compile(
    r"\b(?:figure|fig\.?)\s*[\s#:.-]*(\d{1,4})(?:\s+sheet\s+(\d{1,3}))?\b",
    re.I,
)
STEP_RE = re.compile(
    r"(?:\(([a-z])\)|(?<![A-Za-z0-9])([a-z])[.)])\s+"
    r"(.+?)(?=(?:\([a-z]\)|(?<![A-Za-z0-9])[a-z][.)])\s+|"
    r"\bNOTE\s*:|\bCAUTION\s*:|\bWARNING\s*:|$)",
    re.I | re.S,
)

SAFETY_CONTRACT = {
    "read_only": True,
    "claim_ready_evidence_is_input_not_retrieval": True,
    "only_explicit_row_fields_are_reconstructed": True,
    "visual_callouts_require_explicit_same_record_mapping": True,
    "guidance_is_not_promoted_to_proof": True,
    "previously_valid_answer_is_preserved_on_failure": True,
    "llm_call_added": False,
    "retrieval_changed": False,
    "ranking_changed": False,
    "route_changed": False,
    "answer_permission": False,
    "final_answer_allowed": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> List[Dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _compact(value: Any, limit: int = 4000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _bool_env(environ: Mapping[str, str], name: str, default: bool = True) -> bool:
    raw = str(environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def load_content_reconstruction_config(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    return {
        "enabled": _bool_env(
            env,
            "TRACE_NET_H30_CONTENT_RECONSTRUCTION_ENABLED",
            True,
        ),
    }


def _citation(entry: Mapping[str, Any]) -> str:
    try:
        number = int(entry.get("citation_id") or 0)
    except (TypeError, ValueError):
        return ""
    return f"[{number}]" if number > 0 else ""


def _query_identifier(query: str) -> str:
    match = PART_RE.search(str(query or ""))
    return match.group(0) if match else ""


def _query_page(query: str) -> str:
    match = PAGE_RE.search(str(query or ""))
    return match.group(0) if match else ""


def _query_ata(query: str) -> str:
    match = ATA_RE.search(str(query or ""))
    return match.group(0) if match else ""


def _entry_blob(entry: Mapping[str, Any]) -> str:
    pieces = [
        entry.get("identifier_blob"),
        entry.get("value"),
        entry.get("candidate_value"),
        entry.get("field_name"),
        " ".join(str(value) for value in entry.get("nomenclature") or []),
        " ".join(str(value) for value in entry.get("ata_codes") or []),
        entry.get("ata"),
        entry.get("class"),
    ]
    return _compact(" ".join(str(value or "") for value in pieces), 16000)


def _entry_page(entry: Mapping[str, Any]) -> str:
    page = str(entry.get("page_id") or "").strip()
    if page:
        return page
    for value in entry.get("page_ids") or []:
        if str(value).strip():
            return str(value).strip()
    match = PAGE_RE.search(_entry_blob(entry))
    return match.group(0) if match else ""


def _entry_identifier(entry: Mapping[str, Any]) -> str:
    value = str(entry.get("candidate_value") or "").strip()
    if value:
        return value
    match = PART_RE.search(_entry_blob(entry))
    return match.group(0) if match else ""


def _page_content(result: Mapping[str, Any]) -> Dict[str, Any]:
    envelope = _mapping(result.get("evidence_envelope"))
    coverage = _mapping(envelope.get("coverage"))
    return _mapping(coverage.get("page_content"))


def _page_packs(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    content = _page_content(result)
    pages = content.get("pages")
    if not content.get("available") or not isinstance(pages, list):
        return []
    return [
        dict(row)
        for row in pages
        if isinstance(row, Mapping) and row.get("found") is not False
    ]


def _first_record(pack: Mapping[str, Any], *sections: str) -> Dict[str, Any]:
    for section in sections:
        for row in pack.get(section) or []:
            if isinstance(row, Mapping):
                return dict(row)
    return {}


def _record_text(record: Mapping[str, Any]) -> str:
    return str(
        record.get("text")
        or record.get("value")
        or record.get("content")
        or record.get("summary")
        or ""
    )


def classify_page_role(entry: Mapping[str, Any]) -> str:
    blob = _entry_blob(entry).lower()
    cls = str(entry.get("class") or "").lower()
    if any(token in cls or token in blob for token in ("table", "ipl", "row", "cell")):
        return "IPL/table source"
    if any(token in cls or token in blob for token in ("visual", "figure", "diagram", "illustration")):
        return "figure/diagram source"
    if any(token in blob for token in ("list of effective pages", "25-lep", "revision", "effective page")):
        return "revision/effective-page source"
    if any(token in blob for token in ("procedure", "install ", "remove ", "adjust ", "repair ")):
        return "procedure source"
    if cls == "source_resolution":
        return "source-location lead"
    return "indexed source location"


def _dedupe_page_entries(
    registry: Sequence[Mapping[str, Any]],
    *,
    maximum: int = 10,
) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for raw in registry:
        entry = dict(raw)
        page = _entry_page(entry)
        citation = _citation(entry)
        if not page or not citation or page.casefold() in seen:
            continue
        seen.add(page.casefold())
        output.append(entry)
        if len(output) >= maximum:
            break
    return output


def render_ata_reconstruction(
    result: Mapping[str, Any],
    query: str,
    registry: Sequence[Mapping[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    ata = _query_ata(query)
    pages = _dedupe_page_entries(registry, maximum=8)
    if not pages:
        return "", {
            "ata_page_role_count": 0,
            "ata_direct_record_count": 0,
            "ata_navigation_only": True,
        }

    direct_count = sum(bool(entry.get("can_prove_claims")) for entry in pages)
    first_citation = _citation(pages[0])
    answer = (
        f"The search returned source-location leads for ATA `{ata}` {first_citation}."
        if ata
        else f"The search returned ATA source-location leads {first_citation}."
    )
    evidence: List[str] = []
    for entry in pages:
        page = _entry_page(entry)
        role = classify_page_role(entry)
        evidence.append(f"- Page `{page}` — {role} {_citation(entry)}")

    part_rows: List[str] = []
    seen_parts = set()
    for entry in registry:
        identifier = _entry_identifier(entry)
        citation = _citation(entry)
        if not identifier or not citation:
            continue
        key = _norm(identifier)
        if key in seen_parts:
            continue
        seen_parts.add(key)
        part_rows.append(f"- Part candidate `{identifier}` {citation}")
        if len(part_rows) >= 4:
            break
    evidence.extend(part_rows)

    text = "\n".join(
        [
            "## Answer",
            "",
            answer,
            "",
            "## Evidence",
            "",
            *evidence,
            "",
            "## Limits",
            "",
            "- These source-location leads do not by themselves establish the requested technical relationship.",
        ]
    ).strip()
    return text, {
        "ata_page_role_count": len(pages),
        "ata_direct_record_count": direct_count,
        "ata_navigation_only": direct_count == 0,
    }


def _same_row_segment(text: str, identifier: str, radius: int = 260) -> str:
    target = str(identifier or "").upper()
    if not target:
        return ""
    for line in str(text or "").splitlines():
        if target in line.upper():
            return _compact(line, 900)
    source = re.sub(r"[ \t]+", " ", str(text or ""))
    if source.upper().count(target) != 1:
        return ""
    index = source.upper().find(target)
    if index < 0:
        return ""
    start = max(0, index - radius)
    end = min(len(source), index + len(identifier) + radius)
    segment = _compact(source[start:end], 900)
    # The window fallback is accepted only when it contains an explicit table cue.
    if not re.search(r"\b(?:item|find\s*no|callout|qty|figure|fig\.|\d{2}-\d{2}-\d{2}-\d{1,3})\b", segment, re.I):
        return ""
    return segment


def extract_table_relationship(text: str, identifier: str) -> Dict[str, str]:
    segment = _same_row_segment(text, identifier)
    if not segment:
        return {}
    output: Dict[str, str] = {}

    table_ref = re.search(r"\b(\d{2}-\d{2}-\d{2}-\d{1,3})\b", segment)
    if table_ref:
        output["table_reference"] = table_ref.group(1)

    figure = FIGURE_RE.search(segment)
    if figure:
        output["figure"] = f"Figure {figure.group(1)}" + (
            f" Sheet {figure.group(2)}" if figure.group(2) else ""
        )

    item = re.search(
        r"\b(?:item|item\s*no\.?|find\s*no\.?|callout)\s*[:#.]?\s*(-?\d+[A-Z]?)\b",
        segment,
        re.I,
    )
    if not item:
        item = re.search(
            rf"\b\d{{2}}-\d{{2}}-\d{{2}}-\d{{1,3}}\s+(-?\d+[A-Z]?)\s+{re.escape(identifier)}\b",
            segment,
            re.I,
        )
    if item:
        output["item"] = item.group(1)

    parts = re.split(re.escape(str(identifier)), segment, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        tail = parts[1]
        quantity = re.search(r"\bQTY\b\s*[:#.-]?\s*(\d{1,3})\b", tail, re.I)
        if quantity:
            output["quantity"] = quantity.group(1)
        nomenclature = re.match(
            r"\s*[-:|,]*\s*([A-Z][A-Z /,-]{2,80}?)(?=\s+(?:QTY\b|\d{1,3}\b|$))",
            tail,
            re.I,
        )
        if nomenclature:
            value = _compact(nomenclature.group(1).strip(" -:|,"), 100)
            if value and not PART_RE.search(value):
                output["nomenclature"] = value.title().replace("Assy", "Assembly")

    return output


def _matching_registry_entry(
    registry: Sequence[Mapping[str, Any]],
    identifier: str,
) -> Dict[str, Any]:
    target = _norm(identifier)
    best: Optional[Dict[str, Any]] = None
    for raw in registry:
        entry = dict(raw)
        blob = _entry_blob(entry)
        if target and target not in _norm(blob):
            continue
        if best is None:
            best = entry
        if entry.get("can_prove_claims"):
            return entry
        if "table" in str(entry.get("class") or "").lower():
            best = entry
    return best or {}


def render_table_reconstruction(
    result: Mapping[str, Any],
    query: str,
    registry: Sequence[Mapping[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    identifier = _query_identifier(query)
    entry = _matching_registry_entry(registry, identifier)
    page = _entry_page(entry)
    citation = _citation(entry)

    packs = _page_packs(result)
    pack = next(
        (
            candidate
            for candidate in packs
            if not page or str(candidate.get("page_id") or "").casefold() == page.casefold()
        ),
        packs[0] if packs else {},
    )
    table_record = _first_record(pack, "tables") or entry
    table_text = _record_text(table_record) or _entry_blob(entry)
    relation = extract_table_relationship(table_text, identifier)
    relation_citation = _citation(table_record) or citation

    if not identifier or not page or not citation:
        return "", {
            "table_part_page_match": False,
            "table_relationship_field_count": len(relation),
            "table_relationship_fields": sorted(relation),
        }

    lines = [
        "## Answer",
        "",
        f"`{identifier}` appears in the available IPL/table evidence on page `{page}` {citation}.",
        "",
        "## Evidence",
        "",
        f"- Source-backed record: `{identifier}` — page `{page}` {citation}",
    ]
    details: List[str] = []
    labels = {
        "table_reference": "table/figure reference",
        "figure": "figure",
        "item": "item",
        "nomenclature": "nomenclature",
        "quantity": "quantity",
    }
    for key in ("table_reference", "figure", "item", "nomenclature", "quantity"):
        value = relation.get(key)
        if value:
            details.append(
                f"{labels[key]} `{value}`"
                if key != "nomenclature"
                else f"{labels[key]} {value}"
            )
    if details and relation_citation:
        lines.append(
            "- Reconstructed same-row relationship: "
            + "; ".join(details)
            + f" {relation_citation}"
        )
    return "\n".join(lines).strip(), {
        "table_part_page_match": True,
        "table_relationship_field_count": len(relation),
        "table_relationship_fields": sorted(relation),
    }


def extract_procedure_steps(text: str, maximum: int = 14) -> List[Tuple[str, str]]:
    output: List[Tuple[str, str]] = []
    for match in STEP_RE.finditer(str(text or "")):
        label = (match.group(1) or match.group(2) or "").lower()
        body = _compact(match.group(3), 900)
        body = re.split(
            r"\b(?:PART QTY MATERIAL|Repair Materials|Repair Procedure|Illustrated Parts List)\b",
            body,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" .;:-")
        if len(body) < 8:
            continue
        body = body[0].upper() + body[1:]
        output.append((label, body))
        if len(output) >= maximum:
            break
    return output


def reconstruct_procedure_sequences(
    steps: Sequence[Tuple[str, str]],
) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    current: List[Tuple[str, str]] = []
    previous = -1
    for label, body in steps:
        ordinal = ord(label.lower()) - ord("a")
        if current and ordinal <= previous:
            groups.append({"steps": current})
            current = []
        current.append((label.lower(), body))
        previous = ordinal
    if current:
        groups.append({"steps": current})

    for index, group in enumerate(groups, 1):
        first_label = group["steps"][0][0] if group.get("steps") else "a"
        if index == 1 and first_label != "a":
            title = "Continuation"
        else:
            title = f"Sequence {index}" if len(groups) > 1 else "Sequence 1"
        group["title"] = title
    return groups


def render_procedure_reconstruction(
    result: Mapping[str, Any],
    query: str,
) -> Tuple[str, Dict[str, Any]]:
    page = _query_page(query)
    packs = _page_packs(result)
    pack = next(
        (
            row
            for row in packs
            if not page or str(row.get("page_id") or "").casefold() == page.casefold()
        ),
        packs[0] if packs else {},
    )
    page = str(pack.get("page_id") or page or "the requested page")
    record = _first_record(pack, "ocr")
    text = _record_text(record)
    citation = _citation(record)
    steps = extract_procedure_steps(text)
    groups = reconstruct_procedure_sequences(steps)
    if not steps or not citation:
        return "", {
            "procedure_step_count": len(steps),
            "procedure_sequence_count": len(groups),
            "procedure_reference_limit_added": False,
        }

    if len(groups) >= 2 and groups[0].get("title") == "Continuation":
        answer = (
            f"Page `{page}` contains a continued procedure and a second readable "
            f"procedure sequence {citation}."
        )
    elif len(groups) >= 2:
        answer = f"Page `{page}` contains {len(groups)} readable procedure sequences {citation}."
    else:
        answer = f"Page `{page}` contains a readable procedure sequence {citation}."

    evidence: List[str] = []
    for group in groups:
        title = str(group.get("title") or "Sequence")
        for label, body in group.get("steps") or []:
            evidence.append(f"- {title} — {label}. {body} {citation}")

    limits: List[str] = []
    reference_limit = bool(re.search(r"\bas described in item\s+\w+", text, re.I))
    if reference_limit:
        limits.append(
            f"Some steps refer to other numbered items that are not reproduced on this page {citation}."
        )
    if re.search(r"\bNOTE\s*:", text, re.I):
        limits.append(
            f"The page contains one or more notes; use the cited page for their exact wording {citation}."
        )
    limits.append(
        f"Lettered sequence boundaries were reconstructed from OCR layout; punctuation and line breaks should be checked against the cited page image {citation}."
    )
    lines = ["## Answer", "", answer, "", "## Evidence", "", *evidence]
    if limits:
        lines.extend(["", "## Limits", "", *[f"- {value}" for value in limits]])
    return "\n".join(lines).strip(), {
        "procedure_step_count": len(steps),
        "procedure_sequence_count": len(groups),
        "procedure_reference_limit_added": reference_limit,
    }


def extract_explicit_callout_mappings(
    text: str,
    citation: str,
    maximum: int = 8,
) -> List[Dict[str, str]]:
    if not citation:
        return []
    part_pattern = PART_RE.pattern
    patterns = (
        re.compile(
            rf"\b(?:item|callout)\s*([0-9]{{1,3}}[A-Z]?)\s*[:#.-]?\s*"
            rf"(?:P/?N\s*)?({part_pattern})(?:\s*[-,:]\s*([A-Za-z][^;\n|]{{2,80}}))?",
            re.I,
        ),
        re.compile(
            rf"(?m)^\s*([0-9]{{1,3}}[A-Z]?)\s+({part_pattern})\s+"
            r"([A-Za-z][^\n|]{2,80})$",
            re.I,
        ),
    )
    output: List[Dict[str, str]] = []
    seen = set()
    for pattern in patterns:
        for match in pattern.finditer(str(text or "")):
            callout = str(match.group(1) or "").strip()
            part = str(match.group(2) or "").strip()
            name = str(match.group(3) or "").strip(" -,:")
            key = (callout.casefold(), _norm(part))
            if not callout or not part or key in seen:
                continue
            seen.add(key)
            output.append(
                {
                    "callout": callout,
                    "part_number": part,
                    "nomenclature": _compact(name, 100),
                    "citation": citation,
                }
            )
            if len(output) >= maximum:
                return output
    return output


def _insert_evidence_lines(content: str, lines: Sequence[str]) -> str:
    if not lines:
        return str(content or "")
    text = str(content or "").strip()
    insertion = "\n".join(lines)
    marker = "\n## Limits"
    if marker in text:
        head, tail = text.split(marker, 1)
        return head.rstrip() + "\n" + insertion + marker + tail
    if "## Evidence" in text:
        return text.rstrip() + "\n" + insertion
    return text


def render_visual_reconstruction(
    result: Mapping[str, Any],
    query: str,
    old_content: str,
) -> Tuple[str, Dict[str, Any]]:
    page = _query_page(query)
    packs = _page_packs(result)
    pack = next(
        (
            row
            for row in packs
            if not page or str(row.get("page_id") or "").casefold() == page.casefold()
        ),
        packs[0] if packs else {},
    )
    records: List[Dict[str, Any]] = []
    for section in ("tables", "ocr"):
        records.extend(_rows(pack.get(section)))
    mappings: List[Dict[str, str]] = []
    for record in records:
        mappings.extend(
            extract_explicit_callout_mappings(
                _record_text(record),
                _citation(record),
            )
        )
    deduped: List[Dict[str, str]] = []
    seen = set()
    for row in mappings:
        key = (row["callout"].casefold(), _norm(row["part_number"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    if not deduped:
        return str(old_content or ""), {
            "visual_resolved_callout_count": 0,
            "visual_callout_claim_added": False,
        }

    bullets: List[str] = []
    for row in deduped[:8]:
        detail = f" — {row['nomenclature']}" if row.get("nomenclature") else ""
        bullets.append(
            f"- Resolved callout `{row['callout']}` → part `{row['part_number']}`"
            f"{detail} {row['citation']}"
        )
    return _insert_evidence_lines(old_content, bullets), {
        "visual_resolved_callout_count": len(bullets),
        "visual_callout_claim_added": True,
    }


def render_content_specific_answer(
    result: Mapping[str, Any],
    query: str,
    registry: Sequence[Mapping[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    route = str(result.get("route") or "")
    old_content = str(result.get("content") or "")
    metrics: Dict[str, Any] = {
        "route": route,
        "ata_page_role_count": 0,
        "ata_direct_record_count": 0,
        "ata_navigation_only": False,
        "table_part_page_match": False,
        "table_relationship_field_count": 0,
        "table_relationship_fields": [],
        "procedure_step_count": 0,
        "procedure_sequence_count": 0,
        "procedure_reference_limit_added": False,
        "visual_resolved_callout_count": 0,
        "visual_callout_claim_added": False,
    }
    if route == "ata_system_discovery":
        rendered, extra = render_ata_reconstruction(result, query, registry)
    elif route == "exact_table_ipl_lookup":
        rendered, extra = render_table_reconstruction(result, query, registry)
    elif route == "procedure_task_lookup":
        rendered, extra = render_procedure_reconstruction(result, query)
    elif route == "visual_figure_callout_lookup":
        rendered, extra = render_visual_reconstruction(result, query, old_content)
    else:
        return old_content, metrics
    metrics.update(extra)
    return rendered or old_content, metrics


def content_reconstruction_health(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    config = load_content_reconstruction_config(environ)
    return {
        "status": STATUS,
        "quality_status": "PASS",
        "enabled": bool(config.get("enabled")),
        "target_routes": sorted(TARGET_ROUTES),
        "phase2_stabilization_included": True,
        "only_explicit_row_fields_are_reconstructed": True,
        "visual_callouts_require_explicit_same_record_mapping": True,
        "llm_call_added": False,
        "retrieval_changed": False,
        "ranking_changed": False,
        "route_changed": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def install_content_reconstruction(module: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_CONTENT_RECONSTRUCTION_V1_INSTALLED"
    if module.get(marker):
        return

    runtime_cls = module["Runtime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health
    citation_registry = module["citation_registry"]
    citation_registry_digest = module["citation_registry_digest"]
    validate_answer = module["validate_answer"]
    extract_latest_user = module["extract_latest_user"]
    synthesis_allowed_identifiers = module.get("synthesis_allowed_identifiers")

    def process_content_reconstruction(
        self: Any,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        result = dict(current_process(self, payload))
        config = load_content_reconstruction_config()
        route = str(result.get("route") or "")
        old_content = str(result.get("content") or "")
        old_validation = _mapping(result.get("post_answer_validation"))

        if not config.get("enabled") or route not in TARGET_ROUTES:
            result["content_reconstruction"] = {
                "status": STATUS,
                "quality_status": "SKIPPED",
                "enabled": bool(config.get("enabled")),
                "applied": False,
                "reason": "disabled" if not config.get("enabled") else "route_not_targeted",
                "route": route,
                "gemma_call_count_added": 0,
                "retrieval_changed": False,
                "route_changed": False,
                "source_truth_mutation_allowed": False,
                "write_attempt_count": 0,
            }
            return result

        query = extract_latest_user(payload)
        registry = citation_registry(result)
        rendered, metrics = render_content_specific_answer(result, query, registry)
        extra_allowed = (
            synthesis_allowed_identifiers(query, result)
            if callable(synthesis_allowed_identifiers)
            else None
        )
        validation = validate_answer(
            rendered,
            query,
            result,
            extra_allowed=extra_allowed,
            registry=registry,
        )

        fallback_used = False
        if not validation.get("accepted") and old_validation.get("accepted"):
            rendered = old_content
            validation = old_validation
            fallback_used = True

        result["content"] = rendered
        result["post_answer_validation"] = validation
        result["citation_registry"] = registry
        result["citation_registry_size"] = len(registry)
        result["citation_registry_digest"] = citation_registry_digest(registry)
        result["writer_mode_before_content_reconstruction"] = result.get("writer_mode")
        result["writer_mode"] = (
            "content_reconstruction_fallback_to_prior_valid_answer"
            if fallback_used
            else "content_specific_evidence_reconstruction_v1"
        )
        result["content_reconstruction"] = {
            "status": STATUS,
            "patch_id": PATCH_ID,
            "quality_status": "PASS" if validation.get("accepted") else "FAIL",
            "enabled": True,
            "applied": rendered.strip() != old_content.strip(),
            "route": route,
            "fallback_used": fallback_used,
            "final_validation_accepted": bool(validation.get("accepted")),
            "final_validation_failures": list(validation.get("failures") or []),
            "phase2_ata_page_allowlist_stabilized": True,
            "phase2_exact_page_typed_record_source_stabilized": True,
            **metrics,
            "gemma_call_count_added": 0,
            "retrieval_changed": False,
            "ranking_changed": False,
            "route_changed": False,
            "source_truth_mutation_allowed": False,
            "write_attempt_count": 0,
        }
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["can_answer_directly"] = False
        result["can_prove_claims"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    def health_content_reconstruction(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        health = content_reconstruction_health()
        result["content_reconstruction"] = health
        result["content_reconstruction_enabled"] = bool(health.get("enabled"))
        result["phase3_table_same_row_only"] = True
        result["phase3_visual_explicit_callout_only"] = True
        result["phase3_procedure_sequence_reconstruction"] = True
        result["phase3_ata_page_role_classification"] = True
        result["answer_permission"] = False
        result["final_answer_allowed"] = False
        result["source_truth_mutation_allowed"] = False
        return result

    runtime_cls.process = process_content_reconstruction
    runtime_cls.health = health_content_reconstruction
    module[marker] = True


__all__ = [
    "MODULE",
    "VERSION",
    "STATUS",
    "PATCH_ID",
    "TARGET_ROUTES",
    "classify_page_role",
    "extract_table_relationship",
    "extract_procedure_steps",
    "reconstruct_procedure_sequences",
    "extract_explicit_callout_mappings",
    "render_content_specific_answer",
    "content_reconstruction_health",
    "install_content_reconstruction",
]
