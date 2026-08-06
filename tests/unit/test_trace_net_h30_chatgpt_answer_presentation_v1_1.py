from __future__ import annotations

import copy
import importlib.util
import re
import sys
from pathlib import Path

MODULE_PATH = Path("src/trace_net/writing/answer_presentation/trace_net_h30_chatgpt_answer_presentation_v1_1.py")


def load(name="trace_net_h30_chatgpt_answer_presentation_v1_1_test"):
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
    direct=False,
    kind="",
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
        "can_prove_claims": direct,
        "page_content": bool(kind),
        "page_content_kind": kind,
        "metadata_conflict": conflict,
    }


def result(route, registry, *, content="", atoms=None, coverage=None):
    return {
        "route": route,
        "content": content,
        "query_atoms": atoms or {},
        "citation_registry": copy.deepcopy(registry),
        "evidence_envelope": {
            "direct_evidence": [],
            "candidate_evidence": [],
            "visual_guidance": [],
            "semantic_guidance": [],
            "authority_evidence": [],
            "coverage": copy.deepcopy(coverage or {}),
        },
        "writer_mode": "chatgpt_style_public_answer",
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def headings(text):
    return [line.strip() for line in text.splitlines() if line.startswith("## ")]


def strict_validate(answer, query, current, *, extra_allowed=None, registry=None):
    valid = {int(row["citation_id"]) for row in registry or []}
    cited = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    failures = []
    if not cited.issubset(valid):
        failures.append("unknown_citation_id")
    direct = any(row.get("can_prove_claims") for row in registry or [])
    if direct:
        for line in answer.splitlines():
            low = line.lower()
            if line.startswith("#") or not line.strip():
                continue
            if any(token in low for token in ("page `", "ipl/table", "appears in the indexed source")) and not re.search(r"\[\d+\]", line):
                failures.append("uncited_factual_line")
                break
    return {"accepted": not failures, "quality_status": "PASS" if not failures else "FAIL", "failures": failures}


def test_table_raw_dump_is_replaced_with_cited_summary():
    mod = load("presentation_v11_table")
    registry = [
        entry(
            1,
            "direct_source",
            page="t_p_120_1176_p000030",
            value=(
                "embedding_candidate: TRACE-Net OCR page text. OCR status: ok. "
                "Recommended route: table. EMBRAER MAINTENANCE MANUAL WITH "
                "ILLUSTRATED PARTS LIST CH-SEC-UN-FIG 120-26948-003"
            ),
            direct=True,
        ),
        entry(
            2,
            "direct_source",
            page="t_p_120_1176_p000030",
            value="V2 page context for 120-26948-003",
            direct=True,
        ),
    ]
    current = result("exact_table_ipl_lookup", registry)
    answer = mod.render_chatgpt_style_answer_v1_1(current, "Locate part 120-26948-003 in the IPL table.")
    assert headings(answer)[:2] == ["## Answer", "## Evidence"]
    assert "120-26948-003" in answer
    assert "t_p_120_1176_p000030" in answer
    assert "[1]" in answer
    assert "embedding_candidate" not in answer
    assert "OCR status" not in answer
    assert "Recommended route" not in answer
    assert "CH-SEC-UN-FIG" not in answer
    assert answer.count("t_p_120_1176_p000030") <= 2


def test_exact_part_collapses_duplicate_records_without_merging_nomenclature_claim():
    mod = load("presentation_v11_exact")
    registry = [
        entry(1, "direct_source", page="t_p_120_1176_p000344", value="120-20970-003 source row", direct=True),
        entry(2, "direct_source", page="t_p_120_1176_p000344", value="120-20970-003 duplicate", direct=True),
        entry(3, "direct_source", page="t_p_120_1176_p000353", value="120-20970-003 second page", direct=True),
        entry(4, "candidate", candidate="120-20970-003", page="t_p_120_1176_p000344", nomenclature=["STRUCTURE, ARMREST"]),
    ]
    current = result(
        "exact_identifier_lookup",
        registry,
        atoms={"identifier_mode": "exact", "normalized_identifier": "12020970003"},
    )
    answer = mod.render_chatgpt_style_answer_v1_1(current, "Find part 120-20970-003.")
    assert answer.count("Source-backed record") == 2
    assert answer.count("Structure Armrest") == 1
    assert "appears in the indexed source records [1]" in answer
    assert answer.count("t_p_120_1176_p000344") == 2


def test_suffix_mixed_evidence_stays_in_three_sections_and_cleans_names():
    mod = load("presentation_v11_suffix")
    registry = [
        entry(1, "direct_source", candidate="120-36833-005", page="t_p_120_1176_p000003", direct=True),
        entry(2, "candidate", candidate="120-29067-005", page="t_p_120_1176_p000351", nomenclature=["STRUCTURE, ASSY, STRUCTURE, ASSY. (SEE FIGURE)"], conflict=True),
        entry(3, "candidate", candidate="120-29074-005", page="t_p_120_1176_p000482", nomenclature=["SARY, USING THE INSTALLED"]),
    ]
    current = result(
        "guided_part_discovery",
        registry,
        atoms={"identifier_mode": "suffix", "normalized_identifier": "005"},
        content="## Answer\nDirectly Supported Evidence...\n## Engineering confidence\nMixed evidence",
    )
    answer = mod.render_chatgpt_style_answer_v1_1(current, "I only remember that the part number ends with 005.")
    assert headings(answer) == ["## Answer", "## Evidence", "## Limits"]
    assert "Engineering confidence" not in answer
    assert "Structure Assembly" in answer
    assert "Structure Assembly Structure Assembly" not in answer
    assert "Using The Installed" not in answer
    assert "unresolved source-association conflict" in answer


def test_nomenclature_route_always_uses_evidence_heading():
    mod = load("presentation_v11_nomenclature")
    registry = [
        entry(1, "candidate", candidate="120-48024-001", page="t_p_120_1176_p000055", nomenclature=["RING, LOCKING"]),
    ]
    current = result("nomenclature_function_search", registry)
    answer = mod.render_chatgpt_style_answer_v1_1(current, "Find the ring in the document set.")
    assert headings(answer) == ["## Answer", "## Evidence", "## Limits"]
    assert "Ring Locking" in answer
    assert "not confirmation of a technical relationship" in answer


def test_visual_summary_noise_is_removed_and_callout_uncertainty_moves_to_limits():
    mod = load("presentation_v11_visual")
    content = (
        "## Answer\n\nPage `t_p_120_1176_p000081` contains Figure 1 Sheet 1 [1].\n\n"
        "## Evidence\n\n"
        "- Visible labels include: Single passenger seat [1].\n"
        "- Printed identifier(s): `120-41824-001/501` [1].\n"
        "- Visual summary: visual page associated with part number(s): 120-41824-0, 25-21-00 [4].\n"
        "- The current visual record does not resolve every numbered callout [4]."
    )
    current = result("visual_figure_callout_lookup", [], content=content)
    answer = mod.render_chatgpt_style_answer_v1_1(current, "Show the diagram on page t_p_120_1176_p000081.")
    assert "Visual summary" not in answer
    assert "120-41824-0, 25-21-00" not in answer
    assert "## Limits" in answer
    assert "does not resolve every numbered callout" in answer


def test_procedure_reset_is_grouped_as_continuation_and_second_sequence():
    mod = load("presentation_v11_procedure")
    content = (
        "## Answer\n\nPage `t_p_120_1176_p000482` contains procedure steps [1].\n\n"
        "## Evidence\n\n"
        "- c. Adjust the baggage protector [1]\n"
        "- d. Install the new leg structure [1]\n"
        "- e. Install the preformed seal [1]\n"
        "- f. Finish the reworked region [1]\n"
        "- a. Remove the paint [1]\n"
        "- b. Withdraw the fasteners [1]\n"
        "- c. Install the new lateral leg [1]\n"
    )
    current = result("procedure_task_lookup", [], content=content)
    answer = mod.render_chatgpt_style_answer_v1_1(current, "What procedure is described on page t_p_120_1176_p000482?")
    assert "continued procedure and a second readable procedure sequence" in answer
    assert "Continuation — c." in answer
    assert "Sequence 2 — a." in answer


def test_negative_page_passes_even_when_unrelated_guidance_exists():
    mod = load("presentation_v11_negative")
    registry = [entry(1, "semantic", page="t_p_120_1176_p000001", value="unrelated page")]
    base = result("document_page_navigation", registry, coverage={"page_content": {"available": False, "pages": []}})

    class Runtime:
        def process(self, payload):
            return copy.deepcopy(base)

        def health(self):
            return {"quality_status": "PASS"}

    module = {
        "Runtime": Runtime,
        "validate_answer": lambda answer, *args, **kwargs: {
            "accepted": False,
            "quality_status": "FAIL",
            "failures": ["direct_answer_missing_citation", "uncited_factual_line"],
        },
        "extract_latest_user": lambda payload: payload["query"],
        "citation_registry": lambda current: current["citation_registry"],
        "citation_registry_digest": lambda registry: "digest",
        "synthesis_allowed_identifiers": lambda query, current: None,
    }
    mod.install_chatgpt_answer_presentation_v1_1(module)
    output = Runtime().process({"query": "Open page t_p_120_1176_p999999 and explain what it contains."})
    assert output["post_answer_validation"]["accepted"]
    assert output["post_answer_validation"]["negative_result_without_fabricated_citation"]
    assert "t_p_120_1176_p999999" in output["content"]
    assert "[1]" not in output["content"]


def test_install_repairs_uncited_direct_answer_and_preserves_telemetry():
    mod = load("presentation_v11_install")
    registry = [
        entry(1, "direct_source", page="t_p_120_1176_p000030", value="120-26948-003 table row", direct=True, kind="table")
    ]
    base = result("exact_table_ipl_lookup", registry)
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
    mod.install_chatgpt_answer_presentation_v1_1(module)
    output = Runtime().process({"query": "Locate part 120-26948-003 in the IPL table."})
    assert output["post_answer_validation"]["accepted"]
    assert output["route_plan"] == base["route_plan"]
    assert output["timing"] == base["timing"]
    assert "embedding_candidate" not in output["content"]
    metadata = output["chatgpt_answer_presentation_v1_1"]
    assert metadata["gemma_call_count_added"] == 0
    assert metadata["retrieval_changed"] is False
    assert metadata["source_truth_mutation_allowed"] is False

# TRACE_NET_H30_PHASE5_NOTICE_COMPARISON_RUNTIME_FIX_V1_1
def test_warning_route_renders_explicit_cited_ocr_notice():
    mod = load("presentation_v11_warning_notice")
    page = "t_p_120_1176_p000470"
    registry = [
        entry(
            1,
            "page_ocr_text",
            page=page,
            value="WARNING: Disconnect electrical power before removing the actuator.",
            kind="ocr",
        )
    ]
    current = result("warning_caution_note_lookup", registry)
    answer = mod.render_chatgpt_style_answer_v1_1(
        current,
        f"What warning is explicitly stated on page {page}?",
    )
    assert headings(answer) == ["## Answer", "## Evidence", "## Limits"]
    assert "contains an explicit warning [1]" in answer
    assert "**OCR text:**" in answer
    assert "Disconnect electrical power" in answer


def test_warning_route_fails_closed_with_canonical_no_notice_answer():
    mod = load("presentation_v11_warning_none")
    page = "t_p_120_1176_p000470"
    registry = [
        entry(1, "page_ocr_text", page=page, value="General descriptive page text.", kind="ocr")
    ]
    current = result("warning_caution_note_lookup", registry)
    answer = mod.render_chatgpt_style_answer_v1_1(
        current,
        f"What warning is explicitly stated on page {page}?",
    )
    assert headings(answer) == ["## Answer", "## Evidence", "## Limits"]
    assert "No explicit warning was found" in answer
    assert "[1]" not in answer


def test_comparison_route_renders_both_exact_pages_with_citations():
    mod = load("presentation_v11_page_comparison")
    left = "t_p_120_1176_p000036"
    right = "t_p_120_1176_p000037"
    registry = [
        entry(1, "page_ocr_text", page=left, value="Seat structure removal information.", kind="ocr"),
        entry(2, "page_ocr_text", page=right, value="Seat structure installation information.", kind="ocr"),
    ]
    current = result("cross_source_comparison", registry)
    answer = mod.render_chatgpt_style_answer_v1_1(
        current,
        f"Compare pages {left} versus {right} for the same technical topic.",
    )
    assert headings(answer) == ["## Answer", "## Evidence", "## Limits"]
    assert left in answer and right in answer
    assert "[1]" in answer and "[2]" in answer
    assert answer.count("**OCR text:**") == 2

