import json
from pathlib import Path

from tiff.trace_net_source_citations import SourceCitationOptions, SourceCitationPaths, build_trace_net_source_citations
from tiff.trace_net_source_citations_quality import SourceCitationQualityOptions, SourceCitationQualityPaths, check_trace_net_source_citation_quality


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _good_candidate():
    return {
        "chunk_id": "chunk:source:p1",
        "candidate_id": "chunk:source:p1",
        "page_id": "t_p_120_1176_p000001",
        "document_id": "t_p_120_1176",
        "ata_code": "25-21-00",
        "rag_bucket": "source_evidence",
        "candidate_type": "source_evidence",
        "evidence_layer": "source_trace",
        "final_trust_tier": "A",
        "final_rag_action": "include_as_source_evidence",
        "usable_confidence": 0.91,
        "source_url": "http://localhost/page/1",
        "tiff_path": "local/page1.tif",
        "ocr_path": "local/page1.txt",
        "text": "Source evidence for page 1.",
    }


def test_quality_passes_for_citation_artifacts(tmp_path):
    candidates = tmp_path / "rag_candidate_chunks.jsonl"
    out = tmp_path / "citations"
    _write_jsonl(candidates, [_good_candidate()])
    build_trace_net_source_citations(SourceCitationPaths(candidate_path=candidates, output_dir=out), SourceCitationOptions(include_search_results=False))
    report = check_trace_net_source_citation_quality(
        SourceCitationQualityPaths(output_dir=out),
        SourceCitationQualityOptions(min_citations=1, min_pages=1, min_source_traceable=1, max_missing_source_url=0),
    )
    assert report["status"] == "OK"
    assert report["citation_records"] == 1


def test_quality_fails_when_required_source_url_missing(tmp_path):
    candidates = tmp_path / "rag_candidate_chunks.jsonl"
    out = tmp_path / "citations"
    row = _good_candidate()
    row["source_url"] = ""
    _write_jsonl(candidates, [row])
    build_trace_net_source_citations(SourceCitationPaths(candidate_path=candidates, output_dir=out), SourceCitationOptions(include_search_results=False))
    report = check_trace_net_source_citation_quality(
        SourceCitationQualityPaths(output_dir=out),
        SourceCitationQualityOptions(min_citations=1, min_pages=1, min_source_traceable=0, max_missing_source_url=0),
    )
    assert report["status"] == "FAIL"
    assert any(check["name"] == "missing_source_url" and not check["ok"] for check in report["checks"])
