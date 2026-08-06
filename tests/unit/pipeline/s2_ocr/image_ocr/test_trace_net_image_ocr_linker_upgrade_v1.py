import json
from argparse import Namespace
from pathlib import Path

from tiff.trace_net_image_ocr_figure_callout_extractor_v1 import build_extractor
from tiff.trace_net_visual_callout_table_linker_v2 import build_linker, looks_like_bad_description
from tiff.trace_net_image_ocr_figure_callout_extractor_v1_check import evaluate as evaluate_extractor
from tiff.trace_net_visual_callout_table_linker_v2_check import evaluate as evaluate_linker


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def extractor_args(tmp_path, llava, ocr):
    return Namespace(
        llava_visual_summary_batch=str(llava),
        ocr_route_scan_pack=str(ocr),
        output_dir=str(tmp_path / "extractor_out"),
        min_extractor_records=1,
        min_ocr_text_available=1,
        min_figure_candidate_records=1,
        min_source_trace_ready=1,
        max_unsafe=0,
        max_answer_permission=0,
        max_source_truth_mutation_allowed=0,
        max_write_attempts=0,
    )


def linker_args(tmp_path, llava, extractor, ocr, evidence, min_linked=1):
    return Namespace(
        llava_visual_summary_batch=str(llava),
        ocr_figure_callout_extractor=str(extractor),
        ocr_route_scan_pack=str(ocr),
        trusted_evidence_artifact=[],
        table_exact_search_adapter="",
        table_route_evidence_packager=str(evidence),
        figure_item_evidence="",
        nearby_page_window=2,
        output_dir=str(tmp_path / "linker_out"),
        min_visual_callout_records=1,
        min_linked_callouts=min_linked,
        min_source_trace_ready=min_linked,
        max_unsafe=0,
        max_answer_permission=0,
        max_source_truth_mutation_allowed=0,
        max_write_attempts=0,
    )


def make_llava_and_ocr(tmp_path):
    llava = tmp_path / "llava.json"
    ocr = tmp_path / "ocr.json"
    write_json(llava, {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000315",
                "page_number": 315,
                "source_member": "00000315.tif",
                "figure_candidates": [],
                "callout_candidates": [],
                "visible_text_candidates": [],
                "visual_summary": "Technical diagram page.",
                "answer_permission": False,
            }
        ],
    })
    write_json(ocr, {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000315",
                "page_number": 315,
                "ocr_text": "FIG. 69 ITEM 1 LATERAL LEG STRUCTURE\nSome other OCR text.",
                "source_trace_ready": True,
            }
        ],
    })
    return llava, ocr


def make_table_evidence(tmp_path, description="STRUCTURE, LATERAL LEG"):
    evidence = tmp_path / "table_evidence.json"
    docs = [
        {
            "page_id": "t_p_120_1176_p000315",
            "page_number": 315,
            "table_id": "table_315",
            "row_index": 7,
            "field_name": "ipl_figure_item_or_quantity",
            "normalized_value": "1",
            "source_trace": {"table_id": "table_315", "field_name": "ipl_figure_item_or_quantity"},
        },
        {
            "page_id": "t_p_120_1176_p000315",
            "page_number": 315,
            "table_id": "table_315",
            "row_index": 7,
            "field_name": "ipl_part_number",
            "normalized_value": "120-50645-005",
            "source_trace": {"table_id": "table_315", "field_name": "ipl_part_number"},
        },
        {
            "page_id": "t_p_120_1176_p000315",
            "page_number": 315,
            "table_id": "table_315",
            "row_index": 7,
            "field_name": "ipl_nomenclature",
            "normalized_value": description,
            "source_trace": {"table_id": "table_315", "field_name": "ipl_nomenclature"},
        },
    ]
    write_json(evidence, {"quality_status": "PASS", "evidence_documents": docs})
    return evidence


def test_ocr_extractor_reads_figure_and_item(tmp_path):
    llava, ocr = make_llava_and_ocr(tmp_path)
    artifact = build_extractor(extractor_args(tmp_path, llava, ocr))
    assert artifact["quality_status"] == "PASS"
    record = artifact["records"][0]
    assert "69" in record["figure_candidates"]
    assert "1" in record["callout_candidates"]
    assert record["ocr_label_confidence"] == "HIGH"
    assert record["answer_permission"] is False
    assert record["source_truth_mutation_allowed"] is False


def test_linker_v2_makes_high_link_from_ocr_and_table_row(tmp_path):
    llava, ocr = make_llava_and_ocr(tmp_path)
    extractor = build_extractor(extractor_args(tmp_path, llava, ocr))
    extractor_path = Path(extractor["artifact_paths"]["extractor"])
    evidence = make_table_evidence(tmp_path)
    linker = build_linker(linker_args(tmp_path, llava, extractor_path, ocr, evidence, min_linked=1))
    assert linker["quality_status"] == "PASS"
    linked = [r for r in linker["records"] if r["linked"]]
    assert linked
    assert linked[0]["link_confidence"] == "HIGH"
    assert linked[0]["linked_part_number"] == "120-50645-005"
    assert linked[0]["linked_description"] == "STRUCTURE, LATERAL LEG"
    assert linked[0]["proof_source"] == "trusted_ocr_table_figure_item_evidence"
    assert linked[0]["answer_permission"] is False


