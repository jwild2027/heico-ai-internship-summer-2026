import json
from pathlib import Path

from tiff.trace_net_opensearch_adapter_v1 import (
    build_opensearch_documents,
    sanitize_text,
    quality_report,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_builds_safe_embedding_documents(tmp_path: Path) -> None:
    candidates = {
        "records": [
            {
                "embedding_candidate_id": "emb1",
                "page_id": "p001",
                "rag_bucket": "source_text_evidence",
                "authority": "ocr_text_claim_with_citation",
                "text_for_embedding": "Revision history text",
                "citation_ids": ["cite1"],
            },
            {
                "embedding_candidate_id": "bad1",
                "page_id": "p002",
                "rag_bucket": "raw_ocr",
                "text_for_embedding": "raw text",
            },
        ]
    }
    path = tmp_path / "candidates.json"
    write_json(path, candidates)
    report = build_opensearch_documents(
        embedding_candidates_path=path,
        output_dir=tmp_path / "out",
        min_documents=1,
        min_page_scoped_documents=1,
        require_mapping=True,
    )
    docs = report["documents"]
    assert report["quality_status"] == "PASS"
    assert len(docs) == 1
    assert docs[0]["opensearch_document_id"] == "emb1"
    assert docs[0]["answer_support_candidate"] is True
    assert docs[0]["can_answer_directly"] is False
    assert docs[0]["can_prove_claims"] is False


def test_builds_table_cell_documents(tmp_path: Path) -> None:
    candidates = {"records": [{"embedding_candidate_id": "emb1", "page_id": "p001", "rag_bucket": "source_evidence", "text": "page p001"}]}
    tables = {
        "records": [
            {
                "page_id": "p001",
                "table_type": "parts_list_table",
                "citation_ids": ["cite_table"],
                "rows": [{"normalized_row_id": "row1", "row_text": "1 120-46137-001"}],
                "cells": [
                    {"normalized_cell_id": "cell1", "row_id": "row1", "text": "1", "cell_kind": "number"},
                    {"normalized_cell_id": "cell2", "row_id": "row1", "text": "120-46137-001", "cell_kind": "part_number"},
                ],
            }
        ]
    }
    cpath = tmp_path / "candidates.json"
    tpath = tmp_path / "tables.json"
    write_json(cpath, candidates)
    write_json(tpath, tables)
    report = build_opensearch_documents(
        embedding_candidates_path=cpath,
        table_cell_normalizer_path=tpath,
        output_dir=tmp_path / "out",
        min_documents=3,
        min_page_scoped_documents=3,
        require_mapping=True,
    )
    assert report["quality_status"] == "PASS"
    doc_types = {d["document_type"] for d in report["documents"]}
    assert "table_cell_normalized" in doc_types
    assert "table_row_normalized" in doc_types
    assert report["summary"]["unsafe_index_document_count"] == 0


def test_sanitizes_local_paths() -> None:
    text = sanitize_text(r"see C:\Users\me\local_data\file.tif and /mnt/data/x")
    assert "C:\\Users" not in text
    assert "/mnt/data/x" not in text
    assert "[local_path_redacted]" in text


def test_quality_fails_on_unsafe_document(tmp_path: Path) -> None:
    report = {
        "summary": {
            "opensearch_document_count": 1,
            "page_scoped_document_count": 1,
            "missing_page_id_count": 0,
            "missing_source_trace_count": 0,
            "unsafe_index_document_count": 1,
            "raw_feedback_indexed_count": 0,
            "raw_visual_output_indexed_count": 0,
            "raw_ocr_unfiltered_indexed_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "mapping": {"mappings": {}},
    }
    quality = quality_report(report, min_documents=1, min_page_scoped_documents=1, require_mapping=True)
    assert quality["status"] == "FAIL"


def test_builds_community_and_part_docs_with_lineage(tmp_path: Path) -> None:
    candidates = {"records": [{"embedding_candidate_id": "emb1", "page_id": "p001", "rag_bucket": "source_evidence", "text": "source p001"}]}
    communities = {"communities": [{"community_id": "c1", "label": "Part family 120", "page_ids": ["p001", "p002"], "part_numbers": ["120-1"]}]}
    parts = {"part_candidate_nodes": [{"node_id": "part_candidate::120-1", "label": "120-1", "source_page_ids": ["p001"], "properties": {"part_number": "120-1"}}]}
    cpath = tmp_path / "candidates.json"
    cmpath = tmp_path / "communities.json"
    ppath = tmp_path / "parts.json"
    write_json(cpath, candidates)
    write_json(cmpath, communities)
    write_json(ppath, parts)
    report = build_opensearch_documents(
        embedding_candidates_path=cpath,
        leiden_communities_path=cmpath,
        graph_overlay_part_normalizer_path=ppath,
        output_dir=tmp_path / "out",
        min_documents=3,
        min_page_scoped_documents=3,
        require_mapping=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["missing_page_id_count"] == 0
    assert any(d["document_type"] == "community_summary" for d in report["documents"])
    assert any(d["document_type"] == "part_candidate_lineage" for d in report["documents"])


def test_community_documents_derive_page_lineage_from_node_membership(tmp_path: Path) -> None:
    candidates = {"records": [{"embedding_candidate_id": "emb1", "page_id": "p001", "rag_bucket": "source_evidence", "text": "source p001"}]}
    communities = {
        "communities": [
            {"community_id": "c1", "label": "Community with derived lineage", "part_numbers": ["120-1"]},
        ],
        "node_membership": [
            {"community_id": "c1", "node_id": "page::p001", "page_id": "p001"},
            {"community_id": "c1", "node_id": "part::120-1", "source_page_ids": ["p002", "p003"]},
        ],
    }
    cpath = tmp_path / "candidates.json"
    cmpath = tmp_path / "communities.json"
    write_json(cpath, candidates)
    write_json(cmpath, communities)

    report = build_opensearch_documents(
        embedding_candidates_path=cpath,
        leiden_communities_path=cmpath,
        output_dir=tmp_path / "out",
        min_documents=2,
        min_page_scoped_documents=2,
        require_mapping=True,
    )

    assert report["quality_status"] == "PASS"
    community_docs = [d for d in report["documents"] if d["document_type"] == "community_summary"]
    assert len(community_docs) == 1
    assert community_docs[0]["source_page_ids"] == ["p001", "p002", "p003"]
    assert community_docs[0]["source_trace_present"] is True
    assert report["summary"]["missing_page_id_count"] == 0


def test_community_documents_without_page_lineage_are_skipped(tmp_path: Path) -> None:
    candidates = {"records": [{"embedding_candidate_id": "emb1", "page_id": "p001", "rag_bucket": "source_evidence", "text": "source p001"}]}
    communities = {
        "communities": [
            {"community_id": "c_empty", "label": "Community without page lineage", "part_numbers": ["120-1"]},
        ],
        "node_membership": [
            {"community_id": "c_empty", "node_id": "trust_authority::retrieval_only"},
        ],
    }
    cpath = tmp_path / "candidates.json"
    cmpath = tmp_path / "communities.json"
    write_json(cpath, candidates)
    write_json(cmpath, communities)

    report = build_opensearch_documents(
        embedding_candidates_path=cpath,
        leiden_communities_path=cmpath,
        output_dir=tmp_path / "out",
        min_documents=1,
        min_page_scoped_documents=1,
        require_mapping=True,
    )

    assert report["quality_status"] == "PASS"
    assert not any(d["document_type"] == "community_summary" for d in report["documents"])
    assert report["summary"]["missing_page_id_count"] == 0
    assert report["summary"]["missing_source_trace_count"] == 0
