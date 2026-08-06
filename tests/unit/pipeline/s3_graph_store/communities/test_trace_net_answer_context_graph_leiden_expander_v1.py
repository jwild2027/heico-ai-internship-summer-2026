import json
from pathlib import Path

from tiff.trace_net_answer_context_graph_leiden_expander_v1 import build_answer_context_graph_leiden_expander


def _write(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_graph_leiden_expander_adds_community_roles(tmp_path):
    enricher = tmp_path / "enricher.json"
    leiden = tmp_path / "leiden.json"
    _write(enricher, {
        "quality_status": "PASS",
        "summary": {"question": "Find part number 120-29073-001", "query_part_numbers": ["120-29073-001"]},
        "records": [
            {
                "citation_label": "E1",
                "page_id": "t_p_120_1176_p000005",
                "page_number": 5,
                "route": "table",
                "enriched_context_role": "direct_exact_match_candidate",
                "direct_text_match": False,
                "retrieval_score": 100,
                "enriched_excerpt": "table contents",
                "source_member": "00000005.tif",
                "source_image_sha256": "abc",
            },
            {
                "citation_label": "E2",
                "page_id": "t_p_120_1176_p000045",
                "page_number": 45,
                "route": "table",
                "enriched_context_role": "nearby_or_similar_table_evidence",
                "direct_text_match": False,
                "retrieval_score": 90,
                "enriched_excerpt": "nearby table contents",
                "source_member": "00000045.tif",
                "source_image_sha256": "def",
            },
        ],
    })
    _write(leiden, {
        "quality_status": "PASS",
        "records": [
            {"page_id": "t_p_120_1176_p000005", "leiden_community_id": "c1"},
            {"page_id": "t_p_120_1176_p000045", "leiden_community_id": "c1"},
        ],
    })

    payload = build_answer_context_graph_leiden_expander(
        evidence_enricher=enricher,
        leiden_communities=leiden,
        output_dir=tmp_path / "out",
        require_source_quality_pass=True,
        require_graph_context=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["community_annotation_count"] == 2
    assert summary["same_anchor_leiden_community_count"] == 2
    assert summary["graph_relation_annotation_count"] >= 2
    roles = {r["citation_label"]: r["graph_context_role"] for r in payload["records"]}
    assert roles["E1"] == "direct_exact_match_candidate"
    assert roles["E2"] == "same_leiden_community_neighbor"
    assert "GRAPH / LEIDEN EXPANSION" in payload["llm_context_prompt"]


def test_graph_leiden_expander_preserves_safety_counts(tmp_path):
    enricher = tmp_path / "enricher.json"
    _write(enricher, {
        "quality_status": "PASS",
        "summary": {"question": "Q", "query_part_numbers": []},
        "records": [
            {
                "citation_label": "E1",
                "page_id": "t_p_120_1176_p000005",
                "page_number": 5,
                "route": "table",
                "enriched_context_role": "direct_exact_match_candidate",
                "retrieval_score": 1,
                "enriched_excerpt": "x",
                "source_member": "00000005.tif",
                "source_image_sha256": "abc",
            }
        ],
    })
    payload = build_answer_context_graph_leiden_expander(evidence_enricher=enricher, output_dir=tmp_path / "out", quality=True)
    summary = payload["summary"]
    assert summary["answer_permission_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0
    assert summary["write_attempt_count"] == 0
    assert payload["records"][0]["answer_permission"] is False


def test_graph_leiden_expander_joins_node_container_by_page_number_and_source_member(tmp_path):
    enricher = tmp_path / "enricher.json"
    leiden = tmp_path / "leiden.json"
    _write(enricher, {
        "quality_status": "PASS",
        "summary": {"question": "Find part number 120-29073-001", "query_part_numbers": ["120-29073-001"]},
        "records": [
            {
                "citation_label": "E1",
                "page_id": "t_p_120_1176_p000005",
                "page_number": 5,
                "route": "table",
                "enriched_context_role": "direct_exact_match_candidate",
                "direct_text_match": False,
                "retrieval_score": 100,
                "enriched_excerpt": "candidate table contents",
                "source_member": "00000005.tif",
                "source_image_sha256": "abc",
            },
            {
                "citation_label": "E2",
                "page_id": "t_p_120_1176_p000045",
                "page_number": 45,
                "route": "table",
                "enriched_context_role": "nearby_or_similar_table_evidence",
                "direct_text_match": False,
                "retrieval_score": 90,
                "enriched_excerpt": "nearby table contents",
                "source_member": "00000045.tif",
                "source_image_sha256": "def",
            },
        ],
    })
    # Mirrors real graph artifacts that may not use a top-level `records` list.
    _write(leiden, {
        "quality_status": "PASS",
        "summary": {"page_nodes_with_community_count": 2},
        "nodes": [
            {"node_type": "Page", "page_number": 5, "leiden_community_id": "c99", "source_member": "00000005.tif"},
            {"node_type": "Page", "page_number": 45, "leiden_community_id": "c99", "source_member": "00000045.tif"},
        ],
    })

    payload = build_answer_context_graph_leiden_expander(
        evidence_enricher=enricher,
        leiden_communities=leiden,
        output_dir=tmp_path / "out2",
        require_source_quality_pass=True,
        require_graph_context=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    summary = payload["summary"]
    assert summary["graph_input_record_count"] == 2
    assert summary["community_annotation_count"] == 2
    assert summary["same_anchor_leiden_community_count"] == 2
    assert summary["page_number_join_key_count"] >= 2
    roles = {r["citation_label"]: r["graph_context_role"] for r in payload["records"]}
    assert roles["E2"] == "same_leiden_community_neighbor"
