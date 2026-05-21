#!/usr/bin/env python3
"""Root-level launcher for the PyMuPDF + BGE + Chroma CLI.

This thin wrapper lets you run:
  python pymupdf_bge_chroma_cli.py ingest --pdf path/to/file.pdf

while keeping the real implementation in tools/pymupdf_bge_chroma_cli.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def load_tool_main():
    root = Path(__file__).resolve().parent
    tool_path = root / "tools" / "pymupdf_bge_chroma_cli.py"
    spec = importlib.util.spec_from_file_location("pymupdf_bge_chroma_cli_tool", tool_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load CLI implementation from {tool_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "main"):
        raise RuntimeError(f"CLI implementation at {tool_path} does not define main()")
    return module.main


def main() -> None:
    tool_main = load_tool_main()
    tool_main()


if __name__ == "__main__":
    main()