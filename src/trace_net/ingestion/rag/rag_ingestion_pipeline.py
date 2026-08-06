#!/usr/bin/env python3
"""Benchmark-oriented copy of the PyMuPDF + BGE + Chroma CLI with OCR diagnostics."""

from __future__ import annotations

import argparse
import json
import time
import io
import math
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import pymupdf_bge_chroma_cli as base


DEFAULT_OCR_DEBUG_DIR  = Path("ocr_debug")
DEFAULT_CHUNK_DEBUG_DIR = Path("chunk_debug")
DEFAULT_DB_PATH        = Path("rag.db")


@dataclass(frozen=True)
class PageRecord:
    page: int
    text: str
    ocr_used: bool
    native_text: str
    ocr_text: str
    ocr_quality: float
    ocr_confidence: float


@dataclass(frozen=True)
class RetrievalCase:
    query: str
    answer_terms: tuple[str, ...]
    answer_phrases: tuple[str, ...] = ()
    expected_pages: tuple[int, ...] = ()


@dataclass
class RetrievalResult:
    query: str
    top_k: list[dict[str, Any]]
    hit_at_k: bool
    reciprocal_rank: float
    ndcg_at_k: float
    latency_ms: float
    hallucination_risk: float
    grounded: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark copy with OCR diagnostics.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--pdf", type=Path, required=True)
    ingest_parser.add_argument("--persist-dir", type=Path, default=base.DEFAULT_PERSIST_DIR)
    ingest_parser.add_argument("--collection", default=base.DEFAULT_COLLECTION)
    ingest_parser.add_argument("--model", default=base.DEFAULT_MODEL)
    ingest_parser.add_argument("--chunk-words", type=int, default=base.DEFAULT_CHUNK_WORDS)
    ingest_parser.add_argument("--overlap", type=int, default=base.DEFAULT_CHUNK_OVERLAP)
    ingest_parser.add_argument("--ocr-debug-dir", type=Path, default=DEFAULT_OCR_DEBUG_DIR)
    ingest_parser.add_argument("--chunk-debug-dir", type=Path, default=DEFAULT_CHUNK_DEBUG_DIR)
    ingest_parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    ingest_parser.add_argument("--ocr-debug", dest="ocr_debug", action="store_true", default=True)
    ingest_parser.add_argument("--no-ocr-debug", dest="ocr_debug", action="store_false")
    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--query", required=True)
    query_parser.add_argument("--persist-dir", type=Path, default=base.DEFAULT_PERSIST_DIR)
    query_parser.add_argument("--collection", default=base.DEFAULT_COLLECTION)
    query_parser.add_argument("--model", default=base.DEFAULT_MODEL)
    query_parser.add_argument("--top-k", type=int, default=5)
    query_parser.add_argument("--rerank", action="store_true")
    query_parser.add_argument("--rerank-model", default="bge-reranker-large")
    benchmark_parser = subparsers.add_parser("benchmark")
    benchmark_parser.add_argument("--persist-dir", type=Path, default=base.DEFAULT_PERSIST_DIR)
    benchmark_parser.add_argument("--collection", default=base.DEFAULT_COLLECTION)
    benchmark_parser.add_argument("--model", default=base.DEFAULT_MODEL)
    benchmark_parser.add_argument("--top-k", type=int, default=5)
    benchmark_parser.add_argument("--fetch-k", type=int, default=base.DEFAULT_FETCH_K)
    benchmark_parser.add_argument("--rerank", action="store_true")
    benchmark_parser.add_argument("--rerank-model", default="bge-reranker-large")
    benchmark_parser.add_argument("--out", type=Path)
    benchmark_parser.add_argument("--show-results", action="store_true")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    return parser.parse_args()


def resolve_pdf_path(pdf_path: Path) -> Path:
    return base.resolve_pdf_path(pdf_path)


