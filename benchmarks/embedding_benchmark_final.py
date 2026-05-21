"""Production-style embedding benchmark with stress tests and nDCG@10.

This script combines the simple benchmark and the harder synthetic corpus and
adds production-style stress tests: many distractors, long 2k-word chunks,
OCR-like noise, code snippets, tables/logs, and mixed domains. It also adds
ranking-quality metric nDCG@10 alongside recall/MRR and latency metrics.

Usage:
  python embedding_benchmark_final.py
  python embedding_benchmark_final.py --models mxbai-embed-large,bge-large,nomic-embed-text --k 10 --distractors 500
"""

from __future__ import annotations

import argparse
import math
import random
import time
import json
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
	ndcg_at_10: float
	latency_ms: float
	error: str | None = None


def make_ocr_noise(text: str, rng: random.Random) -> str:
	# Simple OCR-like substitutions applied randomly
	subs = [("o", "0"), ("O", "0"), ("l", "1"), ("I", "1"), ("rn", "m"), ("—", "-"), ("’", "'")]
	out = text
	for a, b in subs:
		if rng.random() < 0.25:
			out = out.replace(a, b)
	# randomly drop or duplicate punctuation
	if rng.random() < 0.15:
		out = out.replace(",", "")
	return out


def make_long_chunk(paragraph: str, words: int) -> str:
	# repeat paragraph until reaching target word count
	parts = []
	while sum(len(p.split()) for p in parts) < words:
		parts.append(paragraph)
	return "\n\n".join(parts)


