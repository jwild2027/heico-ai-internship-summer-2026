"""tools/chroma_client.py — Chroma client factory.

Reads CHROMA_HOST / CHROMA_PORT env vars at runtime.
If set → connects to Chroma HTTP server (Docker).
If not set → uses local PersistentClient (dev/local).

Drop-in replacement for the get_collection() call in pymupdf_bge_chroma_cli.py.

Usage:
    from tools.chroma_client import get_collection
    collection = get_collection(persist_dir, "pdf_chunks")
"""
from __future__ import annotations

import os
from pathlib import Path

import chromadb


def get_client(persist_dir: Path) -> chromadb.ClientAPI:
    """Return a Chroma client — HTTP if env vars set, local otherwise."""
    host = os.getenv("CHROMA_HOST", "").strip()
    port = int(os.getenv("CHROMA_PORT", "8000"))

    if host:
        return chromadb.HttpClient(host=host, port=port)

    return chromadb.PersistentClient(path=str(persist_dir))


def get_collection(persist_dir: Path, collection_name: str) -> chromadb.Collection:
    """Get or create a named collection from the appropriate Chroma client."""
    client = get_client(persist_dir)
    return client.get_or_create_collection(name=collection_name)