def ocr_quality_score(text: str) -> float:
    cleaned = base.normalize_text(text)
    if not cleaned:
        return 0.0
    words = re.findall(r"\b[\w'-]+\b", cleaned)
    if not words:
        return 0.0
    alpha_words = sum(1 for word in words if re.search(r"[A-Za-z]", word))
    noise_chars = len(re.findall(r"[^A-Za-z0-9\s.,;:()\-/'\"]", cleaned))
    repeated_chars = len(re.findall(r"(.)\1{3,}", cleaned))
    word_ratio = alpha_words / max(len(words), 1)
    density = min(len(words) / 120.0, 1.0)
    noise_penalty = min(noise_chars / max(len(cleaned), 1) * 5.0, 0.30)
    repeat_penalty = min(repeated_chars * 0.05, 0.20)
    score = (word_ratio * 0.65) + (density * 0.25) - noise_penalty - repeat_penalty
    return max(0.0, min(1.0, score))


# FIX B: Stronger reference / appendix / TOC page filter
# Catches NIST 800-53 Appendix C control enhancement tables, references
# sections, tables of contents, and other low-prose pages.
def is_reference_page(text: str) -> bool:
    """Detect pages that are references, appendices, or dense index tables.

    Filtering these prevents the retriever from returning useless appendix
    chunks (e.g. SA-15(1), SA-15(2) listed in a control enhancement table).
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return True

    total = len(lines)
    if total < 5:
        return False  # too short to judge

    # Citation density (references section, bibliography)
    citation_lines = sum(1 for l in lines if
        re.search(r'\[SP\s*800-|\bRFC\s*\d+\b|doi\.org|https?://|NIST\s+SP\s+\d+', l))
    if citation_lines / total > 0.30:
        return True

    # Short lines dominate (index, code-only tables)
    short_lines = sum(1 for l in lines if len(l.split()) <= 3)
    if total > 15 and short_lines / total > 0.65:
        return True

    # Pipe-separated table content
    pipe_lines = sum(1 for l in lines if l.count("|") >= 2 or l.count("\t") >= 2)
    if total > 10 and pipe_lines / total > 0.40:
        return True

    # NEW: NIST control enhancement tables — lines starting with a control
    # ID pattern like "SA-15(1) QUALITY METRICS" or "AC-6(10) PROHIBIT NON-PRIVILEGED USERS"
    control_id_line_re = re.compile(r'^[A-Z]{2}-\d+(?:\s*\(\d+\))?\b')
    control_id_lines = sum(1 for l in lines if control_id_line_re.match(l))
    if total > 8 and control_id_lines / total > 0.40:
        return True

    # NEW: Tables of Contents — lines ending in dot-leader + page number
    # e.g. "AC-2 ACCOUNT MANAGEMENT ................. 45"
    toc_lines = sum(1 for l in lines if re.search(r'\.{3,}\s*\d+\s*$', l))
    if total > 10 and toc_lines / total > 0.30:
        return True

    # NEW: Mostly-numeric appendix mapping pages — lines that are
    # mostly numbers/codes with little prose
    short_code_lines = sum(1 for l in lines if
        len(l) < 40 and re.search(r'\b\d+\b', l) and not re.search(r'\b(the|and|of|to|in)\b', l.lower()))
    if total > 15 and short_code_lines / total > 0.50:
        return True

    return False


def merge_page_text(native_text: str, ocr_text: str,
                    ocr_confidence: float = 0.0, ocr_quality: float = 0.0) -> str:
    native_clean = base.normalize_text(native_text)
    ocr_clean = base.normalize_text(ocr_text)
    if not native_clean and not ocr_clean:
        return ""
    if not native_clean:
        return ocr_clean
    if not ocr_clean:
        return native_clean
    if native_clean == ocr_clean:
        return native_clean
    if ocr_confidence < 60.0 or ocr_quality < 0.4:
        return native_clean
    if len(native_clean) >= len(ocr_clean) * 0.85:
        return native_clean
    if len(ocr_clean) >= len(native_clean) * 1.3:
        return ocr_clean
    return native_clean if len(native_clean) >= len(ocr_clean) else ocr_clean


def build_retrieval_cases() -> list[RetrievalCase]:
    return [
        RetrievalCase(query="What are sponsons?",
            answer_terms=("sponson", "sponsons", "wingtip float", "tip float"),
            answer_phrases=("short, winglike projections", "stabilize the hull"),
            expected_pages=(5,)),
        RetrievalCase(query="What does red right returning mean?",
            answer_terms=("red", "right", "returning", "buoy"),
            answer_phrases=("keep the red buoys to their right", "toward the shore"),
            expected_pages=(4,)),
        RetrievalCase(query="What is glassy water?",
            answer_terms=("glassy water", "smooth water", "mirror"),
            answer_phrases=("flat, glassy surface", "mirror"),
            expected_pages=(10, 11)),
        RetrievalCase(query="What are water rudders?",
            answer_terms=("water rudders", "retracted", "maneuvering"),
            answer_phrases=("rear tip of each float", "connected by cables and springs"),
            expected_pages=(8,)),
        RetrievalCase(query="What is hydrodynamic lift?",
            answer_terms=("hydrodynamic lift", "motion", "water"),
            answer_phrases=("upward force produced by the motion of the floats through the water",),
            expected_pages=(6, 7)),
        RetrievalCase(query="What causes weathervaning?",
            answer_terms=("weathervane", "yaw", "wind"),
            answer_phrases=("the wind tends to make the airplane weathervane",),
            expected_pages=(12,)),
        RetrievalCase(query="What does the step on a float do?",
            answer_terms=("step", "water drag", "takeoff"),
            answer_phrases=("reducing water drag during takeoff", "high-speed taxi"),
            expected_pages=(6, 7, 8)),
        RetrievalCase(query="How do buoys mark the channel?",
            answer_terms=("buoys", "channel", "seaward", "nun", "can"),
            answer_phrases=("red, right, returning", "keep the buoy to the right when inbound"),
            expected_pages=(2, 3, 4)),
    ]


def normalize_text_for_match(text: str) -> str:
    return base.normalize_text(text).lower()


def retrieve_ranked_chunks(persist_dir, collection_name, model, query, top_k, fetch_k,
                            rerank=False, rerank_model=None):
    collection = base.get_collection(persist_dir, collection_name)
    query_embedding = base.embed_texts(model, [query], kind="query")[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=max(top_k, fetch_k),
        include=["documents", "metadatas", "distances"],
    )
    if rerank and rerank_model:
        try:
            reranked = base.cross_encoder_rerank(query, results, model=rerank_model, top_k=top_k)
        except Exception:
            reranked = base.lexical_rerank(query, results, top_k)
    else:
        reranked = base.lexical_rerank(query, results, top_k)
    ranked = []
    for item in reranked:
        if len(item) == 5:
            document, metadata, distance, score, method = item
        else:
            document, metadata, distance, score = item
            method = "lexical"
        ranked.append((document, metadata or {}, distance, score, method))
    return ranked


def relevance_grade(case, document, metadata):
    text = normalize_text_for_match(document)
    title = normalize_text_for_match(str(metadata.get("section_title", "")))
    combined = f"{title}\n{text}"
    exact_phrase_hit = any(normalize_text_for_match(phrase) in combined for phrase in case.answer_phrases)
    term_hits = sum(1 for term in case.answer_terms if normalize_text_for_match(term) in combined)
    expected_pages = set(case.expected_pages)
    page_start = int(metadata.get("page_start", metadata.get("page", 0)) or 0)
    page_end = int(metadata.get("page_end", metadata.get("page", 0)) or 0)
    page_hit = any(page_start <= page <= page_end for page in expected_pages)
    if exact_phrase_hit: return 3
    if term_hits >= 3: return 3
    if term_hits >= 2 and page_hit: return 3
    if term_hits >= 2: return 2
    if term_hits >= 1 and page_hit: return 2
    if term_hits >= 1 or page_hit: return 1
    return 0


def dcg_from_grades(grades):
    total = 0.0
    for index, grade in enumerate(grades, start=1):
        if grade <= 0: continue
        total += (2 ** grade - 1) / math.log2(index + 1)
    return total


def evaluate_case(case, persist_dir, collection_name, model, top_k, fetch_k, rerank, rerank_model):
    start_time = time.perf_counter()
    ranked = retrieve_ranked_chunks(persist_dir=persist_dir, collection_name=collection_name,
        model=model, query=case.query, top_k=top_k, fetch_k=fetch_k,
        rerank=rerank, rerank_model=rerank_model)
    latency_ms = (time.perf_counter() - start_time) * 1000.0
    graded_results = []
    for document, metadata, distance, score, method in ranked:
        grade = relevance_grade(case, document, metadata)
        graded_results.append((grade, document, metadata, distance, score, method))
    first_relevant_rank = next((i for i, item in enumerate(graded_results, start=1) if item[0] > 0), 0)
    hit_at_k = first_relevant_rank > 0
    reciprocal_rank = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
    grades = [item[0] for item in graded_results[:top_k]]
    ideal_grades = sorted(grades, reverse=True)
    dcg = dcg_from_grades(grades)
    idcg = dcg_from_grades(ideal_grades)
    ndcg_at_k = dcg / idcg if idcg > 0 else 0.0
    top_context = "\n".join(document for _, document, _, _, _, _ in graded_results[:top_k])
    grounded = any(normalize_text_for_match(phrase) in normalize_text_for_match(top_context) for phrase in case.answer_phrases)
    if not grounded:
        grounded = sum(1 for term in case.answer_terms if normalize_text_for_match(term) in normalize_text_for_match(top_context)) >= 2
    hallucination_risk = 0.0 if grounded else 1.0
    top_docs = [{"grade": grade, "document": document, "metadata": metadata,
                  "distance": distance, "score": score, "method": method}
                for grade, document, metadata, distance, score, method in graded_results[:top_k]]
    return RetrievalResult(query=case.query, top_k=top_docs, hit_at_k=hit_at_k,
        reciprocal_rank=reciprocal_rank, ndcg_at_k=ndcg_at_k, latency_ms=latency_ms,
        hallucination_risk=hallucination_risk, grounded=grounded)


def summarize_retrieval_results(results, top_k):
    if not results:
        return {"recall_at_k": 0.0, "mrr": 0.0, "mean_ndcg_at_k": 0.0,
                "latency_ms_p50": 0.0, "latency_ms_p95": 0.0,
                "hallucination_rate": 0.0, "grounded_answer_rate": 0.0}
    latencies = [r.latency_ms for r in results]
    p95_index = max(int(math.ceil(len(latencies) * 0.95)) - 1, 0)
    latencies_sorted = sorted(latencies)
    return {
        "recall_at_k":        sum(1 for r in results if r.hit_at_k) / len(results),
        "mrr":                sum(r.reciprocal_rank for r in results) / len(results),
        "mean_ndcg_at_k":     sum(r.ndcg_at_k for r in results) / len(results),
        "latency_ms_p50":     statistics.median(latencies_sorted),
        "latency_ms_p95":     latencies_sorted[p95_index],
        "hallucination_rate": sum(r.hallucination_risk for r in results) / len(results),
        "grounded_answer_rate": sum(1.0 - r.hallucination_risk for r in results) / len(results),
        "top_k": float(top_k),
    }


def print_retrieval_benchmark(results, summary, *, show_results):
    print("Retrieval benchmark")
    print(f"Cases: {len(results)}")
    print()
    print(f"Recall@K:          {summary['recall_at_k']:.3f}")
    print(f"MRR:               {summary['mrr']:.3f}")
    print(f"nDCG@K:            {summary['mean_ndcg_at_k']:.3f}")
    print(f"Latency p50 (ms):  {summary['latency_ms_p50']:.1f}")
    print(f"Latency p95 (ms):  {summary['latency_ms_p95']:.1f}")
    print(f"Grounded rate:     {summary['grounded_answer_rate']:.3f}")
    print(f"Hallucination rate:{summary['hallucination_rate']:.3f}")
    if not show_results:
        return
    print()
    for result in results:
        print(f"Query: {result.query}")
        print(f"hit@k={result.hit_at_k} rr={result.reciprocal_rank:.3f} ndcg={result.ndcg_at_k:.3f} "
              f"latency={result.latency_ms:.1f}ms grounded={result.grounded}")
        for index, item in enumerate(result.top_k, start=1):
            preview = item["document"].replace("\n", " ").strip()
            if len(preview) > 220:
                preview = preview[:217] + "..."
            print(f"  [{index}] grade={item['grade']} score={item['score']} distance={item['distance']}")
            print(f"      {preview}")
        print()


def run_retrieval_benchmark(args):
    cases = build_retrieval_cases()
    results = [evaluate_case(case=case, persist_dir=args.persist_dir, collection_name=args.collection,
        model=args.model, top_k=args.top_k, fetch_k=args.fetch_k, rerank=args.rerank,
        rerank_model=(args.rerank_model if getattr(args, "rerank_model", None) else None))
        for case in cases]
    summary = summarize_retrieval_results(results, args.top_k)
    print_retrieval_benchmark(results, summary, show_results=args.show_results)
    if args.out:
        payload = {"summary": summary, "cases": [
            {"query": r.query, "hit_at_k": r.hit_at_k, "reciprocal_rank": r.reciprocal_rank,
             "ndcg_at_k": r.ndcg_at_k, "latency_ms": r.latency_ms,
             "hallucination_risk": r.hallucination_risk, "grounded": r.grounded, "top_k": r.top_k}
            for r in results]}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved benchmark results to {args.out}")


def render_page_image(page: Any, dpi: int = base.OCR_DPI):
    import fitz
    from PIL import Image
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def ocr_page_text_and_image(page: Any, dpi: int = base.OCR_DPI) -> tuple[str, Any, float]:
    import pytesseract
    cmd = base.configure_tesseract()
    if not cmd:
        raise RuntimeError("Tesseract executable not found.")
    image = render_page_image(page, dpi=dpi)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    lines: list[str] = []
    current_line_key = None
    current_words: list[str] = []
    confidence_values: list[float] = []
    texts = data.get("text", [])
    confs = data.get("conf", [])
    block_nums = data.get("block_num", [])
    par_nums = data.get("par_num", [])
    line_nums = data.get("line_num", [])
    for index, raw_text in enumerate(texts):
        word = str(raw_text).strip()
        if not word:
            continue
        try:
            confidence = float(confs[index])
        except (TypeError, ValueError, IndexError):
            confidence = -1.0
        if confidence >= 0:
            confidence_values.append(confidence)
        line_key = (int(block_nums[index]), int(par_nums[index]), int(line_nums[index]))
        if current_line_key is None:
            current_line_key = line_key
        elif line_key != current_line_key:
            if current_words:
                lines.append(" ".join(current_words))
            current_words = []
            current_line_key = line_key
        current_words.append(word)
    if current_words:
        lines.append(" ".join(current_words))
    confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    return "\n".join(lines).strip(), image, confidence


def save_page_debug_artifacts(debug_dir, index, native_text, ocr_text, selected_text,
                               ocr_used, ocr_quality, ocr_confidence, image, save_images):
    debug_dir.mkdir(parents=True, exist_ok=True)
    text_path = debug_dir / f"page_{index:03d}.txt"
    parts = [f"PAGE: {index}", f"OCR_USED: {ocr_used}",
             f"OCR_QUALITY: {ocr_quality:.4f}", f"OCR_CONFIDENCE: {ocr_confidence:.2f}",
             "", "=== NATIVE ===", native_text.strip(), "", "=== OCR ===", ocr_text.strip(),
             "", "=== SELECTED ===", selected_text.strip(), ""]
    text_path.write_text("\n".join(parts), encoding="utf-8")
    if save_images and image is not None and ocr_used:
        image_path = debug_dir / f"page_{index:03d}.png"
        image.save(image_path)


def extract_pages_pymupdf(
    pdf_path: Path,
    debug_dir: Path,
    ocr_debug: bool = True,
    save_images: bool = True,
) -> list[dict[str, Any]]:
    import fitz
    pages: list[dict[str, Any]] = []
    tesseract_cmd = base.configure_tesseract()
    if not tesseract_cmd:
        print("[warning] Tesseract not found; OCR fallback skipped.")

    skipped_ref_pages = 0
    with fitz.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc, start=1):
            native_text = (page.get_text("text") or "").strip()
            ocr_text = ""
            ocr_used = False
            selected_text = native_text
            image = None
            ocr_confidence = 0.0

            if base.native_text_looks_poor(native_text) and tesseract_cmd:
                try:
                    ocr_text, image, ocr_confidence = ocr_page_text_and_image(page, dpi=base.OCR_DPI)
                    if base.normalize_text(ocr_text) and ocr_confidence >= 40.0:
                        ocr_quality_pre = ocr_quality_score(ocr_text)
                        selected_text = merge_page_text(native_text, ocr_text,
                            ocr_confidence=ocr_confidence, ocr_quality=ocr_quality_pre)
                        ocr_used = True
                except Exception as error:
                    print(f"[warning] OCR failed on page {index}: {error}")

            ocr_quality = ocr_quality_score(selected_text)

            # FIX B: Suppress reference / appendix / TOC pages from chunking.
            # They produce noisy chunks that match queries via citation patterns
            # but contain no useful prose.
            is_ref = is_reference_page(selected_text)
            if is_ref:
                selected_text = ""
                skipped_ref_pages += 1

            ref_flag = " [REF-SKIP]" if is_ref else ""
            print(f"Page {index}: OCR={ocr_used} Quality={ocr_quality:.2f} Confidence={ocr_confidence:.2f}{ref_flag}")

            if ocr_debug:
                save_page_debug_artifacts(debug_dir=debug_dir, index=index,
                    native_text=native_text, ocr_text=ocr_text,
                    selected_text=selected_text, ocr_used=ocr_used,
                    ocr_quality=ocr_quality, ocr_confidence=ocr_confidence,
                    image=image, save_images=save_images)
                if ocr_used:
                    print(f"\n--- OCR PAGE {index} ---")
                    print("=== NATIVE ===")
                    print(native_text[:1000])
                    print("\n=== OCR ===")
                    print(ocr_text[:1500])
                    print("\n=== SELECTED ===")
                    print(selected_text[:1500])
                    print("\n-----------------------\n")

            pages.append({
                "page":           index,
                "text":           selected_text.strip(),
                "ocr_used":       ocr_used,
                "native_text":    native_text,
                "ocr_text":       ocr_text,
                "ocr_quality":    ocr_quality,
                "ocr_confidence": ocr_confidence,
            })

    if skipped_ref_pages:
        print(f"[ref-filter] Skipped {skipped_ref_pages} reference/appendix/TOC pages")

    return pages


def enrich_chunk_metadata(chunks, pages):
    page_map = {int(page["page"]): page for page in pages}
    for chunk in chunks:
        start = int(chunk.metadata.get("page_start", 0) or 0)
        end = int(chunk.metadata.get("page_end", 0) or 0)
        page_numbers = [pn for pn in range(start, end + 1) if pn in page_map]
        ocr_pages = [pn for pn in page_numbers if page_map[pn].get("ocr_used")]
        ocr_qualities = [float(page_map[pn].get("ocr_quality", 0.0)) for pn in page_numbers]
        ocr_confidences = [float(page_map[pn].get("ocr_confidence", 0.0)) for pn in page_numbers]
        metadata_update = {
            "contains_ocr":       bool(ocr_pages),
            "ocr_page_count":     len(ocr_pages),
            "ocr_quality_mean":   round(sum(ocr_qualities) / len(ocr_qualities), 4) if ocr_qualities else 0.0,
            "ocr_confidence_mean":round(sum(ocr_confidences) / len(ocr_confidences), 2) if ocr_confidences else 0.0,
        }
        if ocr_pages:
            metadata_update["ocr_pages"] = ",".join(str(pn) for pn in ocr_pages)
        chunk.metadata.update(metadata_update)


def dump_chunks_to_disk(chunks, dump_dir):
    dump_dir.mkdir(parents=True, exist_ok=True)
    for index, chunk in enumerate(chunks, start=1):
        chunk_path = dump_dir / f"chunk_{index:03d}.txt"
        header = [f"CHUNK: {index}", f"CHUNK_ID: {chunk.chunk_id}", f"TITLE: {chunk.title}",
                  f"PAGE_START: {chunk.metadata.get('page_start', 0)}",
                  f"PAGE_END: {chunk.metadata.get('page_end', 0)}",
                  f"METADATA: {chunk.metadata}", ""]
        chunk_path.write_text("\n".join(header + [chunk.text.strip(), ""]), encoding="utf-8")


def ingest_pdf(pdf_path, persist_dir, collection_name, model, chunk_words, overlap,
               ocr_debug_dir, chunk_debug_dir, ocr_debug=True, save_images=True,
               db_path=DEFAULT_DB_PATH):
    from src.db.storage import RAGDatabase
    from src.db.ingest_bridge import ingest_pdf_to_db
    db = RAGDatabase(db_path)
    ingest_pdf_to_db(pdf_path=pdf_path, db=db, persist_dir=persist_dir,
                     collection_name=collection_name, model=model,
                     chunk_words=chunk_words, overlap=overlap,
                     ocr_debug_dir=ocr_debug_dir, chunk_debug_dir=chunk_debug_dir,
                     ocr_debug=ocr_debug, save_images=save_images)
    status = db.status()
    print(f"\n[db] {status['documents']} doc(s)  {status['chunks']} chunks  "
          f"{status['embedded_chunks']} embedded  {status['ocr_selected_pages']} OCR-selected pages")
    db.close()


def main() -> None:
    args = parse_args()
    if args.command == "ingest":
        ingest_pdf(pdf_path=args.pdf, persist_dir=args.persist_dir, collection_name=args.collection,
                   model=args.model, chunk_words=args.chunk_words, overlap=args.overlap,
                   ocr_debug_dir=args.ocr_debug_dir, chunk_debug_dir=args.chunk_debug_dir,
                   ocr_debug=args.ocr_debug, save_images=args.ocr_debug, db_path=args.db_path)
        return
    if args.command == "query":
        base.query_collection(persist_dir=args.persist_dir, collection_name=args.collection,
                               model=args.model, query=args.query, top_k=args.top_k,
                               fetch_k=base.DEFAULT_FETCH_K, rerank=args.rerank,
                               rerank_model=(args.rerank_model if getattr(args, "rerank_model", None) else None))
        return
    if args.command == "benchmark":
        run_retrieval_benchmark(args)
        return
    if args.command == "status":
        from src.db.storage import RAGDatabase
        db = RAGDatabase(args.db_path)
        s = db.status()
        print(f"DB: {s['db_path']}")
        print(f"Documents:          {s['documents']}")
        print(f"Pages:              {s['pages']}")
        print(f"Chunks:             {s['chunks']}")
        print(f"Embedded chunks:    {s['embedded_chunks']}")
        print(f"OCR-selected pages: {s['ocr_selected_pages']}")
        print(f"Retrieval logs:     {s['retrieval_logs']}")
        if s["document_list"]:
            print()
            print(f"{'Filename':<40} {'Status':<10} {'Pages':>5} {'Chunks':>7} {'Embedded':>8}")
            print("-" * 75)
            for doc in s["document_list"]:
                print(f"{doc['filename']:<40} {doc['status']:<10} "
                      f"{str(doc['page_count'] or 0):>5} "
                      f"{str(doc['chunks'] or 0):>7} "
                      f"{str(doc['embedded'] or 0):>8}")
        db.close()
        return
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()