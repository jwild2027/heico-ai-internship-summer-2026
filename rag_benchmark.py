#!/usr/bin/env python3
"""Benchmark-oriented copy of the PyMuPDF + BGE + Chroma CLI.

This version keeps the same ingest/query pipeline, but adds OCR visibility:
- prints native vs OCR text when OCR is used
- saves per-page debug text files
- saves rendered OCR images
- adds OCR metadata to chunks
- computes a simple OCR quality score per page

Examples:
  python rag_benchmark.py ingest --pdf path/to/file.pdf
  python rag_benchmark.py query --query "what is the warranty period?"
"""

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

# Ensure the repo root is on sys.path so we can import from tools/.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import pymupdf_bge_chroma_cli as base  # noqa: E402


DEFAULT_OCR_DEBUG_DIR = Path("ocr_debug")
DEFAULT_CHUNK_DEBUG_DIR = Path("chunk_debug")
DEFAULT_DB_PATH = Path("rag.db")


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
    parser = argparse.ArgumentParser(
        description="Benchmark copy of the PyMuPDF + BGE + Chroma CLI with OCR diagnostics."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Extract, OCR, chunk, embed, and store a PDF.")
    ingest_parser.add_argument("--pdf", type=Path, required=True, help="Path to the PDF file.")
    ingest_parser.add_argument(
        "--persist-dir",
        type=Path,
        default=base.DEFAULT_PERSIST_DIR,
        help="Directory for the persistent ChromaDB store.",
    )
    ingest_parser.add_argument(
        "--collection",
        default=base.DEFAULT_COLLECTION,
        help="ChromaDB collection name.",
    )
    ingest_parser.add_argument(
        "--model",
        default=base.DEFAULT_MODEL,
        help="Ollama embedding model to use.",
    )
    ingest_parser.add_argument("--chunk-words", type=int, default=base.DEFAULT_CHUNK_WORDS)
    ingest_parser.add_argument("--overlap", type=int, default=base.DEFAULT_CHUNK_OVERLAP)
    ingest_parser.add_argument(
        "--ocr-debug-dir",
        type=Path,
        default=DEFAULT_OCR_DEBUG_DIR,
        help="Directory where OCR debug text files and images are saved.",
    )
    ingest_parser.add_argument(
        "--chunk-debug-dir",
        type=Path,
        default=DEFAULT_CHUNK_DEBUG_DIR,
        help="Directory where chunk text dumps are saved.",
    )
    ingest_parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the SQLite database file.",
    )
    ingest_parser.add_argument(
        "--ocr-debug",
        dest="ocr_debug",
        action="store_true",
        default=True,
        help="Enable OCR debug printing and file output (default: on).",
    )
    ingest_parser.add_argument(
        "--no-ocr-debug",
        dest="ocr_debug",
        action="store_false",
        help=argparse.SUPPRESS,
    )

    query_parser = subparsers.add_parser("query", help="Search the stored chunks.")
    query_parser.add_argument("--query", required=True, help="Query text.")
    query_parser.add_argument(
        "--persist-dir",
        type=Path,
        default=base.DEFAULT_PERSIST_DIR,
        help="Directory for the persistent ChromaDB store.",
    )
    query_parser.add_argument(
        "--collection",
        default=base.DEFAULT_COLLECTION,
        help="ChromaDB collection name.",
    )
    query_parser.add_argument(
        "--model",
        default=base.DEFAULT_MODEL,
        help="Ollama embedding model to use.",
    )
    query_parser.add_argument("--top-k", type=int, default=5, help="How many chunks to return.")
    query_parser.add_argument("--rerank", action="store_true", help="Apply cross-encoder reranker to top candidates.")
    query_parser.add_argument("--rerank-model", default="bge-reranker-large", help="Reranker model to use when --rerank is set.")

    benchmark_parser = subparsers.add_parser("benchmark", help="Evaluate retrieval quality on OCR-grounded queries.")
    benchmark_parser.add_argument(
        "--persist-dir",
        type=Path,
        default=base.DEFAULT_PERSIST_DIR,
        help="Directory for the persistent ChromaDB store.",
    )
    benchmark_parser.add_argument(
        "--collection",
        default=base.DEFAULT_COLLECTION,
        help="ChromaDB collection name.",
    )
    benchmark_parser.add_argument(
        "--model",
        default=base.DEFAULT_MODEL,
        help="Ollama embedding model to use.",
    )
    benchmark_parser.add_argument("--top-k", type=int, default=5, help="How many chunks count toward Recall@K.")
    benchmark_parser.add_argument("--fetch-k", type=int, default=base.DEFAULT_FETCH_K, help="How many candidates to fetch before reranking.")
    benchmark_parser.add_argument("--rerank", action="store_true", help="Apply cross-encoder reranker to top candidates.")
    benchmark_parser.add_argument("--rerank-model", default="bge-reranker-large", help="Reranker model to use when --rerank is set.")
    benchmark_parser.add_argument("--out", type=Path, help="Optional JSON file for per-case results and summary.")
    benchmark_parser.add_argument("--show-results", action="store_true", help="Print the ranked chunks for every benchmark case.")

    # status command — shows what's in the DB
    status_parser = subparsers.add_parser("status", help="Show what documents and chunks are stored.")
    status_parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the SQLite database file.",
    )

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


