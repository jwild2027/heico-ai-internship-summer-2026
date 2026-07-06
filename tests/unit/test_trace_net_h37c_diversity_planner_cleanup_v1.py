
from tiff.trace_net_h37_diversity_evidence_planner_v1 import (
    _extract_figure,
    _extract_nomenclature,
    collect_evidence_cards,
)


def test_h37c_filters_anchor_figure():
    assert _extract_figure({"figure": "anchor"}) == ""
    assert _extract_figure({"figure": "91"}) == "91"


def test_h37c_filters_metadata_nomenclature():
    assert _extract_nomenclature({"nomenclature": "source_evidence_document_count"}) == ""
    assert _extract_nomenclature({"nomenclature": "DOUBLE PASSENGER SEAT ASSY"}) == "DOUBLE PASSENGER SEAT ASSY"


def test_h37c_unique_labels_for_duplicate_source_labels(tmp_path):
    import json
    p = tmp_path / "visual.json"
    p.write_text(json.dumps({
        "records": [
            {"citation_label": "V6", "page": "315", "figure": "69", "linked_part_number": "120-50645-005", "nomenclature": "DOUBLE PASSENGER SEAT ASSY"},
            {"citation_label": "V6", "page": "327", "figure": "75", "linked_part_number": "120-50645-011", "nomenclature": "DOUBLE PASSENGER SEAT ASSY"},
        ]
    }), encoding="utf-8")
    cards = collect_evidence_cards(image_visual_evidence_pack=p)
    labels = [c["evidence_label"] for c in cards]
    assert len(labels) == len(set(labels))
