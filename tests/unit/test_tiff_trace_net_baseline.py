from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_pre_algorithm_baseline import flatten_metrics
from tiff.trace_net_baseline_quality import run_quality


def test_flatten_metrics_nested_counts():
    metrics = {"status": "OK", "source_counts": {"pages": 509}, "rag_counts": {"rag_candidate_bucket_counts": {"source_text_evidence": 495}}}
    flat = flatten_metrics(metrics)
    assert flat["source_counts.pages"] == 509
    assert flat["rag_counts.rag_candidate_bucket_counts.source_text_evidence"] == 495


def test_baseline_quality_passes():
    summary = {
        "pages": 509,
        "ocr_records": 509,
        "ocr_text_records": 495,
        "graph_nodes": 30000,
        "graph_edges": 100000,
        "graph_orphan_edges": 0,
        "rag_candidate_records": 1426,
        "rag_candidate_unsafe_records": 0,
        "rag_candidate_missing_source_url": 0,
        "source_citations": 1426,
        "citations_missing_source_url": 0,
    }
    q = run_quality(summary, {"min_pages": 509, "min_ocr_records": 509, "min_ocr_text_records": 495, "min_graph_nodes": 1, "min_graph_edges": 1, "min_rag_candidates": 1426, "min_citations": 1426})
    assert q["status"] == "OK"


def test_baseline_quality_fails_unsafe():
    summary = {
        "pages": 509,
        "ocr_records": 509,
        "ocr_text_records": 495,
        "graph_nodes": 1,
        "graph_edges": 1,
        "graph_orphan_edges": 0,
        "rag_candidate_records": 1426,
        "rag_candidate_unsafe_records": 1,
        "rag_candidate_missing_source_url": 0,
        "source_citations": 1426,
        "citations_missing_source_url": 0,
    }
    q = run_quality(summary, {"min_pages": 1, "min_ocr_records": 1, "min_rag_candidates": 1, "min_citations": 1, "max_unsafe_rag_candidates": 0})
    assert q["status"] == "FAIL"
