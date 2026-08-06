#!/usr/bin/env python3
"""TRACE-Net authenticated unified OpenWebUI front door v2.

One front door for:
- live v27 normal/source-truth route on 8014
- real guided candidate-discovery endpoint on 8016
- strict Gemma visual retrieval
- Qdrant semantic guidance
- Engram policy memory
- deterministic Self-RAG critic and CRAG repair
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tiff.trace_net_query_atom_router_v1 import analyze_query

MODULE = "trace_net_openwebui_unified_rag_v2"
MODEL_ID = "trace-net-openwebui-unified-rag-v2"

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-/]*")
PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b")
MANUAL_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
FIGURE_RE = re.compile(r"\b(?:figure|fig\.?)\s*(\d{1,4})(?:\s+sheet\s+(\d{1,3}))?\b", re.I)

VISUAL_TERMS = {"diagram", "figure", "fig", "image", "drawing", "illustration", "callout", "callouts", "schematic", "exploded", "view"}
GENERIC_VISUAL_TERMS = VISUAL_TERMS | {"show", "find", "page", "pages", "reference", "references", "part", "number", "assembly"}
PARTIAL_MARKERS = ("only know", "only remember", "partial", "starts with", "begins with", "contains", "looked like", "might be", "i think")
REFERENTIAL_TERMS = ("it", "that", "this", "the figure", "the diagram", "that part", "what figure", "which page")
PROMPT_LEAKS = (
    "trace-net's visual observation specialist",
    "scanned aircraft technical-manual pages",
    "required json fields",
    "strict rules",
)
DANGEROUS = (
    "interchangeable", "approved replacement", "safe to install", "fit approval",
    "effectivity", "eligibility", "installation safety",
)

STOP = {
    "a","an","and","are","as","at","be","by","for","from","has","have","in","into",
    "is","it","of","on","or","that","the","this","to","with","without","me","please",
}


def compact(value: Any, limit: int = 2000) -> str:
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


def tokenize(value: Any) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(compact(value, 50000)) if len(t) > 1 and t.lower() not in STOP]


def listify(value: Any) -> List[str]:
    vals = value if isinstance(value, list) else ([value] if value else [])
    out, seen = [], set()
    for item in vals:
        text = compact(item, 1000)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL, timeout=2).strip()
    except Exception:
        return os.environ.get("TRACE_NET_GIT_COMMIT", "unknown")


def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def extract_text_content(content: Any) -> str:
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


def user_messages(messages: Any) -> List[str]:
    out: List[str] = []
    if not isinstance(messages, list):
        return out
    for msg in messages:
        if isinstance(msg, Mapping) and str(msg.get("role", "")).lower() == "user":
            text = extract_text_content(msg.get("content"))
            if text:
                out.append(text)
    return out


def resolve_conversation(payload: Mapping[str, Any]) -> Dict[str, Any]:
    for key in ("query", "question", "input", "prompt"):
        if isinstance(payload.get(key), str) and str(payload[key]).strip():
            latest = str(payload[key]).strip()
            messages = [latest]
            break
    else:
        messages = user_messages(payload.get("messages"))
        latest = messages[-1] if messages else ""

    previous = messages[:-1]
    memory = {
        "part_numbers": [],
        "manual_references": [],
        "figures": [],
    }
    for text in previous[-6:]:
        memory["part_numbers"].extend(PART_RE.findall(text))
        memory["manual_references"].extend(MANUAL_RE.findall(text))
        memory["figures"].extend(
            f"figure {m.group(1)}" + (f" sheet {m.group(2)}" if m.group(2) else "")
            for m in FIGURE_RE.finditer(text)
        )
    for key in memory:
        memory[key] = list(dict.fromkeys(memory[key]))[-4:]

    low = latest.lower()
    current_has_entity = bool(PART_RE.search(latest) or MANUAL_RE.search(latest) or FIGURE_RE.search(latest))
    needs_memory = (not current_has_entity) and any(term in low for term in REFERENTIAL_TERMS)
    additions: List[str] = []
    if needs_memory:
        if memory["part_numbers"]:
            additions.append("active part number " + memory["part_numbers"][-1])
        if memory["manual_references"]:
            additions.append("active manual reference " + memory["manual_references"][-1])
        if memory["figures"]:
            additions.append("active " + memory["figures"][-1])
    resolved = latest + (". Conversation context: " + "; ".join(additions) if additions else "")
    return {
        "latest_query": latest,
        "resolved_query": resolved,
        "working_memory": memory,
        "working_memory_applied": bool(additions),
        "working_memory_additions": additions,
    }


class EngramIndex:
    def __init__(self, path: Optional[Path]):
        self.path = path
        self.records: List[Dict[str, Any]] = []
        self.sha256 = ""
        if path and path.exists():
            data = read_json(path)
            rows = data.get("records")
            if isinstance(rows, list):
                self.records = [dict(r) for r in rows if isinstance(r, Mapping)]
            self.sha256 = sha256_file(path)

    def select(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        q = query.lower()
        scored: List[Tuple[int, Dict[str, Any]]] = []
        for row in self.records:
            triggers = listify(row.get("triggers"))
            score = sum(4 for t in triggers if t.lower() in q)
            if str(row.get("priority")) == "hard_boundary":
                score += 1
            if score:
                scored.append((score, row))
        scored.sort(key=lambda x: (-x[0], str(x[1].get("engram_id", ""))))
        return [
            {
                "engram_id": r.get("engram_id"),
                "memory_type": r.get("memory_type"),
                "priority": r.get("priority"),
                "trait": r.get("trait"),
                "rule": r.get("rule"),
                "good_behavior": r.get("good_behavior"),
            }
            for _, r in scored[:limit]
        ]


class VisualIndex:
    def __init__(self, path: Path, strict: bool = True):
        self.path = path
        self.sha256 = sha256_file(path)
        self.docs: List[Dict[str, Any]] = []
        self.by_page: Dict[str, Dict[str, Any]] = {}
        self.parse_failures: List[Dict[str, Any]] = []
        self.duplicates: List[str] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
            except Exception as exc:
                self.parse_failures.append({"line": line_no, "error": str(exc)})
                continue
            if not isinstance(doc, dict):
                self.parse_failures.append({"line": line_no, "error": "record_not_object"})
                continue
            failures = self.validate_doc(doc)
            if failures:
                self.parse_failures.append({"line": line_no, "page_id": doc.get("page_id"), "error": ",".join(failures)})
                continue
            page_id = str(doc["page_id"])
            if page_id in self.by_page:
                self.duplicates.append(page_id)
                continue
            self.by_page[page_id] = doc
            self.docs.append(doc)
        if strict and (self.parse_failures or self.duplicates):
            raise ValueError(
                f"Visual JSONL failed strict validation: parse_or_schema_failures={len(self.parse_failures)} "
                f"duplicate_page_ids={len(self.duplicates)}"
            )
        self.df = Counter()
        for doc in self.docs:
            self.df.update(set(self.meaningful_tokens(self.doc_text(doc))))

    @staticmethod
    def card(doc: Mapping[str, Any]) -> Mapping[str, Any]:
        value = doc.get("structured_visual_card")
        return value if isinstance(value, Mapping) else {}

    @classmethod
    def validate_doc(cls, doc: Mapping[str, Any]) -> List[str]:
        failures = []
        page_id = compact(doc.get("page_id"), 200)
        if not page_id:
            failures.append("missing_page_id")
        if not compact(doc.get("retrieval_text"), 5000):
            failures.append("missing_retrieval_text")
        blob = json.dumps(doc, ensure_ascii=False).lower()
        if any(pattern in blob for pattern in PROMPT_LEAKS):
            failures.append("prompt_leak")
        safety = doc.get("safety_contract") if isinstance(doc.get("safety_contract"), Mapping) else {}
        for key in ("answer_permission", "final_answer_allowed", "source_truth_mutation_allowed"):
            if safety.get(key):
                failures.append(f"safety_true:{key}")
        return failures

    @classmethod
    def doc_text(cls, doc: Mapping[str, Any]) -> str:
        card = cls.card(doc)
        return " ".join([
            compact(doc.get("retrieval_text"), 20000),
            compact(card.get("normalized_subject"), 2000),
            compact(card.get("normalized_visual_page_type"), 500),
            " ".join(listify(card.get("figure_refs"))),
            " ".join(listify(card.get("part_numbers"))),
            " ".join(listify(card.get("visible_callouts"))),
            " ".join(listify(card.get("retrieval_keywords"))),
        ])

    @staticmethod
    def meaningful_tokens(text: str) -> List[str]:
        return [t for t in tokenize(text) if t not in GENERIC_VISUAL_TERMS]

    def exact_part_docs(self, part_number: str) -> List[Dict[str, Any]]:
        target = part_number.strip().upper()
        rows = []
        for doc in self.docs:
            parts = [p.upper() for p in listify(self.card(doc).get("part_numbers"))]
            if target in parts:
                rows.append(doc)
        return rows

    def rank(
        self,
        query: str,
        *,
        qdrant_page_scores: Optional[Mapping[str, float]] = None,
        top_k: int = 8,
        min_score: float = 2.5,
    ) -> List[Tuple[float, Dict[str, Any], Dict[str, Any]]]:
        exact_parts = PART_RE.findall(query)
        if exact_parts:
            exact_docs = self.exact_part_docs(exact_parts[0])
            return [
                (1000.0 - idx, doc, {"exact_part_match": exact_parts[0], "semantic_page_score": (qdrant_page_scores or {}).get(str(doc.get("page_id")), 0.0)})
                for idx, doc in enumerate(exact_docs[:top_k])
            ]

        q_tokens = set(self.meaningful_tokens(query))
        if not q_tokens:
            return []
        n_docs = max(1, len(self.docs))
        ranked = []
        for doc in self.docs:
            d_tokens = set(self.meaningful_tokens(self.doc_text(doc)))
            overlap = q_tokens & d_tokens
            lexical = sum(math.log((n_docs + 1) / (1 + self.df.get(t, 0))) + 1.0 for t in overlap)
            page_id = str(doc.get("page_id") or "")
            semantic = float((qdrant_page_scores or {}).get(page_id, 0.0))
            phrase_bonus = 0.0
            qlow = query.lower()
            dlow = self.doc_text(doc).lower()
            for phrase in ("passenger seat", "seat assembly", "armrest", "ashtray", "snack table", "locking ring"):
                if phrase in qlow and phrase in dlow:
                    phrase_bonus += 6.0
            score = lexical + phrase_bonus + (semantic * 4.0)
            if score >= min_score and (overlap or semantic >= 0.45):
                ranked.append((score, doc, {
                    "meaningful_token_overlap": sorted(overlap),
                    "lexical_score": round(lexical, 4),
                    "phrase_bonus": phrase_bonus,
                    "semantic_page_score": round(semantic, 4),
                }))
        ranked.sort(key=lambda x: (-x[0], str(x[1].get("page_id", ""))))
        return ranked[:top_k]

    def citation(self, doc: Mapping[str, Any], rank: int, score: float, diagnostics: Mapping[str, Any]) -> Dict[str, Any]:
        card = self.card(doc)
        return {
            "citation_id": rank,
            "citation_type": "visual_retrieval_guidance",
            "page_id": doc.get("page_id"),
            "document_id": doc.get("document_id"),
            "subject": compact(card.get("normalized_subject"), 1000),
            "visual_page_type": compact(card.get("normalized_visual_page_type"), 300),
            "figure_refs": listify(card.get("figure_refs"))[:20],
            "part_numbers": listify(card.get("part_numbers"))[:20],
            "visible_callouts": listify(card.get("visible_callouts"))[:30],
            "score": round(float(score), 4),
            "score_diagnostics": dict(diagnostics),
            "direct_proof_authority": False,
            "source_trace_ready": bool(doc.get("page_id")),
            "citation_ready": bool(doc.get("page_id")),
            "safety_note": "Visual context is retrieval guidance only and cannot prove fit, approval, effectivity, interchangeability, eligibility, or installation.",
        }


class QdrantGuide:
    def __init__(
        self,
        *,
        qdrant_url: str,
        collection: str,
        ollama_url: str,
        embedding_model: str,
        timeout: float,
    ):
        self.qdrant_url = qdrant_url.rstrip("/")
        self.collection = collection
        self.ollama_url = ollama_url.rstrip("/")
        self.embedding_model = embedding_model
        self.timeout = timeout

    def _json_request(self, url: str, payload: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="GET" if data is None else "POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            value = json.loads(resp.read().decode("utf-8"))
        return value if isinstance(value, dict) else {}

    def health(self) -> Dict[str, Any]:
        try:
            data = self._json_request(f"{self.qdrant_url}/collections/{urllib.parse.quote(self.collection)}")
            result = data.get("result") if isinstance(data.get("result"), Mapping) else {}
            return {
                "connected": True,
                "status": result.get("status") or data.get("status") or "ok",
                "points_count": result.get("points_count"),
                "collection": self.collection,
            }
        except Exception as exc:
            return {"connected": False, "collection": self.collection, "error": f"{type(exc).__name__}: {exc}"}

    def embed(self, text: str) -> List[float]:
        data = self._json_request(
            f"{self.ollama_url}/api/embed",
            {"model": self.embedding_model, "input": [text]},
        )
        values = data.get("embeddings")
        if not isinstance(values, list) or not values or not isinstance(values[0], list):
            raise RuntimeError("Ollama embed response did not include embeddings[0]")
        return [float(x) for x in values[0]]

    def search(self, text: str, limit: int = 20) -> List[Dict[str, Any]]:
        vector = self.embed(text)
        data = self._json_request(
            f"{self.qdrant_url}/collections/{urllib.parse.quote(self.collection)}/points/search",
            {"vector": vector, "limit": limit, "with_payload": True, "with_vector": False},
        )
        rows = data.get("result")
        out = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, Mapping):
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), Mapping) else {}
            out.append({
                "point_id": row.get("id"),
                "score": float(row.get("score") or 0.0),
                "page_id": payload.get("page_id"),
                "document_id": payload.get("document_id"),
                "candidate_type": payload.get("candidate_type"),
                "rag_bucket": payload.get("rag_bucket"),
                "trust_tier": payload.get("trust_tier"),
                "embedding_text_preview": payload.get("embedding_text_preview"),
                "requires_source_resolution": payload.get("requires_source_resolution", True),
                "qdrant_is_source_truth": False,
            })
        return out


def route_kind(query: str) -> str:
    """Compatibility wrapper around the deterministic query-atom router."""
    return str(analyze_query(query)["execution_route"])


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
    req = urllib.request.Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
            return resp.status, body if isinstance(body, dict) else {}
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            body = {"error": str(exc)}
        return exc.code, body if isinstance(body, dict) else {}
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}


def visual_answer(query: str, citations: Sequence[Mapping[str, Any]], exact_part: Optional[str]) -> str:
    if not citations:
        return (
            "TRACE-Net did not find a sufficiently relevant confirmed visual page. "
            "Try adding an exact part number, figure number, component name, or nearby callout."
        )
    if exact_part:
        lines = [f"TRACE-Net found confirmed visual page(s) that explicitly list part number {exact_part}:"]
    else:
        lines = ["TRACE-Net found these confirmed visual candidates:"]
    for c in citations[:5]:
        figures = ", ".join(c.get("figure_refs") or []) or "figure not clearly identified"
        parts = ", ".join(c.get("part_numbers") or []) or "no exact part number on the visual card"
        subject = c.get("subject") or "unknown subject"
        lines.append(f"- [{c.get('citation_id')}] page {c.get('page_id')}: {subject}; figures: {figures}; parts: {parts}")
    lines.append("These visual cards help locate the source page; they are not final proof of fit, approval, effectivity, interchangeability, eligibility, or installation.")
    return "\n".join(lines)


def guided_answer(payload: Mapping[str, Any]) -> str:
    candidates = payload.get("strict_prefix_candidates") or payload.get("candidate_routes") or []
    questions = payload.get("clarifying_questions") or []
    lines = ["TRACE-Net treated this as candidate discovery, not a final part identification."]
    if candidates:
        lines.append("Top candidate clues:")
        for idx, item in enumerate(candidates[:5], 1):
            if isinstance(item, Mapping):
                value = item.get("candidate_value") or item.get("part_number") or item.get("value") or item.get("matched_token") or compact(item, 300)
                lines.append(f"- {idx}. {value}")
    if questions:
        lines.append("Helpful follow-up questions:")
        for q in questions[:5]:
            lines.append(f"- {q}")
    return "\n".join(lines)


def router_clarification_payload(
    query: str,
    router_decision: Mapping[str, Any],
) -> Dict[str, Any]:
    plan = (
        router_decision.get("follow_up_plan")
        if isinstance(router_decision.get("follow_up_plan"), Mapping)
        else {}
    )
    atoms = (
        router_decision.get("atoms")
        if isinstance(router_decision.get("atoms"), Mapping)
        else {}
    )
    return {
        "quality_status": "PASS",
        "intent": router_decision.get("selected_tunnel"),
        "known_clues": dict(atoms),
        "missing_clues": list(plan.get("follow_up_topics") or []),
        "candidate_routes": [],
        "strict_prefix_candidates": [],
        "clarifying_questions": list(plan.get("clarifying_questions") or []),
        "source_trace_status": "clarification-before-expensive-search",
        "answer_permission": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed": False,
    }


def fast_clarification(query: str) -> Dict[str, Any]:
    part = PART_RE.findall(query)
    prefix = ""
    m = re.search(r"\b(?:starts?|begins?)\s+(?:with\s+)?([A-Za-z0-9-]{1,12})", query, re.I)
    if m:
        prefix = m.group(1)
    return {
        "quality_status": "PASS",
        "intent": "clarification_before_candidate_discovery",
        "known_clues": {"part_numbers": part, "prefix": prefix},
        "candidate_routes": [],
        "strict_prefix_candidates": [],
        "clarifying_questions": [
            "Do you know any characters after the prefix, including a dash number or suffix?",
            "What physical part type or exact nomenclature is associated with the clue?",
            "Was the clue seen in a table, figure callout, OCR text, or a particular page?",
        ],
        "source_trace_status": "candidate-discovery-only",
        "final_answer_allowed": False,
    }


def self_rag_critic(route: str, result: Mapping[str, Any], query: str) -> Dict[str, Any]:
    failures: List[str] = []
    if route == "normal_ask":
        if int(result.get("downstream_status_code") or 0) != 200:
            failures.append("normal_downstream_not_200")
        if result.get("quality_status") not in {"PASS", "WARN"}:
            failures.append("normal_downstream_quality_bad")
        if result.get("final_gate_status") not in {"LIVE_ORCHESTRATOR_FINAL_GATE_PASS", "LIVE_ORCHESTRATOR_AUDIT_ONLY"}:
            failures.append("normal_final_gate_missing")
        if result.get("final_answer_ready_for_webui") and int(result.get("citation_count") or 0) <= 0:
            failures.append("normal_ready_without_source_citations")
    elif route == "guided_discovery":
        if int(result.get("downstream_status_code") or 0) != 200:
            failures.append("guided_downstream_not_200")
        payload = result.get("downstream_response") if isinstance(result.get("downstream_response"), Mapping) else {}
        if payload.get("quality_status") != "PASS":
            failures.append("guided_downstream_quality_not_pass")
        if not (payload.get("candidate_routes") or payload.get("clarifying_questions")):
            failures.append("guided_has_neither_candidates_nor_questions")
    elif route == "gemma_confirmed_image_visual":
        citations = result.get("citations") or []
        exact = PART_RE.findall(query)
        if not citations:
            failures.append("visual_no_relevant_citations")
        if exact:
            for c in citations:
                if exact[0] not in (c.get("part_numbers") or []):
                    failures.append("visual_exact_part_returned_unrelated_doc")
                    break
    for key in ("answer_permission", "final_answer_allowed", "source_truth_mutation_allowed"):
        if result.get(key):
            failures.append(f"safety_true:{key}")
    return {
        "quality_status": "PASS" if not failures else "RETRY",
        "failures": failures,
        "retry_required": bool(failures),
    }


class UnifiedRuntime:
    def __init__(
        self,
        *,
        normal_base_url: str,
        guided_base_url: str,
        visual_index: VisualIndex,
        engram_index: EngramIndex,
        qdrant: QdrantGuide,
        api_key: str,
        downstream_api_key: str,
        timeout: float,
        max_request_bytes: int,
        max_concurrency: int,
        require_qdrant: bool,
    ):
        self.normal_base_url = normal_base_url.rstrip("/")
        self.guided_base_url = guided_base_url.rstrip("/")
        self.visual = visual_index
        self.engram = engram_index
        self.qdrant = qdrant
        self.api_key = api_key
        self.downstream_api_key = downstream_api_key
        self.timeout = timeout
        self.max_request_bytes = max_request_bytes
        self.semaphore = threading.BoundedSemaphore(max(1, max_concurrency))
        self.require_qdrant = require_qdrant
        self.git_commit = git_commit()

    def qdrant_guidance(self, query: str) -> Tuple[List[Dict[str, Any]], Dict[str, float], Optional[str]]:
        try:
            hits = self.qdrant.search(query, limit=24)
            page_scores: Dict[str, float] = {}
            for hit in hits:
                page = str(hit.get("page_id") or "")
                if page:
                    page_scores[page] = max(page_scores.get(page, 0.0), float(hit.get("score") or 0.0))
            return hits, page_scores, None
        except Exception as exc:
            return [], {}, f"{type(exc).__name__}: {exc}"

    def process(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        conversation = resolve_conversation(payload)
        query = conversation["resolved_query"]
        latest = conversation["latest_query"]
        router_decision = analyze_query(query)
        route = str(router_decision["execution_route"])
        engrams = self.engram.select(query)
        qhits, qpage_scores, qerror = self.qdrant_guidance(query)
        repair_attempts: List[Dict[str, Any]] = []

        if route == "gemma_confirmed_image_visual":
            ranked = self.visual.rank(query, qdrant_page_scores=qpage_scores, top_k=int(payload.get("top_k") or 8))
            citations = [self.visual.citation(doc, i, score, diag) for i, (score, doc, diag) in enumerate(ranked, 1)]
            exact = PART_RE.findall(query)
            result: Dict[str, Any] = {
                "quality_status": "PASS",
                "route": route,
                "content": visual_answer(latest, citations, exact[0] if exact else None),
                "citation_count": len(citations),
                "citations": citations,
                "downstream_status_code": 200,
                "answer_permission": False,
                "final_answer_allowed": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
            critic = self_rag_critic(route, result, query)
            if critic["retry_required"] and not exact:
                ranked = self.visual.rank(query, qdrant_page_scores=qpage_scores, top_k=int(payload.get("top_k") or 8), min_score=1.5)
                citations = [self.visual.citation(doc, i, score, diag) for i, (score, doc, diag) in enumerate(ranked, 1)]
                result.update({"content": visual_answer(latest, citations, None), "citation_count": len(citations), "citations": citations})
                repair_attempts.append({"repair": "lowered_visual_threshold_with_qdrant_page_guidance", "citation_count": len(citations)})
                critic = self_rag_critic(route, result, query)

        elif route == "guided_discovery":
            tunnel = str(router_decision.get("selected_tunnel") or "")
            if tunnel in {"descriptive_part_discovery", "fast_clarification"}:
                status = 200
                downstream = router_clarification_payload(query, router_decision)
            else:
                status, downstream = http_json(
                    self.guided_base_url + "/api/trace-net/guided-discovery",
                    {"question": query, "top_k": int(payload.get("top_k") or 8), "loose_top_k": int(payload.get("loose_top_k") or 8), "include_view": False},
                    api_key=None,
                    timeout=self.timeout,
                )
                if status == 200:
                    router_questions = list(router_decision.get("clarifying_questions") or [])
                    downstream_questions = list(downstream.get("clarifying_questions") or [])
                    downstream["clarifying_questions"] = list(dict.fromkeys(router_questions + downstream_questions))[:5]
            result = {
                "quality_status": "PASS" if status == 200 and downstream.get("quality_status") == "PASS" else "WARN",
                "route": route,
                "content": guided_answer(downstream) if status == 200 else "",
                "citation_count": 0,
                "citations": [],
                "downstream_status_code": status,
                "downstream_response": downstream,
                "answer_permission": False,
                "final_answer_allowed": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
            critic = self_rag_critic(route, result, query)
            if critic["retry_required"]:
                fallback = fast_clarification(query)
                result.update({
                    "quality_status": "PASS",
                    "content": guided_answer(fallback),
                    "downstream_status_code": 200,
                    "downstream_response": fallback,
                })
                repair_attempts.append({"repair": "guided_fast_clarification_fallback", "original_status": status})
                critic = self_rag_critic(route, result, query)

        else:
            status, downstream = http_json(
                self.normal_base_url + "/api/trace-net/ask",
                {"query": query, "messages": payload.get("messages") or [{"role": "user", "content": query}]},
                api_key=self.downstream_api_key,
                timeout=self.timeout,
            )
            result = dict(downstream)
            result.update({
                "route": route,
                "downstream_status_code": status,
                "answer_permission": False,
                "final_answer_allowed": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            })
            if status != 200:
                result["content"] = "TRACE-Net could not reach the live source-truth retrieval service. No answer is provided."
                result["quality_status"] = "WARN"
            critic = self_rag_critic(route, result, query)
            if critic["retry_required"] and qhits:
                result.setdefault("semantic_guidance_only", qhits[:8])
                result.setdefault("content", "")
                if not result.get("content"):
                    pages = [str(h.get("page_id")) for h in qhits[:5] if h.get("page_id")]
                    result["content"] = (
                        "TRACE-Net found semantic candidate pages in Qdrant"
                        + (": " + ", ".join(pages) if pages else "")
                        + ", but it did not resolve them to direct source-truth evidence. No factual claim is made."
                    )
                repair_attempts.append({"repair": "qdrant_semantic_guidance_attached_without_promoting_to_proof", "hit_count": len(qhits)})

        follow_up_questions = list(router_decision.get("clarifying_questions") or [])
        should_surface_followups = (
            route == "guided_discovery"
            or (
                route == "gemma_confirmed_image_visual"
                and int(result.get("citation_count") or 0) == 0
            )
            or (
                route == "normal_ask"
                and (
                    result.get("final_gate_status") == "LIVE_ORCHESTRATOR_AUDIT_ONLY"
                    or router_decision.get("selected_tunnel") == "safety_authority_search"
                )
            )
        )
        if route != "guided_discovery" and should_surface_followups and follow_up_questions:
            content = str(result.get("content") or "").rstrip()
            lines = [content, "", "Helpful follow-up questions:"] if content else ["Helpful follow-up questions:"]
            lines.extend(f"- {question}" for question in follow_up_questions[:5])
            result["content"] = "\n".join(lines)

        safety_rules = [e for e in engrams if str(e.get("priority")) == "hard_boundary"]
        if safety_rules and any(term in query.lower() for term in DANGEROUS):
            result["content"] = result.get("content", "").rstrip() + "\n\nSafety boundary: TRACE-Net requires explicit source authority before making approval, fit, effectivity, interchangeability, eligibility, or installation claims."

        result.update({
            "module": MODULE,
            "model": MODEL_ID,
            "router_decision": router_decision,
            "retrieval_tunnel": router_decision.get("selected_tunnel"),
            "follow_up_plan": router_decision.get("follow_up_plan"),
            "follow_up_questions": list(router_decision.get("clarifying_questions") or []),
            "clarification_required": bool(router_decision.get("clarification_required")),
            "clarification_recommended": bool(router_decision.get("clarification_recommended")),
            "query": latest,
            "resolved_query": query,
            "working_memory": conversation["working_memory"],
            "working_memory_applied": conversation["working_memory_applied"],
            "engram_context": engrams,
            "qdrant_guidance": {
                "connected_for_request": qerror is None,
                "error": qerror,
                "hit_count": len(qhits),
                "hits": qhits[:12],
                "guidance_only": True,
                "source_truth": False,
            },
            "self_rag_critic": critic,
            "crag_repair_attempts": repair_attempts,
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "safety_contract": {
                "read_only": True,
                "qdrant_is_guidance_not_proof": True,
                "visual_is_guidance_not_proof": True,
                "engram_is_behavior_policy_not_source_truth": True,
                "citation_values_derived_from_answer_text": False,
                "postgres_write_attempt": False,
                "qdrant_write_attempt": False,
                "opensearch_write_attempt": False,
            },
        })
        return result

    def health(self) -> Dict[str, Any]:
        normal_status, normal = http_json(self.normal_base_url + "/health", None, api_key=None, timeout=min(3.0, self.timeout))
        guided_status, guided = http_json(self.guided_base_url + "/health", None, api_key=None, timeout=min(3.0, self.timeout))
        qhealth = self.qdrant.health()
        normal_ok = normal_status == 200 and normal.get("module") == "trace_net_live_rag_normal_v2"
        guided_ok = guided_status == 200 and guided.get("service") == "trace_net_guided_candidate_discovery_endpoint_v1" and guided.get("quality_status") == "PASS"
        qok = bool(qhealth.get("connected"))
        ready = normal_ok and guided_ok and bool(self.visual.docs) and bool(self.engram.records) and (qok or not self.require_qdrant)
        return {
            "status": "ok" if ready else "needs_repair",
            "quality_status": "PASS" if ready else "FAIL",
            "module": MODULE,
            "version": "v2",
            "model_id": MODEL_ID,
            "git_commit": self.git_commit,
            "normal": {"status_code": normal_status, "identity_ok": normal_ok, "health": normal},
            "guided": {"status_code": guided_status, "identity_ok": guided_ok, "health": guided},
            "visual": {
                "document_count": len(self.visual.docs),
                "artifact_path": str(self.visual.path),
                "artifact_sha256": self.visual.sha256,
                "parse_or_schema_failure_count": len(self.visual.parse_failures),
                "duplicate_page_id_count": len(self.visual.duplicates),
            },
            "qdrant": qhealth,
            "qdrant_required": self.require_qdrant,
            "engram": {
                "record_count": len(self.engram.records),
                "artifact_path": str(self.engram.path) if self.engram.path else None,
                "artifact_sha256": self.engram.sha256,
            },
            "graph_guidance_connected": bool((normal.get("leiden_page_membership_count") or 0) > 0),
            "v2_summary_guidance_connected": bool((normal.get("page_summary_count") or 0) > 0),
            "openai_routes": ["/v1/models", "/v1/chat/completions"],
            "native_routes": ["/health", "/api/trace-net/ask"],
            "answer_permission": False,
            "final_answer_allowed": False,
        }


def openai_response(result: Mapping[str, Any], model: str) -> Dict[str, Any]:
    return {
        "id": "chatcmpl-trace-unified-v2-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": str(result.get("content") or "")}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": dict(result),
    }


def openai_error(message: str, code: str, status: int) -> Dict[str, Any]:
    return {"error": {"message": message, "type": "trace_net_error", "param": None, "code": code}, "status": status}


def make_handler(runtime: UnifiedRuntime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetUnifiedRagV2/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send(self, status: int, payload: Mapping[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _authorized(self) -> bool:
            return self.headers.get("Authorization", "") == f"Bearer {runtime.api_key}"

        def _read(self) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[int, Dict[str, Any]]]]:
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0:
                return None, (400, openai_error("Request body is required.", "invalid_request", 400))
            if length > runtime.max_request_bytes:
                return None, (413, openai_error("Request exceeds TRACE-Net request-size limit.", "request_too_large", 413))
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
                payload, error = self._read()
                if error:
                    self._send(*error)
                    return
                assert payload is not None
                conv = resolve_conversation(payload)
                if not conv["latest_query"]:
                    self._send(400, openai_error("Missing query or user message.", "missing_query", 400))
                    return
                result = runtime.process(payload)
                path = self.path.split("?", 1)[0]
                if path == "/api/trace-net/ask":
                    self._send(200, result)
                    return
                if path == "/v1/chat/completions":
                    response = openai_response(result, str(payload.get("model") or MODEL_ID))
                    if bool(payload.get("stream")):
                        body = ("data: " + json.dumps(response, ensure_ascii=False) + "\n\ndata: [DONE]\n\n").encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
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
    p.add_argument("--port", type=int, default=8017)
    p.add_argument("--normal-base-url", default="http://127.0.0.1:8014")
    p.add_argument("--guided-base-url", default="http://127.0.0.1:8016")
    p.add_argument("--visual-documents-jsonl", required=True)
    p.add_argument("--engram-core-json", required=True)
    p.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    p.add_argument("--qdrant-collection", default="trace_net_ocr_v2_v3_bge_m3")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    p.add_argument("--embedding-model", default="bge-m3:latest")
    p.add_argument("--api-key", default=os.environ.get("TRACE_NET_API_KEY", "trace-net-local"))
    p.add_argument("--downstream-api-key", default=os.environ.get("TRACE_NET_API_KEY", "trace-net-local"))
    p.add_argument("--timeout-seconds", type=float, default=240.0)
    p.add_argument("--max-request-bytes", type=int, default=1_000_000)
    p.add_argument("--max-concurrency", type=int, default=4)
    p.add_argument("--require-qdrant", action="store_true")
    p.add_argument("--allow-non-strict-visual-jsonl", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    visual = VisualIndex(Path(args.visual_documents_jsonl), strict=not args.allow_non_strict_visual_jsonl)
    engram = EngramIndex(Path(args.engram_core_json))
    qdrant = QdrantGuide(
        qdrant_url=args.qdrant_url,
        collection=args.qdrant_collection,
        ollama_url=args.ollama_url,
        embedding_model=args.embedding_model,
        timeout=min(args.timeout_seconds, 120.0),
    )
    runtime = UnifiedRuntime(
        normal_base_url=args.normal_base_url,
        guided_base_url=args.guided_base_url,
        visual_index=visual,
        engram_index=engram,
        qdrant=qdrant,
        api_key=args.api_key,
        downstream_api_key=args.downstream_api_key,
        timeout=args.timeout_seconds,
        max_request_bytes=args.max_request_bytes,
        max_concurrency=args.max_concurrency,
        require_qdrant=args.require_qdrant,
    )
    health = runtime.health()
    if health["quality_status"] != "PASS":
        print(json.dumps(health, indent=2))
        raise SystemExit("TRACE-Net unified v2 refused to start because required service identities/artifacts are not healthy")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print("status=TRACE_NET_OPENWEBUI_UNIFIED_RAG_V2_READY")
    print("quality_status=PASS")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"model={MODEL_ID}")
    print(f"visual_document_count={len(visual.docs)}")
    print(f"engram_record_count={len(engram.records)}")
    print(f"qdrant_connected={health['qdrant'].get('connected')}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
