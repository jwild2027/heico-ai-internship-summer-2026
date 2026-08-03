#!/usr/bin/env python3
"""TRACE-Net Gemma visual live endpoint v1.

Live local HTTP endpoint for the clean Gemma visual retrieval docs.

This is the live visual endpoint swap:
old visual source:
  gated_visual_retrieval_adapter_v1_1

new visual source:
  confirmed_image_gemma_visual_retrieval_cleaner_v1_full/
    trace_net_confirmed_image_gemma_visual_clean_retrieval_documents_v1.jsonl

Safety contract:
- read-only
- no OCR/LLM/Ollama calls
- no Postgres/Qdrant/OpenSearch writes
- no source-truth mutation
- no answer permission
- Gemma visual context is retrieval guidance only
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MODULE_NAME = "trace_net_gemma_visual_live_endpoint_v1"
DEFAULT_MODEL = "trace-net-gemma-visual-live-v1"
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-./]*")

STOP_TOKENS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "with", "without", "find", "show", "give", "what", "which", "page",
    "tell", "me", "does", "do", "there", "where", "look", "looking",
}

VISUAL_TRIGGER_TERMS = {
    "diagram", "figure", "fig", "image", "visual", "drawing", "illustration",
    "callout", "callouts", "view", "exploded", "schematic",
}
VISUAL_TRIGGER_PHRASES = {
    "technical drawing",
    "exploded view",
    "figure reference",
    "figure references",
    "figure refs",
    "assembly diagram",
    "seat assembly diagram",
    "passenger seat assembly diagram",
    "diagram page",
    "visual page",
    "parts diagram",
    "part diagram",
}

PROMPT_LEAK_PATTERNS = [
    "trace-net's visual observation specialist",
    "trace-net visual observation specialist",
    "scanned aircraft technical-manual pages",
    "existing non-authoritative hints",
    "required json fields",
    "strict rules",
]
UNSAFE_KEYWORD_PATTERNS = [
    "tecnam aircraft",
    "type certificate data sheet",
    "safety note",
    "sensitive information",
]


def compact(value: Any, limit: int = 1200) -> str:
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


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            yield obj


def listify(value: Any) -> List[str]:
    if not value:
        return []
    vals = value if isinstance(value, list) else [value]
    out: List[str] = []
    seen = set()
    for v in vals:
        s = compact(v, 600)
        key = s.lower()
        if s and key not in seen:
            seen.add(key)
            out.append(s)
    return out


def tokenize(text: Any) -> List[str]:
    if text is None:
        return []
    if not isinstance(text, str):
        text = compact(text, 30000)
    out: List[str] = []
    for token in TOKEN_RE.findall(text):
        t = token.lower()
        if len(t) <= 1 or t in STOP_TOKENS:
            continue
        out.append(t)
    return out


def has_bad_pattern(value: Any, patterns: Sequence[str]) -> bool:
    low = compact(value, 30000).lower()
    return any(pattern in low for pattern in patterns)


def validate_clean_doc(doc: Dict[str, Any]) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    card = doc.get("structured_visual_card") if isinstance(doc.get("structured_visual_card"), dict) else {}
    blob = json.dumps(doc, ensure_ascii=False, sort_keys=True)
    if has_bad_pattern(blob, PROMPT_LEAK_PATTERNS):
        failures.append("prompt_leak_detected")
    if has_bad_pattern(card.get("retrieval_keywords"), UNSAFE_KEYWORD_PATTERNS):
        failures.append("unsafe_keyword_detected")
    safety = doc.get("safety_contract") if isinstance(doc.get("safety_contract"), dict) else {}
    for key in ("answer_permission", "final_answer_allowed", "source_truth_mutation_allowed"):
        if safety.get(key):
            failures.append(f"safety_true:{key}")
    if not compact(doc.get("page_id"), 200):
        failures.append("missing_page_id")
    if not compact(doc.get("retrieval_text"), 1000):
        failures.append("missing_retrieval_text")
    return not failures, failures


def doc_text(doc: Dict[str, Any]) -> str:
    card = doc.get("structured_visual_card") if isinstance(doc.get("structured_visual_card"), dict) else {}
    parts = [
        compact(doc.get("page_id"), 100),
        compact(doc.get("document_id"), 200),
        compact(doc.get("route_name"), 100),
        compact(doc.get("retrieval_text"), 14000),
        compact(card.get("normalized_visual_page_type"), 300),
        compact(card.get("normalized_subject"), 700),
        " ".join(listify(card.get("figure_refs"))),
        " ".join(listify(card.get("part_numbers"))),
        " ".join(listify(card.get("visible_callouts"))),
        " ".join(listify(card.get("retrieval_keywords"))),
    ]
    return "\n".join(p for p in parts if p)


def part_like_tokens(tokens: Sequence[str]) -> List[str]:
    return [t for t in tokens if re.search(r"\d{2,}[-./]\d{2,}", t) or re.fullmatch(r"\d{3,4}[a-z]?", t)]


def is_visual_query(query: str) -> Tuple[bool, List[str]]:
    q_lower = query.lower()
    tokens = set(tokenize(query))
    term_hits = sorted(tokens & VISUAL_TRIGGER_TERMS)
    phrase_hits = [p for p in sorted(VISUAL_TRIGGER_PHRASES) if p in q_lower]
    triggers = term_hits + [p for p in phrase_hits if p not in term_hits]
    return bool(triggers), triggers


def score_doc(query: str, doc: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    q_tokens = tokenize(query)
    q_set = set(q_tokens)
    d_text = doc_text(doc)
    d_tokens = tokenize(d_text)
    d_set = set(d_tokens)

    overlap = sorted(q_set & d_set)
    q_parts = part_like_tokens(q_tokens)
    exact_part_hits = [p for p in q_parts if p.lower() in d_text.lower()]

    phrase_hits: List[str] = []
    q_lower = query.lower()
    d_lower = d_text.lower()
    for phrase in (
        "passenger seat",
        "seat assembly",
        "assembly diagram",
        "figure reference",
        "figure references",
        "technical drawing",
        "exploded view",
        "figure",
        "diagram",
        "callout",
        "callouts",
        "part number",
    ):
        if phrase in q_lower and phrase in d_lower:
            phrase_hits.append(phrase)

    if not (overlap or exact_part_hits or phrase_hits):
        return 0.0, {
            "score": 0.0,
            "token_overlap_count": 0,
            "token_overlap": [],
            "exact_part_hits": [],
            "phrase_hits": [],
            "rejected_reason": "no_real_query_document_match",
        }

    norm = math.log(max(len(d_set), 20), 10)
    score = (len(overlap) / norm) + (10.0 * len(exact_part_hits)) + (3.0 * len(phrase_hits)) + 2.0
    return score, {
        "score": round(score, 4),
        "token_overlap_count": len(overlap),
        "token_overlap": overlap[:30],
        "exact_part_hits": exact_part_hits,
        "phrase_hits": phrase_hits,
    }


def make_citation(doc: Dict[str, Any], rank: int, diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    card = doc.get("structured_visual_card") if isinstance(doc.get("structured_visual_card"), dict) else {}
    return {
        "rank": rank,
        "citation_type": "gemma_confirmed_image_visual_context",
        "page_id": doc.get("page_id", ""),
        "document_id": doc.get("document_id", ""),
        "route": "gemma_confirmed_image_visual",
        "source_route_name": doc.get("route_name", ""),
        "subject": compact(card.get("normalized_subject"), 800),
        "visual_page_type": compact(card.get("normalized_visual_page_type"), 300),
        "figure_refs": listify(card.get("figure_refs"))[:20],
        "part_numbers": listify(card.get("part_numbers"))[:20],
        "visible_callouts": listify(card.get("visible_callouts"))[:30],
        "evidence_use": compact(card.get("evidence_use"), 1000),
        "uncertainty_notes": compact(card.get("uncertainty_notes"), 1000),
        "confidence": compact(card.get("confidence"), 50),
        "score_diagnostics": diagnostics,
        "safety_note": "Gemma visual context is retrieval guidance only. It is not final proof for exact text, fit, interchangeability, effectivity, approval, eligibility, or installation.",
    }


class GemmaVisualEndpoint:
    def __init__(self, docs: Sequence[Dict[str, Any]], *, top_k: int = 8, min_score: float = 0.001):
        self.rejected_docs: List[Dict[str, Any]] = []
        clean_docs: List[Dict[str, Any]] = []
        for doc in docs:
            ok, failures = validate_clean_doc(doc)
            if ok:
                clean_docs.append(doc)
            else:
                self.rejected_docs.append({"page_id": doc.get("page_id"), "document_id": doc.get("document_id"), "failures": failures})
        self.docs = clean_docs
        self.top_k = top_k
        self.min_score = min_score

    def context_for_query(self, query: str, *, top_k: Optional[int] = None, min_score: Optional[float] = None) -> Dict[str, Any]:
        top_k = self.top_k if top_k is None else top_k
        min_score = self.min_score if min_score is None else min_score
        visual_query, triggers = is_visual_query(query)

        scored: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []
        if visual_query:
            for doc in self.docs:
                score, diagnostics = score_doc(query, doc)
                if score >= min_score:
                    scored.append((score, doc, diagnostics))

        scored.sort(key=lambda item: (-item[0], str(item[1].get("page_id", ""))))
        citations = [
            make_citation(doc, i, diag)
            for i, (_, doc, diag) in enumerate(scored[:top_k], start=1)
        ]
        status = "gemma_visual_context_candidates_found" if citations else (
            "visual_route_not_triggered" if not visual_query else "no_gemma_visual_context_candidates_found"
        )

        return {
            "module": MODULE_NAME,
            "query": query,
            "route_name": "gemma_confirmed_image_visual",
            "route_triggered": visual_query,
            "route_triggers": triggers,
            "context_pack_status": status,
            "endpoint_payload_type": "trace_net_route_context",
            "source_retrieval_document_count": len(self.docs) + len(self.rejected_docs),
            "clean_retrieval_document_count": len(self.docs),
            "rejected_document_count": len(self.rejected_docs),
            "top_k": top_k,
            "candidate_count": len(scored),
            "citation_count": len(citations),
            "page_count": len({c.get("page_id") for c in citations if c.get("page_id")}),
            "citations": citations,
            "context_instructions": [
                "Use these Gemma visual cards only as retrieval guidance.",
                "Do not answer fit/interchangeability/effectivity/approval/eligibility/installation claims from visual context alone.",
                "Require corroborating OCR/table/source-trace evidence before final claims.",
                "Prefer OCR/table/source-authority fields for exact text and exact part facts.",
            ],
            "answer_contract": {
                "final_answer_allowed": False,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "visual_context_is_retrieval_guidance_only": True,
                "requires_non_visual_source_trace_for_final_claims": True,
            },
            "safety_contract": {
                "source_truth_mutation_allowed": False,
                "postgres_write_attempt": False,
                "qdrant_write_attempt": False,
                "opensearch_write_attempt": False,
                "ollama_call_attempt": False,
                "llm_call_attempt": False,
            },
        }


def extract_question(payload: Dict[str, Any]) -> str:
    for key in ("query", "question", "input", "prompt"):
        if payload.get(key):
            return compact(payload[key], 2000)
    messages = payload.get("messages")
    if isinstance(messages, list):
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                return compact(msg.get("content"), 2000)
    return ""


def openai_response(model: str, question: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    content = json.dumps(
        {
            "trace_net_route": "gemma_confirmed_image_visual",
            "question": question,
            "route_triggered": payload["route_triggered"],
            "context_pack_status": payload["context_pack_status"],
            "citation_count": payload["citation_count"],
            "citations": payload["citations"],
            "answer_permission": False,
            "final_answer_allowed": False,
            "safety_note": "Visual context is retrieval guidance only; final claims require OCR/table/source trace.",
        },
        ensure_ascii=False,
        indent=2,
    )
    return {
        "id": "trace-net-gemma-visual-live-v1",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def make_handler(endpoint: GemmaVisualEndpoint, model: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetGemmaVisualLive/1.0"

        def _json(self, status: int, obj: Dict[str, Any]) -> None:
            body = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _payload(self) -> Dict[str, Any]:
            size = int(self.headers.get("Content-Length", "0") or "0")
            if size <= 0:
                return {}
            raw = self.rfile.read(size)
            try:
                obj = json.loads(raw.decode("utf-8", errors="replace"))
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}

        def do_GET(self) -> None:
            if self.path == "/health":
                self._json(200, {
                    "status": "ok",
                    "module": MODULE_NAME,
                    "route_name": "gemma_confirmed_image_visual",
                    "clean_retrieval_document_count": len(endpoint.docs),
                    "rejected_document_count": len(endpoint.rejected_docs),
                    "answer_permission": False,
                    "final_answer_allowed": False,
                })
            else:
                self._json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            payload = self._payload()
            question = extract_question(payload)
            top_k = int(payload.get("top_k") or endpoint.top_k)
            result = endpoint.context_for_query(question, top_k=top_k)

            if self.path in {"/api/trace-net/visual-context", "/api/trace-net/gemma-visual-context", "/api/trace-net/ask"}:
                self._json(200, result)
            elif self.path == "/v1/chat/completions":
                self._json(200, openai_response(model, question, result))
            else:
                self._json(404, {"error": "not_found"})

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8024)
    p.add_argument("--gemma-visual-retrieval-documents-jsonl", required=True)
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--min-score", type=float, default=0.001)
    p.add_argument("--model", default=DEFAULT_MODEL)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    docs = list(read_jsonl(Path(args.gemma_visual_retrieval_documents_jsonl)) or [])
    endpoint = GemmaVisualEndpoint(docs, top_k=args.top_k, min_score=args.min_score)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(endpoint, args.model))
    print(f"status=TRACE_NET_GEMMA_VISUAL_LIVE_ENDPOINT_V1_READY")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"clean_retrieval_document_count={len(endpoint.docs)}")
    print(f"rejected_document_count={len(endpoint.rejected_docs)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
