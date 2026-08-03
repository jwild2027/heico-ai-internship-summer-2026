from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts/operations/launch_trace_net_cognitive_openwebui_v1.sh"

ENV_TO_LOCAL = {
    "TRACE_NET_H30_PLANNER_ROLLOUT_MODE": "PLANNER_ROLLOUT_MODE",
    "TRACE_NET_H30_PLANNER_EXECUTION_ENABLED": "PLANNER_EXECUTION_ENABLED",
    "TRACE_NET_H30_PLANNER_MAX_LATENCY_MS": "PLANNER_MAX_LATENCY_MS",
    "TRACE_NET_H30_PLANNER_BREAKER_FAILURE_THRESHOLD": "PLANNER_BREAKER_FAILURE_THRESHOLD",
    "TRACE_NET_H30_PLANNER_BREAKER_SECONDS": "PLANNER_BREAKER_SECONDS",
    "TRACE_NET_H30_PLANNER_CANONICAL_BRIDGE_ENABLED": "PLANNER_CANONICAL_BRIDGE_ENABLED",
    "TRACE_NET_H30_PLANNER_REQUIRE_ROUTE": "PLANNER_REQUIRE_ROUTE",
}


def launcher_text() -> str:
    assert LAUNCHER.is_file(), f"missing committed launcher: {LAUNCHER}"
    return LAUNCHER.read_text(encoding="utf-8")


def test_committed_launcher_captures_all_phase45_settings():
    text = launcher_text()
    for env_name, local_name in ENV_TO_LOCAL.items():
        assert f'{local_name}="${{{env_name}:-' in text


def test_committed_launcher_exports_settings_into_8118_process():
    text = launcher_text()
    start = text.index("cat > /tmp/start_trace_net_cognitive_8118.sh")
    end = text.index("\nINNER", start)
    block = text[start:end]
    for env_name, local_name in ENV_TO_LOCAL.items():
        assert f'export {env_name}="${local_name}"' in block


def test_committed_launcher_bounds_rollout_modes():
    text = launcher_text()
    assert "validate_only|narrow|broad|mature" in text
    assert "invalid_planner_rollout_mode=" in text


def test_committed_launcher_checks_live_mode_phase_and_execution():
    text = launcher_text()
    required = (
        'actual_mode = str(health.get("planner_rollout_mode") or "")',
        'actual_execution = bool(health.get("planner_execution_enabled"))',
        '"validate_only": 2',
        '"narrow": 3',
        '"broad": 4',
        '"mature": 5',
        "if actual_mode != requested_mode:",
        "if actual_execution is not expected_execution:",
        "if actual_phase != expected_phase:",
        "planner launcher environment mismatch:",
        'print("planner_launcher_env_check=PASS")',
    )
    for fragment in required:
        assert fragment in text


def test_committed_launcher_saves_and_validates_8118_health():
    text = launcher_text()
    assert '> "$RUNTIME/8118_health.json"' in text
    assert '"$PYTHON" -m json.tool "$RUNTIME/8118_health.json"' in text
    assert (
        '"$PYTHON" - "$RUNTIME/8118_health.json" '
        '"$PLANNER_ROLLOUT_MODE" "$PLANNER_EXECUTION_ENABLED"'
    ) in text
