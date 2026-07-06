from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tiff.trace_net_openwebui_page_context_bridge_v1 import (
    PageContextArtifactPaths,
    PageContextBridgeHandler,
    PageContextBridgeServer,
    count_pack_records,
    enrich_openai_messages,
    extract_page_numbers,
    latest_user_question,
    render_page_context_binder,
    render_page_context_fallback_answer,
    should_use_context_bridge_fallback,
    should_use_page_context,
)
from scripts.check_trace_net_openwebui_page_context_bridge_v1_quality import check_quality


def sample_pack() -> dict:
    return {
        "quality_status": "PASS",
        "query_entities": {
            "question": "write a paragraph about pages 48 and 202",
            "pages": [48, 202],
            "intent": "page_lookup",
        },
        "summary": {
            "selected_page_count": 2,
            "source_trace_ready_page_count": 2,
            "proof_record_count": 2,
            "guidance_record_count": 9,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "reasoning_work_order": {
            "model_should_think": True,
            "purpose": "Give the LLM a source-bounded binder plus reasoning tasks, not a canned answer.",
            "allowed_reasoning": [
                "Synthesize across multiple proof records when the cited evidence supports the claim.",
                "State bounded inferences clearly as inferences and tie them back to source-traceable records.",
            ],
            "disallowed_reasoning": [
                "Do not infer interchangeability, fit, effectivity, replacement approval, installation safety, or procurement authority without explicit source proof."
            ],
            "answer_sections": ["Answer", "Evidence", "Engineering confidence", "Limits"],
        },
        "page_context_records": [
            {
                "page_number": 48,
                "page_id": "t_p_120_1176_p000048",
                "primary_route": "table",
                "source_trace_ready": True,
                "proof_record_count": 1,
                "guidance_record_count": 5,
                "source_files": [
                    {"route": "source_file", "value": "00000048.tif", "citation_ready": True}
                ],
                "route_evidence_priority": ["source_files", "table_evidence", "ocr_excerpts"],
                "page_reasoning_tasks": [
                    "Use this page only within its source-trace limits.",
                    "Prioritize table/OCR/source-file evidence; do not invent missing rows or quantities.",
                ],
                "route_guidance": [
                    {"can_be_used_as_proof": False, "route": "table_candidate", "text": "candidate table guidance"}
                ],
                "vector_guidance": [
                    {"can_be_used_as_proof": False, "route": "vector_hit", "text": "retrieval guidance only"}
                ],
            },
            {
                "page_number": 202,
                "page_id": "t_p_120_1176_p000202",
                "primary_route": "image_visual",
                "source_trace_ready": True,
                "proof_record_count": 1,
                "guidance_record_count": 4,
                "source_files": [
                    {"route": "source_file", "value": "00000202.tif", "citation_ready": True}
                ],
                "route_evidence_priority": ["source_files", "visual_guidance", "ocr_excerpts"],
                "page_reasoning_tasks": [
                    "Use visual observations as guidance for what the page may depict; require OCR/source proof for factual source claims."
                ],
                "visual_guidance": [
                    {"can_be_used_as_proof": False, "summary": "possible visual diagram guidance"}
                ],
            },
        ],
    }


def test_extract_page_numbers_requires_page_cue_and_avoids_part_numbers() -> None:
    assert extract_page_numbers("write about pages 48 and 202") == [48, 202]
    assert extract_page_numbers("show page p000202") == [202]
    assert extract_page_numbers("show p000202") == [202]
    assert extract_page_numbers("pages p000048 and p000202") == [48, 202]
    assert extract_page_numbers("Find part number 120-50645-005") == []
    assert extract_page_numbers("pages 48-50") == [48, 49, 50]
    assert extract_page_numbers("pages p000048-p000050") == [48, 49, 50]


def test_should_use_page_context() -> None:
    assert should_use_page_context("write a paragraph about pages 48 and 202")
    assert should_use_page_context("pick a random page")
    assert not should_use_page_context("Find part number 120-50645-005")


def test_latest_user_question_reads_last_user_message() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "pages 48 and 202"},
    ]
    assert latest_user_question(messages) == "pages 48 and 202"


