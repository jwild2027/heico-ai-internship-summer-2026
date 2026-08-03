"""TRACE-Net Human Review Queue Triage / Dedup v1.

This module turns the raw human-review task queue into reviewer-friendly triage
cards. It groups overlapping tasks by page/community/target, preserves critical
items, and keeps the same TRACE-Net safety contract: review cards are advisory
only and cannot answer, prove claims, mutate source truth, or override trust.
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

SCHEMA_VERSION = "trace_net_human_review_triage_v1"
AUTHORITY = "human_review_triage_advisory_only"
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
PRIORITY_SCORE = {"critical": 100, "high": 75, "medium": 40, "low": 10}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if path is None:
        return default
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def stable_id(prefix: str, *parts: Any) -> str:
    text = "||".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


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


def string_list(value: Any) -> list[str]:
    return [str(item) for item in as_list(value) if item is not None and str(item) != ""]


def sanitize_text(text: Any, max_chars: int = 1400) -> str:
    if text is None:
        return ""
    value = str(text).replace("\r", " ").replace("\n", " ")
    while "  " in value:
        value = value.replace("  ", " ")
    return value.strip()[:max_chars]


def clamp_priority(priority: Any) -> str:
    value = str(priority or "medium").lower()
    return value if value in PRIORITY_ORDER else "medium"


def highest_priority(priorities: Iterable[str]) -> str:
    values = [clamp_priority(p) for p in priorities]
    if not values:
        return "medium"
    return sorted(values, key=lambda p: PRIORITY_ORDER[p])[0]


def priority_sort_value(priority: str) -> int:
    return PRIORITY_ORDER.get(clamp_priority(priority), 9)


def task_page_id(task: dict[str, Any]) -> str | None:
    value = task.get("page_id")
    if value:
        return str(value)
    page_ids = task.get("page_ids") or task.get("source_page_ids")
    if isinstance(page_ids, list) and page_ids:
        return str(page_ids[0])
    return None


def group_key_for_task(task: dict[str, Any]) -> tuple[str, str]:
    """Return a stable grouping key.

    Critical feedback/security tasks stay target-scoped so they are not hidden in a
    giant page card. Page-scoped extraction/review tasks are grouped by page.
    Communities are grouped by community ID. Remaining tasks are target-scoped.
    """
    priority = clamp_priority(task.get("priority"))
    task_type = str(task.get("task_type") or "review_task")
    origin = str(task.get("origin_category") or "review")
    target_type = str(task.get("target_type") or "artifact")
    target_id = str(task.get("target_id") or task.get("review_task_id") or "target")
    page_id = task_page_id(task)
    community_ids = string_list(task.get("community_ids"))

    if priority == "critical":
        return ("critical", f"{origin}:{task_type}:{target_type}:{target_id}")
    if target_type == "community" and (target_id or community_ids):
        return ("community", target_id or community_ids[0])
    if page_id:
        return ("page", page_id)
    if community_ids:
        return ("community", community_ids[0])
    return (target_type, target_id)


def unique_sorted(values: Iterable[Any], *, limit: int | None = None) -> list[str]:
    clean = sorted({str(v) for v in values if v is not None and str(v) != ""})
    if limit is not None:
        return clean[:limit]
    return clean


def summarize_task_types(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(t.get("task_type") or "review_task") for t in tasks)
    return [
        {"task_type": task_type, "count": count}
        for task_type, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def summarize_origins(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(t.get("origin_category") or "review") for t in tasks)
    return [
        {"origin_category": origin, "count": count}
        for origin, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def card_type_for_group(kind: str, tasks: list[dict[str, Any]]) -> str:
    if kind == "critical":
        return "critical_review_card"
    if kind == "community":
        return "community_review_card"
    if kind == "page":
        task_types = {str(t.get("task_type") or "") for t in tasks}
        if any("visual" in t or "callout" in t for t in task_types):
            if any("table" in t for t in task_types):
                return "page_table_visual_review_card"
            return "page_visual_review_card"
        if any("table" in t for t in task_types):
            return "page_table_review_card"
        if any("blank" in t for t in task_types):
            return "page_blank_confirmation_card"
        return "page_review_card"
    return "target_review_card"


def recommended_action_for_card(tasks: list[dict[str, Any]], card_type: str) -> str:
    actions = unique_sorted([t.get("recommended_action") for t in tasks], limit=5)
    if card_type == "critical_review_card":
        prefix = "Resolve this critical review item before using the affected signal in retrieval or answer workflows."
    elif "visual" in card_type or "callout" in card_type:
        prefix = "Verify visual/callout/part candidates against OCR, table rows, catalog, graph, and citations."
    elif "table" in card_type:
        prefix = "Review normalized table rows/cells and confirm repaired values against catalog, graph, and citations."
    elif "blank" in card_type:
        prefix = "Confirm blank classification while preserving source trace and page lineage."
    elif card_type == "community_review_card":
        prefix = "Review this community for useful evidence neighborhoods, high-risk pages, and feedback/retrieval signals."
    else:
        prefix = "Review grouped tasks and update the appropriate TRACE-Net evidence/review status."
    if not actions:
        return prefix
    return prefix + " Related task actions: " + " | ".join(actions)


def make_triage_card(kind: str, value: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    priorities = [clamp_priority(t.get("priority")) for t in tasks]
    priority = highest_priority(priorities)
    page_ids = unique_sorted([task_page_id(t) for t in tasks])
    community_ids = unique_sorted(cid for t in tasks for cid in string_list(t.get("community_ids")))
    citation_ids = unique_sorted((cid for t in tasks for cid in string_list(t.get("citation_ids"))), limit=50)
    part_numbers = unique_sorted((p for t in tasks for p in string_list(t.get("part_numbers"))), limit=50)
    task_ids = unique_sorted([t.get("review_task_id") for t in tasks])
    origins = summarize_origins(tasks)
    task_types = summarize_task_types(tasks)
    card_type = card_type_for_group(kind, tasks)
    reason_samples = unique_sorted([sanitize_text(t.get("reason"), 220) for t in tasks], limit=8)

    # Score emphasizes severity, volume, and evidence richness. It is a queue score,
    # not evidence truth and not answer authority.
    base_score = PRIORITY_SCORE[priority]
    volume_score = min(len(tasks), 25) * 2
    evidence_score = min(len(citation_ids), 10) + min(len(part_numbers), 10) + min(len(community_ids), 5)
    triage_score = round(base_score + volume_score + evidence_score, 3)

    card_id = stable_id("triage", kind, value, task_ids)
    return {
        "triage_card_id": card_id,
        "schema_version": SCHEMA_VERSION,
        "card_type": card_type,
        "group_kind": kind,
        "group_value": value,
        "priority": priority,
        "triage_score": triage_score,
        "review_status": "open",
        "task_count": len(tasks),
        "source_review_task_ids": task_ids,
        "page_id": page_ids[0] if len(page_ids) == 1 else None,
        "page_ids": page_ids,
        "page_count": len(page_ids),
        "community_ids": community_ids,
        "citation_ids": citation_ids,
        "part_numbers": part_numbers,
        "origin_summaries": origins,
        "task_type_summaries": task_types,
        "reason_summary": " | ".join(reason_samples),
        "recommended_action": recommended_action_for_card(tasks, card_type),
        "triage_authority": AUTHORITY,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "final_answer_allowed": False,
        "can_override_citation": False,
        "can_override_trust_authority": False,
        "raw_feedback_direct_to_llm": False,
        "source_truth_mutations_performed": 0,
        "unsafe_triage_card": False,
    }


def build_cards(review_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for task in review_tasks:
        groups[group_key_for_task(task)].append(task)
    cards = [make_triage_card(kind, value, tasks) for (kind, value), tasks in groups.items()]
    return sorted(
        cards,
        key=lambda c: (
            priority_sort_value(c.get("priority", "medium")),
            -float(c.get("triage_score") or 0),
            str(c.get("group_kind") or ""),
            str(c.get("group_value") or ""),
        ),
    )


def compute_summary(*, queue_report: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    input_tasks = queue_report.get("review_tasks", []) or []
    priority_counts = Counter(c["priority"] for c in cards)
    card_type_counts = Counter(c["card_type"] for c in cards)
    origin_counts: Counter[str] = Counter()
    task_type_counts: Counter[str] = Counter()
    for card in cards:
        for item in card.get("origin_summaries", []):
            origin_counts[str(item.get("origin_category"))] += int(item.get("count") or 0)
        for item in card.get("task_type_summaries", []):
            task_type_counts[str(item.get("task_type"))] += int(item.get("count") or 0)
    input_critical_count = len([t for t in input_tasks if clamp_priority(t.get("priority")) == "critical"])
    critical_cards = [c for c in cards if c.get("priority") == "critical"]
    page_scoped_cards = [c for c in cards if c.get("group_kind") == "page"]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "BUILT",
        "input_review_task_count": len(input_tasks),
        "triage_card_count": len(cards),
        "deduped_task_count": max(0, len(input_tasks) - len(cards)),
        "deduplication_ratio": round((1 - (len(cards) / len(input_tasks))) if input_tasks else 0, 6),
        "critical_task_input_count": input_critical_count,
        "critical_task_preserved_count": len(critical_cards),
        "critical_priority_triage_card_count": priority_counts.get("critical", 0),
        "high_priority_triage_card_count": priority_counts.get("high", 0) + priority_counts.get("critical", 0),
        "medium_priority_triage_card_count": priority_counts.get("medium", 0),
        "low_priority_triage_card_count": priority_counts.get("low", 0),
        "page_scoped_triage_card_count": len(page_scoped_cards),
        "multi_task_triage_card_count": len([c for c in cards if int(c.get("task_count") or 0) > 1]),
        "max_tasks_per_card": max([int(c.get("task_count") or 0) for c in cards] or [0]),
        "missing_page_id_count": len([c for c in page_scoped_cards if not c.get("page_id")]),
        "unsafe_triage_card_count": len([c for c in cards if c.get("unsafe_triage_card")]),
        "triage_card_can_answer_directly_count": len([c for c in cards if c.get("can_answer_directly")]),
        "triage_card_can_prove_claims_count": len([c for c in cards if c.get("can_prove_claims")]),
        "source_truth_mutation_allowed_count": len([c for c in cards if c.get("can_mutate_source_truth")]),
        "raw_feedback_direct_to_llm_count": len([c for c in cards if c.get("raw_feedback_direct_to_llm")]),
        "final_answer_allowed_count": len([c for c in cards if c.get("final_answer_allowed")]),
        "priority_counts": dict(sorted(priority_counts.items())),
        "card_type_counts": dict(sorted(card_type_counts.items())),
        "origin_category_task_counts": dict(sorted(origin_counts.items())),
        "task_type_counts": dict(sorted(task_type_counts.items())),
        "source_queue_quality_status": queue_report.get("quality_status") or queue_report.get("status"),
        "source_queue_review_task_count": queue_report.get("summary", {}).get("review_task_count"),
    }


def compute_quality(
    report: dict[str, Any],
    *,
    min_triage_cards: int = 1,
    min_high_priority_cards: int = 1,
    require_source_queue_quality_pass: bool = False,
    require_deduplication: bool = True,
) -> dict[str, Any]:
    s = report.get("summary", {}) or {}
    checks = {
        "min_triage_cards": int(s.get("triage_card_count") or 0) >= min_triage_cards,
        "min_high_priority_cards": int(s.get("high_priority_triage_card_count") or 0) >= min_high_priority_cards,
        "critical_tasks_preserved": int(s.get("critical_task_preserved_count") or 0) >= int(s.get("critical_task_input_count") or 0),
        "missing_page_id_count_zero": int(s.get("missing_page_id_count") or 0) == 0,
        "unsafe_triage_card_count_zero": int(s.get("unsafe_triage_card_count") or 0) == 0,
        "triage_card_can_answer_directly_count_zero": int(s.get("triage_card_can_answer_directly_count") or 0) == 0,
        "triage_card_can_prove_claims_count_zero": int(s.get("triage_card_can_prove_claims_count") or 0) == 0,
        "source_truth_mutation_allowed_count_zero": int(s.get("source_truth_mutation_allowed_count") or 0) == 0,
        "raw_feedback_direct_to_llm_count_zero": int(s.get("raw_feedback_direct_to_llm_count") or 0) == 0,
        "final_answer_allowed_count_zero": int(s.get("final_answer_allowed_count") or 0) == 0,
    }
    if require_source_queue_quality_pass:
        checks["source_queue_quality_status_pass"] = str(s.get("source_queue_quality_status") or "").upper() == "PASS"
    if require_deduplication:
        checks["triage_cards_less_than_input_tasks"] = int(s.get("triage_card_count") or 0) < int(s.get("input_review_task_count") or 0)
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
        "# TRACE-Net Human Review Queue Triage / Dedup v1",
        "",
        f"**Status:** {report['status']}",
        f"**Quality:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "input_review_task_count",
        "triage_card_count",
        "deduped_task_count",
        "deduplication_ratio",
        "critical_task_input_count",
        "critical_task_preserved_count",
        "high_priority_triage_card_count",
        "medium_priority_triage_card_count",
        "low_priority_triage_card_count",
        "multi_task_triage_card_count",
        "missing_page_id_count",
        "unsafe_triage_card_count",
        "triage_card_can_answer_directly_count",
        "triage_card_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {s.get(key)}")
    lines.extend(["", "## Top Triage Cards", ""])
    lines.append("| Priority | Card type | Group | Tasks | Reason |")
    lines.append("|---|---|---|---:|---|")
    for card in report.get("triage_cards", [])[:60]:
        lines.append(
            "| {priority} | {card_type} | {group} | {tasks} | {reason} |".format(
                priority=card.get("priority"),
                card_type=card.get("card_type"),
                group=(card.get("page_id") or card.get("group_value") or "-").replace("|", "\\|"),
                tasks=card.get("task_count"),
                reason=sanitize_text(card.get("reason_summary"), 180).replace("|", "\\|"),
            )
        )
    return "\n".join(lines) + "\n"


def render_html(markdown_text: str) -> str:
    return "<html><body><pre>" + html.escape(markdown_text) + "</pre></body></html>"


def build_human_review_triage(
    *,
    human_review_queue_path: str | Path,
    output_dir: str | Path = "local_data/organization/trace_net/human_review_triage",
    min_triage_cards: int = 1,
    min_high_priority_cards: int = 1,
    require_source_queue_quality_pass: bool = False,
    require_deduplication: bool = True,
    write_quality: bool = False,
) -> dict[str, Any]:
    queue_report = read_json(human_review_queue_path, {})
    cards = build_cards(queue_report.get("review_tasks", []) or [])
    summary = compute_summary(queue_report=queue_report, cards=cards)
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "HUMAN_REVIEW_TRIAGE_BUILT",
        "generated_at": utc_now(),
        "source_queue_path": str(human_review_queue_path),
        "triage_cards": cards,
        "summary": summary,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "final_answer_allowed": False,
    }
    quality = compute_quality(
        report,
        min_triage_cards=min_triage_cards,
        min_high_priority_cards=min_high_priority_cards,
        require_source_queue_quality_pass=require_source_queue_quality_pass,
        require_deduplication=require_deduplication,
    )
    report["quality_status"] = quality["status"]

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_human_review_triage_v1.json"
    cards_path = out / "trace_net_human_review_triage_v1_cards.jsonl"
    summary_path = out / "trace_net_human_review_triage_v1_summary.json"
    quality_path = out / "trace_net_human_review_triage_v1_quality.json"
    manifest_path = out / "trace_net_human_review_triage_v1_manifest.json"
    md_path = out / "trace_net_human_review_triage_v1.md"
    html_path = out / "trace_net_human_review_triage_v1.html"

    report["report_path"] = str(report_path)
    report["cards_path"] = str(cards_path)
    report["quality_path"] = str(quality_path)
    quality["quality_path"] = str(quality_path)

    write_json(report_path, report)
    write_jsonl(cards_path, cards)
    write_json(summary_path, summary)
    write_json(quality_path, quality)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now(),
        "inputs": {"human_review_queue": str(human_review_queue_path)},
        "outputs": {
            "report": str(report_path),
            "cards": str(cards_path),
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
    min_triage_cards: int = 1,
    min_high_priority_cards: int = 1,
    require_source_queue_quality_pass: bool = False,
    require_deduplication: bool = True,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path, {})
    quality = compute_quality(
        report,
        min_triage_cards=min_triage_cards,
        min_high_priority_cards=min_high_priority_cards,
        require_source_queue_quality_pass=require_source_queue_quality_pass,
        require_deduplication=require_deduplication,
    )
    if write_json_report:
        quality_path = Path(report_path).with_name("trace_net_human_review_triage_v1_quality.json")
        write_json(quality_path, quality)
        quality["quality_path"] = str(quality_path)
    return quality


def print_build_summary(report: dict[str, Any]) -> None:
    s = report["summary"]
    print("TRACE-Net human review queue triage / dedup v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "input_review_task_count",
        "triage_card_count",
        "deduped_task_count",
        "deduplication_ratio",
        "critical_task_input_count",
        "critical_task_preserved_count",
        "high_priority_triage_card_count",
        "medium_priority_triage_card_count",
        "low_priority_triage_card_count",
        "missing_page_id_count",
        "unsafe_triage_card_count",
        "triage_card_can_answer_directly_count",
        "triage_card_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" cards_path: {report.get('cards_path')}")
    print(f" quality_path: {report.get('quality_path')}")


def print_quality_summary(quality: dict[str, Any]) -> None:
    s = quality.get("summary", {})
    print("TRACE-Net human review queue triage / dedup v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "input_review_task_count",
        "triage_card_count",
        "deduped_task_count",
        "critical_task_preserved_count",
        "high_priority_triage_card_count",
        "missing_page_id_count",
        "unsafe_triage_card_count",
        "triage_card_can_answer_directly_count",
        "triage_card_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality['quality_path']}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Human Review Queue Triage / Dedup v1")
    parser.add_argument("--human-review-queue", required=True, dest="human_review_queue_path")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/human_review_triage")
    parser.add_argument("--min-triage-cards", type=int, default=1)
    parser.add_argument("--min-high-priority-cards", type=int, default=1)
    parser.add_argument("--require-source-queue-quality-pass", action="store_true")
    parser.add_argument("--allow-no-dedup", action="store_true", help="Do not require card count to be less than input task count.")
    parser.add_argument("--quality", action="store_true", dest="write_quality")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_human_review_triage(
        human_review_queue_path=args.human_review_queue_path,
        output_dir=args.output_dir,
        min_triage_cards=args.min_triage_cards,
        min_high_priority_cards=args.min_high_priority_cards,
        require_source_queue_quality_pass=args.require_source_queue_quality_pass,
        require_deduplication=not args.allow_no_dedup,
        write_quality=args.write_quality,
    )
    print_build_summary(report)
    return 0 if report["quality_status"] == "PASS" else 1


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Human Review Queue Triage / Dedup v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-triage-cards", type=int, default=1)
    parser.add_argument("--min-high-priority-cards", type=int, default=1)
    parser.add_argument("--require-source-queue-quality-pass", action="store_true")
    parser.add_argument("--allow-no-dedup", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: list[str] | None = None) -> int:
    args = quality_arg_parser().parse_args(argv)
    quality = quality_report(
        report_path=args.report_path,
        min_triage_cards=args.min_triage_cards,
        min_high_priority_cards=args.min_high_priority_cards,
        require_source_queue_quality_pass=args.require_source_queue_quality_pass,
        require_deduplication=not args.allow_no_dedup,
        write_json_report=args.write_json,
    )
    print_quality_summary(quality)
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
