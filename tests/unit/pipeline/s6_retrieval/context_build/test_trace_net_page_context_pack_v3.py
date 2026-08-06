from tiff.trace_net_page_context_pack_v3 import (
    build_page_context_pack_v3,
    check_page_context_pack_v3_quality,
    extract_query_entities,
)


def sample_inputs():
    route_manifest = {
        "records": [
            {"page_id": "t_p_120_1176_p000048", "page_number": 48, "page_label": "1048", "primary_route": "normal_text", "ata_section": "25-21-00"},
            {"page_id": "t_p_120_1176_p000202", "page_number": 202, "page_label": "1202", "primary_route": "image_visual", "ata_section": "25-21-00"},
        ]
    }
    ocr_records = {
        "records": [
            {"page_id": "t_p_120_1176_p000048", "ocr_text": "Seat assembly removal instruction mentions 120-50645-005.", "source_file": "000048.tif", "source_link": "rescarta://p48"},
            {"page_id": "t_p_120_1176_p000202", "ocr_text": "Figure page with callouts and seat back structure.", "source_file": "000202.tif"},
        ]
    }
    exact_part_records = {
        "records": [
            {"page_id": "t_p_120_1176_p000048", "part_number": "120-50645-005", "nomenclature": "SEAT ASSY", "source_trace": "ocr:000048"}
        ]
    }
    visual_summaries = {
        "records": [
            {"page_id": "t_p_120_1176_p000202", "summary": "Guidance only: diagram appears to show a seat assembly view."}
        ]
    }
    graph_export = {
        "nodes": [
            {"id": "t_p_120_1176_p000048", "node_type": "page", "page_number": 48, "ata_section": "25-21-00"}
        ],
        "edges": [
            {"source": "t_p_120_1176_p000048", "target": "source_link_48", "edge_type": "HAS_SOURCE_LINK"},
            {"source": "t_p_120_1176_p000048", "target": "120-50645-005", "edge_type": "MENTIONS_PART"},
        ],
    }
    return route_manifest, graph_export, ocr_records, exact_part_records, visual_summaries


def test_extract_query_entities_page_and_part():
    entities = extract_query_entities("What is on page 48 and part 120-50645-005?")
    assert entities["intent"] == "page_lookup"
    assert entities["pages"] == [48]
    assert entities["part_numbers"] == ["120-50645-005"]


def test_build_page_context_pack_selects_requested_pages():
    route, graph, ocr, exact, visual = sample_inputs()
    pack = build_page_context_pack_v3(
        question="write a paragraph about pages 48 and 202",
        route_manifest=route,
        graph_export=graph,
        ocr_records=ocr,
        exact_part_records=exact,
        visual_summaries=visual,
    )
    assert pack["quality_status"] == "PASS"
    page_ids = {r["page_id"] for r in pack["page_context_records"]}
    assert "t_p_120_1176_p000048" in page_ids
    assert "t_p_120_1176_p000202" in page_ids


def test_exact_part_lookup_adds_proof_first_context():
    route, graph, ocr, exact, visual = sample_inputs()
    pack = build_page_context_pack_v3(
        question="Find part number 120-50645-005",
        route_manifest=route,
        graph_export=graph,
        ocr_records=ocr,
        exact_part_records=exact,
        visual_summaries=visual,
    )
    rec = pack["page_context_records"][0]
    assert rec["exact_part_hits"]
    assert rec["proof_record_count"] >= 1
    assert rec["source_trace_ready"] is True


def test_visual_is_guidance_only_not_proof():
    route, graph, ocr, exact, visual = sample_inputs()
    pack = build_page_context_pack_v3(
        question="page 202 diagram",
        route_manifest=route,
        graph_export=graph,
        ocr_records={},
        exact_part_records={},
        visual_summaries=visual,
    )
    rec = pack["page_context_records"][0]
    assert rec["visual_guidance"][0]["proof_role"] == "guidance_only"
    assert rec["visual_guidance"][0]["can_be_used_as_proof"] is False


def test_reasoning_work_order_allows_synthesis_but_blocks_overclaiming():
    route, graph, ocr, exact, visual = sample_inputs()
    pack = build_page_context_pack_v3(
        question="Why might the seat assembly pages be related?",
        route_manifest=route,
        graph_export=graph,
        ocr_records=ocr,
        exact_part_records=exact,
        visual_summaries=visual,
    )
    work = pack["reasoning_work_order"]
    assert work["model_should_think"] is True
    assert any("Synthesize" in rule for rule in work["allowed_reasoning"])
    assert any("interchangeability" in rule for rule in work["disallowed_reasoning"])


def test_quality_gate_passes_safe_pack():
    route, graph, ocr, exact, visual = sample_inputs()
    pack = build_page_context_pack_v3(
        question="page 48",
        route_manifest=route,
        graph_export=graph,
        ocr_records=ocr,
        exact_part_records=exact,
        visual_summaries=visual,
    )
    quality = check_page_context_pack_v3_quality(pack, min_pages=1, require_no_answer_permission=True, require_reasoning_work_order=True)
    assert quality["quality_status"] == "PASS"
    assert quality["failure_reasons"] == []


def test_resolves_numeric_page_from_embedded_source_page_id_without_page_number():
    route_manifest = {
        "records": [
            {"source_page_id": "source_p000048", "primary_route": "normal_text"},
            {"source_page_id": "t_p_120_1176_p000202", "primary_route": "image_visual"},
        ]
    }
    pack = build_page_context_pack_v3(
        question="write a paragraph about pages 48 and 202",
        route_manifest=route_manifest,
    )
    assert pack["quality_status"] == "PASS"
    selected_numbers = {r["page_number"] for r in pack["page_context_records"]}
    assert {48, 202}.issubset(selected_numbers)


