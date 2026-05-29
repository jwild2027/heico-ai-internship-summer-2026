#!/usr/bin/env python3
"""Generate optional AI page-context records for the document organization graph."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.page_context import (  # noqa: E402
    DEFAULT_EXPORT_DIR,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_FILE,
    PageContext,
    generate_page_contexts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate AI PageContext records from organization export pages.")
    parser.add_argument("--export-dir", default=DEFAULT_EXPORT_DIR, help="Input organization export directory.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output context directory.")
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE, help="Output context JSON filename.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model for context generation, e.g. gemma3:12B.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N selected pages.")
    parser.add_argument("--page", action="append", default=[], help="Only process this page_id; may be repeated.")
    parser.add_argument("--dry-run", action="store_true", help="Generate deterministic placeholder contexts without calling Ollama.")
    parser.add_argument("--force", action="store_true", help="Regenerate contexts even if page_id already exists in output JSON.")
    parser.add_argument("--missing-only", action="store_true", help="Select only pages that do not already have a context. Useful for true next-batch scans.")
    parser.add_argument("--max-ocr-chars", type=int, default=6000, help="Max OCR chars sent to the model per page.")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait per Ollama page-context call.")
    parser.add_argument("--write-json", action="store_true", help="Accepted for command consistency; contexts are always written.")
    parser.add_argument("--progress", action="store_true", help="Print a one-line progress update after each page is scanned.")
    parser.add_argument("--show-error-details", action="store_true", help="Print per-page warning/error details for generated contexts.")
    return parser.parse_args()


def error_category(message: str) -> str:
    text = (message or "").lower()
    if not text:
        return "none"
    if "empty ocr" in text:
        return "empty_ocr"
    if "missing ocr" in text:
        return "missing_ocr"
    if "could not read ocr" in text:
        return "unreadable_ocr"
    if "model response did not contain" in text or "json" in text:
        return "model_json_parse_fallback"
    if "ollama run failed" in text:
        return "ollama_failed"
    if "timed out" in text or "timeout" in text:
        return "ollama_timeout"
    if "fallback used" in text:
        return "model_fallback"
    return "other"


def truncate(text: str, limit: int = 260) -> str:
    value = (text or "").replace("\n", " ").strip()
    return value if len(value) <= limit else value[: limit - 3] + "..."


def print_progress_line(index: int, total: int, context: PageContext, action: str) -> None:
    status = "warning" if context.error else "ok"
    action_label = "skipped" if action == "skipped" else "done"
    approx_tokens = context.approx_total_tokens
    if approx_tokens == 0 and action == "skipped":
        approx_tokens_text = "cached"
    else:
        approx_tokens_text = str(approx_tokens)
    print(
        f"[{index}/{total}] {action_label} page={context.page_id} "
        f"role={context.page_role} confidence={context.confidence} "
        f"score={context.quality_score:.2f} elapsed={context.elapsed_seconds:.2f}s "
        f"approx_tokens={approx_tokens_text} status={status}",
        flush=True,
    )


def main() -> int:
    args = parse_args()
    try:
        result, contexts = generate_page_contexts(
            export_dir=args.export_dir,
            output_dir=args.output_dir,
            output_file=args.output_file,
            model=args.model,
            limit=args.limit,
            page_ids=args.page,
            dry_run=args.dry_run,
            force=args.force,
            missing_only=args.missing_only,
            max_ocr_chars=args.max_ocr_chars,
            timeout=args.timeout,
            progress_callback=print_progress_line if args.progress else None,
        )
    except Exception as exc:  # pragma: no cover - CLI safety
        print("Page context generation")
        print("  Status: FAILED")
        print(f"  Error: {exc}")
        return 2

    errored_contexts = [context for context in contexts if context.error]
    error_counts = Counter(error_category(context.error) for context in errored_contexts)

    print("Page context generation")
    print(f"  Status: {result.status}")
    print(f"  Export dir: {result.export_dir}")
    print(f"  Output: {result.output_path}")
    print(f"  Model: {result.model}")
    print(f"  Prompt version: {result.prompt_version}")
    print(f"  Pages selected: {result.page_count_seen}")
    print(f"  Contexts written: {result.contexts_written}")
    print(f"  Skipped existing: {result.skipped_existing}")
    print(f"  Contexts with warnings/errors: {result.failed_contexts}")
    print(f"  Total elapsed: {result.total_elapsed_seconds:.2f}s")
    print(f"  Avg/page elapsed: {result.average_elapsed_seconds:.2f}s")
    print(f"  Approx total tokens: {result.total_approx_tokens}")

    if error_counts:
        print("  Warning/error categories:")
        for category, count in sorted(error_counts.items()):
            print(f"    {category}: {count}")

    if contexts:
        print("\nSample contexts:")
        for context in contexts[:5]:
            marker = " warning" if context.error else ""
            print(f"  - {context.page_id} | role={context.page_role} | confidence={context.confidence}{marker}")
            print(f"    {context.short_summary}")

    if errored_contexts:
        print("\nContext warning/error examples:")
        for context in errored_contexts[:8 if args.show_error_details else 4]:
            print(f"  - {context.page_id}: {truncate(context.error)}")
        if not args.show_error_details and len(errored_contexts) > 4:
            print("  ... use --show-error-details to print more examples")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    return 0 if result.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
