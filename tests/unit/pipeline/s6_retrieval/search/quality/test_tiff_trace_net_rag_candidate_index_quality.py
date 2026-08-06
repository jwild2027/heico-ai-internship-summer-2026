import json
from pathlib import Path

from tiff.trace_net_rag_candidate_index_quality import (
    RagCandidateIndexQualityOptions,
    RagCandidateIndexQualityPaths,
    run_rag_candidate_index_quality,
)


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row) + '\n')


def test_rag_candidate_index_quality_accepts_source_text_pool(tmp_path):
    output = tmp_path / 'candidates'
    rows = [
        {'page_id': 'p1', 'rag_bucket': 'source_evidence', 'evidence_layer': 'source_trace', 'final_trust_tier': 'A', 'text': 'source'},
        {'page_id': 'p1', 'rag_bucket': 'source_text_evidence', 'evidence_layer': 'source_text', 'final_trust_tier': 'A', 'text': 'seat bottom backrest', 'metadata': {'source_text_ocr_joined': True}},
        {'page_id': 'p1', 'rag_bucket': 'verified_part_evidence', 'evidence_layer': 'part_catalog', 'final_trust_tier': 'A', 'text': 'part 120-12345-001'},
        {'page_id': 'p1', 'rag_bucket': 'derived_context', 'evidence_layer': 'table_tile_text_refined', 'final_trust_tier': 'B', 'text': 'derived', 'metadata': {'refined_tile_joined': True}},
    ]
    write_jsonl(output / 'rag_candidate_chunks.jsonl', rows)
    write_jsonl(output / 'rag_candidate_source_chunks.jsonl', [rows[0]])
    write_jsonl(output / 'rag_candidate_source_text_chunks.jsonl', [rows[1]])
    write_jsonl(output / 'rag_candidate_verified_part_chunks.jsonl', [rows[2]])
    write_jsonl(output / 'rag_candidate_derived_chunks.jsonl', [rows[3]])
    (output / 'rag_candidate_summary.json').write_text(json.dumps({
        'status': 'OK',
        'records': 4,
        'pages': 1,
        'source_candidate_records': 1,
        'source_text_candidate_records': 1,
        'source_text_ocr_joined_records': 1,
        'verified_part_candidate_records': 1,
        'derived_context_candidate_records': 1,
        'derived_context_joined_records': 1,
        'derived_context_unjoined_records': 0,
        'unsafe_candidate_records': 0,
        'empty_text_records': 0,
    }), encoding='utf-8')
    (output / 'rag_candidate_graph_nodes.json').write_text(json.dumps([{'id': 'n'}]), encoding='utf-8')
    (output / 'rag_candidate_graph_edges.json').write_text(json.dumps([{'source': 'n', 'target': 'm'}]), encoding='utf-8')

    result = run_rag_candidate_index_quality(
        RagCandidateIndexQualityPaths(
            summary=output / 'rag_candidate_summary.json',
            all_candidates=output / 'rag_candidate_chunks.jsonl',
            source_candidates=output / 'rag_candidate_source_chunks.jsonl',
            source_text_candidates=output / 'rag_candidate_source_text_chunks.jsonl',
            verified_part_candidates=output / 'rag_candidate_verified_part_chunks.jsonl',
            derived_candidates=output / 'rag_candidate_derived_chunks.jsonl',
            graph_nodes=output / 'rag_candidate_graph_nodes.json',
            graph_edges=output / 'rag_candidate_graph_edges.json',
            quality=output / 'quality.json',
        ),
        RagCandidateIndexQualityOptions(
            min_records=4,
            min_pages=1,
            min_source_candidates=1,
            min_source_text_candidates=1,
            min_source_text_ocr_joined_records=1,
            min_verified_part_candidates=1,
            min_derived_candidates=1,
            min_derived_joined_records=1,
            max_derived_unjoined_records=0,
        ),
    )
    assert result['status'] == 'OK'
    assert result['source_text_candidate_records'] == 1
    assert result['source_text_ocr_joined_scan'] == 1


def test_quality_flags_source_text_unsafe_if_bucket_not_allowed(tmp_path):
    output = tmp_path / 'candidates'
    bad = {'page_id': 'p1', 'rag_bucket': 'unsafe_bucket', 'evidence_layer': 'source_text', 'final_trust_tier': 'A', 'text': 'text'}
    write_jsonl(output / 'rag_candidate_chunks.jsonl', [bad])
    write_jsonl(output / 'rag_candidate_source_chunks.jsonl', [])
    write_jsonl(output / 'rag_candidate_source_text_chunks.jsonl', [])
    write_jsonl(output / 'rag_candidate_verified_part_chunks.jsonl', [])
    write_jsonl(output / 'rag_candidate_derived_chunks.jsonl', [])
    (output / 'rag_candidate_summary.json').write_text(json.dumps({'status': 'OK', 'records': 1, 'pages': 1, 'unsafe_candidate_records': 1, 'empty_text_records': 0, 'source_candidate_records': 0, 'source_text_candidate_records': 0, 'verified_part_candidate_records': 0, 'derived_context_candidate_records': 0}), encoding='utf-8')
    (output / 'rag_candidate_graph_nodes.json').write_text(json.dumps([{'id': 'n'}]), encoding='utf-8')
    (output / 'rag_candidate_graph_edges.json').write_text(json.dumps([{'source': 'n', 'target': 'm'}]), encoding='utf-8')

    result = run_rag_candidate_index_quality(
        RagCandidateIndexQualityPaths(
            summary=output / 'rag_candidate_summary.json',
            all_candidates=output / 'rag_candidate_chunks.jsonl',
            source_candidates=output / 'rag_candidate_source_chunks.jsonl',
            source_text_candidates=output / 'rag_candidate_source_text_chunks.jsonl',
            verified_part_candidates=output / 'rag_candidate_verified_part_chunks.jsonl',
            derived_candidates=output / 'rag_candidate_derived_chunks.jsonl',
            graph_nodes=output / 'rag_candidate_graph_nodes.json',
            graph_edges=output / 'rag_candidate_graph_edges.json',
        ),
        RagCandidateIndexQualityOptions(max_unsafe_candidate_records=0),
    )
    assert result['status'] == 'FAIL'
