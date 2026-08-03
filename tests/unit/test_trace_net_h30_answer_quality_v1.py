from __future__ import annotations

import copy
import importlib.util
import re
import sys
from pathlib import Path

MODULE_PATH = Path("src/trace_net/validation/trace_net_h30_answer_quality_v1.py")


def load_module(name: str = "trace_net_h30_answer_quality_test"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def registry_entry(cid, cls, *, value="", candidate="", page="", nomenclature=None, page_content=False, kind=""):
    return {
        "citation_id": cid,
        "class": cls,
        "value": value,
        "identifier_blob": value,
        "candidate_value": candidate,
        "page_id": page,
        "page_ids": [page] if page else [],
        "nomenclature": nomenclature or [],
        "page_content": page_content,
        "page_content_kind": kind,
        "authority": "supporting" if kind in {"ocr", "table"} else "guidance",
        "can_prove_claims": False,
        "guidance_only": kind not in {"ocr", "table"},
    }


def base_result(route, registry, *, content="old answer", page_pack=None):
    result = {
        "route": route,
        "content": content,
        "writer_mode": "old_writer",
        "post_answer_validation": {
            "accepted": False,
            "quality_status": "FAIL",
            "failures": ["stale_failure"],
        },
        "citation_registry": copy.deepcopy(registry),
        "evidence_envelope": {
            "direct_evidence": [],
            "candidate_evidence": [],
            "semantic_guidance": [],
            "visual_guidance": [],
            "coverage": {},
        },
        "follow_up_questions": [
            "Which manual, aircraft, assembly, or document family should be searched?",
            "Are you trying to identify it, find its function, or verify approval?",
        ],
        "answer_permission": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed": False,
    }
    if page_pack is not None:
        result["evidence_envelope"]["coverage"]["page_content"] = {
            "available": True,
            "pages": [page_pack],
            "telemetry": {"exact_page_match": True},
        }
    return result


def simple_validate(answer, query, result, *, extra_allowed=None, registry=None):
    registry = list(registry or [])
    valid = {int(row["citation_id"]) for row in registry}
    cited = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    failures = []
    if not cited.issubset(valid):
        failures.append("unknown_citation_id")
    if "approved replacement" in answer.lower():
        failures.append("dangerous_claim_without_explicit_authority")
    return {
        "accepted": not failures,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }


def install_and_run(result, question):
    quality = load_module("trace_net_h30_answer_quality_overlay_test_" + str(abs(hash(question))))

    class FakeRuntime:
        def process(self, payload):
            return copy.deepcopy(result)

        def health(self):
            return {"quality_status": "PASS"}

    def citation_registry(current):
        return current["citation_registry"]

    def citation_digest(registry):
        return "digest"

    def latest_user(payload):
        return payload["messages"][-1]["content"]

    quality.install_answer_quality({
        "Runtime": FakeRuntime,
        "citation_registry": citation_registry,
        "citation_registry_digest": citation_digest,
        "validate_answer": simple_validate,
        "extract_latest_user": latest_user,
        "synthesis_allowed_identifiers": lambda query, current: None,
    })
    return FakeRuntime().process({"messages": [{"role": "user", "content": question}]})


def test_q11_semantic_ata_is_revalidated_after_final_render():
    registry = [
        registry_entry(1, "semantic", value="ATA 51-25-00 summary", page="t_p_120_1176_p000047"),
        registry_entry(2, "semantic", value="ATA 51-25-00 summary", page="t_p_120_1176_p000005"),
    ]
    result = base_result(
        "ata_system_discovery",
        registry,
        content=(
            "TRACE-Net found guidance only.\n\n"
            "Helpful follow-up questions:\n"
            "- What is the complete part number?"
        ),
    )
    output = install_and_run(
        result,
        "Find the relevant parts and source pages in ATA 51-25-00.",
    )
    assert output["post_answer_validation"]["accepted"]
    assert "t_p_120_1176_p000047" in output["content"]
    assert "[1]" in output["content"]
    assert "Helpful follow-up questions:" not in output["content"]


def test_q12_candidate_uses_current_registry_citation():
    registry = [
        registry_entry(
            1,
            "candidate",
            candidate="120-26948-003",
            page="t_p_120_1176_p000029",
            nomenclature=["SUPPORT . CC CCCCCESTSTEEEEEE"],
        )
    ]
    result = base_result(
        "exact_table_ipl_lookup",
        registry,
        content="old candidate answer [22]",
    )
    output = install_and_run(result, "Locate part 120-26948-003 in the IPL table.")
    assert output["post_answer_validation"]["accepted"]
    assert "[1]" in output["content"]
    assert "[22]" not in output["content"]
    assert "120-26948-003" in output["content"]


def test_internal_status_and_entity_gate_text_is_hidden():
    quality = load_module("trace_net_h30_answer_quality_internal_test")
    cleaned = quality._strip_internal_lines(
        "Useful line\n- entity_gate_removed_12_semantic_guidance_row(s)\n"
        "- guided_nomenclature_candidates returned status 599\nFinal line"
    )
    assert cleaned == "Useful line\nFinal line"


def test_corrupted_nomenclature_is_cleaned():
    quality = load_module("trace_net_h30_answer_quality_nomenclature_test")
    assert quality._clean_nomenclature("PIN, ATTACH. ESE") == "Pin Attach"
    cleaned = quality._clean_nomenclature("SUPPORT . CC CCCCCESTSTEEEEEE")
    assert cleaned == "Support"
    assert quality._clean_nomenclature("SARY, USING THE INSTALLED") == ""


def test_visual_page_is_summarized_not_dumped():
    quality = load_module("trace_net_h30_answer_quality_visual_test")
    ocr = {
        "text": (
            "EMBRAER MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST "
            "SEAT BACKRESTS SEAT BELT ASHTRAY FLOATABLE SEAT BOTTOM "
            "120TP250002.MCE Double Passenger Seat Figure 2 EFFECTIVITY: ALL"
        ),
        "citation_id": 1,
    }
    visual = {
        "text": "Visual observation referencing figure 2 (unlinked_visual_candidate)",
        "citation_id": 4,
    }
    pack = {
        "page_id": "t_p_120_1176_p000018",
        "ocr": [ocr],
        "visuals": [visual],
        "v1_context": [],
        "v2_context": [],
        "v3_page_intelligence": [],
    }
    answer = quality._render_visual_page(pack)
    assert "Seat backrest" in answer
    assert "Seat belt" in answer
    assert "120TP250002.MCE" in answer
    assert "Figure 2" in answer
    assert "calibrated cascade" not in answer
    assert "unlinked_visual_candidate" not in answer
    assert len(answer) < 1200


def test_procedure_page_becomes_bullets():
    quality = load_module("trace_net_h30_answer_quality_procedure_test")
    text = (
        "MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST "
        "(a) Remove the coat of paint from the seat region. "
        "(b) Withdraw the fasteners without damaging the holes. "
        "(c) Install the new lateral leg structure (P/N 120-29073-006). "
        "EFFECTIVITY: ALL 25-21-00"
    )
    pack = {
        "page_id": "t_p_120_1176_p000482",
        "ocr": [{"text": text, "citation_id": 1}],
    }
    answer = quality._render_procedure_page(pack)
    assert "- a. Remove the coat of paint" in answer
    assert "- b. Withdraw the fasteners" in answer
    assert "- c. Install the new lateral leg structure" in answer
    assert "EFFECTIVITY" not in answer
    assert "[1]" in answer


def test_graph_question_directly_states_missing_relationship():
    quality = load_module("trace_net_h30_answer_quality_graph_test")
    registry = [
        registry_entry(
            1,
            "candidate",
            candidate="120-20970-001",
            page="t_p_120_1176_p000010",
            nomenclature=["STRUCTURE, ARMREST"],
        )
    ]
    answer = quality._render_graph_relationship(
        "What assembly is connected to part 120-20970-001?",
        registry,
    )
    assert "No explicit assembly relationship" in answer
    assert "Structure Armrest" in answer
    assert "[1]" in answer


def test_ocr_question_directly_returns_best_page_and_uncertainty():
    quality = load_module("trace_net_h30_answer_quality_ocr_test")
    registry = [
        registry_entry(
            1,
            "semantic",
            value="- Apr 10/06 25-21-00 607 Sep 30/98 25-LEP",
            page="t_p_120_1176_p000005",
        )
    ]
    answer = quality._render_ocr_recovery(
        "Recover the text containing this OCR clue: '- Apr 10/06 25-21-00 607 Sep 30/98 25-LEP'.",
        registry,
    )
    assert "t_p_120_1176_p000005" in answer
    assert "Matched OCR text" in answer
    assert "checked against the page image" in answer
    assert "[1]" in answer


def test_specific_request_suppresses_generic_followups():
    registry = [
        registry_entry(
            1,
            "candidate",
            candidate="120-48024-001",
            page="t_p_120_1176_p000055",
            nomenclature=["RING, LOCKING"],
        )
    ]
    result = base_result("nomenclature_function_search", registry)
    output = install_and_run(
        result,
        "Find the ring in the document set and show connected pages.",
    )
    assert output["follow_up_questions"] == []
    assert "Helpful follow-up questions:" not in output["content"]


def test_negative_part_and_page_do_not_substitute_unrelated_evidence():
    quality = load_module("trace_net_h30_answer_quality_negative_test")
    unrelated = [
        registry_entry(1, "semantic", value="unrelated summary", page="t_p_120_1176_p000001")
    ]
    part_answer = quality._render_candidate_route(
        "Find part 999-99999-999.",
        unrelated,
        "exact_identifier_lookup",
    )
    assert "No indexed match" in part_answer
    assert "t_p_120_1176_p000001" not in part_answer

    result = base_result("document_page_navigation", unrelated)
    page_answer = quality._render_negative_page(
        "Open page t_p_120_1176_p999999 and explain what it contains.",
        result,
    )
    assert "was not found" in page_answer
    assert "No other page was substituted" in page_answer
