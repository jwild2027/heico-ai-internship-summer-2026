#!/usr/bin/env python3
"""PDF ingestion using pdfplumber + shared AI summarization pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from doc_ingest import (  # noqa: E402
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_WORDS,
    DEFAULT_PROMPT,
    run_ingest_with_pages,
    resolve_pdf_path,
)

MODEL = "gemma3:4b"
DEFAULT_PDF = Path(r"C:\Users\juswil\Desktop\test-2.pdf")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest PDF with pdfplumber and summarize with Gemma.")
    parser.add_argument("--pdf", "-p", type=Path, default=DEFAULT_PDF, help="Path to the PDF file to ingest.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("results/pdfplumber_output.json"),
        help="Where to save JSON output.",
    )
    parser.add_argument("--chunk-words", type=int, default=DEFAULT_CHUNK_WORDS)
    parser.add_argument("--overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--prompt", "-t", default=DEFAULT_PROMPT)
    return parser.parse_args()


def extract_pages_pdfplumber(pdf_path: Path) -> list[dict[str, Any]]:
    import pdfplumber

    pages: list[dict[str, Any]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append({"page": index, "text": text})
    return pages


def main() -> None:
    args = parse_args()
    pdf_path = resolve_pdf_path(args.pdf)
    pages = extract_pages_pdfplumber(pdf_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    run_ingest_with_pages(
        pages=pages,
        source_pdf=pdf_path,
        output=args.output,
        model=MODEL,
        chunk_words=args.chunk_words,
        overlap=args.overlap,
        prompt=args.prompt,
    )


if __name__ == "__main__":
    main()
