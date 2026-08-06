#!/usr/bin/env python3
"""Gemma residency, cold-start recovery, and health telemetry for TRACE-Net.

This module changes only model residency, transport observability, and readiness.
It does not select routes/evidence, grant answer permission, mutate source truth,
or write to PostgreSQL, Qdrant, or OpenSearch.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Mapping, MutableMapping, Optional

MODULE = "trace_net_h30_gemma_residency_watchdog_v2"
PATCH_ID = "trace_net_h30_gemma_residency_watchdog_v2"


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    try:
        value = float(raw) if raw is not None else float(default)
    except (TypeError, ValueError):
        value = float(default)
    return max(minimum, value)


def native_ollama_base(value: str) -> str:
    base = str(value or "http://127.0.0.1:11434").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base.rstrip("/")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ollama_expiry(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Ollama may return nanoseconds; datetime accepts microseconds.
    if "." in text:
        prefix, suffix = text.split(".", 1)
        sign_positions = [position for position in (suffix.find("+"), suffix.find("-")) if position >= 0]
        if sign_positions:
            position = min(sign_positions)
            fraction, offset = suffix[:position], suffix[position:]
        else:
            fraction, offset = suffix, ""
        text = prefix + "." + fraction[:6].ljust(6, "0") + offset
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _request_json(
    url: str,
    *,
    payload: Optional[Mapping[str, Any]] = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any]]:
    data = None if payload is None else json.dumps(dict(payload)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if data is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            value = json.loads(raw) if raw.strip() else {}
            return response.status, dict(value) if isinstance(value, Mapping) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except Exception:
            value = {"error": raw or str(exc)}
        return exc.code, dict(value) if isinstance(value, Mapping) else {}
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}


def model_names(payload: Mapping[str, Any]) -> set[str]:
    rows = payload.get("models")
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("name") or row.get("model") or "")
        for row in rows
        if isinstance(row, Mapping) and (row.get("name") or row.get("model"))
    }


def progress_event(stage: str, message: str, *, model: str = "") -> bytes:
    """Return a non-answer SSE event safe to expose before validation.

    The event has no OpenAI ``choices`` content and therefore cannot be mistaken
    for validated assistant text. Clients that do not understand it may ignore it.
    """
    payload = {
        "object": "trace_net.progress",
        "created": int(time.time()),
        "model": model,
        "trace_net_progress": {
            "stage": str(stage),
            "message": str(message),
            "answer_content": False,
            "validated": True,
        },
    }
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")


def safe_stream_write(handler: Any, data: bytes) -> bool:
    try:
        handler.wfile.write(data)
        handler.wfile.flush()
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


class GemmaResidencyManager:
    """Keep one Ollama model resident without touching TRACE-Net evidence state."""

    def __init__(
        self,
        *,
        ollama_url: str,
        model: str,
        keep_alive: str = "1h",
        enabled: bool = True,
        require_resident: bool = True,
        check_interval_seconds: float = 300.0,
        renew_before_seconds: float = 900.0,
        preload_timeout_seconds: float = 300.0,
        request_json: Any = _request_json,
        clock: Any = time.monotonic,
    ) -> None:
        self.ollama_url = native_ollama_base(ollama_url)
        self.model = str(model)
        self.keep_alive = str(keep_alive or "1h")
        self.enabled = bool(enabled)
        self.require_resident = bool(require_resident)
        self.check_interval_seconds = max(10.0, float(check_interval_seconds))
        self.renew_before_seconds = max(0.0, float(renew_before_seconds))
        self.preload_timeout_seconds = max(10.0, float(preload_timeout_seconds))
        self._request_json = request_json
        self._clock = clock
        self._state_lock = threading.RLock()
        self._preload_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state: dict[str, Any] = {
            "resident_check_count": 0,
            "preload_attempt_count": 0,
            "preload_success_count": 0,
            "preload_failure_count": 0,
            "unexpected_eviction_count": 0,
            "last_check_at_utc": "",
            "last_preload_at_utc": "",
            "last_preload_reason": "",
            "last_preload_ms": None,
            "last_error": "",
            "last_resident": False,
            "last_expires_at": "",
            "last_seconds_remaining": None,
        }

    @classmethod
    def from_environment(cls, *, ollama_url: str, model: str) -> "GemmaResidencyManager":
        return cls(
            ollama_url=ollama_url,
            model=model,
            keep_alive=str(os.environ.get("TRACE_NET_GEMMA_KEEP_ALIVE", "1h") or "1h"),
            enabled=env_bool("TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_ENABLED", True),
            require_resident=env_bool("TRACE_NET_GEMMA_REQUIRE_RESIDENT", True),
            check_interval_seconds=env_float(
                "TRACE_NET_GEMMA_RESIDENCY_CHECK_INTERVAL_SECONDS", 300.0, minimum=10.0
            ),
            renew_before_seconds=env_float(
                "TRACE_NET_GEMMA_RENEW_BEFORE_SECONDS", 900.0, minimum=0.0
            ),
            preload_timeout_seconds=env_float(
                "TRACE_NET_GEMMA_PRELOAD_TIMEOUT_SECONDS", 300.0, minimum=10.0
            ),
        )

    def _resident_row(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        for row in payload.get("models") or []:
            if not isinstance(row, Mapping):
                continue
            name = str(row.get("name") or row.get("model") or "")
            if name == self.model:
                return dict(row)
        return {}

    def snapshot(self) -> dict[str, Any]:
        started = self._clock()
        tags_status, tags = self._request_json(
            self.ollama_url + "/api/tags", timeout=min(30.0, self.preload_timeout_seconds)
        )
        ps_status, ps = self._request_json(
            self.ollama_url + "/api/ps", timeout=min(30.0, self.preload_timeout_seconds)
        )
        available = tags_status == 200 and self.model in model_names(tags)
        row = self._resident_row(ps) if ps_status == 200 else {}
        resident = bool(row)
        expires_at = str(row.get("expires_at") or "")
        expiry = parse_ollama_expiry(expires_at)
        seconds_remaining: Optional[float] = None
        if expiry is not None:
            seconds_remaining = round(
                max(0.0, (expiry - datetime.now(timezone.utc)).total_seconds()), 3
            )
        elapsed_ms = round((self._clock() - started) * 1000.0, 3)
        with self._state_lock:
            previous_resident = bool(self._state.get("last_resident"))
            if previous_resident and not resident:
                self._state["unexpected_eviction_count"] = int(
                    self._state.get("unexpected_eviction_count") or 0
                ) + 1
            self._state.update({
                "resident_check_count": int(self._state.get("resident_check_count") or 0) + 1,
                "last_check_at_utc": utc_now(),
                "last_resident": resident,
                "last_expires_at": expires_at,
                "last_seconds_remaining": seconds_remaining,
            })
        return {
            "ollama_ready": tags_status == 200 and ps_status == 200,
            "ollama_tags_status": tags_status,
            "ollama_ps_status": ps_status,
            "gemma_model_available": available,
            "gemma_model_resident": resident,
            "gemma_resident_expires_at": expires_at,
            "gemma_resident_seconds_remaining": seconds_remaining,
            "gemma_size_vram": int(row.get("size_vram") or 0),
            "residency_check_ms": elapsed_ms,
            "loaded_ollama_models": sorted(model_names(ps)) if ps_status == 200 else [],
        }

    def preload(self, reason: str) -> dict[str, Any]:
        if not self.enabled:
            return {"attempted": False, "success": False, "reason": "watchdog_disabled"}
        with self._preload_lock:
            before = self.snapshot()
            remaining = before.get("gemma_resident_seconds_remaining")
            if before.get("gemma_model_resident") and (
                remaining is None or float(remaining) > self.renew_before_seconds
            ):
                return {
                    "attempted": False,
                    "success": True,
                    "reason": "already_resident",
                    "snapshot": before,
                }
            started = self._clock()
            with self._state_lock:
                self._state["preload_attempt_count"] = int(
                    self._state.get("preload_attempt_count") or 0
                ) + 1
                self._state["last_preload_at_utc"] = utc_now()
                self._state["last_preload_reason"] = str(reason)
            status, payload = self._request_json(
                self.ollama_url + "/api/generate",
                payload={
                    "model": self.model,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": self.keep_alive,
                },
                timeout=self.preload_timeout_seconds,
            )
            elapsed_ms = round((self._clock() - started) * 1000.0, 3)
            after = self.snapshot()
            success = status == 200 and bool(after.get("gemma_model_resident"))
            error = "" if success else str(payload.get("error") or f"preload_status_{status}")
            with self._state_lock:
                self._state["last_preload_ms"] = elapsed_ms
                self._state["last_error"] = error
                key = "preload_success_count" if success else "preload_failure_count"
                self._state[key] = int(self._state.get(key) or 0) + 1
            return {
                "attempted": True,
                "success": success,
                "reason": str(reason),
                "status": status,
                "preload_ms": elapsed_ms,
                "error": error,
                "snapshot": after,
            }

    def ensure_resident(self, reason: str) -> dict[str, Any]:
        snapshot = self.snapshot()
        remaining = snapshot.get("gemma_resident_seconds_remaining")
        renewal_due = bool(
            snapshot.get("gemma_model_resident")
            and remaining is not None
            and float(remaining) <= self.renew_before_seconds
        )
        if snapshot.get("gemma_model_resident") and not renewal_due:
            return {
                "attempted": False,
                "success": True,
                "reason": "resident",
                "snapshot": snapshot,
            }
        return self.preload("renewal:" + reason if renewal_due else reason)

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.wait(self.check_interval_seconds):
                try:
                    self.ensure_resident("watchdog")
                except Exception as exc:  # pragma: no cover - defensive daemon guard
                    with self._state_lock:
                        self._state["last_error"] = f"{type(exc).__name__}: {exc}"

        self._thread = threading.Thread(
            target=loop,
            name="trace-net-gemma-residency-watchdog",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def health(self, *, refresh: bool = True) -> dict[str, Any]:
        snapshot = self.snapshot() if refresh else {}
        with self._state_lock:
            state = dict(self._state)
        return {
            "residency_module": MODULE,
            "residency_patch_id": PATCH_ID,
            "gemma_residency_watchdog_enabled": self.enabled,
            "gemma_require_resident": self.require_resident,
            "gemma_residency_watchdog_running": bool(
                self._thread is not None and self._thread.is_alive()
            ),
            "gemma_keep_alive": self.keep_alive,
            "gemma_residency_check_interval_seconds": self.check_interval_seconds,
            "gemma_renew_before_seconds": self.renew_before_seconds,
            "gemma_preload_timeout_seconds": self.preload_timeout_seconds,
            **state,
            **snapshot,
            "cold_start_risk": not bool(snapshot.get("gemma_model_resident")),
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }


def _manager_for(runtime: Any, *, ollama_attr: str, model_attr: str) -> GemmaResidencyManager:
    manager = getattr(runtime, "gemma_residency_manager", None)
    if isinstance(manager, GemmaResidencyManager):
        return manager
    manager = GemmaResidencyManager.from_environment(
        ollama_url=str(getattr(runtime, ollama_attr)),
        model=str(getattr(runtime, model_attr)),
    )
    setattr(runtime, "gemma_residency_manager", manager)
    return manager


def install_writer_residency_watchdog(module: MutableMapping[str, Any]) -> None:
    """Overlay accurate residency health and pre-request recovery onto 8128."""
    if module.get("_TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_V2_INSTALLED"):
        return
    runtime_cls = module["Runtime"]
    original_init = runtime_cls.__init__
    original_health = runtime_cls.health
    original_process = runtime_cls.process

    def init_v2(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        manager = _manager_for(self, ollama_attr="gemma_base_url", model_attr="gemma_model")
        startup = manager.ensure_resident("writer_startup")
        setattr(self, "gemma_startup_residency", startup)
        manager.start()

    def health_v2(self: Any) -> dict[str, Any]:
        result = dict(original_health(self))
        manager = _manager_for(self, ollama_attr="gemma_base_url", model_attr="gemma_model")
        residency = manager.health(refresh=True)
        resident_ok = bool(residency.get("gemma_model_resident"))
        available_ok = bool(residency.get("gemma_model_available"))
        base_ok = result.get("quality_status") == "PASS"
        ready = base_ok and available_ok and (resident_ok or not manager.require_resident)
        result.update(residency)
        result.update({
            "quality_status": "PASS" if ready else "FAIL",
            "gemma_model_ready": ready,
            "gemma_model_available": available_ok,
            "gemma_model_resident": resident_ok,
            "cold_start_risk": not resident_ok,
        })
        return result

    def process_v2(self: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        manager = _manager_for(self, ollama_attr="gemma_base_url", model_attr="gemma_model")
        started = time.monotonic()
        before = manager.snapshot()
        recovery = manager.ensure_resident("writer_request")
        preflight_ms = round((time.monotonic() - started) * 1000.0, 3)
        result = dict(original_process(self, payload))
        timing = dict(result.get("timing") or {})
        after_snapshot = recovery.get("snapshot") if isinstance(recovery, Mapping) else {}
        timing.update({
            "gemma_residency_preflight_ms": preflight_ms,
            "gemma_resident_before_request": bool(before.get("gemma_model_resident")),
            "gemma_resident_after_preflight": bool(
                isinstance(after_snapshot, Mapping)
                and after_snapshot.get("gemma_model_resident")
            ),
            "gemma_preload_before_request": bool(recovery.get("attempted")),
            "gemma_preload_before_request_ms": recovery.get("preload_ms"),
            "gemma_cold_start_recovery_used": bool(recovery.get("attempted")),
        })
        result["timing"] = timing
        result["gemma_residency"] = {
            "resident_before_request": bool(before.get("gemma_model_resident")),
            "resident_after_preflight": bool(
                isinstance(after_snapshot, Mapping)
                and after_snapshot.get("gemma_model_resident")
            ),
            "preload_attempted": bool(recovery.get("attempted")),
            "preload_success": bool(recovery.get("success")),
            "preload_reason": str(recovery.get("reason") or ""),
            "preload_ms": recovery.get("preload_ms"),
            "cold_start_risk": not bool(before.get("gemma_model_resident")),
        }
        return result

    runtime_cls.__init__ = init_v2
    runtime_cls.health = health_v2
    runtime_cls.process = process_v2
    module["_TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_V2_INSTALLED"] = True


def install_nha_runtime_residency_watchdog(runtime_cls: type) -> None:
    """Overlay residency readiness onto an NHA proxy Runtime class."""
    if getattr(runtime_cls, "_TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_V2_INSTALLED", False):
        return
    original_init = runtime_cls.__init__
    original_health = runtime_cls.health

    def init_v2(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        manager = _manager_for(self, ollama_attr="ollama_url", model_attr="gemma_model")
        startup = manager.ensure_resident("nha_proxy_startup")
        setattr(self, "gemma_startup_residency", startup)
        manager.start()

    def health_v2(self: Any) -> dict[str, Any]:
        result = dict(original_health(self))
        manager = _manager_for(self, ollama_attr="ollama_url", model_attr="gemma_model")
        residency = manager.health(refresh=True)
        resident_ok = bool(residency.get("gemma_model_resident"))
        available_ok = bool(residency.get("gemma_model_available"))
        upstream_ok = bool(result.get("upstream_ready"))
        engram_ok = bool(result.get("engram_ready"))
        release_ok = int(result.get("real_relationship_count") or 0) > 0
        ready = upstream_ok and engram_ok and release_ok and available_ok and (
            resident_ok or not manager.require_resident
        )
        result.update(residency)
        result.update({
            "quality_status": "PASS" if ready else "FAIL",
            "gemma_ready": ready,
            "gemma_model_available": available_ok,
            "gemma_model_resident": resident_ok,
            "cold_start_risk": not resident_ok,
            "validated_buffered_streaming": False,
            "validated_progress_streaming": True,
        })
        return result

    runtime_cls.__init__ = init_v2
    runtime_cls.health = health_v2
    runtime_cls._TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_V2_INSTALLED = True
