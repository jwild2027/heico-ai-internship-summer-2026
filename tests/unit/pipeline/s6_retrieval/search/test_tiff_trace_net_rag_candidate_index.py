import json
from pathlib import Path

from tiff.trace_net_rag_candidate_index import RagCandidateIndexOptions, RagCandidateIndexPaths, build_rag_candidate_index


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row) + '\n')


def base_row(source_record_id='source:p1', page_id='p1'):
    return {
        'source_record_id': source_record_id,
        'page_id': page_id,
        'evidence_layer': 'source_trace',
        'rag_bucket': 'source_evidence',
        'final_trust_tier': 'A',
        'final_rag_action': 'include_as_source_evidence',
        'usable_confidence': 0.91,
        'source_trace_status': 'source_verified',
    }


def test_build_rag_candidate_index_creates_safe_source_text_chunks(tmp_path):
    rag_dir = tmp_path / 'rag'
    export_dir = tmp_path / 'export'
    refined_dir = tmp_path / 'refined'
    output_dir = tmp_path / 'candidates'
    ocr_dir = tmp_path / 'ocr'
    ocr_dir.mkdir()
    ocr_file = ocr_dir / 'p1.txt'
    ocr_file.write_text('Seat bottom backrest text. Part 120-12345-001 appears here.', encoding='utf-8')

    write_jsonl(rag_dir / 'rag_eligible_source_evidence.jsonl', [base_row()])
    write_jsonl(rag_dir / 'rag_eligible_verified_part_evidence.jsonl', [
        {
            'source_record_id': 'part:p1',
            'page_id': 'p1',
            'evidence_layer': 'part_catalog',
            'rag_bucket': 'verified_part_evidence',
            'final_trust_tier': 'A',
            'final_rag_action': 'include_as_verified_part_evidence',
            'usable_confidence': 0.88,
            'source_trace_status': 'source_verified',
        }
    ])
    write_jsonl(rag_dir / 'rag_eligible_derived_context.jsonl', [
        {
            'source_record_id': 'tile_p1_001',
            'page_id': 'p1',
            'evidence_layer': 'table_tile_text_refined',
            'rag_bucket': 'derived_context',
            'final_trust_tier': 'B',
            'final_rag_action': 'include_as_derived_context',
            'usable_confidence': 0.76,
            'source_trace_status': 'source_verified',
        }
    ])
    (export_dir / 'page_index.json').parent.mkdir(parents=True, exist_ok=True)
    (export_dir / 'page_index.json').write_text(json.dumps({
        'pages': [
            {
                'page_id': 'p1',
                'document_id': 'doc1',
                'ata_code': '25-21-00',
                'source_url': 'http://example/source/p1',
                'tiff_path': 'pages/p1.tif',
                'ocr_path': str(ocr_file),
                'part_numbers': ['120-12345-001'],
                'context_summary': 'Passenger seat page with seat bottom and backrest.',
            }
        ]
    }), encoding='utf-8')
    write_jsonl(refined_dir / 'table_tile_text_refined_records.jsonl', [
        {
            'tile_id': 'tile_p1_001',
            'page_id': 'p1',
            'catalog_supported_part_numbers': ['120-12345-001'],
            'canonical_part_numbers': ['120-12345-001'],
            'text': '120-12345-001 SEAT PART',
        }
    ])

    result = build_rag_candidate_index(
        RagCandidateIndexPaths(rag_dir=rag_dir, export_dir=export_dir, refined_table_dir=refined_dir, output_dir=output_dir),
        RagCandidateIndexOptions(max_text_chars=2000, max_source_text_chars=2000, min_source_text_chars=10),
    )

    assert result['records'] == 4
    assert result['source_candidate_records'] == 1
    assert result['source_text_candidate_records'] == 1
    assert result['source_text_ocr_joined_records'] == 1
    assert result['verified_part_candidate_records'] == 1
    assert result['derived_context_candidate_records'] == 1
    assert result['unsafe_candidate_records'] == 0
    chunks = [json.loads(line) for line in (output_dir / 'rag_candidate_chunks.jsonl').read_text().splitlines()]
    assert len(chunks) == 4
    source_text = [row for row in chunks if row['rag_bucket'] == 'source_text_evidence'][0]
    assert source_text['evidence_layer'] == 'source_text'
    assert 'Seat bottom backrest text' in source_text['text']
    assert source_text['metadata']['source_text_ocr_joined'] is True


