from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path("src/trace_net/writing/answer_contracts/trace_net_h30_public_answer_contract_v1.py")


def load(name="trace_net_h30_public_answer_contract_test"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_shared_parser_reads_answer_evidence_limits_once():
    mod = load("public_contract_parser")
    parsed = mod.parse_public_answer(
        "## Answer\n\nDirect result [1].\n\n"
        "## Evidence\n\n- Part `120-20970-003` on page `t_p_x_p000001` [1]\n\n"
        "## Limits\n\n- One association remains guidance-level."
    )
    assert parsed["heading_order"] == ["Answer", "Evidence", "Limits"]
    assert parsed["sections"]["Answer"] == ["Direct result [1]."]
    assert parsed["sections"]["Evidence"] == ["Part `120-20970-003` on page `t_p_x_p000001` [1]"]
    assert parsed["sections"]["Limits"] == ["One association remains guidance-level."]
    assert parsed["unknown_headings"] == []


def test_renderer_omits_limits_when_there_is_no_material_limit():
    mod = load("public_contract_renderer")
    answer = mod.render_public_answer(
        "Part `120-26948-003` appears in the IPL table [1].",
        ["Page `t_p_x_p000030` [1]"],
        [],
    )
    assert answer.splitlines()[0] == "## Answer"
    assert "## Evidence" in answer
    assert "## Limits" not in answer


def test_canonicalizer_deduplicates_evidence_and_normalizes_heading_level():
    mod = load("public_contract_canonicalizer")
    result = mod.canonicalize_public_answer(
        "### Answer\nResult [1].\n"
        "### Evidence\n- Page `t_p_x_p000001` [1]\n- Page `t_p_x_p000001` [1]"
    )
    assert result["content"].startswith("## Answer")
    assert result["content"].count("Page `t_p_x_p000001` [1]") == 1
    assert result["changed"]


def test_validator_rejects_internal_leak_and_unexpected_heading():
    mod = load("public_contract_leaks")
    validation = mod.validate_public_answer_contract(
        "## Answer\nResult [1].\n"
        "## Evidence\n- writer_mode=internal [1]\n"
        "## Engineering confidence\n90%",
        route="exact_identifier_lookup",
    )
    assert not validation["accepted"]
    assert "unexpected_heading:Engineering confidence" in validation["failures"]
    assert "public_leak:writer_mode" in validation["failures"]
    assert "public_leak:engineering_confidence" in validation["failures"]


def test_negative_result_is_structurally_valid_without_fabricated_citation():
    mod = load("public_contract_negative")
    answer = (
        "## Answer\n\nPage `t_p_x_p999999` was not found in the indexed document set.\n\n"
        "## Evidence\n\n- No matching indexed page record was returned."
    )
    validation = mod.validate_public_answer_contract(answer, route="document_page_navigation")
    assert validation["accepted"]


def test_install_canonicalizes_technical_answer_and_preserves_prior_validation():
    mod = load("public_contract_install")
    base = {
        "route": "exact_table_ipl_lookup",
        "content": "### Answer\nPart `120-26948-003` appears in the table [1].\n### Evidence\n- Page `t_p_x_p000030` [1]",
        "post_answer_validation": {"accepted": True, "quality_status": "PASS", "failures": []},
        "writer_mode": "prior_writer",
        "answer_permission": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed": False,
    }

    class Runtime:
        def process(self, payload):
            return copy.deepcopy(base)

        def health(self):
            return {"quality_status": "PASS"}

    namespace = {"Runtime": Runtime}
    mod.install_public_answer_contract(namespace)
    output = Runtime().process({"query": "Locate part 120-26948-003."})
    assert output["content"].startswith("## Answer")
    assert "### Answer" not in output["content"]
    assert output["post_answer_validation"]["accepted"]
    assert output["public_answer_contract"]["protected_tokens_preserved"]
    assert output["public_answer_contract"]["gemma_call_count_added"] == 0
    assert output["public_answer_contract"]["retrieval_changed"] is False


def test_install_never_promotes_a_prior_validation_failure():
    mod = load("public_contract_no_promotion")
    base = {
        "route": "exact_identifier_lookup",
        "content": "## Answer\nResult [1].\n## Evidence\n- Part `120-20970-003` [1]",
        "post_answer_validation": {"accepted": False, "quality_status": "FAIL", "failures": ["unsupported_identifier"]},
    }

    class Runtime:
        def process(self, payload):
            return copy.deepcopy(base)

        def health(self):
            return {"quality_status": "PASS"}

    namespace = {"Runtime": Runtime}
    mod.install_public_answer_contract(namespace)
    output = Runtime().process({"query": "Find part 120-20970-003."})
    assert not output["post_answer_validation"]["accepted"]
    assert "unsupported_identifier" in output["post_answer_validation"]["failures"]


def test_nontechnical_general_chat_is_unchanged():
    mod = load("public_contract_general")
    base = {
        "route": "safe_general_chat",
        "content": "Hello there.",
        "post_answer_validation": {"accepted": True, "quality_status": "PASS", "failures": []},
    }

    class Runtime:
        def process(self, payload):
            return copy.deepcopy(base)

        def health(self):
            return {"quality_status": "PASS"}

    namespace = {"Runtime": Runtime}
    mod.install_public_answer_contract(namespace)
    output = Runtime().process({"query": "Hello"})
    assert output["content"] == "Hello there."
    assert output["public_answer_contract"]["applied"] is False
