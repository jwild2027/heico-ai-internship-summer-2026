"""TRACE-Net Engineering WebUI Answer Server v1.3 + Self-RAG/CRAG bridge v1.

This module wraps the active v1.3 WebUI answer server with a live pre-answer
engineering-brain bridge:

question -> Self-RAG/CRAG bridge -> v1.3 answer composer -> trace checklist

It intentionally preserves the v1.3 answer behavior and model id, while adding
an auditable preflight gate that proves query planning, context pack building,
Self-RAG, and CRAG evaluation ran for the request.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from tiff.trace_net_engineering_webui_answer_server_v1_3 import (
    DEFAULT_FINAL_GATE,
    DEFAULT_FISHNET,
    DEFAULT_PAGE_CONTEXT,
    DEFAULT_ROUTE_HANDOFF,
    DEFAULT_RUNNER,
    LLMConfig,
    MODEL_ID,
    _add_llm_args,
    _llm_config_from_args,
    _read_json,
    _write_json,
    _write_jsonl,
    answer_question_v13,
    load_gated_drafts,
    load_page_index,
)
from tiff.trace_net_webui_self_rag_crag_bridge_v1 import (
    REPORT_NAME as BRIDGE_REPORT_NAME,
    build_webui_self_rag_crag_bridge,
)

MODULE_VERSION = "trace_net_engineering_webui_answer_server_v1_3_bridge_v1"
REPORT_NAME = "trace_net_engineering_webui_answer_server_v1_3_bridge_v1.json"

DEFAULT_KERNEL = Path("local_data/organization/trace_net/engineering_reasoning_kernel/trace_net_engineering_reasoning_kernel_v1.json")
DEFAULT_TABLE_EXACT_SEARCH = Path("local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json")
DEFAULT_LEIDEN_COMMUNITIES = Path("local_data/organization/trace_net/leiden_communities/trace_net_leiden_communities_v1.json")
DEFAULT_IMAGE_VISUAL_OBSERVER = Path("local_data/organization/trace_net/image_visual_observer/trace_net_image_visual_observer_v1.json")
DEFAULT_WEBUI_VISUAL_CONTEXT_BRIDGE = Path("local_data/organization/trace_net/webui_visual_context_bridge/trace_net_webui_visual_context_bridge_v1.json")
DEFAULT_BRIDGE_OUTPUT_DIR = Path("local_data/organization/trace_net/webui_self_rag_crag_bridge_live")

SAFETY_COUNT_KEYS = (
    "answer_permission_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "unsafe_record_count",
)


@dataclass(frozen=True)
class BridgeConfig:
    """Runtime configuration for the WebUI Self-RAG/CRAG preflight bridge."""

    enabled: bool = True
    kernel_path: Path = DEFAULT_KERNEL
    output_dir: Path = DEFAULT_BRIDGE_OUTPUT_DIR
    route_dispatch_handoff: Optional[Path] = DEFAULT_ROUTE_HANDOFF
    table_exact_search_adapter: Optional[Path] = DEFAULT_TABLE_EXACT_SEARCH
    page_context_v2: Optional[Path] = DEFAULT_PAGE_CONTEXT
    leiden_communities: Optional[Path] = DEFAULT_LEIDEN_COMMUNITIES
    image_visual_observer: Optional[Path] = DEFAULT_IMAGE_VISUAL_OBSERVER
    webui_visual_context_bridge: Optional[Path] = DEFAULT_WEBUI_VISUAL_CONTEXT_BRIDGE
    max_records_per_slot: int = 8
    min_high_signal_capsules: int = 1
    min_evidence_strength_score: int = 35
    allow_answer_if_bridge_fails: bool = False
    cli_fallback_enabled: bool = True


def _as_path(value: Optional[str]) -> Optional[Path]:
    if value in (None, ""):
        return None
    return Path(str(value))


def _safe_slug(text: str, *, max_chars: int = 60) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
    slug = slug.strip("._-") or "question"
    return slug[:max_chars]


def _new_request_dir(base_dir: Path, question: str) -> Path:
    stamp = int(time.time() * 1000)
    return base_dir / f"request_{stamp}_{_safe_slug(question)}"


def _summary(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, Mapping) else {}


def _statuses(payload: Mapping[str, Any]) -> Dict[str, str]:
    value = payload.get("tool_statuses")
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, Mapping) else {}


def _bridge_passed(payload: Mapping[str, Any]) -> bool:
    summary = _summary(payload)
    statuses = _statuses(payload)
    return (
        payload.get("quality_status") == "PASS"
        and statuses.get("query_planner") == "used"
        and statuses.get("context_pack_builder") == "used"
        and statuses.get("self_rag") == "used"
        and statuses.get("crag_retry") in {"used", "skipped_not_needed"}
        and int(summary.get("answer_permission_count") or 0) == 0
        and int(summary.get("source_truth_mutation_allowed_count") or 0) == 0
    )



def _ensure_bridge_stage_dirs(target_dir: Path) -> None:
    """Pre-create bridge stage directories before in-process or CLI bridge runs.

    Some stage builders write JSONL sidecars directly with ``Path.open("w")``
    and expect their output directory to already exist. The standalone bridge is
    now safe on fresh directories, but the WebUI wrapper also guarantees the
    nested sample/live preflight tree before it calls either the in-process
    bridge or the CLI fallback.
    """
    stage_root = target_dir / "stage_reports"
    for name in (
        "query_planner",
        "context_pack_blueprint",
        "context_pack_builder",
        "self_rag_check",
        "crag_retry_plan",
    ):
        (stage_root / name).mkdir(parents=True, exist_ok=True)




def _patch_stage_writer_parent_dirs_for_in_process_bridge() -> None:
    """Make known engineering stage writer helpers parent-directory safe.

    Some older stage modules write JSON/JSONL/Markdown sidecars by calling
    ``Path.open("w")`` directly. The standalone bridge now pre-creates its
    own stage directories, but the WebUI wrapper can still exercise older
    imported writer helpers through nested sample/live preflight folders. This
    lightweight in-process patch preserves each stage builder and only ensures
    the target file parent exists before the original writer runs.
    """
    import importlib

    module_names = (
        "tiff.trace_net_engineering_query_planner_v1",
        "tiff.trace_net_engineering_context_pack_blueprint_v1",
        "tiff.trace_net_engineering_context_pack_builder_v1",
        "tiff.trace_net_engineering_context_self_rag_check_v1",
        "tiff.trace_net_engineering_context_crag_retry_plan_v1",
    )
    writer_names = ("_write_json", "_write_jsonl", "_write_markdown")

    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for writer_name in writer_names:
            original = getattr(module, writer_name, None)
            if not callable(original) or getattr(original, "_trace_net_parent_dir_safe", False):
                continue

            def _safe_writer(path, *args, __original=original, **kwargs):
                file_path = Path(path)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                return __original(file_path, *args, **kwargs)

            _safe_writer._trace_net_parent_dir_safe = True  # type: ignore[attr-defined]
            _safe_writer.__name__ = getattr(original, "__name__", writer_name)
            _safe_writer.__doc__ = getattr(original, "__doc__", None)
            setattr(module, writer_name, _safe_writer)


def _bridge_status_payload(question: str, bridge_payload: Mapping[str, Any], *, bridge_report_path: Optional[Path] = None) -> Dict[str, Any]:
    summary = dict(_summary(bridge_payload))
    statuses = _statuses(bridge_payload)
    return {
        "webui_self_rag_crag_bridge_used": _bridge_passed(bridge_payload),
        "webui_self_rag_crag_bridge_quality_status": bridge_payload.get("quality_status"),
        "webui_self_rag_crag_bridge_status": bridge_payload.get("status"),
        "webui_self_rag_crag_bridge_report_path": str(bridge_report_path) if bridge_report_path else None,
        "webui_self_rag_crag_bridge_checklist_text": bridge_payload.get("checklist_text") or "",
        "webui_self_rag_crag_bridge_tool_statuses": statuses,
        "webui_self_rag_crag_bridge_used_tools": summary.get("used_tools") or [],
        "query_planner_used": statuses.get("query_planner") == "used",
        "context_pack_builder_used": statuses.get("context_pack_builder") == "used",
        "self_rag_used": statuses.get("self_rag") == "used",
        "crag_retry_status": statuses.get("crag_retry"),
        "crag_retry_evaluated": statuses.get("crag_retry") in {"used", "skipped_not_needed"},
        "crag_retry_plan_count": int(summary.get("crag_retry_plan_count") or 0),
        "self_rag_ready_for_gemma_draft_count": int(summary.get("self_rag_ready_for_gemma_draft_count") or 0),
        "self_rag_crag_retry_required_count": int(summary.get("self_rag_crag_retry_required_count") or 0),
        "context_pack_count": int(summary.get("context_pack_count") or 0),
        "total_evidence_capsule_count": int(summary.get("total_evidence_capsule_count") or 0),
        "total_high_signal_evidence_capsule_count": int(summary.get("total_high_signal_evidence_capsule_count") or 0),
        "webui_self_rag_crag_bridge_in_process_error": bridge_payload.get("in_process_error"),
        "webui_self_rag_crag_bridge_cli_fallback_used": bool(bridge_payload.get("cli_fallback_used")),
        "webui_visual_context_bridge_used": bool(summary.get("webui_visual_context_bridge_used")),
        "webui_visual_context_bridge_quality_status": summary.get("webui_visual_context_bridge_quality_status"),
        "visual_image_route_used": bool(summary.get("visual_image_route_used")),
        "visual_context_card_count": int(summary.get("visual_context_card_count") or 0),
        "review_only_visual_context_excluded_count": int(summary.get("review_only_visual_context_excluded_count") or 0),
        "visual_context_included_pages": summary.get("visual_context_included_pages") or [],
        "visual_context_included_canonical_page_numbers": summary.get("visual_context_included_canonical_page_numbers") or [],
        "webui_visual_context_cards": bridge_payload.get("webui_visual_context_cards") or [],
        "bridge_question": question,
        # These explicit nested keys are intentionally visible to the E2E tool
        # usage audit's flattened trace scanner.
        "self_rag": {"status": statuses.get("self_rag"), "used": statuses.get("self_rag") == "used"},
        "crag_retry": {"status": statuses.get("crag_retry"), "evaluated": statuses.get("crag_retry") in {"used", "skipped_not_needed"}},
        "graph_leiden": {"status": statuses.get("graph_leiden")},
        "route_dispatch": {"status": statuses.get("route_dispatch")},
        "table_route": {"status": statuses.get("table_route")},
        "page_context_v2": {"status": statuses.get("page_context_v2")},
        "visual_image_route": {"status": statuses.get("visual_image_route"), "used": statuses.get("visual_image_route") == "used"},
        "webui_visual_context_bridge": {"status": statuses.get("webui_visual_context_bridge"), "used": statuses.get("webui_visual_context_bridge") == "used"},
    }


def merge_bridge_trace(answer_record: Mapping[str, Any], bridge_payload: Mapping[str, Any], *, bridge_report_path: Optional[Path] = None) -> Dict[str, Any]:
    """Attach bridge results to an existing v1.3 answer trace record."""
    merged = dict(answer_record)
    merged.update(_bridge_status_payload(str(answer_record.get("question") or ""), bridge_payload, bridge_report_path=bridge_report_path))
    # Preserve safety counters. The bridge is pre-answer and must not authorize.
    merged["answer_permission"] = False
    merged["can_answer_directly"] = False
    merged["can_prove_claims"] = False
    merged["source_truth_mutation_allowed"] = False
    merged["postgres_write_attempt"] = False
    merged["qdrant_write_attempt"] = False
    merged["opensearch_write_attempt"] = False
    return merged


def bridge_failure_record(question: str, *, error: str, bridge_payload: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return a controlled no-answer trace when the pre-answer bridge fails."""
    record: Dict[str, Any] = {
        "question": question,
        "response_text": (
            "TRACE-Net did not produce an answer because the Self-RAG/CRAG preflight bridge did not pass. "
            "This is a controlled safety stop, not a source-truth answer."
        ),
        "intent": "bridge_preflight",
        "evidence_status": "bridge_preflight_failed",
        "response_kind": "controlled_bridge_preflight_block",
        "citations": [],
        "citation_count": 0,
        "llm_called": False,
        "llm_model": None,
        "llm_error": error,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "unsafe": False,
    }
    if bridge_payload:
        record.update(_bridge_status_payload(question, bridge_payload))
    else:
        record.update(
            {
                "webui_self_rag_crag_bridge_used": False,
                "webui_self_rag_crag_bridge_quality_status": "ERROR",
                "webui_self_rag_crag_bridge_error": error,
                "query_planner_used": False,
                "context_pack_builder_used": False,
                "self_rag_used": False,
                "crag_retry_evaluated": False,
            }
        )
    return record


