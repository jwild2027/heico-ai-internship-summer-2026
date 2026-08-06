from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_rag_search_quality import RagSearchQualityOptions, RagSearchQualityPaths, evaluate_search_quality


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def test_search_quality_passes_safe_results(tmp_path: Path) -> None:
    out = tmp_path / "search"
    summary = {
        "status": "OK",
        "searched_records": 3,
        "result_records": 2,
        "unsafe_result_records": 0,
        "excluded_result_records": 0,
        "bucket_counts": {"source_evidence": 1, "verified_part_evidence": 1},
    }
    results = [
        {"rank": 1, "safe_candidate": True, "final_rag_action": "include_as_source_evidence", "rag_bucket": "source_evidence"},
        {"rank": 2, "safe_candidate": True, "final_rag_action": "include_as_verified_part_evidence", "rag_bucket": "verified_part_evidence"},
    ]
    _write_json(out / "trace_net_search_summary.json", summary)
    _write_json(out / "trace_net_search_results.json", {"summary": summary, "results": results})
    _write_jsonl(out / "trace_net_search_results.jsonl", results)
    report = evaluate_search_quality(RagSearchQualityPaths(output_dir=out), RagSearchQualityOptions(min_results=2, min_source_results=1, min_verified_part_results=1))
    assert report["status"] == "OK"


def test_search_quality_fails_unsafe_result(tmp_path: Path) -> None:
    out = tmp_path / "search"
    summary = {
        "status": "OK",
        "searched_records": 1,
        "result_records": 1,
        "unsafe_result_records": 1,
        "excluded_result_records": 0,
        "bucket_counts": {"source_evidence": 1},
    }
    results = [{"rank": 1, "safe_candidate": False, "final_rag_action": "include_as_source_evidence", "rag_bucket": "source_evidence"}]
    _write_json(out / "trace_net_search_summary.json", summary)
    _write_json(out / "trace_net_search_results.json", {"summary": summary, "results": results})
    report = evaluate_search_quality(RagSearchQualityPaths(output_dir=out), RagSearchQualityOptions(max_unsafe_results=0))
    assert report["status"] == "FAIL"
