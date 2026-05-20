"""Benchmark local embedding models on a harder synthetic retrieval corpus.

This is identical in behavior to `embedding_benchmark.py` but uses a much more
difficult built-in corpus designed to separate embedding model quality. The
corpus includes distractor chunks, overlapping concepts, OCR-like noise,
long multi-paragraph passages, ambiguous phrasing, and near-duplicates.

Usage:
  python embedding_benchmark_harder.py
  python embedding_benchmark_harder.py --models mxbai-embed-large,bge-large,nomic-embed-text --k 5
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

try:
    import ollama
except Exception as exc:  # pragma: no cover - local environment guard
    raise RuntimeError("Missing ollama Python package. Install it with: pip install ollama") from exc


DEFAULT_MODELS = ["mxbai-embed-large", "bge-large", "nomic-embed-text"]


@dataclass(frozen=True)
class CorpusItem:
    doc_id: str
    text: str


@dataclass(frozen=True)
class QueryItem:
    query_id: str
    query: str
    relevant_doc_id: str


@dataclass
class QueryResult:
    query_id: str
    query: str
    relevant_doc_id: str
    top1_doc_id: str
    topk_doc_ids: list[str]
    top1_score: float
    hit_at_1: bool
    hit_at_k: bool
    reciprocal_rank: float
    latency_ms: float
    error: str | None = None


# HARDER CORPUS: 24 documents with overlapping keywords, OCR-like noise,
# long passages, ambiguous phrasing, distractors, and near-duplicates.
BUILTIN_CORPUS: list[CorpusItem] = [
    CorpusItem("doc-01", "Database indexes speed up lookups by reducing scanned rows and using b-tree or hash structures."),
    CorpusItem("doc-02", "Indexing images in a photo gallery uses metadata indexes and thumbnail caches; note the word 'index' here is in a different domain."),
    CorpusItem("doc-03", "Version control stores snapshots of a codebase over time. Branches let teams work independently; merges combine changes."),
    CorpusItem("doc-04", "Version control systems record history, support branching, and track merges. (near-duplicate of doc-03 with slightly different wording)."),
    CorpusItem("doc-05", "Caching: caches keep frequently used results in faster storage. Eviction strategies include LRU and LFU.\n\nLong-form discussion: an LRU cache evicts the least recently used entry, which works well for temporal locality. In distributed caches, consistency and invalidation matter."),
    CorpusItem("doc-06", "OCR converts images to text. Typical OCR errors: 0 vs O, 1 vs l, rn vs m, and garbled punctuation. Example noisy output: 'Th1s is an OCR line w1th m1sread 0 and O'."),
    CorpusItem("doc-07", "A unit test verifies a small unit of code in isolation, often using mocks or stubs to isolate behavior."),
    CorpusItem("doc-08", "A vector database stores embeddings; approximate nearest neighbor search (ANN) finds semantically similar items quickly."),
    CorpusItem("doc-09", "In physics, a vector has magnitude and direction; this uses the word 'vector' but is unrelated to embeddings."),
    CorpusItem("doc-10", "Latency is per-request delay measured end-to-end. Throughput is requests per second; systems often trade latency for throughput under load."),
    CorpusItem("doc-11", "Structured logging: include consistent fields like timestamp, level, service, request_id, and context to improve searchability and analysis."),
    CorpusItem("doc-12", "Prompt engineering: crafting instructions, examples, and constraints to steer model outputs. Prompts may be ambiguous if not specific."),
    CorpusItem("doc-13", "Cosine similarity measures vector angle and is used to rank nearest neighbors in embedding spaces."),
    CorpusItem("doc-14", "A GPU accelerates parallel computations like matrix multiplications used in neural network inference."),
    CorpusItem("doc-15", "Retries with exponential backoff help when transient network failures occur; be mindful of idempotency when retrying operations."),
    CorpusItem("doc-16", "A reliable benchmark is repeatable, uses fixed inputs, and reports clear metrics such as p50/p95 latencies and error counts.\n\nLong example paragraph: repeatability requires seeding random generators and fixing tool versions. Without that, results can vary dramatically across runs."),
    CorpusItem("doc-17", "RAG retrieves relevant chunks, optionally filters by similarity thresholds, and conditions a language model on the retrieved context to answer questions."),
    CorpusItem("doc-18", "Compression reduces size at the cost of quality or compute; lossy vs lossless are tradeoffs. Examples include gzip, brotli, and image codecs."),
    CorpusItem("doc-19", "A schema defines data fields and types so services can agree on data shapes; schemas help validation and migrations."),
    CorpusItem("doc-20", "CLI design: exit codes, clear help text, and predictable flags. UX matters when automating via scripts."),
    CorpusItem("doc-21", "OCR_NO1SE_EXAMPLE: Th1s l1ne ha5 OCR n0i5e; characters look like 0 and O swapped; garbled hyphens - and— appear. Use this to test noisy matching."),
    CorpusItem("doc-22", "Search engine indexing is related to 'index', but focuses on inverted indexes, tokenization, and ranking rather than DB b-trees."),
    CorpusItem("doc-23", "Image indexing and thumbnail caches (near duplicate of doc-02, slightly reworded): thumbnails speed previews and reduce bandwidth."),
    CorpusItem("doc-24", "Ambiguous phrasing example: 'When should you retry?' could refer to network retries, job retries, or user action retries depending on context."),
]


# Keep queries similar to the original 20 but map to documents in the harder corpus.
BUILTIN_QUERIES: list[QueryItem] = [
    QueryItem("q01", "What does a database index do?", "doc-01"),
    QueryItem("q02", "Why is version control useful for teams?", "doc-03"),
    QueryItem("q03", "What is caching good for?", "doc-05"),
    QueryItem("q04", "Why write unit tests?", "doc-07"),
    QueryItem("q05", "How do vector databases work at a high level?", "doc-08"),
    QueryItem("q06", "What is the difference between latency and throughput?", "doc-10"),
    QueryItem("q07", "What is structured logging?", "doc-11"),
    QueryItem("q08", "What is prompt engineering?", "doc-12"),
    QueryItem("q09", "Why use a load balancer?", "doc-14"),
    QueryItem("q10", "What is OCR used for?", "doc-06"),
    QueryItem("q11", "Why chunk long documents before retrieval?", "doc-16"),
    QueryItem("q12", "How is cosine similarity used in embeddings?", "doc-13"),
    QueryItem("q13", "Why can a GPU speed up inference?", "doc-14"),
    QueryItem("q14", "When should a system retry a failed request?", "doc-15"),
    QueryItem("q15", "What makes a benchmark reliable?", "doc-16"),
    QueryItem("q16", "How does a RAG pipeline answer questions?", "doc-17"),
    QueryItem("q17", "What is the tradeoff of compression?", "doc-18"),
    QueryItem("q18", "Why define a schema?", "doc-19"),
    QueryItem("q19", "What makes a good CLI tool?", "doc-20"),
    QueryItem("q20", "What is the purpose of retries with backoff?", "doc-15"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare embedding models on a harder retrieval corpus.")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated embedding model names (defaults to mxbai-embed-large,bge-large,nomic-embed-text)",
    )
    parser.add_argument("--k", type=int, default=5, help="Top-k retrieval results to evaluate")
    parser.add_argument("--out", type=Path, help="Optional JSON output file")
    parser.add_argument("--show-queries", action="store_true", help="Print every query and its ranked results")
    return parser.parse_args()


def as_list_of_texts(items: Iterable[CorpusItem]) -> list[str]:
    return [item.text for item in items]


def extract_embeddings(response: Any) -> list[list[float]]:
    """Handle both `embed` and deprecated `embeddings` response shapes."""
    if isinstance(response, dict):
        if "embeddings" in response and response["embeddings"] is not None:
            embeddings = response["embeddings"]
            if embeddings and isinstance(embeddings[0], (int, float)):
                return [list(map(float, embeddings))]
            return [list(map(float, row)) for row in embeddings]
        if "embedding" in response and response["embedding"] is not None:
            embedding = response["embedding"]
            if embedding and isinstance(embedding[0], (int, float)):
                return [list(map(float, embedding))]
            return [list(map(float, row)) for row in embedding]

    embeddings = getattr(response, "embeddings", None)
    if embeddings is not None:
        return [list(map(float, row)) for row in embeddings]

    embedding = getattr(response, "embedding", None)
    if embedding is not None:
        if embedding and isinstance(embedding[0], (int, float)):
            return [list(map(float, embedding))]
        return [list(map(float, row)) for row in embedding]

    raise TypeError(f"Unsupported Ollama embedding response shape: {type(response)!r}")


def embed_texts(model: str, texts: list[str]) -> tuple[np.ndarray, float]:
    started = time.perf_counter()

    def call_embed(payload: list[str]) -> Any:
        return ollama.embed(model=model, input=payload, truncate=True)

    try:
        response = call_embed(texts)
        vectors = np.asarray(extract_embeddings(response), dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
    except Exception as batch_error:
        if len(texts) == 1:
            try:
                response = ollama.embeddings(model=model, prompt=texts[0])
                vectors = np.asarray(extract_embeddings(response), dtype=np.float32)
            except Exception:
                raise batch_error
        else:
            vectors_list: list[np.ndarray] = []
            first_error: Exception | None = batch_error
            for text in texts:
                try:
                    response = call_embed([text])
                    vector = np.asarray(extract_embeddings(response), dtype=np.float32)
                except Exception:
                    try:
                        response = ollama.embeddings(model=model, prompt=text)
                        vector = np.asarray(extract_embeddings(response), dtype=np.float32)
                    except Exception as single_error:
                        if first_error is None:
                            first_error = single_error
                        raise first_error
                if vector.ndim == 2:
                    vector = vector[0]
                vectors_list.append(vector)

            vectors = np.stack(vectors_list, axis=0)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    vectors = np.nan_to_num(vectors, nan=0.0, posinf=0.0, neginf=0.0)
    if vectors.ndim == 1:
        vectors = vectors.reshape(1, -1)
    return vectors, elapsed_ms


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-12, None)
    return matrix / norms


def cosine_scores(query_vector: np.ndarray, doc_vectors: np.ndarray) -> np.ndarray:
    query_vector = query_vector.reshape(1, -1)
    return (query_vector @ doc_vectors.T).ravel()


def reciprocal_rank(ranked_doc_ids: list[str], relevant_doc_id: str) -> float:
    try:
        rank = ranked_doc_ids.index(relevant_doc_id) + 1
    except ValueError:
        return 0.0
    return 1.0 / rank


def benchmark_model(model: str, corpus: list[CorpusItem], queries: list[QueryItem], k: int, show_queries: bool) -> dict[str, Any]:
    print(f"\nModel: {model}")

    corpus_texts = as_list_of_texts(corpus)
    corpus_vectors, corpus_latency_ms = embed_texts(model, corpus_texts)
    corpus_vectors = normalize_rows(corpus_vectors)

    print(f"  corpus embedded: {len(corpus)} items in {corpus_latency_ms:.1f} ms")

    doc_ids = [item.doc_id for item in corpus]
    results: list[QueryResult] = []
    query_latencies: list[float] = []

    for query_item in queries:
        started = time.perf_counter()
        error: str | None = None
        topk_doc_ids: list[str] = []
        top1_doc_id = ""
        top1_score = float("nan")

        try:
            query_vectors, _ = embed_texts(model, [query_item.query])
            query_vector = normalize_rows(query_vectors)[0]
            scores = cosine_scores(query_vector, corpus_vectors)
            ranked_indices = np.argsort(scores)[::-1]
            topk_indices = ranked_indices[: max(k, 1)]
            topk_doc_ids = [doc_ids[index] for index in topk_indices]
            top1_doc_id = topk_doc_ids[0]
            top1_score = float(scores[topk_indices[0]])
        except Exception as exc:
            error = str(exc)

        latency_ms = (time.perf_counter() - started) * 1000.0
        if error is None:
            query_latencies.append(latency_ms)

        result = QueryResult(
            query_id=query_item.query_id,
            query=query_item.query,
            relevant_doc_id=query_item.relevant_doc_id,
            top1_doc_id=top1_doc_id,
            topk_doc_ids=topk_doc_ids,
            top1_score=top1_score,
            hit_at_1=(top1_doc_id == query_item.relevant_doc_id),
            hit_at_k=(query_item.relevant_doc_id in topk_doc_ids),
            reciprocal_rank=reciprocal_rank(topk_doc_ids, query_item.relevant_doc_id),
            latency_ms=latency_ms,
            error=error,
        )
        results.append(result)

        if show_queries:
            if error:
                print(f"  [{query_item.query_id}] ERROR: {error}")
            else:
                ranked_preview = ", ".join(topk_doc_ids)
                print(f"  [{query_item.query_id}] {latency_ms:.1f} ms | top1={top1_doc_id} | top{k}=[{ranked_preview}]")

    successful = [result for result in results if result.error is None]
    p50 = percentile(query_latencies, 50) if query_latencies else float("nan")
    p95 = percentile(query_latencies, 95) if query_latencies else float("nan")
    recall_at_1 = sum(1 for result in successful if result.hit_at_1) / len(successful) if successful else 0.0
    recall_at_k = sum(1 for result in successful if result.hit_at_k) / len(successful) if successful else 0.0
    mrr = sum(result.reciprocal_rank for result in successful) / len(successful) if successful else 0.0

    summary = {
        "model": model,
        "corpus_latency_ms": corpus_latency_ms,
        "query_latency_ms": query_latencies,
        "query_latency_p50_ms": p50,
        "query_latency_p95_ms": p95,
        "recall_at_1": recall_at_1,
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "successful_queries": len(successful),
        "total_queries": len(queries),
        "results": [asdict(result) for result in results],
    }

    print(
        f"  recall@1={recall_at_1:.3f}  recall@{k}={recall_at_k:.3f}  mrr={mrr:.3f}  "
        f"p50={p50:.1f} ms  p95={p95:.1f} ms"
    )
    return summary


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    if pct <= 0:
        return values[0]
    if pct >= 100:
        return values[-1]
    index = max(0, min(len(values) - 1, math.ceil((pct / 100.0) * len(values)) - 1))
    return values[index]


def print_summary_table(summaries: list[dict[str, Any]], k: int) -> None:
    print("\nSummary")
    print("model                 recall@1  recall@%d    mrr    p50_ms   p95_ms   corpus_ms" % k)
    print("--------------------   --------  ---------  -----  -------  -------  ---------")
    for summary in summaries:
        print(
            f"{summary['model'][:20]:20}   "
            f"{summary['recall_at_1']:.3f}     "
            f"{summary['recall_at_k']:.3f}    "
            f"{summary['mrr']:.3f}  "
            f"{summary['query_latency_p50_ms']:.1f}   "
            f"{summary['query_latency_p95_ms']:.1f}   "
            f"{summary['corpus_latency_ms']:.1f}"
        )


def main() -> int:
    args = parse_args()
    models = [model.strip() for model in args.models.split(",") if model.strip()]
    if not models:
        print("No models provided.")
        return 1

    print("Benchmarking local embedding models on a harder synthetic retrieval corpus")
    print(f"Models: {models}")
    print(f"Top-k: {args.k}")
    print("Dataset: built-in harder synthetic retrieval set")

    summaries: list[dict[str, Any]] = []
    for model in models:
        try:
            summary = benchmark_model(model, BUILTIN_CORPUS, BUILTIN_QUERIES, args.k, args.show_queries)
        except Exception as exc:
            summary = {
                "model": model,
                "error": str(exc),
                "corpus_latency_ms": float("nan"),
                "query_latency_ms": [],
                "query_latency_p50_ms": float("nan"),
                "query_latency_p95_ms": float("nan"),
                "recall_at_1": 0.0,
                "recall_at_k": 0.0,
                "mrr": 0.0,
                "successful_queries": 0,
                "total_queries": len(BUILTIN_QUERIES),
                "results": [],
            }
            print(f"  ERROR: {summary['error']}")
        summaries.append(summary)

    print_summary_table(summaries, args.k)

    if args.out:
        payload = {
            "models": models,
            "k": args.k,
            "corpus": [asdict(item) for item in BUILTIN_CORPUS],
            "queries": [asdict(item) for item in BUILTIN_QUERIES],
            "summaries": summaries,
        }
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved results to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
