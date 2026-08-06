"""Small stdlib-only Ollama client for local TIFF RAG.

This module intentionally uses urllib instead of requests so the repo does not need
another dependency. It talks only to a local or user-supplied Ollama server.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


class OllamaError(RuntimeError):
    """Raised when Ollama cannot be reached or returns an unexpected response."""


@dataclass(frozen=True)
class OllamaClient:
    """Minimal Ollama API client.

    Parameters
    ----------
    base_url:
        Ollama base URL. Use the default for local Ollama Desktop/daemon.
    timeout:
        Network timeout in seconds.
    """

    base_url: str = DEFAULT_OLLAMA_URL
    timeout: float = 120.0

    def _url(self, path: str) -> str:
        return self.base_url.rstrip("/") + path

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._url(path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise OllamaError(f"Could not reach Ollama at {self.base_url}: {exc}") from exc
        except TimeoutError as exc:
            raise OllamaError(f"Ollama request timed out at {self.base_url}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Ollama returned invalid JSON: {raw[:200]}") from exc

    def embed(self, model: str, texts: str | Iterable[str]) -> list[list[float]]:
        """Return embeddings for one or more texts.

        Uses Ollama's newer /api/embed endpoint first. If a local Ollama build only
        supports the older /api/embeddings endpoint, falls back to one text at a
        time.
        """

        if isinstance(texts, str):
            input_texts = [texts]
        else:
            input_texts = [str(t) for t in texts]
        if not input_texts:
            return []

        try:
            response = self._post_json("/api/embed", {"model": model, "input": input_texts})
            embeddings = response.get("embeddings")
            if isinstance(embeddings, list) and embeddings:
                return [[float(x) for x in emb] for emb in embeddings]
        except OllamaError:
            # Try the older endpoint below before giving up.
            pass

        vectors: list[list[float]] = []
        for text in input_texts:
            response = self._post_json("/api/embeddings", {"model": model, "prompt": text})
            embedding = response.get("embedding")
            if not isinstance(embedding, list):
                raise OllamaError("Ollama did not return an embedding vector")
            vectors.append([float(x) for x in embedding])
        return vectors

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        num_ctx: int | None = None,
    ) -> str:
        """Call Ollama /api/chat and return the assistant message text."""

        options: dict[str, Any] = {"temperature": temperature}
        if num_ctx is not None:
            options["num_ctx"] = num_ctx
        response = self._post_json(
            "/api/chat",
            {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": options,
            },
        )
        message = response.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise OllamaError("Ollama chat response did not include message.content")
        return content.strip()
