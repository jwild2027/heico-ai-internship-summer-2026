#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

TARGET = Path("scripts/operations/launch_trace_net_cognitive_openwebui_v1.sh")
VARIABLES = (
    "TRACE_NET_H30_PLANNER_ROLLOUT_MODE",
    "TRACE_NET_H30_PLANNER_EXECUTION_ENABLED",
    "TRACE_NET_H30_PLANNER_MAX_LATENCY_MS",
    "TRACE_NET_H30_PLANNER_BREAKER_FAILURE_THRESHOLD",
    "TRACE_NET_H30_PLANNER_BREAKER_SECONDS",
    "TRACE_NET_H30_PLANNER_CANONICAL_BRIDGE_ENABLED",
    "TRACE_NET_H30_PLANNER_REQUIRE_ROUTE",
)
CHECKER_FIX_VERSION = "trace_net_h30_phase4_5_1_checker_false_positive_fix_v1"


def protected_port_operational_use(text: str, port: int) -> bool:
    """Return true only when the launcher operationally touches a protected port.

    Human-facing echo/printf text such as ``Existing 8130 stack was not changed``
    is intentionally ignored. Binding, killing, waiting on, or calling the port is
    still detected and fails closed.
    """
    port_text = str(port)
    patterns = (
        rf":{port_text}\b",                       # URL or host:port
        rf"--port(?:=|\s+){port_text}\b",             # server bind flag
        rf"\b{port_text}/tcp\b",                         # fuser/netstat style
        rf"\bstop_session\b[^\n]*\b{port_text}\b",      # launcher stop helper
        rf"\bwait_port\b[^\n]*\b{port_text}\b",        # launcher wait helper
        rf"\bfuser\b[^\n]*\b{port_text}\b",            # direct port kill/check
        rf"\btrace-net-[^\s\"']*{port_text}\b",         # tmux/session name
        rf"\bport_{port_text}\b",                        # generated status name
    )
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"^(?:echo|printf)\b", line):
            continue
        if any(re.search(pattern, line) for pattern in patterns):
            return True
    return False


def build_checks(text: str) -> dict[str, bool]:
    return {
        "marker_present": "TRACE_NET_H30_PHASE4_5_1_LAUNCHER_ENV_V1" in text,
        "all_variables_captured": all(f'${{{name}:-' in text for name in VARIABLES),
        "all_variables_exported": all(f"export {name}=" in text for name in VARIABLES),
        "mode_allowlist": "validate_only|narrow|broad|mature" in text,
        "health_saved": '"$RUNTIME/8118_health.json"' in text,
        "requested_mode_checked": "requested_planner_mode" in text,
        "live_mode_checked": "live_planner_mode" in text,
        "phase_checked": "expected_planner_phase" in text,
        "execution_checked": "expected_planner_execution" in text,
        "fail_closed_mismatch": "planner launcher environment mismatch" in text,
        "success_marker": "planner_launcher_env_check=PASS" in text,
        "protected_8017_absent": not protected_port_operational_use(text, 8017),
        "protected_8130_absent": not protected_port_operational_use(text, 8130),
    }


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    checks = build_checks(text)
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "module": "check_trace_net_h30_phase4_5_1_launcher_env_v1",
        "checker_fix_version": CHECKER_FIX_VERSION,
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "checks": checks,
        "propagated_variable_count": len(VARIABLES),
        "protected_port_check": "operational_use_only",
        "live_mode_assertion": True,
        "source_truth_mutation_allowed": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
