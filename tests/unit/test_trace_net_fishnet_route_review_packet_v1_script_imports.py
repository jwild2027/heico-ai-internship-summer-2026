import importlib.util
from pathlib import Path


def test_build_script_imports():
    path = Path("scripts/build/ocr/build_trace_net_fishnet_route_review_packet_v1.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("build_trace_net_fishnet_route_review_packet_v1", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main_build")


def test_quality_script_imports():
    path = Path("scripts/maintenance/benchmark/check_trace_net_fishnet_route_review_packet_v1_quality.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("check_trace_net_fishnet_route_review_packet_v1_quality", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main_quality")