def build_stress_corpus(num_distractors: int = 500, long_chunk_words: int = 2000, seed: int = 42) -> tuple[list[CorpusItem], list[QueryItem], dict[str, dict[str, int]]]:
	rng = random.Random(seed)

	# Base focused documents (primary relevant targets)
	base_docs = [
		("doc-core-01", "Database indexing: B-trees, hash indexes, and inverted indexes speed lookups."),
		("doc-core-02", "Version control: branches, merges, snapshots, and collaboration workflows."),
		("doc-core-03", "Caching strategies: LRU, LFU, TTL and consistency considerations in distributed caches."),
		("doc-core-04", "OCR system notes: common errors include 0/O, 1/l, and rn/m substitutions."),
		("doc-core-05", "Vector DBs and ANN: how embeddings are stored and queried with HNSW or IVF."),
		("doc-core-06", "Retries and exponential backoff: design for idempotency and throttling."),
		("doc-core-07", "Benchmark design: p50/p95 latencies, seeding, repeatability, and clear error metrics."),
		("doc-core-08", "RAG architecture: retrieve relevant chunks, filter, and condition model consumption."),
		("doc-core-09", "GPU acceleration: matrix multiply batching, CUDA kernels, and memory considerations."),
		("doc-core-10", "Structured data retrieval: logs and tables require different matching strategies than prose."),
	]

	corpus: list[CorpusItem] = [CorpusItem(doc_id, text) for doc_id, text in base_docs]

	# Add near-duplicates and partially overlapping docs
	for i, (doc_id, text) in enumerate(base_docs, start=1):
		if rng.random() < 0.7:
			dup_id = f"doc-dup-{i}"
			dup_text = text.replace(" ", " ") + " (near duplicate with minor edits)."
			corpus.append(CorpusItem(dup_id, dup_text))
		# partially relevant altered doc
		part_id = f"doc-partial-{i}"
		partial = text.split(".")[0] + "."  # keep first sentence only
		corpus.append(CorpusItem(part_id, partial + " This excerpt is loosely related."))

	# Add long chunk documents (2k words approx.)
	sample_par = "This paragraph discusses caching behavior and eviction policies in distributed systems."
	long_text = make_long_chunk(sample_par, long_chunk_words)
	corpus.append(CorpusItem("doc-long-01", long_text))

	# Add OCR-noisy documents
	ocr_example = "This line contains OCR confusions: O and 0, l and 1, rn and m. Use it to test noisy ingestion."
	for i in range(3):
		noisy = make_ocr_noise(ocr_example, rng)
		corpus.append(CorpusItem(f"doc-ocr-{i+1}", noisy))

	# Code snippets
	code_snippet = (
		"def fibonacci(n):\n"
		"    if n <= 1:\n"
		"        return n\n"
		"    a, b = 0, 1\n"
		"    for _ in range(n-1):\n"
		"        a, b = b, a + b\n"
		"    return b\n"
	)
	corpus.append(CorpusItem("doc-code-01", code_snippet))

	# Tables / logs
	table = (
		"time,status,service,latency_ms\n"
		"2026-01-01T00:00:00Z,OK,auth,23\n"
		"2026-01-01T00:00:01Z,ERROR,db,502\n"
		"2026-01-01T00:00:02Z,OK,cache,12\n"
	)
	corpus.append(CorpusItem("doc-table-01", table))

	# Mixed domains distractors: cooking, physics, travel, media -- share small overlapping words
	distractor_templates = [
		"This recipe uses sugar and salt to balance flavor and uses an indexing metaphor for ingredient ordering.",
		"In classical mechanics a vector has magnitude and direction; unrelated to embedding vectors but shares the word vector.",
		"Travel guide: index of attractions, maps, and routes with caching suggestions for offline viewing.",
		"Movie review: the plot indexes several character arcs and uses repetition like a long chunk to emphasize theme.",
	]

	for i in range(num_distractors):
		t = rng.choice(distractor_templates)
		# inject slight random noise to create many distinct distractors
		noise = " " + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz ") for _ in range(20))
		corpus.append(CorpusItem(f"doc-distractor-{i+1}", t + noise))

	# Add some near-duplicate thumbnails / image-index docs
	corpus.append(CorpusItem("doc-image-idx-01", "Image indexing and thumbnail caches reduce bandwidth and speed previews."))
	corpus.append(CorpusItem("doc-image-idx-02", "Thumbnail caches speed previews; image indexing uses metadata and tokens."))

	# Build queries targeting core docs (map some queries to long/ocr/code/table docs)
	queries = [
		QueryItem("q01", "What does a database index do?", "doc-core-01"),
		QueryItem("q02", "Why use version control for teams?", "doc-core-02"),
		QueryItem("q03", "What are eviction strategies for caches?", "doc-core-03"),
		QueryItem("q04", "How do OCR systems misread characters?", "doc-ocr-1" if any("doc-ocr-1" in c.doc_id for c in corpus) else "doc-ocr-1"),
		QueryItem("q05", "How do vector DBs perform ANN search?", "doc-core-05"),
		QueryItem("q06", "When should you retry operations with backoff?", "doc-core-06"),
		QueryItem("q07", "What makes a benchmark repeatable?", "doc-core-07"),
		QueryItem("q08", "How does RAG retrieve and condition context?", "doc-core-08"),
		QueryItem("q09", "Why use GPUs for inference?", "doc-core-09"),
		QueryItem("q10", "How do you search logs and tables?", "doc-table-01"),
		QueryItem("q11", "Explain a long-form discussion on caching and consistency.", "doc-long-01"),
		QueryItem("q12", "Show me an example code snippet for fibonacci.", "doc-code-01"),
		QueryItem("q13", "What are common OCR noise patterns?", "doc-ocr-1" if any(c.doc_id.startswith("doc-ocr-") for c in corpus) else "doc-ocr-1"),
		QueryItem("q14", "What is the difference between vector (physics) and vector (embeddings)?", "doc-core-05"),
		QueryItem("q15", "When should systems use caching?", "doc-core-03"),
		QueryItem("q16", "What is index in image thumbnails?", "doc-image-idx-01"),
		QueryItem("q17", "How to design a retry strategy?", "doc-core-06"),
		QueryItem("q18", "What does structured logging include?", "doc-core-10"),
		QueryItem("q19", "How to evaluate p95 latency in benchmarks?", "doc-core-07"),
		QueryItem("q20", "Ambiguous: When should you retry?", "doc-core-06"),
	]

	# Build a relevance grading map for nDCG (per query -> doc_id -> grade)
	relevance: dict[str, dict[str, int]] = {}
	for q in queries:
		rel = {}
		# primary doc gets grade 3
		rel[q.relevant_doc_id] = 3
		# near duplicates (prefixes doc-dup-* or doc-partial-*) get grade 2 or 1
		for c in corpus:
			if c.doc_id.startswith("doc-dup-") and q.relevant_doc_id in c.text:
				rel[c.doc_id] = 2
			if c.doc_id.startswith("doc-partial-") and q.relevant_doc_id in c.text:
				rel[c.doc_id] = 1
		# partially related core docs get grade 1
		for c in corpus:
			if c.doc_id != q.relevant_doc_id and q.relevant_doc_id.split("-")[1] in c.text:
				rel.setdefault(c.doc_id, 1)
		relevance[q.query_id] = rel

	return corpus, queries, relevance


