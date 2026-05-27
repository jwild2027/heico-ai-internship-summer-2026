#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.ollama_client import DEFAULT_OLLAMA_URL  # noqa: E402
from tiff.rag_web_ui import serve_rag_ui  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve local TIFF RAG web UI")
    parser.add_argument("--db-path", default="local_data/db/tiff_search.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--embed-model", default="bge-m3:latest")
    parser.add_argument("--llm-model", default="llama3.1:8b")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    server = serve_rag_ui(
        db_path=Path(args.db_path),
        host=args.host,
        port=args.port,
        embed_model=args.embed_model,
        llm_model=args.llm_model,
        ollama_url=args.ollama_url,
    )
    url = f"http://{args.host}:{args.port}"
    print("Local TIFF RAG UI running")
    print(f"  URL: {url}")
    print(f"  DB: {args.db_path}")
    print(f"  Embed model: {args.embed_model}")
    print(f"  LLM model: {args.llm_model}")
    print("Press Ctrl+C to stop.")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
