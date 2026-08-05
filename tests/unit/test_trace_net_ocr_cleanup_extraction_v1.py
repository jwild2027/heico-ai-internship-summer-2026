"""Patch 5 — OCR cleanup & extraction. Confirmed, additive, raw-preserving.

Covers: raw/cleaned separation, dotted-leader collapse + TOC/index parsing, PSM-11
callout candidate filtering (candidates only), revision-grid handling, flattened-
table row-association safety, and conservative boilerplate/dehyphenation cleanup.
Includes negative controls (ordinary prose must not be TOC-parsed or dehyphenated
across part numbers).
"""
from tiff.trace_net_ocr_cleanup_extraction_v1 import (
    CLEANUP_VERSION,
    clean_dotted_leaders,
    parse_toc_index_entries,
    filter_supplemental_callout_candidates,
    clean_boilerplate_and_dehyphenate,
    revision_grid_extraction,
    flat_table_row_association_contract,
    build_cleanup_extraction,
)

TOC_509 = """Subject                                                        Page
- Applicability ................................................. i
- Introduction .................................................. 1
- Automatic Test Requirements ....................... NOT APPLICABLE
- Disassembly .................................................. 301
"""

DPL_82 = """120-42660-001 . TABLE, SNACK FOLDING, ASSY .............. VS4956 1
120-29067-019 . STRUCTURE, ASSY. ...................... VS4956 A 1
120-33774-001 . LINING ASSY., SEAT BOTTOM ............. VS4956 1
"""

PROSE = """Remove the damaged plies from laminates and sandwich structure areas.
Mark the area to receive the repair layers with adhesive tape.
"""

PSM11_DIAGRAM = """EMBRAER
MAINTENANCE MANUAL
25-21-00
Page 1391
10 20 30 40 50 A B C
120-42547-019
SNACK ............ FOLDING
"""


# --- B. dotted leaders -------------------------------------------------------
def test_dotted_leaders_collapsed_preserving_label_and_page():
    cleaned, ops = clean_dotted_leaders(TOC_509)
    assert "....." not in cleaned
    assert "Applicability\ti" in cleaned
    assert "Disassembly\t301" in cleaned
    assert any(o["operation"] == "collapse_dotted_leader" for o in ops)


def test_toc_entries_parse_label_and_page_number():
    entries = parse_toc_index_entries(TOC_509)
    by_label = {e["label"].lstrip("- "): e for e in entries}
    assert by_label["Introduction"]["page_number"] == 1
    assert by_label["Applicability"]["page_number"] is None  # roman 'i' -> uncertain
    assert by_label["Applicability"]["uncertain"] is True
    assert by_label["Automatic Test Requirements"]["page_target"].upper() == "NOT APPLICABLE"


def test_dpl_nomenclature_leaders_collapsed_but_part_hyphens_kept():
    cleaned, ops = clean_dotted_leaders(DPL_82)
    assert "120-42660-001" in cleaned  # part-number hyphens intact
    assert "....." not in cleaned
    assert ops


def test_prose_periods_not_treated_as_leaders():
    cleaned, ops = clean_dotted_leaders(PROSE)
    assert ops == []  # no leader collapse on ordinary prose
    assert cleaned.rstrip("\n") == PROSE.rstrip("\n")  # content unchanged


def test_prose_is_not_toc_parsed():
    assert parse_toc_index_entries(PROSE) == []


# --- C. callout candidates ---------------------------------------------------
def test_callout_candidates_are_candidates_only():
    cands = filter_supplemental_callout_candidates(PSM11_DIAGRAM, "", page_id="p1391")
    assert cands, "expected candidates"
    assert all(c["confirmed"] is False and c["source_truth"] is False for c in cands)
    assert all(c["source_psm"] == 11 for c in cands)


def test_callout_filtering_rejects_boilerplate_keeps_numeric_labels():
    cands = filter_supplemental_callout_candidates(PSM11_DIAGRAM, "", page_id="p1391")
    retained = {c["candidate_text"] for c in cands if c["candidate_status"] == "retained"}
    rejected = {c["candidate_text"]: c for c in cands if c["candidate_status"] != "retained"}
    assert "10" in retained and "20" in retained and "A" in retained
    assert "EMBRAER" in rejected and rejected["EMBRAER"]["boilerplate_rejection_reason"]
    assert "25-21-00" in rejected  # ATA footer rejected
    assert "Page" in rejected


def test_callout_candidate_records_provenance_fields():
    cands = filter_supplemental_callout_candidates("120-42547-019", "", page_id="pX")
    c = cands[0]
    assert c["page_id"] == "pX"
    assert c["bounding_box"] is None
    assert c["filtering_reason"]


