#!/usr/bin/env python3
"""Ingest PDFs with PyMuPDF, embed chunks with BGE, and store/query ChromaDB.

Examples:
  python tools/pymupdf_bge_chroma_cli.py ingest --pdf path/to/file.pdf
  python tools/pymupdf_bge_chroma_cli.py query --query "what is the warranty period?"

The default embedding model is `bge-large` through Ollama. The script stores
chunk embeddings in a persistent ChromaDB directory so you can ingest once and
query many times.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
import ollama
import numpy as np
import unicodedata


DEFAULT_MODEL = "bge-large"
DEFAULT_COLLECTION = "pdf_chunks"
DEFAULT_PERSIST_DIR = Path("chroma_db")
DEFAULT_TARGET_WORDS = 220
DEFAULT_MAX_WORDS = 320
DEFAULT_OVERLAP_BLOCKS = 1
DEFAULT_FETCH_K = 15
BGE_PASSAGE_PREFIX = "passage:"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages:"
OCR_DPI = 220
OCR_MIN_WORDS = 12
OCR_MIN_ALPHA_CHARS = 80
COMMON_TESSERACT_PATHS = [
    Path(r"C:\Users\juswil\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is", "it", "of",
    "on", "or", "that", "the", "this", "to", "what", "when", "where", "which", "why", "with",
}

SECTION_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\s+.+|[A-Z0-9][A-Z0-9 ,./;:()&'\"\-]{7,}|[A-Z][A-Z0-9 ,./;:()&'\"\-]{7,})$"
)

# Backwards-compatible CLI defaults
DEFAULT_CHUNK_WORDS = DEFAULT_TARGET_WORDS
DEFAULT_CHUNK_OVERLAP = DEFAULT_OVERLAP_BLOCKS


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    title: str
    text: str
    metadata: dict[str, Any]


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\ufeff", "").replace("\ufffe", "").replace("￾", "")
    text = text.replace("\u00ad", "")
    text = re.sub(r"-\s*\n\s*", "", text)
    # fix hyphenation with space (e.g. "sec- tion" -> "section")
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    # normalize unicode (ligatures, diacritics)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # strip OCR header/footer artifacts
    text = re.sub(r"—\$—", "", text)
    text = re.sub(r"\d+-\d+\s*—[^—\n]*—", "", text)
    # strip PDF chapter file headers e.g. "Ch 01.qxd 8/24/04 10:28 AM Page 1-2"
    text = re.sub(r"Ch\s+\d+\.qxd\s+[\d/]+\s+[\d:]+\s+[AP]M\s+Page\s+[\d-]+", "", text)
    return text.strip()


def normalize_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    line = line.replace("￾", "").replace("\u00ad", "")
    return line


def is_heading_line(line: str) -> bool:
    line = normalize_line(line)
    if not line:
        return False
    if len(line.split()) <= 14 and SECTION_HEADING_RE.match(line):
        return True
    if re.match(r"^\d+\.\d+\b", line):
        return True
    return False


def split_semantic_blocks(page_text: str) -> list[str]:
    cleaned = normalize_text(page_text)
    if not cleaned:
        return []

    blocks: list[str] = []
    current_lines: list[str] = []

    for raw_line in cleaned.splitlines():
        line = normalize_line(raw_line)
        if not line:
            if current_lines:
                blocks.append("\n".join(current_lines).strip())
                current_lines = []
            continue

        if is_heading_line(line) and current_lines:
            blocks.append("\n".join(current_lines).strip())
            current_lines = [line]
            continue

        current_lines.append(line)

    if current_lines:
        blocks.append("\n".join(current_lines).strip())

    return [block for block in blocks if block]


def strip_heading_from_block(block: str) -> str:
    """If the block starts with a heading-only first line, remove it."""
    lines = block.splitlines()
    if not lines:
        return block
    first = lines[0].strip()
    if is_heading_line(first) and len(first.split()) <= 12 and block_word_count(block) < 40:
        return "\n".join(lines[1:]).strip()
    return block


def block_word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


EMBED_WINDOW_WORDS = 300
EMBED_WINDOW_OVERLAP = 40


def chunk_into_windows(text: str, window_words: int = EMBED_WINDOW_WORDS, overlap: int = EMBED_WINDOW_OVERLAP) -> list[str]:
    words = re.findall(r"\S+", text)
    if not words:
        return []
    if len(words) <= window_words:
        return [" ".join(words).strip()]
    step = max(window_words - overlap, 1)
    windows: list[str] = []
    start = 0
    while start < len(words):
        w = words[start : start + window_words]
        if not w:
            break
        windows.append(" ".join(w).strip())
        start += step
    return windows


def extract_title(blocks: list[str]) -> str:
    heading_lines: list[str] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        first_line = lines[0]
        if is_heading_line(first_line):
            heading_lines.append(first_line)
        else:
            break
    return " | ".join(heading_lines).strip()


def clean_query(query: str) -> str:
    query = normalize_text(query)
    query = re.sub(r"\s+", " ", query).strip()
    return query


def query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for term in re.findall(r"[A-Za-z0-9_.-]+", query.lower()):
        if term in STOPWORDS:
            continue
        if len(term) <= 2 and not any(ch.isdigit() for ch in term):
            continue
        terms.append(term)
    return terms


def format_passage_for_embedding(text: str) -> str:
    return f"{BGE_PASSAGE_PREFIX} {text.strip()}"


def format_query_for_embedding(query: str) -> str:
    clean = clean_query(query)
    return f"{BGE_QUERY_PREFIX} {clean}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest PDFs with PyMuPDF, embed with BGE, and query ChromaDB."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Extract, chunk, embed, and store a PDF.")
    ingest_parser.add_argument("--pdf", type=Path, required=True, help="Path to the PDF file.")
    ingest_parser.add_argument(
        "--persist-dir",
        type=Path,
        default=DEFAULT_PERSIST_DIR,
        help="Directory for the persistent ChromaDB store.",
    )
    ingest_parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="ChromaDB collection name.",
    )
    ingest_parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Ollama embedding model to use.",
    )
    ingest_parser.add_argument("--chunk-words", type=int, default=DEFAULT_CHUNK_WORDS)
    ingest_parser.add_argument("--overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)

    query_parser = subparsers.add_parser("query", help="Search the stored chunks.")
    query_parser.add_argument("--query", required=True, help="Query text.")
    query_parser.add_argument(
        "--persist-dir",
        type=Path,
        default=DEFAULT_PERSIST_DIR,
        help="Directory for the persistent ChromaDB store.",
    )
    query_parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="ChromaDB collection name.",
    )
    query_parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Ollama embedding model to use.",
    )
    query_parser.add_argument("--top-k", type=int, default=5, help="How many chunks to return.")
    query_parser.add_argument("--rerank", action="store_true", help="Apply cross-encoder reranker to top candidates.")
    query_parser.add_argument("--rerank-model", default="bge-reranker-large", help="Ollama reranker model to use when --rerank is set.")

    return parser.parse_args()


def resolve_pdf_path(pdf_path: Path) -> Path:
    pdf_path = pdf_path.expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF path is not a file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Unsupported file type: {pdf_path.suffix}. Expected a PDF.")
    return pdf_path


def find_tesseract_cmd() -> str | None:
    """Resolve the Tesseract executable from env, PATH, or common Windows install paths."""
    explicit = os.getenv("TESSERACT_CMD", "").strip()
    if explicit:
        candidate = Path(explicit.strip('"'))
        if candidate.is_dir():
            candidate = candidate / "tesseract.exe"
        if candidate.exists():
            return str(candidate)
        print(f"[warning] TESSERACT_CMD is set but the file does not exist: {candidate}")

    on_path = shutil.which("tesseract")
    if on_path:
        return on_path

    for candidate in COMMON_TESSERACT_PATHS:
        if candidate.exists():
            return str(candidate)

    return None


def configure_tesseract() -> str | None:
    """Configure pytesseract once if the executable can be found."""
    cmd = find_tesseract_cmd()
    if not cmd:
        return None

    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = cmd
    except Exception:
        return cmd

    return cmd


def native_text_looks_poor(text: str) -> bool:
    """Heuristic: OCR pages that are too short or look fragmented after extraction."""
    stripped = normalize_text(text)
    if not stripped:
        return True

    words = re.findall(r"\S+", stripped)
    alpha_chars = len(re.findall(r"[A-Za-z]", stripped))
    hyphen_breaks = len(re.findall(r"\w-\s+\w", text))

    if len(words) < OCR_MIN_WORDS:
        return True
    if alpha_chars < OCR_MIN_ALPHA_CHARS:
        return True
    if hyphen_breaks >= 3:
        return True
    return False


def ocr_page_text(page: Any, dpi: int = OCR_DPI) -> str:
    """Render a PDF page to an image and OCR it with Tesseract."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "OCR fallback needs pytesseract and Pillow. Install them with: pip install pytesseract pillow"
        ) from error

    tesseract_cmd = configure_tesseract()
    if not tesseract_cmd:
        raise RuntimeError(
            "Tesseract executable not found. Install the Tesseract desktop app and either add it to PATH or set TESSERACT_CMD. "
            r"Expected common locations include C:\Program Files\Tesseract-OCR\tesseract.exe"
        )

    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
    image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    return pytesseract.image_to_string(image)


