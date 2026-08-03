from __future__ import annotations
import argparse,json
from dataclasses import dataclass
from pathlib import Path
from typing import Any,Mapping,Sequence
from tiff.trace_net_answer_composer import DEFAULT_OUTPUT_DIR

@dataclass(frozen=True)
class AnswerQualityPaths:
    output_dir:Path=DEFAULT_OUTPUT_DIR; answer_json_path:Path|None=None; answer_md_path:Path|None=None; answer_html_path:Path|None=None; evidence_jsonl_path:Path|None=None; summary_path:Path|None=None; graph_nodes_path:Path|None=None; graph_edges_path:Path|None=None; quality_path:Path|None=None
    @property
    def answer_json(self): return self.answer_json_path or self.output_dir/'trace_net_answer_draft.json'
    @property
    def answer_md(self): return self.answer_md_path or self.output_dir/'trace_net_answer_draft.md'
    @property
    def answer_html(self): return self.answer_html_path or self.output_dir/'trace_net_answer_draft.html'
    @property
    def evidence_jsonl(self): return self.evidence_jsonl_path or self.output_dir/'trace_net_answer_evidence.jsonl'
    @property
    def summary(self): return self.summary_path or self.output_dir/'trace_net_answer_summary.json'
    @property
    def graph_nodes(self): return self.graph_nodes_path or self.output_dir/'trace_net_answer_graph_nodes.json'
    @property
    def graph_edges(self): return self.graph_edges_path or self.output_dir/'trace_net_answer_graph_edges.json'
    @property
    def quality(self): return self.quality_path or self.output_dir/'trace_net_answer_quality.json'

@dataclass(frozen=True)
class AnswerQualityOptions:
    min_pages:int=1; min_evidence_records:int=1; min_citation_groups:int=0; max_unsafe_groups:int=0; max_missing_source_url_groups:int|None=None; max_missing_tiff_path_groups:int|None=None; max_missing_ocr_path_groups:int|None=None; require_status_ok:bool=True; write_json:bool=False

def _read_json(path:Path):
    if not path.exists(): return {}
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return {}
def _jsonl_count(path:Path)->int:
    if not path.exists(): return 0
    return sum(1 for line in path.read_text(encoding='utf-8',errors='replace').splitlines() if line.strip())