def extract_embeddings(response: Any) -> list[list[float]]:
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


def chunk_text_by_words(text: str, max_tokens: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    chunks: list[str] = []
    for i in range(0, len(words), max_tokens):
        chunk = " ".join(words[i : i + max_tokens])
        chunks.append(chunk)
    return chunks


def embed_corpus_with_chunking(model: str, corpus: list[CorpusItem], batch_size: int = 32, embed_batch: int = 64, max_tokens: int = 2048) -> tuple[np.ndarray, float, dict[str, Any]]:
	"""Embed corpus by doc-level batching + chunking.

	Returns (doc_vectors, elapsed_ms, stats) where stats contains token counts and truncated counts.
	"""
	start_all = time.perf_counter()
	doc_vectors_list: list[np.ndarray] = []
	token_counts: list[int] = []
	truncated_docs = 0

	# process documents in batches (by document)
	for i in range(0, len(corpus), batch_size):
		batch_docs = corpus[i : i + batch_size]
		# prepare all chunks for this batch
		chunk_texts: list[str] = []
		chunk_to_doc: list[str] = []
		for doc in batch_docs:
			words = len(doc.text.split())
			token_counts.append(words)
			if words > max_tokens:
				truncated_docs += 1
			chunks = chunk_text_by_words(doc.text, max_tokens)
			for ch in chunks:
				chunk_texts.append(ch)
				chunk_to_doc.append(doc.doc_id)

		# embed chunks in sub-batches to avoid huge payloads
		chunk_vectors: list[np.ndarray] = []
		for j in range(0, len(chunk_texts), embed_batch):
			sub = chunk_texts[j : j + embed_batch]
			if not sub:
				continue
			vecs, _ = embed_texts(model, sub)
			for v in vecs:
				chunk_vectors.append(v)

		# average chunk vectors per document in this batch
		# build mapping doc_id -> list[vectors]
		from collections import defaultdict

		doc_map: dict[str, list[np.ndarray]] = defaultdict(list)
		for doc_id, vec in zip(chunk_to_doc, chunk_vectors):
			doc_map[doc_id].append(vec)

		for doc in batch_docs:
			vecs = doc_map.get(doc.doc_id, [])
			if not vecs:
				# fallback: embed the full text (shouldn't happen)
				v, _ = embed_texts(model, [doc.text])
				doc_vectors_list.append(v[0])
			else:
				avg = np.stack(vecs, axis=0).mean(axis=0)
				doc_vectors_list.append(avg)

	# stack into matrix
	all_vectors = np.stack(doc_vectors_list, axis=0).astype(np.float32)
	elapsed_ms = (time.perf_counter() - start_all) * 1000.0
	stats = {
		"avg_tokens": float(np.mean(token_counts)) if token_counts else 0.0,
		"max_tokens": int(np.max(token_counts)) if token_counts else 0,
		"truncated_docs": int(truncated_docs),
	}
	all_vectors = np.nan_to_num(all_vectors, nan=0.0, posinf=0.0, neginf=0.0)
	return all_vectors, elapsed_ms, stats


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


def dcg(relevances: list[float], k: int) -> float:
	dcg_val = 0.0
	for i, rel in enumerate(relevances[:k], start=1):
		dcg_val += (2 ** rel - 1) / math.log2(i + 1)
	return dcg_val


def ndcg_at_k(ranked_doc_ids: list[str], relevance_map: dict[str, int], k: int) -> float:
	# Build relevance list for the ranked docs
	rels = [relevance_map.get(doc_id, 0) for doc_id in ranked_doc_ids[:k]]
	ideal = sorted(relevance_map.values(), reverse=True)[:k]
	ideal_rels = ideal + [0] * max(0, k - len(ideal))
	idcg_val = dcg(ideal_rels, k)
	if idcg_val == 0:
		return 0.0
	return dcg(rels, k) / idcg_val


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


def benchmark_model(model: str, corpus: list[CorpusItem], queries: list[QueryItem], relevance_map: dict[str, dict[str, int]], k: int, show_queries: bool, batch_size: int = 32, embed_batch: int = 64, max_tokens: int = 2048, reranker: str | None = None) -> dict[str, Any]:
	print(f"\nModel: {model}")

	# Embed corpus with batching + chunking
	corpus_vectors, corpus_latency_ms, embed_stats = embed_corpus_with_chunking(model, corpus, batch_size=batch_size, embed_batch=embed_batch, max_tokens=max_tokens)
	corpus_vectors = normalize_rows(corpus_vectors)

	print(f"  corpus embedded: {len(corpus)} items in {corpus_latency_ms:.1f} ms")
	print(f"  tokens: avg={embed_stats['avg_tokens']:.1f} max={embed_stats['max_tokens']} truncated={embed_stats['truncated_docs']}")

	doc_ids = [item.doc_id for item in corpus]
	results: list[QueryResult] = []
	query_latencies: list[float] = []

	for query_item in queries:
		started = time.perf_counter()
		error: str | None = None
		topk_doc_ids: list[str] = []
		top1_doc_id = ""
		top1_score = float("nan")
		ndcg_score = 0.0

		try:
			query_vectors, _ = embed_texts(model, [query_item.query])
			query_vector = normalize_rows(query_vectors)[0]
			scores = cosine_scores(query_vector, corpus_vectors)
			ranked_indices = np.argsort(scores)[::-1]
			topk_indices = ranked_indices[: max(k, 1)]
			topk_doc_ids = [doc_ids[index] for index in topk_indices]
			top1_doc_id = topk_doc_ids[0]
			top1_score = float(scores[topk_indices[0]])
			# optional reranking using a second model (simulate cross-encoder by re-embedding)
			rel_map = relevance_map.get(query_item.query_id, {})
			if reranker:
				# embed query + candidates with reranker model
				cand_texts = [next(c.text for c in corpus if c.doc_id == d) for d in topk_doc_ids]
				vecs, _ = embed_texts(reranker, [query_item.query] + cand_texts)
				qv = normalize_rows(vecs[0:1])[0]
				cand_vs = normalize_rows(vecs[1:])
				rerank_scores = (qv @ cand_vs.T).ravel()
				# reorder topk_doc_ids by rerank_scores desc
				ranked_order = [d for _, d in sorted(zip(rerank_scores, topk_doc_ids), key=lambda x: x[0], reverse=True)]
				topk_doc_ids = ranked_order
				top1_doc_id = topk_doc_ids[0]
				ndcg_score = ndcg_at_k(topk_doc_ids, rel_map, 10)
			else:
				ndcg_score = ndcg_at_k(topk_doc_ids, rel_map, 10)
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
			ndcg_at_10=ndcg_score,
			latency_ms=latency_ms,
			error=error,
		)
		results.append(result)

		if show_queries:
			if error:
				print(f"  [{query_item.query_id}] ERROR: {error}")
			else:
				ranked_preview = ", ".join(topk_doc_ids[:10])
				print(f"  [{query_item.query_id}] {latency_ms:.1f} ms | top1={top1_doc_id} | ndcg@10={ndcg_score:.3f} | top{k}=[{ranked_preview}]")

	successful = [result for result in results if result.error is None]
	p50 = percentile(query_latencies, 50) if query_latencies else float("nan")
	p95 = percentile(query_latencies, 95) if query_latencies else float("nan")
	recall_at_1 = sum(1 for result in successful if result.hit_at_1) / len(successful) if successful else 0.0
	recall_at_k = sum(1 for result in successful if result.hit_at_k) / len(successful) if successful else 0.0
	mrr = sum(result.reciprocal_rank for result in successful) / len(successful) if successful else 0.0
	mean_ndcg = sum(result.ndcg_at_10 for result in successful) / len(successful) if successful else 0.0
	# compute nDCG@3 and recall@3
	mean_ndcg_3 = sum(ndcg_at_k(r.topk_doc_ids, relevance_map.get(r.query_id, {}), 3) for r in results if r.error is None) / len(successful) if successful else 0.0
	recall_at_3 = sum(1 for r in successful if r.relevant_doc_id in r.topk_doc_ids[:3]) / len(successful) if successful else 0.0

	summary = {
		"model": model,
		"corpus_latency_ms": corpus_latency_ms,
		"query_latency_ms": query_latencies,
		"query_latency_p50_ms": p50,
		"query_latency_p95_ms": p95,
		"recall_at_1": recall_at_1,
		"recall_at_k": recall_at_k,
		"recall_at_3": recall_at_3,
		"mrr": mrr,
		"mean_ndcg_at_10": mean_ndcg,
		"mean_ndcg_at_3": mean_ndcg_3,
		"embed_stats": embed_stats,
		"successful_queries": len(successful),
		"total_queries": len(queries),
		"results": [asdict(result) for result in results],
	}

	print(
		f"  recall@1={recall_at_1:.3f}  recall@{k}={recall_at_k:.3f}  mrr={mrr:.3f}  ndcg@10={mean_ndcg:.3f}  "
		f"p50={p50:.1f} ms  p95={p95:.1f} ms"
	)
	return summary


