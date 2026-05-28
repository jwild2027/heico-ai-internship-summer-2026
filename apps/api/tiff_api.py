"""FastAPI app for the local TIFF/RAG backend.

Run locally with:
    python -m uvicorn apps.api.tiff_api:app --reload

This app is read-only except for the /ask endpoint, which shells out to the
existing scripts/ask_tiff_rag.py command. It does not rebuild OCR or mutate the
index database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Query
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - only hit when dependency missing
    raise SystemExit(
        "FastAPI dependencies are missing. Install them with: "
        "python -m pip install fastapi uvicorn"
    ) from exc

from tiff.api_backend import (
    ask_question,
    check_api_ready,
    find_ata,
    find_page,
    find_part,
    get_organization_summary,
    get_status,
    load_api_data,
    make_paths,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(
    title="HEICO TIFF/RAG API",
    version="0.1.0",
    description="Read-only API over the local TIFF organization/RAG backend.",
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    timeout_seconds: int = Field(180, ge=10, le=600)


@app.get("/health")
def health() -> dict[str, Any]:
    return check_api_ready(make_paths(repo_root=REPO_ROOT))


@app.get("/status")
def status() -> dict[str, Any]:
    data = _load()
    return get_status(data)


@app.get("/organization/summary")
def organization_summary() -> dict[str, Any]:
    data = _load()
    return get_organization_summary(data)


@app.get("/organization/part/{part_number}")
def organization_part(part_number: str, limit_pages: int = Query(10, ge=1, le=100)) -> dict[str, Any]:
    data = _load()
    row = find_part(data, part_number, limit_pages=limit_pages)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Part not found: {part_number}")
    return row


@app.get("/organization/ata/{ata_code}")
def organization_ata(ata_code: str, limit_pages: int = Query(10, ge=1, le=100)) -> dict[str, Any]:
    data = _load()
    row = find_ata(data, ata_code, limit_pages=limit_pages)
    if row is None:
        raise HTTPException(status_code=404, detail=f"ATA not found: {ata_code}")
    return row


@app.get("/organization/page/{page_id}")
def organization_page(page_id: str) -> dict[str, Any]:
    data = _load()
    row = find_page(data, page_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    return row


@app.post("/ask")
def ask(request: AskRequest) -> dict[str, Any]:
    result = ask_question(
        request.question,
        repo_root=REPO_ROOT,
        config_path="local_config.yaml",
        timeout_seconds=request.timeout_seconds,
    )
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result


def _load():
    return load_api_data(make_paths(repo_root=REPO_ROOT))
