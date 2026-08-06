"""TRACE-Net Human Review Promotion Gate v1.

This module evaluates human review decisions that ask for stronger evidence
promotion. Reviewer decisions are advisory; this promotion gate is the control
point that decides whether a decision has enough source/citation/catalog/graph
support to be eligible for a later writeback. The module is intentionally
read-only: it never mutates source truth, graph truth, Qdrant, or Postgres.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_human_review_promotion_gate_v1"
DEFAULT_REPORT_FILENAME = "trace_net_human_review_promotion_gate_v1.json"
DEFAULT_RECORDS_FILENAME = "trace_net_human_review_promotion_gate_v1_records.jsonl"
DEFAULT_SUMMARY_FILENAME = "trace_net_human_review_promotion_gate_v1_summary.json"
DEFAULT_MANIFEST_FILENAME = "trace_net_human_review_promotion_gate_v1_manifest.json"
DEFAULT_QUALITY_FILENAME = "trace_net_human_review_promotion_gate_v1_quality.json"
DEFAULT_MD_FILENAME = "trace_net_human_review_promotion_gate_v1.md"
DEFAULT_HTML_FILENAME = "trace_net_human_review_promotion_gate_v1.html"

PROMOTION_DECISION_TYPES = {
    "approve",
    "confirm_blank",
    "confirm_table_repair",
    "confirm_callout",
    "confirm_part_link",
}

APPROVABLE_DECISION_TYPES = {
    "confirm_blank",
    "confirm_table_repair",
    "confirm_part_link",
}

CALL_OUT_DECISION_TYPES = {"confirm_callout"}
NON_PROMOTION_STATUS = "not_a_promotion_candidate"
APPROVED_STATUS = "approved_for_controlled_promotion"
DENIED_STATUS = "denied_needs_more_evidence"
REVIEW_STATUS = "promotion_review_required"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def unique_nonempty(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "1", "yes", "y", "pass", "approved"}


def load_review_decision_report(path: str | Path) -> dict[str, Any]:
    payload = read_json(path)
    return payload


def load_records_from_report(payload: dict[str, Any], key: str, alt_keys: Iterable[str] = ()) -> list[dict[str, Any]]:
    for candidate_key in [key, *alt_keys]:
        value = payload.get(candidate_key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def load_optional_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return read_json(p)


def index_triage_cards(triage_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cards = load_records_from_report(triage_payload, "triage_cards", ["cards"])
    out: dict[str, dict[str, Any]] = {}
    for card in cards:
        card_id = str(card.get("triage_card_id") or card.get("card_id") or card.get("target_id") or "")
        if card_id:
            out[card_id] = card
    return out


def index_table_repairs(table_payload: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """Return repairs by page and by merged part number."""
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_part: dict[str, list[dict[str, Any]]] = defaultdict(list)
    records = load_records_from_report(table_payload, "records")
    for record in records:
        page_id = str(record.get("page_id") or "")
        repairs = record.get("repairs") or []
        for repair in repairs:
            if not isinstance(repair, dict):
                continue
            repair_copy = dict(repair)
            repair_copy.setdefault("page_id", page_id)
            if page_id:
                by_page[page_id].append(repair_copy)
            part = str(repair_copy.get("merged_part_number") or repair_copy.get("part_number") or "")
            if part:
                by_part[part].append(repair_copy)
    return dict(by_page), dict(by_part)


def index_embedding_candidates(embedding_payload: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], set[str]]:
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_part: dict[str, list[dict[str, Any]]] = defaultdict(list)
    citation_ids: set[str] = set()
    records = load_records_from_report(embedding_payload, "records")
    for record in records:
        page_id = str(record.get("page_id") or "")
        if page_id:
            by_page[page_id].append(record)
        for cid in as_list(record.get("citation_ids")) + as_list(record.get("citation_id")):
            if cid:
                citation_ids.add(str(cid))
        text_blob = " ".join(str(record.get(k) or "") for k in ["text", "content", "search_text", "source_text", "source_candidate_id"])
        for part in as_list(record.get("part_numbers")) + as_list(record.get("part_number")):
            if part:
                by_part[str(part)].append(record)
        # Conservative fallback: if exact known part-looking strings are present in metadata/text.
        for token in text_blob.replace("/", " ").replace("|", " ").split():
            token = token.strip(",.;:()[]{}")
            if token.count("-") >= 2 and any(ch.isdigit() for ch in token):
                by_part[token].append(record)
    return dict(by_page), dict(by_part), citation_ids


def index_graph_parts(graph_payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    part_nodes: dict[str, dict[str, Any]] = {}
    page_ids: set[str] = set()
    for node in load_records_from_report(graph_payload, "part_candidate_nodes"):
        part = str(node.get("part_number") or node.get("canonical_part_candidate") or (node.get("properties") or {}).get("part_number") or "")
        if part:
            part_nodes[part] = node
        for page_id in as_list(node.get("source_page_ids")) + as_list((node.get("properties") or {}).get("source_page_ids")):
            if page_id:
                page_ids.add(str(page_id))
    # Fallback to all node plans.
    for node in load_records_from_report(graph_payload, "node_plans"):
        if str(node.get("node_type") or "") == "PartCandidate":
            props = node.get("properties") or {}
            part = str(props.get("part_number") or props.get("canonical_part_candidate") or node.get("label") or "")
            if part:
                part_nodes.setdefault(part, node)
            for page_id in as_list(props.get("source_page_ids")) + as_list(node.get("source_page_ids")) + as_list(node.get("page_id")):
                if page_id:
                    page_ids.add(str(page_id))
    return part_nodes, page_ids


def derive_support_context(
    *,
    table_cell_normalizer: dict[str, Any],
    embedding_candidates: dict[str, Any],
    graph_overlay_part_normalizer: dict[str, Any],
) -> dict[str, Any]:
    repairs_by_page, repairs_by_part = index_table_repairs(table_cell_normalizer)
    candidates_by_page, candidates_by_part, citation_ids = index_embedding_candidates(embedding_candidates)
    graph_part_nodes, graph_page_ids = index_graph_parts(graph_overlay_part_normalizer)
    return {
        "repairs_by_page": repairs_by_page,
        "repairs_by_part": repairs_by_part,
        "candidates_by_page": candidates_by_page,
        "candidates_by_part": candidates_by_part,
        "citation_ids": citation_ids,
        "graph_part_nodes": graph_part_nodes,
        "graph_page_ids": graph_page_ids,
    }


def collect_decision_context(decision: dict[str, Any], triage_cards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    triage_card_id = str(decision.get("triage_card_id") or "")
    triage_card = triage_cards.get(triage_card_id, {}) if triage_card_id else {}
    page_ids = unique_nonempty([
        *as_list(decision.get("page_ids")),
        *as_list(triage_card.get("page_ids")),
        decision.get("page_id"),
        triage_card.get("page_id"),
    ])
    citation_ids = unique_nonempty([
        *as_list(decision.get("citation_ids")),
        *as_list(triage_card.get("citation_ids")),
    ])
    community_ids = unique_nonempty([
        *as_list(decision.get("community_ids")),
        *as_list(triage_card.get("community_ids")),
    ])
    part_numbers = unique_nonempty([
        *as_list(decision.get("part_numbers")),
        *as_list(triage_card.get("part_numbers")),
        decision.get("part_number"),
        triage_card.get("part_number"),
    ])
    return {
        "triage_card": triage_card,
        "triage_card_id": triage_card_id,
        "page_ids": page_ids,
        "citation_ids": citation_ids,
        "community_ids": community_ids,
        "part_numbers": part_numbers,
    }


def find_support_for_pages(page_ids: list[str], context: dict[str, Any]) -> dict[str, Any]:
    candidates_by_page: dict[str, list[dict[str, Any]]] = context.get("candidates_by_page") or {}
    repairs_by_page: dict[str, list[dict[str, Any]]] = context.get("repairs_by_page") or {}
    graph_page_ids: set[str] = context.get("graph_page_ids") or set()
    pages_with_candidates = [p for p in page_ids if p in candidates_by_page]
    pages_with_repairs = [p for p in page_ids if p in repairs_by_page]
    pages_with_graph = [p for p in page_ids if p in graph_page_ids or p in candidates_by_page or p in repairs_by_page]
    citations = sorted({cid for p in page_ids for cand in candidates_by_page.get(p, []) for cid in as_list(cand.get("citation_ids")) + as_list(cand.get("citation_id")) if cid})
    answer_support_candidates = [
        cand for p in page_ids for cand in candidates_by_page.get(p, [])
        if str(cand.get("rag_bucket") or "") in {"source_text_evidence", "verified_part_evidence"}
    ]
    return {
        "pages_with_candidates": pages_with_candidates,
        "pages_with_repairs": pages_with_repairs,
        "pages_with_graph": pages_with_graph,
        "citation_ids": citations,
        "answer_support_candidate_count": len(answer_support_candidates),
    }


def find_support_for_parts(part_numbers: list[str], context: dict[str, Any]) -> dict[str, Any]:
    candidates_by_part: dict[str, list[dict[str, Any]]] = context.get("candidates_by_part") or {}
    repairs_by_part: dict[str, list[dict[str, Any]]] = context.get("repairs_by_part") or {}
    graph_part_nodes: dict[str, dict[str, Any]] = context.get("graph_part_nodes") or {}
    parts_with_candidates = [p for p in part_numbers if p in candidates_by_part]
    parts_with_repairs = [p for p in part_numbers if p in repairs_by_part]
    parts_with_graph = [p for p in part_numbers if p in graph_part_nodes]
    citations = sorted({cid for p in part_numbers for cand in candidates_by_part.get(p, []) for cid in as_list(cand.get("citation_ids")) + as_list(cand.get("citation_id")) if cid})
    catalog_supported_repairs = [r for p in part_numbers for r in repairs_by_part.get(p, []) if str(r.get("repair_status") or "") == "catalog_supported" or truthy(r.get("catalog_supported"))]
    return {
        "parts_with_candidates": parts_with_candidates,
        "parts_with_repairs": parts_with_repairs,
        "parts_with_graph": parts_with_graph,
        "catalog_supported_repair_count": len(catalog_supported_repairs),
        "citation_ids": citations,
    }


def evaluate_promotion_decision(
    decision: dict[str, Any],
    *,
    triage_cards: dict[str, dict[str, Any]],
    support_context: dict[str, Any],
) -> dict[str, Any]:
    decision_type = str(decision.get("decision_type") or "")
    decision_id = str(decision.get("review_decision_id") or stable_hash(json.dumps(decision, sort_keys=True)))
    ctx = collect_decision_context(decision, triage_cards)
    page_ids = ctx["page_ids"]
    part_numbers = ctx["part_numbers"]
    citation_ids = ctx["citation_ids"]
    page_support = find_support_for_pages(page_ids, support_context)
    part_support = find_support_for_parts(part_numbers, support_context)

    is_candidate = bool(decision.get("promotion_candidate")) or decision_type in PROMOTION_DECISION_TYPES
    unsafe_decision = truthy(decision.get("unsafe_decision")) or truthy(decision.get("prompt_injection_flagged"))
    required_checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, value: Any, expected: Any) -> None:
        required_checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected})

    if not is_candidate:
        status = NON_PROMOTION_STATUS
        reason = "Decision type does not request evidence promotion."
    elif unsafe_decision:
        add_check("decision_safe", False, "unsafe_decision", "safe decision")
        status = DENIED_STATUS
        reason = "Decision was unsafe or prompt-injection flagged."
    else:
        add_check("decision_safe", True, "safe", "safe decision")
        if decision_type == "confirm_blank":
            add_check("has_page_id", bool(page_ids), page_ids, "at least one page id")
            add_check("has_graph_or_source_page_support", bool(page_support["pages_with_graph"] or page_support["pages_with_candidates"]), page_support["pages_with_graph"] or page_support["pages_with_candidates"], "source/graph support")
        elif decision_type == "confirm_table_repair":
            add_check("has_page_id", bool(page_ids), page_ids, "at least one page id")
            add_check("has_table_repair_support", bool(page_support["pages_with_repairs"] or part_support["parts_with_repairs"]), page_support["pages_with_repairs"] or part_support["parts_with_repairs"], "table repair support")
            add_check("catalog_supported_repair", part_support["catalog_supported_repair_count"] > 0 or bool(page_support["pages_with_repairs"]), part_support["catalog_supported_repair_count"], "> 0 catalog-supported repairs or same-page repair")
            combined_citations = unique_nonempty([*citation_ids, *page_support["citation_ids"], *part_support["citation_ids"]])
            add_check("has_citation", bool(combined_citations), combined_citations[:5], "at least one citation")
        elif decision_type == "confirm_part_link":
            add_check("has_page_or_part", bool(page_ids or part_numbers), {"page_ids": page_ids, "part_numbers": part_numbers}, "page or part target")
            add_check("has_part_graph_or_candidate_support", bool(part_support["parts_with_graph"] or part_support["parts_with_candidates"] or page_support["answer_support_candidate_count"] > 0), {"parts_with_graph": part_support["parts_with_graph"], "parts_with_candidates": part_support["parts_with_candidates"], "answer_support_candidate_count": page_support["answer_support_candidate_count"]}, "graph/candidate support")
            combined_citations = unique_nonempty([*citation_ids, *page_support["citation_ids"], *part_support["citation_ids"]])
            add_check("has_citation", bool(combined_citations), combined_citations[:5], "at least one citation")
        elif decision_type == "approve":
            add_check("has_page_or_citation_or_part", bool(page_ids or citation_ids or part_numbers), {"page_ids": page_ids, "citation_ids": citation_ids, "part_numbers": part_numbers}, "traceable target")
            combined_citations = unique_nonempty([*citation_ids, *page_support["citation_ids"], *part_support["citation_ids"]])
            add_check("has_citation_or_review_trace", bool(combined_citations or page_ids), combined_citations[:5] or page_ids, "citation or page trace")
        elif decision_type in CALL_OUT_DECISION_TYPES:
            # Callouts need an extra visual verifier/promotion module before promotion.
            add_check("callout_requires_visual_part_verifier", False, decision_type, "verified callout-to-part support")
        else:
            add_check("supported_promotion_type", False, decision_type, sorted(PROMOTION_DECISION_TYPES))

        failed_checks = [c for c in required_checks if not c["passed"]]
        if not failed_checks and decision_type in APPROVABLE_DECISION_TYPES | {"approve"}:
            status = APPROVED_STATUS
            reason = "All required promotion-gate checks passed for controlled promotion eligibility."
        elif decision_type in CALL_OUT_DECISION_TYPES:
            status = REVIEW_STATUS
            reason = "Callout confirmation requires a verified callout-to-part evidence gate before promotion."
        else:
            status = DENIED_STATUS
            reason = "One or more required promotion-gate checks failed."

    combined_citations = unique_nonempty([*citation_ids, *page_support.get("citation_ids", []), *part_support.get("citation_ids", [])])
    promotion_id = f"hreprom__{stable_hash(decision_id + '|' + decision_type, 16)}"
    approved = status == APPROVED_STATUS

    record = {
        "schema_version": SCHEMA_VERSION,
        "promotion_evaluation_id": promotion_id,
        "review_decision_id": decision_id,
        "decision_type": decision_type,
        "decision_effect": decision.get("decision_effect"),
        "promotion_candidate": is_candidate,
        "promotion_gate_status": status,
        "promotion_gate_reason": reason,
        "target_type": decision.get("target_type"),
        "target_id": decision.get("target_id"),
        "triage_card_id": ctx["triage_card_id"],
        "page_ids": page_ids,
        "citation_ids": combined_citations,
        "community_ids": ctx["community_ids"],
        "part_numbers": part_numbers,
        "required_checks": required_checks,
        "failed_check_count": sum(1 for c in required_checks if not c["passed"]),
        "passed_check_count": sum(1 for c in required_checks if c["passed"]),
        "page_support": page_support,
        "part_support": part_support,
        "promotion_effect": derive_promotion_effect(decision_type, status),
        "requires_writeback_gate": approved,
        "requires_regression_after_promotion": approved,
        "approved_for_controlled_promotion": approved,
        "approved_without_citation": approved and not bool(combined_citations) and decision_type != "confirm_blank",
        "approved_without_source_or_page": approved and not bool(page_ids),
        "approved_without_graph_or_catalog_support": approved and not bool(page_support.get("pages_with_graph") or part_support.get("parts_with_graph") or part_support.get("catalog_supported_repair_count") or page_support.get("answer_support_candidate_count")),
        "authority": "human_review_promotion_gate_controlled_advisory",
        "record_type": "human_review_promotion_evaluation",
        "safety_bucket": "human_review_promotion_gate_controlled",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "final_answer_allowed": False,
        "raw_feedback_direct_to_llm": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "created_at": utc_now_iso(),
    }
    record["unsafe_promotion_reasons"] = []
    if record["approved_without_citation"]:
        record["unsafe_promotion_reasons"].append("approved_without_citation")
    if record["approved_without_source_or_page"]:
        record["unsafe_promotion_reasons"].append("approved_without_source_or_page")
    if truthy(decision.get("can_answer_directly")) or truthy(decision.get("can_prove_claims")) or truthy(decision.get("can_mutate_source_truth")):
        record["unsafe_promotion_reasons"].append("source_decision_has_unsafe_authority")
    record["unsafe_promotion_record"] = bool(record["unsafe_promotion_reasons"])
    return record


def derive_promotion_effect(decision_type: str, status: str) -> str:
    if status != APPROVED_STATUS:
        return "no_promotion_effect"
    if decision_type == "confirm_blank":
        return "eligible_to_record_blank_source_trace_preservation"
    if decision_type == "confirm_table_repair":
        return "eligible_to_create_promoted_table_repair_evidence_candidate"
    if decision_type == "confirm_part_link":
        return "eligible_to_create_promoted_part_link_evidence_candidate"
    if decision_type == "approve":
        return "eligible_for_controlled_review_approved_promotion"
    return "eligible_for_controlled_promotion"


def summarize(records: list[dict[str, Any]], decision_payload: dict[str, Any], source_summaries: dict[str, Any]) -> dict[str, Any]:
    candidate_records = [r for r in records if r.get("promotion_candidate")]
    approved_records = [r for r in records if r.get("promotion_gate_status") == APPROVED_STATUS]
    denied_records = [r for r in records if r.get("promotion_gate_status") == DENIED_STATUS]
    review_records = [r for r in records if r.get("promotion_gate_status") == REVIEW_STATUS]
    non_candidates = [r for r in records if r.get("promotion_gate_status") == NON_PROMOTION_STATUS]
    status_counts = Counter(str(r.get("promotion_gate_status") or "") for r in records)
    decision_type_counts = Counter(str(r.get("decision_type") or "") for r in records)
    target_type_counts = Counter(str(r.get("target_type") or "") for r in records)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "UNKNOWN",
        "review_decision_count": len(records),
        "promotion_candidate_count": len(candidate_records),
        "promotion_evaluation_count": len(candidate_records),
        "promotion_approved_count": len(approved_records),
        "promotion_denied_count": len(denied_records),
        "promotion_review_required_count": len(review_records),
        "non_promotion_decision_count": len(non_candidates),
        "promotion_status_counts": dict(status_counts),
        "decision_type_counts": dict(decision_type_counts),
        "target_type_counts": dict(target_type_counts),
        "approved_without_citation_count": sum(1 for r in records if r.get("approved_without_citation")),
        "approved_without_source_or_page_count": sum(1 for r in records if r.get("approved_without_source_or_page")),
        "approved_without_graph_or_catalog_support_count": sum(1 for r in records if r.get("approved_without_graph_or_catalog_support")),
        "unsafe_promotion_record_count": sum(1 for r in records if r.get("unsafe_promotion_record")),
        "promotion_can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "promotion_can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "promotion_can_mutate_source_truth_count": sum(1 for r in records if r.get("can_mutate_source_truth")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "source_truth_mutations_performed": sum(int(r.get("source_truth_mutations_performed") or 0) for r in records),
        "raw_feedback_direct_to_llm_count": sum(1 for r in records if r.get("raw_feedback_direct_to_llm")),
        "final_answer_allowed_count": sum(1 for r in records if r.get("final_answer_allowed")),
        "writeback_required_count": sum(1 for r in records if r.get("requires_writeback_gate")),
        "regression_required_count": sum(1 for r in records if r.get("requires_regression_after_promotion")),
        "affected_page_count": len({p for r in records for p in as_list(r.get("page_ids")) if p}),
        "affected_citation_count": len({c for r in records for c in as_list(r.get("citation_ids")) if c}),
        "affected_part_number_count": len({p for r in records for p in as_list(r.get("part_numbers")) if p}),
        "source_decision_quality_status": str(decision_payload.get("quality_status") or decision_payload.get("status") or ""),
        "source_decision_report_status": str((decision_payload.get("summary") or {}).get("status") or decision_payload.get("quality_status") or decision_payload.get("status") or ""),
        "source_summaries": source_summaries,
    }


def quality_report(
    report_or_records: dict[str, Any] | list[dict[str, Any]],
    *,
    min_review_decisions: int = 1,
    min_promotion_evaluations: int = 0,
    require_source_decision_quality_pass: bool = False,
) -> dict[str, Any]:
    if isinstance(report_or_records, dict) and "promotion_records" in report_or_records:
        records = report_or_records.get("promotion_records") or []
        summary = dict(report_or_records.get("summary") or {})
    elif isinstance(report_or_records, list):
        records = report_or_records
        summary = summarize(records, {}, {})
    else:
        records = []
        summary = dict(report_or_records.get("summary") or {}) if isinstance(report_or_records, dict) else {}

    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, value: Any, expected: Any, severity: str = "critical") -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected, "severity": severity})

    add_check("min_review_decisions", summary.get("review_decision_count", 0) >= min_review_decisions, summary.get("review_decision_count", 0), f">= {min_review_decisions}")
    add_check("min_promotion_evaluations", summary.get("promotion_evaluation_count", 0) >= min_promotion_evaluations, summary.get("promotion_evaluation_count", 0), f">= {min_promotion_evaluations}")
    add_check("unsafe_promotion_record_count_zero", summary.get("unsafe_promotion_record_count", 0) == 0, summary.get("unsafe_promotion_record_count", 0), 0)
    add_check("approved_without_citation_count_zero", summary.get("approved_without_citation_count", 0) == 0, summary.get("approved_without_citation_count", 0), 0)
    add_check("approved_without_source_or_page_count_zero", summary.get("approved_without_source_or_page_count", 0) == 0, summary.get("approved_without_source_or_page_count", 0), 0)
    add_check("promotion_can_answer_directly_count_zero", summary.get("promotion_can_answer_directly_count", 0) == 0, summary.get("promotion_can_answer_directly_count", 0), 0)
    add_check("promotion_can_prove_claims_count_zero", summary.get("promotion_can_prove_claims_count", 0) == 0, summary.get("promotion_can_prove_claims_count", 0), 0)
    add_check("promotion_can_mutate_source_truth_count_zero", summary.get("promotion_can_mutate_source_truth_count", 0) == 0, summary.get("promotion_can_mutate_source_truth_count", 0), 0)
    add_check("source_truth_mutation_allowed_count_zero", summary.get("source_truth_mutation_allowed_count", 0) == 0, summary.get("source_truth_mutation_allowed_count", 0), 0)
    add_check("source_truth_mutations_performed_zero", summary.get("source_truth_mutations_performed", 0) == 0, summary.get("source_truth_mutations_performed", 0), 0)
    add_check("raw_feedback_direct_to_llm_count_zero", summary.get("raw_feedback_direct_to_llm_count", 0) == 0, summary.get("raw_feedback_direct_to_llm_count", 0), 0)
    add_check("final_answer_allowed_count_zero", summary.get("final_answer_allowed_count", 0) == 0, summary.get("final_answer_allowed_count", 0), 0)

    if require_source_decision_quality_pass:
        status = str(summary.get("source_decision_quality_status") or "").upper()
        add_check("source_decision_quality_pass", status == "PASS", status, "PASS")

    status = "PASS" if all(c["passed"] or c["severity"] != "critical" for c in checks) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "summary": summary,
        "checks": checks,
    }


def build_promotion_gate_report(
    *,
    review_decisions_path: str | Path,
    output_dir: str | Path,
    triage_report_path: str | Path | None = None,
    table_cell_normalizer_path: str | Path | None = None,
    embedding_candidates_path: str | Path | None = None,
    graph_overlay_part_normalizer_path: str | Path | None = None,
    min_review_decisions: int = 1,
    min_promotion_evaluations: int = 0,
    require_source_decision_quality_pass: bool = False,
    require_source_triage_quality_pass: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    decision_payload = load_review_decision_report(review_decisions_path)
    decisions = load_records_from_report(decision_payload, "decision_records", ["records"])
    triage_payload = load_optional_json(triage_report_path)
    triage_cards = index_triage_cards(triage_payload)
    table_payload = load_optional_json(table_cell_normalizer_path)
    embedding_payload = load_optional_json(embedding_candidates_path)
    graph_payload = load_optional_json(graph_overlay_part_normalizer_path)
    support_context = derive_support_context(
        table_cell_normalizer=table_payload,
        embedding_candidates=embedding_payload,
        graph_overlay_part_normalizer=graph_payload,
    )

    records = [
        evaluate_promotion_decision(decision, triage_cards=triage_cards, support_context=support_context)
        for decision in decisions
    ]

    source_summaries = {
        "review_decisions_quality_status": decision_payload.get("quality_status"),
        "review_decisions_summary_status": (decision_payload.get("summary") or {}).get("status"),
        "triage_quality_status": triage_payload.get("quality_status") if triage_payload else "",
        "table_cell_normalizer_quality_status": table_payload.get("quality_status") if table_payload else "",
        "embedding_candidates_quality_status": embedding_payload.get("quality_status") if embedding_payload else "",
        "graph_overlay_part_normalizer_quality_status": graph_payload.get("quality_status") if graph_payload else "",
        "table_repair_page_count": len(support_context["repairs_by_page"]),
        "embedding_candidate_page_count": len(support_context["candidates_by_page"]),
        "graph_part_candidate_count": len(support_context["graph_part_nodes"]),
    }
    summary = summarize(records, decision_payload, source_summaries)
    if require_source_triage_quality_pass:
        triage_status = str(source_summaries.get("triage_quality_status") or "").upper()
        summary["source_triage_quality_required"] = True
        summary["source_triage_quality_pass"] = triage_status == "PASS"
    else:
        summary["source_triage_quality_required"] = False
        summary["source_triage_quality_pass"] = True

    quality = quality_report(
        {"promotion_records": records, "summary": summary},
        min_review_decisions=min_review_decisions,
        min_promotion_evaluations=min_promotion_evaluations,
        require_source_decision_quality_pass=require_source_decision_quality_pass,
    )
    if require_source_triage_quality_pass and not summary["source_triage_quality_pass"]:
        quality["checks"].append({"name": "source_triage_quality_pass", "passed": False, "value": source_summaries.get("triage_quality_status"), "expected": "PASS", "severity": "critical"})
        quality["status"] = "FAIL"
    summary["status"] = quality["status"]

    report_path = output_dir / DEFAULT_REPORT_FILENAME
    records_path = output_dir / DEFAULT_RECORDS_FILENAME
    summary_path = output_dir / DEFAULT_SUMMARY_FILENAME
    manifest_path = output_dir / DEFAULT_MANIFEST_FILENAME
    quality_path = output_dir / DEFAULT_QUALITY_FILENAME
    md_path = output_dir / DEFAULT_MD_FILENAME
    html_path = output_dir / DEFAULT_HTML_FILENAME

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "HUMAN_REVIEW_PROMOTION_GATE_BUILT",
        "quality_status": quality["status"],
        "generated_at": utc_now_iso(),
        "summary": summary,
        "promotion_records": records,
        "quality": quality,
        "report_path": str(report_path),
        "records_path": str(records_path),
        "quality_path": str(quality_path),
        "writeback_mode": "read_only_promotion_gate",
        "source_truth_mutations_performed": 0,
    }

    write_json(report_path, payload)
    write_jsonl(records_path, records)
    write_json(summary_path, summary)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": payload["generated_at"],
        "review_decisions_path": str(review_decisions_path),
        "triage_report_path": str(triage_report_path or ""),
        "table_cell_normalizer_path": str(table_cell_normalizer_path or ""),
        "embedding_candidates_path": str(embedding_candidates_path or ""),
        "graph_overlay_part_normalizer_path": str(graph_overlay_part_normalizer_path or ""),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "quality_path": str(quality_path),
        "writeback_mode": "read_only_promotion_gate",
    })
    if write_quality:
        write_json(quality_path, quality)
    write_markdown(md_path, payload)
    write_html(html_path, payload)
    return payload


def write_markdown(path: str | Path, payload: dict[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Human Review Promotion Gate v1",
        "",
        f"**Status:** {payload.get('status')}",
        f"**Quality:** {payload.get('quality_status')}",
        f"**Writeback mode:** {payload.get('writeback_mode')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "review_decision_count",
        "promotion_candidate_count",
        "promotion_approved_count",
        "promotion_denied_count",
        "promotion_review_required_count",
        "non_promotion_decision_count",
        "approved_without_citation_count",
        "unsafe_promotion_record_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Promotion Records", ""])
    for record in payload.get("promotion_records", [])[:50]:
        lines.append(f"- `{record.get('promotion_evaluation_id')}`: {record.get('decision_type')} -> {record.get('promotion_gate_status')} ({record.get('promotion_gate_reason')})")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html(path: str | Path, payload: dict[str, Any]) -> None:
    summary = payload.get("summary") or {}
    rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in summary.items()
        if not isinstance(v, (dict, list))
    )
    record_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(r.get('promotion_evaluation_id')))}</td>"
        f"<td>{html.escape(str(r.get('decision_type')))}</td>"
        f"<td>{html.escape(str(r.get('promotion_gate_status')))}</td>"
        f"<td>{html.escape(str(r.get('promotion_gate_reason')))}</td>"
        "</tr>"
        for r in payload.get("promotion_records", [])[:200]
    )
    doc = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>TRACE-Net Human Review Promotion Gate v1</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}td,th{{border:1px solid #ddd;padding:6px}}th{{background:#f4f4f4;text-align:left}}code{{background:#f7f7f7;padding:2px 4px}}</style>
</head><body>
<h1>TRACE-Net Human Review Promotion Gate v1</h1>
<p><strong>Status:</strong> {html.escape(str(payload.get('status')))}<br>
<strong>Quality:</strong> {html.escape(str(payload.get('quality_status')))}<br>
<strong>Writeback mode:</strong> {html.escape(str(payload.get('writeback_mode')))}</p>
<h2>Summary</h2><table>{rows}</table>
<h2>Promotion Records</h2><table><tr><th>ID</th><th>Decision</th><th>Status</th><th>Reason</th></tr>{record_rows}</table>
</body></html>"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(doc, encoding="utf-8")


def print_report_summary(payload: dict[str, Any]) -> None:
    summary = payload.get("summary") or {}
    print("TRACE-Net human review promotion gate v1")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in [
        "review_decision_count",
        "promotion_candidate_count",
        "promotion_evaluation_count",
        "promotion_approved_count",
        "promotion_denied_count",
        "promotion_review_required_count",
        "non_promotion_decision_count",
        "approved_without_citation_count",
        "approved_without_source_or_page_count",
        "unsafe_promotion_record_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {payload.get('report_path')}")
    print(f" quality_path: {payload.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net human review promotion gate v1")
    parser.add_argument("--review-decisions", required=True)
    parser.add_argument("--triage-report", default=None)
    parser.add_argument("--table-cell-normalizer", default=None)
    parser.add_argument("--embedding-candidates", default=None)
    parser.add_argument("--graph-overlay-part-normalizer", default=None)
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/human_review_promotion_gate")
    parser.add_argument("--min-review-decisions", type=int, default=1)
    parser.add_argument("--min-promotion-evaluations", type=int, default=0)
    parser.add_argument("--require-source-decision-quality-pass", action="store_true")
    parser.add_argument("--require-source-triage-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        payload = build_promotion_gate_report(
            review_decisions_path=args.review_decisions,
            output_dir=args.output_dir,
            triage_report_path=args.triage_report,
            table_cell_normalizer_path=args.table_cell_normalizer,
            embedding_candidates_path=args.embedding_candidates,
            graph_overlay_part_normalizer_path=args.graph_overlay_part_normalizer,
            min_review_decisions=args.min_review_decisions,
            min_promotion_evaluations=args.min_promotion_evaluations,
            require_source_decision_quality_pass=args.require_source_decision_quality_pass,
            require_source_triage_quality_pass=args.require_source_triage_quality_pass,
            write_quality=args.quality,
        )
    except Exception as exc:
        print(f"TRACE-Net human review promotion gate failed: {exc}")
        return 1
    print_report_summary(payload)
    return 0 if payload.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
