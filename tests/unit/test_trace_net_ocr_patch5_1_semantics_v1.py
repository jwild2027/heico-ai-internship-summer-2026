"""Focused regression tests for TRACE-Net OCR Patch 5.1."""
from __future__ import annotations

from src.trace_net.ocr.trace_net_ocr_cleanup_extraction_v1 import (
    build_cleanup_extraction,
    clean_boilerplate_and_dehyphenate,
    detect_index_toc_structure,
    filter_supplemental_callout_candidates,
    revision_grid_extraction,
)
from src.trace_net.ocr.trace_net_ocr_route_scan_pack_v1 import (
    _classify_route,
    _supplemental_cross_psm_signal,
)
from src.trace_net.validation.trace_net_ocr_cleanup_semantic_checker_v1 import (
    evaluate_cleanup_semantics,
)


def classify(text: str, psm11: str = ""):
    return _classify_route(
        text=text,
        image_features={"ink_ratio_estimate": 0.05},
        tesseract_status="ok",
        supplemental=_supplemental_cross_psm_signal(text, psm11),
    )


def test_page23_vendor_column_prose_is_not_vendor_index():
    text = """8 (WHEN EXHAUSTED USE ...) - Used in the description column of parts for which
existing stocks should be exhausted before the newer designed part is issued.
For correct location of referenced figure, refer to the table of contents.
(5) VENDOR CODE Column.
This column lists the item vendor's codes.
For EMBRAER part numbers, the vendor code is VS4956.
Refer to the Vendor's List to identify the vendor's name and address.
The EFFECTIVITY column enables identification of applicable assemblies.
"""
    assert detect_index_toc_structure(text)["fires"] is False
    route, _, reasons = classify(text)
    assert route == "normal_text", reasons


def test_real_vendor_index_requires_header_and_repeated_codes():
    text = """VENDOR
CODE
E065846
E075221
V15653
VS4956
VENDORS' NAMES AND ADDRESSES
E065846 ACME AEROSPACE
E075221 EXAMPLE SUPPLY
"""
    signal = detect_index_toc_structure(text)
    assert signal["kind"] == "vendor_index"
    route, _, reasons = classify(text)
    assert route == "table", reasons


def test_numerical_index_and_lep_are_structurally_recognized():
    numerical = """PART NUMBER UNITS AIRLINE PART NUMBER UNITS AIRLINE
PER STOCK PER STOCK
CH-SEC-UN-FIG ITEM ASSY NUMBER CH-SEC-UN-FIG ITEM ASSY NUMBER
25-21-00-01 130 4 25-21-00-31 70 8
25-21-00-02 130 4 25-21-00-32 70 8
25-21-00-03 120 4 25-21-00-33 80 8
"""
    lep = """CHAPTER CHAPTER
SECTION SECTION
SUBJECT PAGE DATE SUBJECT PAGE DATE
25-IPL 1072 Jan 15/01 25-IPL 1103 Sep 30/98
25-IPL 1073 Sep 30/98 25-IPL 1104 Sep 30/98
25-IPL 1074 Sep 30/98 25-IPL 1105 Sep 30/98
"""
    assert detect_index_toc_structure(numerical)["kind"] == "numerical_index"
    assert detect_index_toc_structure(lep)["kind"] == "list_of_effective_pages"
    assert classify(numerical)[0] == "table"
    assert classify(lep)[0] == "table"


def test_page494_labeled_figure_routes_visual_without_lowering_global_threshold():
    text = """VACUUM BAG
SEALANT
BLEEDER
PERFORATED PARTING FILM
REPLACEMENT PLIES
VACUUM LINE
MASKING TAPE ABRADED AREA
Cure of Overlapping Plies
Figure 604
"""
    route, confidence, reasons = classify(text, "VACUUM BAG SEALANT BLEEDER")
    assert route == "image_visual"
    assert confidence >= 0.85
    assert reasons[0].startswith("diagram_figure_title_labeled_layout")


