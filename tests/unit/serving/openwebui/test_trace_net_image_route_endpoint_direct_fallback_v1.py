from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from tiff.trace_net_image_route_openwebui_endpoint_v1 import build_endpoint_smoke, run_fast_chat_runner


def _fake_runner(path: Path) -> None:
    path.write_text("import sys\nprint('simulated runner failure')\nsys.exit(1)\n", encoding="utf-8")


def _install_fake_image_modules(monkeypatch) -> None:
    adapter_mod = types.ModuleType("tiff.trace_net_image_route_fast_chat_adapter_v1")
    gate_mod = types.ModuleType("tiff.trace_net_image_route_multi_route_quality_gate_v1")

    def build_adapter(*, image_visual_evidence_pack, question, output_dir, **kwargs):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "TRACE_NET_IMAGE_ROUTE_FAST_CHAT_ADAPTER_BUILT",
            "quality_status": "PASS",
            "route_type": "image_or_diagram",
            "webui_answer_ready": True,
            "answer": "Figure 69 is linked to part number 120-50645-005 on page 315 [V6].",
            "citations": [{"citation_label": "V6", "page_number": 315, "linked_part_number": "120-50645-005", "source_trace_ready": True, "citation_ready": True}],
            "records": [],
            "summary": {
                "route_type": "image_or_diagram",
                "citation_count": 1,
                "source_trace_ready_citation_count": 1,
                "linked_selected_evidence_count": 1,
                "llava_only_part_identity_claim_count": 0,
                "unsupported_claim_count": 0,
                "unsafe_record_count": 0,
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "write_attempt_count": 0,
                "webui_answer_ready": True,
            },
        }
        (out / "trace_net_image_route_fast_chat_adapter_v1.json").write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def evaluate_gate(adapter, **kwargs):
        return {
            "status": "TRACE_NET_IMAGE_ROUTE_MULTI_ROUTE_QUALITY_GATE_CHECKED",
            "quality_status": "PASS",
            "summary": {
                "webui_answer_ready": True,
                "citation_count": 1,
                "source_trace_ready_citation_count": 1,
                "linked_citation_count": 1,
                "unsafe_record_count": 0,
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "write_attempt_count": 0,
            },
            "checks": {"adapter_quality_pass": True, "webui_answer_ready_required_met": True},
            "answer": adapter.get("answer"),
            "citations": adapter.get("citations", []),
        }

    adapter_mod.build_adapter = build_adapter
    gate_mod.evaluate_gate = evaluate_gate
    monkeypatch.setitem(sys.modules, "tiff.trace_net_image_route_fast_chat_adapter_v1", adapter_mod)
    monkeypatch.setitem(sys.modules, "tiff.trace_net_image_route_multi_route_quality_gate_v1", gate_mod)


def test_run_fast_chat_runner_direct_fallback_when_subprocess_fails(tmp_path: Path, monkeypatch) -> None:
    _install_fake_image_modules(monkeypatch)
    runner = tmp_path / "fake_runner.py"
    _fake_runner(runner)
    context = tmp_path / "context.json"
    pack = tmp_path / "pack.json"
    context.write_text('{"quality_status":"PASS"}', encoding="utf-8")
    pack.write_text('{"quality_status":"PASS"}', encoding="utf-8")

    result = run_fast_chat_runner(
        question="What does figure 69 show?",
        repo_root=tmp_path,
        context_pack=context,
        image_visual_evidence_pack=pack,
        output_root=tmp_path / "out",
        runner_script=runner,
        python_executable=sys.executable,
    )
    assert result["quality_status"] == "PASS"
    assert result["direct_fallback_used"] is True
    assert result["summary"]["query_type"] == "image_or_diagram"
    assert result["summary"]["valid_answer_citation_count"] == 1
    assert "120-50645-005" in result["answer"]


def test_smoke_manifest_passes_with_direct_fallback(tmp_path: Path, monkeypatch) -> None:
    _install_fake_image_modules(monkeypatch)
    runner = tmp_path / "fake_runner.py"
    _fake_runner(runner)
    context = tmp_path / "context.json"
    pack = tmp_path / "pack.json"
    context.write_text('{"quality_status":"PASS"}', encoding="utf-8")
    pack.write_text('{"quality_status":"PASS"}', encoding="utf-8")

    manifest = build_endpoint_smoke(
        question="What does figure 69 show?",
        repo_root=tmp_path,
        context_pack=context,
        image_visual_evidence_pack=pack,
        output_dir=tmp_path / "smoke",
        runner_script=runner,
        python_executable=sys.executable,
        require_quality_pass=True,
        require_webui_answer_ready=True,
        min_valid_citations=1,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["webui_answer_ready"] is True
    assert manifest["runner_result"]["direct_fallback_used"] is True
