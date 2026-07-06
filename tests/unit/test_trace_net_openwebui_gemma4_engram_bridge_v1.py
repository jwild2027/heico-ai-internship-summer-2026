from tiff.trace_net_openwebui_gemma4_engram_bridge_v1 import (
    EvidenceCard,
    extract_page_id,
    extract_part_number,
    query_kind,
    retrieve_evidence,
)


def test_query_kind():
    assert query_kind("Find part number 120-50645-005") == "part_lookup"
    assert query_kind("pick a random page") == "random_page"
    assert query_kind("page 2") == "page_lookup"


def test_extractors():
    rec = {"page_id": "t_p_120_1176_p000316", "line_text": "69 - | 120-50645-005 DOUBLE PASSENGER SEAT ASSY"}
    assert extract_page_id(rec) == "t_p_120_1176_p000316"
    assert extract_part_number(rec) == "120-50645-005"


def test_retrieve_exact_part():
    cards = [
        EvidenceCard("O1", "ocr", "x", "p000001", "1", "120-50645-005", "DOUBLE PASSENGER SEAT ASSY", "line_text", "x", "120-50645-005 DOUBLE PASSENGER SEAT ASSY"),
        EvidenceCard("O2", "ocr", "x", "p000002", "2", "120-00000-000", "", "line_text", "x", "other"),
    ]
    kind, selected = retrieve_evidence(cards, "Find part number 120-50645-005", max_cards=3)
    assert kind == "part_lookup"
    assert selected[0].part_number == "120-50645-005"
