"""Patch 4 — the page route manifest is the single final-route authority.

It integrates the upstream OCR scan-pack route as a CANDIDATE signal and resolves
Patch-3 low-confidence table candidates against actual geometry (table-line
geometry artifact or a strong ink ruling grid). Conflicting upstream signals must
collapse to exactly one traceable final decision, preserving secondary routes,
validator gating, reason codes, and the read-only safety contract.
"""
from pathlib import Path

from tiff.trace_net_page_route_manifest_v1 import build_route_card

DETECTOR = Path("artifact_detector.json")


def _source(n=10):
    return {"source_page_id": f"metadata_page_{n:06d}", "page_number": n, "image_filename": f"{n:08d}.tif"}


def _evi(page_id, *, table=0, image=0, ocr=0, keys=None):
    return {
        "page_id": page_id,
        "artifact_count": table + image + ocr,
        "safe_artifact_count": table + image + ocr,
        "unsafe_artifact_count": 0,
        "artifact_keys": keys or [],
        "evidence_category_counts": {},
        "table_evidence_artifact_count": table,
        "image_visual_evidence_artifact_count": image,
        "ocr_text_evidence_artifact_count": ocr,
    }


def _ink(**kw):
    base = {"page_id": "t_p_doc_p000010", "source_page_id": "metadata_page_000010", "page_number": 10,
            "ink_route_evidence_status": "INK_ROUTE_EVIDENCE_BUILT", "ink_primary_route": "",
            "table_grid_likelihood": 0.0, "diagram_likelihood": 0.0, "text_likelihood": 0.0,
            "blank_likelihood": 0.0, "horizontal_line_count": 0, "vertical_line_count": 0, "intersection_count": 0}
    base.update(kw)
    return base


CANDIDATE = {"accepted_route": "table", "route_confidence": 0.5,
             "route_reasons": ["table_supporting_only_no_structure_candidate"]}


def test_table_line_geometry_presence_alone_does_not_confirm_candidate():
    # The table_line_geometry artifact key is presence-only/unvalidated: it must
    # NOT trigger the Patch-4 candidate confirmation path (only validated ink grid
    # does). It is still reported for transparency.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=1, keys=["table_line_geometry"])],
        DETECTOR, scan_pack_card=CANDIDATE,  # no ink grid
    )
    integ = card["scan_pack_route_integration"]
    assert integ["resolution"] == "table_candidate_unconfirmed_deferred"
    assert integ["table_line_geometry_artifact_present_unvalidated"] is True
    assert integ.get("geometry_source") is None
    assert "scan_pack_table_candidate_confirmed_by_geometry" not in card["routing_reasons"]


def test_table_candidate_confirmed_by_strong_ink_grid():
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=1, keys=["source_ingest"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="table", table_grid_likelihood=0.9,
                      horizontal_line_count=9, vertical_line_count=6, intersection_count=120),
        scan_pack_card=CANDIDATE,
    )
    assert card["final_route"] == "table"
    assert card["scan_pack_route_integration"]["table_geometry_present"] is True


def test_table_candidate_without_geometry_is_not_forced_table():
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=2, keys=["source_ingest"])],
        DETECTOR, scan_pack_card=CANDIDATE,  # no table artifact, no ink grid
    )
    assert card["final_route"] != "table"
    assert "scan_pack_table_candidate_unconfirmed_no_geometry" in card["routing_reasons"]
    assert card["scan_pack_route_integration"]["resolution"] == "table_candidate_unconfirmed_deferred"


def test_conflicting_signals_collapse_to_one_traceable_final_decision():
    # scan pack says table-candidate; artifact + ink both say image; no table geometry.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", image=2, keys=["visual_diagram", "callout"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="image_visual", diagram_likelihood=0.9),
        scan_pack_card=CANDIDATE,
    )
    # Exactly one final route, and it is fully traceable.
    assert isinstance(card["final_route"], str) and card["final_route"]
    assert card["final_route"] == card["primary_route"]
    assert card["final_route"] != "table"  # unconfirmed candidate did not win
    integ = card["scan_pack_route_integration"]
    assert integ["scan_pack_route"] == "table" and integ["is_low_confidence_table_candidate"] is True
    assert integ["table_geometry_present"] is False
    assert isinstance(card["secondary_routes"], list)


