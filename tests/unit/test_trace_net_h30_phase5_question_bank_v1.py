from collections import Counter

from scripts.trace_net_h30_phase5_question_bank_v1 import (
    CATEGORY_COUNTS,
    EXPECTED_ROUTE_COUNTS,
    EXPECTED_TOTAL,
    build_phase5_bank,
    validate_phase5_bank,
)


def synthetic_truth():
    nouns = [
        "Pin Attach", "Ring Locking", "Cover Latch", "Panel Support", "Bracket",
        "Fitting", "Screw", "Bolt", "Clip", "Seat", "Fastener", "Retainer",
        "Spring", "Washer", "Armrest", "Support", "Hinge", "Table", "Leg",
    ]
    parts = []
    for index in range(1, 70):
        part = f"120-{20000 + index:05d}-{index % 90 + 1:03d}"
        parts.append({
            "part": part,
            "nomenclature": [nouns[(index - 1) % len(nouns)]],
            "pages": [
                {"page_id": f"t_p_120_1176_p{index:06d}", "source_resolved": True},
                {"page_id": f"t_p_120_1176_p{index + 100:06d}", "source_resolved": True},
            ],
            "source_resolved": True,
        })

    routes = [
        "detailed_parts_list", "table_or_index", "image_visual_diagram",
        "mixed_text_and_figure", "procedure_or_description", "normal_text",
    ]
    cards = []
    for index in range(1, 90):
        page_id = f"t_p_120_1176_p{index:06d}"
        part = parts[(index - 1) % len(parts)]["part"]
        text = (
            f"Unique OCR token BLOCK{index:04d} ROW{index:04d} {part} Figure {index}. "
            f"Warning caution note. Procedure remove install adjust. Illustrated parts list table item. "
            f"Manufacturer identifier MS{16000 + index}-{100 + index}."
        )
        cards.append({
            "page_id": page_id,
            "source_path": f"source_{index}.tif",
            "route": {"recommended_route_candidate": routes[(index - 1) % len(routes)]},
            "important_parts": [part],
            "v2_retrieval_summary": text,
            "ocr": {"sample_text": text},
        })
    ata_pages = {
        f"{20 + index:02d}-{10 + index:02d}-00": [f"t_p_120_1176_p{index:06d}"]
        for index in range(1, 15)
    }
    return {
        "parts": parts,
        "cards": cards,
        "ata_pages": ata_pages,
        "counts": {"graph_nodes": 100, "graph_edges": 200, "v3_cards": len(cards), "parts_with_pages": len(parts)},
        "paths": {"nodes": "nodes.json", "edges": "edges.json", "v3": "v3.json"},
    }


def test_phase5_bank_is_exactly_100_and_route_balanced():
    bank = build_phase5_bank(synthetic_truth())
    validation = validate_phase5_bank(bank)
    assert validation["accepted"], validation
    assert len(bank) == EXPECTED_TOTAL == 100
    assert Counter(item["category"] for item in bank) == Counter(dict(CATEGORY_COUNTS))
    assert Counter(item["expected_route"] for item in bank) == Counter(EXPECTED_ROUTE_COUNTS)
    assert bank[0]["question_id"] == "q001"
    assert bank[-1]["question_id"] == "q100"


def test_phase5_bank_is_deterministic():
    first = build_phase5_bank(synthetic_truth())
    second = build_phase5_bank(synthetic_truth())
    assert validate_phase5_bank(first)["bank_sha256"] == validate_phase5_bank(second)["bank_sha256"]
    assert first == second


def test_phase5_bank_covers_all_19_runtime_routes():
    routes = {item["expected_route"] for item in build_phase5_bank(synthetic_truth())}
    assert routes == set(EXPECTED_ROUTE_COUNTS)
