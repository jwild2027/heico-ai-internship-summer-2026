"""TRACE-Net WebUI Self-RAG / CRAG Bridge v1.

Runs the current engineering-brain artifact stages for one WebUI-style question
and writes a tool/stage checklist that proves which gates were actually
executed.

This bridge is intentionally pre-answer and artifact-only:
- it does not call Gemma
- it does not replace the WebUI server yet
- it does not execute database/vector/search writes
- it does not mutate source truth
- it does not grant answer permission
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE_VERSION = "trace_net_webui_self_rag_crag_bridge_v1"
REPORT_NAME = "trace_net_webui_self_rag_crag_bridge_v1.json"

STAGE_REPORT_NAMES = {
    "query_planner": "trace_net_engineering_query_planner_v1.json",
    "context_pack_blueprint": "trace_net_engineering_context_pack_blueprint_v1.json",
    "context_pack_builder": "trace_net_engineering_context_pack_builder_v1.json",
    "self_rag": "trace_net_engineering_context_self_rag_check_v1.json",
    "crag_retry": "trace_net_engineering_context_crag_retry_plan_v1.json",
}

ARTIFACT_TOOL_KEYS = {
    "route_dispatch": "fishnet_route_dispatch_handoff",
    "table_route": "table_exact_search_adapter",
    "page_context_v2": "page_context_v2",
    "graph_leiden": "leiden_communities",
    "visual_image_route": "image_visual_observer",
}

SAFETY_COUNT_KEYS = (
    "unsafe_record_count",
    "answer_permission_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _as_path(value: Optional[str]) -> Optional[Path]:
    if value in (None, ""):
        return None
    return Path(value)


def _path_status(path: Optional[Path]) -> str:
    if path is None:
        return "not_configured"
    return "available" if path.exists() else "input_missing"


def _stage_row(
    *,
    tool_id: str,
    label: str,
    status: str,
    reason: str,
    path: Optional[Path] = None,
    count: Optional[int] = None,
    quality_status: Optional[str] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "tool_id": tool_id,
        "label": label,
        "status": status,
        "reason": reason,
    }
    if path is not None:
        row["path"] = str(path)
    if count is not None:
        row["count"] = count
    if quality_status is not None:
        row["quality_status"] = quality_status
    return row


def _safe_summary(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _records(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records = payload.get("records") or []
    return [dict(r) for r in records if isinstance(r, Mapping)]


def _stage_used_row(tool_id: str, label: str, report_path: Path, payload: Mapping[str, Any], count_key: str) -> Dict[str, Any]:
    summary = _safe_summary(payload)
    count = int(summary.get(count_key) or len(_records(payload)) or 0)
    quality = str(payload.get("quality_status") or "UNKNOWN")
    status = "used" if quality == "PASS" and count >= 0 else "failed"
    return _stage_row(
        tool_id=tool_id,
        label=label,
        status=status,
        reason=f"stage report built with quality_status={quality}",
        path=report_path,
        count=count,
        quality_status=quality,
    )


def _artifact_tool_rows(context_pack_payload: Mapping[str, Any], input_paths: Mapping[str, Optional[Path]]) -> List[Dict[str, Any]]:
    summary = _safe_summary(context_pack_payload)
    artifact_counts = summary.get("artifact_record_counts") or {}
    rows: List[Dict[str, Any]] = []
    for tool_id, artifact_name in ARTIFACT_TOOL_KEYS.items():
        path = input_paths.get(tool_id)
        path_state = _path_status(path)
        count = int(artifact_counts.get(artifact_name) or 0)
        if count > 0:
            status = "used"
            reason = f"context pack builder selected/loaded {count} records from {artifact_name}"
        elif path_state == "available":
            status = "available_not_used"
            reason = f"artifact exists but no records were loaded/selected from {artifact_name}"
        elif path_state == "input_missing":
            status = "input_missing"
            reason = f"configured path for {artifact_name} does not exist"
        else:
            status = "not_configured"
            reason = f"no path configured for {artifact_name}"
        rows.append(
            _stage_row(
                tool_id=tool_id,
                label=tool_id.replace("_", "/"),
                status=status,
                reason=reason,
                path=path,
                count=count,
            )
        )
    rows.append(
        _stage_row(
            tool_id="embedding_vector",
            label="embedding/vector",
            status="not_wired_in_bridge",
            reason="this bridge uses the current context-pack artifacts; live vector search is not yet a stage input here",
        )
    )
    return rows


def _crag_row(crag_payload: Mapping[str, Any], crag_path: Path, self_rag_payload: Mapping[str, Any]) -> Dict[str, Any]:
    crag_summary = _safe_summary(crag_payload)
    self_summary = _safe_summary(self_rag_payload)
    quality = str(crag_payload.get("quality_status") or "UNKNOWN")
    plan_count = int(crag_summary.get("crag_retry_plan_count") or 0)
    source_required = int(self_summary.get("crag_retry_required_count") or 0)
    if quality != "PASS":
        status = "failed"
        reason = f"CRAG retry plan report quality_status={quality}"
    elif source_required > 0 and plan_count > 0:
        status = "used"
        reason = f"Self-RAG required retry for {source_required} pack(s), so CRAG produced {plan_count} retry plan(s)"
    elif source_required > 0 and plan_count == 0:
        status = "failed"
        reason = "Self-RAG required retry, but CRAG produced zero retry plans"
    else:
        status = "skipped_not_needed"
        reason = "Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans"
    return _stage_row(
        tool_id="crag_retry",
        label="CRAG retry",
        status=status,
        reason=reason,
        path=crag_path,
        count=plan_count,
        quality_status=quality,
    )


def _checklist_text(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = []
    for row in rows:
        label = str(row.get("label") or row.get("tool_id"))
        status = str(row.get("status"))
        reason = str(row.get("reason") or "")
        if reason:
            lines.append(f"{label}: {status} — {reason}")
        else:
            lines.append(f"{label}: {status}")
    return "\n".join(lines)


def _rollup_safety(stage_payloads: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    totals = {key: 0 for key in SAFETY_COUNT_KEYS}
    for payload in stage_payloads:
        summary = _safe_summary(payload)
        for key in SAFETY_COUNT_KEYS:
            totals[key] += int(summary.get(key) or 0)
        # Record-level fallback for reports that do not put every safety field in summary.
        for record in _records(payload):
            if record.get("unsafe"):
                totals["unsafe_record_count"] += 1
            if record.get("answer_permission"):
                totals["answer_permission_count"] += 1
            if record.get("can_answer_directly"):
                totals["can_answer_directly_count"] += 1
            if record.get("can_prove_claims"):
                totals["can_prove_claims_count"] += 1
            if record.get("source_truth_mutation_allowed"):
                totals["source_truth_mutation_allowed_count"] += 1
            if record.get("postgres_write_attempt"):
                totals["postgres_write_attempt_count"] += 1
            if record.get("qdrant_write_attempt"):
                totals["qdrant_write_attempt_count"] += 1
            if record.get("opensearch_write_attempt"):
                totals["opensearch_write_attempt_count"] += 1
    return totals


def _import_stage_builders() -> Dict[str, Any]:
    from tiff.trace_net_engineering_query_planner_v1 import build_engineering_query_planner
    from tiff.trace_net_engineering_context_pack_blueprint_v1 import build_engineering_context_pack_blueprint
    from tiff.trace_net_engineering_context_pack_builder_v1 import build_engineering_context_pack_builder
    from tiff.trace_net_engineering_context_self_rag_check_v1 import build_engineering_context_self_rag_check
    from tiff.trace_net_engineering_context_crag_retry_plan_v1 import build_engineering_context_crag_retry_plan

    return {
        "query_planner": build_engineering_query_planner,
        "context_pack_blueprint": build_engineering_context_pack_blueprint,
        "context_pack_builder": build_engineering_context_pack_builder,
        "self_rag": build_engineering_context_self_rag_check,
        "crag_retry": build_engineering_context_crag_retry_plan,
    }


def build_webui_self_rag_crag_bridge(
    *,
    question: str,
    kernel_path: Path,
    output_dir: Path,
    route_dispatch_handoff: Optional[Path] = None,
    table_exact_search_adapter: Optional[Path] = None,
    page_context_v2: Optional[Path] = None,
    leiden_communities: Optional[Path] = None,
    image_visual_observer: Optional[Path] = None,
    max_records_per_slot: int = 8,
    min_high_signal_capsules: int = 1,
    min_evidence_strength_score: int = 35,
) -> Dict[str, Any]:
    """Run the live artifact-stage bridge for one question."""
    if not question.strip():
        raise ValueError("question must not be empty")
    if not kernel_path.exists():
        raise FileNotFoundError(f"kernel path does not exist: {kernel_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    stage_dir = output_dir / "stage_reports"
    planner_dir = stage_dir / "query_planner"
    blueprint_dir = stage_dir / "context_pack_blueprint"
    pack_dir = stage_dir / "context_pack_builder"
    self_rag_dir = stage_dir / "self_rag_check"
    crag_dir = stage_dir / "crag_retry_plan"

    builders = _import_stage_builders()

    planner_payload = builders["query_planner"](
        kernel_path=kernel_path,
        output_dir=planner_dir,
        questions=[question],
    )
    planner_path = planner_dir / STAGE_REPORT_NAMES["query_planner"]

    blueprint_payload = builders["context_pack_blueprint"](
        query_planner_path=planner_path,
        output_dir=blueprint_dir,
    )
    blueprint_path = blueprint_dir / STAGE_REPORT_NAMES["context_pack_blueprint"]

    pack_payload = builders["context_pack_builder"](
        blueprint_path=blueprint_path,
        output_dir=pack_dir,
        route_dispatch_handoff=route_dispatch_handoff,
        table_exact_search_adapter=table_exact_search_adapter,
        page_context_v2=page_context_v2,
        leiden_communities=leiden_communities,
        image_visual_observer=image_visual_observer,
        max_records_per_slot=max_records_per_slot,
    )
    pack_path = pack_dir / STAGE_REPORT_NAMES["context_pack_builder"]

    self_rag_payload = builders["self_rag"](
        context_pack_path=pack_path,
        output_dir=self_rag_dir,
        min_high_signal_capsules=min_high_signal_capsules,
        min_evidence_strength_score=min_evidence_strength_score,
    )
    self_rag_path = self_rag_dir / STAGE_REPORT_NAMES["self_rag"]

    # Always build the CRAG report. If Self-RAG does not require retry, the
    # CRAG report should contain zero retry plans and the checklist status is
    # skipped_not_needed rather than falsely used.
    crag_payload = builders["crag_retry"](
        self_rag_report_path=self_rag_path,
        output_dir=crag_dir,
    )
    crag_path = crag_dir / STAGE_REPORT_NAMES["crag_retry"]

    stage_payloads = [planner_payload, blueprint_payload, pack_payload, self_rag_payload, crag_payload]
    stage_paths = {
        "query_planner": planner_path,
        "context_pack_blueprint": blueprint_path,
        "context_pack_builder": pack_path,
        "self_rag": self_rag_path,
        "crag_retry": crag_path,
    }

    rows: List[Dict[str, Any]] = [
        _stage_used_row("query_planner", "query planner", planner_path, planner_payload, "query_plan_count"),
        _stage_used_row("context_pack_blueprint", "context pack blueprint", blueprint_path, blueprint_payload, "context_pack_blueprint_count"),
        _stage_used_row("context_pack_builder", "context pack builder", pack_path, pack_payload, "context_pack_count"),
        _stage_used_row("self_rag", "Self-RAG", self_rag_path, self_rag_payload, "self_rag_record_count"),
        _crag_row(crag_payload, crag_path, self_rag_payload),
    ]
    input_paths = {
        "route_dispatch": route_dispatch_handoff,
        "table_route": table_exact_search_adapter,
        "page_context_v2": page_context_v2,
        "graph_leiden": leiden_communities,
        "visual_image_route": image_visual_observer,
    }
    rows.extend(_artifact_tool_rows(pack_payload, input_paths))
    rows.append(
        _stage_row(
            tool_id="gemma_llm",
            label="Gemma LLM",
            status="not_called_by_design",
            reason="this bridge stops before drafting so Self-RAG/CRAG can be audited separately",
        )
    )
    rows.append(
        _stage_row(
            tool_id="final_gate",
            label="final gate",
            status="not_called_by_design",
            reason="no answer draft is produced by this bridge, so final gate is not invoked here",
        )
    )

    statuses = {row["tool_id"]: row["status"] for row in rows}
    status_counts = Counter(row["status"] for row in rows)
    used_tools = [row["tool_id"] for row in rows if row.get("status") == "used"]
    not_used_tools = [row["tool_id"] for row in rows if row.get("status") not in {"used", "skipped_not_needed"}]
    safety = _rollup_safety(stage_payloads)

    self_summary = _safe_summary(self_rag_payload)
    crag_summary = _safe_summary(crag_payload)
    pack_summary = _safe_summary(pack_payload)
    summary: Dict[str, Any] = {
        "question": question,
        "tool_checklist_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "used_tool_count": len(used_tools),
        "used_tools": used_tools,
        "not_used_tool_count": len(not_used_tools),
        "not_used_tools": not_used_tools,
        "query_planner_used": statuses.get("query_planner") == "used",
        "context_pack_blueprint_used": statuses.get("context_pack_blueprint") == "used",
        "context_pack_builder_used": statuses.get("context_pack_builder") == "used",
        "self_rag_used": statuses.get("self_rag") == "used",
        "crag_retry_status": statuses.get("crag_retry"),
        "crag_retry_evaluated": statuses.get("crag_retry") in {"used", "skipped_not_needed"},
        "self_rag_status_counts": self_summary.get("self_rag_status_counts") or {},
        "self_rag_ready_for_gemma_draft_count": int(self_summary.get("ready_for_gemma_draft_count") or 0),
        "self_rag_crag_retry_required_count": int(self_summary.get("crag_retry_required_count") or 0),
        "crag_retry_plan_count": int(crag_summary.get("crag_retry_plan_count") or 0),
        "crag_ready_for_execution_count": int(crag_summary.get("ready_for_crag_execution_count") or 0),
        "context_pack_count": int(pack_summary.get("context_pack_count") or 0),
        "total_evidence_capsule_count": int(pack_summary.get("total_evidence_capsule_count") or 0),
        "total_high_signal_evidence_capsule_count": int(pack_summary.get("total_high_signal_evidence_capsule_count") or 0),
        "artifact_record_counts": pack_summary.get("artifact_record_counts") or {},
        **safety,
    }

    quality_status = "PASS"
    failures: List[str] = []
    for key, payload in zip(("query_planner", "context_pack_blueprint", "context_pack_builder", "self_rag", "crag_retry"), stage_payloads):
        if payload.get("quality_status") != "PASS":
            failures.append(f"{key} quality_status is not PASS")
    if not summary["query_planner_used"]:
        failures.append("query planner was not used")
    if not summary["context_pack_builder_used"]:
        failures.append("context pack builder was not used")
    if not summary["self_rag_used"]:
        failures.append("Self-RAG was not used")
    if not summary["crag_retry_evaluated"]:
        failures.append("CRAG retry was not evaluated")
    for key in SAFETY_COUNT_KEYS:
        if int(summary.get(key) or 0) != 0:
            failures.append(f"{key} is not zero")
    if failures:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "TRACE_NET_WEBUI_SELF_RAG_CRAG_BRIDGE_BUILT",
        "quality_status": quality_status,
        "failures": failures,
        "question": question,
        "summary": summary,
        "tool_checklist": rows,
        "tool_statuses": statuses,
        "checklist_text": _checklist_text(rows),
        "stage_report_paths": {key: str(path) for key, path in stage_paths.items()},
        "input_paths": {key: str(path) if path else None for key, path in input_paths.items()},
        "thresholds": {
            "max_records_per_slot": max_records_per_slot,
            "min_high_signal_capsules": min_high_signal_capsules,
            "min_evidence_strength_score": min_evidence_strength_score,
        },
        "safety_contract": {
            "artifact_authority": "webui_brain_gate_bridge_audit_only",
            "answers_user_question": False,
            "llm_call_allowed": False,
            "retrieval_execution_allowed": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }

    _write_json(output_dir / REPORT_NAME, payload)
    _write_json(output_dir / "trace_net_webui_self_rag_crag_bridge_v1_summary.json", summary)
    _write_jsonl(output_dir / "trace_net_webui_self_rag_crag_bridge_v1_tool_checklist.jsonl", rows)
    (output_dir / "trace_net_webui_self_rag_crag_bridge_v1_checklist.txt").write_text(
        payload["checklist_text"] + "\n",
        encoding="utf-8",
    )
    _write_markdown(output_dir / "trace_net_webui_self_rag_crag_bridge_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = _safe_summary(payload)
    lines = [
        "# TRACE-Net WebUI Self-RAG / CRAG Bridge v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Question",
        "",
        f"`{payload.get('question')}`",
        "",
        "## Summary",
        "",
        f"- Used tools: `{summary.get('used_tools')}`",
        f"- CRAG retry status: `{summary.get('crag_retry_status')}`",
        f"- Self-RAG status counts: `{summary.get('self_rag_status_counts')}`",
        f"- CRAG retry plans: `{summary.get('crag_retry_plan_count')}`",
        f"- Evidence capsules: `{summary.get('total_evidence_capsule_count')}`",
        "",
        "## Checklist",
        "",
        "```text",
        str(payload.get("checklist_text") or ""),
        "```",
        "",
        "## Safety",
        "",
    ]
    for key in SAFETY_COUNT_KEYS:
        lines.append(f"- {key}: `{summary.get(key)}`")
    path.write_text("\n".join(lines), encoding="utf-8")


def check_webui_self_rag_crag_bridge_quality(
    *,
    report_path: Path,
    min_checklist_count: int = 8,
    min_used_tool_count: int = 4,
    require_query_planner_used: bool = False,
    require_context_pack_builder_used: bool = False,
    require_self_rag_used: bool = False,
    require_crag_evaluated: bool = False,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    require_tool_statuses: Sequence[str] = (),
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = _safe_summary(payload)
    statuses = payload.get("tool_statuses") or {}
    failures: List[str] = []

    def fail_if(condition: bool, message: str) -> None:
        if condition:
            failures.append(message)

    fail_if(payload.get("quality_status") != "PASS", "source bridge report quality_status is not PASS")
    fail_if(int(summary.get("tool_checklist_count") or 0) < min_checklist_count, "not enough checklist rows")
    fail_if(int(summary.get("used_tool_count") or 0) < min_used_tool_count, "not enough used tools")
    if require_query_planner_used:
        fail_if(statuses.get("query_planner") != "used", "query planner was not used")
    if require_context_pack_builder_used:
        fail_if(statuses.get("context_pack_builder") != "used", "context pack builder was not used")
    if require_self_rag_used:
        fail_if(statuses.get("self_rag") != "used", "Self-RAG was not used")
    if require_crag_evaluated:
        fail_if(statuses.get("crag_retry") not in {"used", "skipped_not_needed"}, "CRAG retry was not evaluated")
    if require_no_answer_permission:
        for key in ("answer_permission_count", "can_answer_directly_count", "can_prove_claims_count"):
            fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
    if require_no_source_truth_mutation:
        fail_if(int(summary.get("source_truth_mutation_allowed_count") or 0) != 0, "source_truth_mutation_allowed_count is not zero")
    if require_no_write_attempts:
        for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
            fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
    for requirement in require_tool_statuses:
        if "=" not in requirement:
            failures.append(f"invalid --require-tool-status value: {requirement}")
            continue
        tool_id, expected = requirement.split("=", 1)
        actual = statuses.get(tool_id)
        fail_if(actual != expected, f"tool {tool_id} status {actual!r} != expected {expected!r}")

    return {
        "quality_status": "FAIL" if failures else "PASS",
        "summary": summary,
        "tool_statuses": statuses,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net WebUI Self-RAG / CRAG bridge v1.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--route-dispatch-handoff")
    parser.add_argument("--table-exact-search-adapter")
    parser.add_argument("--page-context-v2")
    parser.add_argument("--leiden-communities")
    parser.add_argument("--image-visual-observer")
    parser.add_argument("--max-records-per-slot", type=int, default=8)
    parser.add_argument("--min-high-signal-capsules", type=int, default=1)
    parser.add_argument("--min-evidence-strength-score", type=int, default=35)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_webui_self_rag_crag_bridge(
        question=args.question,
        kernel_path=Path(args.kernel),
        output_dir=Path(args.output_dir),
        route_dispatch_handoff=_as_path(args.route_dispatch_handoff),
        table_exact_search_adapter=_as_path(args.table_exact_search_adapter),
        page_context_v2=_as_path(args.page_context_v2),
        leiden_communities=_as_path(args.leiden_communities),
        image_visual_observer=_as_path(args.image_visual_observer),
        max_records_per_slot=args.max_records_per_slot,
        min_high_signal_capsules=args.min_high_signal_capsules,
        min_evidence_strength_score=args.min_evidence_strength_score,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    print("Checklist:")
    print(payload.get("checklist_text") or "")
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net WebUI Self-RAG / CRAG bridge v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-checklist-count", type=int, default=8)
    parser.add_argument("--min-used-tool-count", type=int, default=4)
    parser.add_argument("--require-query-planner-used", action="store_true")
    parser.add_argument("--require-context-pack-builder-used", action="store_true")
    parser.add_argument("--require-self-rag-used", action="store_true")
    parser.add_argument("--require-crag-evaluated", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    parser.add_argument("--require-tool-status", action="append", default=[])
    args = parser.parse_args(argv)

    result = check_webui_self_rag_crag_bridge_quality(
        report_path=Path(args.report_path),
        min_checklist_count=args.min_checklist_count,
        min_used_tool_count=args.min_used_tool_count,
        require_query_planner_used=args.require_query_planner_used,
        require_context_pack_builder_used=args.require_context_pack_builder_used,
        require_self_rag_used=args.require_self_rag_used,
        require_crag_evaluated=args.require_crag_evaluated,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
        require_tool_statuses=args.require_tool_status,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    print("Tool statuses:", json.dumps(result["tool_statuses"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_webui_self_rag_crag_bridge_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
