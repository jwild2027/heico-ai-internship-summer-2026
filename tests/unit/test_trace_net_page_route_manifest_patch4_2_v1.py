"""Patch 4.2 — manifest honors index/diagram structural scan-pack routes and
protects validated procedure prose from ink-only overrides.

- An index/TOC/vendor structural scan-pack route gets a strong table floor that
  beats marginal image artifact evidence.
- A sparse-diagram structural scan-pack route gets a strong image floor that beats
  ink text-density boosts.
- Validated procedure prose (confident normal_text + strong-prose reason) is not
  flipped by ink-only diagram/grid marks unless artifact image/table evidence
  corroborates it.
- Ink geometry is NOT disabled globally: a non-procedure parts-list is still
  recovered as table by validated ink grid.
- Safety/authority contract preserved.
"""
from pathlib import Path

from tiff.trace_net_page_route_manifest_v1 import build_route_card

DETECTOR = Path("artifact_detector.json")


def _source(n=10):
    return {"source_page_id": f"metadata_page_{n:06d}", "page_number": n, "image_filename": f"{n:08d}.tif"}


def _evi(page_id, *, table=0, image=0, ocr=0, keys=None):
    return {
        "page_id": page_id, "artifact_count": table + image + ocr,
        "safe_artifact_count": table + image + ocr, "unsafe_artifact_count": 0,
        "artifact_keys": keys or [], "evidence_category_counts": {},
        "table_evidence_artifact_count": table, "image_visual_evidence_artifact_count": image,
        "ocr_text_evidence_artifact_count": ocr,
    }


def _ink(**kw):
    base = {"page_id": "t_p_doc_p000010", "source_page_id": "metadata_page_000010", "page_number": 10,
            "ink_route_evidence_status": "INK_ROUTE_EVIDENCE_BUILT", "ink_primary_route": "",
            "table_grid_likelihood": 0.0, "diagram_likelihood": 0.0, "text_likelihood": 0.0,
            "blank_likelihood": 0.0, "horizontal_line_count": 0, "vertical_line_count": 0, "intersection_count": 0}
    base.update(kw)
    return base


def test_index_structural_scan_pack_route_beats_marginal_image_evidence():
    # p24 shape: vendor index; artifact detector has some image evidence, ink says
    # text. The index structural route must win as table.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", table=2, image=3, ocr=3, keys=["vendor_list", "figure_chart_understanding", "callout_visual_part_verifier"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="normal_text", text_likelihood=1.0, diagram_likelihood=0.05),
        scan_pack_card={"accepted_route": "table", "route_confidence": 0.85,
                        "route_reasons": ["index_structural_rows:4:vendor_index"]},
    )
    assert card["final_route"] == "table", card["route_scores"]
    assert card["scan_pack_route_integration"]["resolution"] == "adopted_index_structural_table"


def test_sparse_diagram_scan_pack_route_beats_ink_text_density():
    # p492 shape: sparse diagram; no artifact evidence; ink text_likelihood high
    # (dashed hatching). The diagram structural route must win as image.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", keys=["metadata_zip"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="normal_text", text_likelihood=1.0, diagram_likelihood=0.55),
        scan_pack_card={"accepted_route": "image_visual", "route_confidence": 0.85,
                        "route_reasons": ["diagram_sparse_callouts_psm_disagreement:42"]},
    )
    assert card["final_route"] == "image_visual", card["route_scores"]
    assert card["scan_pack_route_integration"]["resolution"] == "adopted_sparse_diagram_image"


def test_procedure_prose_not_flipped_by_ink_diagram_without_image_evidence():
    # p476/p480 shape: strong procedure prose; ink diagram >= 0.70 from page marks;
    # NO artifact image evidence -> stays normal_text.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=0, keys=["seat_bottom_backrest"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="image_visual", diagram_likelihood=0.75, text_likelihood=1.0,
                      horizontal_line_count=15, vertical_line_count=0, intersection_count=0),
        scan_pack_card={"accepted_route": "normal_text", "route_confidence": 0.95,
                        "route_reasons": ["strong_prose_over_table_vocab"]},
    )
    assert card["final_route"] == "normal_text", card["route_scores"]
    assert card["scan_pack_route_integration"]["validated_ink_geometry"]["ink_diagram_override_suppressed"] is True


