import json
from pathlib import Path

from tiff.trace_net_answer_context_exact_row_proof_v1 import build_answer_context_exact_row_proof


def test_exact_row_proof_upgrades_direct_candidate_from_ocr(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"query_part_numbers": ["120-29073-001"], "question": "Find 120-29073-001"},
        "records": [{
            "citation_label": "E1", "page_id": "p1", "page_number": 5, "route": "table",
            "graph_context_role": "direct_exact_match_candidate", "enriched_excerpt": "header only",
            "source_member": "00000005.tif", "source_image_sha256": "abc"
        }]
    }), encoding="utf-8")
    ocr = tmp_path / "ocr.json"
    ocr.write_text(json.dumps({
        "quality_status": "PASS",
        "records": [{"page_id": "p1", "page_number": 5, "ocr_text": "ITEM 10 PART NUMBER 120-29073-001 STRUCTURE ASSY"}]
    }), encoding="utf-8")
    payload = build_answer_context_exact_row_proof(
        graph_leiden_expander=graph,
        ocr_route_scan_pack=ocr,
        output_dir=tmp_path / "out",
        require_source_quality_pass=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["direct_exact_match_proven_count"] == 1
    rec = payload["records"][0]
    assert rec["exact_row_proof_status"] == "PROVEN"
    assert rec["exact_row_context_role"] == "direct_exact_match_proven"
    assert rec["exact_match_sources"] == ["ocr_route_scan_pack"]
    assert "120-29073-001" in rec["exact_row_text"]


def test_candidate_remains_candidate_without_exact_text(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"query_part_numbers": ["120-29073-001"], "question": "Find 120-29073-001"},
        "records": [{"citation_label": "E1", "page_id": "p1", "page_number": 5, "graph_context_role": "direct_exact_match_candidate", "enriched_excerpt": "no exact part"}]
    }), encoding="utf-8")
    payload = build_answer_context_exact_row_proof(graph_leiden_expander=graph, output_dir=tmp_path / "out", require_source_quality_pass=True)
    assert payload["summary"]["direct_exact_match_proven_count"] == 0
    assert payload["summary"]["direct_exact_match_candidate_count"] == 1
    assert payload["records"][0]["exact_row_proof_status"] == "CANDIDATE"


def test_table_exact_search_adapter_can_prove_by_page_number(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"query_part_numbers": ["ABC-123-001"], "question": "Find ABC-123-001"},
        "records": [{"citation_label": "E1", "page_id": "p1", "page_number": 7, "graph_context_role": "direct_exact_match_candidate"}]
    }), encoding="utf-8")
    exact = tmp_path / "exact.json"
    exact.write_text(json.dumps({"quality_status": "PASS", "documents": [{"page_number": 7, "covered_part_number": "ABC-123-001", "row_text": "ABC-123-001 BOLT ASSY"}]}), encoding="utf-8")
    payload = build_answer_context_exact_row_proof(graph_leiden_expander=graph, table_exact_search_adapter=exact, output_dir=tmp_path / "out")
    assert payload["records"][0]["exact_match_sources"] == ["table_exact_search_adapter"]
    assert payload["summary"]["exact_source_counts"]["table_exact_search_adapter"] == 1


def test_query_metadata_in_context_does_not_prove_all_records(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"query_part_numbers": ["120-29073-001"], "question": "Find 120-29073-001"},
        "records": [
            {
                "citation_label": "E1",
                "page_id": "p1",
                "page_number": 5,
                "graph_context_role": "direct_exact_match_candidate",
                "query_part_numbers": ["120-29073-001"],
                "enriched_excerpt": "LEP page text with no requested part number",
            },
            {
                "citation_label": "E2",
                "page_id": "p2",
                "page_number": 45,
                "graph_context_role": "similar_table_candidate",
                "query_part_numbers": ["120-29073-001"],
                "enriched_excerpt": "120-40636-001 120-40796-001 unrelated table text",
            },
        ],
    }), encoding="utf-8")
    payload = build_answer_context_exact_row_proof(
        graph_leiden_expander=graph,
        output_dir=tmp_path / "out",
        require_source_quality_pass=True,
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["direct_exact_match_proven_count"] == 0
    assert payload["summary"]["direct_exact_match_candidate_count"] == 1
    assert payload["summary"]["nearby_or_related_evidence_count"] == 1
    assert payload["summary"]["untrusted_context_part_match_ignored_count"] == 2
    assert all("graph_expanded_or_enriched_context" not in r.get("exact_match_sources", []) for r in payload["records"])
    assert payload["records"][0]["exact_row_proof_status"] == "CANDIDATE"
    assert payload["records"][1]["exact_row_proof_status"] == "RELATED"


def test_enriched_excerpt_source_is_not_trusted_without_source_artifact_match(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"query_part_numbers": ["ABC-123-001"], "question": "Find ABC-123-001"},
        "records": [{
            "citation_label": "E1",
            "page_id": "p1",
            "page_number": 5,
            "graph_context_role": "direct_exact_match_candidate",
            "enriched_excerpt_source": "ocr_route_scan_pack",
            "enriched_excerpt": "ABC-123-001 appears here but only inside carried context, not the joined source file",
        }],
    }), encoding="utf-8")
    payload = build_answer_context_exact_row_proof(
        graph_leiden_expander=graph,
        output_dir=tmp_path / "out",
    )
    assert payload["summary"]["direct_exact_match_proven_count"] == 0
    assert payload["records"][0]["exact_row_proof_status"] == "CANDIDATE"
    assert payload["records"][0]["exact_match_sources"] == []


def test_outputs_expected_files(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({"quality_status": "PASS", "summary": {"query_part_numbers": ["P-1"]}, "records": []}), encoding="utf-8")
    out = tmp_path / "out"
    build_answer_context_exact_row_proof(graph_leiden_expander=graph, output_dir=out)
    assert (out / "trace_net_answer_context_exact_row_proof_v1.json").exists()
    assert (out / "trace_net_answer_context_exact_row_proof_v1_prompt.txt").exists()
    assert (out / "trace_net_answer_context_exact_row_proof_v1_records.csv").exists()
