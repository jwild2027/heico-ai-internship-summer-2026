"""Patch 4.2 — general index/TOC/vendor structure and sparse-diagram signals in
the scan-pack text classifier. No page-number conditions: every assertion is a
general, testable signal policy.

- Repeated vendor-code+name rows or subject+dotted-leader+page rows authorize the
  table/index route (columnar without visible ruling).
- Ordinary prose containing dates/addresses/numbers must NOT become a table.
- A figure/drawing title with prose-poor body and strong PSM3/PSM11 disagreement
  authorizes image_visual; PSM 11 labels stay candidates only.
- Strong procedural prose stays normal_text; a noisy-but-prose page (high PSM
  agreement) does not flip to image_visual.
"""
from tiff.trace_net_ocr_route_scan_pack_v1 import _classify_route

FEATS = {"ink_ratio_estimate": 0.05}


def route(text, supplemental=None, ink=0.05):
    return _classify_route(
        text=text, image_features={"ink_ratio_estimate": ink},
        tesseract_status="ok", supplemental=supplemental,
    )


VENDOR_INDEX = """VENDORS' NAMES AND ADDRESSES
VENDOR CODE     NAMES AND ADDRESSES
E065846   AEROMOT INDUSTRIA MECANICA METALURGICA LTDA
AV. DAS INDUSTRIAS, 1210
E075221   COMERIT COMPANHIA MERCANTIL E INDUSTRIAL ENGELBRECHT
AV. GONCALO MADEIRA, 220
V15653    KAYNAR MICRODOT COMPANY
800 S. STATE COLLEGE BOULEVARD
VS4956    EMBRAER EMPRESA BRASILEIRA DE AERONAUTICA S.A
AV. BRIGADEIRO FARIA LIMA, 2170
"""

TOC_LEADERS = """TABLE OF CONTENTS
Subject                                                        Page
- Applicability ................................................. i
- Introduction .................................................. 1
- Description and Operation ..................................... 1
- Tests and Fault Isolation .................................... 101
- Automatic Test Requirements ....................... NOT APPLICABLE
- Disassembly .................................................. 301
- Cleaning .................................................... 401
"""

PROCEDURE = """Remove the damaged plies from laminates and sandwich structure areas using No. 80
sandpaper, fine abrasive, or trim out the damaged surface, keeping a geometric shape.
Mark the area to receive the repair layers with adhesive tape, leaving 1-in margin.
Lightly sand the surface within the marked area, so as to achieve a good adhesion.
NOTE: Allow the solvent to evaporate for a few minutes before proceeding.
Install a vacuum line over the top bleeder cloth outside the repair area.
Apply extruded sealing compound all around the area on 15 March 2021 at 220 psi.
"""

PROSE_WITH_NUMBERS = """The unit was inspected on 15 March 2021 and shipped to 800 State College
Boulevard, Fullerton, California 92634. The assembly weighs 220 grams and operates
between 101 and 301 degrees. Contact the vendor at (714) 871-1550 for details about
the replacement schedule and the applicable service bulletins issued during 1998.
"""

DIAGRAM_CAPTION = """Determination of Damage
Figure 602
Sheet 1
120TP250005.MCE
SECTION A-A
"""


def test_vendor_index_rows_route_table():
    r, conf, reasons = route(VENDOR_INDEX)
    assert r == "table", (r, reasons)
    assert any(s.startswith("index_structural_rows") for s in reasons)


def test_toc_dotted_leader_rows_route_table():
    r, conf, reasons = route(TOC_LEADERS)
    assert r == "table", (r, reasons)
    assert any(s.startswith("index_structural_rows") for s in reasons)


def test_ordinary_prose_with_numbers_is_not_table():
    r, conf, reasons = route(PROSE_WITH_NUMBERS)
    assert r == "normal_text", (r, reasons)
    assert not any(s.startswith("index_structural_rows") for s in reasons)


def test_procedure_prose_stays_normal_text():
    r, conf, reasons = route(PROCEDURE)
    assert r == "normal_text", (r, reasons)