# FIX 1: merge_page_text no longer concatenates both texts.
# Old logic returned f"{native_clean}\n\n{ocr_clean}" when native >= 80% of OCR length,
# which doubled content in the selected text and degraded embeddings.
# New logic always picks a single winner based on confidence, quality, and length.
def merge_page_text(
    native_text: str,
    ocr_text: str,
    ocr_confidence: float = 0.0,
    ocr_quality: float = 0.0,
) -> str:
    native_clean = base.normalize_text(native_text)
    ocr_clean = base.normalize_text(ocr_text)

    # Only one source available
    if not native_clean and not ocr_clean:
        return ""
    if not native_clean:
        return ocr_clean
    if not ocr_clean:
        return native_clean

    # Identical — no need to choose
    if native_clean == ocr_clean:
        return native_clean

    # OCR not trustworthy enough to override native
    if ocr_confidence < 60.0 or ocr_quality < 0.4:
        return native_clean

    # Native is clearly more complete — trust it
    if len(native_clean) >= len(ocr_clean) * 0.85:
        return native_clean

    # OCR recovered significantly more content — trust OCR
    if len(ocr_clean) >= len(native_clean) * 1.3:
        return ocr_clean

    # Both partial and similar length — pick the longer one
    return native_clean if len(native_clean) >= len(ocr_clean) else ocr_clean


def build_retrieval_cases() -> list[RetrievalCase]:
    return [
        RetrievalCase(
            query="What are sponsons?",
            answer_terms=("sponson", "sponsons", "wingtip float", "tip float"),
            answer_phrases=("short, winglike projections", "stabilize the hull"),
            expected_pages=(5,),
        ),
        RetrievalCase(
            query="What does red right returning mean?",
            answer_terms=("red", "right", "returning", "buoy"),
            answer_phrases=("keep the red buoys to their right", "toward the shore"),
            expected_pages=(4,),
        ),
        RetrievalCase(
            query="What is glassy water?",
            answer_terms=("glassy water", "smooth water", "mirror"),
            answer_phrases=("flat, glassy surface", "mirror"),
            expected_pages=(10, 11),
        ),
        RetrievalCase(
            query="What are water rudders?",
            answer_terms=("water rudders", "retracted", "maneuvering"),
            answer_phrases=("rear tip of each float", "connected by cables and springs"),
            expected_pages=(8,),
        ),
        RetrievalCase(
            query="What is hydrodynamic lift?",
            answer_terms=("hydrodynamic lift", "motion", "water"),
            answer_phrases=("upward force produced by the motion of the floats through the water",),
            expected_pages=(6, 7),
        ),
        RetrievalCase(
            query="What causes weathervaning?",
            answer_terms=("weathervane", "yaw", "wind"),
            answer_phrases=("the wind tends to make the airplane weathervane",),
            expected_pages=(12,),
        ),
        RetrievalCase(
            query="What does the step on a float do?",
            answer_terms=("step", "water drag", "takeoff"),
            answer_phrases=("reducing water drag during takeoff", "high-speed taxi"),
            expected_pages=(6, 7, 8),
        ),
        RetrievalCase(
            query="How do buoys mark the channel?",
            answer_terms=("buoys", "channel", "seaward", "nun", "can"),
            answer_phrases=("red, right, returning", "keep the buoy to the right when inbound"),
            expected_pages=(2, 3, 4),
        ),
    ]