def _bridge_cli_command(question: str, config: BridgeConfig, target_dir: Path) -> List[str]:
    """Build the exact CLI fallback command for the already-passing bridge script."""
    cmd = [
        sys.executable,
        "scripts/build/validation/build_trace_net_webui_self_rag_crag_bridge_v1.py",
        "--question",
        question,
        "--kernel",
        str(config.kernel_path),
        "--output-dir",
        str(target_dir),
        "--max-records-per-slot",
        str(config.max_records_per_slot),
        "--min-high-signal-capsules",
        str(config.min_high_signal_capsules),
        "--min-evidence-strength-score",
        str(config.min_evidence_strength_score),
        "--quality",
    ]
    optional_args = [
        ("--route-dispatch-handoff", config.route_dispatch_handoff),
        ("--table-exact-search-adapter", config.table_exact_search_adapter),
        ("--page-context-v2", config.page_context_v2),
        ("--leiden-communities", config.leiden_communities),
        ("--image-visual-observer", config.image_visual_observer),
        ("--webui-visual-context-bridge", config.webui_visual_context_bridge),
    ]
    for flag, path in optional_args:
        if path is not None:
            cmd.extend([flag, str(path)])
    return cmd


def _run_bridge_cli_fallback(question: str, config: BridgeConfig, target_dir: Path, *, in_process_error: Exception) -> Tuple[Dict[str, Any], Path]:
    """Run the bridge through its CLI when the in-process call raises.

    Justin already validated the standalone bridge command. The WebUI wrapper should
    therefore fall back to the same CLI path instead of silently blocking because
    of an import/runtime mismatch in the wrapper layer.
    """
    _ensure_bridge_stage_dirs(target_dir)
    report_path = target_dir / BRIDGE_REPORT_NAME
    cmd = _bridge_cli_command(question, config, target_dir)
    result = subprocess.run(cmd, text=True, capture_output=True)
    if report_path.exists():
        payload = _read_json(report_path, required=True)
        payload["in_process_error"] = f"{type(in_process_error).__name__}: {in_process_error}"
        payload["cli_fallback_used"] = True
        payload["cli_fallback_returncode"] = result.returncode
        payload["cli_fallback_stdout_tail"] = (result.stdout or "")[-4000:]
        payload["cli_fallback_stderr_tail"] = (result.stderr or "")[-4000:]
        _write_json(report_path, payload)
        return payload, report_path
    raise RuntimeError(
        "Self-RAG/CRAG bridge failed in-process and CLI fallback did not write a report: "
        f"in_process={type(in_process_error).__name__}: {in_process_error}; "
        f"cli_returncode={result.returncode}; stderr={(result.stderr or '')[-1000:]}"
    )


