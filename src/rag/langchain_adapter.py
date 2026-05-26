"""tools/langchain_adapter.py — RAG answer generation using Ollama + retrieval pipeline."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ollama
import tools.pymupdf_bge_chroma_cli as base

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_LLM_MODEL   = "gemma3:4b"
DEFAULT_EMBED_MODEL = base.DEFAULT_MODEL
DEFAULT_COLLECTION  = base.DEFAULT_COLLECTION
DEFAULT_PERSIST_DIR = base.DEFAULT_PERSIST_DIR
DEFAULT_TOP_K       = 6
DEFAULT_FETCH_K     = 20
MAX_CONTEXT_WORDS   = 1500
DEFAULT_USE_HYDE    = False

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a precise technical assistant. Answer the user's question
using ONLY the context passages provided. If the answer is not contained in the
context, say "I don't have enough information in the provided documents to answer that."

Rules:
- Be concise and direct.
- Do not speculate beyond what the context states.
- When you use information from a specific passage, note it as [p<page>].
- If multiple passages support the answer, cite all relevant pages."""


def build_prompt(query: str, context_chunks: list[dict[str, Any]]) -> str:
    parts = []
    for i, chunk in enumerate(context_chunks, start=1):
        page_start = chunk["metadata"].get("page_start", "?")
        page_end   = chunk["metadata"].get("page_end", page_start)
        title      = chunk["metadata"].get("section_title", "")
        page_label = f"p{page_start}" if page_start == page_end else f"p{page_start}-p{page_end}"
        header     = f"[Passage {i} | {page_label} | {title}]" if title else f"[Passage {i} | {page_label}]"
        parts.append(f"{header}\n{chunk['document']}")
    context = "\n\n".join(parts)
    return f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"


# ---------------------------------------------------------------------------
# HyDE
# ---------------------------------------------------------------------------

HYDE_SYSTEM = """You are a technical document assistant.
Given a question, write a short 2-3 sentence hypothetical answer as if
it came directly from a technical manual. Use specific terminology
that would appear in the source document. Do NOT say you don't know —
always generate a plausible technical answer."""


def generate_hypothetical_answer(query: str, llm_model: str) -> str:
    try:
        response = ollama.chat(
            model=llm_model,
            messages=[
                {"role": "system", "content": HYDE_SYSTEM},
                {"role": "user", "content": f"Question: {query}\n\nWrite a short hypothetical answer:"},
            ],
        )
        hyp = response["message"]["content"].strip()
        return f"{query} {hyp}"
    except Exception:
        return query


# ---------------------------------------------------------------------------
# FIX 2: Query decomposition for comparison/synthesis questions
# ---------------------------------------------------------------------------

DECOMPOSE_SYSTEM = """Break the user's question into 2-3 specific sub-queries that
together answer the full question. Each sub-query should be self-contained and
retrievable from a document. Return one sub-query per line, no numbering, no explanation."""


def decompose_query(query: str, llm_model: str) -> list[str]:
    """FIX 2: Break a comparison or multi-doc question into sub-queries.
    e.g. 'How does 800-171 differ from 800-53?' →
         ['What does NIST 800-53 cover?', 'What does NIST 800-171 cover?']
    """
    try:
        response = ollama.chat(
            model=llm_model,
            messages=[
                {"role": "system", "content": DECOMPOSE_SYSTEM},
                {"role": "user", "content": query},
            ],
        )
        lines = response["message"]["content"].strip().splitlines()
        subs = [l.strip() for l in lines if l.strip() and len(l.strip()) > 10]
        return subs[:3]
    except Exception:
        return []


def _is_comparison_query(query: str) -> bool:
    """Detect queries that require multi-document synthesis."""
    keywords = ["differ", "difference", "compare", "versus", "vs", "relationship between",
                "how does", "what is the", "contrast", "both", "and", "or"]
    q = query.lower()
    # Multi-doc signals: mentions two NIST doc numbers or comparison language
    doc_refs = re.findall(r'800-\d+', q)
    if len(doc_refs) >= 2:
        return True
    return any(kw in q for kw in ["differ", "compare", "versus", " vs ", "relationship between"])


# ---------------------------------------------------------------------------
# FIX 4: Improved grounding verification
# ---------------------------------------------------------------------------

