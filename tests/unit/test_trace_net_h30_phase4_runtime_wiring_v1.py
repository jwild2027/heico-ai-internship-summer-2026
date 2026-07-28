from pathlib import Path


def test_phase4_runtime_wiring_and_single_call_suppression():
    source = Path("scripts/serve_trace_net_full_gemma_cognitive_v1.py").read_text(encoding="utf-8")
    assert "TRACE_NET_H30_PHASE4_CONSTRAINED_WRITER_V1_IMPORT" in source
    assert "install_constrained_gemma_writer(globals())" in source
    assert "legacy_freeform_gemma_suppressed" in source
    assert "and not constrained_writer_enabled" in source
    assert source.index("install_content_reconstruction(globals())") < source.index("install_constrained_gemma_writer(globals())")
    assert source.index("install_constrained_gemma_writer(globals())") < source.index("install_public_answer_contract(globals())")


def test_phase4_launcher_propagates_runtime_settings():
    source = Path("scripts/launch_trace_net_cognitive_openwebui_v1.sh").read_text(encoding="utf-8")
    assert "TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED" in source
    assert "TRACE_NET_H30_CONSTRAINED_WRITER_ROUTES" in source
    assert "trace_net_h30_constrained_gemma_writer_v1.py" in source
    assert "check_trace_net_h30_constrained_gemma_writer_v1.py" in source
