import json
from pathlib import Path

from tiff.trace_net_search_grouper import SearchGroupOptions, SearchGroupPaths, group_search_results
from tiff.trace_net_search_grouper_quality import SearchGroupQualityOptions, SearchGroupQualityPaths, evaluate_search_group_quality


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def test_quality_passes_for_safe_grouped_results(tmp_path):
    search_dir = tmp_path / 'search'
    out = tmp_path / 'out'
    write_jsonl(search_dir / 'trace_net_search_results.jsonl', [
        {
            'rank': 1,
            'score': 10,
            'candidate_id': 'c1',
            'page_id': 'p001',
            'rag_bucket': 'source_text_evidence',
            'evidence_layer': 'source_text',
            'final_trust_tier': 'A',
            'final_rag_action': 'include_as_source_evidence',
            'source_url': 'http://src/p001',
            'tiff_path': 'p001.tif',
            'ocr_path': 'p001.txt',
            'text_preview': 'seat bottom backrest',
            'safe_candidate': True,
        }
    ])
    group_search_results(SearchGroupPaths(search_dir=search_dir, output_dir=out), SearchGroupOptions())
    quality = evaluate_search_group_quality(SearchGroupQualityPaths(output_dir=out), SearchGroupQualityOptions(min_groups=1, min_pages=1, max_unsafe_groups=0, max_excluded_groups=0, write_json=True))
    assert quality['status'] == 'OK'
    assert quality['summary']['search_group_grouped_page_records'] == 1
    assert quality['summary']['search_group_groups_with_source_url'] == 1
    assert (out / 'trace_net_search_grouped_quality.json').exists()


def test_quality_fails_when_unsafe_group_present(tmp_path):
    search_dir = tmp_path / 'search'
    out = tmp_path / 'out'
    write_jsonl(search_dir / 'trace_net_search_results.jsonl', [
        {
            'rank': 1,
            'score': 10,
            'candidate_id': 'c1',
            'page_id': 'p001',
            'rag_bucket': 'table_tiles',
            'evidence_layer': 'table_tiles',
            'final_rag_action': 'exclude_until_table_text_exists',
            'source_url': 'http://src/p001',
            'safe_candidate': False,
        }
    ])
    group_search_results(SearchGroupPaths(search_dir=search_dir, output_dir=out), SearchGroupOptions())
    quality = evaluate_search_group_quality(SearchGroupQualityPaths(output_dir=out), SearchGroupQualityOptions(max_unsafe_groups=0, max_missing_source_url_groups=0))
    assert quality['status'] == 'FAIL'
    assert quality['summary']['search_group_unsafe_grouped_records_scan'] > 0
