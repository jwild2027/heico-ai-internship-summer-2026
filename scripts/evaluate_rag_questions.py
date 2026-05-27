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
from tiff.rag_eval import (  # noqa: E402
    evaluate_questions,
    load_eval_questions,
    summarize_eval_records,
    write_default_eval_questions,
    write_eval_csv,
    write_eval_html,
    write_eval_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repeatable local TIFF/RAG evaluation questions")
    parser.add_argument("--config", default=None, help="Optional local_config.yaml/json path")
    parser.add_argument("--questions", default=None, help="JSON question set path")
    parser.add_argument("--write-default-questions", default=None, help="Write a starter question JSON and exit")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--embed-model", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--ollama-url", default=None)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--output-dir", default="local_data/evals")
    parser.add_argument("--output-prefix", default="rag_eval_results")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-embeddings", action="store_true")
    args = parser.parse_args()

    if args.write_default_questions:
        path = write_default_eval_questions(args.write_default_questions)
        print(f"Wrote starter question set: {path}")
        return 0

    cfg = load_local_config(args.config)
    db_path = args.db_path or str(cfg.get("db_path") or "local_data/db/tiff_search.db")
    embed_model = args.embed_model or str(cfg.get("embed_model") or "bge-m3:latest")
    llm_model = args.llm_model or str(cfg.get("llm_model") or "gemma3:12B")
    ollama_url = args.ollama_url or str(cfg.get("ollama_url") or DEFAULT_OLLAMA_URL)
    top_k = args.top_k if args.top_k is not None else int_from_config(cfg.get("top_k"), default=8)
    use_llm = False if args.no_llm else bool_from_config(cfg.get("use_llm"), default=True)
    use_embeddings = False if args.no_embeddings else bool_from_config(cfg.get("use_embeddings"), default=True)

    questions = load_eval_questions(args.questions)
    records = evaluate_questions(
        questions,
        db_path=db_path,
        embed_model=embed_model,
        llm_model=llm_model,
        ollama_url=ollama_url,
        top_k=top_k,
        use_llm=use_llm,
        use_embeddings=use_embeddings,
    )

    out_dir = Path(args.output_dir)
    csv_path = write_eval_csv(records, out_dir / f"{args.output_prefix}.csv")
    json_path = write_eval_json(records, out_dir / f"{args.output_prefix}.json")
    html_path = write_eval_html(records, out_dir / f"{args.output_prefix}.html")
    summary = summarize_eval_records(records)

    print("RAG evaluation complete")
    print(f"  Questions: {summary['total']}")
    print(f"  Pass: {summary.get('pass', 0)}")
    print(f"  Fail: {summary.get('fail', 0)}")
    print(f"  Manual review: {summary.get('manual_review', 0)}")
    print(f"  LLM used: {summary.get('llm_used', 0)}")
    print(f"  Embeddings used: {summary.get('embeddings_used', 0)}")
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")
    return 1 if summary.get("fail", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