def test_procedure_prose_not_flipped_by_ink_grid_without_table_evidence():
    # p483 shape: strong procedure prose; ink ruling grid >= 0.70; NO artifact table
    # evidence -> stays normal_text.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=0, keys=["source_ingest"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="table", table_grid_likelihood=0.87, text_likelihood=0.75,
                      horizontal_line_count=24, vertical_line_count=5, intersection_count=87),
        scan_pack_card={"accepted_route": "normal_text", "route_confidence": 0.95,
                        "route_reasons": ["strong_prose_over_table_vocab"]},
    )
    assert card["final_route"] == "normal_text", card["route_scores"]
    assert card["scan_pack_route_integration"]["validated_ink_geometry"]["ink_table_grid_override_suppressed"] is True


def test_procedure_plus_real_image_evidence_can_retain_image_secondary():
    # A real mixed procedure+figure page (artifact image evidence present) allows the
    # ink diagram override; image_visual is at least a secondary route.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", image=3, ocr=1, keys=["visual_diagram", "callout"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="image_visual", diagram_likelihood=0.8, text_likelihood=1.0),
        scan_pack_card={"accepted_route": "normal_text", "route_confidence": 0.95,
                        "route_reasons": ["strong_prose_over_table_vocab"]},
    )
    integ = card["scan_pack_route_integration"]["validated_ink_geometry"]
    assert integ.get("ink_diagram_override_suppressed") is not True
    assert "image_visual" in ([card["final_route"]] + card["secondary_routes"])


def test_non_procedure_parts_list_still_recovered_by_ink_grid():
    # Patch-4.1 recovery must survive: a scan-pack table candidate (NOT procedure
    # prose) with a validated ink ruling grid still routes table.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=0, keys=["metadata_zip"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="table", table_grid_likelihood=0.82,
                      horizontal_line_count=5, vertical_line_count=7, intersection_count=32),
        scan_pack_card={"accepted_route": "image_visual", "route_confidence": 0.71,
                        "route_reasons": ["visual_keywords_with_limited_text"]},
    )
    assert card["final_route"] == "table", card["route_scores"]


def test_dispersed_image_with_ink_grid_recovers_table_not_diagram_floor():
    # Page-68 shape: a dense parts table whose scan-pack route is a confident
    # dispersed-callout image (NOT a diagram STRUCTURAL reason), plus a validated ink
    # ruling grid. The dispersed image gets only the 0.60 floor, so the ink-grid table
    # recovery (0.80) wins -> table (no 0.82 diagram-structural floor to block it).
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=0, keys=["metadata_zip"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="table", table_grid_likelihood=0.9,
                      horizontal_line_count=8, vertical_line_count=31, intersection_count=237),
        scan_pack_card={"accepted_route": "image_visual", "route_confidence": 0.85,
                        "route_reasons": ["dispersed_callouts_visual:10"]},
    )
    assert card["final_route"] == "table", card["route_scores"]


def test_safety_contract_preserved_patch4_2():
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=1, keys=["source_ingest"])],
        DETECTOR,
        scan_pack_card={"accepted_route": "table", "route_confidence": 0.85,
                        "route_reasons": ["index_structural_rows:5:toc_leader_index"]},
    )
    assert card["final_route"] == card["primary_route"]
    assert card["final_route_authority"] == "trace_net_page_route_manifest_v1"
    assert card["answer_permission"] is False
    assert card["can_prove_claims"] is False
    assert card["source_truth_mutation_allowed"] is False
    assert card["source_truth_mutations_performed"] == 0
