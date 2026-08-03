#!/usr/bin/env python3
"""TRACE-Net gated visual live endpoint v1.1.

Small local HTTP endpoint that proves the live router/OpenWebUI layer can call
the gated visual context route automatically.

Endpoints:
- GET  /health
- POST /api/trace-net/visual-context
- POST /api/trace-net/ask
- POST /v1/chat/completions

Safety contract:
- Read-only.
- Does not call OCR/LLM/Ollama.
- Does not write Postgres/Qdrant/OpenSearch.
- Does not mutate source-truth artifacts.
- Does not grant answer permission.
- Review-only visual candidates are counted but not used automatically.
- Visual observations are retrieval guidance only, not final proof.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MODULE_NAME = "trace_net_gated_visual_live_endpoint_v1_1"

# Keep direct triggers visual-specific. Generic words like "part", "parts",
# "item", "seat", and "assembly" are intentionally NOT direct triggers because
# partial part lookups such as "I only know the part starts with 24" must go to
# guided discovery, not the visual route.
VISUAL_TRIGGER_TERMS = {
    "diagram", "figure", "fig", "image", "visual", "drawing", "illustration",
    "callout", "callouts", "view", "exploded", "schematic",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-./]*")
STOP_TOKENS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "with", "without", "find", "show", "give", "what", "which", "page",
    "tell", "me", "does", "do", "there", "where", "look", "looking",
}


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            yield obj


def compact(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()[:limit]
    try:
        return re.sub(r"\s+", " ", json.dumps(value, ensure_ascii=False, sort_keys=True)).strip()[:limit]
    except Exception:
        return str(value)[:limit]


def tokenize(text: Any) -> List[str]:
    if text is None:
        return []
    if not isinstance(text, str):
        try:
            text = json.dumps(text, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(text)
    out: List[str] = []
    for t in TOKEN_RE.findall(text):
        t = t.lower()
        if len(t) <= 1 or t in STOP_TOKENS:
            continue
        out.append(t)
    return out


def listify(value: Any) -> List[str]:
    if not value:
        return []
    vals = value if isinstance(value, list) else [value]
    out: List[str] = []
    for v in vals:
        s = compact(v, 300)
        if s and s not in out:
            out.append(s)
    return out


def doc_text(doc: Dict[str, Any]) -> str:
    pieces: List[str] = [
        compact(doc.get("page_id"), 100),
        compact(doc.get("visual_route"), 100),
        compact(doc.get("visual_subtype"), 100),
        compact(doc.get("search_text"), 7000),
    ]
    for summary in listify(doc.get("visual_summaries")):
        pieces.append(summary)
    identifiers = doc.get("identifiers")
    if isinstance(identifiers, dict):
        for values in identifiers.values():
            pieces.extend(listify(values))
    return "\n".join(p for p in pieces if p)


def part_like_tokens(tokens: Sequence[str]) -> List[str]:
    out: List[str] = []
    for t in tokens:
        if re.search(r"\d{2,}[-./]\d{2,}", t) or re.search(r"\d{3,}", t):
            out.append(t)
    return out


def is_visual_query(query: str) -> Tuple[bool, List[str]]:
    tokens = set(tokenize(query))
    triggers = sorted(tokens & VISUAL_TRIGGER_TERMS)
    q_lower = query.lower()
    phrase_triggers: List[str] = []
    # Phrases that are visual by themselves.
    for phrase in (
        "technical drawing",
        "exploded view",
        "illustrated parts list",
        "parts diagram",
        "part diagram",
        "assembly diagram",
        "seat assembly diagram",
        "passenger seat diagram",
        "figure reference",
        "figure references",
        "figure refs",
        "callout",
        "callouts",
        "figure",
        "diagram",
    ):
        if phrase in q_lower:
            phrase_triggers.append(phrase)

    all_triggers = triggers + [p for p in phrase_triggers if p not in triggers]
    return bool(all_triggers), all_triggers


def score_doc(query: str, doc: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    q_tokens = tokenize(query)
    d_text = doc_text(doc)
    d_tokens = tokenize(d_text)
    d_set = set(d_tokens)
    q_set = set(q_tokens)

    overlap = sorted(q_set & d_set)

    q_parts = part_like_tokens(q_tokens)
    exact_part_hits: List[str] = []
    identifiers = doc.get("identifiers") if isinstance(doc.get("identifiers"), dict) else {}
    id_text = json.dumps(identifiers, ensure_ascii=False, sort_keys=True).lower()
    lower_text = d_text.lower()
    for p in q_parts:
        if p.lower() in id_text or p.lower() in lower_text:
            exact_part_hits.append(p)

    phrase_hits: List[str] = []
    q_lower = query.lower()
    for phrase in (
        "seat assembly",
        "passenger seat",
        "callout",
        "figure",
        "diagram",
        "technical drawing",
        "exploded view",
        "part number",
        "nomenclature",
        "parts list",
    ):
        if phrase in q_lower and phrase in lower_text:
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

    route_bonus = 1.5 if doc.get("visual_route") == "image_visual" else 1.0
    subtype_bonus = 1.0 if "diagram" in str(doc.get("visual_subtype", "")).lower() else 0.5
    exact_bonus = 8.0 * len(exact_part_hits)
    phrase_bonus = 2.0 * len(phrase_hits)
    norm = math.log(max(len(d_set), 20), 10)
    score = (len(overlap) / norm) + exact_bonus + phrase_bonus + route_bonus + subtype_bonus

    return score, {
        "score": round(score, 4),
        "token_overlap_count": len(overlap),
        "token_overlap": overlap[:30],
        "exact_part_hits": exact_part_hits,
        "phrase_hits": phrase_hits,
        "route_bonus": route_bonus,
        "subtype_bonus": subtype_bonus,
    }


def make_citation(doc: Dict[str, Any], rank: int, diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    identifiers = doc.get("identifiers") if isinstance(doc.get("identifiers"), dict) else {}
    summaries = listify(doc.get("visual_summaries"))
    return {
        "rank": rank,
        "citation_type": "gated_visual_context",
        "page_id": doc.get("page_id", ""),
        "document_id": doc.get("document_id", ""),
        "route": "image_visual",
        "visual_route": doc.get("visual_route"),
        "visual_subtype": doc.get("visual_subtype"),
        "route_confidence": doc.get("route_confidence"),
        "summary": summaries[0] if summaries else "",
        "part_numbers": listify(identifiers.get("part_numbers"))[:20],
        "figure_refs": listify(identifiers.get("figure_refs"))[:20],
        "callouts": listify(identifiers.get("callouts"))[:30],
        "nomenclature": listify(identifiers.get("nomenclature"))[:10],
        "citation_ready": bool(doc.get("citation_ready")),
        "source_trace_ready": bool(doc.get("source_trace_ready")),
        "score_diagnostics": diagnostics,
        "safety_note": "Visual context is retrieval guidance only and does not prove fit, interchangeability, effectivity, approval, or installation authority by itself.",
    }


def build_context_payload(
    query: str,
    docs: Sequence[Dict[str, Any]],
    *,
    top_k: int,
    min_score: float,
) -> Dict[str, Any]:
    visual_query, triggers = is_visual_query(query)
    scored: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []

    if visual_query:
        for doc in docs:
            if not doc.get("search_ready") or doc.get("review_only"):
                continue
            score, diagnostics = score_doc(query, doc)
            if score >= min_score:
                scored.append((score, doc, diagnostics))

    scored.sort(key=lambda x: (-x[0], str(x[1].get("page_id", ""))))
    citations = [
        make_citation(doc, rank=i, diagnostics=diag)
        for i, (_, doc, diag) in enumerate(scored[:top_k], start=1)
    ]

    status = "visual_context_candidates_found" if citations else (
        "visual_route_not_triggered" if not visual_query else "no_visual_context_candidates_found"
    )

    return {
        "module": MODULE_NAME,
        "query": query,
        "route_name": "gated_image_visual",
        "route_triggered": visual_query,
        "route_triggers": triggers,
        "context_pack_status": status,
        "endpoint_payload_type": "trace_net_route_context",
        "candidate_count": len(scored),
        "citation_count": len(citations),
        "page_count": len({c.get("page_id") for c in citations if c.get("page_id")}),
        "citations": citations,
        "context_instructions": [
            "Use these visual citations only as retrieval guidance.",
            "Do not answer fit/interchangeability/effectivity/approval/installation claims from visual context alone.",
            "Require corroborating OCR/table/source-trace evidence before final claims.",
            "Keep visual_candidate_review pages out of automatic answer context.",
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


def safe_context_text(payload: Dict[str, Any]) -> str:
    lines = [
        "TRACE-Net gated visual context draft.",
        "This is not a final answer. Visual evidence is retrieval guidance only.",
        f"Route triggered: {payload.get('route_triggered')}",
        f"Status: {payload.get('context_pack_status')}",
        f"Citations: {payload.get('citation_count')}",
    ]
    for c in payload.get("citations", [])[:8]:
        parts = [
            f"page {c.get('page_id')}",
            f"score {c.get('score_diagnostics', {}).get('score')}",
            f"subtype {c.get('visual_subtype')}",
        ]
        figs = c.get("figure_refs") or []
        pns = c.get("part_numbers") or []
        if figs:
            parts.append("figures " + ", ".join(figs[:3]))
        if pns:
            parts.append("parts " + ", ".join(pns[:3]))
        lines.append("- " + "; ".join(parts))
    lines.append("Answer permission: false.")
    lines.append("Final answer allowed: false.")
    return "\n".join(lines)


class VisualEndpoint:
    def __init__(self, docs: Sequence[Dict[str, Any]], review_docs: Sequence[Dict[str, Any]], top_k: int, min_score: float) -> None:
        self.docs = list(docs)
        self.review_docs = list(review_docs)
        self.top_k = top_k
        self.min_score = min_score

    def health(self) -> Dict[str, Any]:
        route_counts = Counter(str(d.get("visual_route")) for d in self.docs)
        subtype_counts = Counter(str(d.get("visual_subtype")) for d in self.docs)
        return {
            "status": "ok",
            "module": MODULE_NAME,
            "quality_status": "PASS",
            "retrieval_document_count": len(self.docs),
            "review_only_document_count": len(self.review_docs),
            "visual_route_counts": dict(sorted(route_counts.items())),
            "visual_subtype_counts": dict(sorted(subtype_counts.items())),
            "route_name": "gated_image_visual",
            "final_answer_allowed": False,
            "answer_permission": False,
            "does_not_call_ollama": True,
            "does_not_call_llm": True,
        }

    def build_payload(self, query: str) -> Dict[str, Any]:
        return build_context_payload(query, self.docs, top_k=self.top_k, min_score=self.min_score)

    def ask_response(self, query: str) -> Dict[str, Any]:
        payload = self.build_payload(query)
        return {
            "status": "ok",
            "module": MODULE_NAME,
            "query": query,
            "response_status": "visual_context_draft",
            "response_is_final_answer": False,
            "final_answer_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "route_context": payload,
            "content": safe_context_text(payload),
        }

    def chat_response(self, body: Dict[str, Any]) -> Dict[str, Any]:
        messages = body.get("messages") if isinstance(body.get("messages"), list) else []
        query = ""
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                query = compact(msg.get("content"), limit=2000)
                break
        if not query:
            query = compact(body.get("prompt") or body.get("query") or "", limit=2000)

        ask = self.ask_response(query)
        return {
            "id": "trace-net-gated-visual-live-endpoint-v1-1",
            "object": "chat.completion",
            "model": body.get("model") or "trace-net-gated-visual-live-endpoint-v1-1",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": ask["content"],
                    },
                    "finish_reason": "stop",
                }
            ],
            "trace_net": ask,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }


def make_handler(endpoint: VisualEndpoint):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetGatedVisualLiveEndpoint/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            if getattr(self.server, "quiet", False):
                return
            super().log_message(fmt, *args)

        def _send_json(self, status: int, data: Dict[str, Any]) -> None:
            raw = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _read_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                obj = json.loads(raw.decode("utf-8"))
            except Exception:
                return {}
            return obj if isinstance(obj, dict) else {}

        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] == "/health":
                self._send_json(200, endpoint.health())
            else:
                self._send_json(404, {"error": "not_found", "path": self.path})

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            body = self._read_body()
            if path == "/api/trace-net/visual-context":
                query = compact(body.get("query") or body.get("question") or body.get("input") or body.get("prompt") or "", limit=2000)
                self._send_json(200, endpoint.build_payload(query))
            elif path == "/api/trace-net/ask":
                query = compact(body.get("query") or body.get("question") or body.get("input") or body.get("prompt") or "", limit=2000)
                self._send_json(200, endpoint.ask_response(query))
            elif path == "/v1/chat/completions":
                self._send_json(200, endpoint.chat_response(body))
            else:
                self._send_json(404, {"error": "not_found", "path": path})

    return Handler


def load_endpoint(args: argparse.Namespace) -> VisualEndpoint:
    docs = list(read_jsonl(Path(args.gated_visual_retrieval_documents_jsonl)) or [])
    review_docs = list(read_jsonl(Path(args.review_only_documents_jsonl)) or []) if args.review_only_documents_jsonl else []
    return VisualEndpoint(docs=docs, review_docs=review_docs, top_k=args.top_k, min_score=args.min_score)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gated-visual-retrieval-documents-jsonl", required=True)
    p.add_argument("--review-only-documents-jsonl", default="")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8022)
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--min-score", type=float, default=0.001)
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    endpoint = load_endpoint(args)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(endpoint))
    server.quiet = bool(args.quiet)  # type: ignore[attr-defined]
    print(f"TRACE-Net gated visual live endpoint running at http://{args.host}:{args.port}", flush=True)
    print(f"health: http://{args.host}:{args.port}/health", flush=True)
    print("ask:    POST /api/trace-net/ask", flush=True)
    print("chat:   POST /v1/chat/completions", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTRACE-Net gated visual live endpoint stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