def test_candidate_index_can_disable_source_text(tmp_path):
    rag_dir = tmp_path / 'rag'
    output_dir = tmp_path / 'candidates'
    write_jsonl(rag_dir / 'rag_eligible_source_evidence.jsonl', [base_row()])
    write_jsonl(rag_dir / 'rag_eligible_verified_part_evidence.jsonl', [])
    write_jsonl(rag_dir / 'rag_eligible_derived_context.jsonl', [])
    result = build_rag_candidate_index(
        RagCandidateIndexPaths(rag_dir=rag_dir, output_dir=output_dir),
        RagCandidateIndexOptions(include_source_text=False),
    )
    assert result['records'] == 1
    assert result['source_text_candidate_records'] == 0


def test_candidate_index_flags_unsafe_if_bad_layer_is_indexed(tmp_path):
    rag_dir = tmp_path / 'rag'
    output_dir = tmp_path / 'candidates'
    write_jsonl(rag_dir / 'rag_eligible_source_evidence.jsonl', [])
    write_jsonl(rag_dir / 'rag_eligible_verified_part_evidence.jsonl', [])
    write_jsonl(rag_dir / 'rag_eligible_derived_context.jsonl', [
        {
            'source_record_id': 'bad:candidate',
            'page_id': 'p1',
            'evidence_layer': 'table_candidate',
            'rag_bucket': 'derived_context',
            'final_trust_tier': 'B',
            'final_rag_action': 'include_as_derived_context',
            'source_trace_status': 'source_verified',
        }
    ])
    result = build_rag_candidate_index(RagCandidateIndexPaths(rag_dir=rag_dir, output_dir=output_dir), RagCandidateIndexOptions())
    assert result['unsafe_candidate_records'] == 1
    assert result['status'] == 'WARN'


def test_derived_context_join_accepts_stage5_wrapped_tile_id(tmp_path):
    rag_dir = tmp_path / 'rag'
    export_dir = tmp_path / 'export'
    refined_dir = tmp_path / 'refined'
    output_dir = tmp_path / 'candidates'
    page_id = 't_p_120_1176_p000003'
    real_tile_id = f'{page_id}_tile_001'
    wrapped_tile_id = f'tile_{real_tile_id}'

    write_jsonl(rag_dir / 'rag_eligible_source_evidence.jsonl', [])
    write_jsonl(rag_dir / 'rag_eligible_verified_part_evidence.jsonl', [])
    write_jsonl(rag_dir / 'rag_eligible_derived_context.jsonl', [
        {
            'source_record_id': f'table_tile_text_refined:{page_id}:{wrapped_tile_id}',
            'page_id': page_id,
            'evidence_layer': 'table_tile_text_refined',
            'rag_bucket': 'derived_context',
            'final_trust_tier': 'B',
            'final_rag_action': 'include_as_derived_context',
            'usable_confidence': 0.88,
            'source_trace_status': 'source_verified',
        }
    ])
    (export_dir / 'page_index.json').parent.mkdir(parents=True, exist_ok=True)
    (export_dir / 'page_index.json').write_text(json.dumps({'pages': [{'page_id': page_id, 'source_url': 'http://example/p3'}]}), encoding='utf-8')
    write_jsonl(refined_dir / 'table_tile_text_refined_records.jsonl', [
        {
            'page_id': page_id,
            'tile_id': real_tile_id,
            'tile_index': 1,
            'catalog_supported_part_numbers': ['120-50645-009'],
            'canonical_part_numbers': ['120-50645-009'],
            'unsupported_part_candidates': ['120-50645-037'],
            'index_labels': ['25-APPLICABILITY'],
            'text': '120-50645-009\n25-APPLICABILITY',
        }
    ])

    result = build_rag_candidate_index(
        RagCandidateIndexPaths(rag_dir=rag_dir, export_dir=export_dir, refined_table_dir=refined_dir, output_dir=output_dir),
        RagCandidateIndexOptions(max_text_chars=2000),
    )
    assert result['derived_context_joined_records'] == 1
    chunks = [json.loads(line) for line in (output_dir / 'rag_candidate_derived_chunks.jsonl').read_text().splitlines()]
    assert chunks[0]['metadata']['refined_tile_joined'] is True
    assert chunks[0]['metadata']['refined_tile_id'] == real_tile_id
    assert '120-50645-009' in chunks[0]['text']