def normalize_text_for_match(text: str) -> str:
    return base.normalize_text(text).lower()


def retrieve_ranked_chunks(
    persist_dir: Path,
    collection_name: str,
    model: str,
    query: str,
    top_k: int,
    fetch_k: int,
    rerank: bool = False,
    rerank_model: str | None = None,
) -> list[tuple[str, dict[str, Any], float | None, float | None, str]]:
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

    ranked: list[tuple[str, dict[str, Any], float | None, float | None, str]] = []
    for item in reranked:
        if len(item) == 5:
            document, metadata, distance, score, method = item
        else:
            document, metadata, distance, score = item
            method = "lexical"
        ranked.append((document, metadata or {}, distance, score, method))
    return ranked


def relevance_grade(case: RetrievalCase, document: str, metadata: dict[str, Any]) -> int:
    text = normalize_text_for_match(document)
    title = normalize_text_for_match(str(metadata.get("section_title", "")))
    combined = f"{title}\n{text}"

    exact_phrase_hit = any(normalize_text_for_match(phrase) in combined for phrase in case.answer_phrases)
    term_hits = sum(1 for term in case.answer_terms if normalize_text_for_match(term) in combined)

    expected_pages = set(case.expected_pages)
    page_start = int(metadata.get("page_start", metadata.get("page", 0)) or 0)
    page_end = int(metadata.get("page_end", metadata.get("page", 0)) or 0)
    page_hit = any(page_start <= page <= page_end for page in expected_pages)

    if exact_phrase_hit:
        return 3
    if term_hits >= 3:
        return 3
    if term_hits >= 2 and page_hit:
        return 3
    if term_hits >= 2:
        return 2
    if term_hits >= 1 and page_hit:
        return 2
    if term_hits >= 1 or page_hit:
        return 1
    return 0


def dcg_from_grades(grades: list[int]) -> float:
    total = 0.0
    for index, grade in enumerate(grades, start=1):
        if grade <= 0:
            continue
        total += (2 ** grade - 1) / math.log2(index + 1)
    return total


def evaluate_case(
    case: RetrievalCase,
    persist_dir: Path,
    collection_name: str,
    model: str,
    top_k: int,
    fetch_k: int,
    rerank: bool,
    rerank_model: str | None,
) -> RetrievalResult:
    start_time = time.perf_counter()
    ranked = retrieve_ranked_chunks(
        persist_dir=persist_dir,
        collection_name=collection_name,
        model=model,
        query=case.query,
        top_k=top_k,
        fetch_k=fetch_k,
        rerank=rerank,
        rerank_model=rerank_model,
    )
    latency_ms = (time.perf_counter() - start_time) * 1000.0

    graded_results: list[tuple[int, str, dict[str, Any], float | None, float | None, str]] = []
    for document, metadata, distance, score, method in ranked:
        grade = relevance_grade(case, document, metadata)
        graded_results.append((grade, document, metadata, distance, score, method))

    first_relevant_rank = next((index for index, item in enumerate(graded_results, start=1) if item[0] > 0), 0)
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

    top_docs = []
    for grade, document, metadata, distance, score, method in graded_results[:top_k]:
        top_docs.append(
            {
                "grade": grade,
                "document": document,
                "metadata": metadata,
                "distance": distance,
                "score": score,
                "method": method,
            }
        )

    return RetrievalResult(
        query=case.query,
        top_k=top_docs,
        hit_at_k=hit_at_k,
        reciprocal_rank=reciprocal_rank,
        ndcg_at_k=ndcg_at_k,
        latency_ms=latency_ms,
        hallucination_risk=hallucination_risk,
        grounded=grounded,
    )