def extract_pages_pymupdf(pdf_path: Path) -> list[dict[str, Any]]:
    import fitz

    pages: list[dict[str, Any]] = []
    tesseract_cmd = configure_tesseract()
    if not tesseract_cmd:
        print(
            "[warning] Tesseract executable not found; OCR fallback will be skipped. "
            "Set TESSERACT_CMD to the full path of tesseract.exe or add it to PATH if you want OCR."
        )
    with fitz.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc, start=1):
            native_text = page.get_text("text") or ""
            ocr_used = False

            if native_text_looks_poor(native_text) and tesseract_cmd:
                try:
                    ocr_text = ocr_page_text(page)
                    if normalize_text(ocr_text):
                        native_text = ocr_text
                        ocr_used = True
                except Exception as error:
                    print(f"[warning] OCR failed on page {index}: {error}")

            pages.append({"page": index, "text": native_text, "ocr_used": ocr_used})
    return pages


def build_chunks(pages: list[dict[str, Any]], target_words: int, max_words: int, overlap_blocks: int, source_name: str) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    chunk_number = 1
    current_blocks: list[str] = []
    current_pages: list[int] = []
    current_title_parts: list[str] = []

    def flush_chunk() -> None:
        nonlocal chunk_number, current_blocks, current_pages, current_title_parts
        if not current_blocks:
            return

        title = extract_title(current_blocks) or "Untitled section"
        body_blocks = [strip_heading_from_block(b) for b in current_blocks]
        body_text = "\n\n".join([b for b in body_blocks if b]).strip()
        if not body_text:
            current_blocks = []
            current_pages = []
            current_title_parts = []
            return

        page_start = min(current_pages) if current_pages else 0
        page_end = max(current_pages) if current_pages else 0
        metadata = {
            "source": source_name,
            "page_start": page_start,
            "page_end": page_end,
            "section_title": title,
            "word_count": block_word_count(body_text),
            "block_count": len(current_blocks),
        }
        chunks.append(
            ChunkRecord(
                chunk_id=f"{source_name}:chunk-{chunk_number:04d}",
                title=title,
                text=body_text,
                metadata=metadata,
            )
        )
        chunk_number += 1

        carry_blocks = current_blocks[-overlap_blocks:] if overlap_blocks > 0 else []
        carry_blocks = [strip_heading_from_block(b) for b in carry_blocks]
        carry_pages = current_pages[-overlap_blocks:] if overlap_blocks > 0 else []
        current_blocks = list(carry_blocks)
        current_pages = list(carry_pages)
        current_title_parts = []

    for page in pages:
        page_number = int(page["page"])
        page_text = str(page["text"])
        if not page_text.strip():
            continue

        for block in split_semantic_blocks(page_text):
            block = block.strip()
            if not block:
                continue

            first_line = block.splitlines()[0].strip()
            block_words = block_word_count(block)

            if is_heading_line(first_line) and block_words < 20:
                current_title_parts.append(first_line)
                current_blocks.append(block)
                current_pages.append(page_number)
                continue

            if current_blocks and block_words + block_word_count("\n\n".join(current_blocks)) > max_words:
                flush_chunk()

            if not current_blocks:
                if current_title_parts and first_line not in current_title_parts:
                    current_title_parts.append(first_line)
                current_blocks.append(block)
                current_pages.append(page_number)
                continue

            current_blocks.append(block)
            current_pages.append(page_number)

            if block_word_count("\n\n".join(current_blocks)) >= target_words and block_words > 0:
                flush_chunk()

    flush_chunk()

    return chunks


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


