from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_trace_net_executive_tiff_demo_v4.py"
SPEC = importlib.util.spec_from_file_location("trace_net_demo_v4", MODULE_PATH)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def test_extract_query_atoms_exact_and_nha() -> None:
    atoms = MOD.extract_query_atoms("What bigger assembly is 120-20970-001 installed inside?")
    assert atoms["exact_part_identifiers"] == ["120-20970-001"]
    assert atoms["asks_next_higher_assembly"] is True


def test_deterministic_route_prefers_graph_relationship() -> None:
    atoms = MOD.extract_query_atoms("What is the next higher assembly for 120-20970-001?")
    assert MOD.deterministic_route(atoms) == "graph_relationship_reasoning"


def test_exact_identifier_route() -> None:
    atoms = MOD.extract_query_atoms("Find part 120-29073-001")
    assert MOD.deterministic_route(atoms) == "exact_identifier_lookup"


def test_extract_page_records_merges_route_and_text() -> None:
    ocr = {
        "records": [
            {
                "page_id": "t_p_demo_p000001",
                "page_number": 1,
                "source_member": "page_1.tif",
                "ocr_text": "PART 120-29073-001",
            }
        ]
    }
    route = {
        "records": [
            {
                "page_id": "t_p_demo_p000001",
                "page_number": 1,
                "final_validated_route": "table",
            }
        ]
    }
    merged = MOD.merge_page_records(MOD.extract_page_records(ocr), MOD.extract_page_records(route))
    assert len(merged) == 1
    assert merged[0].route == "table"
    assert "120-29073-001" in merged[0].text


def test_build_graph_snapshot_creates_two_files(tmp_path: Path) -> None:
    records = [
        MOD.PageRecord(
            page_id="t_p_demo_p000001",
            page_number=1,
            source_member="page_1.tif",
            route="table",
            text="PART 120-29073-001",
            raw={},
        )
    ]
    summary = MOD.build_graph_snapshot(tmp_path, Path("metadata.zip"), records)
    assert summary["node_count"] >= 4
    assert summary["edge_count"] >= 3
    assert Path(summary["nodes_path"]).is_file()
    assert Path(summary["edges_path"]).is_file()
    assert summary["production_graph_modified"] is False


def test_engram_has_six_named_layers(tmp_path: Path) -> None:
    records = [MOD.PageRecord("t_p_demo_p000001", 1, "page.tif", "plain_text", "text", {})]
    graph = {"node_count": 3, "edge_count": 2}
    payload = MOD.build_engram_layers(tmp_path, records, graph, {"stage_quality_statuses": {}})
    assert payload["layer_count"] == 6
    assert [row["layer"] for row in payload["layers"]] == [
        "working_memory",
        "semantic_memory",
        "procedural_memory",
        "episodic_memory",
        "trait_memory",
        "critic_memory",
    ]


def test_cosine_similarity() -> None:
    assert round(MOD.cosine_similarity([1.0, 0.0], [1.0, 0.0]), 6) == 1.0
    assert round(MOD.cosine_similarity([1.0, 0.0], [0.0, 1.0]), 6) == 0.0


def test_validate_answer_rejects_new_identifier() -> None:
    evidence = [
        {
            "citation": {"page_id": "t_p_demo_p000001"},
            "ocr_excerpt": "PART 120-29073-001",
        }
    ]
    result = MOD.validate_answer(
        "The answer is 999-99999-999 [E1].",
        "Find 120-29073-001",
        evidence,
        {"llm_status": "PASS"},
    )
    assert result["quality_status"] == "FAIL"
    assert "999-99999-999" in result["unsupported_identifiers"]


def test_validate_answer_accepts_supported_identifier() -> None:
    evidence = [
        {
            "citation": {"page_id": "t_p_demo_p000001"},
            "ocr_excerpt": "PART 120-29073-001",
        }
    ]
    result = MOD.validate_answer(
        "Part 120-29073-001 is shown [E1].",
        "Find 120-29073-001",
        evidence,
        {"llm_status": "PASS"},
    )
    assert result["quality_status"] == "PASS"


def test_parser_defaults_to_two_example_questions() -> None:
    parser = MOD.build_parser()
    args = parser.parse_args([])
    assert args.questions is None
    assert len(MOD.DEFAULT_QUESTIONS) == 2


def test_script_has_no_shell_termination_instructions() -> None:
    text = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ("set -e", "set -u", "set -o pipefail", "sys.exit(", "raise SystemExit")
    for token in forbidden:
        assert token not in text