def summarize_retrieval_results(results: list[RetrievalResult], top_k: int) -> dict[str, float]:
    if not results:
        return {
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "mean_ndcg_at_k": 0.0,
            "latency_ms_p50": 0.0,
            "latency_ms_p95": 0.0,
            "hallucination_rate": 0.0,
            "grounded_answer_rate": 0.0,
        }

    latencies = [result.latency_ms for result in results]
    p95_index = max(int(math.ceil(len(latencies) * 0.95)) - 1, 0)
    latencies_sorted = sorted(latencies)

    recall_at_k = sum(1 for result in results if result.hit_at_k) / len(results)
    mrr = sum(result.reciprocal_rank for result in results) / len(results)
    mean_ndcg_at_k = sum(result.ndcg_at_k for result in results) / len(results)
    hallucination_rate = sum(result.hallucination_risk for result in results) / len(results)
    grounded_answer_rate = sum(1.0 - result.hallucination_risk for result in results) / len(results)

    return {
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "mean_ndcg_at_k": mean_ndcg_at_k,
        "latency_ms_p50": statistics.median(latencies_sorted),
        "latency_ms_p95": latencies_sorted[p95_index],
        "hallucination_rate": hallucination_rate,
        "grounded_answer_rate": grounded_answer_rate,
        "top_k": float(top_k),
    }


def print_retrieval_benchmark(results: list[RetrievalResult], summary: dict[str, float], *, show_results: bool) -> None:
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
        print(
            f"hit@k={result.hit_at_k} rr={result.reciprocal_rank:.3f} ndcg={result.ndcg_at_k:.3f} "
            f"latency={result.latency_ms:.1f}ms grounded={result.grounded} hallucination_risk={result.hallucination_risk:.1f}"
        )
        for index, item in enumerate(result.top_k, start=1):
            preview = item["document"].replace("\n", " ").strip()
            if len(preview) > 220:
                preview = preview[:217] + "..."
            print(f"  [{index}] grade={item['grade']} score={item['score']} distance={item['distance']} method={item['method']}")
            print(f"      {preview}")
        print()


def run_retrieval_benchmark(args: argparse.Namespace) -> None:
    cases = build_retrieval_cases()
    results = [
        evaluate_case(
            case=case,
            persist_dir=args.persist_dir,
            collection_name=args.collection,
            model=args.model,
            top_k=args.top_k,
            fetch_k=args.fetch_k,
            rerank=args.rerank,
            rerank_model=(args.rerank_model if getattr(args, "rerank_model", None) else None),
        )
        for case in cases
    ]
    summary = summarize_retrieval_results(results, args.top_k)
    print_retrieval_benchmark(results, summary, show_results=args.show_results)

    if args.out:
        payload = {
            "summary": summary,
            "cases": [
                {
                    "query": result.query,
                    "hit_at_k": result.hit_at_k,
                    "reciprocal_rank": result.reciprocal_rank,
                    "ndcg_at_k": result.ndcg_at_k,
                    "latency_ms": result.latency_ms,
                    "hallucination_risk": result.hallucination_risk,
                    "grounded": result.grounded,
                    "top_k": result.top_k,
                }
                for result in results
            ],
        }
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
        raise RuntimeError(
            "Tesseract executable not found. Set TESSERACT_CMD or install Tesseract desktop app."
        )

    image = render_page_image(page, dpi=dpi)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

    lines: list[str] = []
    current_line_key: tuple[int, int, int] | None = None
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

        line_key = (
            int(block_nums[index]),
            int(par_nums[index]),
            int(line_nums[index]),
        )

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


