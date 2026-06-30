from __future__ import annotations

import json
import sys
from pathlib import Path

from tiff.trace_net_image_route_openwebui_endpoint_v1 import build_endpoint_smoke, run_fast_chat_runner


def _fake_runner_nested(path: Path) -> None:
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
out = Path(args.output_dir) / 'nested_actual_runner_output'
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
report_path = out / 'trace_net_fast_chat_runner_v1.json'
report_path.write_text(json.dumps(report), encoding='utf-8')
print('Quality status: PASS')
print('Wrote: ' + str(report_path))
""".strip(),
        encoding="utf-8",
    )


def test_runner_report_discovery_finds_nested_report(tmp_path: Path) -> None:
    runner = tmp_path / 'fake_runner_nested.py'
    _fake_runner_nested(runner)
    context = tmp_path / 'context.json'
    pack = tmp_path / 'pack.json'
    context.write_text('{"quality_status":"PASS"}', encoding='utf-8')
    pack.write_text('{"quality_status":"PASS"}', encoding='utf-8')

    result = run_fast_chat_runner(
        question='What does figure 69 show?',
        repo_root=tmp_path,
        context_pack=context,
        image_visual_evidence_pack=pack,
        output_root=tmp_path / 'out',
        runner_script=runner,
        python_executable=sys.executable,
    )
    assert result['quality_status'] == 'PASS'
    assert result['report_found'] is True
    assert result['summary']['query_type'] == 'image_or_diagram'
    assert '120-50645-005' in result['answer']


def test_smoke_manifest_uses_discovered_report(tmp_path: Path) -> None:
    runner = tmp_path / 'fake_runner_nested.py'
    _fake_runner_nested(runner)
    context = tmp_path / 'context.json'
    pack = tmp_path / 'pack.json'
    context.write_text('{"quality_status":"PASS"}', encoding='utf-8')
    pack.write_text('{"quality_status":"PASS"}', encoding='utf-8')

    manifest = build_endpoint_smoke(
        question='What does figure 69 show?',
        repo_root=tmp_path,
        context_pack=context,
        image_visual_evidence_pack=pack,
        output_dir=tmp_path / 'smoke',
        runner_script=runner,
        python_executable=sys.executable,
        require_quality_pass=True,
        require_webui_answer_ready=True,
        min_valid_citations=1,
    )
    assert manifest['quality_status'] == 'PASS'
    assert manifest['summary']['valid_answer_citation_count'] == 1
    assert manifest['runner_result']['report_found'] is True
