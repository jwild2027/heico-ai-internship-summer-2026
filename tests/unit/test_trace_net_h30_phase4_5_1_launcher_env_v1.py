from __future__ import annotations

import importlib.util
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "trace_net_h30_phase4_5_1_launcher_env_fix_v1_patch"
INSTALLER = PACKAGE / "APPLY_FIX.py"


def load_installer():
    spec = importlib.util.spec_from_file_location("phase451_installer", INSTALLER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fixture_text() -> str:
    return '''#!/usr/bin/env bash
SHADOW_PLANNER_TIMEOUT="${TRACE_NET_H30_SHADOW_PLANNER_TIMEOUT_SECONDS:-300}"
cat > /tmp/start_trace_net_cognitive_8118.sh <<INNER
export TRACE_NET_H30_SHADOW_PLANNER_TIMEOUT_SECONDS="$SHADOW_PLANNER_TIMEOUT"
INNER
curl --fail-with-body --silent --show-error http://127.0.0.1:8118/health | "$PYTHON" -m json.tool
'''


def test_patch_adds_all_phase45_exports_and_health_assertion():
    module = load_installer()
    patched, state = module.patch_text(fixture_text())
    assert state == "patched"
    for name in (
        "TRACE_NET_H30_PLANNER_ROLLOUT_MODE",
        "TRACE_NET_H30_PLANNER_EXECUTION_ENABLED",
        "TRACE_NET_H30_PLANNER_MAX_LATENCY_MS",
        "TRACE_NET_H30_PLANNER_BREAKER_FAILURE_THRESHOLD",
        "TRACE_NET_H30_PLANNER_BREAKER_SECONDS",
        "TRACE_NET_H30_PLANNER_CANONICAL_BRIDGE_ENABLED",
        "TRACE_NET_H30_PLANNER_REQUIRE_ROUTE",
    ):
        assert f"export {name}=" in patched
    assert "planner_launcher_env_check=PASS" in patched
    assert "planner launcher environment mismatch" in patched


def test_patch_is_idempotent():
    module = load_installer()
    once, _ = module.patch_text(fixture_text())
    twice, state = module.patch_text(once)
    assert state == "already_applied"
    assert twice == once


def test_invalid_anchor_count_fails_closed():
    module = load_installer()
    broken = fixture_text().replace(module.ANCHOR_HEALTH, "")
    try:
        module.patch_text(broken)
    except ValueError as exc:
        assert "health_anchor" in str(exc)
    else:
        raise AssertionError("installer accepted missing health anchor")


def test_launcher_mode_allowlist_is_bounded():
    module = load_installer()
    patched, _ = module.patch_text(fixture_text())
    assert "validate_only|narrow|broad|mature" in patched
    assert "invalid_planner_rollout_mode" in patched


def test_live_assertion_checks_mode_phase_and_execution():
    module = load_installer()
    patched, _ = module.patch_text(fixture_text())
    assert "actual_mode != requested_mode" in patched
    assert "actual_execution is not expected_execution" in patched
    assert "actual_phase != expected_phase" in patched
