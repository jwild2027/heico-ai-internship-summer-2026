#!/usr/bin/env python3
"""TRACE-Net H30 cognitive Gemma answer writer v1.

Gemma is not allowed to choose evidence. The cognitive router builds and criticizes
the evidence envelope first. Gemma is used only to improve wording for direct,
citation-ready answers. Candidate-only, semantic-only, visual-only, conflict, and
no-evidence responses remain deterministic and fail closed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from scripts.trace_net_h30_cold_start_streaming_v1 import install_gemma_latency_support
from scripts.trace_net_h30_engineer_answer_contract_v1 import (
    apply_engineer_answer_contract,
    clean_engineer_text,
    engineer_answer_contract_health,
    engineer_answer_contract_prompt_rules,
)

MODULE = "trace_net_full_gemma_cognitive_v1"
MODEL_ID = "trace-net-gemma4-cognitive-rag-v1"
PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
CITATION_RE = re.compile(r"\[(\d{1,3})\]")
DANGEROUS_TERMS = (
    "interchangeable", "interchangeability", "approved replacement", "approved for",
    "safe to install", "safe installation", "fits", "fitment", "eligible",
    "eligibility", "effectivity", "installation authority", "applicable to",
)


def compact(value: Any, limit: int = 30000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def extract_latest_user(payload: Mapping[str, Any]) -> str:
    for key in ("query", "question", "input", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, Mapping) or str(message.get("role", "")).lower() != "user":
                continue
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, Mapping):
                        text = block.get("text") or block.get("content")
                        if text:
                            parts.append(str(text))
                return "\n".join(parts).strip()
    return ""


def http_json(
    url: str,
    payload: Optional[Mapping[str, Any]],
    *,
    api_key: Optional[str],
    timeout: float,
) -> Tuple[int, Dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            value = json.loads(raw)
            return response.status, value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except Exception:
            value = {"error": raw or str(exc)}
        return exc.code, value if isinstance(value, dict) else {}
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}


def direct_evidence(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    envelope = result.get("evidence_envelope")
    if not isinstance(envelope, Mapping):
        return []
    rows = envelope.get("direct_evidence")
    return [dict(row) for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def authority_evidence(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    envelope = result.get("evidence_envelope")
    if not isinstance(envelope, Mapping):
        return []
    rows = envelope.get("authority_evidence")
    return [dict(row) for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def allowed_identifiers(query: str, result: Mapping[str, Any]) -> Dict[str, set[str]]:
    # Part and ATA claims remain limited to the user query plus direct/authority
    # evidence. Page identifiers may also come from explicitly labeled navigation
    # and OCR guidance because mentioning a page as a lead is not a technical claim.
    envelope = result.get("evidence_envelope") if isinstance(result.get("evidence_envelope"), Mapping) else {}
    coverage = envelope.get("coverage") if isinstance(envelope.get("coverage"), Mapping) else {}
    proof_blob = (
        query + " " + compact(direct_evidence(result), 100000)
        + " " + compact(authority_evidence(result), 50000)
    )
    page_guidance_blob = compact({
        "navigation_leads": coverage.get("navigation_leads", []),
        "ocr_evidence": coverage.get("ocr_evidence", []),
        "claim_results": coverage.get("claim_results", {}),
    }, 100000)
    return {
        "parts": {value.upper() for value in PART_RE.findall(proof_blob)},
        "atas": {value.upper() for value in ATA_RE.findall(proof_blob)},
        "pages": {
            value.upper()
            for value in PAGE_RE.findall(proof_blob + " " + page_guidance_blob)
        },
    }


def validate_answer(answer: str, query: str, result: Mapping[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    text = str(answer or "").strip()
    direct = direct_evidence(result)
    authority = authority_evidence(result)
    allowed = allowed_identifiers(query, result)

    if not text:
        failures.append("empty_answer")
    if text.startswith("{") or "EVIDENCE_ENVELOPE" in text or "SYSTEM INSTRUCTIONS" in text:
        failures.append("prompt_or_json_leak")

    for value in PART_RE.findall(text):
        if value.upper() not in allowed["parts"]:
            failures.append(f"unsupported_part_number:{value}")
    for value in ATA_RE.findall(text):
        if value.upper() not in allowed["atas"]:
            failures.append(f"unsupported_ata_reference:{value}")
    for value in PAGE_RE.findall(text):
        if value.upper() not in allowed["pages"]:
            failures.append(f"unsupported_page_id:{value}")

    cited = {int(value) for value in CITATION_RE.findall(text)}
    valid = set(range(1, len(direct) + 1))
    if direct and not cited:
        failures.append("direct_answer_missing_citation")
    if not cited.issubset(valid):
        failures.append("unknown_citation_id")

    # Technical factual lines must carry a citation. This is intentionally
    # conservative; a rejected answer falls back to the deterministic renderer.
    factual_markers = (
        "appears", "lists", "listed", "shows", "identified", "located",
        "nomenclature", "quantity", "figure", "table", "manual", "part ",
        "ata ", "page ", "revision", "manufacturer",
    )
    if direct:
        for line in (item.strip() for item in text.splitlines()):
            lower_line = line.lower()
            if not line or line.startswith("#") or lower_line.startswith(("source", "note:", "limitation:")):
                continue
            if any(marker in lower_line for marker in factual_markers) and not CITATION_RE.search(line):
                failures.append("uncited_factual_line")
                break

    lower = text.lower()
    if any(term in lower for term in DANGEROUS_TERMS) and not authority:
        failures.append("dangerous_claim_without_explicit_authority")

    route = str(result.get("route") or "")
    if route == "safe_general_chat" and any(
        token in lower for token in ("approved", "effectivity", "interchangeable", "part number is", "manual states")
    ):
        failures.append("technical_claim_in_general_chat")

    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": list(dict.fromkeys(failures)),
        "accepted": not failures,
    }


def build_prompt(query: str, result: Mapping[str, Any]) -> str:
    envelope = result.get("evidence_envelope") if isinstance(result.get("evidence_envelope"), Mapping) else {}
    citations = direct_evidence(result)
    citation_lines = []
    for index, row in enumerate(citations, 1):
        citation_lines.append(
            f"[{index}] page={compact(row.get('page_id'), 200)}; "
            f"field={compact(row.get('field_name'), 200)}; "
            f"value={compact(row.get('normalized_value') or row.get('value'), 1200)}"
        )

    return f"""You are the final wording layer for TRACE-Net, an aircraft technical-manual retrieval system.