def verify_grounding(answer: str, context_chunks: list[dict[str, Any]]) -> bool:
    """FIX 4: Check that the answer content actually derives from retrieved chunks.

    Two-tier check:
    1. Refusal phrase detection (answer says it doesn't know)
    2. Word overlap check (answer shares significant vocabulary with context)
    """
    # Tier 1: explicit refusal
    refusal_phrases = [
        "don't have enough information",
        "not contained in",
        "cannot answer",
        "no information",
        "not mentioned",
        "i don't have",
        "not provided in",
    ]
    answer_lower = answer.lower()
    if any(p in answer_lower for p in refusal_phrases):
        return False

    # Tier 2: word overlap — answer must share meaningful vocabulary with context
    # Strip common words and check that substantive terms appear in context
    answer_words = set(re.findall(r'\b[a-z]{4,}\b', answer_lower))
    answer_words -= base.STOPWORDS

    if not answer_words:
        return True  # very short answer, give benefit of the doubt

    context_text = " ".join(c["document"].lower() for c in context_chunks)
    context_words = set(re.findall(r'\b[a-z]{4,}\b', context_text))

    overlap = len(answer_words & context_words) / len(answer_words)
    # At least 25% of substantive answer words must appear in retrieved context
    return overlap >= 0.25


# ---------------------------------------------------------------------------
# FIX 2: Merge multiple Chroma result sets (for multi-query retrieval)
# ---------------------------------------------------------------------------

