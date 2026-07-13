import argparse
import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/launch_trace_net_router_stack_v4.py")
spec = importlib.util.spec_from_file_location("launcher_v4", MODULE_PATH)
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)


def test_launcher_v4_uses_router_proxy_v6_script():
    assert launcher.ROUTER_SCRIPT.as_posix() == "scripts/serve_trace_net_guided_discovery_router_proxy_v6.py"


def test_launcher_v4_manifest_model(tmp_path):
    args = argparse.Namespace(
        host="127.0.0.1",
        normal_port=8014,
        guided_port=8016,
        router_port=8017,
        output_root=str(tmp_path),
    )
    path = launcher._write_manifest(args, [], [], launcher.STATUS_READY)
    data = path.read_text(encoding="utf-8")
    assert "TRACE_NET_ROUTER_STACK_LAUNCHER_V4_READY" in data
    assert "trace-net-router-proxy-v6" in data


def test_build_arg_parser_defaults_v4():
    args = launcher.build_arg_parser().parse_args([])
    assert args.router_port == 8017
    assert args.top_k == 8
    assert args.loose_top_k == 8
