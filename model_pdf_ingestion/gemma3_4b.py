#!/usr/bin/env python3
"""Ingest wrapper fixed to `gemma3:4b`.

Usage: run this file the same way you'd run `doc_ingest.py`.
"""
from pathlib import Path
from doc_ingest import parse_args, resolve_pdf_path, run_ingest


def main() -> None:
    args = parse_args()
    args.model = "gemma3:4b"
    run_ingest(resolve_pdf_path(args.pdf), args.output, args.model, args.chunk_words, args.overlap, args.prompt)


if __name__ == "__main__":
    main()
