from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
V2 = REPO_ROOT / "scripts" / "launch_trace_net_gemma_resident_openwebui_v2.sh"
V2_1 = REPO_ROOT / "scripts" / "launch_trace_net_gemma_resident_openwebui_v2_1.sh"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_old_v2_is_safe_compatibility_shim() -> None:
    text = read(V2)
    assert "launch_trace_net_gemma_resident_openwebui_v2_1.sh" in text
    assert 'exec "$SCRIPT_DIR/launch_trace_net_gemma_resident_openwebui_v2_1.sh"' in text
    assert "fuser" not in text


def test_v2_1_never_uses_broad_port_kill() -> None:
    text = read(V2_1)
    assert "fuser" not in text
    assert "Refusing broad port kill" in text
    assert '"broad_port_kill_used": false' in text


def test_v2_1_uses_bounded_exact_process_shutdown() -> None:
    text = read(V2_1)
    assert "timeout 5s tmux kill-session" in text
    assert "pgrep -f --" in text
    assert "kill -TERM" in text
    assert "kill -KILL" in text
    assert "WRITER_PATTERN='[s]erve_trace_net_full_gemma_cognitive_v1.py" in text
    assert "PROXY_PATTERN_V1_1='[s]erve_trace_net_nha_phase16_gemma_proxy_v1_1.py" in text
    assert "PROXY_PATTERN_V1='[s]erve_trace_net_nha_phase16_gemma_proxy_v1.py" in text


def test_v2_1_stops_proxy_before_writer() -> None:
    text = read(V2_1)
    proxy = text.index("stop_exact_service proxy_8131")
    writer = text.index("stop_exact_service writer_8128")
    assert proxy < writer


def test_v2_1_starts_writer_before_proxy() -> None:
    text = read(V2_1)
    writer = text.index('tmux new-session -d -s "$WRITER_SESSION"')
    proxy = text.index('tmux new-session -d -s "$PROXY_SESSION"')
    assert writer < proxy
    assert text.index('wait_health "$WRITER_SESSION"') < proxy


def test_v2_1_uses_simple_start_scripts_not_tee_pipelines() -> None:
    text = read(V2_1)
    assert "start_writer_8128_v2_1.sh" in text
    assert "start_proxy_8131_v2_1.sh" in text
    assert "2>&1 | tee" not in text
    assert '>>$(q "$RUNTIME/8128.log") 2>&1' in text
    assert '>>$(q "$RUNTIME/8131.log") 2>&1' in text


def test_v2_1_preserves_full_writer_feature_environment() -> None:
    text = read(V2_1)
    required = (
        "TRACE_NET_H30_ENGRAM_SKILL_SHADOW_ENABLED",
        "TRACE_NET_H30_EVIDENCE_AWARE_ANSWER_MODES_ENABLED",
        "TRACE_NET_H30_FINAL_ENGRAM_ROLLOUT_ENABLED",
        "TRACE_NET_H30_EVIDENCE_SYNTHESIS_ENABLED",
        "TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED",
        "TRACE_NET_H30_CONSTRAINED_WRITER_ROUTES",
        "TRACE_NET_H30_CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS",
        "TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS",
        "TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED",
    )
    for variable in required:
        assert f"export {variable}=" in text


def test_v2_1_health_gate_rejects_reduced_writer_configuration() -> None:
    text = read(V2_1)
    required = (
        '"evidence_aware_answer_modes_enabled": True',
        '"final_engram_rollout_enabled": True',
        '"constrained_gemma_writer_enabled": True',
        '"legacy_freeform_writer_suppressed": True',
        '"phase3_deterministic_fallback_preserved": True',
    )
    for assertion in required:
        assert assertion in text


def test_v2_1_preserves_residency_and_progress_gates() -> None:
    text = read(V2_1)
    assert '"gemma_model_resident": True' in text
    assert '"cold_start_risk": False' in text
    assert '"validated_progress_streaming": True' in text
    assert '"raw_unvalidated_tokens_exposed": False' in text
    assert "TRACE_NET_GEMMA_RESIDENCY_LAUNCHER_V2_1=PASS" in text


def test_v2_1_does_not_restart_cognitive_router() -> None:
    text = read(V2_1)
    assert "--port 8118" not in text
    assert '"cognitive_router_restarted": false' in text
    assert re.search(r'curl .*?"\$COGNITIVE_URL/health"', text, flags=re.S)