def save_page_debug_artifacts(
    debug_dir: Path,
    index: int,
    native_text: str,
    ocr_text: str,
    selected_text: str,
    ocr_used: bool,
    ocr_quality: float,
    ocr_confidence: float,
    image: Any | None,
    save_images: bool,
) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)

    text_path = debug_dir / f"page_{index:03d}.txt"
    parts = [
        f"PAGE: {index}",
        f"OCR_USED: {ocr_used}",
        f"OCR_QUALITY: {ocr_quality:.4f}",
        f"OCR_CONFIDENCE: {ocr_confidence:.2f}",
        "",
        "=== NATIVE ===",
        native_text.strip(),
        "",
        "=== OCR ===",
        ocr_text.strip(),
        "",
        "=== SELECTED ===",
        selected_text.strip(),
        "",
    ]
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
        print(
            "[warning] Tesseract executable not found; OCR fallback will be skipped. "
            "Set TESSERACT_CMD to the full path of tesseract.exe or add it to PATH if you want OCR."
        )

    with fitz.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc, start=1):
            native_text = page.get_text("text") or ""
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
                        # FIX 1 applied: pass confidence + quality so merge never concatenates
                        selected_text = merge_page_text(
                            native_text,
                            ocr_text,
                            ocr_confidence=ocr_confidence,
                            ocr_quality=ocr_quality_pre,
                        )
                        ocr_used = True
                except Exception as error:
                    print(f"[warning] OCR failed on page {index}: {error}")

            ocr_quality = ocr_quality_score(selected_text)
            print(f"Page {index}: OCR={ocr_used} Quality={ocr_quality:.2f} Confidence={ocr_confidence:.2f}")

            if ocr_debug:
                save_page_debug_artifacts(
                    debug_dir=debug_dir,
                    index=index,
                    native_text=native_text,
                    ocr_text=ocr_text,
                    selected_text=selected_text,
                    ocr_used=ocr_used,
                    ocr_quality=ocr_quality,
                    ocr_confidence=ocr_confidence,
                    image=image,
                    save_images=save_images,
                )
                if ocr_used:
                    print(f"\n--- OCR PAGE {index} ---")
                    print("=== NATIVE ===")
                    print(native_text[:1000])
                    print("\n=== OCR ===")
                    print(ocr_text[:1500])
                    print("\n=== SELECTED ===")
                    print(selected_text[:1500])
                    print("\n-----------------------\n")

            pages.append(
                {
                    "page": index,
                    "text": selected_text,
                    "ocr_used": ocr_used,
                    "native_text": native_text,
                    "ocr_text": ocr_text,
                    "ocr_quality": ocr_quality,
                    "ocr_confidence": ocr_confidence,
                }
            )

    return pages


def enrich_chunk_metadata(chunks: list[base.ChunkRecord], pages: list[dict[str, Any]]) -> None:
    page_map = {int(page["page"]): page for page in pages}
    for chunk in chunks:
        start = int(chunk.metadata.get("page_start", 0) or 0)
        end = int(chunk.metadata.get("page_end", 0) or 0)
        page_numbers = [page_number for page_number in range(start, end + 1) if page_number in page_map]
        ocr_pages = [page_number for page_number in page_numbers if page_map[page_number].get("ocr_used")]
        ocr_qualities = [float(page_map[page_number].get("ocr_quality", 0.0)) for page_number in page_numbers]
        ocr_confidences = [float(page_map[page_number].get("ocr_confidence", 0.0)) for page_number in page_numbers]

        metadata_update: dict[str, Any] = {
            "contains_ocr": bool(ocr_pages),
            "ocr_page_count": len(ocr_pages),
            "ocr_quality_mean": round(sum(ocr_qualities) / len(ocr_qualities), 4) if ocr_qualities else 0.0,
            "ocr_confidence_mean": round(sum(ocr_confidences) / len(ocr_confidences), 2) if ocr_confidences else 0.0,
        }

        # ChromaDB does not accept empty metadata lists, so only include OCR pages when present.
        if ocr_pages:
            metadata_update["ocr_pages"] = ",".join(str(page_number) for page_number in ocr_pages)

        chunk.metadata.update(metadata_update)


