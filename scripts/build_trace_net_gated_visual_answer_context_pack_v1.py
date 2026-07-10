#!/usr/bin/env python3
"""TRACE-Net gated visual answer context pack v1.

Consumes gated visual retrieval documents and builds retrieval context packs for
visual/image-route questions.

This is the bridge from:
  gated_visual_retrieval_adapter_v1_1/search-ready docs
to:
  downstream answer/retrieval context construction.

Safety contract:
- Read-only.
- Does not call OCR/LLM/Ollama.
- Does not write Postgres/Qdrant/OpenSearch.
- Does not mutate source-truth artifacts.
- Does not grant answer permission.
- Visual observations remain candidate/retrieval guidance, not proof by itself.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MODULE_NAME = "trace_net_gated_visual_answer_context_pack_v1"

DEFAULT_AUTO_QUERIES = [
    "seat assembly diagram callouts",
    "figure passenger seat assembly parts",
    "visual diagram part numbers nomenclature",
    "technical drawing callout item reference",
    "exploded view assembly figure",
]


TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-./]*")
STOP_TOKENS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "with", "without", "find", "show", "give", "what", "which", "page",
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
        if len(t) <= 1:
            continue
        if t in STOP_TOKENS:
            continue
        out.append(t)
    return out


def compact(value: Any, limit: int = 900) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()[:limit]
    try:
        return re.sub(r"\s+", " ", json.dumps(value, ensure_ascii=False, sort_keys=True)).strip()[:limit]
    except Exception:
        return str(value)[:limit]


def listify(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        vals = value
    else:
        vals = [value]
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
        compact(doc.get("search_text"), 6000),
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


def score_doc(query: str, doc: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    q_tokens = tokenize(query)
    d_text = doc_text(doc)
    d_tokens = tokenize(d_text)
    d_set = set(d_tokens)
    q_set = set(q_tokens)

    overlap = sorted(q_set & d_set)
    overlap_score = len(overlap)

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
    ):
        if phrase in q_lower and phrase in lower_text:
            phrase_hits.append(phrase)

    # Critical gate: do not let route/subtype bonuses create a hit by
    # themselves. The query must share at least one meaningful token/phrase or
    # exact identifier with the document.
    has_real_match = bool(overlap or exact_part_hits or phrase_hits)
    if not has_real_match:
        diagnostics = {
            "score": 0.0,
            "token_overlap_count": 0,
            "token_overlap": [],
            "exact_part_hits": [],
            "phrase_hits": [],
            "route_bonus": 0.0,
            "subtype_bonus": 0.0,
            "rejected_reason": "no_real_query_document_match",
        }
        return 0.0, diagnostics

    route_bonus = 1.5 if doc.get("visual_route") == "image_visual" else 1.0
    subtype_bonus = 1.0 if "diagram" in str(doc.get("visual_subtype", "")).lower() else 0.5
    exact_bonus = 8.0 * len(exact_part_hits)
    phrase_bonus = 2.0 * len(phrase_hits)

    norm = math.log(max(len(d_set), 20), 10)
    score = (overlap_score / norm) + exact_bonus + phrase_bonus + route_bonus + subtype_bonus

    diagnostics = {
        "score": round(score, 4),
        "token_overlap_count": len(overlap),
        "token_overlap": overlap[:30],
        "exact_part_hits": exact_part_hits,
        "phrase_hits": phrase_hits,
        "route_bonus": route_bonus,
        "subtype_bonus": subtype_bonus,
    }
    return score, diagnostics


def make_citation(doc: Dict[str, Any], rank: int, diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    identifiers = doc.get("identifiers") if isinstance(doc.get("identifiers"), dict) else {}
    summaries = listify(doc.get("visual_summaries"))
    return {
        "rank": rank,
        "page_id": doc.get("page_id", ""),
        "document_id": doc.get("document_id", ""),
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
        "retrieval_guidance": {
            "visual_observation_is_candidate_only": True,
            "requires_source_trace_for_final_claims": True,
            "do_not_treat_as_proof_by_itself": True,
        },
    }


def build_context_pack(query: str, docs: Sequence[Dict[str, Any]], top_k: int) -> Dict[str, Any]:
    scored: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []
    for doc in docs:
        if not doc.get("search_ready"):
            continue
        if doc.get("review_only"):
            continue
        score, diagnostics = score_doc(query, doc)
        if score > 0:
            scored.append((score, doc, diagnostics))

    scored.sort(key=lambda x: (-x[0], str(x[1].get("page_id", ""))))
    top = scored[:top_k]
    citations = [
        make_citation(doc, rank=i, diagnostics=diag)
        for i, (_, doc, diag) in enumerate(top, start=1)
    ]

    return {
        "module": MODULE_NAME,
        "query": query,
        "context_pack_status": "visual_context_candidates_found" if citations else "no_visual_context_candidates_found",
        "top_k": top_k,
        "candidate_count": len(scored),
        "citation_count": len(citations),
        "page_count": len({c.get("page_id") for c in citations if c.get("page_id")}),
        "citations": citations,
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
    queries: List[str] = []
    for q in args.query or []:
        q = q.strip()
        if q:
            queries.append(q)
    if args.query_file:
        path = Path(args.query_file)
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    queries.append(line)
    if args.auto_queries:
        queries.extend(DEFAULT_AUTO_QUERIES)
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
    docs_path = Path(args.gated_visual_retrieval_documents_jsonl)
    review_path = Path(args.review_only_documents_jsonl) if args.review_only_documents_jsonl else None
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    docs = list(read_jsonl(docs_path) or [])
    review_docs = list(read_jsonl(review_path) or []) if review_path else []
    queries = parse_queries(args)

    packs = [build_context_pack(q, docs, args.top_k) for q in queries]

    context_pack_path = output_dir / "trace_net_gated_visual_answer_context_pack_v1.jsonl"
    report_path = output_dir / "trace_net_gated_visual_answer_context_pack_v1_report.txt"
    summary_path = output_dir / "summary.json"

    write_jsonl(context_pack_path, packs)

    successful = [p for p in packs if p.get("citation_count", 0) > 0]
    total_citations = sum(int(p.get("citation_count", 0)) for p in packs)
    cited_pages = sorted({c.get("page_id") for p in packs for c in p.get("citations", []) if c.get("page_id")})
    route_counts = Counter(str(c.get("visual_route")) for p in packs for c in p.get("citations", []))
    subtype_counts = Counter(str(c.get("visual_subtype")) for p in packs for c in p.get("citations", []))

    safety_counts = {
        "final_answer_allowed_true_count": sum(1 for p in packs if bool_nested(p, "final_answer_allowed")),
        "answer_permission_count": sum(1 for p in packs if bool_nested(p, "answer_permission")),
        "can_answer_directly_count": sum(1 for p in packs if bool_nested(p, "can_answer_directly")),
        "can_prove_claims_count": sum(1 for p in packs if bool_nested(p, "can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for p in packs if bool_nested(p, "source_truth_mutation_allowed")),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "ollama_call_attempt_count": 0,
        "llm_call_attempt_count": 0,
    }

    failures: List[str] = []
    if len(docs) < args.min_retrieval_documents:
        failures.append(f"retrieval_document_count:{len(docs)} < {args.min_retrieval_documents}")
    if len(queries) < args.min_query_count:
        failures.append(f"query_count:{len(queries)} < {args.min_query_count}")
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
        "status": "TRACE_NET_GATED_VISUAL_ANSWER_CONTEXT_PACK_V1_BUILT",
        "quality_status": "PASS" if not failures else "FAIL",
        "quality_failures": failures,
        "inputs": {
            "gated_visual_retrieval_documents_jsonl": str(docs_path),
            "review_only_documents_jsonl": str(review_path) if review_path else "",
            "top_k": args.top_k,
            "auto_queries": bool(args.auto_queries),
        },
        "outputs": {
            "context_pack_jsonl": str(context_pack_path),
            "summary": str(summary_path),
            "report": str(report_path),
        },
        "summary": {
            "retrieval_document_count": len(docs),
            "review_only_document_count": len(review_docs),
            "query_count": len(queries),
            "successful_query_count": len(successful),
            "total_citation_count": total_citations,
            "cited_page_count": len(cited_pages),
            "visual_route_counts": dict(sorted(route_counts.items())),
            "visual_subtype_counts": dict(sorted(subtype_counts.items())),
            "review_only_docs_used_for_context_count": 0,
            **safety_counts,
        },
        "safety_contract": {
            "read_only_context_pack_builder": True,
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
        "TRACE-Net gated visual answer context pack v1",
        f"quality_status: {summary['quality_status']}",
        f"retrieval documents: {len(docs)}",
        f"review-only documents available but not used: {len(review_docs)}",
        "",
    ]
    for pack in packs:
        report_lines.append(f"QUERY: {pack['query']}")
        report_lines.append(f"  status: {pack['context_pack_status']}")
        report_lines.append(f"  citations: {pack['citation_count']}")
        for c in pack.get("citations", [])[:5]:
            report_lines.append(
                "  - "
                + str(c.get("page_id"))
                + f" score={c.get('score_diagnostics', {}).get('score')}"
                + f" route={c.get('visual_route')}"
                + f" subtype={c.get('visual_subtype')}"
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
    p.add_argument("--gated-visual-retrieval-documents-jsonl", required=True)
    p.add_argument("--review-only-documents-jsonl", default="")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--query", action="append", default=[])
    p.add_argument("--query-file", default="")
    p.add_argument("--auto-queries", action="store_true")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--min-retrieval-documents", type=int, default=1)
    p.add_argument("--min-query-count", type=int, default=1)
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
