import json
from pathlib import Path

from tiff.trace_net_rag_eligibility import RagEligibilityOptions, RagEligibilityPaths, build_rag_eligibility


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def test_build_rag_eligibility_splits_stage5_records(tmp_path):
    stage5 = tmp_path / 'stage5.jsonl'
    rows = [
        {
            'record_id': 'source:p1',
            'page_id': 'p1',
            'evidence_layer': 'source_trace',
            'final_trust_tier': 'A',
            'final_rag_action': 'include_as_source_evidence',
            'final_repair_action': 'none',
            'source_trace_status': 'source_verified',
            'stage5_controlled': True,
            'decision_source': 'confidence_policy_controlled',
            'usable_confidence': 0.91,
        },
        {
            'record_id': 'part:p1',
            'page_id': 'p1',
            'evidence_layer': 'part_catalog',
            'final_trust_tier': 'A',
            'final_rag_action': 'include_as_verified_part_evidence',
            'final_repair_action': 'none',
            'source_trace_status': 'source_verified',
            'stage5_controlled': True,
            'usable_confidence': 0.88,
        },
        {
            'record_id': 'table:p1:t1',
            'page_id': 'p1',
            'evidence_layer': 'table_tile_text_refined',
            'final_trust_tier': 'B',
            'final_rag_action': 'include_as_derived_context',
            'final_repair_action': 'none',
            'source_trace_status': 'source_verified',
            'stage5_controlled': True,
            'usable_confidence': 0.74,
        },
        {
            'record_id': 'candidate:p2',
            'page_id': 'p2',
            'evidence_layer': 'table_candidate',
            'final_trust_tier': 'C',
            'final_rag_action': 'exclude_until_table_tiles_exist',
            'final_repair_action': 'run_table_crop_tile',
            'source_trace_status': 'source_verified',
            'stage5_controlled': False,
        },
    ]
    write_jsonl(stage5, rows)
    paths = RagEligibilityPaths(stage5_records=stage5, output_dir=tmp_path / 'rag')
    result = build_rag_eligibility(paths, RagEligibilityOptions())
    assert result['records'] == 4
    assert result['source_evidence_records'] == 1
    assert result['verified_part_evidence_records'] == 1
    assert result['derived_context_records'] == 1
    assert result['rag_excluded_records'] == 1
    assert result['unsafe_rag_eligible_records'] == 0
    assert paths.source.exists()
    assert paths.verified_part.exists()
    assert paths.derived.exists()
    assert paths.excluded.exists()
    assert json.loads(paths.summary.read_text())['rag_bucket_counts']['source_evidence'] == 1


def test_rag_eligibility_blocks_unsafe_include(tmp_path):
    stage5 = tmp_path / 'stage5.jsonl'
    write_jsonl(stage5, [
        {
            'record_id': 'bad:table_candidate',
            'page_id': 'p1',
            'evidence_layer': 'table_candidate',
            'final_trust_tier': 'B',
            'final_rag_action': 'include_as_derived_context',
            'source_trace_status': 'source_verified',
        },
        {
            'record_id': 'bad:source',
            'page_id': 'p2',
            'evidence_layer': 'source_trace',
            'final_trust_tier': 'A',
            'final_rag_action': 'include_as_source_evidence',
            'source_trace_status': 'missing_tiff',
        },
    ])
    paths = RagEligibilityPaths(stage5_records=stage5, output_dir=tmp_path / 'rag')
    result = build_rag_eligibility(paths, RagEligibilityOptions())
    assert result['unsafe_rag_eligible_records'] == 2
    assert result['rag_eligible_records'] == 0
    excluded = [json.loads(line) for line in paths.excluded.read_text().splitlines()]
    assert len(excluded) == 2
    assert all(row['unsafe_rag_eligible'] for row in excluded)
