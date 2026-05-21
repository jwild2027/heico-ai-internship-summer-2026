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
import io
import re
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


@dataclass(frozen=True)
class PageRecord:
    page: int
    text: str
    ocr_used: bool
    native_text: str
    ocr_text: str
    ocr_quality: float
    ocr_confidence: float


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


def merge_page_text(native_text: str, ocr_text: str) -> str:
    native_clean = base.normalize_text(native_text)
    ocr_clean = base.normalize_text(ocr_text)

    if not native_clean:
        return ocr_clean
    if not ocr_clean:
        return native_clean
    if native_clean == ocr_clean:
        return native_clean

    if len(native_clean) >= len(ocr_clean) * 0.8:
        return f"{native_clean}\n\n{ocr_clean}"
    return ocr_clean


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


def extract_pages_pymupdf(pdf_path: Path, debug_dir: Path, ocr_debug: bool = True, save_images: bool = True) -> list[dict[str, Any]]:
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
                        selected_text = merge_page_text(native_text, ocr_text)
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
) -> None:
    pdf_path = resolve_pdf_path(pdf_path)
    pages = extract_pages_pymupdf(pdf_path, debug_dir=ocr_debug_dir, ocr_debug=ocr_debug, save_images=save_images)
    ocr_pages = sum(1 for page in pages if page.get("ocr_used"))
    if ocr_pages:
        print(f"OCR used on {ocr_pages}/{len(pages)} pages")
        print(f"OCR debug files: {ocr_debug_dir}")

    chunks = base.build_chunks(
        pages,
        target_words=chunk_words,
        max_words=max(chunk_words, base.DEFAULT_MAX_WORDS),
        overlap_blocks=base.DEFAULT_OVERLAP_BLOCKS,
        source_name=pdf_path.stem,
    )

    if not chunks:
        raise RuntimeError(f"No text chunks were extracted from {pdf_path}")

    enrich_chunk_metadata(chunks, pages)
    dump_chunks_to_disk(chunks, chunk_debug_dir)

    texts = [chunk.text for chunk in chunks]
    embeddings = base.embed_texts(model, texts, kind="passage", show_progress=True)

    collection = base.get_collection(persist_dir, collection_name)
    collection.upsert(
        ids=[chunk.chunk_id for chunk in chunks],
        documents=[f"{chunk.title}\n\n{chunk.text}".strip() for chunk in chunks],
        metadatas=[chunk.metadata for chunk in chunks],
        embeddings=embeddings,
    )

    print(f"Ingested {len(chunks)} chunks from {pdf_path.name} into {persist_dir / collection_name}")
    print(f"Chunk debug files: {chunk_debug_dir}")


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

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
