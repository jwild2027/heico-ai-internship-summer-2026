#!/usr/bin/env python3
"""Run repeatable local TIFF/RAG evaluation questions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.local_config import bool_from_config, int_from_config, load_local_config  # noqa: E402
from tiff.ollama_client import DEFAULT_OLLAMA_URL  # noqa: E402
from tiff.pipeline_manifest import refresh_manifest_eval_summary  # noqa: E402
from tiff.rag_eval import (  # noqa: E402
    EvalQuestion,
    EvalRecord,
    evaluate_question,
    load_eval_questions,
    summarize_eval_records,
    write_eval_csv,
    write_eval_html,
    write_eval_json,
)
from tiff.rag_eval_questions import (  # noqa: E402
    summarize_question_set,
    write_expanded_rag_eval_questions,
)


def _format_record_line(index: int, total: int, record: EvalRecord) -> str:
    bits = [
        f"[{index}/{total}] {record.id}",
        record.status,
        f"elapsed={record.elapsed_seconds:.2f}s",
        f"llm={record.llm_used}",
        f"embed={record.embeddings_used}",
        f"sources={record.source_count}",
    ]
    if record.missing_terms:
        bits.append("missing_terms=" + ", ".join(str(x) for x in record.missing_terms))
    if record.missing_sources:
        bits.append("missing_sources=" + ", ".join(str(x) for x in record.missing_sources))
    if record.expectation_errors:
        bits.append("expectation_errors=" + "; ".join(str(x) for x in record.expectation_errors))
    return "  " + " | ".join(bits)


def run_selected_questions(
    questions: list[EvalQuestion],
    *,
    db_path: str,
    embed_model: str,
    llm_model: str,
    ollama_url: str,
    top_k: int,
    use_llm: bool,
    use_embeddings: bool,
    show_answers: bool = False,
) -> list[EvalRecord]:
    records: list[EvalRecord] = []
    total = len(questions)
    for index, question in enumerate(questions, start=1):
        print(f"[{index}/{total}] {question.id}")
        record = evaluate_question(
            question,
            db_path=db_path,
            embed_model=embed_model,
            llm_model=llm_model,
            ollama_url=ollama_url,
            top_k=top_k,
            use_llm=use_llm,
            use_embeddings=use_embeddings,
        )
        records.append(record)
        print(_format_record_line(index, total, record))
        if show_answers:
            print("    Answer:")
            for line in record.answer.splitlines():
                print("      " + line)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="Optional local_config.yaml/json path")
    parser.add_argument("--questions", default=None, help="JSON question set path")
    parser.add_argument("--write-default-questions", default=None, help="Write the expanded starter question JSON and exit")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--embed-model", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--ollama-url", default=None)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N questions for a smoke test")
    parser.add_argument("--output-dir", default="local_data/evals")
    parser.add_argument("--output-prefix", default="rag_eval_results")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-embeddings", action="store_true")
    parser.add_argument("--write-html", action="store_true", help="Also write the optional HTML report")
    parser.add_argument(
        "--refresh-manifest",
        dest="refresh_manifest",
        action="store_true",
        default=None,
        help="Refresh latest_backend_pipeline.json after writing eval JSON.",
    )
    parser.add_argument(
        "--no-refresh-manifest",
        dest="refresh_manifest",
        action="store_false",
        help="Do not refresh latest_backend_pipeline.json after writing eval JSON.",
    )
    parser.add_argument("--show-answers", action="store_true", help="Print full answers after each row")
    args = parser.parse_args()

    if args.write_default_questions:
        path = write_expanded_rag_eval_questions(args.write_default_questions)
        summary = summarize_question_set()
        print(f"Wrote expanded RAG eval questions: {path}")
        print(f"  Questions: {summary['questions']}")
        print(f"  Deterministic/retrieval checks: {summary['deterministic_or_retrieval']}")
        print(f"  LLM checked: {summary['llm_checked']}")
        print(f"  Manual review: {summary['manual_review']}")
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
    selected_questions = questions[: max(0, args.limit)] if args.limit is not None else questions

    print("RAG evaluation")
    print(f"  Questions selected: {len(selected_questions)} of {len(questions)}")
    print(f"  DB: {db_path}")
    print(f"  Embed model: {embed_model}")
    print(f"  LLM model: {llm_model}")
    print("")

    records = run_selected_questions(
        selected_questions,
        db_path=db_path,
        embed_model=embed_model,
        llm_model=llm_model,
        ollama_url=ollama_url,
        top_k=top_k,
        use_llm=use_llm,
        use_embeddings=use_embeddings,
        show_answers=args.show_answers,
    )

    out_dir = Path(args.output_dir)
    csv_path = write_eval_csv(records, out_dir / f"{args.output_prefix}.csv")
    json_path = write_eval_json(records, out_dir / f"{args.output_prefix}.json")
    html_path = None
    if args.write_html:
        html_path = write_eval_html(records, out_dir / f"{args.output_prefix}.html")

    summary = summarize_eval_records(records)
    print("")
    print("RAG evaluation complete")
    print(f"  Questions: {summary['total']}")
    print(f"  Pass: {summary.get('pass', 0)}")
    print(f"  Fail: {summary.get('fail', 0)}")
    print(f"  Manual review: {summary.get('manual_review', 0)}")
    print(f"  LLM used: {summary.get('llm_used', 0)}")
    print(f"  Embeddings used: {summary.get('embeddings_used', 0)}")
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")
    if html_path is not None:
        print(f"  HTML: {html_path}")

    should_refresh_manifest = args.refresh_manifest
    if should_refresh_manifest is None:
        # Default to refreshing the manifest for full normal eval runs only.
        # Smoke tests with --limit intentionally do not overwrite the manifest
        # question count with a partial result.
        normalized_json = str(json_path).replace("\\", "/")
        should_refresh_manifest = args.limit is None and normalized_json.endswith("local_data/evals/rag_eval_results.json")

    if should_refresh_manifest:
        try:
            refreshed = refresh_manifest_eval_summary(eval_csv=csv_path, eval_json=json_path)
        except Exception as exc:  # pragma: no cover - defensive CLI path
            print(f"  Warning: could not refresh pipeline manifest eval summary: {exc}", file=sys.stderr)
        else:
            if refreshed:
                print("  Refreshed pipeline manifest eval summary:")
                for path in refreshed:
                    print(f"    {path}")

    return 1 if summary.get("fail", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
