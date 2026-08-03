"""scripts/operations/ingestion/ingest_batch.py — Batch ingest all PDFs in a directory into the RAG DB.

Skips PDFs that are already in the DB (same checksum).
Logs per-file results and prints a summary at the end.

Usage:
    python scripts/operations/ingestion/ingest_batch.py --dir data/nist_pdfs --db-path rag.db
    python scripts/operations/ingestion/ingest_batch.py --dir data/nist_pdfs --db-path rag.db --workers 1
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.storage import RAGDatabase
from src.db.ingest_bridge import ingest_pdf_to_db
import tools.pymupdf_bge_chroma_cli as base


DEFAULT_DB_PATH        = Path("rag.db")
DEFAULT_PERSIST_DIR    = base.DEFAULT_PERSIST_DIR
DEFAULT_COLLECTION     = base.DEFAULT_COLLECTION
DEFAULT_MODEL          = base.DEFAULT_MODEL
DEFAULT_CHUNK_WORDS    = base.DEFAULT_CHUNK_WORDS
DEFAULT_OVERLAP        = base.DEFAULT_CHUNK_OVERLAP
DEFAULT_OCR_DEBUG_DIR  = Path("ocr_debug")
DEFAULT_CHUNK_DEBUG_DIR= Path("chunk_debug")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch ingest PDFs into the RAG database."
    )
    parser.add_argument("--dir",        type=Path, required=True,
                        help="Directory containing PDF files to ingest.")
    parser.add_argument("--db-path",    type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--persist-dir",type=Path, default=DEFAULT_PERSIST_DIR)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--model",      default=DEFAULT_MODEL)
    parser.add_argument("--chunk-words",type=int, default=DEFAULT_CHUNK_WORDS)
    parser.add_argument("--overlap",    type=int, default=DEFAULT_OVERLAP)
    parser.add_argument("--no-ocr-debug", action="store_true",
                        help="Disable OCR debug output (faster, less disk usage).")
    parser.add_argument("--glob",       default="*.pdf",
                        help="Glob pattern to match files (default: *.pdf).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    pdf_dir = args.dir.resolve()
    if not pdf_dir.exists():
        print(f"[error] Directory not found: {pdf_dir}")
        sys.exit(1)

    pdfs = sorted(pdf_dir.glob(args.glob))
    if not pdfs:
        print(f"[error] No PDFs found in {pdf_dir} matching '{args.glob}'")
        sys.exit(1)

    print(f"\nBatch ingest: {len(pdfs)} PDFs from {pdf_dir}")
    print(f"DB:         {args.db_path}")
    print(f"Collection: {args.collection}")
    print(f"Model:      {args.model}")
    print()

    db = RAGDatabase(args.db_path)

    results = []
    total_start = time.perf_counter()

    for i, pdf_path in enumerate(pdfs, start=1):
        print(f"[{i:02d}/{len(pdfs)}] {pdf_path.name}")
        t0 = time.perf_counter()
        try:
            summary = ingest_pdf_to_db(
                pdf_path=pdf_path,
                db=db,
                persist_dir=args.persist_dir,
                collection_name=args.collection,
                model=args.model,
                chunk_words=args.chunk_words,
                overlap=args.overlap,
                ocr_debug_dir=DEFAULT_OCR_DEBUG_DIR,
                chunk_debug_dir=DEFAULT_CHUNK_DEBUG_DIR,
                ocr_debug=not args.no_ocr_debug,
                save_images=False,
            )
            elapsed = time.perf_counter() - t0
            status = "new" if summary["is_new"] else "skip"
            print(
                f"         [{status}] {summary['page_count']} pages, "
                f"{summary['chunk_count']} chunks — {elapsed:.1f}s"
            )
            results.append({
                "file": pdf_path.name,
                "status": status,
                "pages": summary["page_count"],
                "chunks": summary["chunk_count"],
                "elapsed": elapsed,
                "error": None,
            })
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            print(f"         [FAIL] {exc} — {elapsed:.1f}s")
            results.append({
                "file": pdf_path.name,
                "status": "error",
                "pages": 0,
                "chunks": 0,
                "elapsed": elapsed,
                "error": str(exc),
            })

        print()

    total_elapsed = time.perf_counter() - total_start

    # Summary
    new_count   = sum(1 for r in results if r["status"] == "new")
    skip_count  = sum(1 for r in results if r["status"] == "skip")
    error_count = sum(1 for r in results if r["status"] == "error")
    total_pages  = sum(r["pages"] for r in results)
    total_chunks = sum(r["chunks"] for r in results)

    print("=" * 60)
    print(f"Batch complete: {len(pdfs)} files in {total_elapsed/60:.1f} min")
    print(f"  Ingested: {new_count}  |  Skipped (exists): {skip_count}  |  Failed: {error_count}")
    print(f"  Total pages: {total_pages}  |  Total chunks: {total_chunks}")

    if error_count:
        print("\nFailed files:")
        for r in results:
            if r["status"] == "error":
                print(f"  {r['file']}: {r['error']}")

    status = db.status()
    print(f"\nDB now contains: {status['documents']} docs, "
          f"{status['chunks']} chunks, "
          f"{status['embedded_chunks']} embedded")
    print("=" * 60)
    db.close()


if __name__ == "__main__":
    main()