def embed_texts(model: str, texts: list[str], *, kind: str = "passage", show_progress: bool = False) -> list[list[float]]:
    """Embed each text. For long passages, split into windows, embed windows, then average."""
    out_vectors: list[list[float]] = []

    if kind == "query":
        payloads = [format_query_for_embedding(t) for t in texts]
        response = ollama.embed(model=model, input=payloads, truncate=True)
        return extract_embeddings(response)

    for idx, text in enumerate(texts, start=1):
        passage = format_passage_for_embedding(text)
        windows = chunk_into_windows(passage)
        if not windows:
            out_vectors.append([0.0])
            continue

        if show_progress:
            print(f"Embedding passage {idx}/{len(texts)} ({len(windows)} windows)")

        if len(windows) == 1:
            try:
                response = ollama.embed(model=model, input=[windows[0]], truncate=True)
                vec = extract_embeddings(response)[0]
                out_vectors.append(vec)
                continue
            except Exception:
                pass

        try:
            response = ollama.embed(model=model, input=windows, truncate=True)
            window_vecs = extract_embeddings(response)
        except Exception:
            window_vecs = []
            for w_i, w in enumerate(windows, start=1):
                if show_progress:
                    print(f"  embedding window {w_i}/{len(windows)}")
                response = ollama.embed(model=model, input=[w], truncate=True)
                window_vecs.append(extract_embeddings(response)[0])

        mat = np.asarray(window_vecs, dtype=np.float64)
        avg = np.mean(mat, axis=0)
        norm = np.linalg.norm(avg) + 1e-12
        avg = (avg / norm).astype(float)
        out_vectors.append(list(avg.tolist()))

    return out_vectors


