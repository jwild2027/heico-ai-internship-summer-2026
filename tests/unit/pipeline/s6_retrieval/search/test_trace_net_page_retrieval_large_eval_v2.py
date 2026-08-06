from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tiff.trace_net_page_retrieval_large_eval_v2 import (
    build_large_eval_v2,
    embed_texts_with_query_cache,
    load_metadata_zip_pages,
    load_query_embedding_cache,
)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_fixture(tmp_path: Path):
    metadata_zip = tmp_path / "metadata.zip"
    with zipfile.ZipFile(metadata_zip, "w") as zf:
        zf.writestr("metadata.xml", "<metadata/>")
        zf.writestr("00000001.tif", b"x" * 10000)
        zf.writestr("00000002.tif", b"x" * 3000)
        zf.writestr("00000003.tif", b"x" * 12000)

    profiles = {
        "quality_status": "PASS",
        "page_profiles": [
            {
                "page_id": "t_p_120_1176_p000001",
                "role": "front_matter",
                "subrole": "revision_history",
                "context_v2": {"retrieval_summary": "Revision history and title block", "retrieval_cues": ["revision", "history"]},
                "source_trace": {"page_id": "t_p_120_1176_p000001"},
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "role": "blank",
                "subrole": "empty_or_blank_page",
                "context_v2": {"retrieval_summary": "Blank page", "retrieval_cues": ["blank"]},
                "source_trace": {"page_id": "t_p_120_1176_p000002"},
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "role": "parts_list",
                "subrole": "table_parts",
                "part_numbers": ["120-46137-001"],
                "context_v2": {"retrieval_summary": "Parts list with table cell", "retrieval_cues": ["120-46137-001", "parts list"]},
                "source_trace": {"page_id": "t_p_120_1176_p000003"},
            },
        ],
    }
    profiles_path = tmp_path / "profiles.json"
    _write_json(profiles_path, profiles)

    nodes = []
    edges = []
    for n in range(1, 4):
        page_id = f"t_p_120_1176_p{n:06d}"
        nodes.append({"node_id": f"page:{page_id}", "node_type": "page", "label": f"page {n}"})
        nodes.append({"node_id": f"source_link:{page_id}", "node_type": "source_link", "label": f"source for {page_id}", "source_uri": f"http://local/{n}"})
        nodes.append({"node_id": f"page_context_v2:{page_id}", "node_type": "page_context_v2", "label": f"Context v2 {page_id}"})
        edges.append({"source_id": f"page:{page_id}", "edge_type": "HAS_SOURCE_LINK", "target_id": f"source_link:{page_id}"})
        edges.append({"source_id": f"page:{page_id}", "edge_type": "HAS_CONTEXT_V2", "target_id": f"page_context_v2:{page_id}"})
    graph_nodes = tmp_path / "graph_nodes.json"
    graph_edges = tmp_path / "graph_edges.json"
    _write_json(graph_nodes, nodes)
    _write_json(graph_edges, edges)

    dublin = {
        "quality_status": "PASS",
        "page_records": [
            {
                "page_id": f"t_p_120_1176_p{n:06d}",
                "dc_title": f"TRACE-Net page {n}",
                "dc_type": ["technical_manual_page"],
                "source_package": {"trace_net:source_package_entry_name": f"{n:06d}.tif", "trace_net:source_package_entry_checksum_match": True},
            }
            for n in range(1, 4)
        ],
    }
    dublin_path = tmp_path / "dublin.json"
    _write_json(dublin_path, dublin)
    return metadata_zip, profiles_path, graph_nodes, graph_edges, dublin_path


def test_load_metadata_zip_pages_detects_tiffs(tmp_path: Path):
    metadata_zip, *_ = _make_fixture(tmp_path)
    pages = load_metadata_zip_pages(metadata_zip, 3)
    assert len(pages) == 3
    assert pages["t_p_120_1176_p000002"]["blank_by_zip_size"] is True


def test_build_large_eval_v2_creates_graph_path_cards(tmp_path: Path):
    metadata_zip, profiles_path, graph_nodes, graph_edges, dublin_path = _make_fixture(tmp_path)
    outdir = tmp_path / "out"
    payload = build_large_eval_v2(
        metadata_zip=metadata_zip,
        profiles_path=profiles_path,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        dublin_core_source_package_extension=dublin_path,
        output_dir=outdir,
        first_pages=3,
        thresholds={
            "min_query_records": 3,
            "min_blank_queries": 1,
            "min_context_v2_queries": 3,
            "min_graph_path_resolved": 3,
            "min_llm_graph_path_cards": 3,
            "max_answer_capable_payloads": 0,
            "max_claim_proof_payloads": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_graph_paths": True,
            "require_no_answer_permission": True,
        },
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["query_record_count"] == 3
    assert payload["summary"]["blank_expected_count"] == 1
    assert payload["summary"]["graph_path_resolved_count"] == 3
    assert payload["summary"]["llm_graph_path_card_count"] == 3
    blank = next(r for r in payload["query_records"] if r["blank_expected"])
    assert "blank" in blank["expected_answer_behavior"].lower()
    assert "Required graph path" in blank["llm_graph_path_prompt"]


def test_build_large_eval_v2_fails_when_graph_path_required_but_missing(tmp_path: Path):
    metadata_zip, profiles_path, *_ = _make_fixture(tmp_path)
    outdir = tmp_path / "out_missing"
    payload = build_large_eval_v2(
        metadata_zip=metadata_zip,
        profiles_path=profiles_path,
        output_dir=outdir,
        first_pages=3,
        thresholds={
            "min_query_records": 3,
            "min_graph_path_resolved": 3,
            "max_answer_capable_payloads": 0,
            "max_claim_proof_payloads": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_graph_paths": True,
        },
    )
    assert payload["quality_status"] == "FAIL"
    assert payload["summary"]["graph_path_resolved_count"] == 0



def test_query_embedding_cache_reuses_previous_vectors(tmp_path: Path):
    cache_path = tmp_path / "query_embedding_cache.jsonl"
    calls = []

    def fake_embedder(texts, *, ollama_url, model):
        calls.append(list(texts))
        vectors = []
        for text in texts:
            base = float(len(text))
            vectors.append([base, base + 1.0, base + 2.0])
        return vectors

    stats1 = {}
    first = embed_texts_with_query_cache(
        ["page 1 revision history", "page 2 blank"],
        ollama_url="http://ollama.local",
        model="bge-m3:latest",
        cache_path=cache_path,
        stats=stats1,
        embedder=fake_embedder,
    )

    assert len(first) == 2
    assert calls == [["page 1 revision history", "page 2 blank"]]
    assert stats1["hit_count"] == 0
    assert stats1["miss_count"] == 2
    assert stats1["write_count"] == 2
    assert stats1["ollama_request_count"] == 1
    assert len(load_query_embedding_cache(cache_path)) == 2

    stats2 = {}
    cache_records = load_query_embedding_cache(cache_path)
    second = embed_texts_with_query_cache(
        ["page 1 revision history", "page 3 parts list"],
        ollama_url="http://ollama.local",
        model="bge-m3:latest",
        cache_path=cache_path,
        cache_records=cache_records,
        stats=stats2,
        embedder=fake_embedder,
    )

    assert second[0] == first[0]
    assert calls[-1] == ["page 3 parts list"]
    assert stats2["hit_count"] == 1
    assert stats2["miss_count"] == 1
    assert stats2["write_count"] == 1
    assert stats2["ollama_request_count"] == 1
    assert len(load_query_embedding_cache(cache_path)) == 3