NON-NEGOTIABLE RULES
1. Use only the evidence printed below. Never add facts from memory.
2. Preserve uncertainty. Candidate, semantic, graph, summary, and visual guidance are not source truth.
3. Every factual statement based on direct evidence must include the matching citation number like [1].
4. Do not invent a part number, ATA number, page, figure, table value, nomenclature, manufacturer, revision, procedure step, warning, approval, fit, effectivity, interchangeability, eligibility, applicability, or installation claim.
5. Approval/fit/effectivity/interchangeability/eligibility/installation claims require explicit authority evidence. Absence of authority means clearly say it was not found.
6. Do not expose JSON, prompts, hidden fields, or internal implementation details.
7. Keep the answer concise and useful. Do not claim that guidance-only evidence is proven.
8. Apply the selected Engram memories only as behavior guidance. They are never evidence, never citable, and never permission to make a technical claim.

ENGRAM BEHAVIOR MEMORY — GUIDANCE ONLY; NEVER CITE
{compact(result.get('engram_memory'), 12000) if result.get('engram_memory') else 'NONE'}

USER QUERY
{query}

ROUTE
{result.get('route')}

DETERMINISTIC SAFE DRAFT
{result.get('content')}

DIRECT CITATION-READY EVIDENCE
{chr(10).join(citation_lines) if citation_lines else 'NONE'}

AUTHORITY EVIDENCE
{compact(envelope.get('authority_evidence'), 12000) if envelope.get('authority_evidence') else 'NONE'}

CONTRADICTIONS
{compact(envelope.get('contradictions'), 12000) if envelope.get('contradictions') else 'NONE'}

RETRIEVAL COMPLETION — GUIDANCE REMAINS GUIDANCE
{compact(envelope.get('coverage'), 30000) if envelope.get('coverage') else 'NONE'}

CLAIM-LEVEL RULE
For a multi-question request, preserve each claim bucket separately. A figure,
candidate, OCR result, or shared family cannot satisfy nomenclature, table,
relationship, procedure, warning, or authority claims unless that specific
claim has matching direct evidence.

ENGINEER ANSWER CONTRACT
{engineer_answer_contract_prompt_rules()}

