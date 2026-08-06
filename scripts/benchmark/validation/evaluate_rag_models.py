#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.rag_model_eval import (
    default_model_eval_questions,
    load_questions,
    run_model_eval_question,
    summarize_results,
    write_questions,
    write_result_files,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare local Ollama answer models on the TIFF RAG eval set.")
    parser.add_argument("--config", default="local_config.yaml", help="Path to local_config.yaml")
    parser.add_argument("--questions", default="local_data/evals/rag_model_eval_questions.json", help="Question JSON path")
    parser.add_argument("--write-default-questions", action="store_true", help="Write the expanded default question set and exit")
    parser.add_argument("--models", nargs="+", default=["gemma3:12B", "llama3.1:8b"], help="Ollama LLM models to compare")
    parser.add_argument("--embed-model", default=None, help="Optional embedding model override")
    parser.add_argument("--output-dir", default="local_data/evals/model_compare", help="Output directory")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--limit", type=int, default=0, help="Limit question count for quick smoke tests")
    parser.add_argument("--force-llm", action="store_true", help="Force LLM even for deterministic lookup questions")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    questions_path = Path(args.questions)
    if args.write_default_questions:
        write_questions(questions_path, default_model_eval_questions())
        print(f"Wrote expanded model-eval questions: {questions_path}")
        return 0

    if not questions_path.exists():
        write_questions(questions_path, default_model_eval_questions())
        print(f"Question file did not exist; wrote default questions: {questions_path}")

    questions = load_questions(questions_path)
    if args.limit and args.limit > 0:
        questions = questions[: args.limit]

    results = []
    total = len(questions) * len(args.models)
    print("TIFF RAG model evaluation")
    print(f"  Questions: {len(questions)}")
    print(f"  Models: {', '.join(args.models)}")
    print(f"  Total runs: {total}")

    counter = 0
    for model in args.models:
        for question in questions:
            counter += 1
            print(f"[{counter}/{total}] {model} :: {question.id}")
            result = run_model_eval_question(
                repo_root=REPO_ROOT,
                config_path=Path(args.config),
                model=model,
                question=question,
                embed_model=args.embed_model,
                timeout_seconds=args.timeout_seconds,
                force_llm=args.force_llm,
            )
            print(f"  {result.status} elapsed={result.elapsed_seconds:.2f}s llm={result.llm_used} embed={result.embeddings_used} sources={result.source_count}")
            results.append(result)

    paths = write_result_files(Path(args.output_dir), results)
    summary = summarize_results(results)
    print("\nModel evaluation complete")
    print(f"  Total: {summary['total']}")
    print(f"  Status counts: {summary['by_status']}")
    print(f"  CSV: {paths['csv']}")
    print(f"  JSON: {paths['json']}")
    print(f"  HTML: {paths['html']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