def test_confident_scan_pack_route_lends_bounded_signal():
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", image=1, keys=["visual_diagram"])],
        DETECTOR,
        scan_pack_card={"accepted_route": "image_visual", "route_confidence": 0.9,
                        "route_reasons": ["visual_keywords_with_limited_text"]},
    )
    assert "scan_pack_route_signal_image_visual" in card["routing_reasons"]
    assert card["scan_pack_route_integration"]["resolution"] == "adopted_image_visual"


def test_final_route_authority_and_safety_contract_preserved():
    card = build_route_card(_source(), [_evi("t_p_doc_p000010", ocr=2)], DETECTOR, scan_pack_card=CANDIDATE)
    assert card["final_route_authority"] == "trace_net_page_route_manifest_v1"
    assert card["final_route"] == card["primary_route"]
    assert card["answer_permission"] is False
    assert card["can_prove_claims"] is False
    assert card["source_truth_mutation_allowed"] is False


def test_final_route_provenance_is_the_manifest_not_the_scan_pack_classifier():
    # The raw scan-pack classifier (_classify_route) emitted a TABLE candidate.
    # The manifest is the authority: with geometry it CONFIRMS table; without
    # geometry it OVERRIDES the raw candidate to non-table. Either way the final
    # decision + authority come from the manifest, not from _classify_route.
    with_geo = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=1, keys=["source_ingest"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="table", table_grid_likelihood=0.9,
                      horizontal_line_count=9, vertical_line_count=6, intersection_count=120),
        scan_pack_card=CANDIDATE,
    )
    without_geo = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=2, keys=["source_ingest"])],
        DETECTOR, scan_pack_card=CANDIDATE,
    )
    # Same raw scan-pack candidate ("table"), different manifest final routes:
    assert with_geo["scan_pack_route_integration"]["scan_pack_route"] == "table"
    assert without_geo["scan_pack_route_integration"]["scan_pack_route"] == "table"
    assert with_geo["final_route"] == "table"          # geometry confirmed
    assert without_geo["final_route"] != "table"        # manifest overrode raw candidate
    for card in (with_geo, without_geo):
        assert card["final_route_authority"] == "trace_net_page_route_manifest_v1"
        assert card["final_route"] == card["primary_route"]


def test_scan_pack_text_does_not_overpower_strong_diagram_evidence():
    # scan pack says normal_text (confident) but artifact + ink both say image.
    card = build_route_card(
        _source(),
        [_evi("t_p_doc_p000010", image=3, ocr=1, keys=["visual_diagram", "callout", "figure_chart_understanding"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="image_visual", diagram_likelihood=0.95),
        scan_pack_card={"accepted_route": "normal_text", "route_confidence": 0.9,
                        "route_reasons": ["normal_text_ocr_density"]},
    )
    assert card["final_route"] == "image_visual", card["route_scores"]


def test_scan_pack_image_yields_to_strong_ruled_table_geometry():
    # scan pack says image_visual (confident) but a ruled-table geometry is present.
    card = build_route_card(
        _source(),
        [_evi("t_p_doc_p000010", table=3, ocr=1, keys=["table_line_geometry", "table_full_region_recovery"])],
        DETECTOR,
        ink_card=_ink(ink_primary_route="table", table_grid_likelihood=0.95,
                      horizontal_line_count=12, vertical_line_count=9, intersection_count=180),
        scan_pack_card={"accepted_route": "image_visual", "route_confidence": 0.9,
                        "route_reasons": ["visual_keywords_with_limited_text"]},
    )
    assert card["final_route"] == "table", card["route_scores"]


def test_scan_pack_table_candidate_without_geometry_yields_to_prose():
    # scan pack table candidate, no geometry: must resolve to text, not table.
    card = build_route_card(
        _source(), [_evi("t_p_doc_p000010", ocr=2, keys=["source_ingest"])],
        DETECTOR, scan_pack_card=CANDIDATE,
    )
    assert card["final_route"] == "normal_text", card["route_scores"]


def test_manifest_works_without_scan_pack_card_backward_compatible():
    card = build_route_card(_source(), [_evi("t_p_doc_p000010", table=2, keys=["table_line_geometry"])], DETECTOR)
    assert card["final_route"] == card["primary_route"]
    assert card["scan_pack_route_integration"]["scan_pack_route_signal_available"] is False
