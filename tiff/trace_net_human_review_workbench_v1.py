"""TRACE-Net Human Review Workbench View Model v1.

Builds a read-only, UI-ready view model over the TRACE-Net human review
triage cards. The workbench model is intentionally not a truth/writeback layer:
it aggregates page images/source package metadata, visual/table/category context,
recommended actions, and allowed reviewer decisions so a UI can present review
work clearly.

Safety contract:
- workbench cards cannot answer directly
- workbench cards cannot prove claims
- workbench cards cannot mutate source truth
- raw feedback is never passed directly to the LLM
- review decisions are advisory until the existing decision recorder/promotion
  gate handles them
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_human_review_workbench_v1"
AUTHORITY = "human_review_workbench_view_model_only"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/human_review_workbench")
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


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


def str_list(value: Any, *, limit: int | None = None) -> list[str]:
    out: list[str] = []
    for item in as_list(value):
        if item is None:
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    deduped = sorted(set(out))
    return deduped[:limit] if limit is not None else deduped


def unique_sorted(values: Iterable[Any], *, limit: int | None = None) -> list[str]:
    clean = sorted({str(v).strip() for v in values if v is not None and str(v).strip()})
    return clean[:limit] if limit is not None else clean


def sanitize_text(value: Any, max_chars: int = 1200) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()[:max_chars]


def stable_id(prefix: str, *parts: Any) -> str:
    data = "||".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha256(data.encode('utf-8')).hexdigest()[:16]}"


def clamp_priority(priority: Any) -> str:
    value = str(priority or "medium").lower()
    return value if value in PRIORITY_ORDER else "medium"


def priority_sort_value(priority: Any) -> int:
    return PRIORITY_ORDER.get(clamp_priority(priority), 9)


def get_nested(obj: dict[str, Any], path: Iterable[str], default: Any = None) -> Any:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue
        if isinstance(value, dict) and not value:
            continue
        return value
    return None


def load_records(payload: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def page_id_from_record(record: dict[str, Any]) -> str | None:
    """Return a page_id from any TRACE-Net page/profile card shape."""
    if not isinstance(record, dict):
        return None
    direct = record.get("page_id")
    if direct:
        return str(direct)
    props = record.get("properties") if isinstance(record.get("properties"), dict) else {}
    if props.get("page_id"):
        return str(props["page_id"])
    dc = record.get("dc") if isinstance(record.get("dc"), dict) else {}
    identifier = dc.get("dc:identifier")
    if identifier:
        return str(identifier)
    trace = record.get("trace_net") if isinstance(record.get("trace_net"), dict) else {}
    trace_page_id = trace.get("trace_net:page_id") or trace.get("page_id")
    if trace_page_id:
        return str(trace_page_id)
    return None


def by_page(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        page_id = page_id_from_record(record)
        if page_id:
            index[str(page_id)] = record
    return index


def task_page_id(task: dict[str, Any]) -> str | None:
    value = task.get("page_id")
    if value:
        return str(value)
    for key in ("page_ids", "source_page_ids"):
        values = task.get(key)
        if isinstance(values, list) and values:
            return str(values[0])
    return None


def source_quality(payload: dict[str, Any]) -> str:
    return str(payload.get("quality_status") or payload.get("summary", {}).get("quality_status") or payload.get("status") or "").upper()


def card_page_ids(card: dict[str, Any]) -> list[str]:
    values = str_list(card.get("page_ids"))
    if not values and card.get("page_id"):
        values = [str(card["page_id"])]
    return values


def task_allowed_decision_hints(card: dict[str, Any]) -> list[str]:
    card_type = str(card.get("card_type") or "")
    task_types = {str(item.get("task_type") or "") for item in card.get("task_type_summaries", []) if isinstance(item, dict)}
    text = " ".join([card_type, " ".join(task_types), str(card.get("reason_summary") or "")]).lower()

    decisions = [
        "needs_more_review",
        "add_reviewer_comment",
        "reject_unusable_signal",
    ]
    if "critical" in card_type or "prompt_injection" in text or "instruction" in text:
        decisions.extend([
            "quarantine_feedback_signal",
            "reject_feedback_instruction_manipulation",
            "sanitize_feedback_memory_only",
            "escalate_security_review",
        ])
    if "blank" in card_type or "blank" in text:
        decisions.extend([
            "confirm_blank_source_trace",
            "reject_blank_classification",
            "request_ocr_blank_recheck",
        ])
    if "table" in card_type or "table" in text or "repair" in text:
        decisions.extend([
            "confirm_table_repair_candidate",
            "reject_table_repair_candidate",
            "request_table_retry",
            "mark_table_row_reviewed",
        ])
    if "visual" in card_type or "callout" in text or "diagram" in text:
        decisions.extend([
            "verify_callout_labels",
            "suppress_random_number_callouts",
            "confirm_visual_part_link",
            "reject_visual_part_link",
            "send_page_to_vision_model_pilot",
        ])
    if "community" in card_type or "community" in text:
        decisions.extend([
            "confirm_community_navigation_label",
            "mark_community_reviewed_navigation_only",
            "request_community_split_or_merge_review",
        ])
    if "feedback" in text and "critical" not in card_type:
        decisions.extend([
            "accept_sanitized_feedback_as_advisory",
            "reject_feedback_as_unhelpful",
            "send_feedback_to_human_decision_recorder",
        ])
    return unique_sorted(decisions)


def next_action_for_card(card: dict[str, Any]) -> str:
    card_type = str(card.get("card_type") or "")
    if card.get("priority") == "critical":
        return "Resolve critical item before using the affected signal in retrieval, review, or answer workflows."
    if "visual" in card_type or "callout" in card_type:
        return "Open the page image, verify callout labels and visual-part links, suppress random numbers, and compare against table/catalog/graph evidence."
    if "table" in card_type:
        return "Inspect normalized rows/cells and confirm or reject table repair candidates before promotion."
    if "blank" in card_type:
        return "Confirm the blank page while preserving source package lineage and source trace."
    if "community" in card_type:
        return "Inspect the category-aware community card and mark community guidance as reviewed or navigation-only."
    return "Review the grouped tasks and record a safe human-review decision."


def summarize_visual(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {"available": False}
    return {
        "available": True,
        "source_visual_type": record.get("source_visual_type") or record.get("figure_understanding_visual_type"),
        "raw_callout_candidate_count": int(record.get("raw_callout_candidate_count") or 0),
        "clean_callout_count": int(record.get("clean_callout_count") or 0),
        "suppressed_random_number_count": int(record.get("suppressed_random_number_count") or record.get("random_number_suppressed_count") or 0),
        "callout_to_table_row_link_count": int(record.get("callout_to_table_row_link_count") or 0),
        "linked_visual_part_candidate_count": int(record.get("linked_visual_part_candidate_count") or record.get("visual_part_link_count") or 0),
        "catalog_verified_visual_part_count": int(record.get("catalog_verified_visual_part_count") or 0),
        "needs_human_review": bool(record.get("needs_human_review")),
        "review_reasons": str_list(record.get("review_reasons"), limit=12),
        "clean_callout_labels": [str(c.get("label")) for c in as_list(record.get("clean_callouts")) if isinstance(c, dict) and c.get("label")][:20],
        "visual_part_links": as_list(record.get("visual_part_links"))[:20],
    }


def summarize_table(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {"available": False}
    repairs = as_list(record.get("repairs"))
    cells = as_list(record.get("cells"))
    rows = as_list(record.get("rows"))
    return {
        "available": True,
        "table_type": record.get("table_type"),
        "trust_tier": record.get("trust_tier"),
        "rag_bucket": record.get("rag_bucket"),
        "row_count": int(record.get("row_count") or len(rows)),
        "cell_count": int(record.get("cell_count") or len(cells)),
        "repair_count": int(record.get("repair_count") or len(repairs)),
        "answer_support_candidate": bool(record.get("answer_support_candidate")),
        "retrieval_only": bool(record.get("retrieval_only")),
        "citation_ids": str_list(record.get("citation_ids"), limit=25),
        "repaired_values": unique_sorted((r.get("repaired_text") or r.get("normalized_text") or r.get("text") for r in repairs if isinstance(r, dict)), limit=20),
    }


def summarize_category(page_card: dict[str, Any] | None) -> dict[str, Any]:
    if not page_card:
        return {"available": False}
    props = page_card.get("properties") if isinstance(page_card.get("properties"), dict) else page_card
    return {
        "available": True,
        "page_category_label": props.get("page_category_label") or page_card.get("label"),
        "category_aware_label": props.get("category_aware_label"),
        "dc_type": str_list(props.get("dc_type") or props.get("dc_types"), limit=20),
        "dominant_element_families": str_list(props.get("dominant_element_families"), limit=12),
        "leiden_hint_element_families": str_list(props.get("leiden_hint_element_families"), limit=12),
        "suppressed_leiden_hint_families": str_list(props.get("suppressed_leiden_hint_families"), limit=12),
        "community_ids": str_list(props.get("community_ids"), limit=25),
        "review_required": bool(props.get("review_required")),
    }


def _trace_source_package_block(page_record: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    """Accept current and legacy source-package field placement."""
    source = page_record.get("source_package") if isinstance(page_record.get("source_package"), dict) else {}
    if source:
        return source
    nested = trace.get("trace_net:source_package") if isinstance(trace.get("trace_net:source_package"), dict) else {}
    return nested


def summarize_source_package(page_record: dict[str, Any] | None) -> dict[str, Any]:
    if not page_record:
        return {"available": False}
    dc = page_record.get("dc") if isinstance(page_record.get("dc"), dict) else {}
    trace = page_record.get("trace_net") if isinstance(page_record.get("trace_net"), dict) else {}
    source = _trace_source_package_block(page_record, trace)
    entry_name = first_nonempty(
        source.get("trace_net:source_package_entry_name"),
        source.get("source_package_entry_name"),
        source.get("entry_name"),
    )
    href = first_nonempty(
        source.get("trace_net:source_package_entry_href"),
        source.get("source_package_entry_href"),
        source.get("href"),
    )
    page_number = first_nonempty(
        source.get("trace_net:source_package_page_number"),
        source.get("source_package_page_number"),
        source.get("page_number"),
        trace.get("trace_net:source_package_page_number"),
    )
    size_bytes = first_nonempty(
        source.get("trace_net:source_package_entry_size_bytes"),
        source.get("source_package_entry_size_bytes"),
        source.get("size_bytes_zip"),
        source.get("size_bytes_mets"),
        trace.get("trace_net:source_package_entry_size_bytes"),
    )
    checksum_sha1 = first_nonempty(
        source.get("trace_net:source_package_entry_checksum_sha1"),
        source.get("source_package_checksum_sha1"),
        source.get("checksum_sha1_mets"),
        source.get("checksum_sha1_computed"),
        trace.get("trace_net:source_package_entry_checksum_sha1"),
    )
    checksum_match = first_nonempty(
        source.get("trace_net:source_package_entry_checksum_match"),
        source.get("source_package_checksum_match"),
        source.get("checksum_match"),
    )
    traceability = first_nonempty(
        source.get("trace_net:source_traceability_status"),
        source.get("source_traceability_status"),
        trace.get("trace_net:source_package_traceability_status"),
        trace.get("trace_net:source_traceability_status"),
    )
    dc_source = dc.get("dc:source") or dc.get("dcterms:source")
    available = bool(entry_name or href or checksum_sha1 or traceability)
    return {
        "available": available,
        "dc_identifier": dc.get("dc:identifier") or page_id_from_record(page_record),
        "dc_type": str_list(dc.get("dc:type"), limit=20),
        "dc_source": dc_source,
        "dc_language": dc.get("dc:language"),
        "source_package_id": source.get("trace_net:source_package_id") or source.get("source_package_id"),
        "source_package_label": source.get("trace_net:source_package_label") or source.get("source_package_label"),
        "source_package_objid": source.get("trace_net:source_package_objid") or source.get("source_package_objid"),
        "source_package_type": source.get("trace_net:source_package_type") or source.get("source_package_type"),
        "source_package_record_status": source.get("trace_net:source_package_record_status") or source.get("source_package_record_status"),
        "source_package_created_at": source.get("trace_net:source_package_created_at") or source.get("source_package_created_at"),
        "source_package_date_captured": source.get("trace_net:source_package_date_captured") or source.get("source_package_date_captured"),
        "source_package_language_code": source.get("trace_net:source_package_language_code") or source.get("source_package_language_code") or dc.get("dc:language"),
        "metadata_xml_present": source.get("trace_net:metadata_xml_present") if "trace_net:metadata_xml_present" in source else source.get("metadata_xml_present"),
        "source_package_entry_name": entry_name,
        "source_package_entry_href": href,
        "source_package_page_number": page_number,
        "source_package_entry_size_bytes": size_bytes,
        "source_package_checksum_sha1": checksum_sha1,
        "source_package_checksum_match": checksum_match,
        "source_traceability_status": traceability,
    }


def make_page_preview(page_id: str, source_package: dict[str, Any]) -> dict[str, Any]:
    entry_name = source_package.get("source_package_entry_name")
    href = source_package.get("source_package_entry_href")
    dc_source = source_package.get("dc_source")
    page_number = source_package.get("source_package_page_number")
    has_entry = bool(entry_name or href or dc_source)
    return {
        "available": has_entry,
        "page_id": page_id,
        "page_number": page_number,
        "image_entry_name": entry_name,
        "image_href": href,
        "source_label": first_nonempty(source_package.get("source_package_label"), dc_source, href, entry_name),
        "source_package_objid": source_package.get("source_package_objid"),
        "entry_size_bytes": source_package.get("source_package_entry_size_bytes"),
        "checksum_sha1": source_package.get("source_package_checksum_sha1"),
        "checksum_match": source_package.get("source_package_checksum_match"),
        "traceability": source_package.get("source_traceability_status"),
        "viewer_hint": "Use image_href or a resolved local TIFF path in the review UI; this view model does not load image bytes.",
        "has_source_package_entry": has_entry,
    }


def make_workbench_card(
    card: dict[str, Any],
    *,
    tasks_by_id: dict[str, dict[str, Any]],
    visual_by_page: dict[str, dict[str, Any]],
    table_by_page: dict[str, dict[str, Any]],
    category_by_page: dict[str, dict[str, Any]],
    source_by_page: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    page_ids = card_page_ids(card)
    primary_page_id = page_ids[0] if page_ids else None
    task_ids = str_list(card.get("source_review_task_ids"), limit=200)
    tasks = [tasks_by_id[task_id] for task_id in task_ids if task_id in tasks_by_id]

    visual_summary = summarize_visual(visual_by_page.get(primary_page_id or ""))
    table_summary = summarize_table(table_by_page.get(primary_page_id or ""))
    category_summary = summarize_category(category_by_page.get(primary_page_id or ""))
    source_package_summary = summarize_source_package(source_by_page.get(primary_page_id or ""))
    page_preview = make_page_preview(primary_page_id or "", source_package_summary) if primary_page_id else {"available": False}

    allowed_decisions = task_allowed_decision_hints(card)
    card_type = str(card.get("card_type") or "review_card")
    card_id = stable_id("hrwb", card.get("triage_card_id"), task_ids, page_ids)
    review_packet = {
        "reason_summary": sanitize_text(card.get("reason_summary"), 2200),
        "recommended_action": sanitize_text(card.get("recommended_action"), 2200),
        "workbench_next_action": next_action_for_card(card),
        "source_review_task_ids": task_ids,
        "task_type_summaries": as_list(card.get("task_type_summaries"))[:30],
        "origin_summaries": as_list(card.get("origin_summaries"))[:30],
        "source_task_reasons": unique_sorted((t.get("reason") for t in tasks), limit=20),
        "source_task_actions": unique_sorted((t.get("recommended_action") for t in tasks), limit=20),
    }
    return {
        "workbench_card_id": card_id,
        "schema_version": SCHEMA_VERSION,
        "triage_card_id": card.get("triage_card_id"),
        "card_type": card_type,
        "priority": clamp_priority(card.get("priority")),
        "triage_score": card.get("triage_score"),
        "review_status": card.get("review_status") or "open",
        "group_kind": card.get("group_kind"),
        "group_value": card.get("group_value"),
        "primary_page_id": primary_page_id,
        "page_ids": page_ids,
        "page_count": len(page_ids),
        "community_ids": str_list(card.get("community_ids"), limit=50),
        "part_numbers": str_list(card.get("part_numbers"), limit=60),
        "citation_ids": str_list(card.get("citation_ids"), limit=60),
        "task_count": int(card.get("task_count") or len(task_ids)),
        "page_preview": page_preview,
        "visual_summary": visual_summary,
        "table_summary": table_summary,
        "category_summary": category_summary,
        "source_package_summary": source_package_summary,
        "review_packet": review_packet,
        "allowed_decisions": allowed_decisions,
        "decision_recorder_hint": {
            "script": "scripts/record_trace_net_human_review_decision_v1.py",
            "target_type": "triage_card",
            "target_id": card.get("triage_card_id"),
            "allowed_decision_types": ["approve", "reject", "needs_more_review"],
            "promotion_gate_required_after_approval": True,
        },
        "workbench_authority": AUTHORITY,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "final_answer_allowed": False,
        "raw_feedback_direct_to_llm": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "unsafe_workbench_card": False,
    }


def make_page_profiles(
    *,
    source_by_page: dict[str, dict[str, Any]],
    category_by_page: dict[str, dict[str, Any]],
    visual_by_page: dict[str, dict[str, Any]],
    table_by_page: dict[str, dict[str, Any]],
    workbench_cards: list[dict[str, Any]],
    triage_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    page_ids = set(source_by_page) | set(category_by_page) | set(visual_by_page) | set(table_by_page)
    for c in triage_cards:
        page_ids.update(card_page_ids(c))
    cards_by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in workbench_cards:
        for page_id in card.get("page_ids", []):
            cards_by_page[str(page_id)].append(card)
    profiles: list[dict[str, Any]] = []
    for page_id in sorted(page_ids):
        page_cards = sorted(cards_by_page.get(page_id, []), key=lambda c: (priority_sort_value(c.get("priority")), -float(c.get("triage_score") or 0)))
        visual = summarize_visual(visual_by_page.get(page_id))
        table = summarize_table(table_by_page.get(page_id))
        category = summarize_category(category_by_page.get(page_id))
        source = summarize_source_package(source_by_page.get(page_id))
        priorities = Counter(c.get("priority") for c in page_cards)
        profiles.append({
            "page_workbench_profile_id": stable_id("hrwb_page", page_id),
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "review_required": bool(page_cards),
            "review_card_count": len(page_cards),
            "review_task_count": sum(int(c.get("task_count") or 0) for c in page_cards),
            "highest_priority": page_cards[0].get("priority") if page_cards else "none",
            "priority_counts": dict(sorted(priorities.items())),
            "workbench_card_ids": [c.get("workbench_card_id") for c in page_cards],
            "triage_card_ids": [c.get("triage_card_id") for c in page_cards],
            "card_types": unique_sorted((c.get("card_type") for c in page_cards), limit=20),
            "part_numbers": unique_sorted((p for c in page_cards for p in c.get("part_numbers", [])), limit=80),
            "citation_ids": unique_sorted((cid for c in page_cards for cid in c.get("citation_ids", [])), limit=80),
            "page_preview": make_page_preview(page_id, source),
            "source_package_summary": source,
            "category_summary": category,
            "visual_summary": visual,
            "table_summary": table,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "source_truth_mutation_allowed": False,
            "final_answer_allowed": False,
        })
    return profiles


def compute_summary(
    *,
    triage_report: dict[str, Any],
    queue_report: dict[str, Any],
    workbench_cards: list[dict[str, Any]],
    page_profiles: list[dict[str, Any]],
    source_statuses: dict[str, str],
) -> dict[str, Any]:
    priority_counts = Counter(c.get("priority") for c in workbench_cards)
    card_type_counts = Counter(c.get("card_type") for c in workbench_cards)
    source_quality_statuses = dict(sorted(source_statuses.items()))
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "algorithm": "trace_net_human_review_workbench_view_model_builder_v1",
        "triage_card_count": len(triage_report.get("triage_cards", []) or []),
        "input_review_task_count": len(queue_report.get("review_tasks", []) or []),
        "workbench_card_count": len(workbench_cards),
        "page_workbench_profile_count": len(page_profiles),
        "page_scoped_workbench_card_count": len([c for c in workbench_cards if c.get("page_ids")]),
        "critical_workbench_card_count": priority_counts.get("critical", 0),
        "high_priority_workbench_card_count": priority_counts.get("high", 0) + priority_counts.get("critical", 0),
        "medium_priority_workbench_card_count": priority_counts.get("medium", 0),
        "low_priority_workbench_card_count": priority_counts.get("low", 0),
        "cards_with_page_ids_count": len([c for c in workbench_cards if c.get("page_ids")]),
        "cards_with_page_preview_count": len([c for c in workbench_cards if c.get("page_preview", {}).get("has_source_package_entry")]),
        "cards_with_visual_summary_count": len([c for c in workbench_cards if c.get("visual_summary", {}).get("available")]),
        "cards_with_table_summary_count": len([c for c in workbench_cards if c.get("table_summary", {}).get("available")]),
        "cards_with_category_summary_count": len([c for c in workbench_cards if c.get("category_summary", {}).get("available")]),
        "cards_with_source_package_summary_count": len([c for c in workbench_cards if c.get("source_package_summary", {}).get("available")]),
        "cards_with_recommended_actions_count": len([c for c in workbench_cards if c.get("review_packet", {}).get("recommended_action")]),
        "cards_with_allowed_decisions_count": len([c for c in workbench_cards if c.get("allowed_decisions")]),
        "pages_with_review_cards_count": len([p for p in page_profiles if p.get("review_card_count")]),
        "unsafe_workbench_card_count": len([c for c in workbench_cards if c.get("unsafe_workbench_card")]),
        "workbench_can_answer_directly_count": len([c for c in workbench_cards if c.get("can_answer_directly")]),
        "workbench_can_prove_claims_count": len([c for c in workbench_cards if c.get("can_prove_claims")]),
        "source_truth_mutation_allowed_count": len([c for c in workbench_cards if c.get("source_truth_mutation_allowed") or c.get("can_mutate_source_truth")]),
        "raw_feedback_direct_to_llm_count": len([c for c in workbench_cards if c.get("raw_feedback_direct_to_llm")]),
        "final_answer_allowed_count": len([c for c in workbench_cards if c.get("final_answer_allowed")]),
        "priority_counts": dict(sorted(priority_counts.items())),
        "card_type_counts": dict(sorted(card_type_counts.items())),
        "source_quality_statuses": source_quality_statuses,
        "source_triage_quality_status": source_quality_statuses.get("human_review_triage"),
        "source_queue_quality_status": source_quality_statuses.get("human_review_queue"),
    }


def compute_quality(
    report: dict[str, Any],
    *,
    require_page_count: int | None = None,
    min_workbench_cards: int = 1,
    min_page_profiles: int = 1,
    min_cards_with_page_ids: int = 1,
    min_high_priority_cards: int = 1,
    min_critical_cards: int = 0,
    require_source_triage_quality_pass: bool = False,
    require_source_queue_quality_pass: bool = False,
) -> dict[str, Any]:
    s = report.get("summary", {}) or {}
    checks: dict[str, bool] = {
        "min_workbench_cards": int(s.get("workbench_card_count") or 0) >= min_workbench_cards,
        "min_page_profiles": int(s.get("page_workbench_profile_count") or 0) >= min_page_profiles,
        "min_cards_with_page_ids": int(s.get("cards_with_page_ids_count") or 0) >= min_cards_with_page_ids,
        "min_high_priority_cards": int(s.get("high_priority_workbench_card_count") or 0) >= min_high_priority_cards,
        "min_critical_cards": int(s.get("critical_workbench_card_count") or 0) >= min_critical_cards,
        "cards_with_recommended_actions_all": int(s.get("cards_with_recommended_actions_count") or 0) == int(s.get("workbench_card_count") or 0),
        "cards_with_allowed_decisions_all": int(s.get("cards_with_allowed_decisions_count") or 0) == int(s.get("workbench_card_count") or 0),
        "unsafe_workbench_card_count_zero": int(s.get("unsafe_workbench_card_count") or 0) == 0,
        "workbench_can_answer_directly_count_zero": int(s.get("workbench_can_answer_directly_count") or 0) == 0,
        "workbench_can_prove_claims_count_zero": int(s.get("workbench_can_prove_claims_count") or 0) == 0,
        "source_truth_mutation_allowed_count_zero": int(s.get("source_truth_mutation_allowed_count") or 0) == 0,
        "raw_feedback_direct_to_llm_count_zero": int(s.get("raw_feedback_direct_to_llm_count") or 0) == 0,
        "final_answer_allowed_count_zero": int(s.get("final_answer_allowed_count") or 0) == 0,
    }
    if require_page_count is not None:
        checks["require_page_count"] = int(s.get("page_workbench_profile_count") or 0) == require_page_count
    if require_source_triage_quality_pass:
        checks["source_triage_quality_status_pass"] = str(s.get("source_triage_quality_status") or "").upper() == "PASS"
    if require_source_queue_quality_pass:
        checks["source_queue_quality_status_pass"] = str(s.get("source_queue_quality_status") or "").upper() == "PASS"
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "checks": checks,
        "summary": s,
        "generated_at": utc_now(),
    }


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# TRACE-Net Human Review Workbench View Model v1",
        "",
        f"**Status:** {report['status']}",
        f"**Quality:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "workbench_card_count",
        "page_workbench_profile_count",
        "critical_workbench_card_count",
        "high_priority_workbench_card_count",
        "cards_with_page_ids_count",
        "cards_with_visual_summary_count",
        "cards_with_table_summary_count",
        "cards_with_category_summary_count",
        "cards_with_source_package_summary_count",
        "unsafe_workbench_card_count",
        "workbench_can_answer_directly_count",
        "workbench_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {s.get(key)}")
    lines.extend(["", "## Top Workbench Cards", ""])
    lines.append("| Priority | Card type | Page/group | Tasks | Next action |")
    lines.append("|---|---|---|---:|---|")
    for card in report.get("workbench_cards", [])[:80]:
        group = card.get("primary_page_id") or card.get("group_value") or "-"
        action = get_nested(card, ["review_packet", "workbench_next_action"], "")
        lines.append(
            "| {priority} | {card_type} | {group} | {tasks} | {action} |".format(
                priority=card.get("priority"),
                card_type=str(card.get("card_type") or "").replace("|", "\\|"),
                group=str(group).replace("|", "\\|"),
                tasks=card.get("task_count"),
                action=sanitize_text(action, 160).replace("|", "\\|"),
            )
        )
    return "\n".join(lines) + "\n"


def render_html(markdown_text: str) -> str:
    return "<html><body><pre>" + html.escape(markdown_text) + "</pre></body></html>"


def build_human_review_workbench(
    *,
    human_review_triage_path: str | Path,
    human_review_queue_path: str | Path,
    callout_visual_part_verifier_path: str | Path | None = None,
    table_cell_normalizer_path: str | Path | None = None,
    category_aware_graph_ui_overlay_path: str | Path | None = None,
    dublin_core_source_package_extension_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    require_page_count: int | None = None,
    min_workbench_cards: int = 1,
    min_page_profiles: int = 1,
    min_cards_with_page_ids: int = 1,
    min_high_priority_cards: int = 1,
    min_critical_cards: int = 0,
    require_source_triage_quality_pass: bool = False,
    require_source_queue_quality_pass: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    triage = read_json(human_review_triage_path, {})
    queue = read_json(human_review_queue_path, {})
    callout = read_json(callout_visual_part_verifier_path, {})
    table = read_json(table_cell_normalizer_path, {})
    category_ui = read_json(category_aware_graph_ui_overlay_path, {})
    dublin_source = read_json(dublin_core_source_package_extension_path, {})

    triage_cards = load_records(triage, ("triage_cards", "cards"))
    review_tasks = load_records(queue, ("review_tasks", "tasks"))
    tasks_by_id = {str(t.get("review_task_id")): t for t in review_tasks if t.get("review_task_id")}
    visual_by_page = by_page(load_records(callout, ("records", "callout_records")))
    table_by_page = by_page(load_records(table, ("records", "table_records", "normalized_records")))

    category_page_cards = load_records(category_ui, ("page_category_profile_cards", "page_cards"))
    # Category-aware graph UI page cards usually store the page under properties.
    category_by_page: dict[str, dict[str, Any]] = {}
    for card in category_page_cards:
        props = card.get("properties") if isinstance(card.get("properties"), dict) else card
        page_id = props.get("page_id") or card.get("page_id")
        if page_id:
            category_by_page[str(page_id)] = card

    source_records = load_records(dublin_source, ("page_records", "pages"))
    source_by_page = by_page(source_records)

    workbench_cards = [
        make_workbench_card(
            card,
            tasks_by_id=tasks_by_id,
            visual_by_page=visual_by_page,
            table_by_page=table_by_page,
            category_by_page=category_by_page,
            source_by_page=source_by_page,
        )
        for card in triage_cards
    ]
    workbench_cards.sort(key=lambda c: (priority_sort_value(c.get("priority")), -float(c.get("triage_score") or 0), str(c.get("triage_card_id"))))

    page_profiles = make_page_profiles(
        source_by_page=source_by_page,
        category_by_page=category_by_page,
        visual_by_page=visual_by_page,
        table_by_page=table_by_page,
        workbench_cards=workbench_cards,
        triage_cards=triage_cards,
    )

    source_statuses = {
        "human_review_triage": source_quality(triage),
        "human_review_queue": source_quality(queue),
        "callout_visual_part_verifier": source_quality(callout) if callout else "",
        "table_cell_normalizer": source_quality(table) if table else "",
        "category_aware_graph_ui_overlay": source_quality(category_ui) if category_ui else "",
        "dublin_core_source_package_extension": source_quality(dublin_source) if dublin_source else "",
    }
    summary = compute_summary(
        triage_report=triage,
        queue_report=queue,
        workbench_cards=workbench_cards,
        page_profiles=page_profiles,
        source_statuses=source_statuses,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "HUMAN_REVIEW_WORKBENCH_BUILT",
        "generated_at": utc_now(),
        "source_paths": {
            "human_review_triage": str(human_review_triage_path),
            "human_review_queue": str(human_review_queue_path),
            "callout_visual_part_verifier": str(callout_visual_part_verifier_path) if callout_visual_part_verifier_path else None,
            "table_cell_normalizer": str(table_cell_normalizer_path) if table_cell_normalizer_path else None,
            "category_aware_graph_ui_overlay": str(category_aware_graph_ui_overlay_path) if category_aware_graph_ui_overlay_path else None,
            "dublin_core_source_package_extension": str(dublin_core_source_package_extension_path) if dublin_core_source_package_extension_path else None,
        },
        "summary": summary,
        "workbench_cards": workbench_cards,
        "page_workbench_profiles": page_profiles,
        "workbench_authority": AUTHORITY,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "final_answer_allowed": False,
    }
    quality = compute_quality(
        report,
        require_page_count=require_page_count,
        min_workbench_cards=min_workbench_cards,
        min_page_profiles=min_page_profiles,
        min_cards_with_page_ids=min_cards_with_page_ids,
        min_high_priority_cards=min_high_priority_cards,
        min_critical_cards=min_critical_cards,
        require_source_triage_quality_pass=require_source_triage_quality_pass,
        require_source_queue_quality_pass=require_source_queue_quality_pass,
    )
    report["quality_status"] = quality["status"]

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_human_review_workbench_v1.json"
    cards_path = out / "trace_net_human_review_workbench_v1_cards.jsonl"
    pages_path = out / "trace_net_human_review_workbench_v1_pages.jsonl"
    summary_path = out / "trace_net_human_review_workbench_v1_summary.json"
    quality_path = out / "trace_net_human_review_workbench_v1_quality.json"
    manifest_path = out / "trace_net_human_review_workbench_v1_manifest.json"
    md_path = out / "trace_net_human_review_workbench_v1.md"
    html_path = out / "trace_net_human_review_workbench_v1.html"

    report["report_path"] = str(report_path)
    report["cards_path"] = str(cards_path)
    report["pages_path"] = str(pages_path)
    report["quality_path"] = str(quality_path)
    quality["quality_path"] = str(quality_path)

    write_json(report_path, report)
    write_jsonl(cards_path, workbench_cards)
    write_jsonl(pages_path, page_profiles)
    write_json(summary_path, summary)
    write_json(quality_path, quality)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now(),
        "inputs": report["source_paths"],
        "outputs": {
            "report": str(report_path),
            "cards": str(cards_path),
            "pages": str(pages_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
        },
    })
    md = render_markdown(report)
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    return report


def quality_report(
    *,
    report_path: str | Path,
    require_page_count: int | None = None,
    min_workbench_cards: int = 1,
    min_page_profiles: int = 1,
    min_cards_with_page_ids: int = 1,
    min_high_priority_cards: int = 1,
    min_critical_cards: int = 0,
    require_source_triage_quality_pass: bool = False,
    require_source_queue_quality_pass: bool = False,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path, {})
    quality = compute_quality(
        report,
        require_page_count=require_page_count,
        min_workbench_cards=min_workbench_cards,
        min_page_profiles=min_page_profiles,
        min_cards_with_page_ids=min_cards_with_page_ids,
        min_high_priority_cards=min_high_priority_cards,
        min_critical_cards=min_critical_cards,
        require_source_triage_quality_pass=require_source_triage_quality_pass,
        require_source_queue_quality_pass=require_source_queue_quality_pass,
    )
    if write_json_report:
        quality_path = Path(report_path).with_name("trace_net_human_review_workbench_v1_quality.json")
        write_json(quality_path, quality)
        quality["quality_path"] = str(quality_path)
    return quality


def print_build_summary(report: dict[str, Any]) -> None:
    s = report["summary"]
    print("TRACE-Net Human Review Workbench View Model v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "workbench_card_count",
        "page_workbench_profile_count",
        "critical_workbench_card_count",
        "high_priority_workbench_card_count",
        "cards_with_page_ids_count",
        "cards_with_allowed_decisions_count",
        "unsafe_workbench_card_count",
        "workbench_can_answer_directly_count",
        "workbench_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" cards_path: {report.get('cards_path')}")
    print(f" pages_path: {report.get('pages_path')}")
    print(f" quality_path: {report.get('quality_path')}")


def print_quality_summary(quality: dict[str, Any]) -> None:
    s = quality.get("summary", {})
    print("TRACE-Net Human Review Workbench View Model v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "workbench_card_count",
        "page_workbench_profile_count",
        "critical_workbench_card_count",
        "high_priority_workbench_card_count",
        "unsafe_workbench_card_count",
        "workbench_can_answer_directly_count",
        "workbench_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Human Review Workbench View Model v1")
    parser.add_argument("--human-review-triage", required=True)
    parser.add_argument("--human-review-queue", required=True)
    parser.add_argument("--callout-visual-part-verifier")
    parser.add_argument("--table-cell-normalizer")
    parser.add_argument("--category-aware-graph-ui-overlay")
    parser.add_argument("--dublin-core-source-package-extension")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-workbench-cards", type=int, default=1)
    parser.add_argument("--min-page-profiles", type=int, default=1)
    parser.add_argument("--min-cards-with-page-ids", type=int, default=1)
    parser.add_argument("--min-high-priority-cards", type=int, default=1)
    parser.add_argument("--min-critical-cards", type=int, default=0)
    parser.add_argument("--require-source-triage-quality-pass", action="store_true")
    parser.add_argument("--require-source-queue-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_human_review_workbench(
        human_review_triage_path=args.human_review_triage,
        human_review_queue_path=args.human_review_queue,
        callout_visual_part_verifier_path=args.callout_visual_part_verifier,
        table_cell_normalizer_path=args.table_cell_normalizer,
        category_aware_graph_ui_overlay_path=args.category_aware_graph_ui_overlay,
        dublin_core_source_package_extension_path=args.dublin_core_source_package_extension,
        output_dir=args.output_dir,
        require_page_count=args.require_page_count,
        min_workbench_cards=args.min_workbench_cards,
        min_page_profiles=args.min_page_profiles,
        min_cards_with_page_ids=args.min_cards_with_page_ids,
        min_high_priority_cards=args.min_high_priority_cards,
        min_critical_cards=args.min_critical_cards,
        require_source_triage_quality_pass=args.require_source_triage_quality_pass,
        require_source_queue_quality_pass=args.require_source_queue_quality_pass,
        write_quality=args.quality,
    )
    print_build_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
