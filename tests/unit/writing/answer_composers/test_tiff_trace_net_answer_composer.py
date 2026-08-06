from __future__ import annotations
import json
from pathlib import Path
from tiff.trace_net_answer_composer import AnswerComposerOptions, AnswerComposerPaths, compose_answer

def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(data)+'\n',encoding='utf-8')
def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')

def test_compose_answer_from_grouped_results(tmp_path: Path):
    search_dir=tmp_path/'search'; out_dir=tmp_path/'answers'
    _write_json(search_dir/'trace_net_search_summary.json', {'effective_query':'120-50645-009'})
    _write_json(search_dir/'trace_net_search_grouped_summary.json', {'status':'OK','grouped_page_records':1})
    _write_jsonl(search_dir/'trace_net_search_grouped_results.jsonl', [{
        'page_id':'p1','group_score':12.5,'best_score':10,'supporting_result_count':2,
        'rag_buckets':['verified_part_evidence','source_text_evidence'],'evidence_layers':['part_catalog','source_text'],
        'matched_part_numbers':['120-50645-009'],'matched_terms':['seat'], 'source_url':'http://localhost/p1','tiff_path':'pages/p1.tif','ocr_path':'ocr/p1.txt',
        'safe_group':True,'unsafe_supporting_results':0,'excluded_supporting_results':0,
        'citations':[{'citation_markdown':'Citation p1','citation_id':'c1'}],
        'supporting_results':[{'candidate_id':'c1','score':10,'rag_bucket':'verified_part_evidence','evidence_layer':'part_catalog','final_trust_tier':'A','final_rag_action':'include_as_verified_part_evidence','usable_confidence':0.9,'matched_part_numbers':['120-50645-009'],'source_url':'http://localhost/p1','tiff_path':'pages/p1.tif','ocr_path':'ocr/p1.txt','text_preview':'Part 120-50645-009 appears here.'},{'candidate_id':'c2','score':9,'rag_bucket':'source_text_evidence','evidence_layer':'source_text','final_trust_tier':'A','final_rag_action':'include_as_source_evidence','usable_confidence':0.8,'matched_terms':['seat'],'source_url':'http://localhost/p1','tiff_path':'pages/p1.tif','ocr_path':'ocr/p1.txt','text_preview':'Seat bottom text.'}]
    }])
    res=compose_answer(AnswerComposerPaths(search_dir=search_dir,output_dir=out_dir), AnswerComposerOptions())
    assert res['summary']['status']=='OK'
    assert res['summary']['answer_page_records']==1
    assert res['summary']['answer_evidence_records']==2
    assert '120-50645-009' in (out_dir/'trace_net_answer_draft.md').read_text(encoding='utf-8')

def test_compose_answer_filters_unsafe_group(tmp_path: Path):
    search_dir=tmp_path/'search'; out_dir=tmp_path/'answers'
    _write_json(search_dir/'trace_net_search_summary.json', {'effective_query':'x'}); _write_json(search_dir/'trace_net_search_grouped_summary.json', {'status':'OK'})
    _write_jsonl(search_dir/'trace_net_search_grouped_results.jsonl', [
        {'page_id':'unsafe','group_score':1,'rag_buckets':['table_candidate'],'supporting_results':[{'candidate_id':'bad','rag_bucket':'table_candidate','evidence_layer':'table_candidate'}],'safe_group':False},
        {'page_id':'safe','group_score':2,'rag_buckets':['source_evidence'],'source_url':'url','tiff_path':'tif','ocr_path':'ocr','safe_group':True,'unsafe_supporting_results':0,'excluded_supporting_results':0,'supporting_results':[{'candidate_id':'good','rag_bucket':'source_evidence','evidence_layer':'source_trace','final_rag_action':'include_as_source_evidence'}]},
    ])
    res=compose_answer(AnswerComposerPaths(search_dir=search_dir,output_dir=out_dir), AnswerComposerOptions())
    assert res['summary']['answer_page_records']==1
    assert res['answer']['sections'][0]['page_id']=='safe'
