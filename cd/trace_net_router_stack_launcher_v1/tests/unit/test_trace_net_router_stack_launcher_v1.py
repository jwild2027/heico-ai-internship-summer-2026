from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts/operations/router/launch_trace_net_router_stack_v1.py"

import importlib.util
spec = importlib.util.spec_from_file_location("launcher", SCRIPT_PATH)
launcher = importlib.util.module_from_spec(spec)
sys.modules["launcher"] = launcher
spec.loader.exec_module(launcher)


def _args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        host="127.0.0.1",
        normal_port=8014,
        guided_port=8016,
        router_port=8017,
        artifact_root="local_data/organization/trace_net",
        output_root=str(tmp_path),
        top_k=8,
        loose_top_k=8,
        startup_timeout_seconds=0.01,
        python_exe=sys.executable,
    )


def _make_required_scripts(root: Path) -> None:
    for rel in (launcher.NORMAL_SCRIPT, launcher.GUIDED_SCRIPT, launcher.ROUTER_SCRIPT):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("print('stub')\n", encoding="utf-8")


def test_build_specs_uses_expected_ports_and_commands(tmp_path, monkeypatch):
    _make_required_scripts(tmp_path)
    monkeypatch.chdir(tmp_path)
    specs = launcher.build_specs(_args(tmp_path / "out"))

    assert [s.name for s in specs] == [
        "normal_endpoint_8014",
        "guided_discovery_endpoint_8016",
        "router_proxy_8017",
    ]
    assert specs[0].health_url == "http://127.0.0.1:8014/health"
    assert specs[1].health_url == "http://127.0.0.1:8016/health"
    assert specs[2].health_url == "http://127.0.0.1:8017/health"

    guided = " ".join(specs[1].command)
    assert "serve_trace_net_guided_candidate_discovery_endpoint_v1.py" in guided
    assert "--artifact-root local_data/organization/trace_net" in guided

    router = " ".join(specs[2].command)
    assert "serve_trace_net_guided_discovery_router_proxy_v3.py" in router
    assert "--normal-base-url http://127.0.0.1:8014" in router
    assert "--guided-base-url http://127.0.0.1:8016" in router


def test_missing_required_script_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="Required script not found"):
        launcher.build_specs(_args(tmp_path / "out"))


def test_write_manifest_contains_web_ui_target(tmp_path, monkeypatch):
    _make_required_scripts(tmp_path)
    monkeypatch.chdir(tmp_path)
    args = _args(tmp_path / "out")
    specs = launcher.build_specs(args)

    manifest_path = launcher._write_manifest(args, specs, [], launcher.STATUS_READY)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["status"] == launcher.STATUS_READY
    assert payload["quality_status"] == "PASS"
    assert payload["router_base_url"] == "http://127.0.0.1:8017/v1"
    assert payload["router_model"] == "trace-net-router-proxy-v3"
    assert payload["safety_contract"]["read_only"] is True
    assert payload["safety_contract"]["postgres_write_attempt_count"] == 0


def test_health_ok_false_on_url_error(monkeypatch):
    def bad_urlopen(*args, **kwargs):
        raise OSError("offline")
    monkeypatch.setattr(launcher.urllib.request, "urlopen", bad_urlopen)
    assert launcher._health_ok("http://127.0.0.1:1/health") is False


def test_start_service_writes_log_and_uses_unbuffered_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log_path = tmp_path / "logs" / "svc.log"
    spec = launcher.ServiceSpec(
        name="svc",
        command=[sys.executable, "-c", "print('hello')"],
        health_url="http://127.0.0.1:9999/health",
        log_path=log_path,
    )

    managed = launcher.start_service(spec)
    managed.process.wait(timeout=5)
    managed.log_handle.close()

    content = log_path.read_text(encoding="utf-8")
    assert "Starting svc" in content
    assert "Command:" in content
    assert "hello" in content


def test_py_compile_launcher():
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
