#!/usr/bin/env python3
"""Add real Gemma/Ollama mode to the TRACE-Net benchmark runner."""
from pathlib import Path

repo = Path.cwd().resolve()
if not (repo / ".git").exists():
    raise SystemExit("Run this from the repository root.")

target = repo / "scripts/benchmark/run_trace_net_router_followup_retrieval_benchmark_v1.py"
text = target.read_text(encoding="utf-8")

replacements = [
    ('def run_retrieval(query: str, state: Mapping[str, Any]) -> Dict[str, Any]:\n    from tiff import trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 as v27\n\n    mutable_state = dict(state)\n    mutable_state["llm_mode"] = "simulate"\n    result = v27.run_live_query_v27(\n        query,\n        mutable_state,\n        llm_mode="simulate",\n        request_timeout=60,\n    )\n', 'def run_retrieval(\n    query: str,\n    state: Mapping[str, Any],\n    *,\n    llm_mode: str = "simulate",\n    llm_model: str = "gemma4:26b",\n    llm_base_url: str = "http://127.0.0.1:11434/v1",\n    llm_api_key: str = "ollama",\n    request_timeout: int = 240,\n) -> Dict[str, Any]:\n    from tiff import trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 as v27\n\n    mutable_state = dict(state)\n    mutable_state["llm_mode"] = llm_mode\n    mutable_state["llm_model"] = llm_model\n    mutable_state["llm_base_url"] = llm_base_url\n    mutable_state["llm_api_key"] = llm_api_key\n    mutable_state["request_timeout"] = request_timeout\n    result = v27.run_live_query_v27(\n        query,\n        mutable_state,\n        llm_mode=llm_mode,\n        request_timeout=request_timeout,\n    )\n', "run_retrieval"),
    ('def evaluate_record(\n    record: Mapping[str, Any],\n    *,\n    retrieval_state: Optional[Mapping[str, Any]],\n) -> Dict[str, Any]:\n', 'def evaluate_record(\n    record: Mapping[str, Any],\n    *,\n    retrieval_state: Optional[Mapping[str, Any]],\n    retrieval_config: Optional[Mapping[str, Any]] = None,\n) -> Dict[str, Any]:\n', "evaluate_record signature"),
    ('        retrieval_result = run_retrieval(query, retrieval_state)\n', '        config = dict(retrieval_config or {})\n        retrieval_result = run_retrieval(\n            query,\n            retrieval_state,\n            llm_mode=str(config.get("llm_mode") or "simulate"),\n            llm_model=str(config.get("llm_model") or "gemma4:26b"),\n            llm_base_url=str(config.get("llm_base_url") or "http://127.0.0.1:11434/v1"),\n            llm_api_key=str(config.get("llm_api_key") or "ollama"),\n            request_timeout=int(config.get("request_timeout") or 240),\n        )\n', "evaluate_record retrieval call"),
    ('    parser.add_argument("--limit", type=int, default=0)\n    parser.add_argument("--min-question-count", type=int, default=150)\n', '    parser.add_argument("--limit", type=int, default=0)\n    parser.add_argument("--min-question-count", type=int, default=150)\n    parser.add_argument(\n        "--llm-mode",\n        choices=["simulate", "ollama"],\n        default="simulate",\n        help="Answer-writer mode for manifest retrieval checks.",\n    )\n    parser.add_argument("--llm-model", default="gemma4:26b")\n    parser.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")\n    parser.add_argument("--llm-api-key", default="ollama")\n    parser.add_argument("--request-timeout", type=int, default=240)\n', "parser llm arguments"),
    ('        result = evaluate_record(row, retrieval_state=retrieval_state)\n', '        result = evaluate_record(\n            row,\n            retrieval_state=retrieval_state,\n            retrieval_config={\n                "llm_mode": args.llm_mode,\n                "llm_model": args.llm_model,\n                "llm_base_url": args.llm_base_url,\n                "llm_api_key": args.llm_api_key,\n                "request_timeout": args.request_timeout,\n            },\n        )\n', "main evaluate_record call"),
    ('                f"category={category} retrieval={retrieval_expectation} "\n                f"query={query[:140]}",\n', '                f"category={category} retrieval={retrieval_expectation} "\n                f"llm_mode={args.llm_mode} query={query[:140]}",\n', "progress llm mode"),
    ('        "manifest": args.manifest or None,\n', '        "manifest": args.manifest or None,\n        "llm_mode": args.llm_mode,\n        "llm_model": args.llm_model,\n        "llm_base_url": args.llm_base_url,\n        "request_timeout": args.request_timeout,\n', "summary llm metadata"),
]

for old, new, label in replacements:
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise SystemExit(f"Could not patch {label}.")

target.write_text(text, encoding="utf-8", newline="\n")

test_src = Path(__file__).resolve().parent / "tests/unit/test_trace_net_benchmark_gemma_mode_v1.py"
test_dst = repo / "tests/unit/test_trace_net_benchmark_gemma_mode_v1.py"
test_dst.parent.mkdir(parents=True, exist_ok=True)
test_dst.write_text(test_src.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

print("updated scripts/benchmark/run_trace_net_router_followup_retrieval_benchmark_v1.py")
print("applied tests/unit/test_trace_net_benchmark_gemma_mode_v1.py")
print("status=TRACE_NET_BENCHMARK_GEMMA_MODE_V1_PATCH_APPLIED")
