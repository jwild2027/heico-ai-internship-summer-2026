#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.local_config import bool_from_config, int_from_config, load_local_config  # noqa: E402
from tiff.ollama_client import DEFAULT_OLLAMA_URL  # noqa: E402
from tiff.rag_answer import answer_question, format_source_label  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask a source-backed local RAG question over TIFF OCR")
    parser.add_argument("question", nargs="+", help="Question to ask")
    parser.add_argument("--config", default=None, help="Optional local_config.yaml/json path")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--embed-model", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--ollama-url", default=None)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--answer-mode", choices=["auto", "lookup", "locate", "summarize", "compare"], default=None)
    parser.add_argument("--retrieval-mode", choices=["auto", "structured", "keyword", "semantic", "hybrid"], default=None)
    parser.add_argument("--force-llm", action="store_true", help="Skip deterministic lookup formatting and force the LLM when --no-llm is not set")
    parser.add_argument("--force-embeddings", action="store_true", help="Run semantic/vector retrieval even if auto routing would not require it")
    parser.add_argument("--no-llm", action="store_true", help="Use extractive source-only answer without calling the chat model")
    parser.add_argument("--no-embeddings", action="store_true", help="Use exact/keyword retrieval only")
    args = parser.parse_args()

    cfg = load_local_config(args.config)
    db_path = args.db_path or str(cfg.get("db_path") or "local_data/db/tiff_search.db")
    embed_model = args.embed_model or str(cfg.get("embed_model") or "bge-m3:latest")
    llm_model = args.llm_model or str(cfg.get("llm_model") or "llama3.1:8b")
    ollama_url = args.ollama_url or str(cfg.get("ollama_url") or DEFAULT_OLLAMA_URL)
    top_k = args.top_k if args.top_k is not None else int_from_config(cfg.get("top_k"), default=6)
    answer_mode = args.answer_mode or str(cfg.get("answer_mode") or "auto")
    retrieval_mode = args.retrieval_mode or str(cfg.get("retrieval_mode") or "auto")
    use_llm = False if args.no_llm else bool_from_config(cfg.get("use_llm"), default=True)
    use_embeddings = False if args.no_embeddings else bool_from_config(cfg.get("use_embeddings"), default=True)
    force_llm = bool(args.force_llm or bool_from_config(cfg.get("force_llm"), default=False))
    force_embeddings = bool(args.force_embeddings or bool_from_config(cfg.get("force_embeddings"), default=False))

    question = " ".join(args.question).strip()
    result = answer_question(
        Path(db_path),
        question,
        embed_model=embed_model,
        llm_model=llm_model,
        ollama_url=ollama_url,
        top_k=top_k,
        use_llm=use_llm,
        use_embeddings=use_embeddings,
        answer_mode=answer_mode,
        retrieval_mode=retrieval_mode,
        force_llm=force_llm,
        force_embeddings=force_embeddings,
    )

    print(f"Question: {result.question}")
    print(f"LLM used: {result.used_llm}")
    print(f"Embeddings used: {result.used_embeddings}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    print("\nAnswer:\n")
    print(result.answer)
    if result.sources:
        print("\nSources:")
        for idx, source in enumerate(result.sources, start=1):
            print(f"{idx}. {format_source_label(source)}")
            print(f"   Type: {source.source_type}  Score: {source.score:.4f}")
            if source.matched_part_number:
                print(f"   Part: {source.matched_part_number}")
            if source.part_nomenclature:
                print(f"   Nomenclature: {source.part_nomenclature}")
            if getattr(source, "rescarta_url", None):
                print(f"   ResCarta: {source.rescarta_url}")
            if getattr(source, "source_url", None):
                print(f"   Source URL: {source.source_url}")
            if getattr(source, "tiff_uri", None):
                print(f"   TIFF URI: {source.tiff_uri}")
            if getattr(source, "ocr_uri", None):
                print(f"   OCR URI: {source.ocr_uri}")
            if source.tiff_path:
                print(f"   TIFF: {source.tiff_path}")
            if source.ocr_text_path:
                print(f"   OCR: {source.ocr_text_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
