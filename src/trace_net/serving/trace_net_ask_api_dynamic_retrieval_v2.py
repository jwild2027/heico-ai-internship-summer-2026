"""TRACE-Net Ask API Dynamic Retrieval v2.

OpenAI-compatible, read-only API layer that dynamically builds retrieval groups for
new queries using Hybrid Retrieval v2 artifacts while preserving TRACE-Net final
answer safety rules.

Safety contract:
- Dynamic retrieval can rank possible evidence groups.
- Dynamic retrieval cannot answer directly or prove claims.
- Final answers are only returned when an existing final-gate artifact authorizes
  the exact query.
- No Postgres, Qdrant, OpenSearch, graph, source, citation, or trust writes occur.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlparse

SCHEMA_VERSION = "trace_net_ask_api_dynamic_retrieval_v2"
DEFAULT_MODEL_NAME = "trace-net-dynamic-hybrid-v2"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/ask_api_dynamic_retrieval_v2")
DEFAULT_PORT = 8013

LOCAL_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:\\\\|[A-Za-z]:/|/mnt/|/home/|local_data[\\/]|\\\\Users\\\\|/Users/)",
    re.IGNORECASE,
)
RAW_BYTES_PATTERN = re.compile(r"b['\"]|\\x[0-9a-fA-F]{2}")


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8", errors="replace"))
        h.update(b"\0")
    return f"{prefix}__{h.hexdigest()[:16]}"


def normalize_query(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def read_json(path: Optional[Path | str]) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path | str, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path | str, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def read_text_if_exists(path: Optional[Path | str]) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def sanitize_for_user(text: str, max_chars: int = 12000) -> tuple[str, dict[str, int]]:
    text = text or ""
    counts = {
        "local_path_leak_count": len(LOCAL_PATH_PATTERN.findall(text)),
        "raw_bytes_repr_count": len(RAW_BYTES_PATTERN.findall(text)),
    }
    text = LOCAL_PATH_PATTERN.sub("[redacted-local-path]", text)
    text = RAW_BYTES_PATTERN.sub("[redacted-bytes]", text)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n[truncated by TRACE-Net Ask API Dynamic Retrieval v2]"
    return text, counts


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "pass", "allowed"}:
            return True
        if v in {"0", "false", "no", "n", "fail", "blocked"}:
            return False
    return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def first_non_empty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def get_quality_status(payload: Mapping[str, Any]) -> str:
    for key in ("quality_status", "status"):
        value = as_text(payload.get(key)).upper()
        if value in {"PASS", "FAIL"}:
            return value
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    for key in ("quality_status", "status"):
        value = as_text(summary.get(key)).upper()
        if value in {"PASS", "FAIL"}:
            return value
    return ""


def bool_from_payload(payload: Mapping[str, Any], key: str, default: bool = False) -> bool:
    if key in payload:
        return as_bool(payload.get(key), default)
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    if key in summary:
        return as_bool(summary.get(key), default)
    return default


def get_report_query(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return first_non_empty(payload.get("query"), summary.get("query"))


def extract_markdown_answer(markdown_text: str) -> str:
    if not markdown_text.strip():
        return ""
    marker = "## Final gated answer"
    idx = markdown_text.find(marker)
    if idx >= 0:
        answer = markdown_text[idx + len(marker):].strip()
        for next_marker in ["\n## ", "\n# "]:
            next_idx = answer.find(next_marker)
            if next_idx > 0:
                answer = answer[:next_idx].strip()
                break
        return answer
    lines = markdown_text.splitlines()
    while lines and lines[0].strip().startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()


def extract_answer_text(report: Mapping[str, Any], markdown_path: Optional[Path] = None) -> str:
    for candidate in [report.get("final_answer_text"), report.get("answer_text"), report.get("answer"), report.get("final_answer")]:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, Mapping):
            for key in ["text", "markdown", "answer_text", "final_answer_text"]:
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return extract_markdown_answer(read_text_if_exists(markdown_path))


@dataclass(frozen=True)
class AskApiDynamicConfig:
    final_answer_report: Optional[Path] = None
    final_answer_markdown: Optional[Path] = None
    hybrid_v2_report: Optional[Path] = None
    hybrid_report: Optional[Path] = None
    opensearch_adapter: Optional[Path] = None
    community_aware_retrieval: Optional[Path] = None
    category_aware_leiden_overlay: Optional[Path] = None
    feedback_memory: Optional[Path] = None
    output_dir: Path = DEFAULT_OUTPUT_DIR
    default_answer_mode: str = "final-gate"
    default_retrieval_mode: str = "dynamic-hybrid-v2"
    model_name: str = DEFAULT_MODEL_NAME
    api_key: str = ""
    top_k_exact: int = 12
    max_groups: int = 8


def _hybrid_v2_module():
    try:
        from tiff import trace_net_hybrid_retrieval_v2 as hybrid_v2  # type: ignore
        return hybrid_v2
    except Exception:
        return None


def _find_existing_hybrid_v2_query(query: str, report: Mapping[str, Any]) -> dict[str, Any]:
    qn = normalize_query(query)
    rows = report.get("query_results") or []
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, Mapping) and normalize_query(as_text(row.get("query"))) == qn:
            return dict(row)
    return {}


def build_dynamic_hybrid_result(query: str, config: AskApiDynamicConfig) -> dict[str, Any]:
    """Build or reuse Hybrid Retrieval v2 result for one query."""
    existing_report = read_json(config.hybrid_v2_report)
    existing = _find_existing_hybrid_v2_query(query, existing_report)
    if existing:
        return {
            "status": "DYNAMIC_HYBRID_RESULT_BUILT",
            "retrieval_mode": "dynamic-hybrid-v2",
            "retrieval_source": "prebuilt_hybrid_v2_query_result",
            "query_result": existing,
            "dynamic_retrieval_used": True,
            "dynamic_retrieval_built_live": False,
            "hybrid_v2_quality_status": get_quality_status(existing_report),
        }

    hybrid_v2 = _hybrid_v2_module()
    if hybrid_v2 is None:
        return {
            "status": "DYNAMIC_HYBRID_RESULT_UNAVAILABLE",
            "retrieval_mode": "dynamic-hybrid-v2",
            "retrieval_source": "hybrid_v2_module_unavailable",
            "query_result": {"query": query, "ranked_groups": [], "ranked_group_count": 0},
            "dynamic_retrieval_used": False,
            "dynamic_retrieval_built_live": False,
        }

    try:
        hybrid_report = hybrid_v2.read_json(config.hybrid_report) if config.hybrid_report else {}
        opensearch_report = hybrid_v2.read_json(config.opensearch_adapter) if config.opensearch_adapter else {}
        community_report = hybrid_v2.read_json(config.community_aware_retrieval) if config.community_aware_retrieval else {}
        category_overlay = hybrid_v2.read_json(config.category_aware_leiden_overlay) if config.category_aware_leiden_overlay else {}
        feedback_memory = hybrid_v2.read_json(config.feedback_memory) if config.feedback_memory else {}
        docs = hybrid_v2.opensearch_documents(opensearch_report)
        q = {"query_id": stable_id("query", query), "query": query, "intent": "api_dynamic_query"}
        result = hybrid_v2.build_query_result(
            q,
            docs=docs,
            hybrid_report=hybrid_report,
            community_report=community_report,
            category_overlay=category_overlay,
            feedback_memory=feedback_memory,
            top_k_exact=config.top_k_exact,
            max_groups=config.max_groups,
        )
        return {
            "status": "DYNAMIC_HYBRID_RESULT_BUILT",
            "retrieval_mode": "dynamic-hybrid-v2",
            "retrieval_source": "live_local_artifact_hybrid_v2",
            "query_result": result,
            "dynamic_retrieval_used": True,
            "dynamic_retrieval_built_live": True,
            "hybrid_report_quality_status": get_quality_status(hybrid_report),
            "opensearch_quality_status": get_quality_status(opensearch_report),
            "community_aware_quality_status": get_quality_status(community_report),
            "category_aware_quality_status": get_quality_status(category_overlay),
            "feedback_memory_quality_status": get_quality_status(feedback_memory),
        }
    except Exception as exc:  # pragma: no cover - defensive in production API
        return {
            "status": "DYNAMIC_HYBRID_RESULT_ERROR",
            "retrieval_mode": "dynamic-hybrid-v2",
            "retrieval_source": "live_local_artifact_hybrid_v2",
            "query_result": {"query": query, "ranked_groups": [], "ranked_group_count": 0},
            "dynamic_retrieval_used": False,
            "dynamic_retrieval_built_live": False,
            "error": repr(exc),
        }


def convert_groups(query_result: Mapping[str, Any], max_groups: int) -> list[dict[str, Any]]:
    groups = query_result.get("ranked_groups") or []
    out: list[dict[str, Any]] = []
    if not isinstance(groups, list):
        return out
    for idx, group in enumerate(groups[:max_groups], start=1):
        if not isinstance(group, Mapping):
            continue
        out.append(
            {
                "rank": group.get("hybrid_v2_rank") or group.get("rank") or idx,
                "page_id": group.get("page_id"),
                "score": group.get("hybrid_v2_score") or group.get("score"),
                "exact_hit_count": group.get("exact_hit_count", 0),
                "semantic_group_count": group.get("semantic_group_count", 0),
                "category_boost": group.get("category_boost", 0),
                "feedback_advisory_delta": group.get("feedback_advisory_delta", 0),
                "category_labels": group.get("category_labels") or [],
                "community_ids": group.get("community_ids") or [],
                "citation_ids": group.get("citation_ids") or [],
                "part_numbers": group.get("part_numbers") or [],
                "rag_buckets": group.get("rag_buckets") or [],
                "retrieval_only": True,
                "answer_allowed": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
                "source_truth_mutation_allowed": False,
                "safety_status": group.get("safety_status") or "retrieval_safe",
            }
        )
    return out


def build_trace_net_dynamic_ask_response(
    query: str,
    config: AskApiDynamicConfig,
    *,
    answer_mode: Optional[str] = None,
    retrieval_mode: Optional[str] = None,
    max_groups: Optional[int] = None,
) -> dict[str, Any]:
    answer_mode = answer_mode or config.default_answer_mode
    retrieval_mode = retrieval_mode or config.default_retrieval_mode
    max_groups = max_groups or config.max_groups

    final_report = read_json(config.final_answer_report)
    final_quality_status = get_quality_status(final_report)
    final_answer_allowed = bool_from_payload(final_report, "final_answer_allowed", False)
    final_query = get_report_query(final_report)
    query_matches_final_artifact = bool(final_query) and normalize_query(final_query) == normalize_query(query)

    dynamic = build_dynamic_hybrid_result(query, config)
    query_result = dynamic.get("query_result") if isinstance(dynamic.get("query_result"), Mapping) else {}
    retrieval_groups = convert_groups(query_result, max_groups=max_groups)

    final_answer_used = False
    if answer_mode == "final-gate":
        if final_report and final_quality_status == "PASS" and final_answer_allowed and query_matches_final_artifact:
            raw_answer = extract_answer_text(final_report, config.final_answer_markdown)
            answer_status = "FINAL_GATE_ARTIFACT_ANSWER"
            final_answer_used = True
        elif retrieval_groups:
            raw_answer = (
                "TRACE-Net dynamic hybrid retrieval found candidate evidence groups for this query, "
                "but no final-gate artifact has authorized a final answer for this exact query. "
                "Review the retrieval groups or run the full TRACE-Net final-gate pipeline for this query."
            )
            answer_status = "DYNAMIC_RETRIEVAL_ONLY_FINAL_GATE_REQUIRED"
        else:
            raw_answer = "TRACE-Net dynamic retrieval did not find safe retrieval groups for this query."
            answer_status = "NO_DYNAMIC_RETRIEVAL_GROUPS"
    elif answer_mode == "retrieval-only":
        raw_answer = "TRACE-Net dynamic hybrid retrieval-only response. No final answer is authorized."
        answer_status = "DYNAMIC_RETRIEVAL_ONLY"
    elif answer_mode == "citation-draft":
        raw_answer = "TRACE-Net citation-draft mode requires the downstream citation draft/final gate pipeline for this query."
        answer_status = "CITATION_DRAFT_REQUIRES_PIPELINE"
    else:
        raw_answer = "Unsupported TRACE-Net answer mode."
        answer_status = "UNSUPPORTED_ANSWER_MODE"

    answer_text, leak_counts = sanitize_for_user(raw_answer)
    local_path_leak_count = leak_counts["local_path_leak_count"]
    raw_bytes_repr_count = leak_counts["raw_bytes_repr_count"]

    exact_hit_group_count = sum(1 for g in retrieval_groups if int(g.get("exact_hit_count") or 0) > 0)
    semantic_group_count = sum(1 for g in retrieval_groups if int(g.get("semantic_group_count") or 0) > 0)
    unsafe_group_count = sum(1 for g in retrieval_groups if as_text(g.get("safety_status")) == "unsafe")

    final_answer_allowed_for_response = bool(final_answer_used)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "query": query,
        "answer_mode": answer_mode,
        "retrieval_mode": retrieval_mode,
        "answer_status": answer_status,
        "final_answer_used": final_answer_used,
        "final_answer_allowed": final_answer_allowed_for_response,
        "final_artifact_quality_status": final_quality_status,
        "final_artifact_query": final_query,
        "query_matches_final_artifact": query_matches_final_artifact,
        "dynamic_retrieval_used": bool(dynamic.get("dynamic_retrieval_used")),
        "dynamic_retrieval_built_live": bool(dynamic.get("dynamic_retrieval_built_live")),
        "dynamic_retrieval_status": dynamic.get("status"),
        "retrieval_source": dynamic.get("retrieval_source"),
        "retrieval_group_count": len(retrieval_groups),
        "exact_hit_group_count": exact_hit_group_count,
        "semantic_group_count": semantic_group_count,
        "unsafe_group_count": unsafe_group_count,
        "local_path_leak_count": local_path_leak_count,
        "raw_bytes_repr_count": raw_bytes_repr_count,
        "can_answer_directly": final_answer_allowed_for_response,
        "can_prove_claims": final_answer_allowed_for_response,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "hybrid_v2_quality_status": dynamic.get("hybrid_v2_quality_status") or dynamic.get("hybrid_report_quality_status", ""),
        "opensearch_quality_status": dynamic.get("opensearch_quality_status", ""),
        "category_aware_quality_status": dynamic.get("category_aware_quality_status", ""),
        "feedback_memory_quality_status": dynamic.get("feedback_memory_quality_status", ""),
    }

    response = {
        "schema_version": SCHEMA_VERSION,
        "status": "ASK_API_DYNAMIC_RESPONSE_BUILT",
        "quality_status": "PASS" if local_path_leak_count == 0 and raw_bytes_repr_count == 0 and unsafe_group_count == 0 else "FAIL",
        "request_id": stable_id("askdynreq", query, answer_mode, retrieval_mode, time.time_ns()),
        "generated_at": utc_now(),
        "model": config.model_name,
        "query": query,
        "answer_text": answer_text,
        "answer_markdown": answer_text,
        "summary": summary,
        "retrieval_groups": retrieval_groups,
        "dynamic_query_result": query_result,
        "supporting_sources": {
            "final_answer_report": str(config.final_answer_report) if config.final_answer_report else "",
            "hybrid_v2_report": str(config.hybrid_v2_report) if config.hybrid_v2_report else "",
            "hybrid_report": str(config.hybrid_report) if config.hybrid_report else "",
            "opensearch_adapter": str(config.opensearch_adapter) if config.opensearch_adapter else "",
            "community_aware_retrieval": str(config.community_aware_retrieval) if config.community_aware_retrieval else "",
            "category_aware_leiden_overlay": str(config.category_aware_leiden_overlay) if config.category_aware_leiden_overlay else "",
            "feedback_memory": str(config.feedback_memory) if config.feedback_memory else "",
        },
        "safety": {
            "read_only_api": True,
            "llm_freeform_answer_allowed": False,
            "source_truth_mutation_allowed": False,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "local_path_leak_count": local_path_leak_count,
            "raw_bytes_repr_count": raw_bytes_repr_count,
            "unsafe_group_count": unsafe_group_count,
        },
    }
    return response


def openai_chat_completion_response(query: str, ask_response: Mapping[str, Any], model_name: str) -> dict[str, Any]:
    content = as_text(ask_response.get("answer_markdown") or ask_response.get("answer_text"))
    groups = ask_response.get("retrieval_groups") or []
    if isinstance(groups, list) and groups:
        lines = [content.rstrip(), "", "TRACE-Net dynamic hybrid retrieval groups:"]
        for group in groups[:8]:
            if not isinstance(group, Mapping):
                continue
            page = group.get("page_id") or "unknown-page"
            lines.append(
                f"- rank {group.get('rank')}: {page}; score={group.get('score')}; "
                f"exact={group.get('exact_hit_count')}; semantic={group.get('semantic_group_count')}; "
                f"categories={as_list(group.get('category_labels'))[:3]}; parts={as_list(group.get('part_numbers'))[:3]}"
            )
        content = "\n".join(lines).strip()
    return {
        "id": stable_id("chatcmpl", query, time.time_ns()),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": ask_response.get("summary", {}),
    }


def build_api_report(config: AskApiDynamicConfig) -> dict[str, Any]:
    final_report = read_json(config.final_answer_report)
    hybrid_v2_report = read_json(config.hybrid_v2_report)
    hybrid_report = read_json(config.hybrid_report)
    opensearch_report = read_json(config.opensearch_adapter)
    category_report = read_json(config.category_aware_leiden_overlay)
    feedback_report = read_json(config.feedback_memory)
    checks = {
        "final_answer_report_present": bool(final_report),
        "final_answer_report_quality_pass": get_quality_status(final_report) == "PASS" if final_report else False,
        "hybrid_v2_report_present": bool(hybrid_v2_report),
        "hybrid_v2_report_quality_pass": get_quality_status(hybrid_v2_report) == "PASS" if hybrid_v2_report else False,
        "hybrid_report_present": bool(hybrid_report),
        "opensearch_adapter_present": bool(opensearch_report),
        "opensearch_adapter_quality_pass": get_quality_status(opensearch_report) == "PASS" if opensearch_report else False,
        "category_aware_leiden_overlay_present": bool(category_report),
        "feedback_memory_present": bool(feedback_report),
        "api_is_read_only": True,
    }
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "model_name": config.model_name,
        "default_answer_mode": config.default_answer_mode,
        "default_retrieval_mode": config.default_retrieval_mode,
        "final_answer_quality_status": get_quality_status(final_report),
        "final_answer_allowed": bool_from_payload(final_report, "final_answer_allowed", False),
        "hybrid_v2_quality_status": get_quality_status(hybrid_v2_report),
        "hybrid_quality_status": get_quality_status(hybrid_report),
        "opensearch_quality_status": get_quality_status(opensearch_report),
        "category_aware_quality_status": get_quality_status(category_report),
        "feedback_quality_status": get_quality_status(feedback_report),
        "dynamic_retrieval_available": bool(opensearch_report) and bool(hybrid_report),
        "api_endpoint_count": 5,
        "read_only_api": True,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ASK_API_DYNAMIC_CONFIG_BUILT",
        "quality_status": "PASS",
        "generated_at": utc_now(),
        "summary": summary,
        "checks": checks,
        "paths": {
            "final_answer_report": str(config.final_answer_report) if config.final_answer_report else "",
            "final_answer_markdown": str(config.final_answer_markdown) if config.final_answer_markdown else "",
            "hybrid_v2_report": str(config.hybrid_v2_report) if config.hybrid_v2_report else "",
            "hybrid_report": str(config.hybrid_report) if config.hybrid_report else "",
            "opensearch_adapter": str(config.opensearch_adapter) if config.opensearch_adapter else "",
            "community_aware_retrieval": str(config.community_aware_retrieval) if config.community_aware_retrieval else "",
            "category_aware_leiden_overlay": str(config.category_aware_leiden_overlay) if config.category_aware_leiden_overlay else "",
            "feedback_memory": str(config.feedback_memory) if config.feedback_memory else "",
        },
        "server": {"default_port": DEFAULT_PORT},
    }


def quality_report(report: Mapping[str, Any], *, require_dynamic_retrieval_available: bool = False, require_final_answer_quality_pass: bool = False) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    checks = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "read_only_ok": bool(summary.get("read_only_api")),
        "source_truth_mutation_allowed_zero": int(summary.get("source_truth_mutation_allowed_count", 999)) == 0,
        "feedback_as_proof_zero": int(summary.get("feedback_as_proof_count", 999)) == 0,
        "community_as_proof_zero": int(summary.get("community_as_proof_count", 999)) == 0,
        "category_as_proof_zero": int(summary.get("category_as_proof_count", 999)) == 0,
        "retrieval_only_answer_allowed_zero": int(summary.get("retrieval_only_answer_allowed_count", 999)) == 0,
        "write_attempts_zero": int(summary.get("postgres_write_attempt_count", 999)) == 0
        and int(summary.get("qdrant_write_attempt_count", 999)) == 0
        and int(summary.get("opensearch_write_attempt_count", 999)) == 0,
    }
    if require_dynamic_retrieval_available:
        checks["dynamic_retrieval_available"] = bool(summary.get("dynamic_retrieval_available"))
    if require_final_answer_quality_pass:
        checks["final_answer_quality_pass"] = summary.get("final_answer_quality_status") == "PASS"
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "quality_status": status,
        "generated_at": utc_now(),
        "summary": {
            "read_only_api": summary.get("read_only_api"),
            "dynamic_retrieval_available": summary.get("dynamic_retrieval_available"),
            "final_answer_quality_status": summary.get("final_answer_quality_status", ""),
            "hybrid_v2_quality_status": summary.get("hybrid_v2_quality_status", ""),
            "opensearch_quality_status": summary.get("opensearch_quality_status", ""),
            "source_truth_mutation_allowed_count": summary.get("source_truth_mutation_allowed_count", 0),
            "feedback_as_proof_count": summary.get("feedback_as_proof_count", 0),
            "community_as_proof_count": summary.get("community_as_proof_count", 0),
            "category_as_proof_count": summary.get("category_as_proof_count", 0),
            "retrieval_only_answer_allowed_count": summary.get("retrieval_only_answer_allowed_count", 0),
            "postgres_write_attempt_count": summary.get("postgres_write_attempt_count", 0),
            "qdrant_write_attempt_count": summary.get("qdrant_write_attempt_count", 0),
            "opensearch_write_attempt_count": summary.get("opensearch_write_attempt_count", 0),
        },
        "checks": checks,
    }


class TraceNetDynamicAskHandler(BaseHTTPRequestHandler):
    server_version = "TraceNetAskAPIDynamic/2.0"

    def _send_json(self, payload: Mapping[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _config(self) -> AskApiDynamicConfig:
        return self.server.trace_net_config  # type: ignore[attr-defined]

    def _authorized(self) -> bool:
        key = self._config().api_key
        if not key:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {key}" or self.headers.get("X-API-Key", "") == key

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json({"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/health", "/api/trace-net/health"}:
            self._send_json({"status": "ok", "schema_version": SCHEMA_VERSION, "service": "TRACE-Net Ask API Dynamic Retrieval v2", "read_only": True})
            return
        if parsed.path == "/v1/models":
            self._send_json({"object": "list", "data": [{"id": self._config().model_name, "object": "model", "owned_by": "trace-net"}]})
            return
        self._send_json({"error": "not_found", "path": parsed.path}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._send_json({"error": "unauthorized"}, status=401)
            return
        parsed = urlparse(self.path)
        try:
            body = self._read_json_body()
        except Exception as exc:
            self._send_json({"error": "invalid_json", "detail": str(exc)}, status=400)
            return
        if parsed.path in {"/api/trace-net/ask", "/trace-net/ask"}:
            query = as_text(body.get("query") or body.get("input"))
            if not query:
                self._send_json({"error": "query is required"}, status=400)
                return
            response = build_trace_net_dynamic_ask_response(
                query,
                self._config(),
                answer_mode=as_text(body.get("answer_mode")) or self._config().default_answer_mode,
                retrieval_mode=as_text(body.get("retrieval_mode")) or self._config().default_retrieval_mode,
                max_groups=int(body.get("max_groups") or self._config().max_groups),
            )
            self._send_json(response)
            return
        if parsed.path in {"/v1/chat/completions", "/api/chat/completions"}:
            messages = body.get("messages") or []
            query = ""
            if isinstance(messages, list):
                for message in reversed(messages):
                    if isinstance(message, Mapping) and message.get("role") == "user":
                        query = as_text(message.get("content"))
                        break
            query = query or as_text(body.get("query") or body.get("prompt"))
            if not query:
                self._send_json({"error": "user message content is required"}, status=400)
                return
            ask = build_trace_net_dynamic_ask_response(
                query,
                self._config(),
                answer_mode=as_text(body.get("answer_mode")) or self._config().default_answer_mode,
                retrieval_mode=as_text(body.get("retrieval_mode")) or self._config().default_retrieval_mode,
                max_groups=self._config().max_groups,
            )
            self._send_json(openai_chat_completion_response(query, ask, self._config().model_name))
            return
        self._send_json({"error": "not_found", "path": parsed.path}, status=404)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("TRACE-Net Ask API Dynamic v2: " + (fmt % args) + "\n")


def run_server(config: AskApiDynamicConfig, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), TraceNetDynamicAskHandler)
    server.trace_net_config = config  # type: ignore[attr-defined]
    print("TRACE-Net Ask API Dynamic Retrieval v2")
    print(" Status: SERVER_RUNNING")
    print(f" url: http://{host}:{port}/")
    print(f" model: {config.model_name}")
    print(" safety: read-only; dynamic retrieval is retrieval-only unless final gate authorizes exact query")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTRACE-Net Ask API Dynamic Retrieval v2 stopped")
    finally:
        server.server_close()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run TRACE-Net Ask API Dynamic Retrieval v2")
    p.add_argument("--final-answer-report", type=Path, default=Path("local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json"))
    p.add_argument("--final-answer-markdown", type=Path, default=Path("local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1_answer.md"))
    p.add_argument("--hybrid-v2-report", type=Path, default=Path("local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json"))
    p.add_argument("--hybrid-report", type=Path, default=Path("local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json"))
    p.add_argument("--opensearch-adapter", type=Path, default=Path("local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json"))
    p.add_argument("--community-aware-retrieval", type=Path, default=Path("local_data/organization/trace_net/community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1.json"))
    p.add_argument("--category-aware-leiden-overlay", type=Path, default=Path("local_data/organization/trace_net/category_aware_leiden_overlay/trace_net_category_aware_leiden_overlay_v1.json"))
    p.add_argument("--feedback-memory", type=Path, default=Path("local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json"))
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    p.add_argument("--api-key", default=os.environ.get("TRACE_NET_ASK_API_KEY", ""))
    p.add_argument("--default-answer-mode", default="final-gate", choices=["final-gate", "retrieval-only", "citation-draft"])
    p.add_argument("--default-retrieval-mode", default="dynamic-hybrid-v2")
    p.add_argument("--top-k-exact", type=int, default=12)
    p.add_argument("--max-groups", type=int, default=8)
    p.add_argument("--build-only", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> AskApiDynamicConfig:
    return AskApiDynamicConfig(
        final_answer_report=args.final_answer_report,
        final_answer_markdown=args.final_answer_markdown,
        hybrid_v2_report=args.hybrid_v2_report,
        hybrid_report=args.hybrid_report,
        opensearch_adapter=args.opensearch_adapter,
        community_aware_retrieval=args.community_aware_retrieval,
        category_aware_leiden_overlay=args.category_aware_leiden_overlay,
        feedback_memory=args.feedback_memory,
        output_dir=args.output_dir,
        default_answer_mode=args.default_answer_mode,
        default_retrieval_mode=args.default_retrieval_mode,
        model_name=args.model_name,
        api_key=args.api_key,
        top_k_exact=args.top_k_exact,
        max_groups=args.max_groups,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    config = config_from_args(args)
    report = build_api_report(config)
    report_path = config.output_dir / "trace_net_ask_api_dynamic_retrieval_v2.json"
    quality_path = config.output_dir / "trace_net_ask_api_dynamic_retrieval_v2_quality.json"
    summary_path = config.output_dir / "trace_net_ask_api_dynamic_retrieval_v2_summary.json"
    write_json(report_path, report)
    quality = quality_report(report)
    write_json(quality_path, quality)
    write_json(summary_path, report["summary"])

    print("TRACE-Net Ask API Dynamic Retrieval v2")
    print(f" Status: {report['status']}")
    print(f" Quality status: {quality['quality_status']}")
    print(f" model_name: {config.model_name}")
    print(f" default_answer_mode: {config.default_answer_mode}")
    print(f" default_retrieval_mode: {config.default_retrieval_mode}")
    print(f" dynamic_retrieval_available: {report['summary'].get('dynamic_retrieval_available')}")
    print(f" final_answer_quality_status: {report['summary'].get('final_answer_quality_status')}")
    print(f" report_path: {report_path}")
    print(f" quality_path: {quality_path}")
    if args.build_only:
        return 0 if quality["quality_status"] == "PASS" else 1
    run_server(config, args.host, args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
