"""Patch 3 reproduction — the scan pack must not auto-route to table from text
volume alone. Part numbers, numeric density, and table vocabulary are SUPPORTING
signals; a confident table needs a text-structural cue (repeated columnar rows).
Strong prose beats unsupported table vocabulary; dispersed diagram callouts
strengthen image_visual, never table. Blank detection is unchanged.

Geometry-based authority (fishnet word-boxes, table-line ruling) is deferred to
Patch 4; this gate is text-only and does not duplicate those algorithms.
"""
from tiff.trace_net_ocr_route_scan_pack_v1 import _classify_route

FEATS = {"ink_ratio_estimate": 0.05}


def route(text, ink=0.05):
    r, conf, reasons = _classify_route(
        text=text, image_features={"ink_ratio_estimate": ink}, tesseract_status="ok"
    )
    return r, conf, reasons


def test_diagram_with_scattered_numeric_callouts_is_image_visual():
    text = "Figure 2 Sheet 1\n1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21"
    r, _, reasons = route(text)
    assert r == "image_visual", reasons


def test_exploded_view_with_two_part_numbers_is_not_table():
    text = ("Figure 3 Sheet 2\nSEAT ASSEMBLY\n1 2 3 4 5 6 7 8 9 10 11 12\n"
            "120-41824-001 120-41825-001 13 14 15 16 17")
    r, _, reasons = route(text)
    assert r != "table", reasons
    assert r == "image_visual", reasons


def test_procedure_prose_with_figures_and_parts_is_normal_text():
    # Reproduces the page-478 defect: procedure prose mentioning parts/figures.
    text = (
        "C. Triple Passenger Seat Leg Replacement (figure 610).\n"
        "(1) Remove the four bolts and discard the old leg structure.\n"
        "(2) Install the new leg structure (P/N 120-29074-005) and torque to specification.\n"
        "(3) Adjust the baggage protector (P/N 120-34292-001) as necessary before riveting.\n"
        "(4) Apply the preformed seal with adhesive and finish the reworked region."
    )
    r, _, reasons = route(text)
    assert r == "normal_text", reasons


def test_dense_dpl_with_aligned_columns_is_table():
    text = (
        "ITEM PART NUMBER NOMENCLATURE QTY\n"
        "1 120-41824-001 SEAT ASSEMBLY 1\n"
        "2 120-41825-001 BACKREST 2\n"
        "3 120-36833-001 CUSHION 1\n"
        "4 120-36833-003 ARMREST 2\n"
        "5 120-29073-006 STRUCTURE 4\n"
    )
    r, _, reasons = route(text)
    assert r == "table", reasons


def test_numerical_index_with_repeated_rows_is_table():
    text = (
        "120-41824-001 82\n120-41825-001 84\n120-36833-001 90\n"
        "120-36833-003 91\n120-29073-006 120\n120-50645-005 133\n"
    )
    r, _, reasons = route(text)
    assert r == "table", reasons


def test_sparse_title_page_is_not_table():
    text = "PASSENGER SEATS\nCOMPONENT MAINTENANCE MANUAL\nWITH ILLUSTRATED PARTS LIST\n25-21-00"
    r, _, reasons = route(text)
    assert r != "table", reasons


def test_mixed_table_and_diagram_defers_to_validator():
    text = (
        "Figure 5 Sheet 1\n1 2 3 4 5 6 7 8 9 10\n"
        "ITEM PART NUMBER QTY\n1 120-41824-001 1\n2 120-41825-001 2\n"
    )
    r, conf, reasons = route(text)
    assert any("mixed" in c or "validator" in c or "candidate" in c for c in reasons), reasons


def test_blank_behavior_is_unchanged():
    r, conf, reasons = _classify_route(
        text="", image_features={"ink_ratio_estimate": 0.0}, tesseract_status="ok"
    )
    assert r == "blank_candidate"


def test_supporting_table_signals_without_structure_are_not_confident_table():
    # Two part numbers in otherwise-prose text: not a confident structural table.
    text = ("The assembly uses part 120-41824-001 together with part 120-41825-001 "
            "as described in the general operation section for this passenger seat unit.")
    r, conf, reasons = route(text)
    assert r != "table" or conf < 0.6, (r, conf, reasons)
