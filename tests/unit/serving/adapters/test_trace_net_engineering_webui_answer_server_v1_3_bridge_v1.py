import json
from pathlib import Path

from tiff.trace_net_engineering_webui_answer_server_v1 import LLMConfig
from tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 import (
    BridgeConfig,
    _ensure_bridge_stage_dirs,
    _patch_stage_writer_parent_dirs_for_in_process_bridge,
    answer_question_with_bridge_v1,
    bridge_failure_record,
    merge_bridge_trace,
)


def _bridge_payload(status="skipped_not_needed"):
    return {
        "status": "TRACE_NET_WEBUI_SELF_RAG_CRAG_BRIDGE_BUILT",
        "quality_status": "PASS",
        "summary": {
            "used_tools": ["query_planner", "context_pack_builder", "self_rag", "graph_leiden"],
            "crag_retry_plan_count": 0,
            "self_rag_ready_for_gemma_draft_count": 1,
            "self_rag_crag_retry_required_count": 0,
            "context_pack_count": 1,
            "total_evidence_capsule_count": 30,
            "total_high_signal_evidence_capsule_count": 30,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "tool_statuses": {
            "query_planner": "used",
            "context_pack_builder": "used",
            "self_rag": "used",
            "crag_retry": status,
            "route_dispatch": "used",
            "table_route": "used",
            "page_context_v2": "used",
            "graph_leiden": "used",
        },
        "checklist_text": "Self-RAG: used\nCRAG retry: skipped_not_needed\ngraph/leiden: used",
    }


def test_merge_bridge_trace_adds_e2e_visible_signals(tmp_path):
    answer = {
        "question": "Find part number 120-29073-001",
        "response_text": "answer",
        "response_kind": "gemma4_composed_gated_lookup",
        "answer_permission": True,
    }
    merged = merge_bridge_trace(answer, _bridge_payload(), bridge_report_path=tmp_path / "bridge.json")

    assert merged["webui_self_rag_crag_bridge_used"] is True
    assert merged["query_planner_used"] is True
    assert merged["context_pack_builder_used"] is True
    assert merged["self_rag_used"] is True
    assert merged["crag_retry_status"] == "skipped_not_needed"
    assert merged["crag_retry_evaluated"] is True
    assert merged["webui_self_rag_crag_bridge_tool_statuses"]["graph_leiden"] == "used"
    assert merged["answer_permission"] is False
    assert merged["source_truth_mutation_allowed"] is False
    assert "Self-RAG" in merged["webui_self_rag_crag_bridge_checklist_text"]


def test_answer_question_runs_bridge_before_existing_answer(monkeypatch, tmp_path):
    calls = []

    def fake_bridge(question, config, output_dir=None):
        calls.append(("bridge", question))
        return _bridge_payload(), tmp_path / "bridge.json"

    def fake_answer_question_v13(*, question, pages, gated_drafts, llm_config):
        calls.append(("answer", question))
        return {
            "question": question,
            "response_text": "TRACE-Net answer",
            "response_kind": "gemma4_composed_gated_lookup",
            "llm_called": True,
            "answer_permission": False,
        }

    import tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 as mod

    monkeypatch.setattr(mod, "run_bridge_preflight", fake_bridge)
    monkeypatch.setattr(mod, "answer_question_v13", fake_answer_question_v13)

    record = answer_question_with_bridge_v1(
        question="Find part number 120-29073-001",
        pages=[],
        gated_drafts=[],
        llm_config=LLMConfig(mode="off"),
        bridge_config=BridgeConfig(kernel_path=tmp_path / "kernel.json", output_dir=tmp_path),
    )

    assert calls[0][0] == "bridge"
    assert calls[1][0] == "answer"
    assert record["webui_self_rag_crag_bridge_used"] is True
    assert record["llm_called"] is True


def test_bridge_failure_blocks_answer_when_required(monkeypatch, tmp_path):
    def fake_bridge(question, config, output_dir=None):
        raise RuntimeError("boom")

    def fake_answer_question_v13(**kwargs):  # pragma: no cover - should not be called
        raise AssertionError("answer should not run when bridge fails")

    import tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 as mod

    monkeypatch.setattr(mod, "run_bridge_preflight", fake_bridge)
    monkeypatch.setattr(mod, "answer_question_v13", fake_answer_question_v13)

    record = answer_question_with_bridge_v1(
        question="any question",
        pages=[],
        gated_drafts=[],
        llm_config=LLMConfig(mode="off"),
        bridge_config=BridgeConfig(kernel_path=tmp_path / "kernel.json", output_dir=tmp_path, allow_answer_if_bridge_fails=False),
    )

    assert record["response_kind"] == "controlled_bridge_preflight_block"
    assert record["llm_called"] is False
    assert record["answer_permission"] is False
    assert "Self-RAG/CRAG preflight bridge did not pass" in record["response_text"]


def test_bridge_failure_record_is_safe():
    record = bridge_failure_record("q", error="bad")
    assert record["answer_permission"] is False
    assert record["can_answer_directly"] is False
    assert record["can_prove_claims"] is False
    assert record["source_truth_mutation_allowed"] is False
    assert record["postgres_write_attempt"] is False
    assert record["qdrant_write_attempt"] is False
    assert record["opensearch_write_attempt"] is False


def test_run_bridge_preflight_uses_cli_fallback_when_in_process_bridge_raises(monkeypatch, tmp_path):
    import tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 as mod

    def boom(**kwargs):
        raise RuntimeError("in-process mismatch")

    def fake_run(cmd, text, capture_output):
        out_dir = Path(cmd[cmd.index("--output-dir") + 1])
        payload = _bridge_payload()
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / mod.BRIDGE_REPORT_NAME).write_text(json.dumps(payload), encoding="utf-8")

        class Result:
            returncode = 0
            stdout = "Quality status: PASS"
            stderr = ""

        return Result()

    monkeypatch.setattr(mod, "build_webui_self_rag_crag_bridge", boom)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    payload, report_path = mod.run_bridge_preflight(
        "Find part number 120-29073-001",
        BridgeConfig(kernel_path=tmp_path / "kernel.json", output_dir=tmp_path, cli_fallback_enabled=True),
        output_dir=tmp_path / "bridge_run",
    )

    assert report_path.exists()
    assert payload["quality_status"] == "PASS"
    assert payload["cli_fallback_used"] is True
    assert "in-process mismatch" in payload["in_process_error"]


