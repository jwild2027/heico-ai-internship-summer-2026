"""FastAPI app for the TIFF/RAG backend boundary.

Run locally with:

    python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000

This app currently reads the local MVP artifacts.  The route contract is meant
to survive the later migration to PostgreSQL/OpenSearch/Qdrant.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from tiff.api_backend import (
    api_status,
    ask_question,
    ata_lookup,
    organization_summary,
    page_lookup,
    part_lookup,
    submit_feedback,
    summarize_feedback,
    trace_page,
    trace_part,
    trace_vector_payload,
)

app = FastAPI(
    title="TIFF RAG API",
    version="0.1.0",
    description="API boundary for TIFF search, graph traceability, source-backed RAG, and feedback.",
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    config: str = "local_config.yaml"
    timeout_seconds: int = 240


class FeedbackRequest(BaseModel):
    question: str = Field(..., min_length=1)
    rating: str = Field(..., description="up, down, neutral, or 1-5")
    category: str = "other"
    reason: str = ""
    answer_id: str | None = None
    answer_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.get("/status")
def get_status() -> dict[str, Any]:
    return api_status()


@app.get("/organization/summary")
def get_organization_summary() -> dict[str, Any]:
    return organization_summary()


@app.get("/organization/parts/{part_number}")
def get_part(part_number: str, limit: int = 8) -> dict[str, Any]:
    result = part_lookup(part_number, limit=limit)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"part not found: {part_number}")
    return result


@app.get("/organization/pages/{page_id}")
def get_page(page_id: str, limit: int = 8) -> dict[str, Any]:
    result = page_lookup(page_id, limit=limit)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"page not found: {page_id}")
    return result


@app.get("/organization/ata/{ata_code}")
def get_ata(ata_code: str, limit: int = 12) -> dict[str, Any]:
    result = ata_lookup(ata_code, limit=limit)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"ATA section not found: {ata_code}")
    return result


@app.get("/trace/part/{part_number}")
def get_part_trace(part_number: str, limit: int = 8) -> dict[str, Any]:
    return trace_part(part_number, limit=limit)


@app.get("/trace/page/{page_id}")
def get_page_trace(page_id: str, limit: int = 8) -> dict[str, Any]:
    return trace_page(page_id, limit=limit)


@app.get("/trace/vector")
def get_vector_trace(page_id: str, chunk_id: str | None = None, score: float | None = None, limit: int = 8) -> dict[str, Any]:
    return trace_vector_payload(page_id=page_id, chunk_id=chunk_id, score=score, limit=limit)


@app.post("/ask")
def post_ask(request: AskRequest) -> dict[str, Any]:
    result = ask_question(
        request.question,
        config=request.config,
        timeout_seconds=request.timeout_seconds,
    )
    return result.to_jsonable()


@app.post("/feedback")
def post_feedback(request: FeedbackRequest) -> dict[str, Any]:
    return submit_feedback(
        question=request.question,
        rating=request.rating,
        category=request.category,
        reason=request.reason,
        answer_id=request.answer_id,
        answer_text=request.answer_text,
        metadata=request.metadata,
    )


@app.get("/feedback/summary")
def get_feedback_summary() -> dict[str, Any]:
    return summarize_feedback()
