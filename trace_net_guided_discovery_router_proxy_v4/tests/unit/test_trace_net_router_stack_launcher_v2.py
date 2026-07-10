import importlib.util
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "launch_trace_net_router_stack_v2.py"
spec = importlib.util.spec_from_file_location("launcher_v2", SCRIPT)
launcher = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)


def test_launcher_v2_uses_router_proxy_v4_script():
    assert str(launcher.ROUTER_SCRIPT) == "scripts/serve_trace_net_guided_discovery_router_proxy_v4.py"


def test_launcher_v2_manifest_reports_router_model_v4(tmp_path):
    class Args:
        output_root = str(tmp_path)
        host = "127.0.0.1"
        router_port = 8017
    spec = launcher.ServiceSpec("router", ["python", "x"], "http://127.0.0.1:8017/health", tmp_path / "router.log")
    path = launcher._write_manifest(Args(), [spec], [], launcher.STATUS_READY)
    text = path.read_text()
    assert "trace-net-router-proxy-v4" in text
    assert "TRACE_NET_ROUTER_STACK_LAUNCHER_V2_READY" in text
