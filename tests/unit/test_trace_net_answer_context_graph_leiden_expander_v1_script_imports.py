import importlib.util
from pathlib import Path


def test_build_and_check_scripts_importable():
    root = Path(__file__).resolve().parents[2]
    for script in [
        root / "scripts" / "build_trace_net_answer_context_graph_leiden_expander_v1.py",
        root / "scripts" / "check_trace_net_answer_context_graph_leiden_expander_v1_quality.py",
    ]:
        spec = importlib.util.spec_from_file_location(script.stem, script)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
