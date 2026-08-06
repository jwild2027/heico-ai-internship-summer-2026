"""TRACE-Net Human Review Promotion Writeback Dry Run v1.

This module converts approved human-review promotion-gate evaluations into a
read-only writeback plan. It never mutates Postgres, Qdrant, OpenSearch, source
files, citations, or graph truth. It only writes local JSON/JSONL/Markdown/HTML
artifacts describing what a later controlled writeback gate *could* do.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_promotion_writeback_dry_run_v1"
STATUS_BUILT = "PROMOTION_WRITEBACK_DRY_RUN_BUILT"
ANSWER_STATUS = "PROMOTION_WRITEBACK_DRY_RUN_ONLY"
ALGORITHM = "trace_net_human_review_promotion_writeback_dry_run_planner_v1"

APPROVED_PROMOTION_STATUSES = {
    "approved",
    "approved_for_controlled_promotion",
    "approved_pending_writeback",
    "controlled_promotion_approved",
    "promotion_approved",
}

PROMOTION_DECISION_TYPES = {
    "approve",
    "confirm_table_repair",
    "confirm_callout",
    "confirm_part_link",
    "confirm_blank",
    "mark_bad_citation",
    "mark_feedback_resolved",
}

FEEDBACK_DECISION_TYPES = {"mark_feedback_resolved", "reject_feedback", "mark_bad_feedback"}
BLANK_DECISION_TYPES = {"confirm_blank"}
CITATION_DECISION_TYPES = {"mark_bad_citation"}
TABLE_DECISION_TYPES = {"confirm_table_repair"}
VISUAL_DECISION_TYPES = {"confirm_callout", "confirm_part_link"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_hash(value: Any, length: int = 16) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return payload


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


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


def unique_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def get_quality_status(payload: dict[str, Any]) -> str:
    for key in ("quality_status", "status"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value.upper()
    quality = payload.get("quality")
    if isinstance(quality, dict):
        value = quality.get("status")
        if isinstance(value, str):
            return value.upper()
    summary = payload.get("summary")
    if isinstance(summary, dict):
        value = summary.get("status") or summary.get("quality_status")
        if isinstance(value, str):
            return value.upper()
    return ""


def extract_promotion_records(promotion_gate: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("promotion_records", "records", "evaluations", "promotion_evaluations"):
        records = promotion_gate.get(key)
        if isinstance(records, list):
            return [r for r in records if isinstance(r, dict)]
    return []


def is_promotion_candidate(record: dict[str, Any]) -> bool:
    if bool(record.get("promotion_candidate")):
        return True
    decision_type = str(record.get("decision_type") or "").strip()
    if decision_type in PROMOTION_DECISION_TYPES:
        return True
    status = str(record.get("promotion_gate_status") or "").strip().lower()
    return status in APPROVED_PROMOTION_STATUSES


def is_approved_promotion(record: dict[str, Any]) -> bool:
    status = str(record.get("promotion_gate_status") or "").strip().lower()
    if status in APPROVED_PROMOTION_STATUSES:
        return True
    if bool(record.get("promotion_approved")):
        return True
    effect = str(record.get("promotion_effect") or "").lower()
    return bool(record.get("promotion_candidate")) and "approve" in effect


def planned_writeback_type(record: dict[str, Any]) -> str:
    decision_type = str(record.get("decision_type") or "").strip()
    effect = str(record.get("promotion_effect") or "").strip()
    target_type = str(record.get("target_type") or "").strip()

    if decision_type in TABLE_DECISION_TYPES or "table" in effect:
        return "promote_reviewed_table_repair_candidate"
    if decision_type in VISUAL_DECISION_TYPES or "visual" in effect or "callout" in effect:
        return "promote_reviewed_visual_part_link_candidate"
    if decision_type in BLANK_DECISION_TYPES:
        return "record_reviewed_blank_source_trace_confirmation"
    if decision_type in CITATION_DECISION_TYPES or target_type == "citation":
        return "record_reviewed_citation_quality_adjustment"
    if decision_type in FEEDBACK_DECISION_TYPES or target_type in {"feedback", "feedback_memory"}:
        return "record_reviewed_feedback_memory_adjustment"
    return "record_reviewed_promotion_candidate"


def required_checks_for_plan(plan_type: str) -> list[str]:
    common = [
        "promotion_gate_status_approved",
        "review_decision_safe",
        "source_truth_mutation_not_allowed",
        "writeback_gate_required",
        "regression_after_writeback_required",
    ]
    if plan_type == "promote_reviewed_table_repair_candidate":
        return common + ["page_id_present", "citation_present", "table_repair_support_present", "catalog_or_graph_support_present"]
    if plan_type == "promote_reviewed_visual_part_link_candidate":
        return common + ["page_id_present", "visual_or_callout_support_present", "catalog_or_graph_support_present", "citation_or_review_reference_present"]
    if plan_type == "record_reviewed_blank_source_trace_confirmation":
        return common + ["page_id_present", "blank_source_trace_preservation_present"]
    if plan_type == "record_reviewed_citation_quality_adjustment":
        return common + ["citation_id_or_target_present", "page_or_target_present"]
    if plan_type == "record_reviewed_feedback_memory_adjustment":
        return common + ["feedback_target_present", "raw_feedback_not_sent_to_llm"]
    return common + ["page_or_target_present"]


def plan_requires_page(plan_type: str) -> bool:
    return plan_type in {
        "promote_reviewed_table_repair_candidate",
        "promote_reviewed_visual_part_link_candidate",
        "record_reviewed_blank_source_trace_confirmation",
    }


def plan_requires_citation(plan_type: str) -> bool:
    return plan_type in {"promote_reviewed_table_repair_candidate"}


def make_writeback_plan(record: dict[str, Any]) -> dict[str, Any]:
    plan_type = planned_writeback_type(record)
    page_ids = unique_strings(record.get("page_ids") or record.get("affected_page_ids") or [])
    citation_ids = unique_strings(record.get("citation_ids") or record.get("affected_citation_ids") or [])
    community_ids = unique_strings(record.get("community_ids") or record.get("affected_community_ids") or [])
    part_numbers = unique_strings(record.get("part_numbers") or record.get("affected_part_numbers") or [])
    target_type = str(record.get("target_type") or "promotion_evaluation")
    target_id = str(record.get("target_id") or record.get("promotion_evaluation_id") or record.get("review_decision_id") or "")
    required_checks = required_checks_for_plan(plan_type)
    missing_checks: list[str] = []

    if plan_requires_page(plan_type) and not page_ids:
        missing_checks.append("page_id_present")
    if plan_requires_citation(plan_type) and not citation_ids:
        missing_checks.append("citation_present")

    if not target_id:
        missing_checks.append("target_id_present")

    status = "planned_pending_writeback_gate" if not missing_checks else "blocked_missing_required_support"

    plan = {
        "writeback_plan_id": "hrwb__" + stable_hash(record),
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "writeback_mode": "dry_run",
        "writeback_status": status,
        "planned_writeback_type": plan_type,
        "promotion_evaluation_id": record.get("promotion_evaluation_id"),
        "review_decision_id": record.get("review_decision_id"),
        "decision_type": record.get("decision_type"),
        "promotion_gate_status": record.get("promotion_gate_status"),
        "promotion_effect": record.get("promotion_effect"),
        "target_type": target_type,
        "target_id": target_id,
        "page_ids": page_ids,
        "citation_ids": citation_ids,
        "community_ids": community_ids,
        "part_numbers": part_numbers,
        "required_checks": required_checks,
        "missing_required_checks": missing_checks,
        "failed_check_count": len(missing_checks),
        "requires_writeback_gate": True,
        "requires_regression_after_writeback": True,
        "requires_source_resolution": True,
        "requires_citation": plan_requires_citation(plan_type),
        "requires_authority_gate": True,
        "requires_quality_gate": True,
        "requires_reindex_after_writeback": plan_type.startswith("promote_") or plan_type.startswith("record_reviewed_citation"),
        "requires_qdrant_refresh": plan_type.startswith("promote_") or plan_type.startswith("record_reviewed_citation"),
        "requires_opensearch_refresh": plan_type.startswith("promote_") or plan_type.startswith("record_reviewed_citation"),
        "requires_graph_refresh": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
        "final_answer_allowed": False,
        "notes": "Dry-run writeback plan only; no source, graph, vector, keyword, or trust mutation performed.",
    }
    return plan


def build_summary(
    promotion_gate: dict[str, Any],
    promotion_records: list[dict[str, Any]],
    writeback_plans: list[dict[str, Any]],
    min_writeback_plans: int,
    require_promotion_gate_quality_pass: bool,
) -> dict[str, Any]:
    gate_quality_status = get_quality_status(promotion_gate)
    promotion_candidate_count = sum(1 for r in promotion_records if is_promotion_candidate(r))
    approved_candidate_count = sum(1 for r in promotion_records if is_approved_promotion(r))
    plan_type_counts: dict[str, int] = {}
    for plan in writeback_plans:
        key = str(plan.get("planned_writeback_type") or "unknown")
        plan_type_counts[key] = plan_type_counts.get(key, 0) + 1

    def count_true(key: str) -> int:
        return sum(1 for p in writeback_plans if bool(p.get(key)))

    missing_page = sum(1 for p in writeback_plans if plan_requires_page(str(p.get("planned_writeback_type"))) and not p.get("page_ids"))
    missing_citation = sum(1 for p in writeback_plans if plan_requires_citation(str(p.get("planned_writeback_type"))) and not p.get("citation_ids"))

    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "PASS",
        "answer_status": ANSWER_STATUS,
        "writeback_mode": "dry_run",
        "promotion_gate_quality_status": gate_quality_status,
        "promotion_gate_quality_required": bool(require_promotion_gate_quality_pass),
        "promotion_record_count": len(promotion_records),
        "promotion_candidate_count": promotion_candidate_count,
        "approved_promotion_candidate_count": approved_candidate_count,
        "writeback_plan_count": len(writeback_plans),
        "writeback_plan_type_counts": plan_type_counts,
        "writeback_plan_missing_page_id_count": missing_page,
        "writeback_plan_missing_citation_count": missing_citation,
        "blocked_writeback_plan_count": sum(1 for p in writeback_plans if p.get("writeback_status") == "blocked_missing_required_support"),
        "planned_pending_writeback_gate_count": sum(1 for p in writeback_plans if p.get("writeback_status") == "planned_pending_writeback_gate"),
        "requires_regression_after_writeback_count": count_true("requires_regression_after_writeback"),
        "requires_qdrant_refresh_count": count_true("requires_qdrant_refresh"),
        "requires_opensearch_refresh_count": count_true("requires_opensearch_refresh"),
        "requires_graph_refresh_count": count_true("requires_graph_refresh"),
        "postgres_write_attempt_count": count_true("postgres_write_attempted"),
        "qdrant_write_attempt_count": count_true("qdrant_write_attempted"),
        "opensearch_write_attempt_count": count_true("opensearch_write_attempted"),
        "source_truth_mutation_allowed_count": count_true("source_truth_mutation_allowed"),
        "source_truth_mutations_performed": sum(int(p.get("source_truth_mutations_performed") or 0) for p in writeback_plans),
        "direct_answer_allowed_count": count_true("can_answer_directly"),
        "claim_proof_allowed_count": count_true("can_prove_claims"),
        "final_answer_allowed_count": count_true("final_answer_allowed"),
        "unsafe_writeback_plan_count": 0,
        "no_op_planned": len(writeback_plans) == 0,
        "minimum_writeback_plan_required": int(min_writeback_plans),
    }
    return summary


def quality_report(report: dict[str, Any], *, min_writeback_plans: int = 0, require_promotion_gate_quality_pass: bool = False) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else report
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any = None, expected: Any = None, severity: str = "critical") -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected, "severity": severity})

    add("writeback_plan_count_min", int(summary.get("writeback_plan_count", 0)) >= min_writeback_plans, summary.get("writeback_plan_count"), f">= {min_writeback_plans}")
    add("writeback_mode_dry_run", summary.get("writeback_mode") == "dry_run", summary.get("writeback_mode"), "dry_run")
    if require_promotion_gate_quality_pass:
        add("promotion_gate_quality_pass", str(summary.get("promotion_gate_quality_status") or "").upper() == "PASS", summary.get("promotion_gate_quality_status"), "PASS")
    add("no_postgres_writes", int(summary.get("postgres_write_attempt_count", 0)) == 0, summary.get("postgres_write_attempt_count"), 0)
    add("no_qdrant_writes", int(summary.get("qdrant_write_attempt_count", 0)) == 0, summary.get("qdrant_write_attempt_count"), 0)
    add("no_opensearch_writes", int(summary.get("opensearch_write_attempt_count", 0)) == 0, summary.get("opensearch_write_attempt_count"), 0)
    add("no_source_truth_mutation_allowed", int(summary.get("source_truth_mutation_allowed_count", 0)) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("no_source_truth_mutations_performed", int(summary.get("source_truth_mutations_performed", 0)) == 0, summary.get("source_truth_mutations_performed"), 0)
    add("no_direct_answer_permission", int(summary.get("direct_answer_allowed_count", 0)) == 0, summary.get("direct_answer_allowed_count"), 0)
    add("no_claim_proof_permission", int(summary.get("claim_proof_allowed_count", 0)) == 0, summary.get("claim_proof_allowed_count"), 0)
    add("no_final_answer_permission", int(summary.get("final_answer_allowed_count", 0)) == 0, summary.get("final_answer_allowed_count"), 0)
    add("no_unsafe_writeback_plans", int(summary.get("unsafe_writeback_plan_count", 0)) == 0, summary.get("unsafe_writeback_plan_count"), 0)
    add("no_approved_table_plan_without_citation", int(summary.get("writeback_plan_missing_citation_count", 0)) == 0, summary.get("writeback_plan_missing_citation_count"), 0)
    add("no_page_scoped_plan_without_page", int(summary.get("writeback_plan_missing_page_id_count", 0)) == 0, summary.get("writeback_plan_missing_page_id_count"), 0)

    failed = [c for c in checks if not c["passed"] and c.get("severity") == "critical"]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION + "_quality",
        "status": status,
        "quality_status": status,
        "checks": checks,
        "failed_check_count": len(failed),
        "writeback_plan_count": int(summary.get("writeback_plan_count", 0)),
        "promotion_candidate_count": int(summary.get("promotion_candidate_count", 0)),
        "approved_promotion_candidate_count": int(summary.get("approved_promotion_candidate_count", 0)),
        "postgres_write_attempt_count": int(summary.get("postgres_write_attempt_count", 0)),
        "source_truth_mutation_allowed_count": int(summary.get("source_truth_mutation_allowed_count", 0)),
        "direct_answer_allowed_count": int(summary.get("direct_answer_allowed_count", 0)),
        "claim_proof_allowed_count": int(summary.get("claim_proof_allowed_count", 0)),
    }


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TRACE-Net Human Review Promotion Writeback Dry Run v1",
        "",
        f"**Status:** {report['status']}",
        f"**Quality:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "writeback_mode",
        "promotion_record_count",
        "promotion_candidate_count",
        "approved_promotion_candidate_count",
        "writeback_plan_count",
        "planned_pending_writeback_gate_count",
        "blocked_writeback_plan_count",
        "postgres_write_attempt_count",
        "source_truth_mutation_allowed_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "no_op_planned",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Planned Writebacks", ""])
    plans = report.get("writeback_plans", [])
    if not plans:
        lines.append("No approved promotion records required writeback planning.")
    else:
        lines.append("| Plan | Type | Status | Pages | Citations | Target |")
        lines.append("|---|---|---|---:|---:|---|")
        for p in plans[:100]:
            lines.append(
                f"| {p.get('writeback_plan_id')} | {p.get('planned_writeback_type')} | {p.get('writeback_status')} | "
                f"{len(p.get('page_ids') or [])} | {len(p.get('citation_ids') or [])} | {p.get('target_type')}:{p.get('target_id')} |"
            )
    lines.extend([
        "",
        "## Safety Contract",
        "",
        "This artifact is a dry-run plan only. It performs no database, graph, vector, keyword, source, citation, trust, or answer writeback.",
    ])
    return "\n".join(lines) + "\n"


def write_html(path: str | Path, markdown_text: str) -> None:
    body = html.escape(markdown_text)
    html_text = "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Promotion Writeback Dry Run</title>"
    html_text += "<style>body{font-family:Arial,sans-serif;margin:2rem;line-height:1.45;}pre{white-space:pre-wrap;background:#f6f8fa;padding:1rem;border-radius:8px;}</style>"
    html_text += "</head><body><pre>" + body + "</pre></body></html>\n"
    Path(path).write_text(html_text, encoding="utf-8")


def build_promotion_writeback_dry_run(
    promotion_gate_path: str | Path,
    output_dir: str | Path,
    *,
    review_decisions_path: str | Path | None = None,
    triage_report_path: str | Path | None = None,
    min_writeback_plans: int = 0,
    require_promotion_gate_quality_pass: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    promotion_gate = read_json(promotion_gate_path)
    review_decisions = read_json(review_decisions_path) if review_decisions_path else None
    triage_report = read_json(triage_report_path) if triage_report_path else None

    promotion_records = extract_promotion_records(promotion_gate)
    approved_records = [r for r in promotion_records if is_approved_promotion(r)]
    writeback_plans = [make_writeback_plan(r) for r in approved_records]

    summary = build_summary(
        promotion_gate,
        promotion_records,
        writeback_plans,
        min_writeback_plans,
        require_promotion_gate_quality_pass,
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": "PASS",
        "answer_status": ANSWER_STATUS,
        "generated_at": utc_now_iso(),
        "algorithm": ALGORITHM,
        "source_paths": {
            "promotion_gate": str(promotion_gate_path),
            "review_decisions": str(review_decisions_path) if review_decisions_path else None,
            "triage_report": str(triage_report_path) if triage_report_path else None,
        },
        "source_summaries": {
            "promotion_gate_quality_status": get_quality_status(promotion_gate),
            "review_decisions_quality_status": get_quality_status(review_decisions) if review_decisions else None,
            "triage_quality_status": get_quality_status(triage_report) if triage_report else None,
        },
        "summary": summary,
        "writeback_plans": writeback_plans,
        "promotion_records_snapshot": promotion_records,
    }

    quality = quality_report(
        report,
        min_writeback_plans=min_writeback_plans,
        require_promotion_gate_quality_pass=require_promotion_gate_quality_pass,
    )
    report["quality"] = quality
    report["quality_status"] = quality["quality_status"]
    summary["status"] = quality["quality_status"]

    report_path = output / "trace_net_promotion_writeback_dry_run_v1.json"
    plans_path = output / "trace_net_promotion_writeback_dry_run_v1_plans.jsonl"
    summary_path = output / "trace_net_promotion_writeback_dry_run_v1_summary.json"
    manifest_path = output / "trace_net_promotion_writeback_dry_run_v1_manifest.json"
    quality_path = output / "trace_net_promotion_writeback_dry_run_v1_quality.json"
    markdown_path = output / "trace_net_promotion_writeback_dry_run_v1.md"
    html_path = output / "trace_net_promotion_writeback_dry_run_v1.html"

    manifest = {
        "schema_version": SCHEMA_VERSION + "_manifest",
        "generated_at": report["generated_at"],
        "report_path": str(report_path),
        "plans_path": str(plans_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
        "writeback_mode": "dry_run",
        "source_paths": report["source_paths"],
    }

    write_json(report_path, report)
    write_jsonl(plans_path, writeback_plans)
    write_json(summary_path, summary)
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, quality)
    else:
        write_json(quality_path, quality)
    markdown_text = build_markdown(report)
    markdown_path.write_text(markdown_text, encoding="utf-8")
    write_html(html_path, markdown_text)

    report.update({
        "report_path": str(report_path),
        "plans_path": str(plans_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "quality_path": str(quality_path),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
    })
    return report


# Compatibility aliases for tests/scripts.
run_promotion_writeback_dry_run = build_promotion_writeback_dry_run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net promotion writeback dry-run plan v1")
    parser.add_argument("--promotion-gate", required=True, help="Path to human review promotion gate report JSON")
    parser.add_argument("--review-decisions", help="Optional human review decisions report JSON")
    parser.add_argument("--triage-report", help="Optional human review triage report JSON")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--min-writeback-plans", type=int, default=0)
    parser.add_argument("--require-promotion-gate-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true", help="Write quality report and print quality status")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_promotion_writeback_dry_run(
            args.promotion_gate,
            args.output_dir,
            review_decisions_path=args.review_decisions,
            triage_report_path=args.triage_report,
            min_writeback_plans=args.min_writeback_plans,
            require_promotion_gate_quality_pass=args.require_promotion_gate_quality_pass,
            write_quality=args.quality,
        )
    except Exception as exc:  # pragma: no cover - CLI safety
        print(f"TRACE-Net promotion writeback dry run failed: {exc}")
        return 1

    summary = report["summary"]
    print("TRACE-Net promotion writeback dry run v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" writeback_mode: {summary['writeback_mode']}")
    print(f" review_promotion_record_count: {summary['promotion_record_count']}")
    print(f" promotion_candidate_count: {summary['promotion_candidate_count']}")
    print(f" approved_promotion_candidate_count: {summary['approved_promotion_candidate_count']}")
    print(f" writeback_plan_count: {summary['writeback_plan_count']}")
    print(f" planned_pending_writeback_gate_count: {summary['planned_pending_writeback_gate_count']}")
    print(f" postgres_write_attempt_count: {summary['postgres_write_attempt_count']}")
    print(f" source_truth_mutation_allowed_count: {summary['source_truth_mutation_allowed_count']}")
    print(f" direct_answer_allowed_count: {summary['direct_answer_allowed_count']}")
    print(f" claim_proof_allowed_count: {summary['claim_proof_allowed_count']}")
    print(f" report_path: {report['report_path']}")
    print(f" quality_path: {report['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
