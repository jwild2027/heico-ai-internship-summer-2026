from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.feedback_session import (
    DEFAULT_OUTPUT,
    DEFAULT_SUMMARY,
    audit_source_zip,
    make_feedback_entry,
    run_answer_command,
    run_interactive_session,
    save_feedback,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an interactive TIFF/RAG answer feedback session.")
    parser.add_argument("--config", default="local_config.yaml", help="Config file for ask_tiff_rag.py.")
    parser.add_argument("--source-zip", help="Path to raw/public TIFF ZIP for traceability context.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Append-only feedback JSONL output.")
    parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY), help="Feedback summary JSON output.")
    parser.add_argument("--timeout", type=int, default=180, help="Answer command timeout in seconds.")
    parser.add_argument("--question", help="Run one non-interactive question and save feedback if rating/reason are supplied.")
    parser.add_argument("--rating", help="Non-interactive rating: up/down/neutral/1-5/pass/fail.")
    parser.add_argument("--reason", help="Non-interactive feedback reason/comment.")
    parser.add_argument("--category", help="Optional feedback category.")
    parser.add_argument("--print-source-zip-audit", action="store_true", help="Print source ZIP audit and exit.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = Path(args.output)
    summary = Path(args.summary_output)

    if args.print_source_zip_audit:
        audit = audit_source_zip(args.source_zip)
        print(json.dumps(asdict(audit), ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if audit.status in {"ok", "not_provided"} else 1

    if args.question:
        if not args.rating or not args.reason:
            raise SystemExit("--question mode requires --rating and --reason")
        audit = audit_source_zip(args.source_zip)
        answer = run_answer_command(args.question, config=args.config, timeout=args.timeout)
        print(answer.stdout.rstrip())
        if answer.stderr.strip():
            print("\n[stderr]")
            print(answer.stderr.rstrip())
        entry = make_feedback_entry(
            session_id="single_question",
            question=args.question,
            answer=answer,
            rating_value=args.rating,
            reason=args.reason,
            category=args.category,
            source_zip=audit,
            config=args.config,
        )
        save_feedback(entry, output, summary)
        print(f"\nSaved feedback: {entry.feedback_id}")
        print(f"Feedback JSONL: {output}")
        print(f"Feedback summary: {summary}")
        return 0 if answer.returncode == 0 else answer.returncode

    return run_interactive_session(
        config=args.config,
        source_zip_path=args.source_zip,
        output_path=output,
        summary_path=summary,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
