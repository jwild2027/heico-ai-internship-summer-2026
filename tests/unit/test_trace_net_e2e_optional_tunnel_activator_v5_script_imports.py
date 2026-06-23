from pathlib import Path


def test_optional_tunnel_activator_scripts_exist():
    assert Path("scripts/build_trace_net_e2e_optional_tunnel_activator_v5.py").exists()
    assert Path("scripts/check_trace_net_e2e_optional_tunnel_activator_v5_quality.py").exists()


def test_optional_tunnel_activator_module_imports():
    import tiff.trace_net_e2e_optional_tunnel_activator_v5 as module

    assert module.SCHEMA_VERSION == "v5"
