from tiff.trace_net_postgres_quality import run_quality


def test_quality_module_exposes_runner():
    assert callable(run_quality)
