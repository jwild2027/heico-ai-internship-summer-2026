"""Small local config loader for TIFF/RAG scripts.

The project should not require a YAML dependency just to avoid long command
lines. This module supports either JSON or a conservative YAML-like format:

    db_path: local_data/db/tiff_search.db
    embed_model: bge-m3:latest
    llm_model: gemma3:12B
    top_k: 8
    use_llm: true

Nested YAML is intentionally not supported. Values are parsed as bool, int,
float, null, or strings. Quotes around strings are optional.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_LOCAL_CONFIG: dict[str, Any] = {
    "db_path": "local_data/db/tiff_search.db",
    "embed_model": "bge-m3:latest",
    "llm_model": "gemma3:12B",
    "ollama_url": "http://127.0.0.1:11434",
    "top_k": 8,
    "answer_mode": "auto",
    "retrieval_mode": "hybrid",
    "use_llm": True,
    "use_embeddings": True,
    "force_llm": False,
    "force_embeddings": False,
}


def _strip_inline_comment(line: str) -> str:
    """Remove unquoted ``#`` comments from one config line."""

    in_single = False
    in_double = False
    escaped = False
    out: list[str] = []
    for ch in line:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\":
            out.append(ch)
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            continue
        if ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out).strip()


def parse_scalar(value: str) -> Any:
    """Parse a simple scalar from the local config format."""

    raw = value.strip()
    if raw == "":
        return ""
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    lowered = raw.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "none", "~"}:
        return None
    try:
        if raw.startswith("0") and raw not in {"0", "0.0"} and not raw.startswith("0."):
            return raw
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def parse_simple_config_text(text: str) -> dict[str, Any]:
    """Parse JSON or a small YAML-like key/value config file."""

    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        data = json.loads(stripped)
        if not isinstance(data, dict):
            raise ValueError("JSON config must contain an object at the top level")
        return dict(data)

    data: dict[str, Any] = {}
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_inline_comment(raw_line)
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Config line {lineno} must be 'key: value': {raw_line!r}")
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Config line {lineno} has an empty key")
        data[key] = parse_scalar(value)
    return data


def load_local_config(path: str | Path | None = None, *, defaults: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Load a config file and merge it with defaults.

    Missing ``path`` means return defaults only. Unknown keys are preserved so
    scripts can opt into extra settings without changing this module.
    """

    merged = dict(DEFAULT_LOCAL_CONFIG if defaults is None else defaults)
    if path is None or str(path).strip() == "":
        return merged
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file does not exist: {cfg_path}")
    parsed = parse_simple_config_text(cfg_path.read_text(encoding="utf-8"))
    merged.update(parsed)
    return merged


def bool_from_config(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "on", "1"}:
        return True
    if text in {"false", "no", "off", "0"}:
        return False
    return default


def int_from_config(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default