def test_dpl_leaders_are_not_cleaned_or_marked_as_index_by_builder():
    dpl = """FIG. ITEM PART NUMBER STOCK NOMENCLATURE EFF FROM TO UNITS PER ASSY
01 10 120-29067-019 STRUCTURE ASSY ............ VS4956 A 1
20 120-33774-001 LINING ASSY ................. VS4956 1
30 120-42221-001 LINING ASSY ................. VS4956 1
"""
    out = build_cleanup_extraction({
        "page_id": "p82",
        "primary_ocr_text": dpl,
        "tesseract_supplemental_psm11_raw_text": "10 20 30 STRUCTURE",
        "accepted_route": "table",
    }, final_route="table")
    assert out["is_index_or_toc"] is False
    assert out["dotted_leader_cleanup_scope_applied"] is False
    assert "............" in out["cleaned_ocr_text"]
    assert out["retained_callout_candidate_count"] == 0


def test_toc_leaders_are_scoped_and_parsed():
    toc = """TABLE OF CONTENTS
Subject Page
Applicability ................................ i
Introduction ................................. 1
Disassembly ................................ 301
Repair ..................................... 601
"""
    out = build_cleanup_extraction({"page_id": "p509", "primary_ocr_text": toc, "accepted_route": "table"}, final_route="table")
    assert out["is_index_or_toc"] is True
    assert out["index_or_toc_kind"] == "table_of_contents"
    assert out["dotted_leader_cleanup_scope_applied"] is True
    assert out["toc_index_entries"]


def test_exact_boilerplate_cleanup_preserves_semantic_content():
    text = """EMBRAER
MAINTENANCE MANUAL WITH
ILLUSTRATED PARTS LIST
INTRODUCTION
This manual includes an illustrated parts list.
DISASSEMBLY
25-IPL 1072 Jan 15/01
ASSEMBLY
EFFECTIVITY: ALL 25-21-00
Page 301
T.P. 120/1176 Sep 30/98
"""
    cleaned, operations = clean_boilerplate_and_dehyphenate(text)
    assert "This manual includes an illustrated parts list." in cleaned
    assert "DISASSEMBLY" in cleaned
    assert "25-IPL 1072 Jan 15/01" in cleaned
    assert "ASSEMBLY" in cleaned
    removals = [op for op in operations if op["operation"] == "remove_repeated_header_footer"]
    assert removals
    assert all(op["confirmed_boilerplate"] is True for op in removals)


def test_repeated_ipl_title_preserves_semantic_second_occurrence_and_cover_title():
    section = """MAINTENANCE MANUAL WITH
ILLUSTRATED PARTS LIST
ILLUSTRATED PARTS LIST
EFFECTIVITY: ALL 25-21-00
Page 1053
T.P. 120/1176 Sep 30/98
"""
    cover = """T.P. 120/1176
PASSENGER SEATS
COMPONENT MAINTENANCE MANUAL
WITH
ILLUSTRATED PARTS LIST
THIS PUBLICATION SUPERSEDES T.P. 120/1176
"""
    cleaned_section, _ = clean_boilerplate_and_dehyphenate(section)
    cleaned_cover, _ = clean_boilerplate_and_dehyphenate(cover)
    assert cleaned_section.count("ILLUSTRATED PARTS LIST") == 1
    assert "COMPONENT MAINTENANCE MANUAL" in cleaned_cover
    assert "ILLUSTRATED PARTS LIST" in cleaned_cover


def test_revision_grid_requires_revision_specific_headers():
    revision = revision_grid_extraction(
        "RECORD OF TEMPORARY REVISIONS\nREV\nDATE\nINSERTED\nDATE\nREMOVED\nPAGE\nNUMBER\n",
        is_grid_route=True,
    )
    dpl = revision_grid_extraction(
        "FIG ITEM PART NUMBER NOMENCLATURE UNITS PER ASSY\n",
        is_grid_route=True,
    )
    assert revision["is_revision_grid"] is True
    assert revision["revision_grid_kind"] == "temporary_revision_record"
    assert dpl["is_revision_grid"] is False


