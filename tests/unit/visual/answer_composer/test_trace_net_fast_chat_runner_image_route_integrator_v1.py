from __future__ import annotations

from pathlib import Path

from tiff.trace_net_fast_chat_runner_image_route_integrator_v1 import apply_integration, integrate_source_text


def _sample_runner() -> str:
    return '''from __future__ import annotations
import argparse
from pathlib import Path
from typing import Any
MODULE = "trace_net_fast_chat_runner_v1"
VERSION = "v1"
def detect_query_type(question: str, part_number: str | None = None, part_family: str | None = None, figure: str | None = None, item: str | None = None) -> dict[str, Any]:
    q_lower = (question or "").lower()
    family = None
    fig = figure
    fig_item = item
    if any(w in q_lower for w in ["diagram", "callout", "image", "figure shows", "visual"]):
        return {
            "query_type": "image_or_diagram",
            "query_route": "planned_image_visual_context",
            "query_part_numbers": [],
            "query_part_families": [family] if family else [],
            "figure": fig,
            "item": fig_item,
            "implemented_query_type": False,
        }
    return {"query_type": "plain_text"}
def _write_text(path, text): pass
def _write_json(path, payload): pass
def _read_json(path): return {}
def _load_builder(module_name, function_names): return None
def _invoke_builder(fn, kwargs): return None
def _quality_status(summary, require_answer_quality_pass=False, require_multi_route_quality_pass=False, require_webui_answer_ready=False): return ("PASS", [])
def build_fast_chat_runner(
    *,
    question: str,
    context_pack: str,
    output_dir: str,
    require_webui_answer_ready: bool = False,
    quality: bool = False,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    context_payload = _read_json(context_pack)
    context_quality = "PASS"
    query_plan = detect_query_type(question)
    query_type = query_plan["query_type"]
    answer_text = ""
    stage_reports: dict[str, str] = {"context_pack": "PASS"}
    stage_paths: dict[str, str] = {}
    stage_payloads: dict[str, Any] = {}
    if query_type == "exact_part_number":
        pass
    elif query_type == "figure_or_item":
        pass
    elif query_type == "part_family":
        pass
    else:
        answer_text = "planned"
    labels = []
    invalid_labels = []
    exact_payload = stage_payloads.get("fast_answer_composer", {}).get("summary", {})
    fig_payload = stage_payloads.get("figure_item_fast_answer_composer", {}).get("summary", {})
    fam_payload = stage_payloads.get("part_family_fast_answer_composer", {}).get("summary", {})
    qgate_payload = stage_payloads.get("answer_quality_gate", {}).get("summary", {})
    implemented = bool(query_plan.get("implemented_query_type"))
    route_ready = False
    if query_type == "exact_part_number":
        route_ready = bool(exact_payload.get("fast_answer_composer_ready"))
    elif query_type == "figure_or_item":
        route_ready = bool(fig_payload.get("figure_item_fast_answer_ready"))
    elif query_type == "part_family":
        route_ready = bool(fam_payload.get("part_family_fast_answer_ready"))
    summary: dict[str, Any] = {
        "part_family_fast_answer_ready": bool(fam_payload.get("part_family_fast_answer_ready")),
        "multi_route_quality_gate_passed": False,
        "webui_answer_ready": False,
        "stage_quality_statuses": stage_reports,
        "stage_report_paths": stage_paths,
        "stage_count": len(stage_reports),
    }
    if run_multi_route_quality_gate:
        pass
    quality_status, failures = _quality_status(
        summary,
        require_webui_answer_ready=require_webui_answer_ready,
    )
    return {"quality_status": quality_status, "summary": summary}
def main_build() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--question", required=True)
    p.add_argument("--context-pack", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--require-webui-answer-ready", action="store_true")
    p.add_argument("--quality", action="store_true")
    args = p.parse_args()
    build_fast_chat_runner(
        question=args.question,
        context_pack=args.context_pack,
        output_dir=args.output_dir,
        require_webui_answer_ready=args.require_webui_answer_ready,
        quality=args.quality,
    )
def check_fast_chat_runner_quality(
    *,
    report_path: str,
    require_part_family_query: bool = False,
) -> dict[str, Any]:
    summary = {}
    failures = []
    if require_part_family_query and summary.get("query_type") != "part_family":
        failures.append("query_type is not part_family")
    return {"quality_status": "PASS" if not failures else "FAIL"}
def main_check() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--require-part-family-query", action="store_true")
'''.replace('    if run_multi_route_quality_gate:', '    run_multi_route_quality_gate = True\n    if run_multi_route_quality_gate:')


def test_integrate_source_text_marks_image_route_implemented() -> None:
    patched, failures, changed = integrate_source_text(_sample_runner())
    assert failures == []
    assert changed is True
    assert '"query_route": "fast_image_diagram_answer"' in patched
    assert '"implemented_query_type": True' in patched
    assert "image_visual_evidence_pack: str | None = None" in patched
    assert 'elif query_type == "image_or_diagram"' in patched
    assert 'trace_net_image_route_fast_chat_adapter_v1' in patched
    assert 'trace_net_image_route_multi_route_quality_gate_v1' in patched
    assert 'p.add_argument("--image-visual-evidence-pack")' in patched
    assert 'require_image_diagram_query: bool = False' in patched


def test_integrator_is_idempotent() -> None:
    first, failures, changed = integrate_source_text(_sample_runner())
    assert failures == []
    second, failures2, changed2 = integrate_source_text(first)
    assert failures2 == []
    assert changed2 is False
    assert first == second


def test_apply_integration_dry_run_writes_output(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    target = root / "tiff" / "trace_net_fast_chat_runner_v1.py"
    target.parent.mkdir(parents=True)
    target.write_text(_sample_runner(), encoding="utf-8")
    out = tmp_path / "patched.py"
    result = apply_integration(root, dry_run=True, output=out)
    assert result["quality_status"] == "PASS"
    assert out.exists()
    assert '"query_type": "image_or_diagram"' in out.read_text(encoding="utf-8")
    assert '"query_route": "fast_image_diagram_answer"' in out.read_text(encoding="utf-8")
    assert target.read_text(encoding="utf-8") == _sample_runner()


def test_apply_integration_updates_target_and_backup(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    target = root / "tiff" / "trace_net_fast_chat_runner_v1.py"
    target.parent.mkdir(parents=True)
    original = _sample_runner()
    target.write_text(original, encoding="utf-8")
    result = apply_integration(root, dry_run=False)
    assert result["quality_status"] == "PASS"
    assert '"query_route": "fast_image_diagram_answer"' in target.read_text(encoding="utf-8")
    backup = target.with_suffix(target.suffix + ".pre_image_route_integration_v1.bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original


def test_integrator_handles_compact_inline_check_function_shape() -> None:
    compact = _sample_runner().replace(
        '    if require_part_family_query and summary.get("query_type") != "part_family":\n        failures.append("query_type is not part_family")\n',
        '    if require_part_family_query and summary.get("query_type") != "part_family": failures.append("query_type is not part_family")\n',
    ).replace(
        '    p.add_argument("--require-part-family-query", action="store_true")\n',
        '    p.add_argument("--require-part-family-query", action="store_true")\n',
    )
    patched, failures, changed = integrate_source_text(compact)
    assert failures == []
    assert changed is True
    assert 'require_image_diagram_query: bool = False' in patched
    assert 'query_type is not image_or_diagram' in patched
    assert 'p.add_argument("--require-image-diagram-query", action="store_true")' in patched
