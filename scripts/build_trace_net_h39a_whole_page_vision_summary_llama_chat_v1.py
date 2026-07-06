from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Tuple

from tiff import trace_net_h39a_whole_page_vision_summary_v1 as h39a


def _chat_url(url: str) -> str:
    if url.endswith("/api/generate"):
        return url[: -len("/api/generate")] + "/api/chat"
    if url.endswith("/api/chat"):
        return url
    return url.rstrip("/") + "/api/chat"


def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")[:4000]
    except Exception:
        return ""


def call_ollama_vision_chat(
    prompt: str,
    image_path: str | Path,
    model: str,
    ollama_url: str,
    timeout_seconds: int,
    num_ctx: int,
) -> Tuple[str, str]:
    """Call Ollama vision through /api/chat.

    Llama 3.2 Vision / mllama is often more reliable through messages[].images
    than the older /api/generate images payload.
    """

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [h39a._image_b64(image_path)],
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.05,
            "num_ctx": num_ctx,
        },
    }

    request = urllib.request.Request(
        _chat_url(ollama_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        message = data.get("message") or {}
        content = message.get("content") or data.get("response") or ""
        return str(content).strip(), ""
    except urllib.error.HTTPError as exc:
        return "", f"HTTPError {exc.code}: {exc.reason}; body={_read_http_error_body(exc)}"
    except Exception as exc:
        return "", repr(exc)


def main() -> int:
    # Monkey-patch only the Ollama transport. Everything else remains H39A:
    # discovery, source TIFF/page selection, JPEG conversion, Engram prompt,
    # safety contract, quality summary, and output schema.
    h39a.call_ollama_vision = call_ollama_vision_chat
    return h39a.main()


if __name__ == "__main__":
    raise SystemExit(main())