def check_answer_quality(paths:AnswerQualityPaths, options:AnswerQualityOptions|None=None)->dict[str,Any]:
    options=options or AnswerQualityOptions(); sm=_read_json(paths.summary); ans=_read_json(paths.answer_json); evidence_count=_jsonl_count(paths.evidence_jsonl); nodes=_read_json(paths.graph_nodes); edges=_read_json(paths.graph_edges); node_count=len(nodes) if isinstance(nodes,list) else 0; edge_count=len(edges) if isinstance(edges,list) else 0
    checks=[]
    def add(n,ok,d): checks.append({'name':n,'status':'OK' if ok else 'FAIL','detail':d})
    add('artifacts_present', paths.summary.exists() and paths.answer_json.exists() and paths.answer_md.exists() and paths.answer_html.exists() and paths.evidence_jsonl.exists(), f'summary={paths.summary.exists()}; answer_json={paths.answer_json.exists()}; md={paths.answer_md.exists()}; html={paths.answer_html.exists()}; evidence={paths.evidence_jsonl.exists()}')
    status=sm.get('status'); add('status_ok', (not options.require_status_ok) or status=='OK', f'status={status}')
    pages=int(sm.get('answer_page_records') or 0); add('answer_pages', pages>=options.min_pages, f'answer_page_records={pages}; minimum={options.min_pages}')
    summ_ev=int(sm.get('answer_evidence_records') or 0); add('evidence_records', evidence_count>=options.min_evidence_records and evidence_count==summ_ev, f'summary={summ_ev}; jsonl={evidence_count}; minimum={options.min_evidence_records}')
    unsafe=int(sm.get('unsafe_answer_groups') or 0); add('unsafe_groups', unsafe<=options.max_unsafe_groups, f'unsafe_answer_groups={unsafe}; max={options.max_unsafe_groups}')
    cits=int(sm.get('groups_with_citations') or 0); add('citation_groups', cits>=options.min_citation_groups, f'groups_with_citations={cits}; minimum={options.min_citation_groups}')
    missing_source=int(sm.get('missing_source_url_groups') or 0)
    if options.max_missing_source_url_groups is not None: add('missing_source_url', missing_source<=options.max_missing_source_url_groups, f'missing_source_url_groups={missing_source}; max={options.max_missing_source_url_groups}')
    missing_tiff=int(sm.get('missing_tiff_path_groups') or 0)
    if options.max_missing_tiff_path_groups is not None: add('missing_tiff_path', missing_tiff<=options.max_missing_tiff_path_groups, f'missing_tiff_path_groups={missing_tiff}; max={options.max_missing_tiff_path_groups}')
    missing_ocr=int(sm.get('missing_ocr_path_groups') or 0)
    if options.max_missing_ocr_path_groups is not None: add('missing_ocr_path', missing_ocr<=options.max_missing_ocr_path_groups, f'missing_ocr_path_groups={missing_ocr}; max={options.max_missing_ocr_path_groups}')
    answer_text=str(ans.get('answer') or ''); add('answer_text', bool(answer_text.strip()), f'answer_text_chars={len(answer_text)}'); add('graph_nodes', node_count>0, f'graph_nodes={node_count}'); add('graph_edges', edge_count>0, f'graph_edges={edge_count}')
    ok=all(c['status']=='OK' for c in checks); q={'status':'OK' if ok else 'FAIL','summary':{'answer_summary_present':paths.summary.exists(),'answer_json_present':paths.answer_json.exists(),'answer_md_present':paths.answer_md.exists(),'answer_html_present':paths.answer_html.exists(),'answer_status':status,'answer_page_records':pages,'answer_evidence_records':summ_ev,'answer_evidence_jsonl_records':evidence_count,'answer_unsafe_groups':unsafe,'answer_groups_with_citations':cits,'answer_missing_source_url_groups':missing_source,'answer_missing_tiff_path_groups':missing_tiff,'answer_missing_ocr_path_groups':missing_ocr,'answer_graph_nodes':node_count,'answer_graph_edges':edge_count,'answer_summary_path':str(paths.summary),'answer_json_path':str(paths.answer_json)},'checks':checks}
    if options.write_json: paths.quality.parent.mkdir(parents=True,exist_ok=True); paths.quality.write_text(json.dumps(q,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return q

def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Check TRACE-Net answer composer quality.'); p.add_argument('--output-dir',type=Path,default=DEFAULT_OUTPUT_DIR); p.add_argument('--summary',type=Path,default=None); p.add_argument('--answer-json',type=Path,default=None); p.add_argument('--answer-md',type=Path,default=None); p.add_argument('--answer-html',type=Path,default=None); p.add_argument('--evidence-jsonl',type=Path,default=None); p.add_argument('--graph-nodes',type=Path,default=None); p.add_argument('--graph-edges',type=Path,default=None); p.add_argument('--quality',type=Path,default=None); p.add_argument('--min-pages',type=int,default=1); p.add_argument('--min-evidence-records',type=int,default=1); p.add_argument('--min-citation-groups',type=int,default=0); p.add_argument('--max-unsafe-groups',type=int,default=0); p.add_argument('--max-missing-source-url-groups',type=int,default=None); p.add_argument('--max-missing-tiff-path-groups',type=int,default=None); p.add_argument('--max-missing-ocr-path-groups',type=int,default=None); p.add_argument('--write-json',action='store_true')
    a=p.parse_args(argv); paths=AnswerQualityPaths(output_dir=a.output_dir,summary_path=a.summary,answer_json_path=a.answer_json,answer_md_path=a.answer_md,answer_html_path=a.answer_html,evidence_jsonl_path=a.evidence_jsonl,graph_nodes_path=a.graph_nodes,graph_edges_path=a.graph_edges,quality_path=a.quality); opts=AnswerQualityOptions(min_pages=a.min_pages,min_evidence_records=a.min_evidence_records,min_citation_groups=a.min_citation_groups,max_unsafe_groups=a.max_unsafe_groups,max_missing_source_url_groups=a.max_missing_source_url_groups,max_missing_tiff_path_groups=a.max_missing_tiff_path_groups,max_missing_ocr_path_groups=a.max_missing_ocr_path_groups,write_json=a.write_json)
    res=check_answer_quality(paths,opts); print('TRACE-Net answer composer quality gate'); print(f"  Status: {res.get('status')}"); print('  Summary:')
    for k,v in res.get('summary',{}).items(): print(f'    {k}: {v}')
    print('  Checks:')
    for c in res.get('checks',[]): print(f"    {c.get('status')} {c.get('name')}: {c.get('detail')}")
    if a.write_json: print(f'\nJSON: {paths.quality}')
    return 0 if res.get('status')=='OK' else 1
if __name__=='__main__': raise SystemExit(main())