def dump_chunks_to_disk(chunks: list[base.ChunkRecord], dump_dir: Path) -> None:
    dump_dir.mkdir(parents=True, exist_ok=True)
    for index, chunk in enumerate(chunks, start=1):
        chunk_path = dump_dir / f"chunk_{index:03d}.txt"
        header = [
            f"CHUNK: {index}",
            f"CHUNK_ID: {chunk.chunk_id}",
            f"TITLE: {chunk.title}",
            f"PAGE_START: {chunk.metadata.get('page_start', 0)}",
            f"PAGE_END: {chunk.metadata.get('page_end', 0)}",
            f"METADATA: {chunk.metadata}",
            "",
        ]
        chunk_path.write_text("\n".join(header + [chunk.text.strip(), ""]), encoding="utf-8")


def ingest_pdf(
    pdf_path: Path,
    persist_dir: Path,
    collection_name: str,
    model: str,
    chunk_words: int,
    overlap: int,
    ocr_debug_dir: Path,
    chunk_debug_dir: Path,
    ocr_debug: bool = True,
    save_images: bool = True,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    from db.storage import RAGDatabase
    from db.ingest_bridge import ingest_pdf_to_db

    db = RAGDatabase(db_path)
    ingest_pdf_to_db(
        pdf_path=pdf_path,
        db=db,
        persist_dir=persist_dir,
        collection_name=collection_name,
        model=model,
        chunk_words=chunk_words,
        overlap=overlap,                    # FIX 2: was hardcoded to DEFAULT_OVERLAP_BLOCKS
        ocr_debug_dir=ocr_debug_dir,
        chunk_debug_dir=chunk_debug_dir,
        ocr_debug=ocr_debug,
        save_images=save_images,
    )

    status = db.status()
    print(f"\n[db] {status['documents']} doc(s)  {status['chunks']} chunks  "
          f"{status['embedded_chunks']} embedded  "
          f"{status['ocr_selected_pages']} OCR-selected pages")
    db.close()


def main() -> None:
    args = parse_args()

    if args.command == "ingest":
        ingest_pdf(
            pdf_path=args.pdf,
            persist_dir=args.persist_dir,
            collection_name=args.collection,
            model=args.model,
            chunk_words=args.chunk_words,
            overlap=args.overlap,
            ocr_debug_dir=args.ocr_debug_dir,
            chunk_debug_dir=args.chunk_debug_dir,
            ocr_debug=args.ocr_debug,
            save_images=args.ocr_debug,
            db_path=args.db_path,
        )
        return

    if args.command == "query":
        base.query_collection(
            persist_dir=args.persist_dir,
            collection_name=args.collection,
            model=args.model,
            query=args.query,
            top_k=args.top_k,
            fetch_k=base.DEFAULT_FETCH_K,
            rerank=args.rerank,
            rerank_model=(args.rerank_model if getattr(args, "rerank_model", None) else None),
        )
        return

    if args.command == "benchmark":
        run_retrieval_benchmark(args)
        return

    if args.command == "status":
        from db.storage import RAGDatabase
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
                print(
                    f"{doc['filename']:<40} {doc['status']:<10} "
                    f"{str(doc['page_count'] or 0):>5} "
                    f"{str(doc['chunks'] or 0):>7} "
                    f"{str(doc['embedded'] or 0):>8}"
                )
        db.close()
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()