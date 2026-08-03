#!/usr/bin/env python3
"""Atomic active-backend pointer utilities for TRACE-Net blue-green routing."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "trace_net_blue_green_pointer_v1"
STATUS = "TRACE_NET_BLUE_GREEN_POINTER_V1"
ALLOWED_COLORS = {"blue", "green", "legacy"}
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_MODEL = "trace-net-gemma4-cognitive-rag-v1"


def _validate_backend_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme != "http":
        raise ValueError("backend_url_must_use_http")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("backend_url_must_be_loopback")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("backend_url_contains_disallowed_components")
    if parsed.path not in {"", "/"}:
        raise ValueError("backend_url_must_not_contain_path")
    if parsed.port is None or not (1 <= parsed.port <= 65535):
        raise ValueError("backend_url_requires_valid_port")
    return raw


def validate_pointer(value: Mapping[str, Any]) -> dict[str, Any]:
    color = str(value.get("active_color") or "").strip().lower()
    if color not in ALLOWED_COLORS:
        raise ValueError("invalid_active_color")
    backend_url = _validate_backend_url(str(value.get("backend_url") or ""))
    model = str(value.get("model") or DEFAULT_MODEL).strip()
    if not model:
        raise ValueError("model_required")
    generation = int(value.get("generation") or 1)
    if generation < 1:
        raise ValueError("generation_must_be_positive")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "quality_status": "PASS",
        "active_color": color,
        "backend_url": backend_url,
        "model": model,
        "generation": generation,
        "updated_unix": float(value.get("updated_unix") or time.time()),
        "candidate_manifest": str(value.get("candidate_manifest") or ""),
        "read_only_pointer": True,
        "source_truth_mutation_allowed": False,
    }


def load_pointer(path: str | Path) -> dict[str, Any]:
    pointer_path = Path(path).expanduser().resolve()
    if not pointer_path.is_file():
        raise FileNotFoundError(f"active backend pointer not found: {pointer_path}")
    value = json.loads(pointer_path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("active backend pointer must be a JSON object")
    return validate_pointer(value)


def backend_health(backend_url: str, *, timeout: float = 8.0) -> tuple[int, dict[str, Any]]:
    url = _validate_backend_url(backend_url) + "/health"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            value = json.loads(raw)
            return int(response.status), dict(value) if isinstance(value, Mapping) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except Exception:
            value = {"error": raw or str(exc)}
        return int(exc.code), dict(value) if isinstance(value, Mapping) else {}
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}


def assert_backend_ready(backend_url: str, *, timeout: float = 8.0) -> dict[str, Any]:
    status, health = backend_health(backend_url, timeout=timeout)
    failures: list[str] = []
    if status != 200:
        failures.append(f"http_status:{status}")
    if health.get("quality_status") != "PASS":
        failures.append("quality_status_not_pass")
    if not health.get("upstream_ready", True):
        failures.append("upstream_not_ready")
    if not health.get("gemma_ready", True):
        failures.append("gemma_not_ready")
    if failures:
        raise RuntimeError("candidate backend health failed: " + ",".join(failures))
    return health


def atomic_write_pointer(
    path: str | Path,
    *,
    active_color: str,
    backend_url: str,
    model: str = DEFAULT_MODEL,
    candidate_manifest: str = "",
    validate_health: bool = True,
    timeout: float = 8.0,
) -> dict[str, Any]:
    pointer_path = Path(path).expanduser().resolve()
    previous: dict[str, Any] | None = None
    if pointer_path.is_file():
        previous = load_pointer(pointer_path)
    if validate_health:
        assert_backend_ready(backend_url, timeout=timeout)
    value = validate_pointer({
        "active_color": active_color,
        "backend_url": backend_url,
        "model": model,
        "generation": int((previous or {}).get("generation") or 0) + 1,
        "updated_unix": time.time(),
        "candidate_manifest": candidate_manifest,
    })
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=pointer_path.name + ".",
        suffix=".tmp",
        dir=str(pointer_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, pointer_path)
        try:
            directory_fd = os.open(pointer_path.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    show = subparsers.add_parser("show")
    show.add_argument("--pointer-path", required=True)

    set_parser = subparsers.add_parser("set")
    set_parser.add_argument("--pointer-path", required=True)
    set_parser.add_argument("--color", choices=sorted(ALLOWED_COLORS), required=True)
    set_parser.add_argument("--backend-url", required=True)
    set_parser.add_argument("--model", default=DEFAULT_MODEL)
    set_parser.add_argument("--candidate-manifest", default="")
    set_parser.add_argument("--timeout-seconds", type=float, default=8.0)
    set_parser.add_argument("--skip-health-check", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "show":
        value = load_pointer(args.pointer_path)
    else:
        value = atomic_write_pointer(
            args.pointer_path,
            active_color=args.color,
            backend_url=args.backend_url,
            model=args.model,
            candidate_manifest=args.candidate_manifest,
            validate_health=not args.skip_health_check,
            timeout=args.timeout_seconds,
        )
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))
    print("TRACE_NET_BLUE_GREEN_POINTER=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
