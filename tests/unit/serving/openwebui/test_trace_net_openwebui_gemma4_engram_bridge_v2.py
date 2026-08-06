import json
from pathlib import Path

from tiff.trace_net_openwebui_gemma4_engram_bridge_v1 import EvidenceCard
from tiff.trace_net_openwebui_gemma4_engram_bridge_v2 import (
    collect_source_pages_from_artifacts,
    filter_evidence_cards,
    query_kind,
)


def test_corpus_stats_query_kind():
    assert query_kind("how many pages can you look at") == "corpus_stats"
    assert query_kind("what pages can you see?") == "corpus_stats"
    assert query_kind("Find part number 120-50645-005") == "part_lookup"


def test_filter_metric_cards():
    cards = [
        EvidenceCard("E1", "exact", "x", "", "", "", "can_answer_directly_count", "nomenclature", "can_answer_directly_count", "can_answer_directly_count"),
        EvidenceCard("O1", "ocr", "x", "t_p_120_1176_p000315", "315", "120-50645-005", "DOUBLE PASSENGER SEAT ASSY", "line_text", "x", "120-50645-005 DOUBLE PASSENGER SEAT ASSY"),
    ]
    out = filter_evidence_cards(cards)
    assert len(out) == 1
    assert out[0].label == "O1"


def test_collect_source_pages(tmp_path):
    p = tmp_path / "artifact.json"
    p.write_text(json.dumps({
        "records": [
            {"page_id": "t_p_120_1176_p000001", "route": "image_visual"},
            {"page_id": "t_p_120_1176_p000002", "route": "image_visual"},
            {"page_id": "metadata_page_000001", "route": "image_visual"},
        ]
    }), encoding="utf-8")
    stats = collect_source_pages_from_artifacts([p])
    assert stats["source_page_count"] == 2
    assert stats["first_page_id"] == "t_p_120_1176_p000001"
    assert stats["last_page_id"] == "t_p_120_1176_p000002"