def test_render_page_context_binder_contains_reasoning_and_safety() -> None:
    binder = render_page_context_binder(sample_pack())
    assert "TRACE-NET PAGE CONTEXT BINDER V3" in binder
    assert "model_should_think: True" in binder
    assert "t_p_120_1176_p000048" in binder
    assert "t_p_120_1176_p000202" in binder
    assert "Do not infer interchangeability" in binder
    assert "retrieval guidance only" in binder


def test_enrich_openai_messages_inserts_binder_after_system() -> None:
    messages = [
        {"role": "system", "content": "existing system"},
        {"role": "user", "content": "write about pages 48 and 202"},
    ]
    enriched = enrich_openai_messages(messages, sample_pack())
    assert len(enriched) == 3
    assert enriched[0]["content"] == "existing system"
    assert enriched[1]["role"] == "system"
    assert "TRACE-NET PAGE CONTEXT BINDER V3" in enriched[1]["content"]
    assert enriched[2]["role"] == "user"


def test_count_pack_records() -> None:
    counts = count_pack_records(sample_pack())
    assert counts["selected_page_count"] == 2
    assert counts["proof_record_count"] == 2
    assert counts["answer_permission_count"] == 0


def test_quality_checker_accepts_safe_preflight_manifest() -> None:
    manifest = {
        "bridge_meta": {
            "page_context_used": True,
            "context_pack_quality_status": "PASS",
            "context_pack_summary": sample_pack()["summary"],
        },
        "enriched_messages_preview": [
            {"role": "system", "content": render_page_context_binder(sample_pack())}
        ],
    }
    result = check_quality(manifest, min_pages=2)
    assert result["quality_status"] == "PASS"
    assert result["failure_reasons"] == []


def test_quality_checker_rejects_missing_binder() -> None:
    manifest = {
        "bridge_meta": {
            "page_context_used": True,
            "context_pack_quality_status": "PASS",
            "context_pack_summary": sample_pack()["summary"],
        },
        "enriched_messages_preview": [{"role": "user", "content": "pages 48 and 202"}],
    }
    result = check_quality(manifest, min_pages=2)
    assert result["quality_status"] == "FAIL"
    assert "binder_preview_missing" in result["failure_reasons"]


def test_artifact_paths_reports_missing_paths(tmp_path: Path) -> None:
    paths = PageContextArtifactPaths(route_manifest="missing-route.json")
    assert "missing-route.json" in paths.missing_paths(tmp_path)



def test_context_bridge_fallback_detects_simulated_off_topic_response() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "TRACE-Net found evidence on page t_p_120_1176_p000003.",
                }
            }
        ],
        "trace_net": {"llm_status": "LLM_SIMULATED", "llm_called": False},
    }
    meta = {
        "page_context_used": True,
        "detected_pages": [48, 202],
        "context_pack_page_ids": ["t_p_120_1176_p000048", "t_p_120_1176_p000202"],
    }
    should_fallback, reason = should_use_context_bridge_fallback(response, meta)
    assert should_fallback
    assert reason == "upstream_llm_simulated_or_not_called"


def test_context_bridge_fallback_accepts_page_aligned_real_response() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Page 48 and page 202 are both present in the binder.",
                }
            }
        ],
        "trace_net": {"llm_status": "LLM_OK", "llm_called": True},
    }
    meta = {
        "page_context_used": True,
        "detected_pages": [48, 202],
        "context_pack_page_ids": ["t_p_120_1176_p000048", "t_p_120_1176_p000202"],
    }
    should_fallback, reason = should_use_context_bridge_fallback(response, meta)
    assert not should_fallback
    assert reason == "upstream_response_page_aligned"


def test_render_page_context_fallback_answer_uses_requested_pages_and_limits() -> None:
    answer = render_page_context_fallback_answer(sample_pack(), {"context_pack_page_ids": []}, "upstream_llm_simulated_or_not_called")
    assert "Page 48" in answer or "page 48" in answer
    assert "t_p_120_1176_p000048" in answer
    assert "Page 202" in answer or "page 202" in answer
    assert "Engineering confidence" in answer
    assert "Limits" in answer
    assert "Do not infer interchangeability" in answer

