from __future__ import annotations

import json
import sys
from pathlib import Path

from tiff.trace_net_image_route_openwebui_endpoint_v1 import (
    build_endpoint_smoke,
    build_openai_response,
    validate_smoke_manifest,
)


def _write_fake_runner(path: Path) -> None:
    path.write_text(
        """
import argparse, json
from pathlib import Path
ap = argparse.ArgumentParser()
ap.add_argument('--question', required=True)
ap.add_argument('--context-pack', required=True)
ap.add_argument('--image-visual-evidence-pack', required=True)
ap.add_argument('--output-dir', required=True)
ap.add_argument('--require-source-quality-pass', action='store_true')
ap.add_argument('--require-webui-answer-ready', action='store_true')
ap.add_argument('--require-multi-route-quality-pass', action='store_true')
ap.add_argument('--quality', action='store_true')
args = ap.parse_args()
out = Path(args.output_dir)
out.mkdir(parents=True, exist_ok=True)
report = {
  'quality_status': 'PASS',
  'answer_text': 'Figure 69 is linked to part number 120-50645-005 on page 315 [V6].',
  'citations': [{'citation_label':'V6','page_number':315,'source_trace_ready':True,'citation_ready':True}],
  'summary': {
    'query_type':'image_or_diagram',
    'query_route':'fast_image_diagram_answer',
    'webui_answer_ready': True,
    'multi_route_quality_gate_passed': True,
    'answer_quality_gate_passed': True,
    'valid_answer_citation_count': 1,
    'invalid_answer_citation_count': 0,
    'unsafe_record_count': 0,
    'answer_permission_count': 0,
    'source_truth_mutation_allowed_count': 0,
    'write_attempt_count': 0,
  }
}
(out / 'trace_net_fast_chat_runner_v1.json').write_text(json.dumps(report), encoding='utf-8')
print('Quality status: PASS')
""".strip(),
        encoding="utf-8",
    )


def test_smoke_builder_calls_runner_with_string_paths(tmp_path: Path) -> None:
    fake_runner = tmp_path / "fake_runner.py"
    _write_fake_runner(fake_runner)
    context = tmp_path / "context.json"
    pack = tmp_path / "pack.json"
    context.write_text('{"quality_status":"PASS"}', encoding="utf-8")
    pack.write_text('{"quality_status":"PASS"}', encoding="utf-8")

    manifest = build_endpoint_smoke(
        question="What does figure 69 show?",
        repo_root=tmp_path,
        context_pack=str(context),
        image_visual_evidence_pack=str(pack),
        output_dir=tmp_path / "out",
        runner_script=fake_runner,
        python_executable=sys.executable,
        require_quality_pass=True,
        require_webui_answer_ready=True,
        min_valid_citations=1,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["query_type"] == "image_or_diagram"
    assert manifest["summary"]["valid_answer_citation_count"] == 1
    assert "120-50645-005" in manifest["answer"]


def test_openai_response_shape_contains_trace_metadata() -> None:
    result = {
        "answer": "Answer [V6]",
        "report_path": "x.json",
        "report": {
            "quality_status": "PASS",
            "citations": [{"citation_label": "V6"}],
            "summary": {"query_type": "image_or_diagram", "webui_answer_ready": True, "valid_answer_citation_count": 1},
        },
    }
    resp = build_openai_response(result)
    assert resp["choices"][0]["message"]["content"] == "Answer [V6]"
    assert resp["trace_net"]["query_type"] == "image_or_diagram"
    assert resp["trace_net"]["citations"][0]["citation_label"] == "V6"


def test_smoke_validator_rejects_unsafe_counts() -> None:
    q, failures, checks = validate_smoke_manifest(
        {"quality_status":"PASS", "summary": {"webui_answer_ready": True, "valid_answer_citation_count": 1, "write_attempt_count": 1}},
        thresholds={"valid_answer_citation_count": 1},
        require_quality_pass=True,
        require_webui_answer_ready=True,
    )
    assert q == "FAIL"
    assert any("write_attempt_count" in f for f in failures)
    assert checks["write_attempt_count_zero"] is False
