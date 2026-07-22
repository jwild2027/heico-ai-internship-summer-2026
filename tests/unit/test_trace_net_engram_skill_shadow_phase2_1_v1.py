import importlib.util
import json
import sys
from pathlib import Path

CARDS_PATH = Path("tiff/trace_net_engram_skill_cards_v1.py")
SHADOW_PATH = Path("tiff/trace_net_engram_skill_shadow_v1.py")
LIBRARY_PATH = Path(
    "local_data/organization/trace_net/engram_skill_cards_v1/"
    "trace_net_engram_skill_cards_v1.json"
)
COGNITIVE_PATH = Path("scripts/serve_trace_net_cognitive_router_v1.py")
GEMMA_PATH = Path("scripts/serve_trace_net_full_gemma_cognitive_v1.py")
LAUNCHER_PATH = Path("scripts/launch_trace_net_cognitive_openwebui_v1.sh")

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module

def real_shaped_q001_atoms():
    return {
        "latest_query": "I only know the part starts with 123",
        "normalized_query": "i only know the part starts with 123",
        "exact_part_numbers": [],
        "ata_exact": [],
        "ata_prefix": None,
        "part_prefix": "123",
        "part_suffix": None,
        "part_contains": None,
        "identifier_mode": "prefix",
        "normalized_identifier": "123",
        "family_identifier": None,
        "allow_family_expansion": False,
        "allow_partial_candidates": True,
        "explicit_partial_wording": True,
        "page_ids": [],
        "figures": [],
        "items": [],
        "nomenclature_terms": [],
        "assembly_context": [],
        "manufacturer": None,
        "visual_requested": False,
        "table_requested": False,
        "procedure_requested": False,
        "warning_requested": False,
        "authority_requested": False,
        "navigation_requested": False,
        "graph_requested": False,
        "comparison_requested": False,
        "contradiction_requested": False,
        "ocr_requested": False,
        "aggregate_requested": False,
        "general_chat": False,
        "multi_question": False,
        "requested_claims": [],
    }

def test_empty_query_atom_fields_do_not_become_positive_atoms():
    module = load(CARDS_PATH, "cards_phase2_1_empty")
    atoms = module.infer_query_atoms(
        "I only know the part starts with 123",
        route="guided_part_discovery",
        query_atoms=real_shaped_q001_atoms(),
    )
    assert "manufacturer" not in atoms
    assert "ata_prefix" not in atoms
    assert "nomenclature_terms" not in atoms
    assert "visual_requested" not in atoms
    assert "part_prefix" in atoms
    assert "explicit_partial_wording" in atoms
    assert "partial_identifier" in atoms

def test_q001_with_runtime_atoms_selects_only_partial_skill():
    module = load(CARDS_PATH, "cards_phase2_1_q001")
    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    result = module.select_engram_skills(
        library,
        query="I only know the part starts with 123",
        route="guided_part_discovery",
        query_atoms=real_shaped_q001_atoms(),
        max_skills=3,
    )
    assert result["selected_skill_ids"] == [
        "partial_identifier_discovery"
    ]

def test_populated_manufacturer_still_selects_manufacturer_skill():
    module = load(CARDS_PATH, "cards_phase2_1_manufacturer")
    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    atoms = real_shaped_q001_atoms()
    atoms["manufacturer"] = "Honeywell"
    atoms["part_prefix"] = None
    atoms["identifier_mode"] = "none"
    atoms["normalized_identifier"] = ""
    atoms["allow_partial_candidates"] = False
    atoms["explicit_partial_wording"] = False
    result = module.select_engram_skills(
        library,
        query="I need a Honeywell hinge part",
        route="nomenclature_function_search",
        query_atoms=atoms,
        max_skills=3,
    )
    assert result["selected_skill_ids"][0] == (
        "manufacturer_plus_description_discovery"
    )

def test_shadow_q001_no_false_manufacturer_skill():
    module = load(SHADOW_PATH, "shadow_phase2_1")
    result = {
        "query": "I only know the part starts with 123",
        "route": "guided_part_discovery",
        "query_atoms": real_shaped_q001_atoms(),
        "route_plan": {
            "retrieval_tunnels": [
                "guided_candidate_discovery",
                "normal_source_resolution",
            ]
        },
        "evidence_envelope": {
            "retrieval_tunnels_used": [
                "guided_candidate_discovery",
            ]
        },
        "content": (
            "TRACE-Net found candidate evidence, not a final "
            "identification: 1234567"
        ),
        "follow_up_questions": [],
    }
    shadow = module.build_engram_skill_shadow(
        result,
        stage="final_answer_writer",
        library_path=LIBRARY_PATH,
        max_skills=3,
    )
    assert shadow["selected_skill_ids"] == [
        "partial_identifier_discovery"
    ]

def test_cognitive_runtime_is_wired_once():
    text = COGNITIVE_PATH.read_text(encoding="utf-8")
    assert text.count(
        "from scripts.trace_net_h30_engram_skill_shadow_v1 "
        "import install_engram_skill_shadow"
    ) == 1
    assert text.count(
        "install_engram_skill_shadow(globals())"
    ) == 1

def test_gemma_runtime_is_wired_once():
    text = GEMMA_PATH.read_text(encoding="utf-8")
    assert text.count(
        "from scripts.trace_net_h30_engram_skill_shadow_v1 "
        "import install_engram_skill_shadow"
    ) == 1
    assert text.count(
        "install_engram_skill_shadow(globals())"
    ) == 1

def test_launcher_propagates_shadow_environment_to_both_services():
    text = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert sum(
        1 for line in text.splitlines()
        if line.startswith('ENGRAM_SKILL_SHADOW_ENABLED=')
    ) == 1
    assert text.count(
        'export TRACE_NET_H30_ENGRAM_SKILL_SHADOW_ENABLED='
    ) == 2
    assert text.count(
        'export TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH='
    ) == 2
    assert text.count(
        'export TRACE_NET_H30_ENGRAM_SKILL_SHADOW_MAX_SKILLS='
    ) == 2
