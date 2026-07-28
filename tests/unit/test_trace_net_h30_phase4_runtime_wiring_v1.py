from pathlib import Path


def test_phase4_runtime_wiring_and_single_call_suppression():
    source = Path("scripts/serve_trace_net_full_gemma_cognitive_v1.py").read_text(encoding="utf-8")
    assert "TRACE_NET_H30_PHASE4_CONSTRAINED_WRITER_V1_IMPORT" in source
    assert "install_constrained_gemma_writer(globals())" in source
    assert "legacy_freeform_gemma_suppressed" in source
    assert "and not constrained_writer_enabled" in source
    assert source.index("install_content_reconstruction(globals())") < source.index("install_constrained_gemma_writer(globals())")
    assert source.index("install_constrained_gemma_writer(globals())") < source.index("install_public_answer_contract(globals())")
    assert "except (BrokenPipeError, ConnectionResetError)" in source


def test_phase4_launcher_propagates_runtime_settings():
    source = Path("scripts/launch_trace_net_cognitive_openwebui_v1.sh").read_text(encoding="utf-8")
    for name in (
        "TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED",
        "TRACE_NET_H30_CONSTRAINED_WRITER_ROUTES",
        "TRACE_NET_H30_CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS",
        "TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS",
        "TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS",
        "TRACE_NET_H30_CONSTRAINED_WRITER_MIN_CALL_SECONDS",
        "TRACE_NET_H30_CONSTRAINED_WRITER_MAX_TOKENS",
        "TRACE_NET_H30_GEMMA_WRITER_QUEUE_TIMEOUT_SECONDS",
        "TRACE_NET_H30_PUBLIC_BRIDGE_TIMEOUT_SECONDS",
    ):
        assert name in source
    assert 'export TRACE_NET_H30_CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS="$CONSTRAINED_WRITER_REQUIRE_EXACT_SUPPORT_SECTIONS"' in source
    assert 'trace_net_h30_phase4_latency_guard_v1.py' in source


def test_public_bridge_ignores_disconnected_client_write():
    source = Path("scripts/serve_trace_net_openwebui_cognitive_bridge_v1.py").read_text(encoding="utf-8")
    assert "except (BrokenPipeError, ConnectionResetError)" in source
    assert "self.close_connection = True" in source