def test_sparse_diagram_with_psm_disagreement_routes_image():
    supp = {"psm11_unique_token_count": 42, "psm3_psm11_agreement": 0.33, "psm11_word_count": 60}
    r, conf, reasons = route(DIAGRAM_CAPTION, supplemental=supp)
    assert r == "image_visual", (r, reasons)
    assert any(s.startswith("diagram_sparse_callouts") for s in reasons)


def test_diagram_signal_requires_psm11_disagreement():
    # Same sparse caption but PSM 11 agrees with PSM 3 (no extra callouts): must
    # NOT be called a diagram from the caption alone.
    supp = {"psm11_unique_token_count": 1, "psm3_psm11_agreement": 0.95, "psm11_word_count": 6}
    r, conf, reasons = route(DIAGRAM_CAPTION, supplemental=supp)
    assert r != "image_visual" or not any(s.startswith("diagram_sparse_callouts") for s in reasons)


def test_noisy_psm11_on_prose_page_does_not_become_diagram():
    # A prose page (no figure title) with noisy PSM 11 output must not flip.
    supp = {"psm11_unique_token_count": 40, "psm3_psm11_agreement": 0.30, "psm11_word_count": 80}
    r, conf, reasons = route(PROSE_WITH_NUMBERS, supplemental=supp)
    assert r == "normal_text", (r, reasons)


def test_diagram_signal_noop_without_supplemental():
    # Without cross-PSM evidence the diagram signal never fires (back-compatible).
    r, conf, reasons = route(DIAGRAM_CAPTION, supplemental=None)
    assert not any(s.startswith("diagram_sparse_callouts") for s in reasons)


def test_structural_table_still_beats_index_and_diagram():
    table = "\n".join(f"120-4182{i}-001  {200+i}  1" for i in range(6))
    r, conf, reasons = route(table)
    assert r == "table"
    assert any(s.startswith("table_structural_rows") for s in reasons)


# --- Real-OCR regression cases (calibrated from live Tesseract output) --------
IPL_TABLE_WITH_FIG_HEADER = """PART NUMBER UNITS AIRLINE
CH-SEC-UN-FIG | ITEM] ASSY NUMBER
25-21-00-10 80 2
25-21-00-11 70 2
25-21-00-12 80 2
25-21-00-13 80 2
25-21-00-14 80 2
"""

VENDOR_INDEX_SPLIT_COLUMNS = """VENDOR
CODE
E065846
E075221
V15653
VS4956
VENDORS' NAMES AND ADDRESSES
NAMES AND ADDRESSES
AEROMOT INDUSTRIA MECANICO METALURGICA LTDA.
"""

TOC_GARBLED_LEADERS = """TABLE OF CONTENTS
Subject Page
- Tests and Fault Isolation ...ccccccceeeeeeee 101
- Automatic Test REQUIFEMENTS ...cceeeeee NOT APPLICABLE
- Disassembly ...eeee 301
- Cleaning ...ee 401
- Check ...ee 501
"""


def test_ipl_table_with_fig_column_header_is_not_a_diagram_structure():
    # "CH-SEC-UN-FIG" merely contains FIG; a heavy PSM-11 disagreement must NOT emit
    # the diagram STRUCTURAL reason (which would earn the 0.82 manifest floor and beat
    # the ink-grid table recovery). The page-68 regression guard: no such reason here,
    # so the manifest's validated ink grid still recovers the parts table.
    supp = {"psm11_unique_token_count": 39, "psm3_psm11_agreement": 0.3, "psm11_word_count": 80}
    r, conf, reasons = route(IPL_TABLE_WITH_FIG_HEADER, supplemental=supp)
    assert not any(s.startswith("diagram_sparse_callouts") for s in reasons), (r, reasons)


def test_vendor_index_with_codes_on_own_lines_routes_table():
    r, conf, reasons = route(VENDOR_INDEX_SPLIT_COLUMNS)
    assert r == "table", (r, reasons)
    assert any(s.startswith("index_structural_rows") for s in reasons)


def test_toc_with_garbled_leaders_still_routes_table():
    r, conf, reasons = route(TOC_GARBLED_LEADERS)
    assert r == "table", (r, reasons)
    assert any(s.startswith("index_structural_rows") for s in reasons)