def get_collection(persist_dir: Path, collection_name: str):
    client = chromadb.PersistentClient(path=str(persist_dir))
    return client.get_or_create_collection(name=collection_name)


def ingest_pdf(pdf_path: Path, persist_dir: Path, collection_name: str, model: str, chunk_words: int, overlap: int) -> None:
    pdf_path = resolve_pdf_path(pdf_path)
    pages = extract_pages_pymupdf(pdf_path)
    ocr_pages = sum(1 for page in pages if page.get("ocr_used"))
    if ocr_pages:
        print(f"OCR used on {ocr_pages}/{len(pages)} pages")
    chunks = build_chunks(
        pages,
        target_words=chunk_words,
        max_words=max(chunk_words, DEFAULT_MAX_WORDS),
        overlap_blocks=DEFAULT_OVERLAP_BLOCKS,
        source_name=pdf_path.stem,
    )

    if not chunks:
        raise RuntimeError(f"No text chunks were extracted from {pdf_path}")

    texts = [chunk.text for chunk in chunks]
    embeddings = embed_texts(model, texts, kind="passage", show_progress=True)

    collection = get_collection(persist_dir, collection_name)
    collection.upsert(
        ids=[chunk.chunk_id for chunk in chunks],
        documents=[f"{chunk.title}\n\n{chunk.text}".strip() for chunk in chunks],
        metadatas=[chunk.metadata for chunk in chunks],
        embeddings=embeddings,
    )

    print(f"Ingested {len(chunks)} chunks from {pdf_path.name} into {persist_dir / collection_name}")


def format_result(index: int, document: str, metadata: dict[str, Any], distance: float | None) -> str:
    score_text = f", distance={distance:.4f}" if distance is not None else ""
    source = metadata.get("source", "unknown")
    page_start = metadata.get("page_start", metadata.get("page", "?"))
    page_end = metadata.get("page_end", metadata.get("page", "?"))
    title = metadata.get("section_title", "Untitled section")
    preview = document.replace("\n", " ").strip()
    if len(preview) > 500:
        preview = preview[:497] + "..."
    page_label = f"p{page_start}" if page_start == page_end else f"p{page_start}-p{page_end}"
    return f"[{index}] {source} {page_label}{score_text}\n{title}\n{preview}"


