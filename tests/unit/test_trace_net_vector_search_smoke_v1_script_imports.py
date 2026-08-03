from pathlib import Path


def test_vector_smoke_run_wrapper_adds_repo_root_and_imports_existing_main() -> None:
    text = Path("scripts/benchmark/run_trace_net_vector_search_smoke_v1.py").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parents[1]" in text
    assert "sys.path.insert(0, str(REPO_ROOT))" in text
    assert "from tiff.trace_net_vector_search_smoke_v1 import main" in text
    assert "run_main" not in text


def test_vector_smoke_quality_wrapper_adds_repo_root_and_imports_existing_quality_main() -> None:
    text = Path("scripts/benchmark/check_trace_net_vector_search_smoke_v1_quality.py").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parents[1]" in text
    assert "sys.path.insert(0, str(REPO_ROOT))" in text
    assert "from tiff.trace_net_vector_search_smoke_v1 import quality_main" in text
    assert "check_main" not in text
