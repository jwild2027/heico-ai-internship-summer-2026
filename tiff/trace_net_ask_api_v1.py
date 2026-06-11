"""TRACE-Net Ask API v1.

A small stdlib HTTP API wrapper around existing TRACE-Net artifacts.

This module is intentionally conservative: it exposes final-gate answers only
when a precomputed final-answer artifact says the answer is allowed. For other
queries it can return retrieval-only context summaries, but it never grants
answer/proof/source-truth authority on its own.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

SCHEMA_VERSION = "trace_net_ask_api_v1"
DEFAULT_MODEL_NAME = "trace-net-final-gate-v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/ask_api")
DEFAULT_PORT = 8012

LOCAL_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:\\\\|[A-Za-z]:/|/mnt/|/home/|local_data[\\/]|\\\\Users\\\\|/Users/)",
    re.IGNORECASE,
)
RAW_BYTES_PATTERN = re.compile(r"b['\"]|\\x[0-9a-fA-F]{2}")
BOILERPLATE_PATTERN = re.compile(r"TRACE-Net gate:|source_truth_mutation", re.IGNORECASE)


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


def read_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path:
        return {}
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def read_text_if_exists(path: Optional[Path]) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def sanitize_for_user(text: str, max_chars: int = 12000) -> Tuple[str, Dict[str, int]]:
    """Remove obvious local path/raw-byte leakage from a user-facing answer."""
    text = text or ""
    leak_counts = {
        "local_path_leak_count": len(LOCAL_PATH_PATTERN.findall(text)),
        "raw_bytes_repr_count": len(RAW_BYTES_PATTERN.findall(text)),
    }
    text = LOCAL_PATH_PATTERN.sub("[redacted-local-path]", text)
    text = RAW_BYTES_PATTERN.sub("[redacted-bytes]", text)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n[truncated by TRACE-Net Ask API v1]"
    return text, leak_counts


def extract_markdown_answer(markdown_text: str) -> str:
    if not markdown_text.strip():
        return ""
    marker = "## Final gated answer"
    idx = markdown_text.find(marker)
    if idx >= 0:
        answer = markdown_text[idx + len(marker):].strip()
        # Stop before common subsequent sections if present.
        for next_marker in ["\n## ", "\n# "]:
            next_idx = answer.find(next_marker)
            if next_idx > 0:
                answer = answer[:next_idx].strip()
                break
        return answer
    # Fallback: remove first title heading and return body.
    lines = markdown_text.splitlines()
    while lines and lines[0].strip().startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()


def extract_answer_text(report: Mapping[str, Any], markdown_path: Optional[Path] = None) -> str:
    candidates = [
        report.get("final_answer_text"),
        report.get("answer_text"),
        report.get("answer"),
        report.get("final_answer"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, Mapping):
            for key in ["text", "markdown", "answer_text", "final_answer_text"]:
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    md_text = read_text_if_exists(markdown_path)
    return extract_markdown_answer(md_text)


def get_quality_status(payload: Mapping[str, Any]) -> str:
    for key in ["quality_status", "quality"]:
        value = payload.get(key)
        if isinstance(value, str):
            return value.upper()
        if isinstance(value, Mapping):
            status = value.get("status")
            if isinstance(status, str):
                return status.upper()
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        status = summary.get("quality_status") or summary.get("status")
        if isinstance(status, str):
            return status.upper()
    return ""


def bool_from_payload(payload: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        value = summary.get(key)
        if isinstance(value, bool):
            return value
    return default


def first_non_empty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def get_report_query(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return first_non_empty(payload.get("query"), summary.get("query"))


def collect_retrieval_groups(community_report: Mapping[str, Any], query: str, max_groups: int = 8) -> List[Dict[str, Any]]:
    query_norm = normalize_query(query)
    query_results = community_report.get("query_results") or community_report.get("results") or []
    if not isinstance(query_results, list):
        return []
    selected: Optional[Mapping[str, Any]] = None
    for qr in query_results:
        if not isinstance(qr, Mapping):
            continue
        q_text = first_non_empty(qr.get("query"), qr.get("query_text"), qr.get("query_id"))
        if normalize_query(q_text) == query_norm or (query_norm and query_norm in normalize_query(q_text)):
            selected = qr
            break
    if selected is None and query_results:
        first = query_results[0]
        selected = first if isinstance(first, Mapping) else None
    if not selected:
        return []
    groups = selected.get("ranked_groups") or selected.get("groups") or selected.get("results") or []
    if not isinstance(groups, list):
        return []
    output: List[Dict[str, Any]] = []
    for i, group in enumerate(groups[:max_groups], start=1):
        if not isinstance(group, Mapping):
            continue
        output.append(
            {
                "rank": group.get("community_aware_rank") or group.get("rank") or i,
                "page_id": group.get("page_id"),
                "score": group.get("community_aware_score") or group.get("score") or group.get("base_hybrid_score"),
                "community_ids": group.get("community_ids") or [],
                "citation_ids": group.get("citation_ids") or [],
                "feedback_memory_ids_applied": group.get("feedback_memory_ids_applied") or [],
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
            }
        )
    return output


@dataclass(frozen=True)
class AskApiConfig:
    final_answer_report: Optional[Path] = None
    final_answer_markdown: Optional[Path] = None
    community_aware_retrieval: Optional[Path] = None
    opensearch_adapter: Optional[Path] = None
    feedback_memory: Optional[Path] = None
    leiden_communities: Optional[Path] = None
    output_dir: Path = DEFAULT_OUTPUT_DIR
    default_answer_mode: str = "final-gate"
    default_retrieval_mode: str = "community-aware"
    model_name: str = DEFAULT_MODEL_NAME
    api_key: str = ""


def build_trace_net_ask_response(
    query: str,
    config: AskApiConfig,
    *,
    answer_mode: Optional[str] = None,
    retrieval_mode: Optional[str] = None,
    max_groups: int = 8,
) -> Dict[str, Any]:
    answer_mode = answer_mode or config.default_answer_mode
    retrieval_mode = retrieval_mode or config.default_retrieval_mode
    final_report = read_json(config.final_answer_report)
    community_report = read_json(config.community_aware_retrieval)
    feedback_report = read_json(config.feedback_memory)
    leiden_report = read_json(config.leiden_communities)
    opensearch_report = read_json(config.opensearch_adapter)

    final_quality_status = get_quality_status(final_report)
    final_answer_allowed = bool_from_payload(final_report, "final_answer_allowed", False)
    final_query = get_report_query(final_report)
    query_matches_final_artifact = bool(final_query) and normalize_query(final_query) == normalize_query(query)

    retrieval_groups = collect_retrieval_groups(community_report, query, max_groups=max_groups)
    raw_answer = ""
    answer_status = "NOT_COMPOSED"
    final_answer_used = False

    if answer_mode == "final-gate":
        if final_report and final_quality_status == "PASS" and final_answer_allowed and query_matches_final_artifact:
            raw_answer = extract_answer_text(final_report, config.final_answer_markdown)
            answer_status = "FINAL_GATE_ARTIFACT_ANSWER"
            final_answer_used = True
        elif final_report and final_quality_status == "PASS" and final_answer_allowed and not query_matches_final_artifact:
            raw_answer = (
                "TRACE-Net has a passing final-gate artifact, but it was produced for a different query. "
                "This API response is retrieval-only for the submitted query until the TRACE-Net pipeline is run for it."
            )
            answer_status = "QUERY_MISMATCH_RETRIEVAL_ONLY"
        else:
            raw_answer = "TRACE-Net does not have an approved final-gate answer artifact for this query."
            answer_status = "NO_APPROVED_FINAL_GATE_ARTIFACT"
    elif answer_mode == "retrieval-only":
        raw_answer = "TRACE-Net retrieval-only response. Review the ranked evidence groups; no final answer is authorized."
        answer_status = "RETRIEVAL_ONLY"
    elif answer_mode == "citation-draft":
        raw_answer = "TRACE-Net citation-draft mode is available only after a citation draft artifact is supplied."
        answer_status = "CITATION_DRAFT_NOT_CONFIGURED"
    else:
        raw_answer = "Unsupported TRACE-Net answer mode."
        answer_status = "UNSUPPORTED_ANSWER_MODE"

    answer_text, leak_counts = sanitize_for_user(raw_answer)
    local_path_leak_count = leak_counts["local_path_leak_count"]
    raw_bytes_repr_count = leak_counts["raw_bytes_repr_count"]

    if not final_answer_used:
        final_answer_allowed_for_response = False
    else:
        final_answer_allowed_for_response = True

    supporting_sources = {
        "final_answer_report": str(config.final_answer_report) if config.final_answer_report else "",
        "community_aware_retrieval": str(config.community_aware_retrieval) if config.community_aware_retrieval else "",
        "opensearch_adapter": str(config.opensearch_adapter) if config.opensearch_adapter else "",
        "feedback_memory": str(config.feedback_memory) if config.feedback_memory else "",
        "leiden_communities": str(config.leiden_communities) if config.leiden_communities else "",
    }

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
        "retrieval_group_count": len(retrieval_groups),
        "community_aware_quality_status": get_quality_status(community_report),
        "feedback_memory_quality_status": get_quality_status(feedback_report),
        "leiden_quality_status": get_quality_status(leiden_report),
        "opensearch_quality_status": get_quality_status(opensearch_report),
        "local_path_leak_count": local_path_leak_count,
        "raw_bytes_repr_count": raw_bytes_repr_count,
        "can_answer_directly": final_answer_allowed_for_response,
        "can_prove_claims": final_answer_allowed_for_response,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
    }

    response = {
        "schema_version": SCHEMA_VERSION,
        "status": "ASK_API_RESPONSE_BUILT",
        "quality_status": "PASS" if local_path_leak_count == 0 and raw_bytes_repr_count == 0 else "FAIL",
        "request_id": stable_id("askreq", query, answer_mode, retrieval_mode, time.time_ns()),
        "generated_at": utc_now(),
        "model": config.model_name,
        "query": query,
        "answer_text": answer_text,
        "answer_markdown": answer_text,
        "summary": summary,
        "retrieval_groups": retrieval_groups,
        "supporting_sources": supporting_sources,
        "safety": {
            "llm_freeform_answer_allowed": False,
            "source_truth_mutation_allowed": False,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "local_path_leak_count": local_path_leak_count,
            "raw_bytes_repr_count": raw_bytes_repr_count,
        },
    }
    return response


def openai_chat_completion_response(query: str, ask_response: Mapping[str, Any], model_name: str) -> Dict[str, Any]:
    content = str(ask_response.get("answer_markdown") or ask_response.get("answer_text") or "")
    groups = ask_response.get("retrieval_groups") or []
    if isinstance(groups, list) and groups:
        lines = [content.rstrip(), "", "TRACE-Net retrieval groups:"]
        for group in groups[:8]:
            if not isinstance(group, Mapping):
                continue
            page = group.get("page_id") or "unknown-page"
            score = group.get("score")
            communities = group.get("community_ids") or []
            lines.append(f"- rank {group.get('rank')}: {page}; score={score}; communities={communities[:3]}")
        content = "\n".join(lines).strip()
    return {
        "id": stable_id("chatcmpl", query, time.time_ns()),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": ask_response.get("summary", {}),
    }


def build_api_report(config: AskApiConfig) -> Dict[str, Any]:
    final_report = read_json(config.final_answer_report)
    community_report = read_json(config.community_aware_retrieval)
    opensearch_report = read_json(config.opensearch_adapter)
    feedback_report = read_json(config.feedback_memory)
    leiden_report = read_json(config.leiden_communities)
    checks = {
        "final_answer_report_present": bool(final_report),
        "final_answer_report_quality_pass": get_quality_status(final_report) == "PASS" if final_report else False,
        "community_aware_retrieval_present": bool(community_report),
        "opensearch_adapter_present": bool(opensearch_report),
        "feedback_memory_present": bool(feedback_report),
        "leiden_communities_present": bool(leiden_report),
        "api_is_read_only": True,
        "source_truth_mutation_allowed_false": True,
    }
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "model_name": config.model_name,
        "default_answer_mode": config.default_answer_mode,
        "default_retrieval_mode": config.default_retrieval_mode,
        "final_answer_quality_status": get_quality_status(final_report),
        "final_answer_allowed": bool_from_payload(final_report, "final_answer_allowed", False),
        "community_aware_quality_status": get_quality_status(community_report),
        "opensearch_quality_status": get_quality_status(opensearch_report),
        "feedback_quality_status": get_quality_status(feedback_report),
        "leiden_quality_status": get_quality_status(leiden_report),
        "api_endpoint_count": 5,
        "read_only_api": True,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "ASK_API_CONFIG_BUILT",
        "quality_status": "PASS",
        "generated_at": utc_now(),
        "summary": summary,
        "checks": checks,
        "server": {"default_port": DEFAULT_PORT},
        "paths": {
            "final_answer_report": str(config.final_answer_report) if config.final_answer_report else "",
            "final_answer_markdown": str(config.final_answer_markdown) if config.final_answer_markdown else "",
            "community_aware_retrieval": str(config.community_aware_retrieval) if config.community_aware_retrieval else "",
            "opensearch_adapter": str(config.opensearch_adapter) if config.opensearch_adapter else "",
            "feedback_memory": str(config.feedback_memory) if config.feedback_memory else "",
            "leiden_communities": str(config.leiden_communities) if config.leiden_communities else "",
        },
    }
    return report


def quality_report(
    report: Mapping[str, Any],
    *,
    require_final_answer_quality_pass: bool = False,
    require_read_only: bool = True,
    max_source_truth_mutation_allowed: int = 0,
) -> Dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    checks = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "read_only_ok": (not require_read_only) or bool(summary.get("read_only_api")),
        "source_truth_mutation_allowed_ok": int(summary.get("source_truth_mutation_allowed_count", 999)) <= max_source_truth_mutation_allowed,
        "feedback_as_proof_zero": int(summary.get("feedback_as_proof_count", 999)) == 0,
        "community_as_proof_zero": int(summary.get("community_as_proof_count", 999)) == 0,
        "write_attempts_zero": int(summary.get("postgres_write_attempt_count", 999)) == 0
        and int(summary.get("qdrant_write_attempt_count", 999)) == 0
        and int(summary.get("opensearch_write_attempt_count", 999)) == 0,
    }
    if require_final_answer_quality_pass:
        checks["final_answer_quality_pass"] = summary.get("final_answer_quality_status") == "PASS"
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "quality_status": status,
        "generated_at": utc_now(),
        "summary": {
            "schema_version": SCHEMA_VERSION,
            "read_only_api": summary.get("read_only_api"),
            "source_truth_mutation_allowed_count": summary.get("source_truth_mutation_allowed_count", 0),
            "feedback_as_proof_count": summary.get("feedback_as_proof_count", 0),
            "community_as_proof_count": summary.get("community_as_proof_count", 0),
            "postgres_write_attempt_count": summary.get("postgres_write_attempt_count", 0),
            "qdrant_write_attempt_count": summary.get("qdrant_write_attempt_count", 0),
            "opensearch_write_attempt_count": summary.get("opensearch_write_attempt_count", 0),
            "final_answer_quality_status": summary.get("final_answer_quality_status", ""),
        },
        "checks": checks,
    }


class TraceNetAskRequestHandler(BaseHTTPRequestHandler):
    server_version = "TraceNetAskAPI/1.0"

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

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _config(self) -> AskApiConfig:
        return self.server.trace_net_config  # type: ignore[attr-defined]

    def _authorized(self) -> bool:
        api_key = self._config().api_key
        if not api_key:
            return True
        auth = self.headers.get("Authorization", "")
        x_key = self.headers.get("X-API-Key", "")
        return auth == f"Bearer {api_key}" or x_key == api_key

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json({"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/health", "/api/trace-net/health"}:
            self._send_json(
                {
                    "status": "ok",
                    "schema_version": SCHEMA_VERSION,
                    "service": "TRACE-Net Ask API v1",
                    "generated_at": utc_now(),
                    "read_only": True,
                }
            )
            return
        if parsed.path == "/v1/models":
            model = self._config().model_name
            self._send_json({"object": "list", "data": [{"id": model, "object": "model", "owned_by": "trace-net"}]})
            return
        self._send_json({"error": "not_found", "path": parsed.path}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._send_json({"error": "unauthorized"}, status=401)
            return
        parsed = urlparse(self.path)
        try:
            body = self._read_json_body()
        except Exception as exc:  # pragma: no cover - defensive
            self._send_json({"error": "invalid_json", "detail": str(exc)}, status=400)
            return

        if parsed.path in {"/api/trace-net/ask", "/trace-net/ask"}:
            query = str(body.get("query") or body.get("input") or "").strip()
            if not query:
                self._send_json({"error": "query is required"}, status=400)
                return
            response = build_trace_net_ask_response(
                query,
                self._config(),
                answer_mode=str(body.get("answer_mode") or self._config().default_answer_mode),
                retrieval_mode=str(body.get("retrieval_mode") or self._config().default_retrieval_mode),
                max_groups=int(body.get("max_groups") or 8),
            )
            self._send_json(response)
            return

        if parsed.path in {"/v1/chat/completions", "/api/chat/completions"}:
            messages = body.get("messages") or []
            query = ""
            if isinstance(messages, list):
                for message in reversed(messages):
                    if isinstance(message, Mapping) and message.get("role") == "user":
                        query = str(message.get("content") or "")
                        break
            query = query or str(body.get("prompt") or body.get("query") or "")
            if not query.strip():
                self._send_json({"error": "user message content is required"}, status=400)
                return
            ask = build_trace_net_ask_response(
                query.strip(),
                self._config(),
                answer_mode=str(body.get("answer_mode") or self._config().default_answer_mode),
                retrieval_mode=str(body.get("retrieval_mode") or self._config().default_retrieval_mode),
                max_groups=8,
            )
            self._send_json(openai_chat_completion_response(query.strip(), ask, self._config().model_name))
            return

        self._send_json({"error": "not_found", "path": parsed.path}, status=404)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("TRACE-Net Ask API: " + (fmt % args) + "\n")


def run_server(config: AskApiConfig, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), TraceNetAskRequestHandler)
    server.trace_net_config = config  # type: ignore[attr-defined]
    print("TRACE-Net Ask API v1")
    print(" Status: SERVER_RUNNING")
    print(f" url: http://{host}:{port}/")
    print(f" model: {config.model_name}")
    print(" safety: read-only; final-gate artifact required for final answers")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTRACE-Net Ask API stopped")
    finally:
        server.server_close()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run TRACE-Net Ask API v1")
    p.add_argument("--final-answer-report", type=Path, default=Path("local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json"))
    p.add_argument("--final-answer-markdown", type=Path, default=Path("local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1_answer.md"))
    p.add_argument("--community-aware-retrieval", type=Path, default=Path("local_data/organization/trace_net/community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1.json"))
    p.add_argument("--opensearch-adapter", type=Path, default=Path("local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json"))
    p.add_argument("--feedback-memory", type=Path, default=Path("local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json"))
    p.add_argument("--leiden-communities", type=Path, default=Path("local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json"))
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    p.add_argument("--api-key", default=os.environ.get("TRACE_NET_ASK_API_KEY", ""))
    p.add_argument("--default-answer-mode", default="final-gate", choices=["final-gate", "retrieval-only", "citation-draft"])
    p.add_argument("--default-retrieval-mode", default="community-aware")
    p.add_argument("--build-only", action="store_true")
    p.add_argument("--quality", action="store_true")
    p.add_argument("--open", action="store_true", help="Print URL. Browser opening is intentionally not automatic in this script.")
    return p.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> AskApiConfig:
    return AskApiConfig(
        final_answer_report=args.final_answer_report,
        final_answer_markdown=args.final_answer_markdown,
        community_aware_retrieval=args.community_aware_retrieval,
        opensearch_adapter=args.opensearch_adapter,
        feedback_memory=args.feedback_memory,
        leiden_communities=args.leiden_communities,
        output_dir=args.output_dir,
        default_answer_mode=args.default_answer_mode,
        default_retrieval_mode=args.default_retrieval_mode,
        model_name=args.model_name,
        api_key=args.api_key,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    config = config_from_args(args)
    report = build_api_report(config)
    report_path = config.output_dir / "trace_net_ask_api_v1.json"
    write_json(report_path, report)
    quality_path = config.output_dir / "trace_net_ask_api_v1_quality.json"
    quality = quality_report(report)
    write_json(quality_path, quality)
    summary_path = config.output_dir / "trace_net_ask_api_v1_summary.json"
    write_json(summary_path, report["summary"])

    print("TRACE-Net Ask API v1")
    print(" Status: ASK_API_CONFIG_BUILT")
    print(f" Quality status: {quality['quality_status']}")
    print(f" model_name: {config.model_name}")
    print(f" default_answer_mode: {config.default_answer_mode}")
    print(f" final_answer_quality_status: {report['summary'].get('final_answer_quality_status')}")
    print(f" final_answer_allowed: {report['summary'].get('final_answer_allowed')}")
    print(f" report_path: {report_path}")
    print(f" quality_path: {quality_path}")

    if args.build_only:
        return 0 if quality["quality_status"] == "PASS" else 1
    run_server(config, args.host, args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
