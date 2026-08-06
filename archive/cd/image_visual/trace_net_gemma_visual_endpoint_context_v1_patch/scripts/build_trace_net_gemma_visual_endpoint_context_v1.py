#!/usr/bin/env python3
"""TRACE-Net Gemma visual endpoint context v1.

Builds router/endpoint-ready visual context payloads from cleaned Gemma visual
retrieval documents.

Input:
  confirmed_image_gemma_visual_retrieval_cleaner_v1_full/
    trace_net_confirmed_image_gemma_visual_clean_retrieval_documents_v1.jsonl

This replaces the older gated_visual_retrieval_adapter source for the visual
route, but keeps the same answer contract:
- visual context is retrieval guidance only
- answer_permission=false
- final_answer_allowed=false
- no source-truth mutation
- no Postgres/Qdrant/OpenSearch writes
- no Ollama/LLM calls
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MODULE_NAME = "trace_net_gemma_visual_endpoint_context_v1"
STATUS_BUILT = "TRACE_NET_GEMMA_VISUAL_ENDPOINT_CONTEXT_V1_BUILT"

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
    "assembly diagram",
    "seat assembly diagram",
    "passenger seat assembly diagram",
    "diagram page",
    "visual page",
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
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


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


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in records)
        + ("\n" if records else ""),
        encoding="utf-8",
    )


def listify(value: Any) -> List[str]:
    if not value:
        return []
    vals = value if isinstance(value, list) else [value]
    out: List[str] = []
    seen = set()
    for v in vals:
        s = compact(v, 500)
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def tokenize(text: Any) -> List[str]:
    if text is None:
        return []
    if not isinstance(text, str):
        text = compact(text, 20000)
    out: List[str] = []
    for token in TOKEN_RE.findall(text):
        t = token.lower()
        if len(t) <= 1:
            continue
        if t in STOP_TOKENS:
            continue
        out.append(t)
    return out


def has_bad_pattern(value: Any, patterns: Sequence[str]) -> bool:
    low = compact(value, 20000).lower()
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
    pieces = [
        compact(doc.get("page_id"), 100),
        compact(doc.get("document_id"), 200),
        compact(doc.get("route_name"), 100),
        compact(doc.get("retrieval_text"), 12000),
        compact(card.get("normalized_visual_page_type"), 300),
        compact(card.get("normalized_subject"), 700),
        " ".join(listify(card.get("figure_refs"))),
        " ".join(listify(card.get("part_numbers"))),
        " ".join(listify(card.get("visible_callouts"))),
        " ".join(listify(card.get("retrieval_keywords"))),
    ]
    return "\n".join(p for p in pieces if p)


def part_like_tokens(tokens: Sequence[str]) -> List[str]:
    out: List[str] = []
    for t in tokens:
        if re.search(r"\d{2,}[-./]\d{2,}", t) or re.fullmatch(r"\d{3,4}[a-z]?", t):
            out.append(t)
    return out


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
    exact_part_hits: List[str] = []
    lower_text = d_text.lower()
    for p in q_parts:
        if p.lower() in lower_text:
            exact_part_hits.append(p)

    phrase_hits: List[str] = []
    q_lower = query.lower()
    lower_doc = d_text.lower()
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
        if phrase in q_lower and phrase in lower_doc:
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
    exact_bonus = 10.0 * len(exact_part_hits)
    phrase_bonus = 3.0 * len(phrase_hits)
    score = (len(overlap) / norm) + exact_bonus + phrase_bonus + 2.0

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


def build_payload_for_query(
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
            ok, _ = validate_clean_doc(doc)
            if not ok:
                continue
            score, diagnostics = score_doc(query, doc)
            if score >= min_score:
                scored.append((score, doc, diagnostics))

    scored.sort(key=lambda item: (-item[0], str(item[1].get("page_id", ""))))
    citations = [
        make_citation(doc, rank=i, diagnostics=diag)
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


def parse_queries(args: argparse.Namespace) -> List[str]:
    queries = [q.strip() for q in (args.query or []) if q and q.strip()]
    if args.query_file:
        path = Path(args.query_file)
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    queries.append(line)
    out: List[str] = []
    for q in queries:
        if q not in out:
            out.append(q)
    return out


def bool_nested(record: Dict[str, Any], key: str) -> bool:
    for group in ("answer_contract", "safety_contract"):
        obj = record.get(group)
        if isinstance(obj, dict) and isinstance(obj.get(key), bool):
            return bool(obj.get(key))
    value = record.get(key)
    return bool(value) if isinstance(value, bool) else False


def build(args: argparse.Namespace) -> Dict[str, Any]:
    docs_path = Path(args.gemma_visual_retrieval_documents_jsonl)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_docs = list(read_jsonl(docs_path) or [])
    rejected: List[Dict[str, Any]] = []
    docs: List[Dict[str, Any]] = []
    for doc in all_docs:
        ok, failures = validate_clean_doc(doc)
        if ok:
            docs.append(doc)
        else:
            rejected.append({"page_id": doc.get("page_id"), "document_id": doc.get("document_id"), "failures": failures})

    queries = parse_queries(args)
    payloads = [
        build_payload_for_query(q, docs, top_k=args.top_k, min_score=args.min_score)
        for q in queries
    ]

    payload_path = output_dir / "trace_net_gemma_visual_endpoint_context_v1.jsonl"
    rejected_path = output_dir / "trace_net_gemma_visual_endpoint_context_v1_rejected_docs.jsonl"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "trace_net_gemma_visual_endpoint_context_v1_report.txt"

    write_jsonl(payload_path, payloads)
    write_jsonl(rejected_path, rejected)

    triggered = [p for p in payloads if p.get("route_triggered")]
    successful = [p for p in payloads if p.get("citation_count", 0) > 0]
    total_citations = sum(int(p.get("citation_count", 0)) for p in payloads)
    cited_pages = sorted({c.get("page_id") for p in payloads for c in p.get("citations", []) if c.get("page_id")})
    route_counts = Counter(str(c.get("route")) for p in payloads for c in p.get("citations", []))

    safety_counts = {
        "final_answer_allowed_true_count": sum(1 for p in payloads if bool_nested(p, "final_answer_allowed")),
        "answer_permission_count": sum(1 for p in payloads if bool_nested(p, "answer_permission")),
        "can_answer_directly_count": sum(1 for p in payloads if bool_nested(p, "can_answer_directly")),
        "can_prove_claims_count": sum(1 for p in payloads if bool_nested(p, "can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for p in payloads if bool_nested(p, "source_truth_mutation_allowed")),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "ollama_call_attempt_count": 0,
        "llm_call_attempt_count": 0,
    }

    failures: List[str] = []
    if len(docs) < args.min_retrieval_documents:
        failures.append(f"clean_retrieval_document_count:{len(docs)} < {args.min_retrieval_documents}")
    if rejected:
        failures.append(f"rejected_document_count:{len(rejected)} != 0")
    if len(queries) < args.min_query_count:
        failures.append(f"query_count:{len(queries)} < {args.min_query_count}")
    if len(triggered) < args.min_triggered_query_count:
        failures.append(f"triggered_query_count:{len(triggered)} < {args.min_triggered_query_count}")
    if len(successful) < args.min_successful_query_count:
        failures.append(f"successful_query_count:{len(successful)} < {args.min_successful_query_count}")
    if total_citations < args.min_total_citations:
        failures.append(f"total_citation_count:{total_citations} < {args.min_total_citations}")
    if len(cited_pages) < args.min_cited_pages:
        failures.append(f"cited_page_count:{len(cited_pages)} < {args.min_cited_pages}")
    for key, value in safety_counts.items():
        if value != 0:
            failures.append(f"{key}:{value} != 0")

    summary = {
        "module": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": "PASS" if not failures else "FAIL",
        "quality_failures": failures,
        "inputs": {
            "gemma_visual_retrieval_documents_jsonl": str(docs_path),
            "top_k": args.top_k,
            "min_score": args.min_score,
        },
        "outputs": {
            "endpoint_context_jsonl": str(payload_path),
            "rejected_docs_jsonl": str(rejected_path),
            "summary": str(summary_path),
            "report": str(report_path),
        },
        "summary": {
            "source_retrieval_document_count": len(all_docs),
            "clean_retrieval_document_count": len(docs),
            "rejected_document_count": len(rejected),
            "query_count": len(queries),
            "triggered_query_count": len(triggered),
            "successful_query_count": len(successful),
            "total_citation_count": total_citations,
            "cited_page_count": len(cited_pages),
            "route_counts": dict(sorted(route_counts.items())),
            **safety_counts,
        },
        "endpoint_contract": {
            "route_name": "gemma_confirmed_image_visual",
            "context_payload_type": "trace_net_route_context",
            "uses_clean_gemma_visual_retrieval_documents": True,
            "final_answer_allowed": False,
            "answer_permission": False,
        },
        "safety_contract": {
            "read_only_endpoint_context_adapter": True,
            "does_not_call_ollama": True,
            "does_not_call_llm": True,
            "does_not_write_postgres": True,
            "does_not_write_qdrant": True,
            "does_not_write_opensearch": True,
            "does_not_mutate_source_truth": True,
            "final_answer_allowed": False,
            "answer_permission": False,
        },
    }

    write_json(summary_path, summary)

    report_lines = [
        "TRACE-Net Gemma visual endpoint context v1",
        f"quality_status: {summary['quality_status']}",
        f"clean retrieval documents: {len(docs)}",
        f"rejected documents: {len(rejected)}",
        "",
    ]
    for payload in payloads:
        report_lines.append(f"QUERY: {payload['query']}")
        report_lines.append(f"  triggered: {payload['route_triggered']} triggers={payload['route_triggers']}")
        report_lines.append(f"  status: {payload['context_pack_status']}")
        report_lines.append(f"  citations: {payload['citation_count']}")
        for c in payload.get("citations", [])[:5]:
            report_lines.append(
                "  - "
                + str(c.get("page_id"))
                + f" score={c.get('score_diagnostics', {}).get('score')}"
                + f" subject={c.get('subject')[:80]}"
            )
        report_lines.append("")
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    for key, value in summary["summary"].items():
        if isinstance(value, dict):
            print(f"{key}=" + json.dumps(value, sort_keys=True))
        else:
            print(f"{key}={value}")
    print("output_dir=" + str(output_dir))
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gemma-visual-retrieval-documents-jsonl", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--query", action="append", default=[])
    p.add_argument("--query-file", default="")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--min-score", type=float, default=0.001)
    p.add_argument("--min-retrieval-documents", type=int, default=1)
    p.add_argument("--min-query-count", type=int, default=1)
    p.add_argument("--min-triggered-query-count", type=int, default=1)
    p.add_argument("--min-successful-query-count", type=int, default=1)
    p.add_argument("--min-total-citations", type=int, default=1)
    p.add_argument("--min-cited-pages", type=int, default=1)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = build(args)
    return 0 if summary.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
