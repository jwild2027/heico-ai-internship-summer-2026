from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_live_llm_draft_adapter_v22 import (
    LlmConfig,
    build_report,
    render_markdown,
    write_report_files,
)


def sample_prompt_contract_report(count: int = 5):
    contracts = []
    for i in range(1, count + 1):
        query = f"Find part number 120-0000{i}-001"
        context = f"""TRACE-NET CONTEXT PACK

SOURCE-TRUTH EVIDENCE (direct proof authority; cite these for factual claims):
- [1] page=p{i:04d} field=covered_part_number value=120-0000{i}-001

NEARBY SOURCE-TRUTH CONTEXT (source-truth records, but not direct query matches; use cautiously):
- None

GRAPH / LEIDEN GUIDANCE (navigation only; not proof):
[]

V2 SUMMARY GUIDANCE (meaning/compression only; not proof):
[]

AGGREGATION / CAPPING METADATA:
{{
  "total_match_count": 1,
  "returned_match_count": 1,
  "result_was_capped": false,
  "more_results_available": false,
  "high_degree_node_detected": false
}}

SELF-RAG / CRAG STATUS:
{{"self_rag_status":"CONTEXT_READY_FOR_LLM","crag_status":"NO_RETRY_NEEDED"}}

ANSWER RULES:
{{"cite_every_factual_claim": true}}
"""
        contracts.append(
            {
                "prompt_contract_id": f"contract_{i}",
                "context_pack_id": f"pack_{i}",
                "user_query": query,
                "prompt_contract_status": "PROMPT_CONTRACT_READY_FOR_LLM_DRAFT",
                "ready_for_llm_draft": True,
                "messages": [
                    {"role": "system", "content": "Use source-truth evidence only."},
                    {"role": "user", "content": query},
                    {"role": "user", "content": context},
                ],
            }
        )
    return {"prompt_contracts": contracts}


def thresholds():
    return {
        "min_prompt_contracts": 5,
        "min_llm_drafts": 5,
        "min_drafts_ready_for_final_gate": 5,
        "min_drafts_with_nonempty_content": 5,
        "min_source_truth_supported_prompts": 5,
        "min_successful_llm_calls": 5,
        "min_live_llm_calls": 0,
        "min_simulated_llm_drafts": 5,
        "max_llm_call_errors": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_no_answer_permission": True,
    }


def test_v22_simulated_drafts_ready_for_final_gate():
    report = build_report(sample_prompt_contract_report(), config=LlmConfig(mode="simulate"), thresholds=thresholds())
    assert report["quality_status"] == "PASS"
    assert report["llm_draft_count"] == 5
    assert report["drafts_ready_for_final_gate_count"] == 5
    assert report["simulated_llm_draft_count"] == 5
    assert report["live_llm_call_count"] == 0
    assert "[1]" in report["llm_drafts"][0]["draft_text"]
    assert report["llm_drafts"][0]["requires_final_gate"] is True


def test_v22_quality_fails_on_llm_call_errors_threshold():
    th = thresholds()
    th["min_simulated_llm_drafts"] = 0
    th["min_successful_llm_calls"] = 0
    th["min_drafts_ready_for_final_gate"] = 0
    th["min_drafts_with_nonempty_content"] = 0
    report = build_report(sample_prompt_contract_report(count=1), config=LlmConfig(mode="unknown"), thresholds=th)
    assert report["quality_status"] == "FAIL"
    assert report["llm_call_error_count"] == 1


def test_v22_ollama_call_can_be_monkeypatched(monkeypatch):
    import tiff.trace_net_e2e_live_llm_draft_adapter_v22 as mod

    def fake_call(**kwargs):
        return "TRACE-Net found the requested evidence [1].", {"reasoning_present": True, "reasoning_omitted_from_draft": True}

    monkeypatch.setattr(mod, "_call_openai_compatible_llm", fake_call)
    th = thresholds()
    th.update({"min_live_llm_calls": 1, "min_simulated_llm_drafts": 0, "min_prompt_contracts": 1, "min_llm_drafts": 1, "min_successful_llm_calls": 1, "min_drafts_ready_for_final_gate": 1, "min_drafts_with_nonempty_content": 1, "min_source_truth_supported_prompts": 1})
    report = build_report(sample_prompt_contract_report(count=1), config=LlmConfig(mode="ollama", model="gemma4:26b"), thresholds=th)
    assert report["quality_status"] == "PASS"
    assert report["live_llm_call_count"] == 1
    assert report["llm_reasoning_omitted_count"] == 1
    assert report["llm_drafts"][0]["draft_text"] == "TRACE-Net found the requested evidence [1]."


def test_v22_writes_report_files(tmp_path: Path):
    report = build_report(sample_prompt_contract_report(), config=LlmConfig(mode="simulate"), thresholds=thresholds())
    paths = write_report_files(report, tmp_path)
    assert Path(paths["report_path"]).exists()
    assert Path(paths["drafts_jsonl_path"]).exists()
    assert Path(paths["inspect_md_path"]).exists()
    loaded = json.loads(Path(paths["report_path"]).read_text(encoding="utf-8"))
    assert loaded["module"] == "trace_net_e2e_live_llm_draft_adapter_v22"


def test_v22_markdown_mentions_final_gate():
    report = build_report(sample_prompt_contract_report(), config=LlmConfig(mode="simulate"), thresholds=thresholds())
    md = render_markdown(report)
    assert "Live LLM Draft Adapter v22" in md
    assert "final gate" in md.lower()