def test_script_wrappers_bootstrap_repo_root_for_direct_execution() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    scripts = [
        repo_root / "scripts" / "build_trace_net_openwebui_page_context_bridge_v1.py",
        repo_root / "scripts" / "serve_trace_net_openwebui_page_context_bridge_v1.py",
    ]
    for script in scripts:
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=str(repo_root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()

from tiff.trace_net_openwebui_page_context_bridge_v1 import (
    build_native_failure_fallback_response,
    build_native_page_context_response,
    call_native_ollama_openai_chat,
    normalize_ollama_openai_base_url,
    ollama_native_api_base_url,
    render_native_page_answer_messages,
)


def test_normalize_ollama_openai_base_url_adds_v1() -> None:
    assert normalize_ollama_openai_base_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434/v1"
    assert normalize_ollama_openai_base_url("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434/v1"
    assert normalize_ollama_openai_base_url("http://127.0.0.1:11434/v1/chat/completions") == "http://127.0.0.1:11434/v1"




def test_ollama_native_api_base_url_removes_v1() -> None:
    assert ollama_native_api_base_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert ollama_native_api_base_url("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434"
    assert ollama_native_api_base_url("http://127.0.0.1:11434/v1/chat/completions") == "http://127.0.0.1:11434"


def test_call_native_ollama_uses_api_chat_with_think_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return json.dumps({
                "message": {"role": "assistant", "content": "Answer\nPage 48 and page 202 are aligned."},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 20,
            }).encode("utf-8")

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    content, metadata = call_native_ollama_openai_chat(
        messages=[{"role": "user", "content": "hello"}],
        base_url="http://127.0.0.1:11434/v1",
        model="gemma4:26b",
        num_ctx=8192,
        max_tokens=1200,
    )

    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["think"] is False
    assert captured["payload"]["options"]["num_ctx"] == 8192
    assert captured["payload"]["options"]["num_predict"] == 1200
    assert content.startswith("Answer")
    assert metadata["native_llm_provider_endpoint"] == "ollama_api_chat"
    assert metadata["empty_content"] is False

def test_render_native_page_answer_messages_requires_sections_and_pages() -> None:
    messages = render_native_page_answer_messages(sample_pack(), question="write about pages 48 and 202")
    assert messages[0]["role"] == "system"
    assert "Answer, Evidence, Engineering confidence, Limits" in messages[0]["content"]
    assert "t_p_120_1176_p000048" in messages[1]["content"]
    assert "t_p_120_1176_p000202" in messages[1]["content"]
    assert "Do not infer interchangeability" in messages[0]["content"]


def test_build_native_page_context_response_accepts_aligned_native_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    import tiff.trace_net_openwebui_page_context_bridge_v1 as bridge

    def fake_call_native(**kwargs):
        return (
            "Answer\nPage 48 and page 202 are both present. Page t_p_120_1176_p000048 is table-routed; page t_p_120_1176_p000202 is image_visual-routed.",
            {"usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}},
        )

    monkeypatch.setattr(bridge, "call_native_ollama_openai_chat", fake_call_native)
    meta = {
        "page_context_used": True,
        "detected_pages": [48, 202],
        "context_pack_page_ids": ["t_p_120_1176_p000048", "t_p_120_1176_p000202"],
        "context_pack_quality_status": "PASS",
        "context_pack_summary": sample_pack()["summary"],
    }
    response = build_native_page_context_response(
        pack=sample_pack(),
        meta=meta,
        question="write about pages 48 and 202",
        model_id="trace-net-page-context-v3-bridge",
        native_llm_base_url="http://127.0.0.1:11434",
        native_llm_model="gemma4:26b",
    )
    assert response["trace_net"]["page_context_bridge"]["native_page_answer_used"] is True
    assert response["trace_net"]["page_context_bridge"]["fallback_used"] is False
    assert response["trace_net"]["page_context_bridge"]["alignment_status"] == "upstream_response_page_aligned"


def test_native_failure_fallback_response_preserves_safety() -> None:
    meta = {
        "page_context_used": True,
        "detected_pages": [48, 202],
        "context_pack_page_ids": ["t_p_120_1176_p000048", "t_p_120_1176_p000202"],
        "context_pack_summary": sample_pack()["summary"],
    }
    response = build_native_failure_fallback_response(
        pack=sample_pack(),
        meta=meta,
        model_id="trace-net-page-context-v3-bridge",
        reason="native_page_answer_failed_or_not_aligned",
        error="boom",
    )
    bridge = response["trace_net"]["page_context_bridge"]
    assert bridge["fallback_used"] is True
    assert bridge["native_llm_called"] is False
    assert bridge["safety"]["answer_permission"] is False
    assert "page 48" in response["choices"][0]["message"]["content"].lower()


def test_build_native_page_context_response_retries_empty_content(monkeypatch: pytest.MonkeyPatch) -> None:
    import tiff.trace_net_openwebui_page_context_bridge_v1 as bridge

    calls = []

    def fake_call_native(**kwargs):
        calls.append(kwargs.get("attempt_label"))
        if kwargs.get("attempt_label") == "primary":
            return "", {"empty_content": True, "message_keys": ["reasoning"], "usage": {}}
        return (
            "Answer\nPage 48 (t_p_120_1176_p000048) and page 202 (t_p_120_1176_p000202) are both in the binder.\n\nEvidence\nThe context pack is PASS.\n\nEngineering confidence\nHigh for page identity.\n\nLimits\nGuidance is not proof.",
            {"empty_content": False, "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}},
        )

    monkeypatch.setattr(bridge, "call_native_ollama_openai_chat", fake_call_native)
    meta = {
        "page_context_used": True,
        "detected_pages": [48, 202],
        "context_pack_page_ids": ["t_p_120_1176_p000048", "t_p_120_1176_p000202"],
        "context_pack_quality_status": "PASS",
        "context_pack_summary": sample_pack()["summary"],
    }
    response = bridge.build_native_page_context_response(
        pack=sample_pack(),
        meta=meta,
        question="write about pages 48 and 202",
        model_id="trace-net-page-context-v3-bridge",
        native_llm_base_url="http://127.0.0.1:11434",
        native_llm_model="gemma4:26b",
    )
    bridge_meta = response["trace_net"]["page_context_bridge"]
    assert calls == ["primary", "strict_final_content_retry"]
    assert bridge_meta["native_page_answer_used"] is True
    assert bridge_meta["native_llm_called"] is True
    assert bridge_meta["native_llm_attempted"] is True
    assert bridge_meta["native_llm_retry_attempted"] is True
    assert bridge_meta["fallback_used"] is False
    assert response["trace_net"]["native_llm_metadata"]["native_llm_primary_empty_content"] is True


def test_native_failure_fallback_can_preserve_attempted_empty_content_metadata() -> None:
    meta = {
        "page_context_used": True,
        "detected_pages": [48, 202],
        "context_pack_page_ids": ["t_p_120_1176_p000048", "t_p_120_1176_p000202"],
        "context_pack_summary": sample_pack()["summary"],
    }
    response = build_native_failure_fallback_response(
        pack=sample_pack(),
        meta=meta,
        model_id="trace-net-page-context-v3-bridge",
        reason="native_page_answer_failed_or_not_aligned",
        error="native page answer returned empty content after strict final-answer retry",
        native_llm_attempted=True,
        native_llm_metadata={"empty_content": True, "message_keys": ["reasoning"]},
    )
    bridge = response["trace_net"]["page_context_bridge"]
    assert bridge["fallback_used"] is True
    assert bridge["native_llm_called"] is True
    assert bridge["native_llm_attempted"] is True
    assert bridge["native_llm_metadata"]["empty_content"] is True
    assert bridge["safety"]["answer_permission"] is False


def test_page_context_bridge_server_stores_native_context_limits(tmp_path: Path) -> None:
    server = PageContextBridgeServer(
        ("127.0.0.1", 0),
        PageContextBridgeHandler,
        repo_root=tmp_path,
        upstream_base_url="http://127.0.0.1:8022/v1",
        model_id="trace-net-page-context-v3-bridge",
        upstream_model="trace-net-e2e-live-orchestrator-fastpath-gemma-v27",
        max_pages=8,
        max_binder_chars=14000,
        native_page_answer_mode="auto",
        native_llm_base_url="http://127.0.0.1:11434/v1",
        native_llm_model="gemma4:26b",
        native_llm_api_key="ollama",
        native_temperature=0.1,
        native_request_timeout=300.0,
        native_num_ctx=8192,
        native_max_tokens=1200,
    )
    try:
        assert server.native_num_ctx == 8192
        assert server.native_max_tokens == 1200
    finally:
        server.server_close()