def lexical_rerank(query: str, results: dict[str, list[list[Any]]], top_k: int) -> list[tuple[str, dict[str, Any], float | None, int]]:
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    terms = query_terms(query)

    scored: list[tuple[str, dict[str, Any], float | None, int]] = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        cleaned_doc = document.lower()
        overlap_score = 0
        for term in terms:
            if term in cleaned_doc:
                overlap_score += 2 if term.isdigit() or "." in term else 1
        scored.append((document, metadata or {}, distance, overlap_score))

    scored.sort(key=lambda item: (-item[3], item[2] if item[2] is not None else 9999.0))

    # Deduplicate by page range so overlap chunks from the same page
    # don't consume multiple result slots.
    seen_pages: set[tuple] = set()
    deduped: list = []
    for item in scored:
        meta = item[1] or {}
        page_key = (meta.get("page_start"), meta.get("page_end"))
        if page_key not in seen_pages:
            seen_pages.add(page_key)
            deduped.append(item)

    return deduped[:top_k]


def cross_encoder_rerank(query: str, results: dict[str, list[list[Any]]], model: str, top_k: int) -> list[tuple[str, dict[str, Any], float | None, float]]:
    """Use an Ollama cross-encoder-style model to score each candidate."""
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    try:
        from sentence_transformers import CrossEncoder

        try:
            reranker = CrossEncoder(model)
        except Exception as e:
            print("[warning] failed to load CrossEncoder model:", str(e))
            print("[hint] This often happens when the environment cannot download from Hugging Face (SSL / network issue).")
            print(" - Option A: install 'sentence-transformers' and ensure network/SSL is functional (pip install certifi).")
            print(" - Option B: download a reranker model on a machine with working TLS and provide a local path via --rerank-model /path/to/model")
            print(" - Example PowerShell step to use certifi's CA bundle:")
            print(r"   $env:SSL_CERT_FILE = (python -c \"import certifi; print(certifi.where())\")")
            print("Common smaller alternative (more likely to download): 'cross-encoder/ms-marco-MiniLM-L-6-v2'")
            print("Falling back to lexical rerank.")
            lex = lexical_rerank(query, results, top_k)
            return [(doc, meta, dist, float(score), "lexical") for (doc, meta, dist, score) in lex]

        pairs = [[query, doc] for doc in documents]
        scores = reranker.predict(pairs)
        scored = []
        for doc, meta, dist, sc in zip(documents, metadatas, distances, scores):
            scored.append((doc, meta or {}, dist, float(sc), "cross"))
        scored.sort(key=lambda item: -item[3])
        return scored[:top_k]
    except ModuleNotFoundError:
        print("[info] 'sentence-transformers' is not installed. Install it with: pip install sentence-transformers")
        print("Falling back to lexical rerank.")
        lex = lexical_rerank(query, results, top_k)
        return [(doc, meta, dist, float(score), "lexical") for (doc, meta, dist, score) in lex]
    except Exception as e:
        print("[warning] CrossEncoder reranker failed:", str(e))
        print("Falling back to lexical rerank.")
        lex = lexical_rerank(query, results, top_k)
        return [(doc, meta, dist, float(score), "lexical") for (doc, meta, dist, score) in lex]


def query_collection(persist_dir: Path, collection_name: str, model: str, query: str, top_k: int, fetch_k: int, rerank: bool = False, rerank_model: str | None = None) -> None:
    collection = get_collection(persist_dir, collection_name)
    if collection.count() == 0:
        print(f"No chunks found in {persist_dir / collection_name}. Run ingest first.")
        return

    query_embedding = embed_texts(model, [query], kind="query")[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=max(top_k, fetch_k),
        include=["documents", "metadatas", "distances"],
    )

    if rerank and rerank_model:
        try:
            reranked = cross_encoder_rerank(query, results, model=rerank_model, top_k=top_k)
        except Exception:
            reranked = lexical_rerank(query, results, top_k)
    else:
        reranked = lexical_rerank(query, results, top_k)

    print(f"Query: {query}\n")
    for index, item in enumerate(reranked, start=1):
        if len(item) == 5:
            document, metadata, distance, score, method = item
        else:
            document, metadata, distance, score = item
            method = "lexical"

        print(format_result(index, document, metadata or {}, distance))
        if method == "lexical":
            print(f"overlap_score={int(score)} (lexical)")
        else:
            print(f"score={score:.4f} ({method})")

        if index != len(reranked):
            print()


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
        )
        return

    if args.command == "query":
        query_collection(
            persist_dir=args.persist_dir,
            collection_name=args.collection,
            model=args.model,
            query=args.query,
            top_k=args.top_k,
            fetch_k=DEFAULT_FETCH_K,
            rerank=args.rerank,
            rerank_model=(args.rerank_model if getattr(args, "rerank_model", None) else None),
        )
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()