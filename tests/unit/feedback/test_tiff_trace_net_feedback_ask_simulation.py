from pathlib import Path

from tiff.trace_net_feedback_ask_simulation import (
    FeedbackAskSimulationOptions,
    FeedbackAskSimulationPaths,
    simulate_feedback_aware_ask,
)

import json


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')


def test_feedback_ask_simulation_composes_simulated_answer(tmp_path):
    search_dir = tmp_path / 'search'
    answers_dir = tmp_path / 'answers'
    sim_dir = tmp_path / 'feedback_search_simulation'
    out_dir = tmp_path / 'feedback_ask_simulation'

    current_grouped = [
        {'page_id': 'page_a', 'rank': 1, 'group_score': 10, 'rag_buckets': ['verified_part_evidence'], 'supporting_results': [{'candidate_id': 'c1', 'rag_bucket': 'verified_part_evidence', 'score': 10, 'source_url': 'url_a', 'tiff_path': 'a.tif', 'ocr_path': 'a.txt'}], 'source_url': 'url_a', 'tiff_path': 'a.tif', 'ocr_path': 'a.txt'},
        {'page_id': 'page_b', 'rank': 2, 'group_score': 9, 'rag_buckets': ['source_text_evidence'], 'supporting_results': [{'candidate_id': 'c2', 'rag_bucket': 'source_text_evidence', 'score': 9, 'source_url': 'url_b', 'tiff_path': 'b.tif', 'ocr_path': 'b.txt'}], 'source_url': 'url_b', 'tiff_path': 'b.tif', 'ocr_path': 'b.txt'},
    ]
    simulated = [
        dict(current_grouped[0], base_rank=1, simulated_rank=1, base_group_score=10, simulated_group_score=18, feedback_score_delta=8, rank_delta=0, feedback_signal_count=1, feedback_signal_types=['boost_for_query'], feedback_signals=[{'signal_id': 's1', 'signal': 'boost_for_query', 'delta': 8}]),
        dict(current_grouped[1], base_rank=2, simulated_rank=2, base_group_score=9, simulated_group_score=-3, feedback_score_delta=-12, rank_delta=0, feedback_signal_count=1, feedback_signal_types=['demote_for_query'], feedback_signals=[{'signal_id': 's2', 'signal': 'demote_for_query', 'delta': -12}]),
    ]
    write_jsonl(search_dir / 'trace_net_search_grouped_results.jsonl', current_grouped)
    write_json(search_dir / 'trace_net_search_grouped_summary.json', {'top_group_score': 10})
    write_json(answers_dir / 'trace_net_answer_summary.json', {'status': 'OK', 'query': 'abc', 'answer_page_records': 2, 'answer_evidence_records': 2})
    write_json(answers_dir / 'trace_net_answer_draft.json', {'summary': {'status': 'OK'}, 'pages': []})
    write_jsonl(sim_dir / 'trace_net_feedback_search_simulation_results.jsonl', simulated)
    write_json(sim_dir / 'trace_net_feedback_search_simulation_summary.json', {'status': 'OK', 'query_fingerprint': 'part_number:ABC', 'matching_feedback_signal_records': 2, 'feedback_signals_used': 2, 'groups_with_feedback_adjustment': 2, 'rank_changed_records': 0, 'top_page_before': 'page_a', 'top_page_after': 'page_a', 'source_truth_mutation_records': 0, 'context_warning_signals_used': 0})

    paths = FeedbackAskSimulationPaths(search_dir=search_dir, answers_dir=answers_dir, feedback_search_sim_dir=sim_dir, output_dir=out_dir)
    result = simulate_feedback_aware_ask(paths, FeedbackAskSimulationOptions())
    summary = result['summary']
    assert summary['status'] == 'OK'
    assert summary['simulated_answer_page_records'] == 2
    assert summary['feedback_signals_used'] == 2
    assert summary['groups_adjusted'] == 2
    assert summary['unsafe_simulated_answer_groups'] == 0
    assert (out_dir / 'trace_net_feedback_ask_simulation_answer.md').exists()
    assert (out_dir / 'trace_net_feedback_ask_simulation_evidence.jsonl').exists()


def test_feedback_ask_simulation_flags_empty(tmp_path):
    search_dir = tmp_path / 'search'
    answers_dir = tmp_path / 'answers'
    sim_dir = tmp_path / 'feedback_search_simulation'
    out_dir = tmp_path / 'feedback_ask_simulation'
    write_jsonl(sim_dir / 'trace_net_feedback_search_simulation_results.jsonl', [])
    write_json(sim_dir / 'trace_net_feedback_search_simulation_summary.json', {'status': 'OK'})
    paths = FeedbackAskSimulationPaths(search_dir=search_dir, answers_dir=answers_dir, feedback_search_sim_dir=sim_dir, output_dir=out_dir)
    result = simulate_feedback_aware_ask(paths, FeedbackAskSimulationOptions())
    assert result['summary']['status'] == 'EMPTY'
