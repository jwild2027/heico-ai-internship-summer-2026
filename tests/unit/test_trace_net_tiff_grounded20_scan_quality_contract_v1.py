from pathlib import Path


def test_q17_benchmark_does_not_assume_blur():
    source = Path("scripts/benchmark/ingestion/run_trace_net_tiff_grounded20_v1.py").read_text(encoding="utf-8")
    assert "the blurry scanned page" not in source.lower()
    assert "locate the scanned page containing this ocr clue" in source.lower()
    assert "reconstruct the surrounding text and table relationships" in source.lower()
