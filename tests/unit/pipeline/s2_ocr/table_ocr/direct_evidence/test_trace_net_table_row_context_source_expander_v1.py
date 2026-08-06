import json
from pathlib import Path

from tiff.trace_net_table_row_context_source_expander_v1 import build_source_expander, check_source_expander


def write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def visual_pack(tmp_path: Path):
    return write(tmp_path / "image_visual_pack.json", {
        "quality_status": "PASS",
        "records": [
            {
                "linked": True,
                "linked_part_number": "120-50645-005",
                "citation_label": "V6",
                "page_id": "t_p_120_1176_p000315",
                "page_number": 315,
                "figure": "69",
                "callout": "",
                "source_trace_ready": True,
                "citation_ready": True,
            }
        ],
    })


def table_pack_with_desc(tmp_path: Path):
    return write(tmp_path / "table_pack.json", {
        "quality_status": "PASS",
        "evidence_documents": [
            {
                "evidence_id": "ev_part",
                "field_name": "ipl_part_number",
                "raw_value": "120-50645-005",
                "normalized_value": "120-50645-005",
                "page_id": "p3",
                "table_id": "t1",
                "row_index": 7,
                "column_index": 1,
                "source_trace": {"source_cell_id": "cell_part", "source_value_record_id": "value_part", "page_id": "p3", "table_id": "t1"},
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            },
            {
                "evidence_id": "ev_desc",
                "field_name": "ipl_nomenclature",
                "raw_value": "SUPPORT BRACKET",
                "normalized_value": "SUPPORT BRACKET",
                "page_id": "p3",
                "table_id": "t1",
                "row_index": 7,
                "column_index": 2,
                "source_trace": {"source_cell_id": "cell_desc", "page_id": "p3", "table_id": "t1"},
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            },
        ],
    })


def table_pack_missing_desc(tmp_path: Path):
    return write(tmp_path / "table_pack.json", {
        "quality_status": "PASS",
        "evidence_documents": [
            {
                "evidence_id": "ev_part",
                "field_name": "covered_part_number",
                "raw_value": "120-50645-005",
                "normalized_value": "120-50645-005",
                "page_id": "p3",
                "table_id": "t1",
                "row_index": 7,
                "column_index": 1,
                "source_trace": {"source_cell_id": "cell_part", "source_value_record_id": "value_part", "page_id": "p3", "table_id": "t1"},
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            },
            {
                "evidence_id": "ev_part2",
                "field_name": "covered_part_number",
                "raw_value": "120-50645-007",
                "normalized_value": "120-50645-007",
                "page_id": "p3",
                "table_id": "t1",
                "row_index": 7,
                "column_index": 2,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            },
        ],
    })