def test_ensure_bridge_stage_dirs_creates_all_nested_stage_outputs(tmp_path):
    target = tmp_path / "sample_bridge_preflight"
    _ensure_bridge_stage_dirs(target)

    for name in (
        "query_planner",
        "context_pack_blueprint",
        "context_pack_builder",
        "self_rag_check",
        "crag_retry_plan",
    ):
        assert (target / "stage_reports" / name).is_dir()


def test_run_bridge_preflight_precreates_stage_dirs_before_in_process_call(monkeypatch, tmp_path):
    import tiff.trace_net_engineering_webui_answer_server_v1_3_bridge_v1 as mod

    seen = {}

    def fake_bridge(**kwargs):
        out = Path(kwargs["output_dir"])
        seen["stage_dir_exists"] = (out / "stage_reports" / "context_pack_blueprint").is_dir()
        payload = _bridge_payload()
        payload["cli_fallback_used"] = False
        (out / mod.BRIDGE_REPORT_NAME).parent.mkdir(parents=True, exist_ok=True)
        (out / mod.BRIDGE_REPORT_NAME).write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(mod, "build_webui_self_rag_crag_bridge", fake_bridge)

    payload, report_path = mod.run_bridge_preflight(
        "Find part number 120-29073-001",
        BridgeConfig(kernel_path=tmp_path / "kernel.json", output_dir=tmp_path, cli_fallback_enabled=False),
        output_dir=tmp_path / "bridge_run",
    )

    assert seen["stage_dir_exists"] is True
    assert payload["quality_status"] == "PASS"
    assert report_path.name == mod.BRIDGE_REPORT_NAME


def test_stage_writer_parent_dir_patch_makes_blueprint_jsonl_safe(tmp_path):
    from tiff import trace_net_engineering_context_pack_blueprint_v1 as blueprint

    _patch_stage_writer_parent_dirs_for_in_process_bridge()
    out = tmp_path / "missing" / "nested" / "records.jsonl"
    blueprint._write_jsonl(out, [{"ok": True}])

    assert out.exists()
    assert out.read_text(encoding="utf-8").strip() == '{"ok": true}'
