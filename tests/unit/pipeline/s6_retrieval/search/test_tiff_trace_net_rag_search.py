from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_rag_search import RagSearchOptions, RagSearchPaths, search_rag_candidates


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _candidate(chunk_id: str, page_id: str, bucket: str, layer: str, text: str, tier: str = "A", action: str | None = None, conf: float = 0.9) -> dict:
    action = action or {
        "source_evidence": "include_as_source_evidence",
        "source_text_evidence": "include_as_source_evidence",
        "verified_part_evidence": "include_as_verified_part_evidence",
        "derived_context": "include_as_derived_context",
    }[bucket]
    return {
        "chunk_id": chunk_id,
        "candidate_id": chunk_id,
        "page_id": page_id,
        "document_id": "doc1",
        "ata_code": "25-21-00",
        "evidence_layer": layer,
        "rag_bucket": bucket,
        "candidate_type": bucket,
        "text": text,
        "source_url": f"http://example/{page_id}",
        "tiff_path": f"pages/{page_id}.tif",
        "ocr_path": f"ocr/{page_id}.txt",
        "final_trust_tier": tier,
        "final_rag_action": action,
        "usable_confidence": conf,
        "metadata": {"catalog_supported_part_numbers": ["120-50645-009"] if "120-50645-009" in text else []},
    }


def test_part_number_search_prioritizes_verified_part_candidate(tmp_path: Path) -> None:
    candidates = tmp_path / "rag_candidate_chunks.jsonl"
    _write_jsonl(
        candidates,
        [
            _candidate("c1", "page1", "source_evidence", "source_trace", "Source evidence for page one."),
            _candidate("c2", "page2", "verified_part_evidence", "part_catalog", "Verified part 120-50645-009 for passenger seat."),
            _candidate("c3", "page3", "derived_context", "table_tile_text_refined", "Derived table context mentions 120-50645-009." , tier="B", conf=0.75),
        ],
    )
    paths = RagSearchPaths(candidate_dir=tmp_path, output_dir=tmp_path / "out")
    summary = search_rag_candidates(paths, RagSearchOptions(part_number="120-50645-009", top_k=3))
    assert summary["result_records"] == 2
    payload = json.loads(paths.results.read_text(encoding="utf-8"))
    assert payload["results"][0]["rag_bucket"] == "verified_part_evidence"
    assert payload["results"][0]["score_components"]["matched_part_numbers"]
    assert summary["unsafe_result_records"] == 0


def test_page_lookup_finds_source_candidate(tmp_path: Path) -> None:
    candidates = tmp_path / "rag_candidate_chunks.jsonl"
    _write_jsonl(
        candidates,
        [
            _candidate("c1", "t_p_120_1176_p000010", "source_evidence", "source_trace", "Source evidence for p10."),
            _candidate("c2", "t_p_120_1176_p000011", "verified_part_evidence", "part_catalog", "Part 120-11111-001."),
        ],
    )
    paths = RagSearchPaths(candidate_dir=tmp_path, output_dir=tmp_path / "out")
    summary = search_rag_candidates(paths, RagSearchOptions(page_id="t_p_120_1176_p000010", top_k=5))
    payload = json.loads(paths.results.read_text(encoding="utf-8"))
    assert summary["result_records"] == 1
    assert payload["results"][0]["page_id"] == "t_p_120_1176_p000010"
    assert payload["results"][0]["rag_bucket"] == "source_evidence"


def test_bucket_filter_limits_search_scope(tmp_path: Path) -> None:
    candidates = tmp_path / "rag_candidate_chunks.jsonl"
    _write_jsonl(
        candidates,
        [
            _candidate("c1", "page1", "source_evidence", "source_trace", "seat bottom source page"),
            _candidate("c2", "page2", "derived_context", "table_tile_text_refined", "seat bottom derived table context", tier="B", conf=0.7),
        ],
    )
    paths = RagSearchPaths(candidate_dir=tmp_path, output_dir=tmp_path / "out")
    summary = search_rag_candidates(paths, RagSearchOptions(query="seat bottom", bucket="derived_context", top_k=5))
    assert summary["result_records"] == 1
    assert summary["bucket_counts"] == {"derived_context": 1}



def test_keyword_search_can_return_source_text_candidate(tmp_path: Path) -> None:
    candidates = tmp_path / "rag_candidate_chunks.jsonl"
    _write_jsonl(
        candidates,
        [
            _candidate("c1", "page1", "source_text_evidence", "source_text", "OCR text says seat bottom and backrest installation."),
            _candidate("c2", "page2", "source_evidence", "source_trace", "Source evidence metadata only."),
        ],
    )
    paths = RagSearchPaths(candidate_dir=tmp_path, output_dir=tmp_path / "out")
    summary = search_rag_candidates(paths, RagSearchOptions(query="seat bottom backrest", top_k=5))
    payload = json.loads(paths.results.read_text(encoding="utf-8"))
    assert summary["result_records"] == 1
    assert payload["results"][0]["rag_bucket"] == "source_text_evidence"
    assert summary["unsafe_result_records"] == 0
