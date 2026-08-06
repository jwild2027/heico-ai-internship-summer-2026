import json
from pathlib import Path

from tiff.trace_net_source_citation_quality import (
    SourceCitationQualityOptions,
    SourceCitationQualityPaths,
    evaluate_source_citation_quality,
)


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_source_citation_quality_passes(tmp_path):
    out = tmp_path / "citations"
    summary = {
        "status": "OK",
        "records": 3,
        "rag_bucket_counts": {
            "source_evidence": 1,
            "source_text_evidence": 1,
            "verified_part_evidence": 1,
        },
        "citation_kind_counts": {"source": 1, "source_text": 1, "verified_part": 1},
    }
    out.mkdir(parents=True)
    (out / "trace_net_source_citation_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    rows = []
    for idx, bucket in enumerate(["source_evidence", "source_text_evidence", "verified_part_evidence"], start=1):
        rows.append({
            "citation_id": f"citation:{idx}",
            "page_id": f"p{idx}",
            "rag_bucket": bucket,
            "source_url": "http://localhost/source",
            "tiff_path": "page.tif",
            "ocr_path": "page.txt",
            "safe_for_rag": True,
            "missing_source_url": False,
            "missing_tiff_path": False,
            "missing_ocr_path": False,
        })
    _write_jsonl(out / "trace_net_source_citations.jsonl", rows)

    report = evaluate_source_citation_quality(
        SourceCitationQualityPaths(output_dir=out),
        SourceCitationQualityOptions(
            min_records=3,
            min_pages=3,
            min_source_citations=1,
            min_source_text_citations=1,
            min_verified_part_citations=1,
            max_missing_source_urls=0,
            max_missing_tiff_paths=0,
            max_missing_ocr_paths=0,
            max_unsafe_citations=0,
        ),
    )
    assert report["status"] == "OK"
    assert report["source_citation_records"] == 3


def test_source_citation_quality_fails_missing_source(tmp_path):
    out = tmp_path / "citations"
    out.mkdir(parents=True)
    (out / "trace_net_source_citation_summary.json").write_text(json.dumps({"status": "OK", "records": 1, "rag_bucket_counts": {"source_evidence": 1}}), encoding="utf-8")
    _write_jsonl(out / "trace_net_source_citations.jsonl", [{
        "citation_id": "citation:1",
        "page_id": "p1",
        "rag_bucket": "source_evidence",
        "safe_for_rag": True,
        "missing_source_url": True,
        "missing_tiff_path": False,
        "missing_ocr_path": False,
    }])
    report = evaluate_source_citation_quality(
        SourceCitationQualityPaths(output_dir=out),
        SourceCitationQualityOptions(max_missing_source_urls=0),
    )
    assert report["status"] == "FAIL"
    assert any(not check["ok"] and check["name"] == "missing_source_urls" for check in report["checks"])
