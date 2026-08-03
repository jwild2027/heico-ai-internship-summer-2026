from __future__ import annotations

import copy
import importlib.util
import re
import sys
from pathlib import Path

MODULE_PATH = Path("src/trace_net/writing/trace_net_h30_chatgpt_answer_presentation_v1.py")


def load(name: str = "trace_net_h30_chatgpt_answer_presentation_test"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def entry(
    cid: int,
    cls: str,
    *,
    candidate: str = "",
    page: str = "",
    value: str = "",
    nomenclature=None,
    direct: bool = False,
    kind: str = "",
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
        "authority": "proof" if direct else "guidance",
    }


def result(route: str, registry, *, content: str = "", evidence=None, coverage=None):
    evidence = evidence or {}
    return {
        "route": route,
        "content": content,
        "citation_registry": copy.deepcopy(registry),
        "evidence_envelope": {
            "direct_evidence": copy.deepcopy(evidence.get("direct", [])),
            "candidate_evidence": copy.deepcopy(evidence.get("candidate", [])),
            "visual_guidance": copy.deepcopy(evidence.get("visual", [])),
            "semantic_guidance": copy.deepcopy(evidence.get("semantic", [])),
            "authority_evidence": copy.deepcopy(evidence.get("authority", [])),
            "coverage": copy.deepcopy(coverage or {}),
        },
        "writer_mode": "answer_quality_route_renderer",
        "follow_up_questions": ["Which manual should be searched?"],
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def headings(text: str):
    return [line.strip() for line in text.splitlines() if line.startswith("## ")]


def test_exact_table_hides_raw_ocr_dump_and_uses_three_section_style():
    mod = load("chatgpt_presentation_table")
    registry = [
        entry(
            1,
            "direct_source",
            candidate="120-26948-003",
            page="t_p_120_1176_p000030",
            nomenclature=["SUPPORT"],
            direct=True,
            kind="table",
            value=(
                "embedding_candidate: TRACE-Net OCR page text. OCR status: ok. "
                "Recommended route: table. EMBRAER MAINTENANCE MANUAL WITH "
                "ILLUSTRATED PARTS LIST CH-SEC-UN-FIG PER STOCK 120-26948-003"
            ),
        )
    ]
    current = result(
        "exact_table_ipl_lookup",
        registry,
        content="## Answer\n\nTRACE-Net found citation-ready source evidence: " + registry[0]["value"],
        evidence={"direct": [{"page_id": "t_p_120_1176_p000030", "value": "120-26948-003"}]},
    )
    answer = mod.render_chatgpt_style_answer(current, "Locate part 120-26948-003 in the IPL table.")
    assert headings(answer)[:2] == ["## Answer", "## Evidence"]
    assert "120-26948-003" in answer
    assert "Support" in answer
    assert "t_p_120_1176_p000030" in answer
    assert "[1]" in answer
    assert "embedding_candidate" not in answer
    assert "OCR status" not in answer
    assert "Recommended route" not in answer
    assert "CH-SEC-UN-FIG" not in answer


def test_exact_candidate_is_plain_language_and_keeps_candidate_limit():
    mod = load("chatgpt_presentation_candidate")
    registry = [
        entry(
            1,
            "candidate",
            candidate="120-20970-001",
            page="t_p_120_1176_p000343",
            nomenclature=["STRUCTURE, ARMREST"],
        )
    ]
    current = result("exact_identifier_lookup", registry)
    answer = mod.render_chatgpt_style_answer(current, "Find part 120-20970-001.")
    assert headings(answer) == ["## Answer", "## Evidence", "## Limits"]
    assert "best indexed match" in answer.lower()
    assert "Structure Armrest" in answer
    assert "candidate evidence" in answer
    assert "route" not in answer.lower()


def test_ocr_layout_is_reconstructed_without_raw_dump_or_blur_claim():
    mod = load("chatgpt_presentation_ocr")
    registry = [
        entry(
            1,
            "semantic",
            page="t_p_120_1176_p000005",
            value="- Apr 10/06 25-21-00 607 Sep 30/98 25-LEP",
        )
    ]
    current = result(
        "ocr_scan_recovery",
        registry,
        content=(
            "## Answer\n\n"
            "The strongest indexed match for the supplied OCR clue is page `t_p_120_1176_p000005` [1].\n"
            "- Matched OCR text: '- Apr 10/06 25-21-00 607 Sep 30/98 25-LEP' [1]\n"
            "- The clue appears to combine cells from a List of Effective Pages table rather than one continuous sentence.\n"
            "- Reconstructed row: ATA 25-21-00 — manual page 607 — dated Sep 30/98 [1]\n"
            "- Reconstructed row: Section 25-LEP — dated Apr 10/06 [1]\n"
            "- This is a layout reconstruction from OCR, not a scan-quality or blur classification.\n"
            "- OCR reading order and broken characters should be checked against the page image."
        ),
    )
    answer = mod.render_chatgpt_style_answer(
        current,
        "Locate the scanned page containing this OCR clue and reconstruct the table relationships.",
    )
    assert headings(answer) == ["## Answer", "## Evidence", "## Limits"]
    assert "ATA 25-21-00" in answer
    assert "manual page 607" in answer
    assert "Section 25-LEP" in answer
    assert "Matched OCR text" not in answer
    assert "scan-quality or blur classification" in answer
    for line in answer.splitlines():
        if any(token in line.lower() for token in ("page `", "ata 25-21-00", "section 25-lep")):
            assert "[1]" in line


def test_graph_association_is_not_promoted_to_parent_assembly():
    mod = load("chatgpt_presentation_graph")
    registry = [
        entry(
            1,
            "candidate",
            candidate="120-20970-001",
            page="t_p_120_1176_p000343",
            nomenclature=["STRUCTURE, ARMREST"],
        )
    ]
    current = result("graph_relationship_reasoning", registry)
    answer = mod.render_chatgpt_style_answer(
        current,
        "What assembly is connected to part 120-20970-001?",
    )
    assert "No explicit parent-assembly relationship" in answer
    assert "Structure Armrest" in answer
    assert "does not prove a parent-assembly relationship" in answer
    assert "[1]" in answer


def test_existing_visual_answer_is_reformatted_without_internal_details():
    mod = load("chatgpt_presentation_visual")
    current = result(
        "visual_figure_callout_lookup",
        [entry(1, "page_content", page="t_p_120_1176_p000018", kind="ocr")],
        content=(
            "## Answer\n\n"
            "Page `t_p_120_1176_p000018` contains Figure 2 [1].\n"
            "- Visible labels include Seat backrest, Seat belt, and Ashtray [1].\n"
            "- retrieval_tunnels_used=confirmed_visual\n"
            "### Limits\n"
            "- The current visual record does not resolve every numbered callout [1]."
        ),
    )
    answer = mod.render_chatgpt_style_answer(
        current,
        "Show the diagram on page t_p_120_1176_p000018.",
    )
    assert headings(answer) == ["## Answer", "## Evidence", "## Limits"]
    assert "Seat backrest" in answer
    assert "retrieval_tunnels" not in answer


def strict_validate(answer, query, current, *, extra_allowed=None, registry=None):
    valid = {int(row["citation_id"]) for row in registry or []}
    cited = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    failures = []
    if not cited.issubset(valid):
        failures.append("unknown_citation_id")
    if not cited:
        failures.append("direct_answer_missing_citation")
    return {"accepted": not failures, "quality_status": "PASS" if not failures else "FAIL", "failures": failures}


def test_negative_page_is_allowed_without_fabricating_a_citation():
    mod = load("chatgpt_presentation_negative")
    base = result("document_page_navigation", [], content="old answer")

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
    mod.install_chatgpt_answer_presentation(module)
    output = Runtime().process({"query": "Open page t_p_120_1176_p999999 and explain what it contains."})
    assert output["post_answer_validation"]["accepted"]
    assert output["post_answer_validation"]["negative_result_without_fabricated_citation"]
    assert "t_p_120_1176_p999999" in output["content"]
    assert "[1]" not in output["content"]


def test_install_preserves_auditor_telemetry_and_adds_no_llm_or_retrieval():
    mod = load("chatgpt_presentation_install")
    registry = [entry(1, "candidate", candidate="120-48024-001", page="t_p_120_1176_p000055")]
    base = result("exact_identifier_lookup", registry, content="old answer")
    base["route_plan"] = {"retrieval_tunnels": ["normal_source_truth"]}
    base["timing"] = {"gemma_called": True}

    class Runtime:
        def process(self, payload):
            return copy.deepcopy(base)

        def health(self):
            return {"quality_status": "PASS"}

    module = {
        "Runtime": Runtime,
        "validate_answer": lambda *args, **kwargs: {"accepted": True, "quality_status": "PASS", "failures": []},
        "extract_latest_user": lambda payload: payload["query"],
        "citation_registry": lambda current: current["citation_registry"],
        "citation_registry_digest": lambda registry: "digest",
        "synthesis_allowed_identifiers": lambda query, current: None,
    }
    mod.install_chatgpt_answer_presentation(module)
    output = Runtime().process({"query": "Find part 120-48024-001."})
    assert output["route_plan"] == base["route_plan"]
    assert output["timing"] == base["timing"]
    metadata = output["chatgpt_answer_presentation"]
    assert metadata["gemma_call_count_added"] == 0
    assert metadata["retrieval_changed"] is False
    assert metadata["source_truth_mutation_allowed"] is False
    assert "normal_source_truth" not in output["content"]
