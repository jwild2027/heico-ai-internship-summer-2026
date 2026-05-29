from __future__ import annotations

import json
from typing import Any

import pytest

from tiff import streamlit_api_client as client


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_normalize_api_url() -> None:
    assert client.normalize_api_url("127.0.0.1:8000/") == "http://127.0.0.1:8000"
    assert client.normalize_api_url("http://localhost:8000///") == "http://localhost:8000"
    assert client.normalize_api_url("") == client.DEFAULT_API_URL


def test_build_url_with_query() -> None:
    url = client.build_url("127.0.0.1:8000", "/trace/vector", {"page_id": "p1", "score": 0.5, "empty": ""})
    assert url.startswith("http://127.0.0.1:8000/trace/vector?")
    assert "page_id=p1" in url
    assert "score=0.5" in url
    assert "empty" not in url


def test_get_part_uses_expected_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_urlopen(request, timeout=0):  # noqa: ANN001
        calls.append(request.full_url)
        return FakeResponse({"status": "ok", "part_number": "120-37313-001"})

    monkeypatch.setattr(client, "urlopen", fake_urlopen)
    payload = client.get_part("http://api.test", "120-37313-001")
    assert payload["status"] == "ok"
    assert calls == ["http://api.test/organization/parts/120-37313-001"]


def test_ask_question_posts_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request, timeout=0):  # noqa: ANN001
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"answer": "ok"})

    monkeypatch.setattr(client, "urlopen", fake_urlopen)
    payload = client.ask_question("http://api.test", "What is part 120-37313-001?", timeout_seconds=25)
    assert payload["answer"] == "ok"
    assert seen["url"] == "http://api.test/ask"
    assert seen["method"] == "POST"
    assert seen["payload"] == {"question": "What is part 120-37313-001?", "timeout_seconds": 25}


def test_extract_answer_text_prefers_answer_field() -> None:
    assert client.extract_answer_text({"answer": " hello "}) == "hello"
    assert client.extract_answer_text({"data": {"stdout": "from stdout"}}) == "from stdout"
    assert "x" in client.extract_answer_text({"x": 1})