def test_callouts_are_scoped_to_visual_routes_and_primary_duplicates_rejected():
    record = {
        "page_id": "p494",
        "primary_ocr_text": "VACUUM BAG Figure 604",
        "tesseract_supplemental_psm11_raw_text": "VACUUM BAG 10 A NEWLABEL",
    }
    nonvisual = build_cleanup_extraction({**record, "accepted_route": "normal_text"}, final_route="normal_text")
    visual = build_cleanup_extraction({**record, "accepted_route": "image_visual"}, final_route="image_visual")
    assert nonvisual["supplemental_callout_scope_applied"] is False
    assert nonvisual["filtered_supplemental_callout_candidates"] == []
    candidates = visual["filtered_supplemental_callout_candidates"]
    by_text = {candidate["candidate_text"]: candidate for candidate in candidates}
    assert by_text["VACUUM"]["candidate_status"] == "rejected_primary_duplicate"
    assert by_text["10"]["candidate_status"] == "retained"
    assert all(candidate["confirmed"] is False and candidate["source_truth"] is False for candidate in candidates)
    assert all(candidate["bounding_box"] is None for candidate in candidates)


def test_semantic_checker_tracks_exact_353_part_numbers_not_ata_footer_codes():
    baseline = [
        {
            "page_number": 1,
            "expected_coarse_route": "normal_text",
            "expected_subtype": "normal_text",
        }
    ]
    raw = "120-42547-019\nEFFECTIVITY: ALL 25-21-00\nPage 1\n"
    cleanup = build_cleanup_extraction(
        {"page_id": "p1", "primary_ocr_text": raw, "accepted_route": "normal_text"},
        final_route="normal_text",
    )
    result = evaluate_cleanup_semantics(
        [{
            "canonical_page_number": 1,
            "canonical_final_route": "normal_text",
            "ocr_sidecar_status": "present",
            "primary_ocr_text": raw,
            "cleanup_extraction": cleanup,
        }],
        baseline,
    )
    assert result["metrics"]["part_loss_pages"] == []


def test_semantic_checker_passes_clean_synthetic_records():
    baseline = [
        {"page_number": 1, "expected_coarse_route": "table", "expected_subtype": "table_of_contents"},
        {"page_number": 2, "expected_coarse_route": "table", "expected_subtype": "list_of_effective_pages"},
        {"page_number": 3, "expected_coarse_route": "table", "expected_subtype": "revision_or_service_record"},
        {"page_number": 4, "expected_coarse_route": "image_visual", "expected_subtype": "image_visual_diagram"},
        {"page_number": 5, "expected_coarse_route": "blank_candidate", "expected_subtype": "blank_candidate"},
    ]
    samples = {
        1: ("table", "TABLE OF CONTENTS\nSubject Page\nA .... 1\nB .... 2\nC .... 3\n", "present"),
        2: ("table", "CHAPTER\nSECTION\nSUBJECT PAGE DATE\n25-IPL 1 Jan 1/01\n25-IPL 2 Jan 1/01\n25-IPL 3 Jan 1/01\n", "present"),
        3: ("table", "RECORD OF REVISIONS\nREV\nDATE\nINSERTED\n", "present"),
        4: ("image_visual", "Figure 1\nLABEL A\n", "present"),
        5: ("blank_candidate", "", "missing"),
    }
    records = []
    for page, (route, text, sidecar) in samples.items():
        cleanup = build_cleanup_extraction({"page_id": f"p{page}", "primary_ocr_text": text, "accepted_route": route}, final_route=route)
        records.append({
            "canonical_page_number": page,
            "canonical_final_route": route,
            "ocr_sidecar_status": sidecar,
            "primary_ocr_text": text,
            "cleanup_extraction": cleanup,
        })
    result = evaluate_cleanup_semantics(records, baseline)
    assert result["quality_status"] == "PASS", result
