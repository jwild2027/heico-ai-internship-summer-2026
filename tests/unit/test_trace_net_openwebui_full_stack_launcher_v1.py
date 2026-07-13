from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/launch_trace_net_openwebui_full_stack_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("openwebui_launcher_v1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["openwebui_launcher_v1"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_connection_info_points_openwebui_to_router(tmp_path) -> None:
    mod = load_module()
    parser = mod.build_arg_parser()
    args = parser.parse_args([
        "--host", "127.0.0.1",
        "--router-port", "8017",
        "--runtime-dir", str(tmp_path),
    ])

    info = mod.create_connection_info(args, tmp_path)

    assert info["openwebui"]["connect_to_one_front_door_only"] is True
    assert info["openwebui"]["base_url_same_host"] == "http://127.0.0.1:8017/v1"
    assert info["openwebui"]["model"] == "trace-net-router-proxy-v6-gemma-visual-v1"
    assert info["internal_routes"]["router_front_door"] == "http://127.0.0.1:8017"


def test_build_commands_use_new_gemma_visual_router() -> None:
    mod = load_module()
    parser = mod.build_arg_parser()
    args = parser.parse_args([
        "--gemma-visual-retrieval-documents-jsonl", "docs.jsonl",
    ])

    commands = mod.build_commands(args)
    router_cmd = " ".join(commands["router"])

    assert "serve_trace_net_router_proxy_v6_gemma_visual_v1.py" in router_cmd
    assert "--gemma-visual-retrieval-documents-jsonl docs.jsonl" in router_cmd
    assert "--model trace-net-router-proxy-v6-gemma-visual-v1" in router_cmd