# --- F. boilerplate + dehyphenation -----------------------------------------
def test_boilerplate_headers_removed_in_derivative():
    text = "EMBRAER\nMAINTENANCE MANUAL WITH\nILLUSTRATED PARTS LIST\nReal content line here.\nEFFECTIVITY: ALL\nT.P. 120/1176\n"
    cleaned, ops = clean_boilerplate_and_dehyphenate(text)
    assert "Real content line here." in cleaned
    assert "EMBRAER" not in cleaned
    assert "ILLUSTRATED PARTS LIST" not in cleaned
    assert any(o["operation"] in ("remove_repeated_header_footer", "normalize_embraer_header") for o in ops)


def test_dehyphenation_joins_lowercase_continuation():
    text = "the sur-\nface around the damaged area\n"
    cleaned, ops = clean_boilerplate_and_dehyphenate(text)
    assert "surface around the damaged area" in cleaned
    assert any(o["operation"] == "join_linebreak_hyphen" for o in ops)


def test_dehyphenation_never_joins_part_number_hyphen():
    text = "120-\n42660-001 SNACK FOLDING\n"
    cleaned, ops = clean_boilerplate_and_dehyphenate(text)
    # next line starts with a digit (uppercase-ish), not a lowercase continuation
    assert "12042660-001" not in cleaned
    assert not any(o["operation"] == "join_linebreak_hyphen" for o in ops)


# --- D. revision grid --------------------------------------------------------
def test_revision_grid_preserves_headers_no_invention():
    grid = revision_grid_extraction("RECORD OF TEMPORARY REVISIONS\nREV No. DATE INSERTED\n", is_grid_route=True)
    assert grid["is_revision_grid"] is True
    assert grid["invented_cell_text"] is False
    assert grid["empty_cells_preserved_as_uncertain"] is True
    assert grid["psm6_grid_noise_promoted"] is False


# --- E. flattened-table safety ----------------------------------------------
def test_flat_table_row_association_forbidden_when_only_flattened():
    c = flat_table_row_association_contract(has_reconstructed_rows=False)
    assert c["flat_text_row_association_forbidden"] is True
    assert c["row_relationship_usable"] is False
    assert c["proves_item_part_nomenclature_quantity"] is False
    assert c["searchable_flat_text_allowed"] is True


def test_row_usable_only_with_reconstruction():
    c = flat_table_row_association_contract(has_reconstructed_rows=True)
    assert c["flat_text_row_association_forbidden"] is False
    assert c["row_relationship_usable"] is True
    assert "coordinates" in c["required_fields_for_row_usability"]


# --- A. top-level additive builder ------------------------------------------
def _record(**kw):
    base = {
        "page_id": "t_p_120_1176_p000509",
        "ocr_sample_text": TOC_509,
        "tesseract_supplemental_psm11_raw_text": PSM11_DIAGRAM,
        "accepted_route": "table",
    }
    base.update(kw)
    return base


def test_build_cleanup_preserves_raw_and_adds_cleaned():
    rec = _record()
    out = build_cleanup_extraction(rec, final_route="table")
    assert out["cleanup_version"] == CLEANUP_VERSION
    assert out["raw_ocr_text"] == TOC_509  # raw preserved byte-for-byte
    assert out["raw_psm11_supplemental_text"] == PSM11_DIAGRAM
    assert out["cleaned_ocr_text"] != TOC_509  # derivative differs
    assert out["is_index_or_toc"] is True
    assert out["toc_index_entries"]
    assert out["retained_callout_candidate_count"] >= 1
    assert out["supplemental_callouts_confirmed"] is False


def test_build_cleanup_safety_contract():
    out = build_cleanup_extraction(_record(), final_route="table")
    assert out["answer_permission"] is False
    assert out["can_prove_claims"] is False
    assert out["source_truth_mutation_allowed"] is False
    assert out["source_truth_mutations_performed"] == 0
    assert out["postgres_write_attempt_count"] == 0
    assert out["qdrant_write_attempt_count"] == 0
    assert out["opensearch_write_attempt_count"] == 0
    assert out["flat_text_row_association_forbidden"] is True


def test_build_cleanup_does_not_mutate_input_record():
    rec = _record()
    import copy
    snapshot = copy.deepcopy(rec)
    build_cleanup_extraction(rec, final_route="table")
    assert rec == snapshot  # input untouched


def test_build_cleanup_prose_route_has_no_toc_entries():
    rec = _record(ocr_sample_text=PROSE, accepted_route="normal_text")
    out = build_cleanup_extraction(rec, final_route="normal_text")
    assert out["toc_index_entries"] == []
    assert out["is_index_or_toc"] is False
    assert out["raw_ocr_text"] == PROSE