def run_bridge_preflight(question: str, config: BridgeConfig, *, output_dir: Optional[Path] = None) -> Tuple[Dict[str, Any], Path]:
    """Run the Self-RAG/CRAG bridge and return payload plus report path."""
    if not config.enabled:
        payload = {
            "module": MODULE_VERSION,
            "status": "TRACE_NET_WEBUI_SELF_RAG_CRAG_BRIDGE_DISABLED",
            "quality_status": "FAIL",
            "summary": {"question": question},
            "tool_statuses": {},
            "checklist_text": "Self-RAG/CRAG bridge: disabled",
        }
        return payload, output_dir or config.output_dir
    target_dir = output_dir or _new_request_dir(config.output_dir, question)
    _patch_stage_writer_parent_dirs_for_in_process_bridge()
    _ensure_bridge_stage_dirs(target_dir)
    try:
        payload = build_webui_self_rag_crag_bridge(
            question=question,
            kernel_path=config.kernel_path,
            output_dir=target_dir,
            route_dispatch_handoff=config.route_dispatch_handoff,
            table_exact_search_adapter=config.table_exact_search_adapter,
            page_context_v2=config.page_context_v2,
            leiden_communities=config.leiden_communities,
            image_visual_observer=config.image_visual_observer,
            webui_visual_context_bridge=config.webui_visual_context_bridge,
            max_records_per_slot=config.max_records_per_slot,
            min_high_signal_capsules=config.min_high_signal_capsules,
            min_evidence_strength_score=config.min_evidence_strength_score,
        )
        payload["cli_fallback_used"] = False
        return payload, target_dir / BRIDGE_REPORT_NAME
    except Exception as exc:
        if config.cli_fallback_enabled:
            return _run_bridge_cli_fallback(question, config, target_dir, in_process_error=exc)
        raise


