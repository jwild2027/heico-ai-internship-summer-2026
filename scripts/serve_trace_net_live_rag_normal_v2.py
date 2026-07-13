#!/usr/bin/env python3
"""TRACE-Net truthful live normal endpoint v2.

Wraps the existing v27 live orchestrator and exposes both native and
OpenAI-compatible routes with:

- live request-time retrieval (not canned smoke matching)
- fail-closed source-backed citations
- safe Gemma draft acceptance only when every cited fact resolves
- readable answers instead of internal JSON
- API-key validation, request-size limits, concurrency limits, streaming,
  model listing, service identity, artifact checksum, and structured health
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_live_rag_normal_v2"
MODEL_ID = "trace-net-live-rag-normal-v2"
MAX_REQUEST_BYTES_DEFAULT = 1_000_000

PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b")
MANUAL_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b")
CITATION_RE = re.compile(r"\[(\d{1,3})\]")
DANGEROUS_CLAIMS = (
    "interchangeable", "interchangeability", "approved replacement",
    "safe to install", "safe installation", "fits", "fitment",
    "eligible", "eligibility", "effectivity", "approved for",
)
AUTHORITY_FIELDS = (
    "approval", "interchange", "effectivity", "eligibility",
    "installation_authority", "approved_replacement",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL, timeout=2
        ).strip()
    except Exception:
        return os.environ.get("TRACE_NET_GIT_COMMIT", "unknown")


def import_v27() -> Any:
    return importlib.import_module("tiff.trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27")


def load_state(manifest: Path, overrides: Mapping[str, Any]) -> Tuple[Any, Dict[str, Any]]:
    if not manifest.exists():
        raise FileNotFoundError(f"v27 manifest does not exist: {manifest}")
    v27 = import_v27()
    state = v27.load_state_for_serving(manifest)
    for key, value in overrides.items():
        if value is not None:
            state[key] = value
    state["model_id"] = MODEL_ID
    return v27, state


def extract_latest_user(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for item in reversed(messages):
        if not isinstance(item, Mapping) or str(item.get("role", "")).lower() != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for block in content:
                if isinstance(block, Mapping):
                    text = block.get("text") or block.get("content")
                    if text:
                        parts.append(str(text))
            return "\n".join(parts).strip()
    return ""


def extract_query(payload: Mapping[str, Any]) -> str:
    for key in ("query", "question", "input", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return extract_latest_user(payload.get("messages"))


def validate_direct_citations(result: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    retrieval = result.get("retrieval") if isinstance(result.get("retrieval"), Mapping) else {}
    rows = retrieval.get("direct_evidence") if isinstance(retrieval, Mapping) else []
    citations: List[Dict[str, Any]] = []
    failures: List[str] = []
    seen = set()
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, Mapping):
            failures.append("non_mapping_direct_evidence")
            continue
        page_id = str(raw.get("page_id") or "").strip()
        field_name = str(raw.get("field_name") or "").strip()
        value = str(raw.get("normalized_value") or "").strip()
        document_id = str(raw.get("document_id") or "").strip()
        if not page_id or not field_name or not value:
            failures.append("missing_source_backed_citation_fields")
            continue
        key = (page_id, field_name, value)
        if key in seen:
            continue
        seen.add(key)
        citations.append({
            "citation_id": len(citations) + 1,
            "page_id": page_id,
            "field_name": field_name,
            "normalized_value": value,
            "document_id": document_id,
            "source_trace_ready": True,
            "citation_ready": True,
            "direct_proof_authority": True,
        })
    return citations, failures


def _supported_tokens(citations: Sequence[Mapping[str, Any]], query: str) -> Tuple[set[str], set[str], set[str]]:
    blob = " ".join(
        f"{c.get('page_id','')} {c.get('field_name','')} {c.get('normalized_value','')}"
        for c in citations
    )
    return set(PART_RE.findall(blob)), set(MANUAL_RE.findall(blob)), set(PAGE_RE.findall(blob))


def validate_llm_draft(
    draft: str,
    citations: Sequence[Mapping[str, Any]],
    query: str,
) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    text = str(draft or "").strip()
    if not text:
        return False, ["empty_llm_draft"]
    if text.startswith("{") or "TRACE-NET LIVE CONTEXT PACK" in text:
        failures.append("prompt_or_json_leak")

    valid_ids = {int(c.get("citation_id", i + 1)) for i, c in enumerate(citations)}
    cited_ids = {int(x) for x in CITATION_RE.findall(text)}
    if citations and not cited_ids:
        failures.append("draft_missing_citations")
    if not cited_ids.issubset(valid_ids):
        failures.append("draft_has_unknown_citation_id")

    supported_parts, supported_manuals, supported_pages = _supported_tokens(citations, query)
    for token in PART_RE.findall(text):
        if token not in supported_parts:
            failures.append(f"unsupported_part_number:{token}")
    for token in MANUAL_RE.findall(text):
        if token not in supported_manuals:
            failures.append(f"unsupported_manual_reference:{token}")
    for token in PAGE_RE.findall(text):
        if token not in supported_pages:
            failures.append(f"unsupported_page_id:{token}")

    lower = text.lower()
    authority_blob = " ".join(str(c.get("field_name") or "").lower() for c in citations)
    if any(term in lower for term in DANGEROUS_CLAIMS) and not any(field in authority_blob for field in AUTHORITY_FIELDS):
        failures.append("dangerous_claim_without_authority_field")
    return not failures, failures


def render_citation_lines(citations: Sequence[Mapping[str, Any]], limit: int = 8) -> str:
    lines: List[str] = []
    for citation in citations[:limit]:
        lines.append(
            f"[{citation.get('citation_id')}] page={citation.get('page_id')} "
            f"field={citation.get('field_name')} value={citation.get('normalized_value')}"
        )
    return "\n".join(lines)


def compose_result(query: str, raw: Mapping[str, Any]) -> Dict[str, Any]:
    citations, citation_failures = validate_direct_citations(raw)
    deterministic = str(raw.get("final_answer") or "").strip()
    draft = str(raw.get("llm_draft_text") or "").strip()
    draft_ok, draft_failures = validate_llm_draft(draft, citations, query)

    llm_succeeded = str(raw.get("llm_status") or "") == "LLM_CALL_SUCCEEDED"
    used_llm_draft = bool(llm_succeeded and draft_ok and citations)
    content = draft if used_llm_draft else deterministic
    if not content:
        content = (
            "TRACE-Net did not produce a source-backed answer. "
            "No factual claim is made."
        )

    if citations:
        content = content.rstrip() + "\n\nSources:\n" + render_citation_lines(citations)
    elif bool(raw.get("final_answer_ready_for_webui")):
        content = (
            "TRACE-Net blocked the answer because the result did not include "
            "complete source-backed citation fields."
        )

    final_ready = bool(raw.get("final_answer_ready_for_webui")) and bool(citations)
    quality = "PASS" if (final_ready or str(raw.get("final_gate_status")) == "LIVE_ORCHESTRATOR_AUDIT_ONLY") else "WARN"
    return {
        "module": MODULE,
        "quality_status": quality,
        "route": "normal_ask",
        "query": query,
        "content": content,
        "citation_count": len(citations),
        "citations": citations,
        "source_citation_failures": citation_failures,
        "llm_draft_used": used_llm_draft,
        "llm_draft_validation_failures": draft_failures,
        "final_gate_status": raw.get("final_gate_status"),
        "final_answer_ready_for_webui": final_ready,
        "matched_source_truth": bool(citations),
        "query_plan": raw.get("query_plan", {}),
        "retrieval_summary": {
            "total_match_count": (raw.get("retrieval") or {}).get("total_match_count"),
            "returned_match_count": (raw.get("retrieval") or {}).get("returned_match_count"),
            "result_was_capped": (raw.get("retrieval") or {}).get("result_was_capped"),
        },
        "guidance_summary": {
            "graph_guidance_count": len((raw.get("guidance") or {}).get("graph_guidance") or []),
            "v2_summary_guidance_count": len((raw.get("guidance") or {}).get("v2_summary_guidance") or []),
        },
        "llm_status": raw.get("llm_status"),
        "stage_timings_ms": raw.get("stage_timings_ms", {}),
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "safety_contract": {
            "read_only": True,
            "citation_values_derived_from_answer_text": False,
            "source_backed_citations_required": True,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }


def run_normal_query(v27: Any, state: Mapping[str, Any], query: str) -> Dict[str, Any]:
    raw = v27.run_live_query_v27(query, state)
    return compose_result(query, raw)


def openai_response(model: str, result: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": "chatcmpl-trace-normal-v2-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result["content"]}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": dict(result),
    }


def openai_error(message: str, code: str, status: int) -> Dict[str, Any]:
    return {"error": {"message": message, "type": "trace_net_error", "param": None, "code": code}, "status": status}


class Runtime:
    def __init__(
        self,
        *,
        v27: Any,
        state: Dict[str, Any],
        manifest: Path,
        api_key: str,
        max_request_bytes: int,
        max_concurrency: int,
    ):
        self.v27 = v27
        self.state = state
        self.manifest = manifest
        self.manifest_sha256 = sha256_file(manifest)
        self.api_key = api_key
        self.max_request_bytes = max_request_bytes
        self.semaphore = threading.BoundedSemaphore(max(1, max_concurrency))
        self.git_commit = git_commit()

    def health(self) -> Dict[str, Any]:
        exact_count = len(self.state.get("exact_search_documents") or [])
        graph_count = len(self.state.get("page_to_community") or {})
        summary_count = len(self.state.get("page_summaries") or {})
        ready = exact_count > 0 and str(self.state.get("quality_status") or "").upper() == "PASS"
        return {
            "status": "ok" if ready else "needs_repair",
            "quality_status": "PASS" if ready else "FAIL",
            "module": MODULE,
            "version": "v2",
            "model_id": MODEL_ID,
            "git_commit": self.git_commit,
            "manifest_path": str(self.manifest),
            "manifest_sha256": self.manifest_sha256,
            "v27_module": getattr(self.v27, "MODULE", "unknown"),
            "exact_search_document_count": exact_count,
            "page_summary_count": summary_count,
            "leiden_page_membership_count": graph_count,
            "live_request_time_retrieval": True,
            "canned_smoke_matcher": False,
            "source_backed_citations_required": True,
            "answer_permission": False,
            "final_answer_allowed": False,
        }


def make_handler(runtime: Runtime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetLiveRagNormalV2/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send(self, status: int, payload: Mapping[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            return self.headers.get("Authorization", "") == f"Bearer {runtime.api_key}"

        def _read_json(self) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[int, Dict[str, Any]]]]:
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0:
                return None, (400, openai_error("Request body is required.", "invalid_request", 400))
            if length > runtime.max_request_bytes:
                return None, (413, openai_error("Request body exceeds TRACE-Net limit.", "request_too_large", 413))
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                return None, (400, openai_error(f"Invalid JSON: {exc}", "invalid_json", 400))
            if not isinstance(value, dict):
                return None, (400, openai_error("JSON body must be an object.", "invalid_request", 400))
            return value, None

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/health":
                self._send(200, runtime.health())
                return
            if not self._authorized():
                self._send(401, openai_error("Invalid or missing API key.", "unauthorized", 401))
                return
            if path == "/v1/models":
                self._send(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": int(time.time()), "owned_by": "trace-net-local"}]})
                return
            self._send(404, openai_error("Route not found.", "not_found", 404))

        def do_POST(self) -> None:
            if not self._authorized():
                self._send(401, openai_error("Invalid or missing API key.", "unauthorized", 401))
                return
            if not runtime.semaphore.acquire(blocking=False):
                self._send(429, openai_error("TRACE-Net is at its concurrency limit.", "rate_limit", 429))
                return
            try:
                payload, error = self._read_json()
                if error:
                    self._send(*error)
                    return
                assert payload is not None
                query = extract_query(payload)
                if not query:
                    self._send(400, openai_error("Missing query or user message.", "missing_query", 400))
                    return
                result = run_normal_query(runtime.v27, runtime.state, query)
                path = self.path.split("?", 1)[0]
                if path == "/api/trace-net/ask":
                    self._send(200, result)
                    return
                if path == "/v1/chat/completions":
                    response = openai_response(str(payload.get("model") or MODEL_ID), result)
                    if bool(payload.get("stream")):
                        data = "data: " + json.dumps(response, ensure_ascii=False) + "\n\ndata: [DONE]\n\n"
                        raw = data.encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Content-Length", str(len(raw)))
                        self.end_headers()
                        self.wfile.write(raw)
                    else:
                        self._send(200, response)
                    return
                self._send(404, openai_error("Route not found.", "not_found", 404))
            except Exception as exc:
                self._send(500, openai_error(f"{type(exc).__name__}: {exc}", "internal_error", 500))
            finally:
                runtime.semaphore.release()

    return Handler


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8014)
    p.add_argument("--live-orchestrator-stage-timing-fastpath", required=True)
    p.add_argument("--llm-mode", choices=["simulate", "ollama"], default="ollama")
    p.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")
    p.add_argument("--llm-model", default="gemma4:26b")
    p.add_argument("--llm-api-key", default="ollama")
    p.add_argument("--request-timeout", type=int, default=240)
    p.add_argument("--fast-path-mode", choices=["exact", "all_direct", "off"], default="exact")
    p.add_argument("--api-key", default=os.environ.get("TRACE_NET_API_KEY", "trace-net-local"))
    p.add_argument("--max-request-bytes", type=int, default=MAX_REQUEST_BYTES_DEFAULT)
    p.add_argument("--max-concurrency", type=int, default=4)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = Path(args.live_orchestrator_stage_timing_fastpath)
    v27, state = load_state(manifest, {
        "llm_mode": args.llm_mode,
        "llm_base_url": args.llm_base_url,
        "llm_model": args.llm_model,
        "llm_api_key": args.llm_api_key,
        "request_timeout": args.request_timeout,
        "fast_path_mode": args.fast_path_mode,
    })
    runtime = Runtime(
        v27=v27,
        state=state,
        manifest=manifest,
        api_key=args.api_key,
        max_request_bytes=args.max_request_bytes,
        max_concurrency=args.max_concurrency,
    )
    health = runtime.health()
    if health["quality_status"] != "PASS":
        raise SystemExit("TRACE-Net normal v2 refused to start: v27 state is not PASS/live-ready")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print("status=TRACE_NET_LIVE_RAG_NORMAL_V2_READY")
    print(f"quality_status={health['quality_status']}")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"model={MODEL_ID}")
    print(f"exact_search_document_count={health['exact_search_document_count']}")
    print(f"page_summary_count={health['page_summary_count']}")
    print(f"leiden_page_membership_count={health['leiden_page_membership_count']}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
