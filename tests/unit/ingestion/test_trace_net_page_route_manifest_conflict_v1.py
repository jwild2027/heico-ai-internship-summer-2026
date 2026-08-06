"""Patch 4.1 — final routing-conflict correction (manifest scoring only).

Reproduces the measured conflict groups and pins the required signal policy:
- a high-confidence text-structural table stays primary even with a figure;
- validated ink ruling-grid geometry keeps a mislabeled parts list as table;
- validated ink diagram geometry keeps a diagram page as image;
- human_review is a gating signal and never adds image-route score;
- scan-pack/ink agreement corroborates the shared route over marginal evidence;
- conflicting evidence still yields exactly one traceable final route;
- the read-only safety contract is preserved.
No OCR/PSM/blank/fishnet changes here.
"""
from pathlib import Path

from tiff.trace_net_page_route_manifest_v1 import build_route_card

DETECTOR = Path("artifact_detector.json")


def _source(n=10):
    return {"source_page_id": f"metadata_page_{n:06d}", "page_number": n, "image_filename": f"{n:08d}.tif"}


def _evi(page_id, *, table=0, image=0, ocr=0, human_review=0, keys=None):
    return {
        "page_id": page_id, "artifact_count": table + image + ocr,
        "safe_artifact_count": table + image + ocr, "unsafe_artifact_count": 0,
        "artifact_keys": keys or [], "evidence_category_counts": {},
        "table_evidence_artifact_count": table, "image_visual_evidence_artifact_count": image,
        "ocr_text_evidence_artifact_count": ocr, "human_review_evidence_artifact_count": human_review,
    }


def _ink(**kw):
    base = {"page_id": "t_p_doc_p000010", "source_page_id": "metadata_page_000010", "page_number": 10,
            "ink_route_evidence_status": "INK_ROUTE_EVIDENCE_BUILT", "ink_primary_route": "",
            "table_grid_likelihood": 0.0, "diagram_likelihood": 0.0, "text_likelihood": 0.0,
            "blank_likelihood": 0.0, "horizontal_line_count": 0, "vertical_line_count": 0, "intersection_count": 0}
    base.update(kw)
    return base


def test_high_conf_structural_table_stays_primary_over_diagram_evidence():
    # Group A shape: a DPL with repeated rows plus an exploded-view figure.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", image=2, ocr=1, keys=["visual_diagram", "callout"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="table", table_grid_likelihood=0.6, diagram_likelihood=0.3),
        scan_pack_card={"accepted_route": "table", "route_confidence": 0.85,
                        "route_reasons": ["table_structural_rows:8"]},
    )
    assert card["final_route"] == "table", card["route_scores"]
    assert "image_visual" in card["secondary_routes"]


def test_validated_ink_ruling_grid_keeps_mislabeled_parts_list_as_table():
    # Group A real shape: scan pack mislabeled image, but ink has a ruling grid.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=0, keys=["metadata_zip"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="table", table_grid_likelihood=0.82,
                      horizontal_line_count=5, vertical_line_count=7, intersection_count=32),
        scan_pack_card={"accepted_route": "image_visual", "route_confidence": 0.71,
                        "route_reasons": ["dispersed_callouts_visual:12"]},
    )
    assert card["final_route"] == "table", card["route_scores"]


def test_validated_ink_diagram_with_caption_prose_is_image_primary():
    # Group C shape: strong diagram ink + caption prose scan-pack normal_text.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=1, keys=["source_ingest"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="image_visual", diagram_likelihood=1.0, text_likelihood=1.0),
        scan_pack_card={"accepted_route": "normal_text", "route_confidence": 0.55,
                        "route_reasons": ["normal_text_ocr_density"]},
    )
    assert card["final_route"] == "image_visual", card["route_scores"]
    assert "normal_text" in card["secondary_routes"]


def test_strong_normal_prose_with_human_review_stays_normal():
    # Group B shape: strong prose + human-review artifact + a false image count.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", image=3, ocr=3, human_review=3, keys=["human_review_queue"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="normal_text", text_likelihood=1.0, diagram_likelihood=0.2,
                      horizontal_line_count=22, vertical_line_count=0, intersection_count=0),
        scan_pack_card={"accepted_route": "normal_text", "route_confidence": 0.9,
                        "route_reasons": ["descriptive_prose_over_table_vocab"]},
    )
    assert card["final_route"] == "normal_text", card["route_scores"]


def test_human_review_presence_alone_does_not_add_image_score():
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=2, human_review=4, keys=["human_review_queue", "human_review_triage"])],
        DETECTOR,
        scan_pack_card={"accepted_route": "normal_text", "route_confidence": 0.9, "route_reasons": ["strong_prose"]},
    )
    assert card["image_visual_score"] == 0.0
    assert card["final_route"] != "image_visual"


def test_conflicting_evidence_yields_one_traceable_final_route():
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", image=2, keys=["visual_diagram"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="table", table_grid_likelihood=0.82,
                      horizontal_line_count=5, vertical_line_count=7, intersection_count=32),
        scan_pack_card={"accepted_route": "normal_text", "route_confidence": 0.6, "route_reasons": ["normal_text_ocr_density"]},
    )
    assert isinstance(card["final_route"], str) and card["final_route"]
    assert card["final_route"] == card["primary_route"]
    assert isinstance(card["secondary_routes"], list)


def test_safety_contract_preserved_under_conflict():
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", image=2, keys=["visual_diagram"])],
        DETECTOR, ink_card=_ink(ink_primary_route="image_visual", diagram_likelihood=1.0),
        scan_pack_card={"accepted_route": "table", "route_confidence": 0.5,
                        "route_reasons": ["table_supporting_only_no_structure_candidate"]},
    )
    assert card["answer_permission"] is False
    assert card["can_prove_claims"] is False
    assert card["source_truth_mutation_allowed"] is False
    assert card["source_truth_mutations_performed"] == 0
