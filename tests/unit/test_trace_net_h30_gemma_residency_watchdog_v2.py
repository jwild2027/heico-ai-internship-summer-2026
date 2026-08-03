from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from scripts.trace_net_h30_gemma_residency_watchdog_v2 import (
    GemmaResidencyManager,
    parse_ollama_expiry,
    progress_event,
)


class FakeOllama:
    def __init__(self, *, resident: bool, expires_in: float = 3600.0) -> None:
        self.resident = resident
        self.expires_in = expires_in
        self.generate_calls = 0
        self.calls: list[tuple[str, object]] = []

    def __call__(self, url: str, *, payload=None, timeout=30.0):
        self.calls.append((url, payload))
        if url.endswith("/api/tags"):
            return 200, {"models": [{"name": "gemma4:26b"}]}
        if url.endswith("/api/ps"):
            if not self.resident:
                return 200, {"models": []}
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=self.expires_in)
            ).isoformat()
            return 200, {
                "models": [{
                    "name": "gemma4:26b",
                    "expires_at": expires_at,
                    "size_vram": 18_388_111_849,
                }]
            }
        if url.endswith("/api/generate"):
            self.generate_calls += 1
            self.resident = True
            self.expires_in = 3600.0
            assert payload["model"] == "gemma4:26b"
            assert payload["prompt"] == ""
            assert payload["stream"] is False
            assert payload["keep_alive"] == "1h"
            return 200, {"done": True}
        raise AssertionError(url)


def manager(fake: FakeOllama, *, renew_before: float = 900.0) -> GemmaResidencyManager:
    return GemmaResidencyManager(
        ollama_url="http://127.0.0.1:11434/v1",
        model="gemma4:26b",
        keep_alive="1h",
        enabled=True,
        require_resident=True,
        check_interval_seconds=300,
        renew_before_seconds=renew_before,
        preload_timeout_seconds=300,
        request_json=fake,
    )


def test_parse_ollama_expiry_accepts_nanoseconds() -> None:
    value = parse_ollama_expiry("2026-08-03T09:27:15.798095103-04:00")
    assert value is not None
    assert value.tzinfo is not None
    assert value.astimezone(timezone.utc).year == 2026


def test_cold_model_is_preloaded_and_verified() -> None:
    fake = FakeOllama(resident=False)
    result = manager(fake).ensure_resident("unit_test")
    assert result["attempted"] is True
    assert result["success"] is True
    assert result["snapshot"]["gemma_model_resident"] is True
    assert fake.generate_calls == 1


def test_warm_model_does_not_receive_unnecessary_preload() -> None:
    fake = FakeOllama(resident=True, expires_in=3600)
    result = manager(fake).ensure_resident("unit_test")
    assert result["attempted"] is False
    assert result["success"] is True
    assert fake.generate_calls == 0


def test_near_expiry_model_is_renewed() -> None:
    fake = FakeOllama(resident=True, expires_in=60)
    result = manager(fake, renew_before=900).ensure_resident("unit_test")
    assert result["attempted"] is True
    assert result["success"] is True
    assert result["reason"].startswith("renewal:")
    assert fake.generate_calls == 1


def test_health_separates_availability_from_residency() -> None:
    fake = FakeOllama(resident=False)
    health = manager(fake).health(refresh=True)
    assert health["ollama_ready"] is True
    assert health["gemma_model_available"] is True
    assert health["gemma_model_resident"] is False
    assert health["cold_start_risk"] is True
    assert health["answer_permission"] is False
    assert health["source_truth_mutation_allowed"] is False
    assert health["postgres_write_attempt_count"] == 0
    assert health["qdrant_write_attempt_count"] == 0
    assert health["opensearch_write_attempt_count"] == 0


def test_progress_event_is_not_assistant_answer_content() -> None:
    raw = progress_event(
        "gemma_writing",
        "Gemma is wording approved evidence.",
        model="trace-net-gemma4-cognitive-rag-v1",
    ).decode("utf-8")
    assert raw.startswith("data: ")
    payload = json.loads(raw[6:].strip())
    assert payload["object"] == "trace_net.progress"
    assert payload["trace_net_progress"]["answer_content"] is False
    assert payload["trace_net_progress"]["validated"] is True
    assert "choices" not in payload
