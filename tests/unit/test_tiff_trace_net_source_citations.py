import json
from pathlib import Path

from tiff.trace_net_source_citations import SourceCitationOptions, SourceCitationPaths, build_trace_net_source_citations


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_builds_citations_for_safe_candidates(tmp_path):
    candidates = tmp_path / "rag_candidate_chunks.jsonl"
    search = tmp_path / "trace_net_search_results.jsonl"
    out = tmp_path / "citations"
    rows = [
        {
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
        },
        {
            "chunk_id": "chunk:part:p1",
            "candidate_id": "chunk:part:p1",
            "page_id": "t_p_120_1176_p000001",
            "document_id": "t_p_120_1176",
            "ata_code": "25-21-00",
            "rag_bucket": "verified_part_evidence",
            "candidate_type": "verified_part_evidence",
            "evidence_layer": "part_catalog",
            "final_trust_tier": "A",
            "final_rag_action": "include_as_verified_part_evidence",
            "usable_confidence": 0.88,
            "source_url": "http://localhost/page/1",
            "tiff_path": "local/page1.tif",
            "ocr_path": "local/page1.txt",
            "text": "Verified part 120-12345-001.",
        },
    ]
    _write_jsonl(candidates, rows)
    _write_jsonl(search, [{"rank": 1, "chunk_id": "chunk:part:p1", "candidate_id": "chunk:part:p1", "page_id": "t_p_120_1176_p000001", "score": 10.0}])
    summary = build_trace_net_source_citations(
        SourceCitationPaths(candidate_path=candidates, search_results_path=search, output_dir=out),
        SourceCitationOptions(),
    )
    assert summary["status"] == "OK"
    assert summary["citation_records"] == 2
    assert summary["search_results_with_citations"] == 1
    citations = [json.loads(line) for line in (out / "trace_net_source_citations.jsonl").read_text().splitlines()]
    assert all(c["citation_text"] for c in citations)
    assert all(c["source_url"] for c in citations)
    annotated = [json.loads(line) for line in (out / "trace_net_search_results_with_citations.jsonl").read_text().splitlines()]
    assert annotated[0]["citation"]["citation_id"].startswith("cite:")


def test_unsafe_candidate_is_flagged(tmp_path):
    candidates = tmp_path / "rag_candidate_chunks.jsonl"
    out = tmp_path / "citations"
    _write_jsonl(candidates, [{
        "chunk_id": "bad",
        "page_id": "p1",
        "rag_bucket": "table_candidate",
        "evidence_layer": "table_candidate",
        "final_trust_tier": "C",
        "final_rag_action": "exclude_from_rag",
        "text": "bad",
    }])
    summary = build_trace_net_source_citations(SourceCitationPaths(candidate_path=candidates, output_dir=out), SourceCitationOptions(include_search_results=False))
    assert summary["status"] == "WARN"
    assert summary["unsafe_citation_records"] == 1
