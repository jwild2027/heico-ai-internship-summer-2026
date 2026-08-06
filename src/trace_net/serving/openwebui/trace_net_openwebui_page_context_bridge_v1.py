"""TRACE-Net OpenWebUI page-context bridge v1.

This module is intentionally a thin adapter. It does not replace the current
V3 bridge or Gemma answer runner. Instead, it detects page-centered questions,
builds a page_context_pack_v3 binder, and injects that binder into OpenAI-style
chat messages before forwarding to the existing V3 bridge.

Safety contract:
- read-only artifact access
- no Postgres/Qdrant/OpenSearch writes
- no source-truth mutation
- no answer permission
- graph/vector/visual/summary records remain guidance unless backed by proof
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_openwebui_page_context_bridge_v1"
VERSION = "1.0.0"
DEFAULT_MODEL_ID = "trace-net-page-context-v3-bridge"
DEFAULT_UPSTREAM_MODEL = "trace-net-gemma4-engram-e2e-v3"
DEFAULT_NATIVE_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_NATIVE_LLM_MODEL = "gemma4:26b"
DEFAULT_NATIVE_NUM_CTX = 8192
DEFAULT_NATIVE_MAX_TOKENS = 1200

_PAGE_PHRASE_RE = re.compile(
    r"\bpages?\s+(?P<body>(?:p0*\d{1,6}|\d{1,4}|and|to|through|,|\s|-)+)",
    re.IGNORECASE,
)
_P_ID_RE = re.compile(r"\bp0*(?P<num>\d{1,6})\b", re.IGNORECASE)
_INT_RE = re.compile(r"\d{1,4}")


@dataclass(frozen=True)
class PageContextArtifactPaths:
    route_manifest: str = "local_data/organization/trace_net/calibrated_cascade_route_brain_v35_3/trace_net_cascade_route_manifest_v35_3.json"
    graph_export: str = "local_data/organization/trace_net/anchor_aware_graph_leiden_expander_gemma4_native_001/trace_net_anchor_aware_graph_leiden_expander_v1.json"
    ocr_records: str = "local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json"
    table_evidence: str = "local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json"
    exact_part_records: str = "local_data/organization/trace_net/part_number_exact_retrieval_probe_gemma4_native_001/trace_net_part_number_exact_retrieval_probe_v1.json"
    visual_summaries: str = "local_data/organization/trace_net/e2e_image_visual_observer_route/trace_net_e2e_image_visual_observer_route_v34.json"
    vector_hits: str = "local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json"

    def existing_cli_args(self, repo_root: Path) -> List[str]:
        """Return only optional artifact CLI args that exist on disk."""
        mapping = [
            ("--graph-export", self.graph_export),
            ("--ocr-records", self.ocr_records),
            ("--table-evidence", self.table_evidence),
            ("--exact-part-records", self.exact_part_records),
            ("--visual-summaries", self.visual_summaries),
            ("--vector-hits", self.vector_hits),
        ]
        args: List[str] = []
        for flag, rel in mapping:
            if (repo_root / rel).exists():
                args.extend([flag, rel])
        return args

    def missing_paths(self, repo_root: Path) -> List[str]:
        paths = asdict(self)
        return [rel for rel in paths.values() if rel and not (repo_root / rel).exists()]


def _dedupe_ints(values: Iterable[int]) -> List[int]:
    seen = set()
    out = []
    for value in values:
        if value <= 0:
            continue
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def extract_page_numbers(question: str) -> List[int]:
    """Extract explicit page numbers while avoiding part-number false positives.

    This intentionally requires a page-like cue, such as "page", "pages", or
    p000202. It does not parse arbitrary integers from part numbers.
    """
    text = question or ""
    pages: List[int] = []

    for match in _PAGE_PHRASE_RE.finditer(text):
        body = match.group("body") or ""

        # Parse page-id tokens such as p000202 first and remove them before
        # collecting plain integers. Otherwise the leading zero padding can be
        # partially interpreted as a separate page, for example p000202 -> 2.
        p_id_numbers = [int(token.group("num")) for token in _P_ID_RE.finditer(body)]
        body_without_p_ids = _P_ID_RE.sub(" ", body)
        ints = [int(token) for token in _INT_RE.findall(body_without_p_ids)]

        # Support small ranges like "pages 48-50", "pages 48 to 50", or
        # "pages p000048-p000050".
        range_like = bool(re.search(r"\b(to|through)\b|-", body, re.IGNORECASE))
        if len(p_id_numbers) == 2 and range_like:
            start, end = p_id_numbers
            if 0 < start <= end and (end - start) <= 25:
                pages.extend(range(start, end + 1))
            else:
                pages.extend(p_id_numbers)
        else:
            pages.extend(p_id_numbers)

        if len(ints) == 2 and range_like:
            start, end = ints
            if 0 < start <= end and (end - start) <= 25:
                pages.extend(range(start, end + 1))
            else:
                pages.extend(ints)
        else:
            pages.extend(ints)

    # Also allow page-id tokens outside a page phrase, e.g. "show p000202".
    for match in _P_ID_RE.finditer(text):
        pages.append(int(match.group("num")))

    return _dedupe_ints(pages)


def should_use_page_context(question: str) -> bool:
    lowered = (question or "").lower()
    return bool(extract_page_numbers(question)) or "random page" in lowered or "source page" in lowered


def latest_user_question(messages: Sequence[Mapping[str, Any]]) -> str:
    for msg in reversed(list(messages or [])):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, Mapping) and item.get("type") == "text":
                        text_parts.append(str(item.get("text", "")))
                return "\n".join(text_parts)
    return ""


def _safe_filename_fragment(text: str, limit: int = 80) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
    cleaned = cleaned.strip("_")[:limit]
    return cleaned or "question"


def default_output_path(question: str, pages: Sequence[int]) -> str:
    page_part = "_".join(str(p) for p in pages[:12]) if pages else _safe_filename_fragment(question)
    return (
        "local_data/organization/trace_net/page_context_pack_v3/"
        f"trace_net_page_context_pack_v3_openwebui_pages_{page_part}.json"
    )


def build_page_context_pack_via_cli(
    *,
    question: str,
    pages: Sequence[int],
    repo_root: str | Path = ".",
    output_path: str | Path | None = None,
    artifact_paths: PageContextArtifactPaths | None = None,
    max_pages: int = 8,
    python_executable: str | None = None,
) -> Dict[str, Any]:
    """Build a page_context_pack_v3 by invoking the existing builder script."""
    repo = Path(repo_root).resolve()
    paths = artifact_paths or PageContextArtifactPaths()
    py = python_executable or sys.executable
    out_rel = str(output_path or default_output_path(question, pages))

    route_manifest = repo / paths.route_manifest
    if not route_manifest.exists():
        raise FileNotFoundError(f"route manifest not found: {paths.route_manifest}")

    cmd = [
        py,
        "scripts/build/context/build_trace_net_page_context_pack_v3.py",
        "--question",
        question,
        "--route-manifest",
        paths.route_manifest,
        "--max-pages",
        str(max_pages),
        "--output",
        out_rel,
    ]
    if pages:
        cmd.append("--pages")
        cmd.extend(str(p) for p in pages)
    cmd.extend(paths.existing_cli_args(repo))

    start = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    duration_ms = int((time.time() - start) * 1000)
    if proc.returncode != 0:
        raise RuntimeError(
            "page context builder failed\n"
            f"returncode={proc.returncode}\n"
            f"stdout={proc.stdout[-4000:]}\n"
            f"stderr={proc.stderr[-4000:]}"
        )

    out_path = repo / out_rel
    if not out_path.exists():
        raise FileNotFoundError(f"builder did not create output: {out_rel}")
    pack = json.loads(out_path.read_text(encoding="utf-8"))
    pack.setdefault("bridge_build", {})
    pack["bridge_build"].update(
        {
            "module": MODULE,
            "version": VERSION,
            "builder_duration_ms": duration_ms,
            "builder_stdout_tail": proc.stdout[-2000:],
            "builder_stderr_tail": proc.stderr[-2000:],
            "output_path": out_rel,
            "missing_optional_artifact_paths": paths.missing_paths(repo),
        }
    )
    return pack


def count_pack_records(pack: Mapping[str, Any]) -> Dict[str, int]:
    summary = pack.get("summary") if isinstance(pack.get("summary"), Mapping) else {}
    counts = {
        "selected_page_count": int(summary.get("selected_page_count", 0) or 0),
        "source_trace_ready_page_count": int(summary.get("source_trace_ready_page_count", 0) or 0),
        "proof_record_count": int(summary.get("proof_record_count", 0) or 0),
        "guidance_record_count": int(summary.get("guidance_record_count", 0) or 0),
        "answer_permission_count": int(summary.get("answer_permission_count", 0) or 0),
        "source_truth_mutation_allowed_count": int(summary.get("source_truth_mutation_allowed_count", 0) or 0),
    }
    return counts


def _sample(value: Any, max_chars: int = 700) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def render_page_context_binder(pack: Mapping[str, Any], *, max_chars: int = 14000) -> str:
    """Render a compact source-bounded binder for Gemma."""
    counts = count_pack_records(pack)
    query = pack.get("query_entities", {}) if isinstance(pack.get("query_entities"), Mapping) else {}
    rwo = pack.get("reasoning_work_order", {}) if isinstance(pack.get("reasoning_work_order"), Mapping) else {}

    lines: List[str] = []
    lines.append("TRACE-NET PAGE CONTEXT BINDER V3")
    lines.append("Use this as a source-bounded evidence binder, not as a canned answer.")
    lines.append("Gemma should synthesize cautiously for complex questions while obeying the proof limits.")
    lines.append("")
    lines.append("QUESTION")
    lines.append(str(query.get("question") or pack.get("question") or ""))
    lines.append("")
    lines.append("QUALITY / SAFETY SUMMARY")
    lines.append(json.dumps(counts, sort_keys=True))
    lines.append("Safety rule: answer_permission and source_truth_mutation_allowed must remain false/zero.")
    lines.append("Only current proof/source-locator records can support factual source claims.")
    lines.append("Graph, vector, visual, summary, and route guidance are retrieval guidance unless backed by proof.")
    lines.append("")
    lines.append("REASONING WORK ORDER")
    lines.append(f"model_should_think: {bool(rwo.get('model_should_think'))}")
    if rwo.get("purpose"):
        lines.append(f"purpose: {rwo.get('purpose')}")
    for key in ("allowed_reasoning", "disallowed_reasoning", "answer_sections"):
        values = rwo.get(key)
        if isinstance(values, list) and values:
            lines.append(f"{key}:")
            for item in values[:8]:
                lines.append(f"- {item}")
    lines.append("")

    for record in pack.get("page_context_records", []) or []:
        if not isinstance(record, Mapping):
            continue
        lines.append("PAGE CONTEXT RECORD")
        lines.append(f"page_number: {record.get('page_number')}")
        lines.append(f"page_id: {record.get('page_id')}")
        lines.append(f"primary_route: {record.get('primary_route')}")
        lines.append(f"source_trace_ready: {record.get('source_trace_ready')}")
        lines.append(f"proof_record_count: {record.get('proof_record_count')}")
        lines.append(f"guidance_record_count: {record.get('guidance_record_count')}")
        if record.get("route_evidence_priority"):
            lines.append("route_evidence_priority: " + ", ".join(map(str, record.get("route_evidence_priority", []))))
        if record.get("page_reasoning_tasks"):
            lines.append("page_reasoning_tasks:")
            for task in record.get("page_reasoning_tasks", [])[:6]:
                lines.append(f"- {task}")

        for key in (
            "source_files",
            "source_links",
            "ocr_excerpts",
            "table_evidence",
            "exact_part_hits",
            "visual_guidance",
            "route_guidance",
            "graph_neighbors",
            "vector_guidance",
        ):
            values = record.get(key)
            if isinstance(values, list) and values:
                lines.append(f"{key} ({len(values)}):")
                for item in values[:3]:
                    lines.append("- " + _sample(item))
        lines.append("")

    binder = "\n".join(lines).strip()
    if len(binder) > max_chars:
        binder = binder[: max_chars - 300] + "\n\n[TRUNCATED: binder shortened for prompt budget. Preserve safety and proof limits.]"
    return binder


def enrich_openai_messages(
    messages: Sequence[Mapping[str, Any]],
    pack: Mapping[str, Any],
    *,
    max_binder_chars: int = 14000,
) -> List[Dict[str, Any]]:
    binder = render_page_context_binder(pack, max_chars=max_binder_chars)
    binder_message = {
        "role": "system",
        "content": binder,
    }
    original = [dict(m) for m in messages]
    # Preserve existing system messages first, then insert binder before user content.
    system_messages = [m for m in original if m.get("role") == "system"]
    non_system_messages = [m for m in original if m.get("role") != "system"]
    return system_messages + [binder_message] + non_system_messages


def enrich_chat_payload(
    payload: MutableMapping[str, Any],
    *,
    repo_root: str | Path = ".",
    artifact_paths: PageContextArtifactPaths | None = None,
    output_path: str | None = None,
    max_pages: int = 8,
    max_binder_chars: int = 14000,
    python_executable: str | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        raise ValueError("payload.messages must be a list")
    question = latest_user_question(messages)
    pages = extract_page_numbers(question)
    bridge_meta: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "page_context_used": False,
        "detected_pages": pages,
        "question": question,
    }
    enriched = dict(payload)

    if not should_use_page_context(question) or not pages:
        bridge_meta["reason"] = "no explicit page query detected"
        return enriched, bridge_meta

    pack = build_page_context_pack_via_cli(
        question=question,
        pages=pages,
        repo_root=repo_root,
        output_path=output_path,
        artifact_paths=artifact_paths,
        max_pages=max_pages,
        python_executable=python_executable,
    )
    enriched["messages"] = enrich_openai_messages(messages, pack, max_binder_chars=max_binder_chars)
    # Preserve requested model by default. The proxy server may override to upstream_model.
    bridge_meta.update(
        {
            "page_context_used": True,
            "context_pack_quality_status": pack.get("quality_status"),
            "context_pack_summary": pack.get("summary"),
            "context_pack_output_path": pack.get("bridge_build", {}).get("output_path") or output_path,
            "context_pack_page_ids": [r.get("page_id") for r in pack.get("page_context_records", []) if isinstance(r, Mapping)],
        }
    )
    return enriched, bridge_meta



def normalize_ollama_openai_base_url(base_url: str) -> str:
    """Normalize Ollama/OpenAI-compatible base URL to the /v1 base.

    The lower-level OpenAI-compatible call appends /chat/completions, so a raw
    Ollama root such as http://127.0.0.1:11434 must become
    http://127.0.0.1:11434/v1.
    """
    raw = (base_url or DEFAULT_NATIVE_LLM_BASE_URL).strip().rstrip("/")
    if not raw:
        return DEFAULT_NATIVE_LLM_BASE_URL
    if raw.endswith("/chat/completions"):
        raw = raw[: -len("/chat/completions")]
    if raw.endswith("/v1"):
        return raw
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme and parsed.netloc and parsed.path in ("", "/"):
        return raw + "/v1"
    return raw


def ollama_native_api_base_url(base_url: str) -> str:
    """Return the root Ollama URL for /api/chat calls.

    The OpenAI-compatible base is usually http://host:11434/v1, but the native
    Ollama chat endpoint lives at http://host:11434/api/chat. This helper
    accepts either form so the CLI can keep accepting /v1 or raw Ollama roots.
    """
    raw = (base_url or DEFAULT_NATIVE_LLM_BASE_URL).strip().rstrip("/")
    if not raw:
        raw = DEFAULT_NATIVE_LLM_BASE_URL
    if raw.endswith("/chat/completions"):
        raw = raw[: -len("/chat/completions")]
    if raw.endswith("/v1"):
        raw = raw[: -len("/v1")]
    return raw.rstrip("/")



class NativePageAnswerError(RuntimeError):
    """Raised when native page-answer generation attempted but cannot be safely used."""

    def __init__(self, message: str, *, llm_attempted: bool = False, llm_metadata: Optional[Mapping[str, Any]] = None):
        super().__init__(message)
        self.llm_attempted = bool(llm_attempted)
        self.llm_metadata = dict(llm_metadata or {})


def render_native_page_answer_messages(
    pack: Mapping[str, Any],
    *,
    question: str,
    max_binder_chars: int = 14000,
    strict_final_content: bool = False,
) -> List[Dict[str, str]]:
    """Create a direct Gemma prompt for page-binder questions.

    This lets the model reason from the binder itself instead of relying on the
    upstream exact-search endpoint to reinterpret the injected context. When
    strict_final_content is true, this is a retry prompt that explicitly asks
    thinking models to put the final answer in message.content.
    """
    binder = render_page_context_binder(pack, max_chars=max_binder_chars)
    system = (
        "You are the TRACE-Net page-binder answer writer. Answer from the provided "
        "page_context_pack_v3 binder only. You may synthesize cautiously for complex "
        "questions, but you must separate proof from guidance. Use the sections: "
        "Answer, Evidence, Engineering confidence, Limits. Mention every requested "
        "page number and page_id. Do not infer interchangeability, fit, effectivity, "
        "replacement approval, installation safety, or procurement authority unless "
        "explicit source proof is present. Never output hidden reasoning as the answer."
    )
    if strict_final_content:
        system += (
            " This is a final-answer retry. Put the complete user-visible final answer "
            "in message.content. Do not return an empty content field. Start exactly with 'Answer'."
        )
    user = (
        f"USER QUESTION:\n{question}\n\n"
        f"{binder}\n\n"
        "Write the answer now. Keep it concise, source-bounded, and explicit about limits. "
        "The final answer must be visible in message.content."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_native_ollama_openai_chat(
    *,
    messages: Sequence[Mapping[str, str]],
    base_url: str = DEFAULT_NATIVE_LLM_BASE_URL,
    model: str = DEFAULT_NATIVE_LLM_MODEL,
    api_key: str = "ollama",
    temperature: float = 0.1,
    timeout: float = 300.0,
    attempt_label: str = "primary",
    num_ctx: int = DEFAULT_NATIVE_NUM_CTX,
    max_tokens: int = DEFAULT_NATIVE_MAX_TOKENS,
) -> Tuple[str, Dict[str, Any]]:
    """Call Ollama native /api/chat for page-binder answers.

    Ollama's OpenAI-compatible endpoint can return a large `reasoning` field
    and an empty `message.content` for thinking models when the context budget
    is hit. TRACE-Net needs user-visible final content, not hidden reasoning, so
    this native path calls /api/chat with thinking disabled and a larger context
    window. Reasoning/thinking fields are still detected and never used as
    answer text.
    """
    api_base = ollama_native_api_base_url(base_url)
    url = api_base.rstrip("/") + "/api/chat"
    safe_num_ctx = max(4096, int(num_ctx or DEFAULT_NATIVE_NUM_CTX))
    safe_max_tokens = max(256, int(max_tokens or DEFAULT_NATIVE_MAX_TOKENS))
    payload_obj = {
        "model": model,
        "messages": list(messages),
        "stream": False,
        "think": False,
        "options": {
            "temperature": float(temperature),
            "num_ctx": safe_num_ctx,
            "num_predict": safe_max_tokens,
        },
    }
    payload = json.dumps(payload_obj).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key or 'ollama'}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - local dev LLM endpoint
        data = json.loads(resp.read().decode("utf-8"))

    message = data.get("message") if isinstance(data, Mapping) else {}
    if not isinstance(message, Mapping):
        message = {}
    content = str(message.get("content") or "").strip()
    prompt_tokens = int(data.get("prompt_eval_count", 0) or 0)
    completion_tokens = int(data.get("eval_count", 0) or 0)
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    metadata = {
        "native_llm_url": url,
        "native_llm_provider_endpoint": "ollama_api_chat",
        "native_llm_model": model,
        "native_llm_attempt_label": attempt_label,
        "native_llm_num_ctx": safe_num_ctx,
        "native_llm_max_tokens": safe_max_tokens,
        "provider_response_id": data.get("id"),
        "finish_reason": data.get("done_reason"),
        "done": data.get("done"),
        "usage": usage,
        "message_keys": sorted(str(k) for k in message.keys()),
        "content_length": len(content),
        "empty_content": not bool(content),
        "reasoning_omitted_from_draft": "reasoning" in message or "thinking" in message,
        "reasoning_field_present": "reasoning" in message,
        "thinking_field_present": "thinking" in message,
        "think_disabled_requested": True,
    }
    return content, metadata


def build_native_page_context_response(
    *,
    pack: Mapping[str, Any],
    meta: Mapping[str, Any],
    question: str,
    model_id: str,
    native_llm_base_url: str,
    native_llm_model: str,
    native_llm_api_key: str = "ollama",
    native_temperature: float = 0.1,
    native_request_timeout: float = 300.0,
    native_num_ctx: int = DEFAULT_NATIVE_NUM_CTX,
    native_max_tokens: int = DEFAULT_NATIVE_MAX_TOKENS,
    max_binder_chars: int = 14000,
    created: Optional[int] = None,
) -> Dict[str, Any]:
    messages = render_native_page_answer_messages(pack, question=question, max_binder_chars=max_binder_chars)
    started = time.time()
    content, llm_metadata = call_native_ollama_openai_chat(
        messages=messages,
        base_url=native_llm_base_url,
        model=native_llm_model,
        api_key=native_llm_api_key,
        temperature=native_temperature,
        timeout=native_request_timeout,
        attempt_label="primary",
        num_ctx=native_num_ctx,
        max_tokens=native_max_tokens,
    )
    retry_attempted = False
    retry_metadata: Dict[str, Any] = {}
    if not content:
        retry_attempted = True
        retry_messages = render_native_page_answer_messages(
            pack,
            question=question,
            max_binder_chars=max_binder_chars,
            strict_final_content=True,
        )
        content, retry_metadata = call_native_ollama_openai_chat(
            messages=retry_messages,
            base_url=native_llm_base_url,
            model=native_llm_model,
            api_key=native_llm_api_key,
            temperature=0.0,
            timeout=native_request_timeout,
            attempt_label="strict_final_content_retry",
            num_ctx=native_num_ctx,
            max_tokens=native_max_tokens,
        )
    elapsed_ms = round((time.time() - started) * 1000, 3)
    combined_metadata = dict(llm_metadata)
    combined_metadata["native_llm_retry_attempted"] = retry_attempted
    if retry_attempted:
        combined_metadata["native_llm_primary_empty_content"] = bool(llm_metadata.get("empty_content"))
        combined_metadata["native_llm_retry_metadata"] = retry_metadata
    if not content:
        raise NativePageAnswerError(
            "native page answer returned empty content after strict final-answer retry",
            llm_attempted=True,
            llm_metadata=combined_metadata,
        )
    response = {
        "id": f"chatcmpl-tracenet-page-native-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(created if created is not None else time.time()),
        "model": model_id,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": (retry_metadata.get("usage") if retry_attempted else llm_metadata.get("usage")) or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "page_context_bridge": {
                "page_context_used": True,
                "native_page_answer_used": True,
                "native_llm_called": True,
                "native_llm_attempted": True,
                "native_llm_status": "NATIVE_PAGE_LLM_CALL_SUCCEEDED",
                "native_llm_model": native_llm_model,
                "native_llm_base_url": normalize_ollama_openai_base_url(native_llm_base_url),
                "native_llm_provider_endpoint": "ollama_api_chat",
                "native_llm_num_ctx": native_num_ctx,
                "native_llm_max_tokens": native_max_tokens,
                "native_llm_elapsed_ms": elapsed_ms,
                "native_llm_retry_attempted": retry_attempted,
                "fallback_used": False,
                "context_pack_quality_status": meta.get("context_pack_quality_status") or pack.get("quality_status"),
                "context_pack_summary": meta.get("context_pack_summary") or pack.get("summary"),
                "context_pack_output_path": meta.get("context_pack_output_path"),
                "context_pack_page_ids": meta.get("context_pack_page_ids", []),
                "detected_pages": meta.get("detected_pages", []),
                "safety": {
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                    "writes_to_postgres": False,
                    "writes_to_qdrant": False,
                    "writes_to_opensearch": False,
                },
            },
            "native_llm_metadata": combined_metadata,
        },
    }
    aligned, reason = should_use_context_bridge_fallback(response, meta)
    if aligned:
        raise NativePageAnswerError(
            f"native page answer failed alignment check: {reason}",
            llm_attempted=True,
            llm_metadata=combined_metadata,
        )
    response["trace_net"]["page_context_bridge"]["alignment_status"] = reason
    return response


def build_native_failure_fallback_response(
    *,
    pack: Mapping[str, Any],
    meta: Mapping[str, Any],
    model_id: str,
    reason: str,
    error: str = "",
    native_llm_attempted: bool = False,
    native_llm_metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    content = render_page_context_fallback_answer(pack, meta, reason)
    response = {
        "id": f"chatcmpl-tracenet-page-fallback-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "page_context_bridge": {
                "page_context_used": True,
                "native_page_answer_used": False,
                "native_llm_called": bool(native_llm_attempted),
                "native_llm_attempted": bool(native_llm_attempted),
                "native_llm_status": "NATIVE_PAGE_LLM_CALL_FAILED_FALLBACK" if error else "NATIVE_PAGE_FALLBACK",
                "native_llm_error": error,
                "native_llm_metadata": dict(native_llm_metadata or {}),
                "fallback_used": True,
                "fallback_reason": reason,
                "context_pack_quality_status": meta.get("context_pack_quality_status") or pack.get("quality_status"),
                "context_pack_summary": meta.get("context_pack_summary") or pack.get("summary"),
                "context_pack_output_path": meta.get("context_pack_output_path"),
                "context_pack_page_ids": meta.get("context_pack_page_ids", []),
                "detected_pages": meta.get("detected_pages", []),
                "safety": {
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                    "writes_to_postgres": False,
                    "writes_to_qdrant": False,
                    "writes_to_opensearch": False,
                },
            }
        },
    }
    return response


def _page_number_from_page_id(page_id: str) -> Optional[int]:
    match = re.search(r"p0*(\d{1,6})\b", str(page_id or ""), re.IGNORECASE)
    return int(match.group(1)) if match else None


def _load_pack_from_meta(meta: Mapping[str, Any], repo_root: str | Path) -> Dict[str, Any]:
    rel = meta.get("context_pack_output_path")
    if not rel:
        return {}
    path = Path(repo_root) / str(rel)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _openai_response_content(response_json: Mapping[str, Any]) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    message = first.get("message")
    if not isinstance(message, Mapping):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _content_mentions_requested_pages(content: str, meta: Mapping[str, Any]) -> bool:
    if not meta.get("page_context_used"):
        return True
    text = (content or "").lower()
    requested_pages: List[int] = []
    for value in meta.get("detected_pages", []) or []:
        try:
            requested_pages.append(int(value))
        except Exception:
            pass
    for page_id in meta.get("context_pack_page_ids", []) or []:
        page_num = _page_number_from_page_id(str(page_id))
        if page_num is not None:
            requested_pages.append(page_num)
    requested_pages = _dedupe_ints(requested_pages)
    if not requested_pages:
        return True
    for page in requested_pages:
        page_tokens = [
            f"page {page}",
            f"p{page:06d}",
            f"p{page:03d}",
            f"000{page:03d}"[-6:],
        ]
        if not any(token.lower() in text for token in page_tokens):
            return False
    return True


def should_use_context_bridge_fallback(response_json: Mapping[str, Any], meta: Mapping[str, Any]) -> Tuple[bool, str]:
    if not meta.get("page_context_used"):
        return False, "page_context_not_used"
    content = _openai_response_content(response_json)
    trace = response_json.get("trace_net") if isinstance(response_json.get("trace_net"), Mapping) else {}
    if trace.get("llm_status") == "LLM_SIMULATED" or trace.get("llm_called") is False:
        return True, "upstream_llm_simulated_or_not_called"
    if not _content_mentions_requested_pages(content, meta):
        return True, "upstream_response_not_page_aligned"
    return False, "upstream_response_page_aligned"


def _first_text_from_guidance(values: Any, *, max_items: int = 2, max_chars: int = 500) -> List[str]:
    out: List[str] = []
    if not isinstance(values, list):
        return out
    for item in values:
        text = ""
        if isinstance(item, Mapping):
            text = str(item.get("text") or item.get("summary") or item.get("excerpt") or item.get("value") or "")
        elif isinstance(item, str):
            text = item
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append(text[:max_chars])
        if len(out) >= max_items:
            break
    return out


def render_page_context_fallback_answer(pack: Mapping[str, Any], meta: Mapping[str, Any], upstream_reason: str) -> str:
    """Build a safe deterministic answer when the upstream simulated/off-topic path ignores the binder.

    This is not intended to replace Gemma reasoning in ollama mode. It is a guardrail for
    simulate mode and for responses that fail to mention the requested source pages.
    """
    summary = pack.get("summary") if isinstance(pack.get("summary"), Mapping) else meta.get("context_pack_summary", {})
    records = pack.get("page_context_records") if isinstance(pack.get("page_context_records"), list) else []
    lines: List[str] = []
    lines.append("Answer")
    if records:
        bits = []
        for rec in records:
            if not isinstance(rec, Mapping):
                continue
            page = rec.get("page_number")
            route = rec.get("primary_route")
            srcs = rec.get("source_files") if isinstance(rec.get("source_files"), list) else []
            src = ""
            if srcs and isinstance(srcs[0], Mapping):
                src = str(srcs[0].get("value") or "")
            part = f"page {page} ({rec.get('page_id')}) is routed as {route}"
            if src:
                part += f" with source file {src}"
            bits.append(part)
        lines.append("TRACE-Net built a page-context binder for " + "; ".join(bits) + ".")
    else:
        lines.append("TRACE-Net built a page-context binder, but the page records were not available for rendering.")
    lines.append("The model should reason from these page records, but the response must stay within the source-trace limits of the binder.")
    lines.append("")

    lines.append("Evidence")
    lines.append(f"Context pack quality: {pack.get('quality_status') or meta.get('context_pack_quality_status')}")
    if isinstance(summary, Mapping):
        lines.append(
            "Counts: "
            f"selected_page_count={summary.get('selected_page_count', 0)}, "
            f"source_trace_ready_page_count={summary.get('source_trace_ready_page_count', 0)}, "
            f"proof_record_count={summary.get('proof_record_count', 0)}, "
            f"guidance_record_count={summary.get('guidance_record_count', 0)}, "
            f"answer_permission_count={summary.get('answer_permission_count', 0)}, "
            f"source_truth_mutation_allowed_count={summary.get('source_truth_mutation_allowed_count', 0)}."
        )
    for rec in records:
        if not isinstance(rec, Mapping):
            continue
        lines.append(
            f"- Page {rec.get('page_number')} / {rec.get('page_id')}: route={rec.get('primary_route')}; "
            f"source_trace_ready={rec.get('source_trace_ready')}; "
            f"proof_records={rec.get('proof_record_count')}; guidance_records={rec.get('guidance_record_count')}."
        )
        for cue in _first_text_from_guidance(rec.get("vector_guidance"), max_items=2, max_chars=420):
            lines.append(f"  Guidance cue, not proof: {cue}")
    lines.append("")

    lines.append("Engineering confidence")
    lines.append("High for page identity, route, and source-file locator because the context pack is PASS and the requested page IDs are present. Lower for detailed engineering interpretation until OCR excerpts, visual observations, or claim-proof records are attached.")
    lines.append("")

    lines.append("Limits")
    lines.append("This guardrail answer was used because the upstream response was simulated or not aligned with the requested page binder: " + upstream_reason + ".")
    lines.append("Do not infer interchangeability, fit, effectivity, replacement approval, installation safety, or procurement authority from this binder unless explicit source proof is attached.")
    return "\n".join(lines)


def apply_context_bridge_fallback_if_needed(
    body: bytes,
    *,
    meta: Mapping[str, Any],
    repo_root: str | Path,
    status: int,
    content_type: str,
) -> Tuple[int, bytes, str, bool]:
    if status >= 400 or "json" not in (content_type or "").lower() or not meta.get("page_context_used"):
        return status, body, content_type, False
    try:
        response_json = json.loads(body.decode("utf-8"))
    except Exception:
        return status, body, content_type, False
    use_fallback, reason = should_use_context_bridge_fallback(response_json, meta)
    if not use_fallback:
        response_json.setdefault("trace_net", {})
        if isinstance(response_json["trace_net"], MutableMapping):
            response_json["trace_net"]["page_context_bridge"] = {
                "page_context_used": True,
                "fallback_used": False,
                "reason": reason,
                "context_pack_output_path": meta.get("context_pack_output_path"),
                "context_pack_page_ids": meta.get("context_pack_page_ids", []),
            }
        return status, json.dumps(response_json).encode("utf-8"), "application/json", False

    pack = _load_pack_from_meta(meta, repo_root)
    fallback_content = render_page_context_fallback_answer(pack, meta, reason)
    upstream_trace = response_json.get("trace_net") if isinstance(response_json.get("trace_net"), Mapping) else {}
    choices = response_json.setdefault("choices", [])
    if not isinstance(choices, list) or not choices:
        response_json["choices"] = [{"index": 0, "message": {"role": "assistant", "content": fallback_content}, "finish_reason": "stop"}]
    else:
        first = choices[0]
        if not isinstance(first, MutableMapping):
            response_json["choices"][0] = {"index": 0, "message": {"role": "assistant", "content": fallback_content}, "finish_reason": "stop"}
        else:
            msg = first.setdefault("message", {})
            if not isinstance(msg, MutableMapping):
                first["message"] = {"role": "assistant", "content": fallback_content}
            else:
                msg["role"] = "assistant"
                msg["content"] = fallback_content
            first["finish_reason"] = "stop"
    response_json["model"] = response_json.get("model") or DEFAULT_MODEL_ID
    response_json["trace_net"] = {
        "page_context_bridge": {
            "page_context_used": True,
            "fallback_used": True,
            "fallback_reason": reason,
            "context_pack_quality_status": meta.get("context_pack_quality_status"),
            "context_pack_summary": meta.get("context_pack_summary"),
            "context_pack_output_path": meta.get("context_pack_output_path"),
            "context_pack_page_ids": meta.get("context_pack_page_ids", []),
            "detected_pages": meta.get("detected_pages", []),
            "safety": {
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "writes_to_postgres": False,
                "writes_to_qdrant": False,
                "writes_to_opensearch": False,
            },
        },
        "upstream_trace_net": upstream_trace,
    }
    return 200, json.dumps(response_json, ensure_ascii=False).encode("utf-8"), "application/json", True

def make_preflight_manifest(
    *,
    question: str,
    pages: Sequence[int] | None = None,
    repo_root: str | Path = ".",
    output_context_pack: str | None = None,
    output_manifest: str | Path | None = None,
    artifact_paths: PageContextArtifactPaths | None = None,
) -> Dict[str, Any]:
    selected_pages = list(pages) if pages else extract_page_numbers(question)
    dummy_payload = {
        "model": DEFAULT_MODEL_ID,
        "messages": [{"role": "user", "content": question}],
        "temperature": 0.0,
    }
    enriched, meta = enrich_chat_payload(
        dummy_payload,
        repo_root=repo_root,
        artifact_paths=artifact_paths,
        output_path=output_context_pack,
    )
    manifest = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": "PASS" if meta.get("page_context_used") else "REVIEW",
        "question": question,
        "requested_pages": selected_pages,
        "bridge_meta": meta,
        "enriched_message_count": len(enriched.get("messages", [])),
        "enriched_messages_preview": enriched.get("messages", [])[:3],
        "safety_contract": {
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }
    if output_manifest:
        out = Path(repo_root) / output_manifest
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_json_request(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _post_json(url: str, payload: Mapping[str, Any], timeout: float = 180.0) -> Tuple[int, bytes, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - local dev bridge
            return resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "application/json")


def _get_json(url: str, timeout: float = 30.0) -> Tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - local dev bridge
            return resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "application/json")


class PageContextBridgeServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: Tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],
        *,
        repo_root: str | Path,
        upstream_base_url: str,
        model_id: str,
        upstream_model: str,
        max_pages: int,
        max_binder_chars: int,
        native_page_answer_mode: str,
        native_llm_base_url: str,
        native_llm_model: str,
        native_llm_api_key: str,
        native_temperature: float,
        native_request_timeout: float,
        native_num_ctx: int = DEFAULT_NATIVE_NUM_CTX,
        native_max_tokens: int = DEFAULT_NATIVE_MAX_TOKENS,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.repo_root = Path(repo_root).resolve()
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.model_id = model_id
        self.upstream_model = upstream_model
        self.max_pages = max_pages
        self.max_binder_chars = max_binder_chars
        self.native_page_answer_mode = native_page_answer_mode
        self.native_llm_base_url = normalize_ollama_openai_base_url(native_llm_base_url)
        self.native_llm_model = native_llm_model
        self.native_llm_api_key = native_llm_api_key
        self.native_temperature = native_temperature
        self.native_request_timeout = native_request_timeout
        self.native_num_ctx = native_num_ctx
        self.native_max_tokens = native_max_tokens
        self.artifact_paths = PageContextArtifactPaths()


class PageContextBridgeHandler(BaseHTTPRequestHandler):
    server: PageContextBridgeServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/"):
            _json_response(
                self,
                200,
                {
                    "status": "ok",
                    "module": MODULE,
                    "version": VERSION,
                    "model_id": self.server.model_id,
                    "upstream_base_url": self.server.upstream_base_url,
                    "upstream_model": self.server.upstream_model,
                    "native_page_answer_mode": self.server.native_page_answer_mode,
                    "native_llm_model": self.server.native_llm_model,
                    "native_llm_base_url": self.server.native_llm_base_url,
                    "native_llm_provider_endpoint": "ollama_api_chat",
                    "native_llm_num_ctx": self.server.native_num_ctx,
                    "native_llm_max_tokens": self.server.native_max_tokens,
                    "safety_contract": {
                        "read_only": True,
                        "answer_permission": False,
                        "source_truth_mutation_allowed": False,
                    },
                },
            )
            return
        if self.path == "/v1/models":
            # Return proxy model locally. Open WebUI only needs a discoverable model.
            _json_response(
                self,
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.server.model_id,
                            "object": "model",
                            "owned_by": "trace-net-local",
                        }
                    ],
                },
            )
            return
        _json_response(self, 404, {"error": "not found", "path": self.path})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/v1/chat/completions":
            try:
                payload = _read_json_request(self)
                output_path = default_output_path(latest_user_question(payload.get("messages", [])), extract_page_numbers(latest_user_question(payload.get("messages", []))))
                enriched, meta = enrich_chat_payload(
                    payload,
                    repo_root=self.server.repo_root,
                    artifact_paths=self.server.artifact_paths,
                    output_path=output_path,
                    max_pages=self.server.max_pages,
                    max_binder_chars=self.server.max_binder_chars,
                )
                fallback_used = False
                content_type = "application/json"

                if meta.get("page_context_used") and self.server.native_page_answer_mode in ("auto", "ollama"):
                    pack = _load_pack_from_meta(meta, self.server.repo_root)
                    question = str(meta.get("question") or latest_user_question(payload.get("messages", [])) or "")
                    try:
                        response_json = build_native_page_context_response(
                            pack=pack,
                            meta=meta,
                            question=question,
                            model_id=self.server.model_id,
                            native_llm_base_url=self.server.native_llm_base_url,
                            native_llm_model=self.server.native_llm_model,
                            native_llm_api_key=self.server.native_llm_api_key,
                            native_temperature=self.server.native_temperature,
                            native_request_timeout=self.server.native_request_timeout,
                            native_num_ctx=self.server.native_num_ctx,
                            native_max_tokens=self.server.native_max_tokens,
                            max_binder_chars=self.server.max_binder_chars,
                        )
                    except Exception as native_exc:
                        native_attempted = bool(getattr(native_exc, "llm_attempted", False))
                        native_metadata = getattr(native_exc, "llm_metadata", {}) or {}
                        response_json = build_native_failure_fallback_response(
                            pack=pack,
                            meta=meta,
                            model_id=self.server.model_id,
                            reason="native_page_answer_failed_or_not_aligned",
                            error=str(native_exc),
                            native_llm_attempted=native_attempted,
                            native_llm_metadata=native_metadata,
                        )
                        fallback_used = True
                    body = json.dumps(response_json, ensure_ascii=False).encode("utf-8")
                    status = 200
                else:
                    enriched["model"] = self.server.upstream_model
                    status, body, content_type = _post_json(
                        self.server.upstream_base_url + "/chat/completions",
                        enriched,
                        timeout=240.0,
                    )
                    status, body, content_type, fallback_used = apply_context_bridge_fallback_if_needed(
                        body,
                        meta=meta,
                        repo_root=self.server.repo_root,
                        status=status,
                        content_type=content_type,
                    )
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("X-Trace-Net-Page-Context-Used", "true" if meta.get("page_context_used") else "false")
                self.send_header("X-Trace-Net-Page-Context-Native", "true" if (meta.get("page_context_used") and self.server.native_page_answer_mode in ("auto", "ollama")) else "false")
                self.send_header("X-Trace-Net-Page-Context-Fallback", "true" if fallback_used else "false")
                if meta.get("context_pack_output_path"):
                    self.send_header("X-Trace-Net-Context-Pack", str(meta.get("context_pack_output_path")))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # pragma: no cover - server error path
                _json_response(
                    self,
                    502,
                    {
                        "error": "page_context_bridge_failed",
                        "message": str(exc),
                        "module": MODULE,
                    },
                )
            return

        if self.path == "/api/trace-net/page-context-preview":
            try:
                payload = _read_json_request(self)
                question = str(payload.get("question") or latest_user_question(payload.get("messages", [])) or "")
                pages = payload.get("pages") or extract_page_numbers(question)
                pack = build_page_context_pack_via_cli(
                    question=question,
                    pages=[int(p) for p in pages],
                    repo_root=self.server.repo_root,
                    artifact_paths=self.server.artifact_paths,
                    output_path=payload.get("output_path") or default_output_path(question, [int(p) for p in pages]),
                    max_pages=self.server.max_pages,
                )
                _json_response(
                    self,
                    200,
                    {
                        "module": MODULE,
                        "quality_status": pack.get("quality_status"),
                        "summary": pack.get("summary"),
                        "page_context_records": pack.get("page_context_records", []),
                        "context_pack_output_path": pack.get("bridge_build", {}).get("output_path"),
                    },
                )
            except Exception as exc:  # pragma: no cover
                _json_response(self, 500, {"error": "preview_failed", "message": str(exc)})
            return

        _json_response(self, 404, {"error": "not found", "path": self.path})


def serve(
    *,
    host: str,
    port: int,
    repo_root: str | Path,
    upstream_base_url: str,
    model_id: str = DEFAULT_MODEL_ID,
    upstream_model: str = DEFAULT_UPSTREAM_MODEL,
    max_pages: int = 8,
    max_binder_chars: int = 14000,
    native_page_answer_mode: str = "auto",
    native_llm_base_url: str = DEFAULT_NATIVE_LLM_BASE_URL,
    native_llm_model: str = DEFAULT_NATIVE_LLM_MODEL,
    native_llm_api_key: str = "ollama",
    native_temperature: float = 0.1,
    native_request_timeout: float = 300.0,
    native_num_ctx: int = DEFAULT_NATIVE_NUM_CTX,
    native_max_tokens: int = DEFAULT_NATIVE_MAX_TOKENS,
) -> None:
    server = PageContextBridgeServer(
        (host, port),
        PageContextBridgeHandler,
        repo_root=repo_root,
        upstream_base_url=upstream_base_url,
        model_id=model_id,
        upstream_model=upstream_model,
        max_pages=max_pages,
        max_binder_chars=max_binder_chars,
        native_page_answer_mode=native_page_answer_mode,
        native_llm_base_url=native_llm_base_url,
        native_llm_model=native_llm_model,
        native_llm_api_key=native_llm_api_key,
        native_temperature=native_temperature,
        native_request_timeout=native_request_timeout,
        native_num_ctx=native_num_ctx,
        native_max_tokens=native_max_tokens,
    )
    print(json.dumps({
        "status": "serving",
        "module": MODULE,
        "version": VERSION,
        "host": host,
        "port": port,
        "base_url": f"http://{host}:{port}/v1",
        "model_id": model_id,
        "upstream_base_url": upstream_base_url,
        "upstream_model": upstream_model,
        "native_page_answer_mode": native_page_answer_mode,
        "native_llm_base_url": normalize_ollama_openai_base_url(native_llm_base_url),
        "native_llm_model": native_llm_model,
        "native_num_ctx": native_num_ctx,
        "native_max_tokens": native_max_tokens,
    }, indent=2))
    server.serve_forever()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=MODULE)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pre = sub.add_parser("preflight", help="Build a page-context bridge preflight manifest")
    p_pre.add_argument("--question", required=True)
    p_pre.add_argument("--pages", nargs="*", type=int, default=None)
    p_pre.add_argument("--repo-root", default=".")
    p_pre.add_argument("--output-context-pack", default=None)
    p_pre.add_argument("--output", required=True)

    p_serve = sub.add_parser("serve", help="Serve an OpenAI-compatible page-context proxy")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8023)
    p_serve.add_argument("--repo-root", default=".")
    p_serve.add_argument("--upstream-base-url", default="http://127.0.0.1:8022/v1")
    p_serve.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    p_serve.add_argument("--upstream-model", default=DEFAULT_UPSTREAM_MODEL)
    p_serve.add_argument("--max-pages", type=int, default=8)
    p_serve.add_argument("--max-binder-chars", type=int, default=14000)
    p_serve.add_argument("--native-page-answer-mode", default="auto", choices=["auto", "ollama", "off"])
    p_serve.add_argument("--native-llm-base-url", default=DEFAULT_NATIVE_LLM_BASE_URL)
    p_serve.add_argument("--native-llm-model", default=DEFAULT_NATIVE_LLM_MODEL)
    p_serve.add_argument("--native-llm-api-key", default="ollama")
    p_serve.add_argument("--native-temperature", type=float, default=0.1)
    p_serve.add_argument("--native-request-timeout", type=float, default=300.0)
    p_serve.add_argument("--native-num-ctx", type=int, default=DEFAULT_NATIVE_NUM_CTX)
    p_serve.add_argument("--native-max-tokens", type=int, default=DEFAULT_NATIVE_MAX_TOKENS)

    args = parser.parse_args(argv)
    if args.cmd == "preflight":
        manifest = make_preflight_manifest(
            question=args.question,
            pages=args.pages,
            repo_root=args.repo_root,
            output_context_pack=args.output_context_pack,
            output_manifest=args.output,
        )
        print(f"Wrote: {args.output}")
        print("quality_status:", manifest.get("quality_status"))
        print("bridge_meta:", json.dumps(manifest.get("bridge_meta", {}), indent=2)[:2000])
        return 0 if manifest.get("quality_status") == "PASS" else 2
    if args.cmd == "serve":
        serve(
            host=args.host,
            port=args.port,
            repo_root=args.repo_root,
            upstream_base_url=args.upstream_base_url,
            model_id=args.model_id,
            upstream_model=args.upstream_model,
            max_pages=args.max_pages,
            max_binder_chars=args.max_binder_chars,
            native_page_answer_mode=args.native_page_answer_mode,
            native_llm_base_url=args.native_llm_base_url,
            native_llm_model=args.native_llm_model,
            native_llm_api_key=args.native_llm_api_key,
            native_temperature=args.native_temperature,
            native_request_timeout=args.native_request_timeout,
            native_num_ctx=args.native_num_ctx,
            native_max_tokens=args.native_max_tokens,
        )
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