def test_linker_v2_suppresses_tiff_filename_as_description(tmp_path):
    llava, ocr = make_llava_and_ocr(tmp_path)
    extractor = build_extractor(extractor_args(tmp_path, llava, ocr))
    extractor_path = Path(extractor["artifact_paths"]["extractor"])
    evidence = make_table_evidence(tmp_path, description="00000315.tif")
    linker = build_linker(linker_args(tmp_path, llava, extractor_path, ocr, evidence, min_linked=1))
    linked = [r for r in linker["records"] if r["linked"]]
    assert linked
    assert linked[0]["linked_description"] == ""
    assert linked[0]["linked_description_quality"] == "missing_not_filename"
    assert looks_like_bad_description("00000315.tif")


def test_linker_v2_keeps_unproven_visual_label_low(tmp_path):
    llava, ocr = make_llava_and_ocr(tmp_path)
    extractor = build_extractor(extractor_args(tmp_path, llava, ocr))
    extractor_path = Path(extractor["artifact_paths"]["extractor"])
    empty_evidence = tmp_path / "empty_evidence.json"
    write_json(empty_evidence, {"quality_status": "PASS", "evidence_documents": []})
    linker = build_linker(linker_args(tmp_path, llava, extractor_path, ocr, empty_evidence, min_linked=0))
    assert linker["quality_status"] == "PASS"
    assert linker["summary"]["linked_callout_record_count"] == 0
    assert linker["summary"]["low_confidence_link_count"] >= 1
    assert all(not r["answer_permission"] for r in linker["records"])


def test_checkers_accept_clean_artifacts(tmp_path):
    llava, ocr = make_llava_and_ocr(tmp_path)
    extractor = build_extractor(extractor_args(tmp_path, llava, ocr))
    records = extractor["records"]
    quality, checks, summary = evaluate_extractor(records, "PASS", Namespace(
        require_quality_pass=True,
        min_extractor_records=1,
        min_ocr_text_available=1,
        min_figure_candidate_records=1,
        min_source_trace_ready=1,
        max_unsafe=0,
        max_answer_permission=0,
        max_source_truth_mutation_allowed=0,
        max_write_attempts=0,
    ))
    assert quality == "PASS"
    assert summary["answer_permission_count"] == 0

    extractor_path = Path(extractor["artifact_paths"]["extractor"])
    evidence = make_table_evidence(tmp_path)
    linker = build_linker(linker_args(tmp_path, llava, extractor_path, ocr, evidence, min_linked=1))
    quality2, checks2, summary2 = evaluate_linker(linker["records"], "PASS", Namespace(
        require_quality_pass=True,
        min_visual_callout_records=1,
        min_linked_callouts=1,
        min_source_trace_ready=1,
        max_unsafe=0,
        max_answer_permission=0,
        max_source_truth_mutation_allowed=0,
        max_write_attempts=0,
    ))
    assert quality2 == "PASS"
    assert summary2["linked_callout_record_count"] >= 1


def test_linker_v2_uses_ocr_route_scan_pack_as_trusted_evidence_and_dedupes_same_part(tmp_path):
    """Regression: v2 accidentally used OCR only as text guidance, losing B2 links."""
    llava = tmp_path / "llava.json"
    ocr = tmp_path / "ocr.json"
    extractor = tmp_path / "extractor.json"
    write_json(llava, {
        "quality_status": "PASS",
        "records": [{
            "page_id": "t_p_120_1176_p000315",
            "page_number": 315,
            "figure_candidates": ["69"],
            "callout_candidates": [],
            "visual_summary": "Diagram page with figure 69.",
        }],
    })
    write_json(extractor, {
        "quality_status": "PASS",
        "records": [{
            "page_id": "t_p_120_1176_p000315",
            "page_number": 315,
            "ocr_figure_candidates": ["69"],
            "ocr_callout_candidates": [],
            "source_trace_ready": True,
        }],
    })
    # Two OCR-ish records with the same page/figure/part should be treated as
    # one unique trusted proof, not ambiguity.
    write_json(ocr, {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000315",
                "page_number": 315,
                "ocr_text": "FIG. 69 120-50645-005 STRUCTURE LATERAL LEG",
                "source_trace_ready": True,
                "citation_ready": True,
            },
            {
                "page_id": "t_p_120_1176_p000315",
                "page_number": 315,
                "ocr_text": "FIGURE 69 PN 120-50645-005",
                "source_trace_ready": True,
                "citation_ready": True,
            },
        ],
    })
    empty_table = tmp_path / "empty_table.json"
    write_json(empty_table, {"quality_status": "PASS", "evidence_documents": []})
    linker = build_linker(linker_args(tmp_path, llava, extractor, ocr, empty_table, min_linked=1))
    assert linker["quality_status"] == "PASS"
    assert linker["summary"]["trusted_evidence_record_count"] >= 1
    linked = [r for r in linker["records"] if r["linked"]]
    assert linked
    assert linked[0]["link_confidence"] == "MEDIUM"
    assert linked[0]["linked_part_number"] == "120-50645-005"
