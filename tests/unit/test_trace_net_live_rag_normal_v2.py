from __future__ import annotations
import importlib.util, sys
from pathlib import Path

SCRIPT = Path("scripts/operations/serving/serve_trace_net_live_rag_normal_v2.py")

def load():
    spec = importlib.util.spec_from_file_location("normal_v2", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["normal_v2"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

def base_raw():
    return {
        "retrieval": {"direct_evidence": [{"citation_id":1,"page_id":"t_p_x_p000001","field_name":"part_number","normalized_value":"120-41824-003","document_id":"d1"}], "total_match_count":1,"returned_match_count":1,"result_was_capped":False},
        "guidance": {"graph_guidance":[{}], "v2_summary_guidance":[{}]},
        "final_answer":"Deterministic answer [1].",
        "llm_draft_text":"Gemma found part 120-41824-003 on t_p_x_p000001 [1].",
        "llm_status":"LLM_CALL_SUCCEEDED",
        "final_gate_status":"LIVE_ORCHESTRATOR_FINAL_GATE_PASS",
        "final_answer_ready_for_webui":True,
    }

def test_source_citations_are_not_inferred_from_answer():
    mod = load()
    raw = base_raw()
    raw["retrieval"]["direct_evidence"][0]["normalized_value"] = ""
    result = mod.compose_result("Find part 120-41824-003", raw)
    assert result["citation_count"] == 0
    assert result["final_answer_ready_for_webui"] is False
    assert "source-backed citation" in result["content"]

def test_safe_llm_draft_can_be_used():
    mod = load()
    result = mod.compose_result("Find part 120-41824-003", base_raw())
    assert result["llm_draft_used"] is True
    assert result["citation_count"] == 1

def test_unsupported_draft_falls_back():
    mod = load()
    raw = base_raw()
    raw["llm_draft_text"] = "Gemma found part 999-99999-999 [1]."
    result = mod.compose_result("Find part 120-41824-003", raw)
    assert result["llm_draft_used"] is False
    assert "unsupported_part_number" in " ".join(result["llm_draft_validation_failures"])

def test_dangerous_claim_without_authority_is_blocked():
    mod = load()
    raw = base_raw()
    raw["llm_draft_text"] = "Part 120-41824-003 is interchangeable [1]."
    result = mod.compose_result("Is it interchangeable?", raw)
    assert result["llm_draft_used"] is False