def print_summary_table(summaries: list[dict[str, Any]], k: int) -> None:
	print("\nSummary")
	print("model                 recall@1  recall@%d    mrr    ndcg@10   p50_ms   p95_ms   corpus_ms" % k)
	print("--------------------   --------  ---------  -----  -------  -------  -------  ---------")
	for summary in summaries:
		print(
			f"{summary['model'][:20]:20}   "
			f"{summary['recall_at_1']:.3f}     "
			f"{summary['recall_at_k']:.3f}    "
			f"{summary['mrr']:.3f}  "
			f"{summary['mean_ndcg_at_10']:.3f}   "
			f"{summary['query_latency_p50_ms']:.1f}   "
			f"{summary['query_latency_p95_ms']:.1f}   "
			f"{summary['corpus_latency_ms']:.1f}"
		)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Production-style embedding benchmark with stress tests and nDCG@10.")
	parser.add_argument(
		"--models",
		default=",".join(DEFAULT_MODELS),
		help="Comma-separated embedding model names",
	)
	parser.add_argument("--k", type=int, default=10, help="Top-k retrieval results to evaluate")
	parser.add_argument("--distractors", type=int, default=500, help="Number of synthetic distractor docs to add")
	parser.add_argument("--long-chunk-words", type=int, default=2000, help="Approx word count for long chunks")
	parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
	parser.add_argument("--batch-size", type=int, default=32, dest="batch_size", help="Document-level batch size for corpus embedding")
	parser.add_argument("--embed-batch-size", type=int, default=64, dest="embed_batch_size", help="Sub-batch size for chunk embedding calls")
	parser.add_argument("--max-tokens", type=int, default=2048, dest="max_tokens", help="Max tokens (approx words) per chunk before chunking/truncation")
	parser.add_argument("--reranker", type=str, default="", help="Optional reranker embedding model name to rerank top-k candidates")
	parser.add_argument("--out", type=Path, default=Path("embedding-benchmark-final-results.json"), help="Optional JSON output file")
	parser.add_argument("--show-queries", action="store_true", help="Print every query and its ranked results")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	models = [model.strip() for model in args.models.split(",") if model.strip()]
	if not models:
		print("No models provided.")
		return 1

	print("Building stress corpus...")
	corpus, queries, relevance = build_stress_corpus(num_distractors=args.distractors, long_chunk_words=args.long_chunk_words, seed=args.seed)
	print(f"Corpus size: {len(corpus)} documents; Queries: {len(queries)}")

	summaries: list[dict[str, Any]] = []
	for model in models:
		try:
			reranker_model = args.reranker.strip() or None
			summary = benchmark_model(
				model,
				corpus,
				queries,
				relevance,
				args.k,
				args.show_queries,
				batch_size=args.batch_size,
				embed_batch=args.embed_batch_size,
				max_tokens=args.max_tokens,
				reranker=reranker_model,
			)
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
				"mean_ndcg_at_10": 0.0,
				"successful_queries": 0,
				"total_queries": len(queries),
				"results": [],
			}
			print(f"  ERROR: {summary['error']}")
		summaries.append(summary)

	print_summary_table(summaries, args.k)

	if args.out:
		payload = {
			"models": models,
			"k": args.k,
			"distractors": args.distractors,
			"long_chunk_words": args.long_chunk_words,
			"seed": args.seed,
			"corpus_size": len(corpus),
			"queries": [asdict(q) for q in queries],
			"summaries": summaries,
		}
		args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
		print(f"\nSaved results to {args.out}")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())

