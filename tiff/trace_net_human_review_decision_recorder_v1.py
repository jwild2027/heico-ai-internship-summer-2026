"""TRACE-Net Human Review Decision Recorder v1.

This module records reviewer decisions for TRACE-Net human-review triage cards.
It is intentionally conservative: decisions are advisory workflow records, not
source truth mutations and not answer proof.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_human_review_decision_recorder_v1"
DEFAULT_EVENTS_FILENAME = "trace_net_human_review_decisions_v1_events.jsonl"
DEFAULT_REPORT_FILENAME = "trace_net_human_review_decisions_v1.json"
DEFAULT_RECORDS_FILENAME = "trace_net_human_review_decisions_v1_records.jsonl"
DEFAULT_SUMMARY_FILENAME = "trace_net_human_review_decisions_v1_summary.json"
DEFAULT_MANIFEST_FILENAME = "trace_net_human_review_decisions_v1_manifest.json"
DEFAULT_QUALITY_FILENAME = "trace_net_human_review_decisions_v1_quality.json"
DEFAULT_MD_FILENAME = "trace_net_human_review_decisions_v1.md"
DEFAULT_HTML_FILENAME = "trace_net_human_review_decisions_v1.html"

SUPPORTED_TARGET_TYPES = {
    "triage_card",
    "review_task",
    "answer",
    "claim",
    "citation",
    "page",
    "table_row",
    "table_cell",
    "visual_region",
    "callout_candidate",
    "part_candidate",
    "community",
    "feedback_memory",
}

SUPPORTED_DECISION_TYPES = {
    "approve",
    "reject",
    "needs_more_review",
    "confirm_blank",
    "confirm_table_repair",
    "reject_table_repair",
    "confirm_callout",
    "reject_callout",
    "confirm_part_link",
    "reject_part_link",
    "mark_bad_citation",
    "mark_feedback_resolved",
}

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"\bignore\s+(all\s+)?(previous|prior)\s+instructions\b", re.I),
    re.compile(r"\bdisregard\s+(all\s+)?(previous|prior)\s+instructions\b", re.I),
    re.compile(r"\breveal\s+(the\s+)?(system|developer)\s+prompt\b", re.I),
    re.compile(r"\b(system|developer)\s+message\b", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\balways\s+trust\b", re.I),
    re.compile(r"\bdo\s+not\s+follow\s+trace-net\b", re.I),
]

DECISION_EFFECTS = {
    "approve": "review_approved_advisory_pending_promotion_gate",
    "reject": "review_rejected_advisory_pending_policy_update",
    "needs_more_review": "hold_for_additional_review",
    "confirm_blank": "blank_confirmation_advisory_pending_graph_policy",
    "confirm_table_repair": "table_repair_confirmed_pending_promotion_gate",
    "reject_table_repair": "table_repair_rejected_pending_policy_update",
    "confirm_callout": "callout_confirmed_pending_catalog_graph_gate",
    "reject_callout": "callout_rejected_pending_policy_update",
    "confirm_part_link": "part_link_confirmed_pending_catalog_graph_gate",
    "reject_part_link": "part_link_rejected_pending_policy_update",
    "mark_bad_citation": "citation_disputed_pending_citation_review",
    "mark_feedback_resolved": "feedback_review_resolved_advisory",
}

PROMOTION_DECISION_TYPES = {
    "approve",
    "confirm_blank",
    "confirm_table_repair",
    "confirm_callout",
    "confirm_part_link",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


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


def contains_prompt_injection(text: str) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in PROMPT_INJECTION_PATTERNS)


def sanitize_comment(text: str | None) -> tuple[str, bool]:
    raw = (text or "").strip()
    flagged = contains_prompt_injection(raw)
    compact = re.sub(r"\s+", " ", raw)
    compact = compact[:1000]
    if flagged:
        return "[redacted: possible instruction-manipulation feedback requires review]", True
    return compact, False


def load_triage_cards(triage_report_path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not triage_report_path:
        return {}
    path = Path(triage_report_path)
    if not path.exists():
        return {}
    payload = read_json(path)
    cards = payload.get("triage_cards") or payload.get("cards") or []
    return {str(card.get("triage_card_id") or card.get("card_id") or card.get("target_id")): card for card in cards}


def default_events_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / DEFAULT_EVENTS_FILENAME


def infer_target_from_triage_card(card: dict[str, Any]) -> tuple[str, str]:
    target_type = str(card.get("target_type") or "triage_card")
    target_id = str(card.get("target_id") or card.get("triage_card_id") or "")
    if not target_id:
        target_id = str(card.get("triage_card_id") or card.get("card_id") or "unknown_target")
    return target_type, target_id


def create_review_decision_event(
    *,
    decision_type: str,
    target_type: str | None = None,
    target_id: str | None = None,
    actor_id: str = "local_reviewer",
    actor_role: str = "reviewer",
    triage_card_id: str | None = None,
    source_review_task_ids: Iterable[str] | None = None,
    page_ids: Iterable[str] | None = None,
    citation_ids: Iterable[str] | None = None,
    community_ids: Iterable[str] | None = None,
    part_numbers: Iterable[str] | None = None,
    comment_text: str | None = None,
    triage_cards_by_id: dict[str, dict[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    triage_cards_by_id = triage_cards_by_id or {}
    triage_card = triage_cards_by_id.get(str(triage_card_id)) if triage_card_id else None

    if triage_card:
        if not target_type or not target_id:
            inferred_type, inferred_id = infer_target_from_triage_card(triage_card)
            target_type = target_type or inferred_type
            target_id = target_id or inferred_id
        page_ids = unique_nonempty([*(page_ids or []), *as_list(triage_card.get("page_ids")), triage_card.get("page_id")])
        citation_ids = unique_nonempty([*(citation_ids or []), *as_list(triage_card.get("citation_ids"))])
        community_ids = unique_nonempty([*(community_ids or []), *as_list(triage_card.get("community_ids")), triage_card.get("community_id")])
        part_numbers = unique_nonempty([*(part_numbers or []), *as_list(triage_card.get("part_numbers")), triage_card.get("part_number")])
        source_review_task_ids = unique_nonempty([
            *(source_review_task_ids or []),
            *as_list(triage_card.get("source_review_task_ids")),
            *as_list(triage_card.get("review_task_ids")),
        ])

    page_ids = unique_nonempty(page_ids or [])
    citation_ids = unique_nonempty(citation_ids or [])
    community_ids = unique_nonempty(community_ids or [])
    part_numbers = unique_nonempty(part_numbers or [])
    source_review_task_ids = unique_nonempty(source_review_task_ids or [])

    decision_type = str(decision_type).strip()
    target_type = str(target_type or "").strip()
    target_id = str(target_id or "").strip()
    actor_id = str(actor_id or "").strip()
    actor_role = str(actor_role or "reviewer").strip()
    created_at = created_at or utc_now_iso()
    comment_sanitized, prompt_injection_flagged = sanitize_comment(comment_text)

    seed = "|".join([
        created_at,
        actor_id,
        actor_role,
        decision_type,
        target_type,
        target_id,
        str(triage_card_id or ""),
        comment_sanitized,
    ])
    decision_id = f"hrdec__{stable_hash(seed, 16)}"
    actor_hash = f"actor__{stable_hash(actor_id or 'missing_actor', 12)}"

    invalid_decision_type = decision_type not in SUPPORTED_DECISION_TYPES
    invalid_target_type = target_type not in SUPPORTED_TARGET_TYPES
    decision_effect = DECISION_EFFECTS.get(decision_type, "unsupported_decision_type_review_required")

    summary_parts = [
        f"Reviewer decision '{decision_type}' recorded for {target_type or 'missing_target_type'}:{target_id or 'missing_target_id'}."
    ]
    if page_ids:
        summary_parts.append(f"Pages: {', '.join(page_ids[:8])}.")
    if citation_ids:
        summary_parts.append(f"Citations: {len(citation_ids)} linked.")
    if community_ids:
        summary_parts.append(f"Communities: {', '.join(community_ids[:5])}.")
    if part_numbers:
        summary_parts.append(f"Parts: {', '.join(part_numbers[:5])}.")
    if prompt_injection_flagged:
        summary_parts.append("Comment was redacted because it looked like instruction-manipulation feedback.")
    elif comment_sanitized:
        summary_parts.append(f"Comment: {comment_sanitized}")

    record = {
        "schema_version": SCHEMA_VERSION,
        "review_decision_id": decision_id,
        "created_at": created_at,
        "actor_id_hash": actor_hash,
        "actor_role": actor_role,
        "reviewer_present": bool(actor_id),
        "triage_card_id": triage_card_id or "",
        "source_review_task_ids": source_review_task_ids,
        "decision_type": decision_type,
        "decision_effect": decision_effect,
        "target_type": target_type,
        "target_id": target_id,
        "page_ids": page_ids,
        "citation_ids": citation_ids,
        "community_ids": community_ids,
        "part_numbers": part_numbers,
        "comment_text_redacted": comment_sanitized,
        "comment_was_redacted": prompt_injection_flagged,
        "prompt_injection_flagged": prompt_injection_flagged,
        "sanitized_decision_summary": " ".join(summary_parts),
        "authority": "human_review_decision_advisory_only",
        "record_type": "human_review_decision",
        "safety_bucket": "human_review_decision_advisory",
        "review_reference_allowed": not prompt_injection_flagged,
        "llm_reference_allowed": not prompt_injection_flagged,
        "raw_feedback_direct_to_llm": False,
        "retrieval_advisory_allowed": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "final_answer_allowed": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "requires_promotion_gate": decision_type in PROMOTION_DECISION_TYPES,
        "promotion_candidate": decision_type in PROMOTION_DECISION_TYPES,
        "promotion_status": "pending_promotion_gate" if decision_type in PROMOTION_DECISION_TYPES else "not_a_promotion_candidate",
        "invalid_decision_type": invalid_decision_type,
        "invalid_target_type": invalid_target_type,
        "missing_actor": not bool(actor_id),
        "missing_target": not bool(target_type and target_id),
        "missing_timestamp": not bool(created_at),
        "unsafe_decision_reasons": [],
    }

    if invalid_decision_type:
        record["unsafe_decision_reasons"].append("invalid_decision_type")
    if invalid_target_type:
        record["unsafe_decision_reasons"].append("invalid_target_type")
    if record["missing_actor"]:
        record["unsafe_decision_reasons"].append("missing_actor")
    if record["missing_target"]:
        record["unsafe_decision_reasons"].append("missing_target")
    if record["missing_timestamp"]:
        record["unsafe_decision_reasons"].append("missing_timestamp")

    record["unsafe_decision"] = bool(record["unsafe_decision_reasons"])
    return record


def record_review_decision(
    *,
    decisions_path: str | Path,
    decision_type: str,
    target_type: str | None = None,
    target_id: str | None = None,
    actor_id: str = "local_reviewer",
    actor_role: str = "reviewer",
    triage_card_id: str | None = None,
    source_review_task_ids: Iterable[str] | None = None,
    page_ids: Iterable[str] | None = None,
    citation_ids: Iterable[str] | None = None,
    community_ids: Iterable[str] | None = None,
    part_numbers: Iterable[str] | None = None,
    comment_text: str | None = None,
    triage_report_path: str | Path | None = None,
) -> dict[str, Any]:
    cards_by_id = load_triage_cards(triage_report_path)
    record = create_review_decision_event(
        decision_type=decision_type,
        target_type=target_type,
        target_id=target_id,
        actor_id=actor_id,
        actor_role=actor_role,
        triage_card_id=triage_card_id,
        source_review_task_ids=source_review_task_ids,
        page_ids=page_ids,
        citation_ids=citation_ids,
        community_ids=community_ids,
        part_numbers=part_numbers,
        comment_text=comment_text,
        triage_cards_by_id=cards_by_id,
    )
    append_jsonl(decisions_path, record)
    return record


def index_triage_cards(triage_report_path: str | Path | None) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not triage_report_path or not Path(triage_report_path).exists():
        return {}, {}
    payload = read_json(triage_report_path)
    return payload, load_triage_cards(triage_report_path)


def summarize_records(records: list[dict[str, Any]], triage_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    triage_payload = triage_payload or {}
    decision_count = len(records)
    decision_type_counts = Counter(str(r.get("decision_type") or "") for r in records)
    target_type_counts = Counter(str(r.get("target_type") or "") for r in records)
    actor_role_counts = Counter(str(r.get("actor_role") or "") for r in records)

    affected_pages = sorted({page for r in records for page in as_list(r.get("page_ids")) if page})
    affected_citations = sorted({c for r in records for c in as_list(r.get("citation_ids")) if c})
    affected_communities = sorted({c for r in records for c in as_list(r.get("community_ids")) if c})
    affected_parts = sorted({p for r in records for p in as_list(r.get("part_numbers")) if p})

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "UNKNOWN",
        "review_decision_count": decision_count,
        "decision_type_counts": dict(decision_type_counts),
        "target_type_counts": dict(target_type_counts),
        "actor_role_counts": dict(actor_role_counts),
        "approved_decision_count": sum(1 for r in records if r.get("decision_type") == "approve"),
        "rejected_decision_count": sum(1 for r in records if r.get("decision_type") == "reject"),
        "needs_more_review_decision_count": sum(1 for r in records if r.get("decision_type") == "needs_more_review"),
        "promotion_candidate_count": sum(1 for r in records if r.get("promotion_candidate")),
        "prompt_injection_flagged_count": sum(1 for r in records if r.get("prompt_injection_flagged")),
        "review_reference_allowed_count": sum(1 for r in records if r.get("review_reference_allowed")),
        "llm_reference_allowed_count": sum(1 for r in records if r.get("llm_reference_allowed")),
        "raw_feedback_direct_to_llm_count": sum(1 for r in records if r.get("raw_feedback_direct_to_llm")),
        "retrieval_advisory_allowed_count": sum(1 for r in records if r.get("retrieval_advisory_allowed")),
        "decision_can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "decision_can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "decision_can_mutate_source_truth_count": sum(1 for r in records if r.get("can_mutate_source_truth")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "source_truth_mutations_performed": sum(int(r.get("source_truth_mutations_performed") or 0) for r in records),
        "final_answer_allowed_count": sum(1 for r in records if r.get("final_answer_allowed")),
        "invalid_decision_type_count": sum(1 for r in records if r.get("invalid_decision_type")),
        "invalid_target_type_count": sum(1 for r in records if r.get("invalid_target_type")),
        "missing_actor_count": sum(1 for r in records if r.get("missing_actor")),
        "missing_target_count": sum(1 for r in records if r.get("missing_target")),
        "missing_timestamp_count": sum(1 for r in records if r.get("missing_timestamp")),
        "unsafe_decision_count": sum(1 for r in records if r.get("unsafe_decision")),
        "affected_page_count": len(affected_pages),
        "affected_citation_count": len(affected_citations),
        "affected_community_count": len(affected_communities),
        "affected_part_number_count": len(affected_parts),
        "affected_page_ids": affected_pages[:1000],
        "affected_citation_ids": affected_citations[:1000],
        "affected_community_ids": affected_communities[:1000],
        "affected_part_numbers": affected_parts[:1000],
        "source_triage_quality_status": str(triage_payload.get("quality_status") or triage_payload.get("status") or ""),
        "source_triage_card_count": int((triage_payload.get("summary") or {}).get("triage_card_count") or len(triage_payload.get("triage_cards") or [])) if triage_payload else 0,
    }
    return summary


def quality_report(
    report_or_records: dict[str, Any] | list[dict[str, Any]],
    *,
    min_review_decisions: int = 1,
    require_source_triage_quality_pass: bool = False,
) -> dict[str, Any]:
    if isinstance(report_or_records, dict) and "decision_records" in report_or_records:
        records = report_or_records.get("decision_records") or []
        summary = dict(report_or_records.get("summary") or summarize_records(records))
    elif isinstance(report_or_records, list):
        records = report_or_records
        summary = summarize_records(records)
    else:
        records = []
        summary = dict(report_or_records.get("summary") or {}) if isinstance(report_or_records, dict) else {}

    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, value: Any, expected: Any, severity: str = "critical") -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected, "severity": severity})

    add_check("min_review_decisions", summary.get("review_decision_count", 0) >= min_review_decisions, summary.get("review_decision_count", 0), f">= {min_review_decisions}")
    add_check("invalid_decision_type_count_zero", summary.get("invalid_decision_type_count", 0) == 0, summary.get("invalid_decision_type_count", 0), 0)
    add_check("invalid_target_type_count_zero", summary.get("invalid_target_type_count", 0) == 0, summary.get("invalid_target_type_count", 0), 0)
    add_check("missing_actor_count_zero", summary.get("missing_actor_count", 0) == 0, summary.get("missing_actor_count", 0), 0)
    add_check("missing_target_count_zero", summary.get("missing_target_count", 0) == 0, summary.get("missing_target_count", 0), 0)
    add_check("missing_timestamp_count_zero", summary.get("missing_timestamp_count", 0) == 0, summary.get("missing_timestamp_count", 0), 0)
    add_check("unsafe_decision_count_zero", summary.get("unsafe_decision_count", 0) == 0, summary.get("unsafe_decision_count", 0), 0)
    add_check("raw_feedback_direct_to_llm_count_zero", summary.get("raw_feedback_direct_to_llm_count", 0) == 0, summary.get("raw_feedback_direct_to_llm_count", 0), 0)
    add_check("decision_can_answer_directly_count_zero", summary.get("decision_can_answer_directly_count", 0) == 0, summary.get("decision_can_answer_directly_count", 0), 0)
    add_check("decision_can_prove_claims_count_zero", summary.get("decision_can_prove_claims_count", 0) == 0, summary.get("decision_can_prove_claims_count", 0), 0)
    add_check("decision_can_mutate_source_truth_count_zero", summary.get("decision_can_mutate_source_truth_count", 0) == 0, summary.get("decision_can_mutate_source_truth_count", 0), 0)
    add_check("source_truth_mutation_allowed_count_zero", summary.get("source_truth_mutation_allowed_count", 0) == 0, summary.get("source_truth_mutation_allowed_count", 0), 0)
    add_check("source_truth_mutations_performed_zero", summary.get("source_truth_mutations_performed", 0) == 0, summary.get("source_truth_mutations_performed", 0), 0)
    add_check("final_answer_allowed_count_zero", summary.get("final_answer_allowed_count", 0) == 0, summary.get("final_answer_allowed_count", 0), 0)

    if require_source_triage_quality_pass:
        status = str(summary.get("source_triage_quality_status") or "").upper()
        add_check("source_triage_quality_pass", status == "PASS", status, "PASS")

    status = "PASS" if all(c["passed"] or c["severity"] != "critical" for c in checks) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "summary": summary,
        "checks": checks,
    }


def build_review_decision_report(
    *,
    decisions_path: str | Path,
    output_dir: str | Path,
    triage_report_path: str | Path | None = None,
    min_review_decisions: int = 1,
    require_source_triage_quality_pass: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = read_jsonl(decisions_path)
    triage_payload, _ = index_triage_cards(triage_report_path)
    summary = summarize_records(records, triage_payload)
    quality = quality_report(
        {"decision_records": records, "summary": summary},
        min_review_decisions=min_review_decisions,
        require_source_triage_quality_pass=require_source_triage_quality_pass,
    )
    summary["status"] = quality["status"]

    report_path = output_dir / DEFAULT_REPORT_FILENAME
    records_path = output_dir / DEFAULT_RECORDS_FILENAME
    summary_path = output_dir / DEFAULT_SUMMARY_FILENAME
    manifest_path = output_dir / DEFAULT_MANIFEST_FILENAME
    quality_path = output_dir / DEFAULT_QUALITY_FILENAME
    md_path = output_dir / DEFAULT_MD_FILENAME
    html_path = output_dir / DEFAULT_HTML_FILENAME

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "HUMAN_REVIEW_DECISIONS_BUILT",
        "quality_status": quality["status"],
        "decisions_path": str(decisions_path),
        "source_triage_report_path": str(triage_report_path or ""),
        "summary": summary,
        "decision_records": records,
        "quality": quality,
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
    }

    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now_iso(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_paths": {
            "decisions_path": str(decisions_path),
            "triage_report_path": str(triage_report_path or ""),
        },
    }

    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, quality)
    write_markdown(md_path, report)
    write_html(html_path, report)
    return report


def write_markdown(path: str | Path, report: dict[str, Any]) -> None:
    summary = report.get("summary") or {}
    rows = [
        "# TRACE-Net Human Review Decision Recorder v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "review_decision_count",
        "approved_decision_count",
        "rejected_decision_count",
        "needs_more_review_decision_count",
        "promotion_candidate_count",
        "prompt_injection_flagged_count",
        "raw_feedback_direct_to_llm_count",
        "decision_can_answer_directly_count",
        "decision_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "unsafe_decision_count",
        "affected_page_count",
        "affected_community_count",
    ]:
        rows.append(f"- {key}: {summary.get(key, 0)}")
    rows.extend(["", "## Decisions", ""])
    for record in (report.get("decision_records") or [])[:50]:
        rows.append(f"- **{record.get('decision_type')}** `{record.get('target_type')}:{record.get('target_id')}` - {record.get('sanitized_decision_summary')}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_html(path: str | Path, report: dict[str, Any]) -> None:
    md = []
    md.append("<html><head><meta charset='utf-8'><title>TRACE-Net Human Review Decisions</title></head><body>")
    md.append("<h1>TRACE-Net Human Review Decision Recorder v1</h1>")
    md.append(f"<p><strong>Status:</strong> {html.escape(str(report.get('status')))}</p>")
    md.append(f"<p><strong>Quality:</strong> {html.escape(str(report.get('quality_status')))}</p>")
    md.append("<h2>Summary</h2><ul>")
    for key, value in (report.get("summary") or {}).items():
        if isinstance(value, (str, int, float, bool)):
            md.append(f"<li><strong>{html.escape(str(key))}:</strong> {html.escape(str(value))}</li>")
    md.append("</ul><h2>Decisions</h2><ul>")
    for record in (report.get("decision_records") or [])[:100]:
        md.append("<li>" + html.escape(f"{record.get('decision_type')} {record.get('target_type')}:{record.get('target_id')} - {record.get('sanitized_decision_summary')}") + "</li>")
    md.append("</ul></body></html>")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(md), encoding="utf-8")


def print_record_summary(record: dict[str, Any]) -> None:
    print("TRACE-Net human review decision v1")
    print(" Status: RECORDED")
    print(f" review_decision_id: {record.get('review_decision_id')}")
    print(f" decision_type: {record.get('decision_type')}")
    print(f" target_type: {record.get('target_type')}")
    print(f" target_id: {record.get('target_id')}")
    print(f" prompt_injection_flagged: {record.get('prompt_injection_flagged')}")
    print(f" can_answer_directly: {record.get('can_answer_directly')}")
    print(f" can_prove_claims: {record.get('can_prove_claims')}")
    print(f" can_mutate_source_truth: {record.get('can_mutate_source_truth')}")


def print_report_summary(report: dict[str, Any]) -> None:
    summary = report.get("summary") or {}
    print("TRACE-Net human review decisions v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "review_decision_count",
        "approved_decision_count",
        "rejected_decision_count",
        "needs_more_review_decision_count",
        "promotion_candidate_count",
        "prompt_injection_flagged_count",
        "raw_feedback_direct_to_llm_count",
        "decision_can_answer_directly_count",
        "decision_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "unsafe_decision_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" records_path: {report.get('records_path')}")
    print(f" quality_path: {report.get('quality_path')}")


def record_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record a TRACE-Net human review decision v1")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/human_review_decisions")
    parser.add_argument("--decisions-path")
    parser.add_argument("--triage-report")
    parser.add_argument("--triage-card-id")
    parser.add_argument("--decision-type", required=True, choices=sorted(SUPPORTED_DECISION_TYPES))
    parser.add_argument("--target-type", choices=sorted(SUPPORTED_TARGET_TYPES))
    parser.add_argument("--target-id")
    parser.add_argument("--actor-id", default="local_reviewer")
    parser.add_argument("--actor-role", default="reviewer")
    parser.add_argument("--source-review-task-id", action="append", default=[])
    parser.add_argument("--page-id", action="append", default=[])
    parser.add_argument("--citation-id", action="append", default=[])
    parser.add_argument("--community-id", action="append", default=[])
    parser.add_argument("--part-number", action="append", default=[])
    parser.add_argument("--comment", default="")
    args = parser.parse_args(argv)

    decisions_path = Path(args.decisions_path) if args.decisions_path else default_events_path(args.output_dir)
    record = record_review_decision(
        decisions_path=decisions_path,
        decision_type=args.decision_type,
        target_type=args.target_type,
        target_id=args.target_id,
        actor_id=args.actor_id,
        actor_role=args.actor_role,
        triage_card_id=args.triage_card_id,
        source_review_task_ids=args.source_review_task_id,
        page_ids=args.page_id,
        citation_ids=args.citation_id,
        community_ids=args.community_id,
        part_numbers=args.part_number,
        comment_text=args.comment,
        triage_report_path=args.triage_report,
    )
    print_record_summary(record)
    print(f" decisions_path: {decisions_path}")
    return 0 if not record.get("unsafe_decision") else 2


def build_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net human review decision report v1")
    parser.add_argument("--decisions-path", default="local_data/organization/trace_net/human_review_decisions/trace_net_human_review_decisions_v1_events.jsonl")
    parser.add_argument("--triage-report", default="local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/human_review_decisions")
    parser.add_argument("--min-review-decisions", type=int, default=1)
    parser.add_argument("--require-source-triage-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    report = build_review_decision_report(
        decisions_path=args.decisions_path,
        triage_report_path=args.triage_report,
        output_dir=args.output_dir,
        min_review_decisions=args.min_review_decisions,
        require_source_triage_quality_pass=args.require_source_triage_quality_pass,
        write_quality=args.quality,
    )
    print_report_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 2


def check_quality_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net human review decisions quality v1")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-review-decisions", type=int, default=1)
    parser.add_argument("--require-source-triage-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    report = read_json(args.report_path)
    quality = quality_report(
        report,
        min_review_decisions=args.min_review_decisions,
        require_source_triage_quality_pass=args.require_source_triage_quality_pass,
    )
    if args.write_json:
        quality_path = Path(args.report_path).with_name(DEFAULT_QUALITY_FILENAME)
        write_json(quality_path, quality)
    print("TRACE-Net human review decisions v1 quality")
    print(f" Status: {quality.get('status')}")
    summary = quality.get("summary") or {}
    for key in [
        "review_decision_count",
        "invalid_decision_type_count",
        "missing_actor_count",
        "missing_target_count",
        "unsafe_decision_count",
        "raw_feedback_direct_to_llm_count",
        "decision_can_answer_directly_count",
        "decision_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    if args.write_json:
        print(f" quality_path: {Path(args.report_path).with_name(DEFAULT_QUALITY_FILENAME)}")
    return 0 if quality.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(build_main())
