"""TRACE-Net Human Review Queue v1.

This module builds a read-only, safety-preserving human review queue from
TRACE-Net operational artifacts. It converts broad health/retry/review signals
into prioritized reviewer tasks without granting answer authority or mutating
source truth.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_human_review_queue_v1"
AUTHORITY = "human_review_advisory_only"

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if path is None:
        return default
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def read_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    p = Path(path)
    if not p.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


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


def pick_page_id(payload: dict[str, Any]) -> str | None:
    for key in ("page_id", "page", "source_page_id", "target_page_id"):
        value = payload.get(key)
        if value:
            return str(value)
    page_ids = payload.get("page_ids") or payload.get("source_page_ids")
    if isinstance(page_ids, list) and page_ids:
        return str(page_ids[0])
    return None


def severity_to_priority(severity: str | None, default: str = "medium") -> str:
    sev = (severity or "").lower()
    if sev == "critical":
        return "critical"
    if sev in {"review", "warning"}:
        return "medium"
    return default


def clamp_priority(priority: str) -> str:
    if priority not in PRIORITY_ORDER:
        return "medium"
    return priority


def sanitize_text(text: Any, max_chars: int = 1200) -> str:
    if text is None:
        return ""
    value = str(text).replace("\r", " ").replace("\n", " ")
    while "  " in value:
        value = value.replace("  ", " ")
    return value.strip()[:max_chars]


@dataclass(frozen=True)
class ReviewTaskSpec:
    task_type: str
    priority: str
    origin_category: str
    source_stage: str
    reason: str
    recommended_action: str
    page_id: str | None = None
    target_type: str = "artifact"
    target_id: str | None = None
    requires_page_id: bool = False
    artifact_path: str | None = None
    issue_key: str | None = None
    issue_value: Any = None
    citation_ids: tuple[str, ...] = ()
    community_ids: tuple[str, ...] = ()
    part_numbers: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


def make_task(spec: ReviewTaskSpec) -> dict[str, Any]:
    task_id = stable_id(
        "review",
        spec.task_type,
        spec.source_stage,
        spec.page_id,
        spec.target_type,
        spec.target_id,
        spec.issue_key,
        spec.reason,
    )
    missing_page_id = bool(spec.requires_page_id and not spec.page_id)
    unsafe = False
    return {
        "review_task_id": task_id,
        "schema_version": SCHEMA_VERSION,
        "task_type": spec.task_type,
        "priority": clamp_priority(spec.priority),
        "origin_category": spec.origin_category,
        "source_stage": spec.source_stage,
        "page_id": spec.page_id,
        "requires_page_id": spec.requires_page_id,
        "missing_page_id": missing_page_id,
        "target_type": spec.target_type,
        "target_id": spec.target_id,
        "artifact_path": spec.artifact_path,
        "issue_key": spec.issue_key,
        "issue_value": spec.issue_value,
        "reason": sanitize_text(spec.reason),
        "recommended_action": sanitize_text(spec.recommended_action),
        "review_status": "open",
        "review_queue_authority": AUTHORITY,
        "citation_ids": list(spec.citation_ids),
        "community_ids": list(spec.community_ids),
        "part_numbers": list(spec.part_numbers),
        "tags": list(spec.tags),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "final_answer_allowed": False,
        "can_override_citation": False,
        "can_override_trust_authority": False,
        "source_truth_mutations_performed": 0,
        "unsafe_review_task": unsafe,
    }


def add_task(tasks: list[dict[str, Any]], seen: set[str], spec: ReviewTaskSpec) -> None:
    task = make_task(spec)
    if task["review_task_id"] in seen:
        return
    seen.add(task["review_task_id"])
    tasks.append(task)


def extract_it_console_tasks(console: dict[str, Any], tasks: list[dict[str, Any]], seen: set[str]) -> None:
    for issue in console.get("issues", []) or []:
        severity = str(issue.get("severity") or "warning").lower()
        if severity not in {"critical", "warning", "review"}:
            continue
        category = str(issue.get("category") or "operations")
        stage = str(issue.get("stage_id") or issue.get("stage_name") or "it_operations_console")
        key = issue.get("key")
        value = issue.get("value")
        page_id = pick_page_id(issue)
        if category in {"source_truth_mutation", "answer_permission", "raw_feedback_direct_to_llm"} or severity == "critical":
            task_type = "it_critical_issue_review"
            priority = "critical"
        elif severity == "review":
            task_type = "it_review_backlog_item"
            priority = "medium"
        else:
            task_type = "it_warning_triage"
            priority = "low"
        add_task(
            tasks,
            seen,
            ReviewTaskSpec(
                task_type=task_type,
                priority=priority,
                origin_category=category,
                source_stage=stage,
                page_id=page_id,
                target_type="it_issue",
                target_id=stable_id("issue", stage, key, value, issue.get("artifact_path")),
                artifact_path=issue.get("artifact_path"),
                issue_key=str(key) if key is not None else None,
                issue_value=value,
                reason=issue.get("message") or f"IT console reported {category} issue.",
                recommended_action=issue.get("recommended_action") or "Review the underlying stage artifact and clear the condition.",
                tags=(severity, category),
            ),
        )


def extract_fishnet_tasks(report: dict[str, Any], tasks: list[dict[str, Any]], seen: set[str]) -> None:
    for record in report.get("records", []) or []:
        page_id = str(record.get("page_id") or "") or None
        disposition = str(record.get("fishnet_disposition") or "")
        priority = str(record.get("priority") or "medium")
        review_actions = string_list(record.get("review_actions"))
        actual_retry_actions = string_list(record.get("actual_retry_actions"))
        blank_actions = string_list(record.get("blank_handling_actions"))
        if review_actions or record.get("needs_human_review"):
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="fishnet_review_required",
                    priority="high" if priority in {"high", "critical"} else "medium",
                    origin_category="fishnet_retry",
                    source_stage="fishnet_retry_refined",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="page",
                    target_id=page_id,
                    reason=f"Fishnet disposition '{disposition}' includes review actions: {', '.join(review_actions) or 'human review required'}.",
                    recommended_action="Review the page's fishnet retry plan and mark retry/review disposition.",
                    tags=("fishnet", "review_required"),
                ),
            )
        if any("repaired_table" in action or "table" in action for action in review_actions + actual_retry_actions):
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="review_table_retry_or_repair",
                    priority="high",
                    origin_category="table_extraction",
                    source_stage="fishnet_retry_refined",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="page",
                    target_id=page_id,
                    reason="Fishnet indicates table rows/cells or repaired table cells need validation.",
                    recommended_action="Inspect normalized table rows/cells and compare repaired part numbers against catalog/graph evidence.",
                    tags=("table", "fishnet"),
                ),
            )
        if any("visual" in action or "vision" in action or "callout" in action for action in review_actions + actual_retry_actions):
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="verify_visual_or_callout_retry",
                    priority="high" if record.get("needs_vision_model") else "medium",
                    origin_category="visual_diagram",
                    source_stage="fishnet_retry_refined",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="page",
                    target_id=page_id,
                    reason="Fishnet indicates visual regions, callouts, or vision-model pilot output need verification.",
                    recommended_action="Verify visual/callout candidates against OCR, table rows, catalog, graph, and citations.",
                    tags=("visual", "callout", "fishnet"),
                ),
            )
        if blank_actions:
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="confirm_blank_source_trace",
                    priority="low",
                    origin_category="source_ingest",
                    source_stage="fishnet_retry_refined",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="page",
                    target_id=page_id,
                    reason="Fishnet marked this page as source-confirmed blank; source trace should be preserved.",
                    recommended_action="Confirm blank page classification only if source trace and page lineage are preserved.",
                    tags=("blank", "source_trace"),
                ),
            )


def extract_table_tasks(report: dict[str, Any], tasks: list[dict[str, Any]], seen: set[str]) -> None:
    for record in report.get("records", []) or []:
        page_id = str(record.get("page_id") or "") or None
        repairs = record.get("repairs") or []
        repair_count = int(record.get("repair_count") or record.get("normalized_repair_count") or len(repairs) or 0)
        if repair_count > 0:
            part_numbers = []
            for repair in repairs:
                merged = repair.get("merged_part_number")
                if merged:
                    part_numbers.append(str(merged))
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="review_repaired_table_cells",
                    priority="high",
                    origin_category="table_extraction",
                    source_stage="table_cell_normalizer",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="table_record",
                    target_id=str(record.get("normalized_table_id") or record.get("table_id") or page_id),
                    citation_ids=tuple(string_list(record.get("citation_ids"))),
                    part_numbers=tuple(sorted(set(part_numbers))),
                    reason=f"Table normalizer produced {repair_count} repaired cell/part-number candidate(s).",
                    recommended_action="Confirm repaired row/cell values before promoting table evidence beyond review status.",
                    tags=("table", "repair", "part_number"),
                ),
            )
        if int(record.get("candidate_unverified_merge_count") or 0) > 0:
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="review_unverified_table_part_merge",
                    priority="high",
                    origin_category="table_extraction",
                    source_stage="table_cell_normalizer",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="table_record",
                    target_id=str(record.get("normalized_table_id") or record.get("table_id") or page_id),
                    reason="Table normalizer has candidate part-number merges without catalog support.",
                    recommended_action="Compare unverified merged part numbers against catalog, graph, and source text before use.",
                    tags=("table", "unverified_merge"),
                ),
            )


def extract_visual_tasks(report: dict[str, Any], tasks: list[dict[str, Any]], seen: set[str]) -> None:
    for record in report.get("records", []) or []:
        page_id = str(record.get("page_id") or "") or None
        needs_review = bool(record.get("needs_human_review"))
        requires_catalog = bool(record.get("requires_catalog_compare"))
        linked_parts = string_list(record.get("linked_part_candidates"))
        callouts = string_list(record.get("callout_labels"))
        visual_type = str(record.get("visual_type") or record.get("source_visual_type") or "visual")
        if needs_review or requires_catalog or linked_parts:
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="verify_visual_part_candidates",
                    priority="high" if linked_parts else "medium",
                    origin_category="visual_diagram",
                    source_stage="figure_chart_understanding",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="visual_record",
                    target_id=str(record.get("visual_understanding_id") or page_id),
                    part_numbers=tuple(linked_parts[:25]),
                    reason=f"Visual page '{visual_type}' has unverified visual/callout/part evidence or catalog comparison requirements.",
                    recommended_action="Verify diagram/callout/part candidates against same-page OCR, table rows, catalog, graph, and citations.",
                    tags=("visual", "catalog_compare"),
                ),
            )
        if callouts:
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="review_callout_candidates",
                    priority="medium",
                    origin_category="visual_diagram",
                    source_stage="figure_chart_understanding",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="visual_record",
                    target_id=str(record.get("visual_understanding_id") or page_id),
                    reason=f"Detected {len(callouts)} callout candidate(s) that may include random numbers or unverified labels.",
                    recommended_action="Separate true diagram callouts from random numbers, page numbers, dates, quantities, and OCR noise.",
                    tags=("callout", "visual"),
                ),
            )


def extract_ink_tasks(report: dict[str, Any], tasks: list[dict[str, Any]], seen: set[str]) -> None:
    for record in report.get("records", []) or []:
        page_id = str(record.get("page_id") or "") or None
        if record.get("needs_human_review"):
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="review_visual_layout_classification",
                    priority="medium",
                    origin_category="visual_diagram",
                    source_stage="visual_ink_layout_calibrator",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="page",
                    target_id=page_id,
                    reason="Ink/layout calibrator marked the page for human review.",
                    recommended_action="Confirm calibrated layout class and route before expensive vision/model processing.",
                    tags=("ink_layout", "visual"),
                ),
            )
        if record.get("source_confirmed_blank"):
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="confirm_blank_source_trace",
                    priority="low",
                    origin_category="source_ingest",
                    source_stage="visual_ink_layout_calibrator",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="page",
                    target_id=page_id,
                    reason="Ink/layout calibrator source-confirmed a blank page.",
                    recommended_action="Spot-check blank classification and ensure source trace remains preserved.",
                    tags=("blank", "ink_layout"),
                ),
            )


def extract_callout_verifier_tasks(report: dict[str, Any], tasks: list[dict[str, Any]], seen: set[str]) -> None:
    for record in report.get("records", []) or []:
        page_id = str(record.get("page_id") or "") or None
        if record.get("needs_human_review") or record.get("review_reasons"):
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="review_callout_visual_part_verification",
                    priority="high",
                    origin_category="visual_diagram",
                    source_stage="callout_visual_part_verifier",
                    page_id=page_id,
                    requires_page_id=True,
                    target_type="callout_visual_part_record",
                    target_id=str(record.get("verifier_record_id") or page_id),
                    part_numbers=tuple(string_list(record.get("linked_visual_part_candidates"))[:25]),
                    reason="Callout/visual part verifier found unverified callout or visual-part relationships.",
                    recommended_action="Confirm callout labels, suppress random numbers, and verify linked parts against catalog/graph/table evidence.",
                    tags=("callout", "visual_part"),
                ),
            )


def extract_feedback_tasks(report: dict[str, Any], tasks: list[dict[str, Any]], seen: set[str]) -> None:
    for record in report.get("memory_records", []) or []:
        target_type = str(record.get("target_type") or "feedback")
        target_id = str(record.get("target_id") or record.get("memory_id") or "feedback")
        page_id = pick_page_id(record)
        rating = float(record.get("rating_score") or 0)
        prompt_flag = bool(record.get("prompt_injection_flagged"))
        if prompt_flag:
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="review_prompt_injection_feedback",
                    priority="critical",
                    origin_category="feedback_memory",
                    source_stage="feedback_memory",
                    page_id=page_id,
                    target_type=target_type,
                    target_id=target_id,
                    reason="Feedback memory flagged a possible prompt-injection or instruction-manipulation comment.",
                    recommended_action="Review the raw feedback event; keep only sanitized advisory memory and do not pass raw text to the LLM.",
                    tags=("feedback", "prompt_injection"),
                ),
            )
        elif rating < 0:
            add_task(
                tasks,
                seen,
                ReviewTaskSpec(
                    task_type="review_negative_feedback_target",
                    priority="medium",
                    origin_category="feedback_memory",
                    source_stage="feedback_memory",
                    page_id=page_id,
                    target_type=target_type,
                    target_id=target_id,
                    reason="User feedback marked this target as not helpful or potentially wrong.",
                    recommended_action="Inspect the associated answer/page/citation/community and decide whether ranking, review status, or guidance should change.",
                    tags=("feedback", "negative"),
                ),
            )


def extract_leiden_tasks(report: dict[str, Any], tasks: list[dict[str, Any]], seen: set[str], max_tasks: int = 25) -> None:
    communities = report.get("communities", []) or []
    # Queue only the largest/highly visual or review-heavy communities to keep this actionable.
    sorted_communities = sorted(communities, key=lambda c: int(c.get("node_count") or 0), reverse=True)
    count = 0
    for community in sorted_communities:
        if count >= max_tasks:
            break
        node_count = int(community.get("node_count") or 0)
        page_count = int(community.get("page_count") or 0)
        dominant = string_list(community.get("dominant_node_types"))
        part_families = string_list(community.get("part_families"))
        if node_count < 50 and page_count < 5:
            continue
        if not (part_families or any("Callout" in item or "Table" in item for item in dominant)):
            continue
        community_id = str(community.get("community_id") or community.get("id") or stable_id("community", community))
        add_task(
            tasks,
            seen,
            ReviewTaskSpec(
                task_type="review_high_signal_graph_community",
                priority="low",
                origin_category="graph_community",
                source_stage="leiden_graph_communities",
                target_type="community",
                target_id=community_id,
                community_ids=(community_id,),
                part_numbers=tuple(string_list(community.get("part_numbers"))[:25]),
                reason=f"Large or high-signal community with {node_count} node(s), {page_count} page(s), and part families {', '.join(part_families[:5])}.",
                recommended_action="Inspect the community summary for review-risk clusters, useful part families, and evidence neighborhoods.",
                tags=("community", "leiden"),
            ),
        )
        count += 1


def extract_final_answer_tasks(report: dict[str, Any], tasks: list[dict[str, Any]], seen: set[str]) -> None:
    summary = report.get("summary", {}) or {}
    if int(summary.get("uncited_final_claim_count") or report.get("uncited_final_claim_count") or 0) > 0:
        add_task(
            tasks,
            seen,
            ReviewTaskSpec(
                task_type="review_uncited_final_claim",
                priority="critical",
                origin_category="answer_gate",
                source_stage="final_answer_gate",
                target_type="answer_report",
                target_id=str(report.get("report_id") or "trace_net_final_answer_gate_v1"),
                reason="Final answer gate report indicates one or more uncited final claims.",
                recommended_action="Block publication until every final claim has citation, page/source, and authority.",
                tags=("answer_gate", "citation"),
            ),
        )


def sort_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        tasks,
        key=lambda t: (
            PRIORITY_ORDER.get(t.get("priority"), 9),
            str(t.get("origin_category") or ""),
            str(t.get("page_id") or ""),
            str(t.get("task_type") or ""),
            str(t.get("review_task_id") or ""),
        ),
    )


def compute_quality(report: dict[str, Any], *, min_review_tasks: int = 1, min_high_priority_review_tasks: int = 1, require_it_console_quality_pass: bool = False) -> dict[str, Any]:
    summary = report.get("summary", {})
    checks = {
        "min_review_tasks": int(summary.get("review_task_count") or 0) >= min_review_tasks,
        "min_high_priority_review_tasks": int(summary.get("high_priority_review_task_count") or 0) >= min_high_priority_review_tasks,
        "missing_page_id_count_zero": int(summary.get("missing_page_id_count") or 0) == 0,
        "unsafe_review_task_count_zero": int(summary.get("unsafe_review_task_count") or 0) == 0,
        "review_task_can_answer_directly_count_zero": int(summary.get("review_task_can_answer_directly_count") or 0) == 0,
        "review_task_can_prove_claims_count_zero": int(summary.get("review_task_can_prove_claims_count") or 0) == 0,
        "source_truth_mutation_allowed_count_zero": int(summary.get("source_truth_mutation_allowed_count") or 0) == 0,
        "raw_feedback_direct_to_llm_count_zero": int(summary.get("raw_feedback_direct_to_llm_count") or 0) == 0,
    }
    if require_it_console_quality_pass:
        checks["it_console_quality_status_pass"] = str(summary.get("it_console_quality_status") or "").upper() == "PASS"
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "checks": checks,
        "summary": summary,
        "generated_at": utc_now(),
    }


def build_human_review_queue(
    *,
    it_console_path: str | Path | None = None,
    fishnet_retry_refined_path: str | Path | None = None,
    figure_chart_understanding_path: str | Path | None = None,
    visual_ink_layout_calibrator_path: str | Path | None = None,
    callout_visual_part_verifier_path: str | Path | None = None,
    table_cell_normalizer_path: str | Path | None = None,
    feedback_memory_path: str | Path | None = None,
    leiden_communities_path: str | Path | None = None,
    community_aware_retrieval_path: str | Path | None = None,
    final_answer_report_path: str | Path | None = None,
    output_dir: str | Path = "local_data/organization/trace_net/human_review_queue",
    min_review_tasks: int = 1,
    min_high_priority_review_tasks: int = 1,
    require_it_console_quality_pass: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    sources = {
        "it_console": read_json(it_console_path, {}),
        "fishnet_retry_refined": read_json(fishnet_retry_refined_path, {}),
        "figure_chart_understanding": read_json(figure_chart_understanding_path, {}),
        "visual_ink_layout_calibrator": read_json(visual_ink_layout_calibrator_path, {}),
        "callout_visual_part_verifier": read_json(callout_visual_part_verifier_path, {}),
        "table_cell_normalizer": read_json(table_cell_normalizer_path, {}),
        "feedback_memory": read_json(feedback_memory_path, {}),
        "leiden_communities": read_json(leiden_communities_path, {}),
        "community_aware_retrieval": read_json(community_aware_retrieval_path, {}),
        "final_answer_report": read_json(final_answer_report_path, {}),
    }

    tasks: list[dict[str, Any]] = []
    seen: set[str] = set()

    extract_it_console_tasks(sources["it_console"], tasks, seen)
    extract_fishnet_tasks(sources["fishnet_retry_refined"], tasks, seen)
    extract_table_tasks(sources["table_cell_normalizer"], tasks, seen)
    extract_visual_tasks(sources["figure_chart_understanding"], tasks, seen)
    extract_ink_tasks(sources["visual_ink_layout_calibrator"], tasks, seen)
    extract_callout_verifier_tasks(sources["callout_visual_part_verifier"], tasks, seen)
    extract_feedback_tasks(sources["feedback_memory"], tasks, seen)
    extract_leiden_tasks(sources["leiden_communities"], tasks, seen)
    extract_final_answer_tasks(sources["final_answer_report"], tasks, seen)

    tasks = sort_tasks(tasks)

    priority_counts = Counter(t["priority"] for t in tasks)
    task_type_counts = Counter(t["task_type"] for t in tasks)
    origin_counts = Counter(t["origin_category"] for t in tasks)
    page_ids = sorted({t["page_id"] for t in tasks if t.get("page_id")})

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "BUILT",
        "review_task_count": len(tasks),
        "open_review_task_count": len([t for t in tasks if t.get("review_status") == "open"]),
        "critical_priority_review_task_count": priority_counts.get("critical", 0),
        "high_priority_review_task_count": priority_counts.get("high", 0) + priority_counts.get("critical", 0),
        "medium_priority_review_task_count": priority_counts.get("medium", 0),
        "low_priority_review_task_count": priority_counts.get("low", 0),
        "page_scoped_review_task_count": len([t for t in tasks if t.get("page_id")]),
        "review_page_count": len(page_ids),
        "missing_page_id_count": len([t for t in tasks if t.get("missing_page_id")]),
        "unsafe_review_task_count": len([t for t in tasks if t.get("unsafe_review_task")]),
        "review_task_can_answer_directly_count": len([t for t in tasks if t.get("can_answer_directly")]),
        "review_task_can_prove_claims_count": len([t for t in tasks if t.get("can_prove_claims")]),
        "source_truth_mutation_allowed_count": len([t for t in tasks if t.get("can_mutate_source_truth")]),
        "raw_feedback_direct_to_llm_count": 0,
        "prompt_injection_review_task_count": task_type_counts.get("review_prompt_injection_feedback", 0),
        "table_repair_review_task_count": task_type_counts.get("review_repaired_table_cells", 0) + task_type_counts.get("review_table_retry_or_repair", 0),
        "visual_review_task_count": sum(count for task_type, count in task_type_counts.items() if "visual" in task_type or "callout" in task_type),
        "feedback_review_task_count": sum(count for task_type, count in task_type_counts.items() if "feedback" in task_type),
        "community_review_task_count": task_type_counts.get("review_high_signal_graph_community", 0),
        "origin_category_counts": dict(sorted(origin_counts.items())),
        "task_type_counts": dict(sorted(task_type_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "source_quality_statuses": {
            name: src.get("quality_status") or src.get("status") or src.get("summary", {}).get("status")
            for name, src in sources.items()
            if isinstance(src, dict) and src
        },
        "it_console_quality_status": sources["it_console"].get("quality_status") or sources["it_console"].get("summary", {}).get("status") or sources["it_console"].get("status"),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutations_performed": 0,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "HUMAN_REVIEW_QUEUE_BUILT",
        "quality_status": "UNKNOWN",
        "generated_at": utc_now(),
        "summary": summary,
        "review_tasks": tasks,
        "review_pages": page_ids,
    }
    quality = compute_quality(
        report,
        min_review_tasks=min_review_tasks,
        min_high_priority_review_tasks=min_high_priority_review_tasks,
        require_it_console_quality_pass=require_it_console_quality_pass,
    )
    report["quality_status"] = quality["status"]
    report["summary"]["status"] = quality["status"]

    report_path = out / "trace_net_human_review_queue_v1.json"
    tasks_path = out / "trace_net_human_review_queue_v1_tasks.jsonl"
    summary_path = out / "trace_net_human_review_queue_v1_summary.json"
    quality_path = out / "trace_net_human_review_queue_v1_quality.json"
    manifest_path = out / "trace_net_human_review_queue_v1_manifest.json"
    md_path = out / "trace_net_human_review_queue_v1.md"
    html_path = out / "trace_net_human_review_queue_v1.html"

    report["report_path"] = str(report_path)
    report["tasks_path"] = str(tasks_path)
    report["quality_path"] = str(quality_path)

    write_json(report_path, report)
    write_jsonl(tasks_path, tasks)
    write_json(summary_path, summary)
    write_json(quality_path, quality)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now(),
        "inputs": {
            "it_console": str(it_console_path) if it_console_path else None,
            "fishnet_retry_refined": str(fishnet_retry_refined_path) if fishnet_retry_refined_path else None,
            "figure_chart_understanding": str(figure_chart_understanding_path) if figure_chart_understanding_path else None,
            "visual_ink_layout_calibrator": str(visual_ink_layout_calibrator_path) if visual_ink_layout_calibrator_path else None,
            "callout_visual_part_verifier": str(callout_visual_part_verifier_path) if callout_visual_part_verifier_path else None,
            "table_cell_normalizer": str(table_cell_normalizer_path) if table_cell_normalizer_path else None,
            "feedback_memory": str(feedback_memory_path) if feedback_memory_path else None,
            "leiden_communities": str(leiden_communities_path) if leiden_communities_path else None,
            "community_aware_retrieval": str(community_aware_retrieval_path) if community_aware_retrieval_path else None,
            "final_answer_report": str(final_answer_report_path) if final_answer_report_path else None,
        },
        "outputs": {
            "report": str(report_path),
            "tasks": str(tasks_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
        },
    })

    md = render_markdown(report)
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# TRACE-Net Human Review Queue v1",
        "",
        f"**Status:** {report['status']}",
        f"**Quality:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "review_task_count",
        "critical_priority_review_task_count",
        "high_priority_review_task_count",
        "medium_priority_review_task_count",
        "low_priority_review_task_count",
        "review_page_count",
        "missing_page_id_count",
        "unsafe_review_task_count",
        "review_task_can_answer_directly_count",
        "review_task_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "prompt_injection_review_task_count",
        "table_repair_review_task_count",
        "visual_review_task_count",
        "feedback_review_task_count",
        "community_review_task_count",
    ]:
        lines.append(f"- {key}: {s.get(key)}")
    lines.extend(["", "## Top Review Tasks", ""])
    lines.append("| Priority | Type | Page | Source | Reason |")
    lines.append("|---|---|---|---|---|")
    for task in report.get("review_tasks", [])[:50]:
        lines.append(
            "| {priority} | {task_type} | {page} | {source} | {reason} |".format(
                priority=task.get("priority"),
                task_type=task.get("task_type"),
                page=task.get("page_id") or "-",
                source=task.get("source_stage"),
                reason=sanitize_text(task.get("reason"), 180).replace("|", "\\|"),
            )
        )
    return "\n".join(lines) + "\n"


def render_html(markdown_text: str) -> str:
    return "<html><body><pre>" + html.escape(markdown_text) + "</pre></body></html>"


def quality_report(
    *,
    report_path: str | Path,
    min_review_tasks: int = 1,
    min_high_priority_review_tasks: int = 1,
    require_it_console_quality_pass: bool = False,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path, {})
    quality = compute_quality(
        report,
        min_review_tasks=min_review_tasks,
        min_high_priority_review_tasks=min_high_priority_review_tasks,
        require_it_console_quality_pass=require_it_console_quality_pass,
    )
    if write_json_report:
        quality_path = Path(report_path).with_name("trace_net_human_review_queue_v1_quality.json")
        write_json(quality_path, quality)
        quality["quality_path"] = str(quality_path)
    return quality


def print_build_summary(report: dict[str, Any]) -> None:
    s = report["summary"]
    print("TRACE-Net human review queue v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "review_task_count",
        "critical_priority_review_task_count",
        "high_priority_review_task_count",
        "medium_priority_review_task_count",
        "low_priority_review_task_count",
        "review_page_count",
        "prompt_injection_review_task_count",
        "table_repair_review_task_count",
        "visual_review_task_count",
        "feedback_review_task_count",
        "community_review_task_count",
        "missing_page_id_count",
        "unsafe_review_task_count",
        "review_task_can_answer_directly_count",
        "review_task_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" tasks_path: {report.get('tasks_path')}")
    print(f" quality_path: {report.get('quality_path')}")


def print_quality_summary(quality: dict[str, Any]) -> None:
    s = quality.get("summary", {})
    print("TRACE-Net human review queue v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "review_task_count",
        "critical_priority_review_task_count",
        "high_priority_review_task_count",
        "review_page_count",
        "missing_page_id_count",
        "unsafe_review_task_count",
        "review_task_can_answer_directly_count",
        "review_task_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "raw_feedback_direct_to_llm_count",
    ]:
        print(f" {key}: {s.get(key)}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality['quality_path']}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Human Review Queue v1")
    parser.add_argument("--it-console", dest="it_console_path")
    parser.add_argument("--fishnet-retry-refined", dest="fishnet_retry_refined_path")
    parser.add_argument("--figure-chart-understanding", dest="figure_chart_understanding_path")
    parser.add_argument("--visual-ink-layout-calibrator", dest="visual_ink_layout_calibrator_path")
    parser.add_argument("--callout-visual-part-verifier", dest="callout_visual_part_verifier_path")
    parser.add_argument("--table-cell-normalizer", dest="table_cell_normalizer_path")
    parser.add_argument("--feedback-memory", dest="feedback_memory_path")
    parser.add_argument("--leiden-communities", dest="leiden_communities_path")
    parser.add_argument("--community-aware-retrieval", dest="community_aware_retrieval_path")
    parser.add_argument("--final-answer-report", dest="final_answer_report_path")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/human_review_queue")
    parser.add_argument("--min-review-tasks", type=int, default=1)
    parser.add_argument("--min-high-priority-review-tasks", type=int, default=1)
    parser.add_argument("--require-it-console-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true", dest="write_quality")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_human_review_queue(
        it_console_path=args.it_console_path,
        fishnet_retry_refined_path=args.fishnet_retry_refined_path,
        figure_chart_understanding_path=args.figure_chart_understanding_path,
        visual_ink_layout_calibrator_path=args.visual_ink_layout_calibrator_path,
        callout_visual_part_verifier_path=args.callout_visual_part_verifier_path,
        table_cell_normalizer_path=args.table_cell_normalizer_path,
        feedback_memory_path=args.feedback_memory_path,
        leiden_communities_path=args.leiden_communities_path,
        community_aware_retrieval_path=args.community_aware_retrieval_path,
        final_answer_report_path=args.final_answer_report_path,
        output_dir=args.output_dir,
        min_review_tasks=args.min_review_tasks,
        min_high_priority_review_tasks=args.min_high_priority_review_tasks,
        require_it_console_quality_pass=args.require_it_console_quality_pass,
        write_quality=args.write_quality,
    )
    print_build_summary(report)
    return 0 if report["quality_status"] == "PASS" else 1


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Human Review Queue v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-review-tasks", type=int, default=1)
    parser.add_argument("--min-high-priority-review-tasks", type=int, default=1)
    parser.add_argument("--require-it-console-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def quality_main(argv: list[str] | None = None) -> int:
    args = quality_arg_parser().parse_args(argv)
    quality = quality_report(
        report_path=args.report_path,
        min_review_tasks=args.min_review_tasks,
        min_high_priority_review_tasks=args.min_high_priority_review_tasks,
        require_it_console_quality_pass=args.require_it_console_quality_pass,
        write_json_report=args.write_json,
    )
    print_quality_summary(quality)
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
