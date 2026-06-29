import json
from pathlib import Path

import pytest

from tiff import trace_net_raw_to_answer_context_engineered_native_v1 as mod


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_runs_context_engineering_chain_and_uses_anchor_prompt(tmp_path, monkeypatch):
    output = tmp_path / "out"
    artifacts = {
        "pipeline": output / "trace_net_ocr_classifier_pipeline_runner_v1.json",
        "scan_pack": output / "ocr_route_scan_pack_tesseract_full" / "trace_net_ocr_route_scan_pack_v1.json",
        "contract": output / "loader_contract_audit" / "trace_net_loader_contract_audit_v1.json",
        "retrieval_payload_audit": output / "retrieval_payload_audit" / "trace_net_retrieval_payload_audit_v1.json",
    }
    write_json(artifacts["pipeline"], {"quality_status": "PASS", "summary": {"all_stage_quality_pass": True, "stage_count": 9, "stage_report_count": 9, "stage_quality_statuses": {"ocr": "PASS"}}})
    write_json(artifacts["scan_pack"], {"quality_status": "PASS", "records": []})
    write_json(artifacts["contract"], {"quality_status": "PASS", "summary": {"postgres_contract_ready_count": 509, "qdrant_contract_ready_count": 450, "opensearch_contract_ready_count": 282, "lineage_ready_count": 509}})
    write_json(artifacts["retrieval_payload_audit"], {"quality_status": "PASS", "summary": {"qdrant_payload_count": 450, "opensearch_payload_count": 282, "retrieval_payload_audit_record_count": 509, "violation_record_count": 0}})

    monkeypatch.setattr(mod, "_find_pipeline_artifacts", lambda out: artifacts)

    def fake_probe(**kwargs):
        payload = {"quality_status": "PASS", "summary": {"exact_hit_count": 2, "exact_direct_hit_count": 1, "direct_exact_page_numbers": [343], "violation_record_count": 0}, "records": []}
        write_json(Path(kwargs["output_dir"]) / "trace_net_part_number_exact_retrieval_probe_v1.json", payload)
        return payload

    def fake_anchor(**kwargs):
        payload = {"quality_status": "PASS", "summary": {"direct_exact_anchor_count": 1, "direct_exact_anchor_page_count": 1, "direct_exact_anchor_page_numbers": [343], "violation_record_count": 0}, "records": []}
        write_json(Path(kwargs["output_dir"]) / "trace_net_answer_context_anchor_injector_v1.json", payload)
        return payload

    def fake_anchor_aware(**kwargs):
        payload = {
            "quality_status": "PASS",
            "summary": {
                "anchor_aware_record_count": 2,
                "citation_count": 2,
                "context_prompt_char_count": 1000,
                "direct_exact_anchor_count": 1,
                "direct_exact_anchor_page_count": 1,
                "direct_exact_anchor_page_numbers": [343],
                "anchor_community_count": 1,
                "same_anchor_leiden_community_count": 1,
                "ready_for_gemma_anchor_aware_prompt": True,
                "ready_for_answer_quality_gate": True,
                "violation_record_count": 0,
            },
            "records": [{"citation_label": "E1", "anchor_aware_role": "direct_exact_match_anchor", "page_number": 343}],
            "llm_context_prompt": "DIRECT EXACT ANCHORS: E1 page 343 part 120-29073-001",
        }
        write_json(Path(kwargs["output_dir"]) / "trace_net_anchor_aware_graph_leiden_expander_v1.json", payload)
        return payload

    captured = {}

    def fake_llm(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return {"llm_called": True, "llm_status": "PASS", "llm_answer_char_count": 42, "answer_text": "Found it [E1].", "llm_model": kwargs["model"]}

    monkeypatch.setattr(mod, "build_part_number_exact_retrieval_probe", fake_probe)
    monkeypatch.setattr(mod, "build_answer_context_anchor_injector", fake_anchor)
    monkeypatch.setattr(mod, "build_anchor_aware_graph_leiden_expander", fake_anchor_aware)
    monkeypatch.setattr(mod, "call_ollama_native", fake_llm)

    payload = mod.build_raw_to_answer_context_engineered_native(
        source_package=tmp_path / "metadata.zip",
        tesseract_cmd=tmp_path / "tesseract.exe",
        output_dir=output,
        question="Find part number 120-29073-001",
        part_numbers=["120-29073-001"],
        skip_pipeline_if_present=True,
        require_llm_success=True,
        require_anchor_communities=True,
        quality=True,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["context_engineering_enabled"] is True
    assert payload["summary"]["direct_exact_anchor_count"] == 1
    assert payload["summary"]["anchor_community_count"] == 1
    assert payload["summary"]["llm_status"] == "PASS"
    assert "DIRECT EXACT ANCHORS" in captured["prompt"]
    assert (output / mod.REPORT_NAME).exists()


def test_quality_check_requires_context_flags(tmp_path):
    report = tmp_path / "report.json"
    write_json(report, {"quality_status": "PASS", "summary": {"stage_report_count": 12, "postgres_contract_ready_count": 509, "qdrant_contract_ready_count": 450, "opensearch_contract_ready_count": 282, "qdrant_payload_count": 450, "opensearch_payload_count": 282, "direct_exact_anchor_count": 8, "anchor_community_count": 1, "citation_count": 36, "context_prompt_char_count": 2000, "violation_record_count": 0, "all_stage_quality_pass": True, "context_engineering_enabled": True, "ready_for_gemma_anchor_aware_prompt": True, "dry_run_only": True, "human_review_required_count": 0, "manual_review_required_count": 0, "unsafe_record_count": 0, "answer_permission_count": 0, "source_truth_mutation_allowed_count": 0, "write_attempt_count": 0, "llm_status": "PASS", "llm_answer_char_count": 100}})
    result = mod.check_quality(report_path=report, require_all_stage_quality_pass=True, require_context_engineering_enabled=True, require_anchor_aware_prompt=True, require_dry_run_only=True, require_no_human_review_required=True, require_no_answer_permission=True, require_no_source_truth_mutation=True, require_no_write_attempts=True, require_llm_success=True)
    assert result["quality_status"] == "PASS"
