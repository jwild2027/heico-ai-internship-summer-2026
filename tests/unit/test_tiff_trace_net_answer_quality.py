from __future__ import annotations
import json
from pathlib import Path
from tiff.trace_net_answer_composer import AnswerComposerOptions, AnswerComposerPaths, compose_answer
from tiff.trace_net_answer_quality import AnswerQualityOptions, AnswerQualityPaths, check_answer_quality

def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(data)+'\n',encoding='utf-8')
def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
def _build_answer(tmp_path: Path):
    sd=tmp_path/'search'; od=tmp_path/'answers'
    _write_json(sd/'trace_net_search_summary.json', {'effective_query':'seat'}); _write_json(sd/'trace_net_search_grouped_summary.json', {'status':'OK'})
    _write_jsonl(sd/'trace_net_search_grouped_results.jsonl', [{'page_id':'p1','group_score':5,'rag_buckets':['source_text_evidence'],'evidence_layers':['source_text'],'matched_terms':['seat'],'source_url':'url','tiff_path':'tif','ocr_path':'ocr','safe_group':True,'unsafe_supporting_results':0,'excluded_supporting_results':0,'citations':[{'citation_markdown':'Citation p1'}],'supporting_results':[{'candidate_id':'good','rag_bucket':'source_text_evidence','evidence_layer':'source_text','final_trust_tier':'A','final_rag_action':'include_as_source_evidence','usable_confidence':0.8,'source_url':'url','tiff_path':'tif','ocr_path':'ocr','text_preview':'seat text'}]}])
    compose_answer(AnswerComposerPaths(search_dir=sd,output_dir=od), AnswerComposerOptions())
    return od

def test_answer_quality_ok(tmp_path: Path):
    od=_build_answer(tmp_path)
    q=check_answer_quality(AnswerQualityPaths(output_dir=od), AnswerQualityOptions(min_pages=1,min_evidence_records=1,min_citation_groups=1,max_unsafe_groups=0))
    assert q['status']=='OK'
    assert q['summary']['answer_page_records']==1
    assert q['summary']['answer_groups_with_citations']==1

def test_answer_quality_fails_when_missing_required_citation(tmp_path: Path):
    od=_build_answer(tmp_path)
    q=check_answer_quality(AnswerQualityPaths(output_dir=od), AnswerQualityOptions(min_pages=1,min_evidence_records=1,min_citation_groups=2))
    assert q['status']=='FAIL'
