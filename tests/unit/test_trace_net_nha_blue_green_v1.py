from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import serve_trace_net_blue_green_frontdoor_v1 as frontdoor
from scripts import trace_net_blue_green_pointer_v1 as pointer

REPO = Path(__file__).resolve().parents[2]


def test_pointer_rejects_non_loopback_backend():
    with pytest.raises(ValueError, match="loopback"):
        pointer.validate_pointer({
            "active_color": "green",
            "backend_url": "http://10.0.1.99:8231",
            "model": pointer.DEFAULT_MODEL,
            "generation": 1,
        })


def test_pointer_atomic_write_and_load(tmp_path: Path):
    path = tmp_path / "active.json"
    first = pointer.atomic_write_pointer(
        path,
        active_color="green",
        backend_url="http://127.0.0.1:8231",
        validate_health=False,
    )
    loaded = pointer.load_pointer(path)
    assert loaded["active_color"] == "green"
    assert loaded["backend_url"] == "http://127.0.0.1:8231"
    assert loaded["generation"] == first["generation"] == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_pointer_generation_increments(tmp_path: Path):
    path = tmp_path / "active.json"
    pointer.atomic_write_pointer(
        path,
        active_color="green",
        backend_url="http://127.0.0.1:8231",
        validate_health=False,
    )
    second = pointer.atomic_write_pointer(
        path,
        active_color="blue",
        backend_url="http://127.0.0.1:8331",
        validate_health=False,
    )
    assert second["generation"] == 2
    assert pointer.load_pointer(path)["active_color"] == "blue"


def test_frontdoor_health_reloads_pointer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    path = tmp_path / "active.json"
    pointer.atomic_write_pointer(
        path,
        active_color="green",
        backend_url="http://127.0.0.1:8231",
        validate_health=False,
    )

    def healthy(url, payload, *, api_key, timeout):
        return 200, {"quality_status": "PASS", "module": "candidate"}, {}

    monkeypatch.setattr(frontdoor, "request_json", healthy)
    runtime = frontdoor.Runtime(
        pointer_path=str(path),
        backend_api_key="k",
        public_api_key="k",
        public_model=pointer.DEFAULT_MODEL,
        timeout=10,
    )
    assert runtime.health()["active_color"] == "green"
    pointer.atomic_write_pointer(
        path,
        active_color="blue",
        backend_url="http://127.0.0.1:8331",
        validate_health=False,
    )
    health = runtime.health()
    assert health["active_color"] == "blue"
    assert health["active_backend"] == "http://127.0.0.1:8331"
    assert health["dynamic_pointer_reload"] is True


def test_frontdoor_preserves_trace_headers():
    headers = frontdoor.trace_headers(
        {"x-trace-net-model-calls": "1", "content-type": "application/json"},
        {"active_color": "green", "generation": 3, "backend_url": "http://127.0.0.1:8231"},
    )
    assert headers["X-Trace-Net-Model-Calls"] == "1"
    assert headers["X-Trace-Net-Blue-Green-Color"] == "green"
    assert "Content-Type" not in headers


def test_phase20_wrapper_delegates_to_blue_green_without_nested_handler():
    text = (REPO / "scripts/run_trace_net_nha_phase20_final_server_gate_v1.sh").read_text(encoding="utf-8")
    assert "run_trace_net_nha_blue_green_final_gate_v1.sh" in text
    assert "rollback_on_failure" not in text
    assert "launch_trace_net_nha_phase19_stack_v1.sh" not in text


def test_final_gate_cleans_only_candidate_services():
    text = (REPO / "scripts/run_trace_net_nha_blue_green_final_gate_v1.sh").read_text(encoding="utf-8")
    assert "launch_trace_net_nha_blue_green_candidate_v1.sh" in text
    assert "launch_trace_net_nha_phase19_stack_v1.sh" not in text
    assert "production_ports_restarted=false" in text
    assert "run_trace_net_nha_phase20_gemma100_v1.py" in text
    assert "run_trace_net_nha_phase18_unified8131_gate_v1.py" in text


def test_candidate_launcher_does_not_stop_production_router_or_writer():
    text = (REPO / "scripts/launch_trace_net_nha_blue_green_candidate_v1.sh").read_text(encoding="utf-8")
    assert "stop_one \"$ROUTER_SESSION\" \"$ROUTER_PORT\"" in text
    assert "stop_one \"$WRITER_SESSION\" \"$WRITER_PORT\"" in text
    assert "8118/tcp" not in text
    assert "8128/tcp" not in text
    assert "8131/tcp" not in text


def test_promoter_never_rebuilds_8118_or_8128():
    text = (REPO / "scripts/promote_trace_net_nha_blue_green_v1.sh").read_text(encoding="utf-8")
    assert "launch_trace_net_cognitive_openwebui_v1.sh" not in text
    assert "8118/tcp" not in text
    assert "8128/tcp" not in text
    assert "atomic_pointer_only" in text
    assert "serve_trace_net_blue_green_frontdoor_v1.py" in text


def test_color_port_sets_are_disjoint():
    text = (REPO / "scripts/launch_trace_net_nha_blue_green_candidate_v1.sh").read_text(encoding="utf-8")
    for value in ("8218", "8228", "8231", "8233", "8318", "8328", "8331", "8333"):
        assert value in text
    assert len({8218, 8228, 8231, 8233, 8318, 8328, 8331, 8333}) == 8


def test_tracked_answer_key_has_50_unambiguous_relationships():
    fixture = REPO / "tests/fixtures/trace_net_nha_phase20_synthetic_direct_parent_answer_key_v1.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    rows = payload.get("relationships") or []
    assert payload.get("quality_status") == "PASS"
    assert len(rows) == 50
    assert len({row["relationship_id"] for row in rows}) == 50
    assert all(len(row.get("parent_candidates") or []) == 1 for row in rows)


def test_candidate_manifest_contract_is_read_only(tmp_path: Path):
    sample = {
        "schema_version": "trace_net_blue_green_candidate_v1",
        "quality_status": "PASS",
        "production_ports_touched": [],
        "rollback_handler_present": False,
    }
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(sample), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["production_ports_touched"] == []
    assert loaded["rollback_handler_present"] is False
