import json
from pathlib import Path

from tiff.trace_net_visual_part_nomenclature_enricher_v1 import (
    build_visual_part_nomenclature_enricher,
    check_visual_part_nomenclature_enricher,
)


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def test_enriches_visual_part_description_from_grouped_table_row(tmp_path):
    pack = _write(tmp_path / "pack.json", {
        "quality_status": "PASS",
        "records": [{
            "citation_label": "V6",
            "linked": True,
            "page_id": "t_p_120_1176_p000315",
            "page_number": 315,
            "figure": "69",
            "callout": "",
            "linked_part_number": "120-50645-005",
            "linked_description": "",
            "link_confidence": "MEDIUM",
            "proof_strength": "linked_visual_plus_figure_page_table_proof",
            "source_trace_ready": True,
            "citation_ready": True,
        }]
    })
    table = _write(tmp_path / "table.json", {
        "quality_status": "PASS",
        "evidence_documents": [
            {
                "page_id": "t_p_120_1176_p000315",
                "table_id": "table315",
                "row_index": 7,
                "field_name": "covered_part_number",
                "normalized_value": "120-50645-005",
                "source_trace": {"page_id": "t_p_120_1176_p000315", "table_id": "table315", "row_index": 7},
            },
            {
                "page_id": "t_p_120_1176_p000315",
                "table_id": "table315",
                "row_index": 7,
                "field_name": "ipl_nomenclature",
                "normalized_value": "STRUCTURE, SUPPORT LEG",
                "source_trace": {"page_id": "t_p_120_1176_p000315", "table_id": "table315", "row_index": 7, "field_name": "ipl_nomenclature"},
            },
        ],
    })
    result = build_visual_part_nomenclature_enricher(
        image_visual_evidence_pack=pack,
        table_route_evidence_packager=table,
        output_dir=tmp_path / "out",
        min_linked_visual_parts=1,
        min_description_enriched=1,
        min_source_trace_ready=1,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["description_enriched_count"] == 1
    rec = result["records"][0]
    assert rec["linked_description"] == "STRUCTURE, SUPPORT LEG"
    assert rec["description_status"] == "enriched"
    assert rec["answer_permission"] is False
    assert rec["source_truth_mutation_allowed"] is False


def test_filters_filename_as_bad_description_and_reports_missing(tmp_path):
    pack = _write(tmp_path / "pack.json", {
        "records": [{
            "citation_label": "V7",
            "linked": True,
            "page_id": "t_p_120_1176_p000327",
            "page_number": 327,
            "figure": "75",
            "linked_part_number": "120-50645-011",
            "linked_description": "00000327.tif",
            "source_trace_ready": True,
            "citation_ready": True,
        }]
    })
    table = _write(tmp_path / "table.json", {
        "evidence_documents": [
            {"page_id": "t_p_120_1176_p000327", "table_id": "t", "row_index": 1, "field_name": "covered_part_number", "normalized_value": "120-50645-011"},
            {"page_id": "t_p_120_1176_p000327", "table_id": "t", "row_index": 1, "field_name": "source_member", "normalized_value": "00000327.tif"},
        ]
    })
    result = build_visual_part_nomenclature_enricher(
        image_visual_evidence_pack=pack,
        table_route_evidence_packager=table,
        output_dir=tmp_path / "out",
        min_linked_visual_parts=1,
        min_description_enriched=0,
        min_source_trace_ready=1,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["description_missing_count"] == 1
    assert result["records"][0]["linked_description"] == ""
    assert result["missing_description_records"][0]["reason"] == "no_trusted_description_field_found"


def test_quality_check_fails_when_description_threshold_not_met(tmp_path):
    pack = _write(tmp_path / "pack.json", {
        "records": [{
            "citation_label": "V8",
            "linked": True,
            "page_id": "t_p_120_1176_p000382",
            "page_number": 382,
            "figure": "91",
            "linked_part_number": "120-29068-003",
            "source_trace_ready": True,
            "citation_ready": True,
        }]
    })
    table = _write(tmp_path / "table.json", {"evidence_documents": []})
    build_visual_part_nomenclature_enricher(
        image_visual_evidence_pack=pack,
        table_route_evidence_packager=table,
        output_dir=tmp_path / "out",
        min_linked_visual_parts=1,
        min_description_enriched=0,
        min_source_trace_ready=1,
    )
    check = check_visual_part_nomenclature_enricher(
        enricher=tmp_path / "out" / "trace_net_visual_part_nomenclature_enricher_v1.json",
        output=tmp_path / "check.json",
        require_quality_pass=True,
        min_linked_visual_parts=1,
        min_description_enriched=1,
        min_source_trace_ready=1,
    )
    assert check["quality_status"] == "FAIL"
    assert any("description available" in f for f in check["failures"])


def test_writes_csv_and_quality_check_artifacts(tmp_path):
    pack = _write(tmp_path / "pack.json", {
        "records": [{
            "citation_label": "V6",
            "linked": True,
            "page_id": "t_p_120_1176_p000315",
            "page_number": 315,
            "figure": "69",
            "linked_part_number": "120-50645-005",
            "source_trace_ready": True,
            "citation_ready": True,
        }]
    })
    table = _write(tmp_path / "table.json", {"evidence_documents": []})
    result = build_visual_part_nomenclature_enricher(
        image_visual_evidence_pack=pack,
        table_route_evidence_packager=table,
        output_dir=tmp_path / "out",
        min_linked_visual_parts=1,
        min_description_enriched=0,
        min_source_trace_ready=1,
    )
    assert Path(result["paths"]["records_csv"]).exists()
    assert Path(result["paths"]["quality_check"]).exists()
    assert Path(result["paths"]["missing_report"]).exists()
