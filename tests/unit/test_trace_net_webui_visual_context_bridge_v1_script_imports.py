import importlib.util
from pathlib import Path


def test_build_and_check_scripts_import():
    for script in [
        "scripts/build/visual/build_trace_net_webui_visual_context_bridge_v1.py",
        "scripts/maintenance/serving/check_trace_net_webui_visual_context_bridge_v1_quality.py",
    ]:
        path = Path(script)
        assert path.exists()
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