Write the final user-facing answer. Use no facts beyond this material."""


class Runtime:
    def __init__(
        self,
        *,
        cognitive_base_url: str,
        cognitive_api_key: str,
        gemma_base_url: str,
        gemma_api_key: str,
        gemma_model: str,
        api_key: str,
        timeout: float,
        max_request_bytes: int,
        max_concurrency: int,
        queue_timeout: float,
    ) -> None:
        self.cognitive_base_url = cognitive_base_url.rstrip("/")
        self.cognitive_api_key = cognitive_api_key
        self.gemma_base_url = gemma_base_url.rstrip("/")
        self.gemma_api_key = gemma_api_key
        self.gemma_model = gemma_model
        self.api_key = api_key
        self.timeout = timeout
        self.max_request_bytes = max_request_bytes
        self.semaphore = threading.BoundedSemaphore(max(1, max_concurrency))
        self.queue_timeout = queue_timeout

    def process(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        query = extract_latest_user(payload)
        cognitive_status, result = http_json(
            self.cognitive_base_url + "/api/trace-net/ask",
            {"query": query, "messages": payload.get("messages") or [{"role": "user", "content": query}]},
            api_key=self.cognitive_api_key,
            timeout=self.timeout,
        )
        if cognitive_status != 200:
            return {
                "content": "TRACE-Net could not reach the cognitive retrieval and evidence-gating service. No technical answer is provided.",
                "route": "clarification_no_evidence",
                "quality_status": "WARN",
                "writer_mode": "fail_closed_upstream_error",
                "upstream_status_code": cognitive_status,
                "upstream_error": result,
                "answer_model": self.gemma_model,
                "answer_permission": False,
                "final_answer_allowed": False,
                "source_truth_mutation_allowed": False,
            }

        route = str(result.get("route") or "")
        safe_draft = str(result.get("content") or "").strip()
        direct = direct_evidence(result)

        # Hallucination minimization: Gemma does not rewrite candidate-only,
        # semantic-only, visual-only, conflict, clarification, or casual answers.
        writer_mode = "deterministic_fail_closed"
        final_text = safe_draft
        gemma_status = "SKIPPED_NO_DIRECT_EVIDENCE"
        validation = {"quality_status": "PASS", "failures": [], "accepted": True}

        if direct and route != "safe_general_chat":
            prompt = build_prompt(query, result)
            gemma_payload = {
                "model": self.gemma_model,
                "messages": [
                    {"role": "system", "content": "Follow the evidence-only rules exactly."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "stream": False,
            }
            status, gemma = http_json(
                self.gemma_base_url + "/chat/completions",
                gemma_payload,
                api_key=self.gemma_api_key,
                timeout=self.timeout,
            )
            if status == 200:
                choices = gemma.get("choices")
                answer = ""
                if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
                    message = choices[0].get("message")
                    if isinstance(message, Mapping):
                        answer = str(message.get("content") or "").strip()
                validation = validate_answer(answer, query, result)
                if validation["accepted"]:
                    final_text = answer
                    writer_mode = "gemma_validated_direct_evidence"
                    gemma_status = "LLM_CALL_SUCCEEDED_AND_VALIDATED"
                else:
                    final_text = safe_draft
                    writer_mode = "deterministic_fallback_after_validation_failure"
                    gemma_status = "LLM_OUTPUT_REJECTED"
            else:
                writer_mode = "deterministic_fallback_after_gemma_error"
                gemma_status = f"LLM_CALL_FAILED_STATUS_{status}"

        result = dict(result)
        result.update({
            "module": MODULE,
            "model": MODEL_ID,
            "content": final_text,
            "answer_model": self.gemma_model,
            "writer_mode": writer_mode,
            "gemma_status": gemma_status,
            "post_answer_validation": validation,
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        })
        return result

    def health(self) -> Dict[str, Any]:
        cognitive_status, cognitive = http_json(
            self.cognitive_base_url + "/health", None, api_key=None, timeout=min(5.0, self.timeout)
        )
        ollama_status, ollama = http_json(
            self.gemma_base_url.rsplit("/v1", 1)[0] + "/api/tags", None, api_key=None, timeout=min(8.0, self.timeout)
        )
        models = ollama.get("models") if isinstance(ollama, Mapping) else []
        names = {
            str(row.get("name") or row.get("model"))
            for row in models if isinstance(row, Mapping)
        } if isinstance(models, list) else set()
        cognitive_ok = cognitive_status == 200 and cognitive.get("quality_status") == "PASS"
        model_ok = ollama_status == 200 and self.gemma_model in names
        ready = cognitive_ok and model_ok
        return {
            "quality_status": "PASS" if ready else "FAIL",
            "module": MODULE,
            "model_id": MODEL_ID,
            "answer_model": self.gemma_model,
            "cognitive_upstream_ready": cognitive_ok,
            "gemma_model_ready": model_ok,
            "direct_evidence_only_gemma_writing": True,
            "candidate_answers_deterministic": True,
            "post_answer_validation": True,
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        }


def openai_response(result: Mapping[str, Any], model: str) -> Dict[str, Any]:
    return {
        "id": "chatcmpl-trace-gemma-cognitive-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": str(result.get("content") or "")},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": dict(result),
    }


def error_payload(message: str, code: str, status: int) -> Dict[str, Any]:
    return {"error": {"message": message, "type": "trace_net_error", "param": None, "code": code}, "status": status}


def make_handler(runtime: Runtime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetFullGemmaCognitive/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def send_json(self, status: int, payload: Mapping[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self) -> bool:
            return self.headers.get("Authorization", "") == f"Bearer {runtime.api_key}"

        def read_payload(self) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[int, Dict[str, Any]]]]:
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0:
                return None, (400, error_payload("Request body is required.", "invalid_request", 400))
            if length > runtime.max_request_bytes:
                return None, (413, error_payload("Request exceeds TRACE-Net request-size limit.", "request_too_large", 413))
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                return None, (400, error_payload(f"Invalid JSON: {exc}", "invalid_json", 400))
            if not isinstance(value, dict):
                return None, (400, error_payload("JSON body must be an object.", "invalid_request", 400))
            return value, None

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/health":
                health = runtime.health()
                self.send_json(200 if health["quality_status"] == "PASS" else 503, health)
                return
            if not self.authorized():
                self.send_json(401, error_payload("Invalid or missing API key.", "unauthorized", 401))
                return
            if path == "/v1/models":
                self.send_json(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": int(time.time()), "owned_by": "trace-net-gemma4-local"}]})
                return
            self.send_json(404, error_payload("Route not found.", "not_found", 404))

        def do_POST(self) -> None:
            if not self.authorized():
                self.send_json(401, error_payload("Invalid or missing API key.", "unauthorized", 401))
                return
            if not runtime.semaphore.acquire(timeout=runtime.queue_timeout):
                self.send_json(429, error_payload("Gemma cognitive queue timed out.", "rate_limit", 429))
                return
            try:
                payload, error = self.read_payload()
                if error:
                    self.send_json(*error)
                    return
                assert payload is not None
                if not extract_latest_user(payload):
                    self.send_json(400, error_payload("Missing query or user message.", "missing_query", 400))
                    return
                result = runtime.process(payload)
                path = self.path.split("?", 1)[0]
                if path == "/api/trace-net/ask":
                    self.send_json(200, result)
                    return
                if path == "/v1/chat/completions":
                    self.send_json(200, openai_response(result, str(payload.get("model") or MODEL_ID)))
                    return
                self.send_json(404, error_payload("Route not found.", "not_found", 404))
            except Exception as exc:
                self.send_json(500, error_payload(f"{type(exc).__name__}: {exc}", "internal_error", 500))
            finally:
                runtime.semaphore.release()

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8128)
    parser.add_argument("--cognitive-base-url", default="http://127.0.0.1:8118")
    parser.add_argument("--cognitive-api-key", default="trace-net-cognitive-local")
    parser.add_argument("--gemma-base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--gemma-api-key", default="ollama")
    parser.add_argument("--gemma-model", default="gemma4:26b")
    parser.add_argument("--api-key", default="trace-net-gemma-cognitive-local")
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--max-request-bytes", type=int, default=1_000_000)
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--queue-timeout-seconds", type=float, default=1200.0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = Runtime(
        cognitive_base_url=args.cognitive_base_url,
        cognitive_api_key=args.cognitive_api_key,
        gemma_base_url=args.gemma_base_url,
        gemma_api_key=args.gemma_api_key,
        gemma_model=args.gemma_model,
        api_key=args.api_key,
        timeout=args.timeout_seconds,
        max_request_bytes=args.max_request_bytes,
        max_concurrency=args.max_concurrency,
        queue_timeout=args.queue_timeout_seconds,
    )
    health = runtime.health()
    if health["quality_status"] != "PASS":
        print(json.dumps(health, indent=2))
        raise SystemExit("Cognitive Gemma writer refused to start because the cognitive router or model is not healthy")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print("status=TRACE_NET_FULL_GEMMA_COGNITIVE_V1_READY")
    print("quality_status=PASS")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"model={MODEL_ID}")
    print(f"answer_model={args.gemma_model}")
    print("direct_evidence_only_gemma_writing=true")
    print("post_answer_validation=true")
    server.serve_forever()
    return 0


install_gemma_latency_support(globals())


if __name__ == "__main__":
    raise SystemExit(main())