def answer_question_with_bridge_v1(
    *,
    question: str,
    pages: Sequence[Mapping[str, Any]],
    gated_drafts: Sequence[Mapping[str, Any]],
    llm_config: LLMConfig,
    bridge_config: BridgeConfig,
    bridge_output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run bridge preflight before v1.3 answer composition."""
    bridge_payload: Optional[Dict[str, Any]] = None
    bridge_report_path: Optional[Path] = None
    try:
        bridge_payload, bridge_report_path = run_bridge_preflight(question, bridge_config, output_dir=bridge_output_dir)
    except Exception as exc:
        if not bridge_config.allow_answer_if_bridge_fails:
            return bridge_failure_record(question, error=f"{type(exc).__name__}: {exc}")
        bridge_payload = {
            "module": MODULE_VERSION,
            "status": "TRACE_NET_WEBUI_SELF_RAG_CRAG_BRIDGE_EXCEPTION",
            "quality_status": "FAIL",
            "summary": {"question": question},
            "tool_statuses": {},
            "checklist_text": f"Self-RAG/CRAG bridge exception: {type(exc).__name__}: {exc}",
        }
    if bridge_payload and not _bridge_passed(bridge_payload) and not bridge_config.allow_answer_if_bridge_fails:
        return bridge_failure_record(question, error="bridge quality_status/required stages did not pass", bridge_payload=bridge_payload)

    answer_record = answer_question_v13(
        question=question,
        pages=pages,
        gated_drafts=gated_drafts,
        llm_config=llm_config,
    )
    if bridge_payload:
        return merge_bridge_trace(answer_record, bridge_payload, bridge_report_path=bridge_report_path)
    return dict(answer_record)


def _bridge_config_from_args(args: argparse.Namespace) -> BridgeConfig:
    return BridgeConfig(
        enabled=not bool(getattr(args, "disable_self_rag_crag_bridge", False)),
        kernel_path=Path(args.kernel),
        output_dir=Path(args.bridge_output_dir),
        route_dispatch_handoff=_as_path(args.route_handoff),
        table_exact_search_adapter=_as_path(args.table_exact_search_adapter),
        page_context_v2=_as_path(args.page_context_v2),
        leiden_communities=_as_path(args.leiden_communities),
        image_visual_observer=_as_path(args.image_visual_observer),
        webui_visual_context_bridge=_as_path(args.webui_visual_context_bridge),
        max_records_per_slot=int(args.max_records_per_slot),
        min_high_signal_capsules=int(args.min_high_signal_capsules),
        min_evidence_strength_score=int(args.min_evidence_strength_score),
        allow_answer_if_bridge_fails=bool(getattr(args, "allow_answer_if_bridge_fails", False)),
        cli_fallback_enabled=not bool(getattr(args, "disable_bridge_cli_fallback", False)),
    )


def _add_bridge_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kernel", default=str(DEFAULT_KERNEL))
    parser.add_argument("--bridge-output-dir", default=str(DEFAULT_BRIDGE_OUTPUT_DIR))
    parser.add_argument("--table-exact-search-adapter", default=str(DEFAULT_TABLE_EXACT_SEARCH))
    parser.add_argument("--leiden-communities", default=str(DEFAULT_LEIDEN_COMMUNITIES))
    parser.add_argument("--image-visual-observer", default=str(DEFAULT_IMAGE_VISUAL_OBSERVER))
    parser.add_argument("--webui-visual-context-bridge", default=str(DEFAULT_WEBUI_VISUAL_CONTEXT_BRIDGE))
    parser.add_argument("--max-records-per-slot", type=int, default=8)
    parser.add_argument("--min-high-signal-capsules", type=int, default=1)
    parser.add_argument("--min-evidence-strength-score", type=int, default=35)
    parser.add_argument("--disable-self-rag-crag-bridge", action="store_true")
    parser.add_argument("--allow-answer-if-bridge-fails", action="store_true")
    parser.add_argument("--disable-bridge-cli-fallback", action="store_true")


def build_manifest_bridge_v1(
    *,
    output_dir: Path,
    final_gate_path: Path,
    runner_path: Path,
    page_context_path: Path,
    fishnet_path: Path,
    route_handoff_path: Path,
    sample_question: str,
    llm_config: LLMConfig,
    bridge_config: BridgeConfig,
) -> Dict[str, Any]:
    pages = load_page_index(
        page_context_path=page_context_path,
        fishnet_path=fishnet_path,
        route_handoff_path=route_handoff_path,
    )
    gated_drafts = load_gated_drafts(final_gate_path=final_gate_path, runner_path=runner_path)
    sample_bridge_dir = output_dir / "sample_bridge_preflight"
    _ensure_bridge_stage_dirs(sample_bridge_dir)
    sample_record = answer_question_with_bridge_v1(
        question=sample_question,
        pages=pages,
        gated_drafts=gated_drafts,
        llm_config=LLMConfig(mode="off", model=llm_config.model, base_url=llm_config.base_url),
        bridge_config=bridge_config,
        bridge_output_dir=sample_bridge_dir,
    )
    tool_statuses = sample_record.get("webui_self_rag_crag_bridge_tool_statuses") or {}
    summary = {
        "page_record_count": len(pages),
        "page_with_text_count": sum(1 for page in pages if page.get("has_text")),
        "gated_draft_count": len(gated_drafts),
        "sample_response_kind": sample_record.get("response_kind"),
        "sample_response_char_count": len(str(sample_record.get("response_text") or "")),
        "server_llm_mode": llm_config.mode,
        "server_llm_model": llm_config.model if llm_config.enabled else None,
        "server_llm_base_url": llm_config.base_url if llm_config.enabled else None,
        "self_rag_crag_bridge_enabled": bridge_config.enabled,
        "self_rag_crag_bridge_required_before_answer": not bridge_config.allow_answer_if_bridge_fails,
        "sample_bridge_quality_status": sample_record.get("webui_self_rag_crag_bridge_quality_status"),
        "sample_bridge_used": bool(sample_record.get("webui_self_rag_crag_bridge_used")),
        "sample_bridge_tool_statuses": tool_statuses,
        "sample_bridge_error": sample_record.get("webui_self_rag_crag_bridge_error") or sample_record.get("llm_error"),
        "sample_bridge_in_process_error": sample_record.get("webui_self_rag_crag_bridge_in_process_error"),
        "sample_bridge_cli_fallback_used": bool(sample_record.get("webui_self_rag_crag_bridge_cli_fallback_used")),
        "query_planner_used": bool(sample_record.get("query_planner_used")),
        "context_pack_builder_used": bool(sample_record.get("context_pack_builder_used")),
        "self_rag_used": bool(sample_record.get("self_rag_used")),
        "crag_retry_status": sample_record.get("crag_retry_status"),
        "crag_retry_evaluated": bool(sample_record.get("crag_retry_evaluated")),
        "context_pack_count": int(sample_record.get("context_pack_count") or 0),
        "total_evidence_capsule_count": int(sample_record.get("total_evidence_capsule_count") or 0),
        "webui_visual_context_bridge_used": bool(sample_record.get("webui_visual_context_bridge_used")),
        "visual_image_route_used": bool(sample_record.get("visual_image_route_used")),
        "webui_visual_context_bridge_quality_status": sample_record.get("webui_visual_context_bridge_quality_status"),
        "visual_context_card_count": int(sample_record.get("visual_context_card_count") or 0),
        "review_only_visual_context_excluded_count": int(sample_record.get("review_only_visual_context_excluded_count") or 0),
        "visual_context_included_pages": sample_record.get("visual_context_included_pages") or [],
        "visual_context_included_canonical_page_numbers": sample_record.get("visual_context_included_canonical_page_numbers") or [],
        "ready_for_webui": True,
        "openai_compatible_chat_completions_route": True,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "retrieval_execution_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unsafe_record_count": 0,
    }
    failures: List[str] = []
    if not pages and not gated_drafts:
        failures.append("no pages or gated drafts loaded")
    if bridge_config.enabled:
        if not summary["sample_bridge_used"]:
            failures.append("sample bridge did not pass")
        if not summary["self_rag_used"]:
            failures.append("sample Self-RAG was not used")
        if not summary["crag_retry_evaluated"]:
            failures.append("sample CRAG retry was not evaluated")
    for key in SAFETY_COUNT_KEYS:
        if int(summary.get(key) or 0) != 0:
            failures.append(f"{key} is not zero")
    quality_status = "FAIL" if failures else "PASS"
    payload = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_WEBUI_ANSWER_SERVER_V1_3_SELF_RAG_CRAG_BRIDGE_MANIFEST_BUILT",
        "quality_status": quality_status,
        "failures": failures,
        "summary": summary,
        "model_id": MODEL_ID,
        "records": [sample_record],
        "routes": {"health": "/health", "models": "/v1/models", "chat_completions": "/v1/chat/completions"},
        "input_paths": {
            "final_gate": str(final_gate_path),
            "runner_report": str(runner_path),
            "page_context_v2": str(page_context_path),
            "fishnet_ocr_grid": str(fishnet_path),
            "route_handoff": str(route_handoff_path),
            "kernel": str(bridge_config.kernel_path),
            "table_exact_search_adapter": str(bridge_config.table_exact_search_adapter) if bridge_config.table_exact_search_adapter else None,
            "leiden_communities": str(bridge_config.leiden_communities) if bridge_config.leiden_communities else None,
            "image_visual_observer": str(bridge_config.image_visual_observer) if bridge_config.image_visual_observer else None,
            "webui_visual_context_bridge": str(bridge_config.webui_visual_context_bridge) if bridge_config.webui_visual_context_bridge else None,
            "bridge_cli_fallback_enabled": bridge_config.cli_fallback_enabled,
        },
        "safety_contract": {
            "manual_review_required": True,
            "bridge_required_before_answer": not bridge_config.allow_answer_if_bridge_fails,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_json(output_dir / "trace_net_engineering_webui_answer_server_v1_3_bridge_v1_summary.json", summary)
    _write_jsonl(output_dir / "trace_net_engineering_webui_answer_server_v1_3_bridge_v1_records.jsonl", [sample_record])
    _write_json(output_dir / "trace_net_engineering_webui_answer_server_v1_3_bridge_v1_quality.json", {"quality_status": quality_status, "summary": summary, "failures": failures})
    return payload


def check_manifest_bridge_v1(
    *,
    report_path: Path,
    min_page_records: int = 1,
    min_gated_drafts: int = 0,
    require_llm_model: Optional[str] = None,
    require_bridge_preflight: bool = False,
    require_self_rag_used: bool = False,
    require_crag_evaluated: bool = False,
    require_webui_visual_context_bridge_used: bool = False,
    min_visual_context_cards: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path, required=True)
    summary = dict(_summary(payload))
    failures: List[str] = []

    def fail_if(condition: bool, message: str) -> None:
        if condition:
            failures.append(message)

    fail_if(payload.get("quality_status") != "PASS", "manifest quality_status is not PASS")
    fail_if(int(summary.get("page_record_count") or 0) < min_page_records, "not enough page records")
    fail_if(int(summary.get("gated_draft_count") or 0) < min_gated_drafts, "not enough gated drafts")
    if require_llm_model:
        fail_if(summary.get("server_llm_model") != require_llm_model, f"server llm model is not {require_llm_model}")
    if require_bridge_preflight:
        fail_if(not summary.get("self_rag_crag_bridge_enabled"), "Self-RAG/CRAG bridge is not enabled")
        fail_if(not summary.get("sample_bridge_used"), "sample bridge was not used")
    if require_self_rag_used:
        fail_if(not summary.get("self_rag_used"), "Self-RAG was not used")
    if require_crag_evaluated:
        fail_if(summary.get("crag_retry_status") not in {"used", "skipped_not_needed"}, "CRAG retry was not evaluated")
    if require_webui_visual_context_bridge_used:
        fail_if(not summary.get("webui_visual_context_bridge_used"), "WebUI visual context bridge was not used")
        fail_if(summary.get("webui_visual_context_bridge_quality_status") != "PASS", "WebUI visual context bridge quality_status is not PASS")
        fail_if(not summary.get("visual_image_route_used"), "visual image route was not used")
    if min_visual_context_cards:
        fail_if(int(summary.get("visual_context_card_count") or 0) < min_visual_context_cards, "not enough visual context cards")
    if require_no_answer_permission:
        for key in ("answer_permission_count", "can_answer_directly_count", "can_prove_claims_count"):
            fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
    if require_no_source_truth_mutation:
        fail_if(int(summary.get("source_truth_mutation_allowed_count") or 0) != 0, "source_truth_mutation_allowed_count is not zero")
    if require_no_write_attempts:
        for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
            fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
    return {
        "quality_status": "FAIL" if failures else "PASS",
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


class TraceNetWebUIHandlerV13BridgeV1(BaseHTTPRequestHandler):
    server_version = "TraceNetWebUIAnswerServer/1.3-bridge-v1"

    def _json_response(self, status: int, payload: Mapping[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/"}:
            self._json_response(
                200,
                {
                    "status": "ok",
                    "module": MODULE_VERSION,
                    "server_version": "v1.3-bridge-v1",
                    "model_id": MODEL_ID,
                    "page_record_count": len(self.server.pages),  # type: ignore[attr-defined]
                    "gated_draft_count": len(self.server.gated_drafts),  # type: ignore[attr-defined]
                    "llm_mode": self.server.llm_config.mode,  # type: ignore[attr-defined]
                    "llm_model": self.server.llm_config.model if self.server.llm_config.enabled else None,  # type: ignore[attr-defined]
                    "self_rag_crag_bridge_enabled": self.server.bridge_config.enabled,  # type: ignore[attr-defined]
                    "bridge_required_before_answer": not self.server.bridge_config.allow_answer_if_bridge_fails,  # type: ignore[attr-defined]
                    "webui_visual_context_bridge_configured": bool(self.server.bridge_config.webui_visual_context_bridge),  # type: ignore[attr-defined]
                    "webui_visual_context_bridge": str(self.server.bridge_config.webui_visual_context_bridge) if self.server.bridge_config.webui_visual_context_bridge else None,  # type: ignore[attr-defined]
                    "clean_fallback_enabled": True,
                    "ready_for_webui": True,
                },
            )
            return
        if self.path in {"/v1/models", "/api/models"}:
            self._json_response(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": int(time.time()), "owned_by": "trace-net"}]})
            return
        self._json_response(404, {"error": f"not found: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/v1/chat/completions", "/api/chat/completions"}:
            self._json_response(404, {"error": f"not found: {self.path}"})
            return
        try:
            body = self._read_body_json()
            messages = body.get("messages") or []
            question = ""
            for msg in reversed(messages):
                if isinstance(msg, Mapping) and msg.get("role") == "user":
                    question = str(msg.get("content") or "")
                    break
            if not question:
                question = "pick a random page to summarize"
            record = answer_question_with_bridge_v1(
                question=question,
                pages=self.server.pages,  # type: ignore[attr-defined]
                gated_drafts=self.server.gated_drafts,  # type: ignore[attr-defined]
                llm_config=self.server.llm_config,  # type: ignore[attr-defined]
                bridge_config=self.server.bridge_config,  # type: ignore[attr-defined]
            )
            response = {
                "id": f"chatcmpl-trace-net-{int(time.time() * 1000)}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model") or MODEL_ID,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": record["response_text"]}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "trace_net": record,
            }
            self._json_response(200, response)
        except Exception as exc:
            self._json_response(500, {"error": f"{type(exc).__name__}: {exc}"})


class TraceNetHTTPServerV13BridgeV1(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: Tuple[str, int],
        handler_class: Any,
        *,
        pages: Sequence[Mapping[str, Any]],
        gated_drafts: Sequence[Mapping[str, Any]],
        llm_config: LLMConfig,
        bridge_config: BridgeConfig,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.pages = list(pages)
        self.gated_drafts = list(gated_drafts)
        self.llm_config = llm_config
        self.bridge_config = bridge_config


def run_server_bridge_v1(
    *,
    host: str,
    port: int,
    final_gate_path: Path,
    runner_path: Path,
    page_context_path: Path,
    fishnet_path: Path,
    route_handoff_path: Path,
    llm_config: LLMConfig,
    bridge_config: BridgeConfig,
) -> None:
    pages = load_page_index(page_context_path=page_context_path, fishnet_path=fishnet_path, route_handoff_path=route_handoff_path)
    gated_drafts = load_gated_drafts(final_gate_path=final_gate_path, runner_path=runner_path)
    server = TraceNetHTTPServerV13BridgeV1(
        (host, port),
        TraceNetWebUIHandlerV13BridgeV1,
        pages=pages,
        gated_drafts=gated_drafts,
        llm_config=llm_config,
        bridge_config=bridge_config,
    )
    print(f"TRACE-Net WebUI answer server v1.3 + Self-RAG/CRAG bridge v1 running on http://{host}:{port}")
    print(f"Model ID exposed to WebUI: {MODEL_ID}")
    print(f"Runtime LLM model: {llm_config.model if llm_config.enabled else 'off'}")
    print(f"Self-RAG/CRAG bridge enabled: {bridge_config.enabled}")
    print(f"Bridge required before answer: {not bridge_config.allow_answer_if_bridge_fails}")
    print(f"Pages loaded: {len(pages)}")
    print(f"Gated drafts loaded: {len(gated_drafts)}")
    server.serve_forever()


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering WebUI answer server v1.3 bridge manifest.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--final-gate", default=str(DEFAULT_FINAL_GATE))
    parser.add_argument("--runner-report", default=str(DEFAULT_RUNNER))
    parser.add_argument("--page-context-v2", default=str(DEFAULT_PAGE_CONTEXT))
    parser.add_argument("--fishnet-ocr-grid", default=str(DEFAULT_FISHNET))
    parser.add_argument("--route-handoff", default=str(DEFAULT_ROUTE_HANDOFF))
    parser.add_argument("--sample-question", default="Find part number 120-29073-001 and nearby similar parts. Use every TRACE-Net evidence route that is available and show source boundaries.")
    _add_llm_args(parser)
    _add_bridge_args(parser)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    payload = build_manifest_bridge_v1(
        output_dir=Path(args.output_dir),
        final_gate_path=Path(args.final_gate),
        runner_path=Path(args.runner_report),
        page_context_path=Path(args.page_context_v2),
        fishnet_path=Path(args.fishnet_ocr_grid),
        route_handoff_path=Path(args.route_handoff),
        sample_question=args.sample_question,
        llm_config=_llm_config_from_args(args),
        bridge_config=_bridge_config_from_args(args),
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering WebUI answer server v1.3 bridge quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-page-records", type=int, default=1)
    parser.add_argument("--min-gated-drafts", type=int, default=0)
    parser.add_argument("--require-llm-model")
    parser.add_argument("--require-bridge-preflight", action="store_true")
    parser.add_argument("--require-self-rag-used", action="store_true")
    parser.add_argument("--require-crag-evaluated", action="store_true")
    parser.add_argument("--require-webui-visual-context-bridge-used", action="store_true")
    parser.add_argument("--min-visual-context-cards", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    result = check_manifest_bridge_v1(
        report_path=Path(args.report_path),
        min_page_records=args.min_page_records,
        min_gated_drafts=args.min_gated_drafts,
        require_llm_model=args.require_llm_model,
        require_bridge_preflight=args.require_bridge_preflight,
        require_self_rag_used=args.require_self_rag_used,
        require_crag_evaluated=args.require_crag_evaluated,
        require_webui_visual_context_bridge_used=args.require_webui_visual_context_bridge_used,
        min_visual_context_cards=args.min_visual_context_cards,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_engineering_webui_answer_server_v1_3_bridge_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


def main_run(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run TRACE-Net engineering WebUI answer server v1.3 with Self-RAG/CRAG bridge.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8044)
    parser.add_argument("--final-gate", default=str(DEFAULT_FINAL_GATE))
    parser.add_argument("--runner-report", default=str(DEFAULT_RUNNER))
    parser.add_argument("--page-context-v2", default=str(DEFAULT_PAGE_CONTEXT))
    parser.add_argument("--fishnet-ocr-grid", default=str(DEFAULT_FISHNET))
    parser.add_argument("--route-handoff", default=str(DEFAULT_ROUTE_HANDOFF))
    _add_llm_args(parser)
    _add_bridge_args(parser)
    args = parser.parse_args(argv)
    run_server_bridge_v1(
        host=args.host,
        port=args.port,
        final_gate_path=Path(args.final_gate),
        runner_path=Path(args.runner_report),
        page_context_path=Path(args.page_context_v2),
        fishnet_path=Path(args.fishnet_ocr_grid),
        route_handoff_path=Path(args.route_handoff),
        llm_config=_llm_config_from_args(args),
        bridge_config=_bridge_config_from_args(args),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_build())
