from pathlib import Path
import json

from tiff.trace_net_feedback_ask_simulation_quality import (
    FeedbackAskSimulationQualityOptions,
    FeedbackAskSimulationQualityPaths,
    evaluate_feedback_ask_simulation_quality,
)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')


def test_feedback_ask_quality_passes(tmp_path):
    base = tmp_path / 'sim'
    write_json(base / 'trace_net_feedback_ask_simulation_summary.json', {
        'status': 'OK',
        'simulated_answer_page_records': 2,
        'simulated_answer_evidence_records': 2,
        'feedback_signals_used': 2,
        'groups_adjusted': 2,
        'rank_changed_records': 1,
        'unsafe_simulated_answer_groups': 0,
        'excluded_simulated_answer_groups': 0,
        'source_truth_mutation_records': 0,
        'context_warning_signals_used': 0,
        'missing_source_url_groups': 0,
        'missing_tiff_path_groups': 0,
        'missing_ocr_path_groups': 0,
        'answer_changed': True,
        'graph_nodes': 3,
        'graph_edges': 2,
    })
    write_json(base / 'trace_net_feedback_ask_simulation.json', {'simulated_pages': [{'page_id': 'p1'}, {'page_id': 'p2'}]})
    write_jsonl(base / 'trace_net_feedback_ask_simulation_evidence.jsonl', [{'x': 1}, {'x': 2}])
    (base / 'trace_net_feedback_ask_simulation_answer.md').write_text('answer', encoding='utf-8')
    (base / 'trace_net_feedback_ask_simulation_answer.html').write_text('<p>answer</p>', encoding='utf-8')
    write_json(base / 'trace_net_feedback_ask_simulation_graph_nodes.json', [{'id': 'n1'}, {'id': 'n2'}, {'id': 'n3'}])
    write_json(base / 'trace_net_feedback_ask_simulation_graph_edges.json', [{'source': 'n1', 'target': 'n2'}, {'source': 'n2', 'target': 'n3'}])
    paths = FeedbackAskSimulationQualityPaths(
        summary_path=base / 'trace_net_feedback_ask_simulation_summary.json',
        simulation_path=base / 'trace_net_feedback_ask_simulation.json',
        evidence_path=base / 'trace_net_feedback_ask_simulation_evidence.jsonl',
        answer_md_path=base / 'trace_net_feedback_ask_simulation_answer.md',
        answer_html_path=base / 'trace_net_feedback_ask_simulation_answer.html',
        graph_nodes_path=base / 'trace_net_feedback_ask_simulation_graph_nodes.json',
        graph_edges_path=base / 'trace_net_feedback_ask_simulation_graph_edges.json',
        quality_path=base / 'quality.json',
    )
    report = evaluate_feedback_ask_simulation_quality(paths, FeedbackAskSimulationQualityOptions(min_pages=1, min_evidence_records=1, min_feedback_signals_used=1, min_groups_adjusted=1, min_rank_changed_records=1, require_answer_changed=True, write_json=True))
    assert report['status'] == 'OK'
    assert (base / 'quality.json').exists()


def test_feedback_ask_quality_fails_on_unsafe(tmp_path):
    base = tmp_path / 'sim'
    write_json(base / 'trace_net_feedback_ask_simulation_summary.json', {'status': 'OK', 'simulated_answer_page_records': 1, 'simulated_answer_evidence_records': 1, 'unsafe_simulated_answer_groups': 1, 'source_truth_mutation_records': 0, 'context_warning_signals_used': 0})
    write_json(base / 'trace_net_feedback_ask_simulation.json', {'simulated_pages': [{'page_id': 'p1'}]})
    write_jsonl(base / 'trace_net_feedback_ask_simulation_evidence.jsonl', [{'x': 1}])
    (base / 'trace_net_feedback_ask_simulation_answer.md').write_text('answer', encoding='utf-8')
    (base / 'trace_net_feedback_ask_simulation_answer.html').write_text('<p>answer</p>', encoding='utf-8')
    write_json(base / 'trace_net_feedback_ask_simulation_graph_nodes.json', [{'id': 'n1'}])
    write_json(base / 'trace_net_feedback_ask_simulation_graph_edges.json', [{'source': 'n1', 'target': 'n1'}])
    paths = FeedbackAskSimulationQualityPaths(
        summary_path=base / 'trace_net_feedback_ask_simulation_summary.json',
        simulation_path=base / 'trace_net_feedback_ask_simulation.json',
        evidence_path=base / 'trace_net_feedback_ask_simulation_evidence.jsonl',
        answer_md_path=base / 'trace_net_feedback_ask_simulation_answer.md',
        answer_html_path=base / 'trace_net_feedback_ask_simulation_answer.html',
        graph_nodes_path=base / 'trace_net_feedback_ask_simulation_graph_nodes.json',
        graph_edges_path=base / 'trace_net_feedback_ask_simulation_graph_edges.json',
        quality_path=base / 'quality.json',
    )
    report = evaluate_feedback_ask_simulation_quality(paths, FeedbackAskSimulationQualityOptions(max_unsafe_groups=0))
    assert report['status'] == 'FAIL'
