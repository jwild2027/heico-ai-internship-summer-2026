import json
from pathlib import Path
from scripts.build.tables.build_trace_net_full_corpus_serving_pack_v1 import parser, build


def test_build_full_corpus_pack_from_fixture(tmp_path: Path):
    source = tmp_path / "artifact.json"
    source.write_text(json.dumps({
        "records": [
            {
                "page_id": "p000001",
                "document_id": "manual-a",
                "part_numbers": ["120-41824-003"],
                "table_text": "LOCKING RING",
                "v2_summary": "Illustrated parts list page for a locking ring.",
                "community_id": "community_1",
            },
            {
                "page_id": "p000002",
                "manual_reference": "25-21-00",
                "ocr_text": "Removal procedure and caution text.",
                "page_summary": "Procedure page with removal steps and caution.",
            },
        ]
    }), encoding="utf-8")
    out = tmp_path / "out"
    args = parser().parse_args([
        "--artifact-root", str(tmp_path),
        "--input", str(source),
        "--output-dir", str(out),
        "--min-exact-documents", "1",
        "--min-page-summaries", "1",
        "--min-page-memberships", "1",
    ])
    result = build(args)
    assert result["quality_status"] == "PASS"
    assert result["exact_search_document_count"] >= 4
    assert result["page_summary_count"] == 2
    assert result["leiden_page_membership_count"] == 2
    assert Path(result["paths"]["v27_manifest"]).exists()
    manifest = json.loads(Path(result["paths"]["v27_manifest"]).read_text())
    assert manifest["exact_search_document_count"] >= 4
    assert manifest["page_summary_count"] == 2
    assert manifest["leiden_page_membership_count"] == 2


def test_builder_extracts_guided_nomenclature_as_searchable_table_text(tmp_path: Path):
    source = tmp_path / "last_guided_discovery_response.json"
    source.write_text(json.dumps({
        "candidate_routes": [
            {
                "route_id": "route_6",
                "candidate_part_number": "120-48024-001",
                "nomenclature": "RING, LOCKING",
                "page_id": "t_p_120_1176_p000055",
                "document": "EMB CMM ATA 25-21-00 REV.4",
                "community_id": "community_locking_rings",
            }
        ]
    }), encoding="utf-8")
    out = tmp_path / "out"
    args = parser().parse_args([
        "--artifact-root", str(tmp_path),
        "--input", str(source),
        "--output-dir", str(out),
        "--min-exact-documents", "1",
        "--min-page-summaries", "0",
        "--min-page-memberships", "1",
    ])
    result = build(args)
    assert result["quality_status"] == "PASS"
    adapter = json.loads(Path(result["paths"]["adapter"]).read_text())
    rows = adapter["exact_search_documents"]
    assert any(r["field_name"] == "part_number" and r["normalized_value"] == "120-48024-001" for r in rows)
    assert any(r["field_name"] == "nomenclature" and r["normalized_value"] == "RING, LOCKING" for r in rows)
    assert any(r["field_name"] == "table_text" and r["normalized_value"] == "RING, LOCKING" for r in rows)


def test_full_corpus_manifest_can_match_locking_ring_order_insensitive(tmp_path: Path):
    source = tmp_path / "last_guided_discovery_response.json"
    source.write_text(json.dumps({
        "candidate_routes": [
            {
                "candidate_part_number": "120-48024-001",
                "nomenclature": "RING, LOCKING",
                "page_id": "t_p_120_1176_p000055",
                "community_id": "community_locking_rings",
            }
        ]
    }), encoding="utf-8")
    out = tmp_path / "out"
    args = parser().parse_args([
        "--artifact-root", str(tmp_path),
        "--input", str(source),
        "--output-dir", str(out),
        "--min-exact-documents", "1",
        "--min-page-summaries", "0",
        "--min-page-memberships", "1",
    ])
    result = build(args)
    from tiff import trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 as v27
    state = v27.load_state_for_serving(Path(result["paths"]["v27_manifest"]))
    state["llm_mode"] = "simulate"
    answer = v27.run_live_query_v27("Search table text LOCKING RING", state, llm_mode="simulate")
    assert answer["final_gate_status"] == "LIVE_ORCHESTRATOR_FINAL_GATE_PASS"
    assert len(answer["retrieval"]["direct_evidence"]) >= 1
