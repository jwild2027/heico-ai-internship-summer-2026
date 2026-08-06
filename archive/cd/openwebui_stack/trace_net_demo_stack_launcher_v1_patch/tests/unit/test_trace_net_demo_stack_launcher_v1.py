from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/operations/serving/serve_trace_net_demo_stack_launcher_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("demo_stack_launcher", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["demo_stack_launcher"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_build_service_specs_contains_three_services(tmp_path: Path) -> None:
    mod = load_module()

    root = tmp_path
    (root / "scripts").mkdir()
    for name in [
        "serve_trace_net_e2e_local_endpoint_v1.py",
        "serve_trace_net_guided_candidate_discovery_endpoint_v1.py",
        "serve_trace_net_router_proxy_v6_gated_visual_v1_1.py",
    ]:
        (root / "scripts" / name).write_text("print('stub')\n", encoding="utf-8")

    docs = root / "local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/trace_net_gated_visual_retrieval_documents_v1_1.jsonl"
    review = root / "local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/trace_net_gated_visual_candidate_review_documents_v1_1.jsonl"
    docs.parent.mkdir(parents=True)
    docs.write_text("{}\n", encoding="utf-8")
    review.write_text("{}\n", encoding="utf-8")

    args = argparse.Namespace(
        host="127.0.0.1",
        normal_port=8014,
        guided_port=8016,
        router_port=8017,
        artifact_root="local_data/organization/trace_net",
        output_dir=str(tmp_path / "runtime"),
        guided_output_dir="local_data/organization/trace_net/guided_candidate_discovery_endpoint_v1_runtime",
        gated_visual_retrieval_documents_jsonl="local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/trace_net_gated_visual_retrieval_documents_v1_1.jsonl",
        review_only_documents_jsonl="local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/trace_net_gated_visual_candidate_review_documents_v1_1.jsonl",
        model="trace-net-router-proxy-v6-gated-visual-v1-1",
        top_k=8,
        loose_top_k=8,
        visual_top_k=8,
    )

    specs = mod.build_service_specs(args, root=root)

    assert [s.name for s in specs] == ["normal_ask", "guided_discovery", "router_proxy"]
    assert [s.port for s in specs] == [8014, 8016, 8017]
    assert any("--normal-base-url" in s.command for s in specs)
    assert any("--guided-base-url" in s.command for s in specs)


def test_parse_args_defaults() -> None:
    mod = load_module()
    args = mod.parse_args([])
    assert args.normal_port == 8014
    assert args.guided_port == 8016
    assert args.router_port == 8017
    assert args.model == "trace-net-router-proxy-v6-gated-visual-v1-1"
    assert "gated_visual_retrieval_adapter_v1_1" in args.gated_visual_retrieval_documents_jsonl
