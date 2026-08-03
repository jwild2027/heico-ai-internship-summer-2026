from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path("scripts/maintenance/operations/check_trace_net_h30_phase4_5_1_launcher_env_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("phase451_checker", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_human_facing_8130_message_is_not_operational_use():
    module = load_module()
    text = 'echo "Existing 8130 stack was not changed."\n'
    assert module.protected_port_operational_use(text, 8130) is False


def test_comment_with_protected_port_is_not_operational_use():
    module = load_module()
    assert module.protected_port_operational_use("# preserve port 8017\n", 8017) is False


def test_server_bind_to_protected_port_is_detected():
    module = load_module()
    assert module.protected_port_operational_use("python server.py --port 8130\n", 8130) is True


def test_url_call_to_protected_port_is_detected():
    module = load_module()
    assert module.protected_port_operational_use("curl http://127.0.0.1:8017/health\n", 8017) is True


def test_stop_session_on_protected_port_is_detected():
    module = load_module()
    assert module.protected_port_operational_use("stop_session trace-net-old 8130\n", 8130) is True
