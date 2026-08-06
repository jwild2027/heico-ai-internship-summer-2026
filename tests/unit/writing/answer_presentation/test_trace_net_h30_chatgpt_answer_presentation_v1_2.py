from __future__ import annotations

import copy
import importlib.util
import re
import sys
from pathlib import Path

MODULE_PATH = Path("src/trace_net/writing/answer_presentation/trace_net_h30_chatgpt_answer_presentation_v1_2.py")


def load(name="trace_net_h30_chatgpt_answer_presentation_v1_2_test"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def entry(
    cid,
    cls,
    *,
    candidate="",
    page="",
    value="",
    nomenclature=None,
    field_name="",
    direct=False,
    conflict=False,
):
    return {
        "citation_id": cid,
        "class": cls,
        "candidate_value": candidate,
        "part_number": candidate,
        "page_id": page,
        "page_ids": [page] if page else [],
        "value": value,
        "identifier_blob": value or candidate,
        "nomenclature": nomenclature or [],
        "field_name": field_name,
        "can_prove_claims": direct,
        "metadata_conflict": conflict,
    }


def result(route, registry, *, atoms=None, content="prior"):
    return {
        "route": route,
        "content": content,
        "query_atoms": atoms or {},
        "citation_registry": copy.deepcopy(registry),
        "post_answer_validation": {
            "accepted": False,
            "quality_status": "FAIL",
            "failures": ["stale_failure"],
        },
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def strict_validate(answer, query, current, *, extra_allowed=None, registry=None):
    valid = {int(row["citation_id"]) for row in registry or []}
    cited = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    failures = []
    if not cited.issubset(valid):
        failures.append("unknown_citation_id")
    direct = any(row.get("can_prove_claims") for row in registry or [])
    if direct:
        factual_markers = (
            "appears", "lists", "listed", "shows", "identified", "located",
            "nomenclature", "quantity", "figure", "table", "manual", "part ",
            "ata ", "page ", "revision", "manufacturer",
        )
        for line in answer.splitlines():
            low = line.lower()
            if not line.strip() or line.startswith("#"):
                continue
            if any(marker in low for marker in factual_markers) and not re.search(r"\[\d+\]", line):
                failures.append("uncited_factual_line")
                break
    return {
        "accepted": not failures,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }


def headings(text):
    return [line.strip() for line in text.splitlines() if line.startswith("## ")]


def test_q02_q03_mixed_exact_limit_avoids_uncited_factual_markers():
    mod = load("presentation_v12_exact")
    registry = [
        entry(1, "direct_source", page="t_p_120_1176_p000344", value="120-20970-003 source", direct=True),
        entry(4, "direct_source", page="t_p_120_1176_p000353", value="120-20970-003 source", direct=True),
        entry(7, "candidate", candidate="120-20970-003", page="t_p_120_1176_p000344", nomenclature=["STRUCTURE, ARMREST"]),
    ]
    current = result(
        "exact_identifier_lookup",
        registry,
        atoms={"identifier_mode": "exact", "normalized_identifier": "12020970003"},
    )
    answer = mod.render_part_answer_v1_2(current, "Find part 120-20970-003.")
    validation = strict_validate(answer, "Find part 120-20970-003.", current, registry=registry)
    assert validation["accepted"], validation
    assert "Some associations remain guidance-level." in answer
    assert "Some listed nomenclature or page associations" not in answer
    assert "t_p_120_1176_p000344" in answer
    assert "t_p_120_1176_p000353" in answer
    assert "Structure Armrest" in answer


def test_nomenclature_route_requires_requested_noun_and_drops_page_only_record():
    mod = load("presentation_v12_nomenclature")
    registry = [
        entry(1, "candidate", candidate="120-48024-001", page="t_p_120_1176_p000055", nomenclature=["RING, LOCKING"]),
        entry(2, "semantic", candidate="120-29068-025", page="t_p_120_1176_p000427", value="unrelated page association"),
        entry(3, "candidate", candidate="120-48023-001", page="t_p_120_1176_p000054", nomenclature=["PIN, ATTACH"]),
    ]
    current = result(
        "nomenclature_function_search",
        registry,
        atoms={"nomenclature_terms": ["ring"]},
    )
    answer = mod.render_part_answer_v1_2(current, "Find the ring in the document set.")
    assert "120-48024-001" in answer
    assert "Ring Locking" in answer
    assert "120-29068-025" not in answer
    assert "120-48023-001" not in answer


def test_known_assyv_and_internal_field_label_are_hidden():
    mod = load("presentation_v12_names")
    registry = [
        entry(
            1,
            "direct_source",
            candidate="120-36833-005",
            page="t_p_120_1176_p000003",
            field_name="Covered Part Number",
            direct=True,
        ),
        entry(
            2,
            "candidate",
            candidate="120-29067-005",
            page="t_p_120_1176_p000351",
            nomenclature=["STRUCTURE ASSYV"],
        ),
    ]
    current = result(
        "guided_part_discovery",
        registry,
        atoms={"identifier_mode": "suffix", "normalized_identifier": "005"},
    )
    answer = mod.render_part_answer_v1_2(current, "I only remember that the part number ends with 005.")
    assert headings(answer) == ["## Answer", "## Evidence", "## Limits"]
    assert "Covered Part Number" not in answer
    assert "ASSYV" not in answer
    assert "Structure Assembly" in answer
    assert "Matching candidates are listed below [1]." in answer


def test_exact_candidate_answer_cites_the_best_match():
    mod = load("presentation_v12_candidate")
    registry = [
        entry(1, "candidate", candidate="120-20970-001", page="t_p_120_1176_p000343", nomenclature=["STRUCTURE, ARMREST"]),
    ]
    current = result(
        "exact_identifier_lookup",
        registry,
        atoms={"identifier_mode": "exact", "normalized_identifier": "12020970001"},
    )
    answer = mod.render_part_answer_v1_2(current, "Find part 120-20970-001.")
    answer_line = answer.split("## Answer", 1)[1].split("## Evidence", 1)[0]
    assert "[1]" in answer_line
    assert "record remains a candidate" in answer


def test_install_revalidates_target_route_and_preserves_non_target_route():
    mod = load("presentation_v12_install")
    registry = [
        entry(1, "direct_source", page="t_p_120_1176_p000030", value="120-26948-003 source", direct=True),
        entry(4, "candidate", candidate="120-26948-003", page="t_p_120_1176_p000029", nomenclature=["SUPPORT"]),
    ]
    base = result(
        "exact_identifier_lookup",
        registry,
        atoms={"identifier_mode": "exact", "normalized_identifier": "12026948003"},
    )
    base["route_plan"] = {"retrieval_tunnels": ["normal_source_truth"]}
    base["timing"] = {"gemma_called": True}

    class Runtime:
        def process(self, payload):
            return copy.deepcopy(base)

        def health(self):
            return {"quality_status": "PASS"}

    module = {
        "Runtime": Runtime,
        "validate_answer": strict_validate,
        "extract_latest_user": lambda payload: payload["query"],
        "citation_registry": lambda current: current["citation_registry"],
        "citation_registry_digest": lambda registry: "digest",
        "synthesis_allowed_identifiers": lambda query, current: None,
    }
    mod.install_chatgpt_answer_presentation_v1_2(module)
    output = Runtime().process({"query": "Find part 120-26948-003."})
    assert output["post_answer_validation"]["accepted"]
    assert output["route_plan"] == base["route_plan"]
    assert output["timing"] == base["timing"]
    metadata = output["chatgpt_answer_presentation_v1_2"]
    assert metadata["gemma_call_count_added"] == 0
    assert metadata["retrieval_changed"] is False
    assert metadata["source_truth_mutation_allowed"] is False
