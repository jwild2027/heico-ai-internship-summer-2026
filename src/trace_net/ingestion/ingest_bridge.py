"""db/ingest_bridge.py — wires rag_benchmark.py's pipeline into the DB layer."""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.pymupdf_bge_chroma_cli as base
import src.benchmarks.rag_benchmark as bench
from src.db.storage import RAGDatabase


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
    pdf_path = base.resolve_pdf_path(pdf_path)

    existing_docs_before = db.list_documents()
    print(f"[db] Before ingest: {len(existing_docs_before)} document(s) in {db.db_path}")
    for d in existing_docs_before:
        print(f"[db]   - {d['filename']} ({d.get('page_count') or '?'} pages, "
              f"status={d['status']}, id={d['id'][:8]}…)")

    doc_id, is_new = db.upsert_document(pdf_path)
    if not is_new:
        print(f"[db] Document already exists (same checksum): {pdf_path.name} → {doc_id}")
        existing_chunks = db.get_chunks_for_document(doc_id)
        if existing_chunks:
            existing_ids = [c["id"] for c in existing_chunks]
            try:
                collection = base.get_collection(persist_dir, collection_name)
                collection.delete(ids=existing_ids)
                print(f"[db] Removed {len(existing_ids)} existing chunks from Chroma")
            except Exception as e:
                print(f"[db] Warning: could not remove old Chroma chunks: {e}")
        cleared = db.clear_document_content(doc_id)
        print(f"[db] Cleared prior SQLite content for re-ingest: "
              f"{cleared['chunks']} chunks, {cleared['pages']} pages, "
              f"{cleared['page_texts']} page_texts, {cleared['images']} images")

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
        pages = bench.extract_pages_pymupdf(
            pdf_path,
            debug_dir=ocr_debug_dir,
            ocr_debug=ocr_debug,
            save_images=save_images,
        )
        db.set_document_page_count(doc_id, len(pages))

        page_id_map: dict[int, str] = {}
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

            db.insert_page_text(page_id, "native", native_text,
                quality_score=None, confidence=None, is_selected=False)

            if ocr_text.strip():
                db.insert_page_text(page_id, "tesseract", ocr_text,
                    quality_score=quality, confidence=confidence, is_selected=False)

            if ocr_used and ocr_text.strip():
                strategy = "merged" if native_text.strip() else "tesseract"
            else:
                strategy = "native"

            selected_pt_id = db.insert_page_text(page_id, strategy, selected,
                quality_score=quality,
                confidence=confidence if ocr_used else None,
                is_selected=True)
            page_text_id_map[page_number] = selected_pt_id

            img_path = ocr_debug_dir / f"page_{page_number:03d}.png"
            if img_path.exists():
                db.insert_image(page_id, "render", img_path, dpi=base.OCR_DPI)

        from src.chunking.chunking_strategy import choose_strategy, profile_document
        strategy, reason = choose_strategy(pages)
        profile = profile_document(pages)
        print(f"[chunk] Strategy: {strategy}  ({reason})")

        db_chunk_ids: list[str] = []
        chunk_texts: list[str] = []
        chroma_metadatas: list[dict[str, Any]] = []

        if strategy == "parent_child":
            # Pass pdf_path so the chunker can try outline-based chunking first
            from src.chunking.parent_child_chunker import build_parent_child_chunks, summarize
            parents, children = build_parent_child_chunks(
                pages, source_name=pdf_path.stem, pdf_path=pdf_path,
            )
            print(f"[chunk] {summarize(parents, children)}")

            parent_db_ids: dict[str, str] = {}

            for p_idx, parent in enumerate(parents):
                page_id      = page_id_map.get(parent.page_start, next(iter(page_id_map.values())))
                page_text_id = page_text_id_map.get(parent.page_start, next(iter(page_text_id_map.values())))
                p_db_id = db.insert_chunk(
                    doc_id=doc_id, page_id=page_id, page_text_id=page_text_id,
                    run_id=run_id, chunk_index=p_idx,
                    text=parent.text, title=parent.title,
                    word_count=parent.word_count,
                    page_start=parent.page_start, page_end=parent.page_end,
                    chunker_version=chunker_version,
                    strategy="parent_child", level="parent",
                    parent_id=None, explicit_id=parent.parent_id,
                    config={"target_words": 600, "max_words": 800,
                            "chunking_method": parent.metadata.get("chunking_method")},
                )
                parent_db_ids[parent.parent_id] = p_db_id
                db.mark_chunks_embedded([p_db_id])

            for c_idx, child in enumerate(children):
                page_id      = page_id_map.get(child.page_start, next(iter(page_id_map.values())))
                page_text_id = page_text_id_map.get(child.page_start, next(iter(page_text_id_map.values())))
                parent_db_id = parent_db_ids.get(child.parent_id, child.parent_id)
                c_db_id = db.insert_chunk(
                    doc_id=doc_id, page_id=page_id, page_text_id=page_text_id,
                    run_id=run_id, chunk_index=c_idx,
                    text=child.text,
                    title=child.metadata.get("parent_title", ""),
                    char_start=child.char_start, char_end=child.char_end,
                    word_count=child.word_count,
                    page_start=child.page_start, page_end=child.page_end,
                    chunker_version=chunker_version,
                    strategy="parent_child", level="child",
                    parent_id=parent_db_id, explicit_id=child.child_id,
                    config={"target_words": 120, "overlap_words": 20},
                )
                db_chunk_ids.append(c_db_id)
                chunk_texts.append(child.text)
                chroma_metadatas.append({
                    "doc_id":          doc_id,
                    "page_id":         page_id_map.get(child.page_start, ""),
                    "page_number":     child.page_start,
                    "page_start":      child.page_start,
                    "page_end":        child.page_end,
                    "source":          pdf_path.stem,
                    "section_title":   child.metadata.get("parent_title", ""),
                    "chunker_version": chunker_version,
                    "strategy":        "parent_child",
                    "level":           "child",
                    "parent_id":       parent_db_id,
                    "word_count":      child.word_count,
                    "chunking_method": child.metadata.get("chunking_method", "unknown"),
                })

            bench.dump_chunks_to_disk(
                [base.ChunkRecord(
                    chunk_id=child.child_id,
                    title=child.metadata.get("parent_title", ""),
                    text=child.text,
                    metadata={"page_start": child.page_start, "page_end": child.page_end},
                ) for child in children],
                chunk_debug_dir,
            )

        else:
            chunks = base.build_chunks(
                pages, target_words=chunk_words,
                max_words=max(chunk_words, base.DEFAULT_MAX_WORDS),
                overlap_blocks=overlap, source_name=pdf_path.stem,
            )
            if not chunks:
                raise RuntimeError(f"No chunks extracted from {pdf_path}")
            bench.enrich_chunk_metadata(chunks, pages)
            bench.dump_chunks_to_disk(chunks, chunk_debug_dir)

            for idx, chunk in enumerate(chunks):
                page_start = int(chunk.metadata.get("page_start") or 1)
                page_end   = int(chunk.metadata.get("page_end") or page_start)
                page_id      = page_id_map.get(page_start, next(iter(page_id_map.values())))
                page_text_id = page_text_id_map.get(page_start, next(iter(page_text_id_map.values())))
                db_chunk_id = db.insert_chunk(
                    doc_id=doc_id, page_id=page_id, page_text_id=page_text_id,
                    run_id=run_id, chunk_index=idx,
                    text=chunk.text, title=chunk.title,
                    word_count=chunk.metadata.get("word_count"),
                    page_start=page_start, page_end=page_end,
                    chunker_version=chunker_version,
                    strategy="flat", level="flat",
                    config={"target_words": chunk_words, "overlap_blocks": overlap,
                            "max_words": max(chunk_words, base.DEFAULT_MAX_WORDS)},
                )
                db_chunk_ids.append(db_chunk_id)
                chunk_texts.append(chunk.text)
                chroma_metadatas.append({
                    "doc_id":          doc_id,
                    "page_id":         page_id_map.get(page_start, ""),
                    "page_number":     page_start,
                    "page_start":      page_start,
                    "page_end":        page_end,
                    "source":          pdf_path.stem,
                    "section_title":   chunk.title or "",
                    "chunker_version": chunker_version,
                    "strategy":        "flat",
                    "level":           "flat",
                    "word_count":      chunk.metadata.get("word_count", 0),
                })

        if not chunk_texts:
            raise RuntimeError(f"No embeddable chunks produced for {pdf_path}")

        embeddings = base.embed_texts(model, chunk_texts, kind="passage", show_progress=True)
        collection = base.get_collection(persist_dir, collection_name)
        collection.upsert(
            ids=db_chunk_ids, documents=chunk_texts,
            metadatas=chroma_metadatas, embeddings=embeddings,
        )

        db.mark_chunks_embedded(db_chunk_ids)
        db.set_document_status(doc_id, "done")
        db.finish_ingestion_run(run_id)

        summary = {
            "doc_id": doc_id, "run_id": run_id, "filename": pdf_path.name,
            "page_count": len(pages), "chunk_count": len(db_chunk_ids),
            "is_new": is_new,
        }
        print(f"[db] Ingested {pdf_path.name}: {len(pages)} pages, "
              f"{len(db_chunk_ids)} chunks → SQLite + Chroma")

        existing_docs_after = db.list_documents()
        after_ids = {d["id"] for d in existing_docs_after}
        missing = [d for d in existing_docs_before if d["id"] not in after_ids]
        print(f"[db] After ingest:  {len(existing_docs_after)} document(s) in {db.db_path}")
        for d in existing_docs_after:
            print(f"[db]   - {d['filename']} ({d.get('page_count') or '?'} pages, "
                  f"status={d['status']}, id={d['id'][:8]}…)")
        if missing:
            names = ", ".join(f"{d['filename']} (id={d['id'][:8]}…)" for d in missing)
            raise RuntimeError(
                f"[db] Document(s) disappeared during ingest of {pdf_path.name}: {names}."
            )

        return summary

    except Exception as exc:
        db.set_document_status(doc_id, "error")
        db.finish_ingestion_run(run_id, error=str(exc))
        traceback.print_exc()
        raise