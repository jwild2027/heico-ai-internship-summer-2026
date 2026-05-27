#!/usr/bin/env python3
"""Write the expanded local TIFF RAG eval question set."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.rag_eval_questions import (  # noqa: E402
    EXPANDED_RAG_EVAL_QUESTIONS,
    summarize_question_set,
    write_expanded_rag_eval_questions,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions",
        default="local_data/evals/rag_eval_questions.json",
        help="Output JSON path for the normal pipeline eval question set.",
    )
    parser.add_argument("--no-backup", action="store_true", help="Do not create a .bak copy when overwriting an existing file.")
    parser.add_argument("--list", action="store_true", help="Print question ids after writing.")
    args = parser.parse_args()

    out_path = Path(args.questions)
    if out_path.exists() and not args.no_backup:
        backup = out_path.with_suffix(out_path.suffix + ".bak")
        shutil.copy2(out_path, backup)
        print(f"Backed up existing questions: {backup}")

    path = write_expanded_rag_eval_questions(out_path)
    summary = summarize_question_set(EXPANDED_RAG_EVAL_QUESTIONS)
    print(f"Wrote expanded RAG eval questions: {path}")
    print(f"  Questions: {summary['questions']}")
    print(f"  Deterministic/retrieval checks: {summary['deterministic_or_retrieval']}")
    print(f"  LLM checked: {summary['llm_checked']}")
    print(f"  Manual review: {summary['manual_review']}")
    print(f"  Expected no-LLM checks: {summary['expected_no_llm']}")
    print(f"  Expected embedding checks: {summary['expected_embeddings']}")

    if args.list:
        print("Question ids:")
        for index, row in enumerate(EXPANDED_RAG_EVAL_QUESTIONS, start=1):
            print(f"  {index}. {row['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
