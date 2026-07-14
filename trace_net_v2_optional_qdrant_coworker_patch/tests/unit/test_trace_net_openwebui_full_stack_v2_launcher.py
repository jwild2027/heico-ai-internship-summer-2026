from __future__ import annotations
import importlib.util, sys
from pathlib import Path

SCRIPT = Path("scripts/launch_trace_net_openwebui_full_stack_v2.py")

def load():
    spec = importlib.util.spec_from_file_location("launcher_v2", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["launcher_v2"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

def test_launcher_uses_live_v27_and_real_guided_endpoint():
    mod = load()
    args = mod.build_parser().parse_args([])
    commands = mod.build_commands(args)
    normal = " ".join(commands["normal_8014"])
    guided = " ".join(commands["guided_8016"])
    unified = " ".join(commands["unified_8017"])
    assert "serve_trace_net_live_rag_normal_v2.py" in normal
    assert "trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.json" in normal
    assert "serve_trace_net_guided_candidate_discovery_endpoint_v1.py" in guided
    assert "serve_trace_net_guided_discovery_router_proxy_v6.py" not in guided
    assert "serve_trace_net_openwebui_unified_rag_v2.py" in unified

def test_expected_service_identities():
    mod = load()
    assert mod.expected_identity(8014) == "trace_net_live_rag_normal_v2"
    assert mod.expected_identity(8016) == "trace_net_guided_candidate_discovery_endpoint_v1"
    assert mod.expected_identity(8017) == "trace_net_openwebui_unified_rag_v2"

def test_front_door_defaults_local_only():
    mod = load()
    args = mod.build_parser().parse_args([])
    commands = mod.build_commands(args)
    unified = commands["unified_8017"]
    assert unified[unified.index("--host") + 1] == "127.0.0.1"

def test_front_door_can_bind_to_network_without_exposing_internal_services():
    mod = load()
    args = mod.build_parser().parse_args(["--front-door-host", "0.0.0.0"])
    commands = mod.build_commands(args)
    normal = commands["normal_8014"]
    guided = commands["guided_8016"]
    unified = commands["unified_8017"]
    assert normal[normal.index("--host") + 1] == "127.0.0.1"
    assert guided[guided.index("--host") + 1] == "127.0.0.1"
    assert unified[unified.index("--host") + 1] == "0.0.0.0"

def test_qdrant_is_optional_by_default_for_coworker_mode():
    mod = load()
    args = mod.build_parser().parse_args([])
    commands = mod.build_commands(args)
    assert "--require-qdrant" not in commands["unified_8017"]

def test_qdrant_can_still_be_required_explicitly():
    mod = load()
    args = mod.build_parser().parse_args(["--require-qdrant"])
    commands = mod.build_commands(args)
    assert "--require-qdrant" in commands["unified_8017"]
