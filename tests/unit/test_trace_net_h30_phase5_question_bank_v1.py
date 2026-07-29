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

# TRACE_NET_H30_PHASE5_ATA_REUSE_V1
def test_phase5_bank_reuses_five_grounded_ata_codes():
    truth = synthetic_truth()
    truth["ata_pages"] = dict(list(truth["ata_pages"].items())[:5])

    bank = build_phase5_bank(truth)
    ata_questions = [item for item in bank if item["category"] == "ata_system"]

    assert len(ata_questions) == 8
    assert len({item["expected_terms"][0] for item in ata_questions}) == 5
    assert len({item["question"] for item in ata_questions}) == 8
    assert sum(bool(item["source_basis"]["ata_code_reused"]) for item in ata_questions) == 3
    assert all(item["expected_route"] == "ata_system_discovery" for item in ata_questions)
    assert validate_phase5_bank(bank)["accepted"]


def test_phase5_bank_supports_one_grounded_ata_code():
    truth = synthetic_truth()
    first_ata, first_pages = next(iter(truth["ata_pages"].items()))
    truth["ata_pages"] = {first_ata: first_pages}

    bank = build_phase5_bank(truth)
    ata_questions = [item for item in bank if item["category"] == "ata_system"]

    assert len(ata_questions) == 8
    assert {item["expected_terms"][0] for item in ata_questions} == {first_ata}
    assert len({item["question"] for item in ata_questions}) == 8
    assert sum(bool(item["source_basis"]["ata_code_reused"]) for item in ata_questions) == 7
    assert validate_phase5_bank(bank)["accepted"]

# TRACE_NET_H30_PHASE5_UNIQUE_PROMPTS_V1
def test_phase5_bank_keeps_partial_prompts_unique_for_repeated_families():
    truth = synthetic_truth()

    # Shape the early grounded records like a real IPL: several dash-number
    # variants share the same family and several records share suffix 005.
    repeated_parts = [
        "120-20970-001",
        "120-20970-003",
        "120-20970-005",
        "120-20970-007",
        "120-26948-003",
        "120-26948-005",
        "120-29067-005",
        "120-29067-015",
        "120-29068-005",
        "120-29068-035",
        "120-29069-005",
        "120-29070-005",
        "120-29074-005",
        "120-41824-001",
        "120-41824-003",
        "120-48023-001",
        "120-48024-001",
        "120-61610-001",
    ]
    for row, part in zip(truth["parts"], repeated_parts):
        row["part"] = part

    bank = build_phase5_bank(truth)
    partial_questions = [
        item for item in bank
        if item["category"].startswith("partial_")
    ]

    assert len(partial_questions) == 10
    assert len({item["question"].casefold() for item in partial_questions}) == 10
    assert all(item["source_basis"].get("prompt_variant") in {1, 2, 3} for item in partial_questions)
    assert validate_phase5_bank(bank)["accepted"]


def test_phase5_bank_deduplicates_manufacturer_fallback_candidates():
    truth = synthetic_truth()
    # The generated V3 text already contains manufacturer IDs; appending the
    # fallback list must not create duplicate benchmark questions.
    bank = build_phase5_bank(truth)
    manufacturer_questions = [
        item for item in bank
        if item["category"] == "manufacturer_identifier"
    ]
    assert len(manufacturer_questions) == 2
    assert len({item["question"].casefold() for item in manufacturer_questions}) == 2
    assert validate_phase5_bank(bank)["accepted"]

