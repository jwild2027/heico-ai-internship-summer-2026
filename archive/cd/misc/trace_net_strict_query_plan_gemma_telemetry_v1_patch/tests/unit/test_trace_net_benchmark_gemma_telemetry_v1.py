import importlib.util
import json
import sys
from pathlib import Path

from tiff import trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 as v27


SCRIPT = Path("scripts/benchmark/run_trace_net_router_followup_retrieval_benchmark_v1.py")


def load():
    spec = importlib.util.spec_from_file_location("gemma_telemetry_v1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gemma_telemetry_v1"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def state(tmp_path: Path):
    adapter = tmp_path / "adapter.json"
    adapter.write_text(
        json.dumps({
            "quality_status": "PASS",
            "exact_search_documents": [
                {
                    "document_id": "part",
                    "page_id": "t_p_120_1176_p000003",
                    "field_name": "part_number",
                    "normalized_value": "120-41824-003",
                    "search_text": "120-41824-003",
                }
            ],
        }),
        encoding="utf-8",
    )
    return v27.build_state(
        table_exact_search_adapter_path=adapter,
        output_dir=None,
        llm_mode="simulate",
        fast_path_mode="exact",
        include_standard_demo_queries=False,
    )


def test_parser_accepts_fast_path_off_and_require_gemma():
    mod = load()
    args = mod.build_parser().parse_args([
        "--llm-mode", "ollama",
        "--fast-path-mode", "off",
        "--require-gemma-call",
    ])
    assert args.fast_path_mode == "off"
    assert args.require_gemma_call is True


def test_retrieval_telemetry_reports_fast_path_skip(tmp_path):
    mod = load()
    result = mod.run_retrieval(
        "Find part number 120-41824-003",
        state(tmp_path),
        llm_mode="simulate",
        fast_path_mode="exact",
    )
    assert result["llm_status"] == "LLM_SKIPPED_FAST_PATH"
    assert result["fast_path_used"] is True
    assert result["query_intent"] == "part_number"


def test_retrieval_telemetry_reports_simulated_non_fast_path(tmp_path):
    mod = load()
    result = mod.run_retrieval(
        "Find part number 120-41824-003",
        state(tmp_path),
        llm_mode="simulate",
        fast_path_mode="off",
    )
    assert result["llm_status"] == "LLM_SIMULATED"
    assert result["fast_path_used"] is False
    assert result["target_value"] == "120-41824-003"