def test_build_selects_row_description(tmp_path):
    result = build_source_expander(
        image_visual_evidence_pack=visual_pack(tmp_path),
        table_route_evidence_packager=table_pack_with_desc(tmp_path),
        output_dir=tmp_path / "out",
        min_linked_visual_parts=1,
        min_row_context_records=1,
        min_source_trace_ready=1,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["description_selected_count"] == 1
    assert result["records"][0]["selected_description"] == "SUPPORT BRACKET"
    assert result["records"][0]["answer_permission"] is False


def test_missing_description_is_pass_when_row_context_exists(tmp_path):
    result = build_source_expander(
        image_visual_evidence_pack=visual_pack(tmp_path),
        table_route_evidence_packager=table_pack_missing_desc(tmp_path),
        output_dir=tmp_path / "out",
        min_linked_visual_parts=1,
        min_row_context_records=1,
        min_source_trace_ready=1,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["description_selected_count"] == 0
    assert result["summary"]["description_missing_count"] == 1
    assert result["records"][0]["row_context_cell_count"] >= 1


def test_upstream_artifact_scan_can_find_description_by_source_id(tmp_path):
    vis = visual_pack(tmp_path)
    table = table_pack_missing_desc(tmp_path)
    upstream = write(tmp_path / "upstream.json", {
        "records": [
            {
                "source_cell_id": "cell_part",
                "nomenclature": "HINGE ASSEMBLY",
                "part_number": "120-50645-005",
            }
        ]
    })
    result = build_source_expander(
        image_visual_evidence_pack=vis,
        table_route_evidence_packager=table,
        source_artifacts=[upstream],
        output_dir=tmp_path / "out",
        min_linked_visual_parts=1,
        min_row_context_records=1,
        min_source_trace_ready=1,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["description_selected_count"] == 1
    assert result["records"][0]["selected_description"] == "HINGE ASSEMBLY"


def test_check_fails_when_row_context_threshold_not_met(tmp_path):
    result = build_source_expander(
        image_visual_evidence_pack=visual_pack(tmp_path),
        table_route_evidence_packager=write(tmp_path / "empty_table.json", {"evidence_documents": []}),
        output_dir=tmp_path / "out",
        min_linked_visual_parts=1,
        min_row_context_records=0,
        min_source_trace_ready=1,
    )
    check = check_source_expander(
        expander=tmp_path / "out" / "trace_net_table_row_context_source_expander_v1.json",
        min_linked_visual_parts=1,
        min_row_context_records=1,
        min_source_trace_ready=1,
    )
    assert result["quality_status"] == "PASS"
    assert check["quality_status"] == "FAIL"
    assert any("row_context_record_count" in f for f in check["failures"])


def test_rejects_graph_and_dublin_core_labels_as_descriptions(tmp_path):
    vis = visual_pack(tmp_path)
    table = table_pack_missing_desc(tmp_path)
    graph = tmp_path / "category_aware_leiden_overlay" / "trace_net_category_aware_leiden_overlay_v1.json"
    graph.parent.mkdir(parents=True, exist_ok=True)
    write(graph, {
        "community_category_profiles": [
            {
                "part_number": "120-50645-005",
                "category_aware_label": "Table + parts + diagram review community",
                "source_community_label": "Part family community 120-50645",
            }
        ]
    })
    dc = tmp_path / "dublin_core_crosswalk" / "trace_net_dublin_core_crosswalk_v1.json"
    dc.parent.mkdir(parents=True, exist_ok=True)
    write(dc, {
        "page_records": [
            {
                "dc": {"title": "TRACE-Net page 315"},
                "trace_net": {"ocr_present": True, "context_v2_present": False},
                "text": "120-50645-005",
            }
        ]
    })

    result = build_source_expander(
        image_visual_evidence_pack=vis,
        table_route_evidence_packager=table,
        source_artifacts=[graph, dc],
        output_dir=tmp_path / "out",
        min_linked_visual_parts=1,
        min_row_context_records=1,
        min_source_trace_ready=1,
    )

    rec = result["records"][0]
    assert result["quality_status"] == "PASS"
    assert result["summary"]["description_selected_count"] == 0
    assert result["summary"]["description_missing_count"] == 1
    assert result["summary"]["description_rejected_count"] >= 1
    assert rec["selected_description"] == ""
    rejected_text = json.dumps(rec["rejected_description_candidates"])
    assert "review community" in rejected_text or "TRACE-Net page" in rejected_text


def test_accepts_only_official_upstream_nomenclature_not_generic_text(tmp_path):
    vis = visual_pack(tmp_path)
    table = table_pack_missing_desc(tmp_path)
    upstream = write(tmp_path / "upstream.json", {
        "records": [
            {
                "source_cell_id": "cell_part",
                "part_number": "120-50645-005",
                "text": "generic nearby text that should not be a nomenclature",
                "nomenclature": "HINGE ASSEMBLY",
            }
        ]
    })
    result = build_source_expander(
        image_visual_evidence_pack=vis,
        table_route_evidence_packager=table,
        source_artifacts=[upstream],
        output_dir=tmp_path / "out",
        min_linked_visual_parts=1,
        min_row_context_records=1,
        min_source_trace_ready=1,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["description_selected_count"] == 1
    assert result["records"][0]["selected_description"] == "HINGE ASSEMBLY"
    assert result["records"][0]["selected_description_source"]["field_name"] == "nomenclature"
