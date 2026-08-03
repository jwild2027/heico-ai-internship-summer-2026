from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


MODULE = "trace_net_h37_diversity_evidence_planner_v1"
VERSION = "v1"

ROUTE_PREFIX = {
    "visual": "V",
    "ocr": "O",
    "table": "T",
    "exact": "E",
    "unknown": "X",
}

SYNTHESIS_TASK_TYPES = {
    "multi_page_summary",
    "quiz_generation",
    "representative_page_explanation",
    "part_comparison_without_overclaiming",
    "route_audit",
    "evidence_strength_ranking",
    "followup_query_generation",
}


DEFAULT_QUERY_TASKS = [
    {
        "question_id": "h37_q01_part_lookup",
        "task_type": "part_lookup",
        "query_text": "Find part number 120-50645-005. Give nomenclature if available and cite source-trace-ready evidence.",
        "min_unique_routes": 2,
        "min_unique_pages": 1,
        "min_unique_part_numbers": 1,
        "min_unique_figures": 1,
        "max_same_nomenclature": 6,
    },
    {
        "question_id": "h37_q02_representative_page",
        "task_type": "representative_page_explanation",
        "query_text": "Pick one representative source-trace-ready page, figure, or record and explain what TRACE-Net can safely say.",
        "min_unique_routes": 1,
        "min_unique_pages": 1,
        "min_unique_part_numbers": 1,
        "min_unique_figures": 1,
        "max_same_nomenclature": 3,
    },
    {
        "question_id": "h37_q03_multi_page_summary",
        "task_type": "multi_page_summary",
        "query_text": "Summarize evidence across multiple pages, figures, or records with source-trace-ready citations.",
        "min_unique_routes": 2,
        "min_unique_pages": 3,
        "min_unique_part_numbers": 3,
        "min_unique_figures": 3,
        "max_same_nomenclature": 2,
    },
    {
        "question_id": "h37_q04_nomenclature_lookup",
        "task_type": "nomenclature_lookup",
        "query_text": "Look up nomenclature for part number 120-50645-005 and separate OCR route from visual route.",
        "min_unique_routes": 2,
        "min_unique_pages": 1,
        "min_unique_part_numbers": 1,
        "min_unique_figures": 1,
        "max_same_nomenclature": 6,
    },
    {
        "question_id": "h37_q05_quiz_generation",
        "task_type": "quiz_generation",
        "query_text": "Create a technician quiz using diverse source-trace-ready evidence, answer key, citations, and one limits question.",
        "min_unique_routes": 2,
        "min_unique_pages": 3,
        "min_unique_part_numbers": 3,
        "min_unique_figures": 3,
        "max_same_nomenclature": 2,
    },
]


def _read_json(path: str | Path | None) -> Any:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(dict(r), ensure_ascii=False, sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
    )


