#!/usr/bin/env python3
"""Run all scraper variants on the same PDF with the same Gemma model."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = [
    ("pypdf", "pypdf_ingest.py", "pypdf_output.json"),
    ("pdfplumber", "pdfplumber_ingest.py", "pdfplumber_output.json"),
    ("unstructured", "unstructured_ingest.py", "unstructured_output.json"),
    ("pymupdf", "pymupdf_ingest.py", "pymupdf_output.json"),
]

DEFAULT_PDF = Path(r"C:\Users\juswil\Desktop\test-2.pdf")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PDF scraper comparison with a fixed Gemma model.")
    parser.add_argument("--pdf", "-p", type=Path, default=DEFAULT_PDF, help="PDF path to process.")
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--chunk-words", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=40)
    parser.add_argument("--prompt", "-t", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scripts_dir = Path(__file__).resolve().parent
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[str, bool, str]] = []

    for name, script, output_name in SCRIPTS:
        output_path = args.output_dir / output_name
        cmd = [
            sys.executable,
            str(scripts_dir / script),
            "--pdf",
            str(args.pdf),
            "--output",
            str(output_path),
            "--chunk-words",
            str(args.chunk_words),
            "--overlap",
            str(args.overlap),
        ]
        if args.prompt:
            cmd.extend(["--prompt", args.prompt])

        print(f"\n=== Running {name} scraper ===")
        completed = subprocess.run(cmd, check=False)
        if completed.returncode == 0:
            results.append((name, True, str(output_path)))
        else:
            results.append((name, False, f"exit code {completed.returncode}"))

    print("\nComparison run complete.")
    for name, ok, detail in results:
        status = "OK" if ok else "FAILED"
        print(f"- {name}: {status} ({detail})")


if __name__ == "__main__":
    main()
