import json
from pathlib import Path

from tiff.trace_net_rag_eligibility import RagEligibilityOptions, RagEligibilityPaths, build_rag_eligibility
from tiff.trace_net_rag_eligibility_quality import RagEligibilityQualityOptions, RagEligibilityQualityPaths, run_rag_eligibility_quality


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def make_good_artifacts(tmp_path: Path):
    stage5 = tmp_path / 'stage5.jsonl'
    rows = [
        {'record_id': 'source:p1', 'page_id': 'p1', 'evidence_layer': 'source_trace', 'final_trust_tier': 'A', 'final_rag_action': 'include_as_source_evidence', 'source_trace_status': 'source_verified'},
        {'record_id': 'part:p1', 'page_id': 'p1', 'evidence_layer': 'part_catalog', 'final_trust_tier': 'A', 'final_rag_action': 'include_as_verified_part_evidence', 'source_trace_status': 'source_verified'},
        {'record_id': 'derived:p1', 'page_id': 'p1', 'evidence_layer': 'table_tile_text_refined', 'final_trust_tier': 'B', 'final_rag_action': 'include_as_derived_context', 'source_trace_status': 'source_verified'},
        {'record_id': 'excluded:p1', 'page_id': 'p1', 'evidence_layer': 'table_tiles', 'final_trust_tier': 'B', 'final_rag_action': 'exclude_until_table_text_exists', 'source_trace_status': 'source_verified'},
    ]
    write_jsonl(stage5, rows)
    paths = RagEligibilityPaths(stage5_records=stage5, output_dir=tmp_path / 'rag')
    build_rag_eligibility(paths, RagEligibilityOptions())
    return paths


def test_rag_eligibility_quality_passes(tmp_path):
    paths = make_good_artifacts(tmp_path)
    qpaths = RagEligibilityQualityPaths(
        summary=paths.summary,
        all_records=paths.all_records,
        source_evidence=paths.source,
        verified_part_evidence=paths.verified_part,
        derived_context=paths.derived,
        excluded_records=paths.excluded,
        graph_nodes=paths.graph_nodes,
        graph_edges=paths.graph_edges,
        quality=tmp_path / 'quality.json',
    )
    result = run_rag_eligibility_quality(qpaths, RagEligibilityQualityOptions(
        min_records=4,
        min_pages=1,
        min_source_evidence_records=1,
        min_verified_part_records=1,
        min_derived_context_records=1,
        write_json=True,
    ))
    assert result['status'] == 'OK'
    assert qpaths.quality.exists()


def test_rag_eligibility_quality_fails_on_unsafe(tmp_path):
    stage5 = tmp_path / 'stage5.jsonl'
    write_jsonl(stage5, [
        {'record_id': 'unsafe', 'page_id': 'p1', 'evidence_layer': 'table_candidate', 'final_trust_tier': 'B', 'final_rag_action': 'include_as_derived_context', 'source_trace_status': 'source_verified'},
    ])
    paths = RagEligibilityPaths(stage5_records=stage5, output_dir=tmp_path / 'rag')
    build_rag_eligibility(paths, RagEligibilityOptions())
    qpaths = RagEligibilityQualityPaths(summary=paths.summary, all_records=paths.all_records, source_evidence=paths.source, verified_part_evidence=paths.verified_part, derived_context=paths.derived, excluded_records=paths.excluded, graph_nodes=paths.graph_nodes, graph_edges=paths.graph_edges)
    result = run_rag_eligibility_quality(qpaths, RagEligibilityQualityOptions(min_records=1, min_pages=1, max_unsafe_rag_eligible_records=0))
    assert result['status'] == 'FAIL'
    assert any(not c['ok'] and c['name'] == 'unsafe_rag_eligible' for c in result['checks'])
