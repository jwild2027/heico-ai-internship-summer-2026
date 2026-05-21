"""db/ingest_bridge.py — wires rag_benchmark.py's pipeline into the DB layer.

This is the ONLY file that needs to know about both rag_benchmark and db.storage.
rag_benchmark.py and pymupdf_bge_chroma_cli.py stay unchanged.

Usage (replaces direct calls to rag_benchmark.ingest_pdf):

    from db.ingest_bridge import ingest_pdf_to_db

    ingest_pdf_to_db(
        pdf_path=Path("my_doc.pdf"),
        db=RAGDatabase("rag.db"),
        persist_dir=Path("chroma_db"),
        collection_name="pdf_chunks",
        model="bge-large",
        chunk_words=220,
        overlap=1,
        ocr_debug_dir=Path("ocr_debug"),
        chunk_debug_dir=Path("chunk_debug"),
    )
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

# Ensure repo root is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.pymupdf_bge_chroma_cli as base  # noqa: E402
import rag_benchmark as bench                 # noqa: E402
from db.storage import RAGDatabase            # noqa: E402


def ingest_pdf_to_db(
    pdf_path: Path,
    db: RAGDatabase,
    persist_dir: Path,
    collection_name: str,
    model: str,
    chunk_words: int,
    overlap: int,
    ocr_debug_dir: Path,
    chunk_debug_dir: Path,
    ocr_debug: bool = True,
    save_images: bool = True,
    chunker_version: str = "semantic_v1",
) -> dict[str, Any]:
    """Ingest a PDF and persist everything to SQLite + Chroma.

    Returns a summary dict with doc_id, run_id, page_count, chunk_count.
    """
    pdf_path = base.resolve_pdf_path(pdf_path)

    # ----------------------------------------------------------------
    # 1. Register document (skip if same checksum already ingested)
    # ----------------------------------------------------------------
    doc_id, is_new = db.upsert_document(pdf_path)
    if not is_new:
        print(f"[db] Document already ingested (same checksum): {pdf_path.name} → {doc_id}")

    config = {
        "model": model,
        "chunk_words": chunk_words,
        "overlap": overlap,
        "chunker_version": chunker_version,
        "ocr_debug": ocr_debug,
    }
    run_id = db.start_ingestion_run(doc_id, config)
    db.set_document_status(doc_id, "ingesting")

    try:
        # ------------------------------------------------------------
        # 2. Extract pages (native + OCR + merge) via rag_benchmark
        # ------------------------------------------------------------
        pages = bench.extract_pages_pymupdf(
            pdf_path,
            debug_dir=ocr_debug_dir,
            ocr_debug=ocr_debug,
            save_images=save_images,
        )
        db.set_document_page_count(doc_id, len(pages))

        # ------------------------------------------------------------
        # 3. Persist pages + page_texts to SQLite
        # ------------------------------------------------------------
        # page_number → page_id (needed when building chunks below)
        page_id_map: dict[int, str] = {}
        # page_number → selected page_text_id
        page_text_id_map: dict[int, str] = {}

        for page_data in pages:
            page_number = int(page_data["page"])
            page_id = db.insert_page(doc_id, run_id, page_number)
            page_id_map[page_number] = page_id

            native_text = page_data.get("native_text") or ""
            ocr_text    = page_data.get("ocr_text") or ""
            selected    = page_data.get("text") or ""
            ocr_used    = bool(page_data.get("ocr_used", False))
            quality     = float(page_data.get("ocr_quality", 0.0))
            confidence  = float(page_data.get("ocr_confidence", 0.0))

            # Always store native attempt
            db.insert_page_text(
                page_id, "native", native_text,
                quality_score=None, confidence=None, is_selected=False,
            )

            # Store OCR attempt when it was run
            ocr_pt_id = None
            if ocr_text.strip():
                ocr_pt_id = db.insert_page_text(
                    page_id, "tesseract", ocr_text,
                    quality_score=quality, confidence=confidence, is_selected=False,
                )

            # Determine which strategy produced the selected text and store it
            if ocr_used and ocr_text.strip():
                strategy = "merged" if native_text.strip() else "tesseract"
            else:
                strategy = "native"

            selected_pt_id = db.insert_page_text(
                page_id, strategy, selected,
                quality_score=quality,
                confidence=confidence if ocr_used else None,
                is_selected=True,
            )
            page_text_id_map[page_number] = selected_pt_id

            # Save page image if available
            img_path = ocr_debug_dir / f"page_{page_number:03d}.png"
            if img_path.exists():
                db.insert_image(page_id, "render", img_path, dpi=base.OCR_DPI)

        # ------------------------------------------------------------
        # 4. Chunk the pages (existing logic, unchanged)
        # ------------------------------------------------------------
        chunks = base.build_chunks(
            pages,
            target_words=chunk_words,
            max_words=max(chunk_words, base.DEFAULT_MAX_WORDS),
            overlap_blocks=overlap,           # ← fixed: was hardcoded DEFAULT
            source_name=pdf_path.stem,
        )
        if not chunks:
            raise RuntimeError(f"No chunks extracted from {pdf_path}")

        bench.enrich_chunk_metadata(chunks, pages)
        bench.dump_chunks_to_disk(chunks, chunk_debug_dir)

        # ------------------------------------------------------------
        # 5. Persist chunks to SQLite
        # ------------------------------------------------------------
        # chunk.chunk_id from the existing code (e.g. "stem:chunk-0001")
        # We'll use a fresh UUID as the canonical DB id and also as the Chroma id.
        db_chunk_ids: list[str] = []
        chunk_texts: list[str] = []

        for idx, chunk in enumerate(chunks):
            page_start = int(chunk.metadata.get("page_start") or 1)
            page_end   = int(chunk.metadata.get("page_end") or page_start)

            # Use the page_id of the first page this chunk spans
            page_id      = page_id_map.get(page_start, next(iter(page_id_map.values())))
            page_text_id = page_text_id_map.get(page_start, next(iter(page_text_id_map.values())))

            db_chunk_id = db.insert_chunk(
                doc_id=doc_id,
                page_id=page_id,
                page_text_id=page_text_id,
                run_id=run_id,
                chunk_index=idx,
                text=chunk.text,
                title=chunk.title,
                word_count=chunk.metadata.get("word_count"),
                page_start=page_start,
                page_end=page_end,
                chunker_version=chunker_version,
                config={
                    "target_words": chunk_words,
                    "overlap_blocks": overlap,
                    "max_words": max(chunk_words, base.DEFAULT_MAX_WORDS),
                },
            )
            db_chunk_ids.append(db_chunk_id)
            chunk_texts.append(chunk.text)

        # ------------------------------------------------------------
        # 6. Embed and upsert into Chroma (using DB chunk UUIDs as ids)
        # ------------------------------------------------------------
        embeddings = base.embed_texts(model, chunk_texts, kind="passage", show_progress=True)
        collection = base.get_collection(persist_dir, collection_name)

        chroma_metadatas = []
        for idx, chunk in enumerate(chunks):
            chroma_metadatas.append({
                "doc_id":          doc_id,
                "page_id":         page_id_map.get(int(chunk.metadata.get("page_start") or 1), ""),
                "page_number":     int(chunk.metadata.get("page_start") or 1),
                "page_start":      int(chunk.metadata.get("page_start") or 1),
                "page_end":        int(chunk.metadata.get("page_end") or 1),
                "source":          pdf_path.stem,
                "section_title":   chunk.title or "",
                "chunker_version": chunker_version,
                "strategy":        chunk.metadata.get("ocr_strategy", "native"),
                "word_count":      chunk.metadata.get("word_count", 0),
            })

        collection.upsert(
            ids=db_chunk_ids,                           # UUID, matches SQLite chunks.id
            documents=[f"{c.title}\n\n{c.text}".strip() for c in chunks],
            metadatas=chroma_metadatas,
            embeddings=embeddings,
        )

        # ------------------------------------------------------------
        # 7. Mark chunks as embedded in SQLite
        # ------------------------------------------------------------
        db.mark_chunks_embedded(db_chunk_ids)
        db.set_document_status(doc_id, "done")
        db.finish_ingestion_run(run_id)

        summary = {
            "doc_id":      doc_id,
            "run_id":      run_id,
            "filename":    pdf_path.name,
            "page_count":  len(pages),
            "chunk_count": len(chunks),
            "is_new":      is_new,
        }
        print(
            f"[db] Ingested {pdf_path.name}: "
            f"{len(pages)} pages, {len(chunks)} chunks → SQLite + Chroma"
        )
        return summary

    except Exception as exc:
        db.set_document_status(doc_id, "error")
        db.finish_ingestion_run(run_id, error=str(exc))
        traceback.print_exc()
        raise