from collections import Counter

from scripts.trace_net_h30_phase5_question_bank_v1 import (
    CATEGORY_COUNTS,
    EXPECTED_ROUTE_COUNTS,
    EXPECTED_TOTAL,
    build_phase5_bank,
    enrich_phase5_truth,
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


# TRACE_NET_H30_PHASE5_CALIBRATED_CORPUS_V1
def test_phase5_route_sensitive_prompts_are_single_intent_and_contract_aware():
    bank = build_phase5_bank(synthetic_truth())
    by_category = {}
    for item in bank:
        by_category.setdefault(item["category"], []).append(item)

    assert {item["question"].casefold() for item in by_category["safe_general"]} == {
        "hello", "what can you do?",
    }
    assert all(not item["requires_citation"] for item in by_category["safe_general"])
    assert all(not item["public_contract_required"] for item in by_category["safe_general"])

    partial = [item for item in bank if item["category"].startswith("partial_")]
    assert all(
        "only remember" in item["question"].casefold()
        or "only know" in item["question"].casefold()
        for item in partial
    )

    single_intent_categories = {
        "table_ipl", "visual_figure", "procedure", "warning_caution_note",
        "cross_source_comparison", "high_degree_aggregation",
    }
    assert all(
        " and " not in item["question"].casefold()
        for item in bank if item["category"] in single_intent_categories
    )

    assert all(
        item["source_basis"]["route"] in {"detailed_parts_list", "table_or_index"}
        for item in by_category["table_ipl"]
    )
    assert all(item["expected_identifiers"] for item in by_category["table_ipl"])
    assert all(
        item["source_basis"]["route"] in {"image_visual_diagram", "mixed_text_and_figure"}
        for item in by_category["visual_figure"]
    )
    assert all(
        item["source_basis"]["route"] == "procedure_or_description"
        for item in by_category["procedure"]
    )
    assert all(
        item["expected_terms"][0] not in {"SUPPORT", "TABLE", "LEG"}
        for item in by_category["nomenclature"]
    )

    negative_controls = [item for item in bank if item["negative_control"]]
    assert all(not item["requires_citation"] for item in negative_controls)
    clarification = by_category["clarification"][0]
    assert not clarification["requires_citation"]
    assert not clarification["public_contract_required"]
# TRACE_NET_H30_PHASE5_ROUTE_RESOLVER_ENRICHMENT_V1
def test_phase5_enriches_deployed_sparse_card_routes_from_resolver(tmp_path):
    import json

    truth = synthetic_truth()
    resolver_records = []
    for card in truth["cards"]:
        route = card["route"]["recommended_route_candidate"]
        resolver_records.append({
            "page_id": card["page_id"],
            "primary_route": route,
            "secondary_routes": [],
            "part_number_tokens": list(card.get("important_parts") or []),
            "signal_counts": {},
        })
        card["route"] = {}

    report = tmp_path / "local_data/organization/trace_net/route_confidence_resolver/trace_net_route_confidence_resolver_v1.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({
        "quality_status": "PASS",
        "records": resolver_records,
    }), encoding="utf-8")

    enriched = enrich_phase5_truth(tmp_path, truth)
    info = enriched["phase5_route_resolver"]
    assert info["loaded"] is True
    assert info["record_count"] == len(truth["cards"])
    assert info["matched_card_count"] == len(truth["cards"])
    assert enriched["cards"][0]["phase5_route_resolver"]["primary_route"]

    bank = build_phase5_bank(enriched)
    assert validate_phase5_bank(bank)["accepted"]
    table_rows = [row for row in bank if row["category"] == "table_ipl"]
    assert len(table_rows) == 7
    assert all("route_resolver:" in row["source_basis"]["selection_basis"] for row in table_rows)


def test_phase5_content_signal_fallback_is_strict_but_not_route_metadata_dependent():
    truth = synthetic_truth()
    for index, card in enumerate(truth["cards"]):
        card["route"] = {}
        if index < 12:
            card["v2_retrieval_summary"] += " Diagram illustration callout exploded view."

    enriched = enrich_phase5_truth("/path/that/does/not/exist", truth)
    assert enriched["phase5_route_resolver"]["loaded"] is False

    bank = build_phase5_bank(enriched)
    assert validate_phase5_bank(bank)["accepted"]
    table_rows = [row for row in bank if row["category"] == "table_ipl"]
    visual_rows = [row for row in bank if row["category"] == "visual_figure"]
    assert all(row["source_basis"]["selection_basis"].startswith("content_signals:") for row in table_rows)
    assert all(row["source_basis"]["selection_basis"].startswith("content_signals:") for row in visual_rows)

# TRACE_NET_H30_PHASE5_RESIDUAL_REPAIR_V1

def test_phase5_third_partial_prompt_places_literal_clue_after_operator():
    bank = build_phase5_bank(synthetic_truth())
    third_rows = [
        row for row in bank
        if row["category"].startswith("partial_")
        and (row.get("source_basis") or {}).get("prompt_variant") == 3
    ]
    assert third_rows
    for row in third_rows:
        clue = row["source_basis"]["clue"]
        question = row["question"]
        assert f"{clue}; that is my only clue" in question
        assert " it." not in question


def test_phase5_warning_pages_exclude_front_matter_routes():
    bank = build_phase5_bank(synthetic_truth())
    warning_rows = [row for row in bank if row["category"] == "warning_caution_note"]
    assert len(warning_rows) == 4
    assert all(
        (row.get("source_basis") or {}).get("route")
        not in {"blank_candidate", "cover_or_title_page", "review_required"}
        for row in warning_rows
    )


def test_phase5_comparison_pages_are_source_resolved_or_strict_route_pages():
    bank = build_phase5_bank(synthetic_truth())
    comparison_rows = [row for row in bank if row["category"] == "cross_source_comparison"]
    assert len(comparison_rows) == 4
    assert all(
        (row.get("source_basis") or {}).get("selection_basis")
        == "source_resolved_or_strict_route_page"
        for row in comparison_rows
    )
