"""Small standard-library client for the TIFF FastAPI boundary.

This module is intentionally dependency-light so Streamlit can call the API
without pulling in requests/httpx.  It is also easy to swap out later when the
UI moves to a production frontend.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_API_URL = "http://127.0.0.1:8000"


class TiffApiError(RuntimeError):
    """Raised when the TIFF API cannot be reached or returns invalid JSON."""


@dataclass(frozen=True)
class ApiResult:
    """Thin wrapper for API responses used by the UI."""

    data: dict[str, Any]
    status_code: int | None = None


def normalize_api_url(api_url: str | None) -> str:
    """Return a clean API base URL.

    Accepts plain host:port values as a convenience, for example
    ``127.0.0.1:8000`` becomes ``http://127.0.0.1:8000``.
    """

    cleaned = (api_url or DEFAULT_API_URL).strip()
    if not cleaned:
        cleaned = DEFAULT_API_URL
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"http://{cleaned}"
    return cleaned.rstrip("/")


def build_url(api_url: str, path: str, query: dict[str, Any] | None = None) -> str:
    base = normalize_api_url(api_url)
    cleaned_path = path if path.startswith("/") else f"/{path}"
    url = f"{base}{cleaned_path}"
    if query:
        filtered = {k: v for k, v in query.items() if v is not None and v != ""}
        if filtered:
            url = f"{url}?{urlencode(filtered)}"
    return url


def _request_json(
    api_url: str,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    timeout_seconds: float = 60.0,
) -> ApiResult:
    url = build_url(api_url, path, query=query)
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url=url, data=body, method=method.upper(), headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - local/dev API client
            raw = response.read().decode("utf-8", errors="replace")
            status = getattr(response, "status", None)
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise TiffApiError(f"API returned HTTP {exc.code} for {url}: {raw_body[:500]}") from exc
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise TiffApiError(f"Could not reach TIFF API at {url}: {exc}") from exc

    if not raw.strip():
        return ApiResult(data={}, status_code=status)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TiffApiError(f"API returned invalid JSON for {url}: {raw[:500]}") from exc
    if not isinstance(parsed, dict):
        raise TiffApiError(f"API returned a non-object JSON payload for {url}: {type(parsed).__name__}")
    return ApiResult(data=parsed, status_code=status)


def get_status(api_url: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    return _request_json(api_url, "GET", "/status", timeout_seconds=timeout_seconds).data


def get_organization_summary(api_url: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    return _request_json(api_url, "GET", "/organization/summary", timeout_seconds=timeout_seconds).data


def get_part(api_url: str, part_number: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    return _request_json(
        api_url,
        "GET",
        f"/organization/parts/{part_number}",
        timeout_seconds=timeout_seconds,
    ).data


def get_page(api_url: str, page_id: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    return _request_json(api_url, "GET", f"/organization/pages/{page_id}", timeout_seconds=timeout_seconds).data


def get_ata(api_url: str, ata_code: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    return _request_json(api_url, "GET", f"/organization/ata/{ata_code}", timeout_seconds=timeout_seconds).data


def trace_part(api_url: str, part_number: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    return _request_json(api_url, "GET", f"/trace/part/{part_number}", timeout_seconds=timeout_seconds).data


def trace_page(api_url: str, page_id: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    return _request_json(api_url, "GET", f"/trace/page/{page_id}", timeout_seconds=timeout_seconds).data


def trace_vector(
    api_url: str,
    *,
    page_id: str,
    chunk_id: str | None = None,
    score: float | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    return _request_json(
        api_url,
        "GET",
        "/trace/vector",
        query={"page_id": page_id, "chunk_id": chunk_id, "score": score},
        timeout_seconds=timeout_seconds,
    ).data


def ask_question(api_url: str, question: str, *, timeout_seconds: float = 120.0) -> dict[str, Any]:
    return _request_json(
        api_url,
        "POST",
        "/ask",
        payload={"question": question, "timeout_seconds": timeout_seconds},
        timeout_seconds=timeout_seconds + 10,
    ).data


def submit_feedback(
    api_url: str,
    *,
    question: str,
    answer: str,
    rating: str,
    category: str,
    reason: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    return _request_json(
        api_url,
        "POST",
        "/feedback",
        payload={
            "question": question,
            "answer": answer,
            "rating": rating,
            "category": category,
            "reason": reason,
        },
        timeout_seconds=timeout_seconds,
    ).data


def get_feedback_summary(api_url: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    return _request_json(api_url, "GET", "/feedback/summary", timeout_seconds=timeout_seconds).data


def extract_answer_text(payload: dict[str, Any]) -> str:
    """Best-effort extraction of the answer text from compatible API responses."""

    for key in ("answer", "answer_text", "output", "stdout", "response"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = payload.get("data")
    if isinstance(nested, dict):
        return extract_answer_text(nested)
    return json.dumps(payload, indent=2, ensure_ascii=False)
