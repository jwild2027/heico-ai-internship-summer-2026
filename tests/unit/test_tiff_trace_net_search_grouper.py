import json
from pathlib import Path

from tiff.trace_net_search_grouper import SearchGroupOptions, SearchGroupPaths, group_search_results


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def test_groups_multiple_chunks_by_page_and_preserves_support(tmp_path):
    search_dir = tmp_path / 'search'
    citations_dir = tmp_path / 'citations'
    out = tmp_path / 'out'
    rows = [
        {
            'rank': 1,
            'score': 52.5,
            'candidate_id': 'cand1',
            'chunk_id': 'cand1',
            'page_id': 'p001',
            'document_id': 'doc',
            'ata_code': '25-21-00',
            'rag_bucket': 'verified_part_evidence',
            'evidence_layer': 'part_catalog',
            'final_trust_tier': 'A',
            'usable_confidence': 0.91,
            'final_rag_action': 'include_as_verified_part_evidence',
            'source_url': 'http://src/p001',
            'tiff_path': 'p001.tif',
            'ocr_path': 'p001.txt',
            'part_numbers': ['120-50645-009'],
            'score_components': {'matched_part_numbers': ['120-50645-009']},
            'text_preview': 'part 120-50645-009 appears here',
            'safe_candidate': True,
        },
        {
            'rank': 2,
            'score': 49.0,
            'candidate_id': 'cand2',
            'chunk_id': 'cand2',
            'page_id': 'p001',
            'document_id': 'doc',
            'ata_code': '25-21-00',
            'rag_bucket': 'source_text_evidence',
            'evidence_layer': 'source_text',
            'final_trust_tier': 'A',
            'usable_confidence': 0.88,
            'final_rag_action': 'include_as_source_evidence',
            'source_url': 'http://src/p001',
            'tiff_path': 'p001.tif',
            'ocr_path': 'p001.txt',
            'score_components': {'matched_terms': ['seat', 'bottom']},
            'text_preview': 'seat bottom text',
            'safe_candidate': True,
        },
        {
            'rank': 3,
            'score': 20.0,
            'candidate_id': 'cand3',
            'chunk_id': 'cand3',
            'page_id': 'p002',
            'document_id': 'doc',
            'ata_code': '25-21-00',
            'rag_bucket': 'source_evidence',
            'evidence_layer': 'source_trace',
            'final_trust_tier': 'A',
            'usable_confidence': 0.8,
            'final_rag_action': 'include_as_source_evidence',
            'source_url': 'http://src/p002',
            'tiff_path': 'p002.tif',
            'ocr_path': 'p002.txt',
            'score_components': {'matched_pages': ['p002']},
            'text_preview': 'source trace',
            'safe_candidate': True,
        },
    ]
    citations = [
        {'candidate_id': 'cand1', 'citation_id': 'cit1', 'citation_short': 'p001 source', 'citation_markdown': '- Source: p001', 'page_id': 'p001'},
        {'candidate_id': 'cand2', 'citation_id': 'cit2', 'citation_short': 'p001 text', 'citation_markdown': '- OCR: p001', 'page_id': 'p001'},
    ]
    write_jsonl(search_dir / 'trace_net_search_results.jsonl', rows)
    write_jsonl(citations_dir / 'trace_net_source_citations.jsonl', citations)

    result = group_search_results(SearchGroupPaths(search_dir=search_dir, citations_dir=citations_dir, output_dir=out), SearchGroupOptions(top_k_groups=10))
    summary = result['summary']
    groups = result['groups']
    assert summary['status'] == 'OK'
    assert summary['search_result_records'] == 3
    assert summary['grouped_page_records'] == 2
    assert summary['groups_with_multiple_buckets'] >= 1
    p001 = next(g for g in groups if g['page_id'] == 'p001')
    assert p001['supporting_result_count'] == 2
    assert set(p001['rag_buckets']) == {'verified_part_evidence', 'source_text_evidence'}
    assert '120-50645-009' in p001['matched_part_numbers']
    assert p001['citation_count'] == 2
    assert p001['safe_group'] is True
    assert (out / 'trace_net_search_grouped_results.jsonl').exists()
    assert (out / 'trace_net_search_grouped_graph_nodes.json').exists()


def test_grouping_flags_unsafe_support(tmp_path):
    search_dir = tmp_path / 'search'
    out = tmp_path / 'out'
    write_jsonl(search_dir / 'trace_net_search_results.jsonl', [
        {
            'rank': 1,
            'score': 1.0,
            'candidate_id': 'bad',
            'page_id': 'p001',
            'rag_bucket': 'table_candidate',
            'evidence_layer': 'table_candidate',
            'final_rag_action': 'exclude_until_table_tiles_exist',
            'source_url': 'http://src/p001',
            'safe_candidate': False,
        }
    ])
    result = group_search_results(SearchGroupPaths(search_dir=search_dir, output_dir=out), SearchGroupOptions())
    assert result['summary']['unsafe_grouped_records'] == 1
    assert result['groups'][0]['safe_group'] is False