def test_nested_manifest_records_are_discovered():
    route_manifest = {
        "manifest": {
            "route_manifest_records": [
                {"page_id": "source_p000048", "primary_route": "normal_text"},
            ]
        }
    }
    pack = build_page_context_pack_v3(
        question="page 48",
        route_manifest=route_manifest,
    )
    assert pack["summary"]["selected_page_count"] == 1
    assert pack["page_context_records"][0]["page_number"] == 48


def test_unresolved_requested_page_gets_safe_placeholder_not_empty_pack():
    pack = build_page_context_pack_v3(
        question="page 999",
        requested_pages=[999],
        route_manifest={},
    )
    assert pack["summary"]["selected_page_count"] == 1
    rec = pack["page_context_records"][0]
    assert rec["page_number"] == 999
    assert rec["source_trace_ready"] is False
    assert "requested_page_not_resolved_in_input_artifacts" in rec["warnings"]


def test_route_manifest_source_locator_and_route_priority_are_attached():
    route_manifest = {
        "records": [
            {
                "page_id": "t_p_120_1176_p000202",
                "primary_route": "image_visual",
                "source_member": "00000202.tif",
                "source_link": "rescarta://p202",
            }
        ]
    }
    pack = build_page_context_pack_v3(question="page 202", route_manifest=route_manifest)
    rec = pack["page_context_records"][0]
    assert rec["source_files"]
    assert rec["source_links"]
    assert rec["source_trace_ready"] is True
    assert rec["route_evidence_priority"][0] == "source_files"
    assert "visual_guidance" in rec["route_evidence_priority"]


def test_unproven_table_record_becomes_route_guidance_not_proof():
    route_manifest = {"records": [{"page_id": "t_p_120_1176_p000202", "page_number": 202, "primary_route": "image_visual"}]}
    table = {
        "records": [
            {
                "page_id": "t_p_120_1176_p000202",
                "source_table_id": "table202",
                "can_prove_claims": False,
                "can_answer_directly": False,
                "cells": [],
                "rows": [],
                "citation_ready": True,
            }
        ]
    }
    pack = build_page_context_pack_v3(question="page 202", route_manifest=route_manifest, table_evidence=table)
    rec = pack["page_context_records"][0]
    assert rec["table_evidence"] == []
    assert rec["route_guidance"]
    assert rec["route_guidance"][0]["can_be_used_as_proof"] is False


def test_graph_citation_map_can_add_source_file_guidance():
    route_manifest = {"records": [{"page_id": "t_p_120_1176_p000343", "page_number": 343, "primary_route": "table"}]}
    graph = {
        "citation_map": [
            {
                "page_id": "t_p_120_1176_p000343",
                "page_number": 343,
                "source_member": "00000343.tif",
                "citation_label": "E1",
                "proof_strength": "direct_exact_proof",
            }
        ]
    }
    pack = build_page_context_pack_v3(question="page 343", route_manifest=route_manifest, graph_export=graph)
    rec = pack["page_context_records"][0]
    assert rec["source_files"]
    assert rec["graph_neighbors"]


def test_quality_gate_can_require_guidance_and_source_locators():
    route, graph, ocr, exact, visual = sample_inputs()
    route["records"][0]["source_file"] = "000048.tif"
    pack = build_page_context_pack_v3(
        question="page 48",
        route_manifest=route,
        graph_export=graph,
        ocr_records=ocr,
        exact_part_records=exact,
        visual_summaries=visual,
    )
    quality = check_page_context_pack_v3_quality(
        pack,
        min_pages=1,
        require_no_answer_permission=True,
        require_reasoning_work_order=True,
        min_guidance_records=1,
        min_source_trace_ready_pages=1,
        min_source_locators=1,
    )
    assert quality["quality_status"] == "PASS"


def test_numeric_page_label_does_not_override_source_page_number() -> None:
    from tiff.trace_net_page_context_pack_v3 import build_page_context_pack_v3

    route_manifest = {
        "records": [
            {"page_id": "t_p_120_1176_p000048", "page_number": 48, "page_label": "A"},
            {"page_id": "t_p_120_1176_p000448", "page_number": 448, "page_label": "48"},
            {"page_id": "t_p_120_1176_p000202", "page_number": 202},
        ]
    }
    vector_hits = {
        "records": [
            {"page_id": "t_p_120_1176_p000048", "embedding_text": "source page 48 context"},
            {"page_id": "t_p_120_1176_p000448", "embedding_text": "manual label 48 but source page 448 context"},
            {"page_id": "t_p_120_1176_p000202", "embedding_text": "source page 202 context"},
        ]
    }
    pack = build_page_context_pack_v3(
        question="write a paragraph about pages 48 and 202",
        requested_pages=[48, 202],
        route_manifest=route_manifest,
        vector_hits=vector_hits,
    )
    page_ids = [r["page_id"] for r in pack["page_context_records"]]
    assert page_ids == ["t_p_120_1176_p000048", "t_p_120_1176_p000202"]
    assert "t_p_120_1176_p000448" not in page_ids


def test_label_qualified_lookup_can_still_find_numeric_page_label() -> None:
    from tiff.trace_net_page_context_pack_v3 import build_index

    route_manifest = {
        "records": [
            {"page_id": "t_p_120_1176_p000448", "page_number": 448, "page_label": "48"},
        ]
    }
    idx = build_index(route_manifest=route_manifest)
    assert idx.resolve("48") is None
    assert idx.resolve("label:48") == "t_p_120_1176_p000448"
