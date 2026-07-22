import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path


MODULE_PATH = Path("tiff/trace_net_engram_skill_cards_v1.py")
LIBRARY_PATH = Path(
    "local_data/organization/trace_net/engram_skill_cards_v1/"
    "trace_net_engram_skill_cards_v1.json"
)


def load_module():
    spec = importlib.util.spec_from_file_location("trace_net_engram_skill_cards_v1", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["trace_net_engram_skill_cards_v1"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_library():
    return json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))


def select(query, route):
    module = load_module()
    return module.select_engram_skills(
        load_library(),
        query=query,
        route=route,
        max_skills=5,
    )


def test_library_has_five_safe_valid_cards():
    module = load_module()
    result = module.validate_skill_library(load_library())
    assert result["quality_status"] == "PASS"
    assert result["skill_card_count"] == 5
    assert result["answer_permission"] is False
    assert result["source_truth_mutation_allowed"] is False
    assert result["can_be_used_as_proof"] is False
    assert result["write_attempt_count"] == 0


def test_each_card_has_required_examples_and_lessons():
    for card in load_library()["skill_cards"]:
        assert len(card["positive_examples"]) >= 5
        assert len(card["negative_examples"]) >= 3
        assert len(card["known_failure_lessons"]) >= 3
        assert "working_memory" not in card["memory_layers"]
        assert card["safety_contract"]["engram_guidance_only"] is True
        assert card["safety_contract"]["answer_permission"] is False
        assert card["safety_contract"]["can_be_used_as_proof"] is False


def test_q001_selects_partial_identifier_first():
    result = select(
        "I only know the part starts with 123",
        "guided_part_discovery",
    )
    assert result["quality_status"] == "PASS"
    assert result["selected_skill_ids"][0] == "partial_identifier_discovery"
    assert "exact_identifier_lookup" not in result["selected_skill_ids"]
    assert result["answer_permission"] is False


def test_exact_identifier_selects_exact_lookup_first():
    result = select(
        "Where is P/N 120-41824-003 listed?",
        "document_page_navigation",
    )
    assert result["selected_skill_ids"][0] == "exact_identifier_lookup"
    assert "partial_identifier_discovery" not in result["selected_skill_ids"]


def test_ata_and_description_selects_ata_skill_first():
    result = select(
        "Find a hinge in ATA 25-21-00",
        "ata_system_discovery",
    )
    assert result["selected_skill_ids"][0] == "ata_plus_description_discovery"


def test_manufacturer_and_description_selects_manufacturer_skill_first():
    result = select(
        "I need a Honeywell hinge part",
        "nomenclature_function_search",
    )
    assert result["selected_skill_ids"][0] == "manufacturer_plus_description_discovery"


def test_nomenclature_function_selects_component_skill_first():
    result = select(
        "I need a part that lets the seat pivot",
        "nomenclature_function_search",
    )
    assert result["selected_skill_ids"][0] == "nomenclature_function_discovery"


def test_selection_is_deterministic_and_bounded():
    module = load_module()
    library = load_library()
    first = module.select_engram_skills(
        library,
        query="Find an Embraer seat bracket",
        route="nomenclature_function_search",
        max_skills=50,
    )
    second = module.select_engram_skills(
        library,
        query="Find an Embraer seat bracket",
        route="nomenclature_function_search",
        max_skills=50,
    )
    assert first["selected_skill_ids"] == second["selected_skill_ids"]
    assert first["max_skills"] == 5
    assert first["selected_skill_count"] <= 5


def test_unsafe_card_is_rejected():
    module = load_module()
    library = deepcopy(load_library())
    library["skill_cards"][0]["safety_contract"]["answer_permission"] = True
    result = module.validate_skill_library(library)
    assert result["quality_status"] == "FAIL"
    assert any("unsafe_safety_field:answer_permission" in item for item in result["errors"])