def _iter_dicts(obj: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(obj, Mapping):
        yield obj
        for v in obj.values():
            yield from _iter_dicts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dicts(item)


def _norm_text(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _first(d: Mapping[str, Any], keys: Iterable[str]) -> str:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return _norm_text(v)
    return ""


def _infer_route(record: Mapping[str, Any], explicit_route: str = "") -> str:
    blob = json.dumps(record, ensure_ascii=False).lower()
    if explicit_route:
        return explicit_route
    if "ocr" in blob or "nomenclature_window" in blob or "line_text" in blob:
        return "ocr"
    if "visual" in blob or "figure" in blob or "callout" in blob or "llava" in blob:
        return "visual"
    if "table" in blob or "row" in blob or "cell" in blob:
        return "table"
    if "exact" in blob or "covered_part_number" in blob:
        return "exact"
    return "unknown"


def _extract_page(record: Mapping[str, Any]) -> str:
    page = _first(record, ["page", "page_number", "manual_page", "source_page", "page_index"])
    if page:
        return page
    page_id = _first(record, ["page_id", "source_page_id", "ocr_page_id"])
    m = re.search(r"p0*([0-9]{1,5})", page_id)
    if m:
        return m.group(1)
    return ""


def _extract_part(record: Mapping[str, Any]) -> str:
    part = _first(record, [
        "part_number",
        "linked_part_number",
        "covered_part_number",
        "part",
        "item_part_number",
        "pn",
    ])
    if part:
        return part
    blob = json.dumps(record, ensure_ascii=False)
    m = re.search(r"\b\d{3}-\d{5}-\d{3}\b", blob)
    return m.group(0) if m else ""


def _extract_figure(record: Mapping[str, Any]) -> str:
    fig = _first(record, ["figure", "figure_number", "linked_figure", "source_figure"])
    if not fig:
        blob = json.dumps(record, ensure_ascii=False)
        m = re.search(r"\bfigure\s+([0-9A-Za-z.-]+)\b", blob, re.I)
        fig = m.group(1) if m else ""
    fig = _norm_text(fig)
    if fig.lower() in {"anchor", "none", "null", "n/a", "na", "unknown"}:
        return ""
    if "_" in fig or fig.lower().endswith("_count"):
        return ""
    return fig

def _looks_like_metadata_value(value: str) -> bool:
    raw = _norm_text(value)
    low = raw.lower()
    if not low:
        return False
    metadata_markers = (
        "source_",
        "record_count",
        "_count",
        "quality_status",
        "schema_version",
        "trace_net_",
        "artifact",
        "manifest",
        "module",
        "version",
    )
    if any(m in low for m in metadata_markers):
        return True
    if "_" in raw and " " not in raw:
        return True
    return False


def _extract_nomenclature(record: Mapping[str, Any]) -> str:
    nom = _first(record, ["nomenclature", "part_name", "description", "name", "part_description"])
    if nom and not _looks_like_metadata_value(nom):
        return nom
    line = _first(record, ["line_text", "text", "ocr_text"])
    m = re.search(r"\b\d{3}-\d{5}-\d{3}\s+([A-Z0-9][A-Z0-9 /.-]{4,80}?)(?:\.{2,}|VS|REF|$)", line)
    if m:
        candidate = _norm_text(m.group(1))
        if not _looks_like_metadata_value(candidate):
            return candidate
    return ""

def _source_id(record: Mapping[str, Any]) -> str:
    return _first(record, [
        "record_id", "evidence_id", "source_record_id", "id", "point_id",
        "source_trace_id", "card_id",
    ])


def _label_for(record: Mapping[str, Any], route: str, idx: int) -> str:
    label = _first(record, ["citation_label", "label", "source_visual_citation_label"])
    if label and re.match(r"^[A-Z][0-9]+$", label):
        return label
    prefix = ROUTE_PREFIX.get(route, "X")
    return f"{prefix}{idx}"


def _quality_score(record: Mapping[str, Any], route: str) -> float:
    score = 0.0
    blob = json.dumps(record, ensure_ascii=False).lower()
    for k in ("citation_ready", "source_trace_ready", "source_traceable", "quality_status"):
        v = record.get(k)
        if v is True or str(v).upper() == "PASS":
            score += 3.0
    if _extract_part(record):
        score += 2.0
    if _extract_nomenclature(record):
        score += 2.0
    if _extract_figure(record):
        score += 1.25
    if _extract_page(record):
        score += 1.0
    if route in {"ocr", "visual", "table", "exact"}:
        score += 0.5
    if "answer_permission" in blob:
        score += 0.1
    return score


def _make_preview(record: Mapping[str, Any], max_chars: int = 420) -> str:
    fields = []
    for key in ("page_id", "page", "figure", "linked_part_number", "part_number", "covered_part_number", "nomenclature", "line_text", "field", "value"):
        if key in record and record.get(key) not in (None, "", [], {}):
            fields.append(f"{key}={_norm_text(record.get(key))}")
    if not fields:
        fields.append(json.dumps(record, ensure_ascii=False)[:max_chars])
    return _norm_text(" | ".join(fields))[:max_chars]


def collect_evidence_cards(
    image_visual_evidence_pack: str | Path | None = None,
    raw_ocr_nomenclature_extractor: str | Path | None = None,
    table_route_evidence_packager: str | Path | None = None,
    table_exact_search_adapter: str | Path | None = None,
    max_cards_per_source: int = 400,
) -> List[Dict[str, Any]]:
    sources = [
        ("visual", image_visual_evidence_pack),
        ("ocr", raw_ocr_nomenclature_extractor),
        ("table", table_route_evidence_packager),
        ("exact", table_exact_search_adapter),
    ]
    cards: List[Dict[str, Any]] = []
    per_route_idx: Counter[str] = Counter()
    used_labels: set[str] = set()
    seen: set[Tuple[str, str, str, str, str]] = set()

    for explicit_route, path in sources:
        data = _read_json(path)
        if data is None:
            continue
        count = 0
        for rec in _iter_dicts(data):
            route = _infer_route(rec, explicit_route)
            part = _extract_part(rec)
            fig = _extract_figure(rec)
            page = _extract_page(rec)
            nom = _extract_nomenclature(rec)
            sid = _source_id(rec)
            if nom and _looks_like_metadata_value(nom):
                nom = ""
            if not (part or fig or page or nom or sid):
                continue
            if not (part or fig or page or nom) and sid:
                # Do not let manifest-only records become diversity evidence.
                continue
            key = (route, part, fig, page, nom)
            if key in seen:
                continue
            seen.add(key)
            per_route_idx[route] += 1
            label = _label_for(rec, route, per_route_idx[route])
            if label in used_labels:
                label = f"{ROUTE_PREFIX.get(route, 'X')}{per_route_idx[route]}"
            while label in used_labels:
                per_route_idx[route] += 1
                label = f"{ROUTE_PREFIX.get(route, 'X')}{per_route_idx[route]}"
            used_labels.add(label)
            card = {
                "evidence_label": label,
                "route": route,
                "page": page,
                "figure": fig,
                "part_number": part,
                "nomenclature": nom,
                "source_id": sid,
                "quality_score": round(_quality_score(rec, route), 4),
                "preview": _make_preview(rec),
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "can_be_used_as_proof": True,
            }
            cards.append(card)
            count += 1
            if count >= max_cards_per_source:
                break
    cards.sort(key=lambda c: (c["quality_score"], c["route"], c["evidence_label"]), reverse=True)
    return cards


def _task_records_from_contract_run(contract_run: Mapping[str, Any] | None) -> List[Dict[str, Any]]:
    if not contract_run:
        return [dict(r) for r in DEFAULT_QUERY_TASKS]
    records = []
    for rec in contract_run.get("records", []) or []:
        qid = _norm_text(rec.get("question_id"))
        task = _norm_text(rec.get("task_type"))
        question = _norm_text(rec.get("question") or rec.get("query_text") or qid)
        if not qid or not task:
            continue
        base = {
            "question_id": qid,
            "task_type": task,
            "query_text": question,
            "min_unique_routes": 2 if task in SYNTHESIS_TASK_TYPES else 1,
            "min_unique_pages": 3 if task in {"multi_page_summary", "quiz_generation"} else 1,
            "min_unique_part_numbers": 3 if task in {"multi_page_summary", "quiz_generation"} else 1,
            "min_unique_figures": 3 if task in {"multi_page_summary", "quiz_generation"} else 1,
            "max_same_nomenclature": 2 if task in SYNTHESIS_TASK_TYPES else 6,
        }
        records.append(base)
    return records or [dict(r) for r in DEFAULT_QUERY_TASKS]


def _tokenize_query(text: str) -> List[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9-]{3,}", text) if t.lower() not in {"the", "and", "with", "from", "that", "this", "what", "trace", "net"}]


def _relevance(card: Mapping[str, Any], query_text: str, task_type: str) -> float:
    text = " ".join(str(card.get(k, "")) for k in ("part_number", "nomenclature", "figure", "page", "route", "preview")).lower()
    score = float(card.get("quality_score") or 0)
    for tok in _tokenize_query(query_text):
        if tok.lower() in text:
            score += 3.0
    if task_type == "nomenclature_lookup" and card.get("route") == "ocr":
        score += 4.0
    if task_type == "part_lookup" and card.get("part_number"):
        score += 3.0
    if task_type in {"multi_page_summary", "quiz_generation"}:
        if card.get("part_number"):
            score += 1.0
        if card.get("page"):
            score += 1.0
        if card.get("figure"):
            score += 1.0
    return score


def _diversity_tuple(card: Mapping[str, Any]) -> Tuple[str, str, str, str, str]:
    return (
        _norm_text(card.get("route")),
        _norm_text(card.get("page")),
        _norm_text(card.get("figure")),
        _norm_text(card.get("part_number")),
        _norm_text(card.get("nomenclature")).lower(),
    )


def select_diverse_cards(
    cards: List[Mapping[str, Any]],
    task: Mapping[str, Any],
    max_cards: int = 8,
) -> List[Dict[str, Any]]:
    task_type = _norm_text(task.get("task_type"))
    query_text = _norm_text(task.get("query_text"))
    min_routes = int(task.get("min_unique_routes") or 1)
    min_pages = int(task.get("min_unique_pages") or 1)
    min_parts = int(task.get("min_unique_part_numbers") or 1)
    min_figures = int(task.get("min_unique_figures") or 1)
    max_same_nom = int(task.get("max_same_nomenclature") or 999)

    candidates = [dict(c) for c in cards]
    for c in candidates:
        c["_relevance"] = round(_relevance(c, query_text, task_type), 4)

    # Pre-sort by relevance, but greedy selection penalizes already-covered dimensions.
    candidates.sort(key=lambda c: (c["_relevance"], c.get("quality_score", 0)), reverse=True)

    selected: List[Dict[str, Any]] = []
    used_keys: set[Tuple[str, str, str, str, str]] = set()
    counts = {
        "route": Counter(),
        "page": Counter(),
        "figure": Counter(),
        "part": Counter(),
        "nomenclature": Counter(),
    }

    def add(card: Dict[str, Any]) -> bool:
        key = _diversity_tuple(card)
        if key in used_keys:
            return False
        nom_key = _norm_text(card.get("nomenclature")).lower()
        if nom_key and counts["nomenclature"][nom_key] >= max_same_nom:
            return False
        selected.append(card)
        used_keys.add(key)
        for name, value in [
            ("route", card.get("route")),
            ("page", card.get("page")),
            ("figure", card.get("figure")),
            ("part", card.get("part_number")),
            ("nomenclature", nom_key),
        ]:
            if value:
                counts[name][_norm_text(value).lower()] += 1
        return True

    # Seed required route diversity first.
    for route in ("ocr", "visual", "table", "exact"):
        if len(set(c.get("route") for c in selected if c.get("route"))) >= min_routes:
            break
        for c in candidates:
            if c.get("route") == route and c not in selected:
                if add(c):
                    break

    # Then greedily add items that maximize new pages/figures/parts/nomenclature.
    while len(selected) < max_cards:
        best = None
        best_score = -999999.0
        current_pages = {c.get("page") for c in selected if c.get("page")}
        current_figures = {c.get("figure") for c in selected if c.get("figure")}
        current_parts = {c.get("part_number") for c in selected if c.get("part_number")}
        current_routes = {c.get("route") for c in selected if c.get("route")}
        current_noms = {_norm_text(c.get("nomenclature")).lower() for c in selected if c.get("nomenclature")}
        for c in candidates:
            if c in selected or _diversity_tuple(c) in used_keys:
                continue
            score = c["_relevance"]
            if c.get("page") and c.get("page") not in current_pages:
                score += 8.0 if len(current_pages) < min_pages else 2.0
            if c.get("figure") and c.get("figure") not in current_figures:
                score += 7.0 if len(current_figures) < min_figures else 1.5
            if c.get("part_number") and c.get("part_number") not in current_parts:
                score += 7.0 if len(current_parts) < min_parts else 1.5
            if c.get("route") and c.get("route") not in current_routes:
                score += 9.0 if len(current_routes) < min_routes else 1.0
            nom_key = _norm_text(c.get("nomenclature")).lower()
            if nom_key and nom_key not in current_noms:
                score += 3.0
            if nom_key and counts["nomenclature"][nom_key] >= max_same_nom:
                score -= 100.0
            if score > best_score:
                best = c
                best_score = score
        if not best or best_score < -100:
            break
        if not add(best):
            break

    for c in selected:
        c.pop("_relevance", None)
    return selected


def _unique_count(cards: List[Mapping[str, Any]], key: str) -> int:
    vals = {_norm_text(c.get(key)).lower() for c in cards if _norm_text(c.get(key))}
    return len(vals)


def _diversity_findings(cards: List[Mapping[str, Any]], task: Mapping[str, Any]) -> List[str]:
    findings = []
    checks = [
        ("route", "min_unique_routes", "route"),
        ("page", "min_unique_pages", "page"),
        ("part_number", "min_unique_part_numbers", "part_number"),
        ("figure", "min_unique_figures", "figure"),
    ]
    for card_key, task_key, label in checks:
        need = int(task.get(task_key) or 0)
        have = _unique_count(cards, card_key)
        if have < need:
            findings.append(f"too_few_unique_{label}s:{have}<{need}")
    max_nom = int(task.get("max_same_nomenclature") or 999)
    nom_counts = Counter(_norm_text(c.get("nomenclature")).lower() for c in cards if _norm_text(c.get("nomenclature")))
    over = [f"{nom}:{count}>{max_nom}" for nom, count in nom_counts.items() if count > max_nom]
    if over:
        findings.append("same_nomenclature_over_limit:" + ",".join(over[:3]))
    return findings


def build_diversity_evidence_planner(
    output_dir: str | Path,
    contract_run: str | Path | None = None,
    image_visual_evidence_pack: str | Path | None = None,
    raw_ocr_nomenclature_extractor: str | Path | None = None,
    table_route_evidence_packager: str | Path | None = None,
    table_exact_search_adapter: str | Path | None = None,
    max_cards_per_task: int = 8,
    min_plan_records: int = 5,
    min_diversity_pass: int = 4,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    contract_data = _read_json(contract_run)
    task_records = _task_records_from_contract_run(contract_data)
    cards = collect_evidence_cards(
        image_visual_evidence_pack=image_visual_evidence_pack,
        raw_ocr_nomenclature_extractor=raw_ocr_nomenclature_extractor,
        table_route_evidence_packager=table_route_evidence_packager,
        table_exact_search_adapter=table_exact_search_adapter,
    )

    plan_records: List[Dict[str, Any]] = []
    overlay_map: Dict[str, Any] = {}

    for task in task_records[:min(len(task_records), max(min_plan_records, len(task_records)))]:
        selected = select_diverse_cards(cards, task, max_cards=max_cards_per_task)
        findings = _diversity_findings(selected, task)
        diversity_pass = not findings
        labels = [c["evidence_label"] for c in selected]
        routes = sorted({_norm_text(c.get("route")) for c in selected if _norm_text(c.get("route"))})
        pages = sorted({_norm_text(c.get("page")) for c in selected if _norm_text(c.get("page"))})
        parts = sorted({_norm_text(c.get("part_number")) for c in selected if _norm_text(c.get("part_number"))})
        figures = sorted({_norm_text(c.get("figure")) for c in selected if _norm_text(c.get("figure"))})
        nomenclatures = sorted({_norm_text(c.get("nomenclature")) for c in selected if _norm_text(c.get("nomenclature"))})
        qid = _norm_text(task.get("question_id"))
        rec = {
            "question_id": qid,
            "task_type": task.get("task_type"),
            "query_text": task.get("query_text"),
            "diversity_status": "PASS" if diversity_pass else "REVIEW",
            "diversity_pass": diversity_pass,
            "findings": findings,
            "selected_evidence_labels": labels,
            "selected_routes": routes,
            "selected_pages": pages,
            "selected_part_numbers": parts,
            "selected_figures": figures,
            "selected_nomenclatures": nomenclatures,
            "unique_evidence_label_count": len(set(labels)),
            "unique_route_count": len(routes),
            "unique_page_count": len(pages),
            "unique_part_number_count": len(parts),
            "unique_figure_count": len(figures),
            "unique_nomenclature_count": len(nomenclatures),
            "selected_cards": selected,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "unsafe": False,
            "write_attempt_count": 0,
        }
        plan_records.append(rec)
        overlay_map[qid] = {
            "question_id": qid,
            "task_type": task.get("task_type"),
            "diversity_guidance_text": build_diversity_prompt_overlay(rec),
            "selected_evidence_labels": labels,
            "selected_cards": selected,
            "proof_boundary": "Diversity planner selects source-trace candidate cards; manual claims still require proof_context citations.",
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }

    summary = {
        "module": MODULE,
        "version": VERSION,
        "plan_record_count": len(plan_records),
        "evidence_card_count": len(cards),
        "diversity_pass_count": sum(1 for r in plan_records if r["diversity_pass"]),
        "review_count": sum(1 for r in plan_records if not r["diversity_pass"]),
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "qdrant_read_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_finding_count": 0,
        "ready_for_h38_quiz_contract_runner": True,
    }

    failures: List[str] = []
    if summary["plan_record_count"] < min_plan_records:
        failures.append("plan_record_count_below_min")
    if summary["diversity_pass_count"] < min_diversity_pass:
        failures.append("diversity_pass_count_below_min")
    if require_no_answer_permission and summary["answer_permission_count"]:
        failures.append("answer_permission_nonzero")
    if summary["unsafe_finding_count"] > max_unsafe:
        failures.append("unsafe_finding_count_above_max")
    if summary["write_attempt_count"] > max_write_attempts:
        failures.append("write_attempt_count_above_max")

    quality_status = "PASS" if not failures else "FAIL"
    summary["quality_failures"] = failures

    manifest = {
        "status": "TRACE_NET_H37_DIVERSITY_EVIDENCE_PLANNER_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "planner_policy": {
            "mode": "artifact_first_diversity_evidence_planner",
            "purpose": "Prevent synthesis tasks from collapsing into a single strong evidence cluster.",
            "proof_boundary": "Planner selects diverse source-trace candidate cards only; factual manual claims still require proof_context citations.",
            "forbidden": [
                "answer_permission_from_planner",
                "source_truth_mutation_from_planner",
                "engram_or_summary_or_planner_used_as_proof",
                "live_io_from_planner",
            ],
            "diversity_dimensions": [
                "route",
                "page",
                "figure",
                "part_number",
                "nomenclature",
            ],
        },
        "source_paths": {
            "contract_run": str(contract_run) if contract_run else "",
            "image_visual_evidence_pack": str(image_visual_evidence_pack) if image_visual_evidence_pack else "",
            "raw_ocr_nomenclature_extractor": str(raw_ocr_nomenclature_extractor) if raw_ocr_nomenclature_extractor else "",
            "table_route_evidence_packager": str(table_route_evidence_packager) if table_route_evidence_packager else "",
            "table_exact_search_adapter": str(table_exact_search_adapter) if table_exact_search_adapter else "",
        },
        "plan_records": plan_records,
        "diversity_overlay_map": overlay_map,
    }

    _write_json(out / f"{MODULE}.json", manifest)
    _write_jsonl(out / f"{MODULE}_plan_records.jsonl", plan_records)
    _write_json(out / "trace_net_h37_diversity_overlay_map_v1.json", overlay_map)
    _write_json(out / f"{MODULE}_quality_check.json", {
        "status": "TRACE_NET_H37_DIVERSITY_EVIDENCE_PLANNER_CHECKED",
        "quality_status": quality_status,
        "summary": summary,
    })
    return manifest


def build_diversity_prompt_overlay(plan_record: Mapping[str, Any]) -> str:
    lines = [
        "TRACE-NET H37 DIVERSITY EVIDENCE PLANNER OVERLAY",
        "",
        "Use these selected evidence cards to improve evidence diversity.",
        "This overlay is behavior/retrieval guidance only; it is not proof by itself.",
        "Only current proof_context citations can prove factual source claims.",
        "",
        f"target_question_id: {plan_record.get('question_id')}",
        f"task_type: {plan_record.get('task_type')}",
        "",
        "Diversity requirements:",
        "- Use multiple source-trace-ready evidence cards when the task asks for synthesis.",
        "- Prefer unique pages, figures, part numbers, routes, and nomenclatures.",
        "- Do not collapse every synthesis answer into the same DOUBLE PASSENGER SEAT ASSY cluster unless the task specifically asks for it.",
        "- Do not claim interchangeability, fit, effectivity, replacement approval, or installation safety unless explicit proof_context authority supports it.",
        "",
        "Selected evidence cards:",
    ]
    for c in plan_record.get("selected_cards", [])[:10]:
        lines.append(
            f"- [{c.get('evidence_label')}] route={c.get('route')} page={c.get('page')} "
            f"figure={c.get('figure')} part={c.get('part_number')} nomenclature={c.get('nomenclature')} | "
            f"{c.get('preview')}"
        )
    return "\n".join(lines).strip()


def check_diversity_evidence_planner(
    diversity_planner: str | Path,
    min_plan_records: int = 5,
    min_diversity_pass: int = 4,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(diversity_planner)
    if data is None:
        raise FileNotFoundError(diversity_planner)
    summary = dict(data.get("summary", {}))
    failures: List[str] = []
    if int(summary.get("plan_record_count") or 0) < min_plan_records:
        failures.append("plan_record_count_below_min")
    if int(summary.get("diversity_pass_count") or 0) < min_diversity_pass:
        failures.append("diversity_pass_count_below_min")
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_not_pass")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_nonzero")
    if int(summary.get("unsafe_finding_count") or 0) > max_unsafe:
        failures.append("unsafe_finding_count_above_max")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count_above_max")
    quality_status = "PASS" if not failures else "FAIL"
    return {
        "status": "TRACE_NET_H37_DIVERSITY_EVIDENCE_PLANNER_CHECKED",
        "quality_status": quality_status,
        "plan_record_count": int(summary.get("plan_record_count") or 0),
        "diversity_pass_count": int(summary.get("diversity_pass_count") or 0),
        "review_count": int(summary.get("review_count") or 0),
        "unsafe_finding_count": int(summary.get("unsafe_finding_count") or 0),
        "answer_permission_count": int(summary.get("answer_permission_count") or 0),
        "write_attempt_count": int(summary.get("write_attempt_count") or 0),
        "quality_failures": failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net H37 diversity evidence planner")
    parser.add_argument("--contract-run")
    parser.add_argument("--image-visual-evidence-pack")
    parser.add_argument("--raw-ocr-nomenclature-extractor")
    parser.add_argument("--table-route-evidence-packager")
    parser.add_argument("--table-exact-search-adapter")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-cards-per-task", type=int, default=8)
    parser.add_argument("--min-plan-records", type=int, default=5)
    parser.add_argument("--min-diversity-pass", type=int, default=4)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-write-attempts", type=int, default=0)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_diversity_evidence_planner(**vars(args))
    s = manifest["summary"]
    print("status=TRACE_NET_H37_DIVERSITY_EVIDENCE_PLANNER_BUILT")
    print(f"quality_status={manifest['quality_status']}")
    print(f"plan_record_count={s['plan_record_count']}")
    print(f"diversity_pass_count={s['diversity_pass_count']}")
    print(f"review_count={s['review_count']}")
    print(f"unsafe_finding_count={s['unsafe_finding_count']}")
    print(f"answer_permission_count={s['answer_permission_count']}")
    print(f"write_attempt_count={s['write_attempt_count']}")
    print(f"output={Path(args.output_dir) / (MODULE + '.json')}")
    return 0 if manifest["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