def _merge_chroma_results(result_sets: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple Chroma query result sets, deduplicating by document content."""
    seen_docs: set[str] = set()
    merged_docs: list[str] = []
    merged_metas: list[dict] = []
    merged_dists: list[float] = []

    for results in result_sets:
        docs  = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            key = doc[:100]  # first 100 chars as dedup key
            if key not in seen_docs:
                seen_docs.add(key)
                merged_docs.append(doc)
                merged_metas.append(meta or {})
                merged_dists.append(dist)

    return {
        "documents": [merged_docs],
        "metadatas": [merged_metas],
        "distances": [merged_dists],
    }


# ---------------------------------------------------------------------------
# Core ask() function
# ---------------------------------------------------------------------------

def ask(
    query: str,
    *,
    llm_model: str = DEFAULT_LLM_MODEL,
    embed_model: str = DEFAULT_EMBED_MODEL,
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    top_k: int = DEFAULT_TOP_K,
    fetch_k: int = DEFAULT_FETCH_K,
    use_hyde: bool = DEFAULT_USE_HYDE,
) -> dict[str, Any]:
    t_start = time.perf_counter()

    collection = base.get_collection(persist_dir, collection_name)
    if collection.count() == 0:
        return {
            "answer": "No documents ingested yet. Run ingest first.",
            "citations": [], "chunks": [], "latency_ms": 0.0,
            "grounded": False, "hyde_used": False,
        }

    # HyDE
    hyde_used = False
    retrieval_text = query
    if use_hyde:
        hypothetical = generate_hypothetical_answer(query, llm_model)
        if hypothetical != query:
            retrieval_text = hypothetical
            hyde_used = True

    # FIX 5: Direct control ID lookup from SQLite before vector search
    # When the query mentions a specific NIST control (e.g. AC-2, IA-2, SC-8),
    # fetch those chunks directly from the DB to guarantee they appear in context
    control_ids = re.findall(r'\b[A-Z]{2}-\d+(?:\(\d+\))?\b', query.upper())
    direct_context_chunks: list[dict[str, Any]] = []

    if control_ids:
        try:
            from src.db.storage import RAGDatabase
            _db_direct = RAGDatabase("rag.db")
            for cid in control_ids:
                direct_hits = _db_direct.search_chunks_by_title(cid, level="child")
                for hit in direct_hits[:2]:  # top 2 per control ID
                    direct_context_chunks.append({
                        "document": hit["text"],
                        "metadata": {
                            "source":        hit.get("doc_id", ""),
                            "page_start":    hit.get("page_start"),
                            "page_end":      hit.get("page_end"),
                            "section_title": hit.get("title", cid),
                            "level":         hit.get("level", "child"),
                            "parent_id":     hit.get("parent_id"),
                        },
                        "distance": 0.0,   # direct lookup — distance not applicable
                        "score":    999,   # highest priority
                    })
            _db_direct.close()
        except Exception:
            pass

    # Primary vector search
    query_embedding = base.embed_texts(embed_model, [retrieval_text], kind="query")[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=max(top_k, fetch_k),
        include=["documents", "metadatas", "distances"],
    )
    all_result_sets = [results]

    # FIX 2: Multi-query for comparison/synthesis questions
    if _is_comparison_query(query):
        sub_queries = decompose_query(query, llm_model)
        for sq in sub_queries:
            try:
                sq_embedding = base.embed_texts(embed_model, [sq], kind="query")[0]
                sq_results = collection.query(
                    query_embeddings=[sq_embedding],
                    n_results=10,
                    include=["documents", "metadatas", "distances"],
                )
                all_result_sets.append(sq_results)
            except Exception:
                pass

    merged_results = _merge_chroma_results(all_result_sets)
    reranked = base.lexical_rerank(query, merged_results, top_k)

    # Parent expansion
    try:
        from src.db.storage import RAGDatabase
        _db = RAGDatabase("rag.db")
        parent_ids_to_fetch = []
        for item in reranked:
            meta = item[1] or {}
            if meta.get("level") == "child" and meta.get("parent_id"):
                parent_ids_to_fetch.append(meta["parent_id"])
        parent_rows = _db.get_parents_by_ids(parent_ids_to_fetch) if parent_ids_to_fetch else []
        parent_map = {p["id"]: p for p in parent_rows}
        _db.close()
    except Exception:
        parent_map = {}

    # Assemble context — direct lookup chunks first, then vector results
    context_chunks: list[dict[str, Any]] = []
    seen_parent_ids: set[str] = set()
    total_words = 0

    # Prepend direct control ID chunks (Fix 5)
    for dc in direct_context_chunks:
        words = len(dc["document"].split())
        if total_words + words > MAX_CONTEXT_WORDS and context_chunks:
            break
        context_chunks.append(dc)
        total_words += words

    # Then vector results with parent expansion
    for item in reranked:
        document, metadata, distance, score = item[0], item[1], item[2], item[3]
        meta = metadata or {}
        parent_id = meta.get("parent_id") if meta.get("level") == "child" else None

        if parent_id and parent_id in parent_map:
            if parent_id in seen_parent_ids:
                continue
            parent_row = parent_map[parent_id]
            document = parent_row["text"]
            meta = {
                **meta,
                "page_start":    parent_row.get("page_start"),
                "page_end":      parent_row.get("page_end"),
                "section_title": parent_row.get("title", meta.get("section_title", "")),
                "expanded_from": "child",
            }
            seen_parent_ids.add(parent_id)

        words = len(document.split())
        if total_words + words > MAX_CONTEXT_WORDS and context_chunks:
            break
        context_chunks.append({
            "document": document,
            "metadata": meta,
            "distance": distance,
            "score":    score,
        })
        total_words += words

    # Build prompt and call LLM
    prompt = build_prompt(query, context_chunks)
    response = ollama.chat(
        model=llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    )
    answer = response["message"]["content"].strip()
    latency_ms = (time.perf_counter() - t_start) * 1000.0

    # Citations
    citations = []
    seen = set()
    for chunk in context_chunks:
        page_start = chunk["metadata"].get("page_start", "?")
        page_end   = chunk["metadata"].get("page_end", page_start)
        title      = chunk["metadata"].get("section_title", "")
        source     = chunk["metadata"].get("source", "")
        key        = (source, page_start, page_end)
        if key not in seen:
            seen.add(key)
            citations.append({
                "source":     source,
                "page_start": page_start,
                "page_end":   page_end,
                "title":      title,
                "distance":   round(chunk["distance"], 4) if chunk["distance"] else None,
            })

    # FIX 4: Improved grounding check
    grounded = verify_grounding(answer, context_chunks)

    return {
        "answer":     answer,
        "citations":  citations,
        "chunks":     context_chunks,
        "latency_ms": round(latency_ms, 1),
        "grounded":   grounded,
        "hyde_used":  hyde_used,
    }


# ---------------------------------------------------------------------------
# Test suite (unchanged)
# ---------------------------------------------------------------------------

TEST_CASES = [
    {"source_doc": "test-2", "query": "What are sponsons?",
     "expected_terms": ["sponson", "winglike", "hull", "stabilize"], "difficulty": "easy"},
    {"source_doc": "test-2", "query": "What is the step on a float?",
     "expected_terms": ["step", "water drag", "takeoff", "longitudinal"], "difficulty": "easy"},
    {"source_doc": "test-2", "query": "What are water rudders?",
     "expected_terms": ["water rudder", "retract", "maneuvering", "cables"], "difficulty": "easy"},
    {"source_doc": "test-2", "query": "What is hydrodynamic lift?",
     "expected_terms": ["hydrodynamic", "upward force", "motion", "floats"], "difficulty": "easy"},
    {"source_doc": "test-2", "query": "How does a seaplane slow down on water?",
     "expected_terms": ["brakes", "wind", "current", "motion"], "difficulty": "medium"},
    {"source_doc": "test-2", "query": "What makes glassy water dangerous for landing?",
     "expected_terms": ["glassy", "altitude", "illusion", "featureless"], "difficulty": "medium"},
    {"source_doc": "test-2", "query": "How do you know which side of a buoy to pass?",
     "expected_terms": ["red", "right", "returning", "channel", "nun", "can"], "difficulty": "medium"},
    {"source_doc": "test-2", "query": "What causes a seaplane to weathervane?",
     "expected_terms": ["weathervane", "wind", "yaw", "nose"], "difficulty": "medium"},
    {"source_doc": "test-2", "query": "What are the differences between flying boats and floatplanes?",
     "expected_terms": ["flying boat", "floatplane", "hull", "fuselage", "pontoon"], "difficulty": "hard"},
    {"source_doc": "test-2", "query": "What regulations apply when a seaplane is on water?",
     "expected_terms": ["USCG", "vessel", "91.115", "right-of-way"], "difficulty": "hard"},
    {"source_doc": "test-2", "query": "How does buoyancy work for seaplane floats?",
     "expected_terms": ["buoyancy", "displace", "weight", "fresh water"], "difficulty": "hard"},
    {"source_doc": "test-2", "query": "What is the engine horsepower requirement for a seaplane?",
     "expected_terms": [], "difficulty": "adversarial", "expect_grounded": False},
    {"source_doc": "test-2", "query": "How do you file a flight plan for a seaplane?",
     "expected_terms": [], "difficulty": "adversarial", "expect_grounded": False},
    {"source_doc": "test-3", "query": "What is Class B airspace?",
     "expected_terms": ["class b", "10,000", "msl", "atc"], "difficulty": "easy"},
    {"source_doc": "test-3", "query": "What does NOTAM stand for?",
     "expected_terms": ["notice", "airmen", "time-critical"], "difficulty": "easy"},
    {"source_doc": "test-3", "query": "What frequency is used at a non-towered airport with no UNICOM or FSS?",
     "expected_terms": ["multicom", "122.9", "non-towered"], "difficulty": "easy"},
    {"source_doc": "test-3", "query": "What is density altitude?",
     "expected_terms": ["density altitude", "standard", "air density"], "difficulty": "easy"},
    {"source_doc": "test-3", "query": "What are the symptoms of hyperventilation?",
     "expected_terms": ["hyperventilation", "lightheaded", "tingling", "visual"], "difficulty": "medium"},
    {"source_doc": "test-3", "query": "Why does humidity reduce drone performance?",
     "expected_terms": ["humidity", "density", "moist", "less dense"], "difficulty": "medium"},
    {"source_doc": "test-3", "query": "What does the IMSAFE checklist cover?",
     "expected_terms": ["illness", "medication", "stress", "alcohol", "fatigue", "emotion"], "difficulty": "medium"},
    {"source_doc": "test-3", "query": "How does excess weight affect a small unmanned aircraft?",
     "expected_terms": ["weight", "longer", "stalling", "takeoff", "landing"], "difficulty": "medium"},
    {"source_doc": "test-3", "query": "What are the five hazardous attitudes a pilot can have?",
     "expected_terms": ["anti-authority", "impulsivity", "invulnerability", "macho", "resignation"], "difficulty": "hard"},
    {"source_doc": "test-3", "query": "Describe the three stages of a thunderstorm's life cycle.",
     "expected_terms": ["cumulus", "mature", "dissipating", "updraft", "downdraft"], "difficulty": "hard"},
    {"source_doc": "test-3", "query": "What is the difference between a restricted area and a prohibited area?",
     "expected_terms": ["prohibited", "restricted", "hazardous", "authorization"], "difficulty": "hard"},
    {"source_doc": "test-3", "query": "What is the maximum flight range of a DJI Mavic 3 in kilometers?",
     "expected_terms": [], "difficulty": "adversarial", "expect_grounded": False},
    {"source_doc": "test-3", "query": "How do I register my drone with EASA in the European Union?",
     "expected_terms": [], "difficulty": "adversarial", "expect_grounded": False},
]


def grade_result(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    answer_lower = result["answer"].lower()
    expected_terms = case.get("expected_terms", [])
    expect_grounded = case.get("expect_grounded", True)
    term_hits = [t for t in expected_terms if t.lower() in answer_lower]
    term_score = len(term_hits) / len(expected_terms) if expected_terms else None
    if not expect_grounded:
        passed = not result["grounded"]
    else:
        passed = result["grounded"] and (term_score is None or term_score >= 0.5)
    return {
        "query": case["query"], "difficulty": case["difficulty"], "passed": passed,
        "grounded": result["grounded"],
        "term_score": round(term_score, 2) if term_score is not None else None,
        "term_hits": term_hits, "latency_ms": result["latency_ms"],
        "answer": result["answer"], "citations": result["citations"],
    }


def run_tests(*, llm_model: str = DEFAULT_LLM_MODEL, embed_model: str = DEFAULT_EMBED_MODEL,
              persist_dir: Path = DEFAULT_PERSIST_DIR, collection_name: str = DEFAULT_COLLECTION,
              top_k: int = DEFAULT_TOP_K, out_path: Path | None = None, show_answers: bool = True) -> None:
    grades = []
    for i, case in enumerate(TEST_CASES, start=1):
        print(f"[{i:02d}/{len(TEST_CASES)}] {case['difficulty'].upper():12s} {case['query']}")
        result = ask(case["query"], llm_model=llm_model, embed_model=embed_model,
                     persist_dir=persist_dir, collection_name=collection_name, top_k=top_k)
        grade = grade_result(case, result)
        grades.append(grade)
        status = "PASS" if grade["passed"] else "FAIL"
        term_info = f"terms={grade['term_score']}" if grade["term_score"] is not None else "adversarial"
        print(f"         {status} | grounded={grade['grounded']} | {term_info} | {grade['latency_ms']}ms")
        if show_answers:
            print(f"         Answer: {grade['answer'][:200].replace(chr(10), ' ')}...")
            if grade["citations"]:
                pages = ", ".join(
                    f"p{c['page_start']}" if c["page_start"] == c["page_end"]
                    else f"p{c['page_start']}-p{c['page_end']}"
                    for c in grade["citations"]
                )
                print(f"         Sources: {pages}")
        print()
    total = len(grades)
    passed = sum(1 for g in grades if g["passed"])
    by_diff: dict[str, list] = {}
    for g in grades:
        by_diff.setdefault(g["difficulty"], []).append(g["passed"])
    avg_latency = sum(g["latency_ms"] for g in grades) / total
    print("=" * 60)
    print(f"RESULTS: {passed}/{total} passed  |  avg latency {avg_latency:.0f}ms")
    for diff, results in sorted(by_diff.items()):
        p = sum(results)
        print(f"  {diff:12s}: {p}/{len(results)}")
    print("=" * 60)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps({"summary": {"passed": passed, "total": total}, "cases": grades}, indent=2),
            encoding="utf-8",
        )
        print(f"Saved to {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG answer generation with Ollama.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("--query", required=True)
    ask_parser.add_argument("--llm-model",   default=DEFAULT_LLM_MODEL)
    ask_parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    ask_parser.add_argument("--persist-dir", type=Path, default=DEFAULT_PERSIST_DIR)
    ask_parser.add_argument("--collection",  default=DEFAULT_COLLECTION)
    ask_parser.add_argument("--top-k",       type=int, default=DEFAULT_TOP_K)
    ask_parser.add_argument("--show-chunks", action="store_true")
    test_parser = subparsers.add_parser("test")
    test_parser.add_argument("--llm-model",   default=DEFAULT_LLM_MODEL)
    test_parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    test_parser.add_argument("--persist-dir", type=Path, default=DEFAULT_PERSIST_DIR)
    test_parser.add_argument("--collection",  default=DEFAULT_COLLECTION)
    test_parser.add_argument("--top-k",       type=int, default=DEFAULT_TOP_K)
    test_parser.add_argument("--out",         type=Path)
    test_parser.add_argument("--no-answers",  action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "ask":
        result = ask(args.query, llm_model=args.llm_model, embed_model=args.embed_model,
                     persist_dir=args.persist_dir, collection_name=args.collection, top_k=args.top_k)
        print(f"\nAnswer:\n{result['answer']}\n")
        if result["citations"]:
            print("Sources:")
            for c in result["citations"]:
                page = f"p{c['page_start']}" if c["page_start"] == c["page_end"] else f"p{c['page_start']}-p{c['page_end']}"
                print(f"  {page} — {c['title']}  (distance={c['distance']})")
        print(f"\nLatency: {result['latency_ms']}ms | Grounded: {result['grounded']}")
        if args.show_chunks:
            print("\n--- Retrieved chunks ---")
            for i, chunk in enumerate(result["chunks"], start=1):
                meta = chunk["metadata"]
                print(f"[{i}] p{meta.get('page_start')} dist={chunk['distance']:.4f}")
                print(f"    {chunk['document'][:200].replace(chr(10), ' ')}...")
    elif args.command == "test":
        run_tests(llm_model=args.llm_model, embed_model=args.embed_model,
                  persist_dir=args.persist_dir, collection_name=args.collection,
                  top_k=args.top_k, out_path=args.out, show_answers=not args.no_answers)


if __name__ == "__main__":
    main()