from __future__ import annotations

import importlib.util
from pathlib import Path


def test_runner_script_imports():
    path = Path("scripts/run_trace_net_ocr_classifier_pipeline_v1.py")
    spec = importlib.util.spec_from_file_location("run_trace_net_ocr_classifier_pipeline_v1", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_quality_script_imports():
    path = Path("scripts/check_trace_net_ocr_classifier_pipeline_v1_quality.py")
    spec = importlib.util.spec_from_file_location("check_trace_net_ocr_classifier_pipeline_v1_quality", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
