from __future__ import annotations
import argparse, html, json, re, webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

VERSION='trace_net_answer_composer_v1'
DEFAULT_SEARCH_DIR=Path('local_data/organization/trace_net/search')
DEFAULT_OUTPUT_DIR=Path('local_data/organization/trace_net/answers')
SAFE_BUCKETS={'source_evidence','source_text_evidence','verified_part_evidence','derived_context'}
SAFE_ACTIONS={'include_as_source_evidence','include_as_verified_part_evidence','include_as_derived_context',''}
UNSAFE_LAYERS={'table_candidate','table_tiles'}
BUCKET_LABELS={'source_evidence':'source/citation evidence','source_text_evidence':'source OCR/text evidence','verified_part_evidence':'verified part evidence','derived_context':'derived table/context evidence'}

@dataclass(frozen=True)
class AnswerComposerPaths:
    search_dir: Path=DEFAULT_SEARCH_DIR; output_dir: Path=DEFAULT_OUTPUT_DIR
    grouped_results_path: Path|None=None; grouped_summary_path: Path|None=None; search_summary_path: Path|None=None
    answer_json_path: Path|None=None; answer_md_path: Path|None=None; answer_html_path: Path|None=None
    evidence_jsonl_path: Path|None=None; summary_path: Path|None=None; graph_nodes_path: Path|None=None; graph_edges_path: Path|None=None
    @property
    def grouped_results(self): return self.grouped_results_path or self.search_dir/'trace_net_search_grouped_results.jsonl'
    @property
    def grouped_summary(self): return self.grouped_summary_path or self.search_dir/'trace_net_search_grouped_summary.json'
    @property
    def search_summary(self): return self.search_summary_path or self.search_dir/'trace_net_search_summary.json'
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

@dataclass(frozen=True)
class AnswerComposerOptions:
    max_pages:int=10; max_evidence_per_page:int=6; max_preview_chars:int=450; include_supporting_text:bool=True; open_report:bool=False

def _utc(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def _txt(v:Any, default=''):
    if v is None: return default
    s=str(v).strip(); return s if s else default
def _num(v:Any, default=0.0):
    try: return float(v) if v is not None else default
    except Exception: return default
def _list(v:Any): return list(v) if isinstance(v,list) else []
def _dict(v:Any): return dict(v) if isinstance(v,Mapping) else {}
def _clip(v:Any,n:int):
    s=_txt(v); return s if len(s)<=n else s[:max(0,n-1)].rstrip()+'…'
def _slug(v:Any):
    s=re.sub(r'[^a-z0-9._:-]+','_',_txt(v).lower()); return re.sub(r'_+','_',s).strip('_') or 'unknown'
def _uniq(vals:Iterable[Any]):
    out=[]; seen=set()
    for v in vals:
        s=_txt(v); k=s.lower()
        if s and k not in seen: seen.add(k); out.append(s)
    return out
def _count(vals:Iterable[str]):
    d={}
    for v in vals:
        if v: d[v]=d.get(v,0)+1
    return dict(sorted(d.items()))
def _read_json(path:Path):
    if not path.exists(): return {}
    try: v=json.loads(path.read_text(encoding='utf-8'))
    except Exception: return {}
    return dict(v) if isinstance(v,Mapping) else {}
def _read_jsonl(path:Path):
    rows=[]
    if not path.exists(): return rows
    with path.open('r',encoding='utf-8',errors='replace') as h:
        for line in h:
            line=line.strip()
            if not line: continue
            try: v=json.loads(line)
            except Exception: continue
            if isinstance(v,Mapping): rows.append(dict(v))
    return rows
def _write_json(path:Path,data:Any): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8')
def _write_jsonl(path:Path,rows:Sequence[Mapping[str,Any]]):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8') as h:
        for r in rows: h.write(json.dumps(dict(r),sort_keys=True,ensure_ascii=False)+'\n')
def _write_text(path:Path,s:str): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(s,encoding='utf-8')

def _safe_support(row:Mapping[str,Any]):
    return _txt(row.get('rag_bucket')) in SAFE_BUCKETS and _txt(row.get('evidence_layer')) not in UNSAFE_LAYERS and _txt(row.get('final_rag_action')) in SAFE_ACTIONS and row.get('safe_result') is not False and row.get('safe_candidate') is not False

def _safe_group(group:Mapping[str,Any]):
    if group.get('safe_group') is False or int(group.get('unsafe_supporting_results') or 0)>0 or int(group.get('excluded_supporting_results') or 0)>0: return False
    return all(_safe_support(s) for s in _list(group.get('supporting_results')))

def _query(grouped:Mapping[str,Any], search:Mapping[str,Any]):
    for src in (search,grouped):
        for k in ('effective_query','query','part_number','page_id'):
            if _txt(src.get(k)): return _txt(src.get(k))
        q=_dict(src.get('query'))
        for k in ('effective_query','query','part_number','page_id'):
            if _txt(q.get(k)): return _txt(q.get(k))
    return 'latest TRACE-Net search'

def _citation(group:Mapping[str,Any]):
    for c in _list(group.get('citations')):
        if isinstance(c,Mapping) and _txt(c.get('citation_markdown')): return _txt(c.get('citation_markdown'))
    bits=[]
    if _txt(group.get('source_url')): bits.append('Source URL: '+_txt(group.get('source_url')))
    if _txt(group.get('tiff_path')): bits.append('TIFF: '+_txt(group.get('tiff_path')))
    if _txt(group.get('ocr_path')): bits.append('OCR: '+_txt(group.get('ocr_path')))
    return '; '.join(bits)

def _bucket_sentence(buckets:Sequence[str]):
    labels=[BUCKET_LABELS.get(b,b) for b in buckets]
    if not labels: return 'supporting evidence'
    return labels[0] if len(labels)==1 else ', '.join(labels[:-1])+', and '+labels[-1]

def _section_sentence(group:Mapping[str,Any], buckets, parts, terms):
    pg=_txt(group.get('page_id'),'unknown page'); support=int(group.get('supporting_result_count') or len(_list(group.get('supporting_results'))))
    extra=''
    if parts: extra=' Matched part number(s): '+', '.join(parts[:8])+'.'
    elif terms: extra=' Matched term(s): '+', '.join(terms[:8])+'.'
    return f'Page {pg} is supported by {support} TRACE-Net evidence record(s), including {_bucket_sentence(buckets)}.{extra}'

def _evidence_rows(group:Mapping[str,Any], max_evidence:int, max_preview:int):
    rows=[]
    for s in _list(group.get('supporting_results'))[:max(1,max_evidence)]:
        if not isinstance(s,Mapping): continue
        rows.append({'page_id':_txt(group.get('page_id')),'candidate_id':_txt(s.get('candidate_id') or s.get('chunk_id')),'rank':int(s.get('rank') or 0),'score':round(_num(s.get('score')),6),'rag_bucket':_txt(s.get('rag_bucket')),'evidence_layer':_txt(s.get('evidence_layer')),'trust_tier':_txt(s.get('final_trust_tier')),'usable_confidence':round(_num(s.get('usable_confidence')),6),'matched_part_numbers':_uniq(s.get('matched_part_numbers') or []),'matched_terms':_uniq(s.get('matched_terms') or []),'source_url':_txt(s.get('source_url') or group.get('source_url')),'tiff_path':_txt(s.get('tiff_path') or group.get('tiff_path')),'ocr_path':_txt(s.get('ocr_path') or group.get('ocr_path')),'text_preview':_clip(s.get('text_preview'),max_preview),'citation_markdown':_txt(s.get('citation_markdown'))})
    return rows

def compose_answer(paths:AnswerComposerPaths, options:AnswerComposerOptions|None=None):
    options=options or AnswerComposerOptions()
    groups_all=_read_jsonl(paths.grouped_results); grouped=_read_json(paths.grouped_summary); search=_read_json(paths.search_summary)
    safe=[g for g in groups_all if _safe_group(g)]; groups=safe[:max(1,options.max_pages)]; query=_query(grouped,search)
    evidence=[]; sections=[]
    for i,g in enumerate(groups,1):
        buckets=_uniq(g.get('rag_buckets') or []); parts=_uniq(g.get('matched_part_numbers') or []); terms=_uniq(g.get('matched_terms') or [])
        ev=_evidence_rows(g,options.max_evidence_per_page,options.max_preview_chars); evidence.extend(ev)
        ata=', '.join(_list(g.get('ata_codes'))) or _txt(g.get('ata_code'))
        title=f'{i}. Page {_txt(g.get("page_id"))}' + (f' — ATA {ata}' if ata else '')
        sections.append({'rank':i,'page_id':_txt(g.get('page_id')),'title':title,'group_score':round(_num(g.get('group_score')),6),'best_score':round(_num(g.get('best_score')),6),'supporting_result_count':int(g.get('supporting_result_count') or len(ev)),'evidence_buckets':buckets,'evidence_layers':_uniq(g.get('evidence_layers') or []),'matched_part_numbers':parts,'matched_terms':terms,'source_url':_txt(g.get('source_url')),'tiff_path':_txt(g.get('tiff_path')),'ocr_path':_txt(g.get('ocr_path')),'citation_markdown':_citation(g),'answer_sentence':_section_sentence(g,buckets,parts,terms),'supporting_evidence':ev})
    summary={'status':'OK' if sections else 'FAIL','version':VERSION,'created_at':_utc(),'query':query,'grouped_results_path':str(paths.grouped_results),'group_records_loaded':len(groups_all),'safe_group_records_loaded':len(safe),'answer_page_records':len(sections),'answer_source_records':len(sections),'answer_evidence_records':len(evidence),'unsafe_answer_groups':len(groups_all)-len(safe),'missing_source_url_groups':sum(1 for s in sections if not s['source_url']),'missing_tiff_path_groups':sum(1 for s in sections if not s['tiff_path']),'missing_ocr_path_groups':sum(1 for s in sections if not s['ocr_path']),'groups_with_citations':sum(1 for s in sections if s['citation_markdown'] or s['source_url']),'bucket_counts':_count(b for s in sections for b in s['evidence_buckets']),'evidence_layer_counts':_count(l for s in sections for l in s['evidence_layers']),'matched_part_numbers':_uniq(p for s in sections for p in s['matched_part_numbers']),'matched_terms':_uniq(t for s in sections for t in s['matched_terms']),'top_group_score':sections[0]['group_score'] if sections else 0,'paths':{'answer_json':str(paths.answer_json),'answer_md':str(paths.answer_md),'answer_html':str(paths.answer_html),'evidence_jsonl':str(paths.evidence_jsonl),'summary':str(paths.summary),'graph_nodes':str(paths.graph_nodes),'graph_edges':str(paths.graph_edges)}}
    answer={'status':summary['status'],'version':VERSION,'query':query,'summary':summary,'answer':_plain_answer(query,sections),'sections':sections,'safety_note':'This deterministic draft is composed only from TRACE-Net RAG-eligible grouped search results. It does not use excluded records or model-generated answers.'}
    nodes,edges=_graph(sections,summary)
    _write_json(paths.answer_json,answer); _write_text(paths.answer_md,_render_md(answer)); _write_text(paths.answer_html,_render_html(answer)); _write_jsonl(paths.evidence_jsonl,evidence); _write_json(paths.summary,summary); _write_json(paths.graph_nodes,nodes); _write_json(paths.graph_edges,edges)
    if options.open_report:
        try: webbrowser.open(paths.answer_html.resolve().as_uri())
        except Exception: pass
    return {'summary':summary,'answer':answer,'evidence_rows':evidence,'graph_nodes':nodes,'graph_edges':edges}

def _plain_answer(query,sections):
    if not sections: return f'No TRACE-Net safe grouped results were available for query: {query}.'
    lines=[f'TRACE-Net found {len(sections)} source-backed page result(s) for: {query}.']
    lines += [f"{s['rank']}. {s['answer_sentence']}" for s in sections]
    lines.append('All listed results are from RAG-eligible TRACE-Net candidate chunks and include source trace metadata.')
    return '\n'.join(lines)

def _graph(sections,summary):
    nodes={'trace_net:answer_draft':{'id':'trace_net:answer_draft','type':'trace_net_answer','query':summary.get('query'),'version':VERSION}}; edges=[]
    def add(nid,typ,**attrs):
        if not nid: return
        node=nodes.setdefault(nid,{'id':nid,'type':typ}); node.update({k:v for k,v in attrs.items() if v not in ('',None,[])})
    for s in sections:
        pg=s['page_id']; gid='answer_page:'+_slug(pg); add(gid,'answer_page_result',page_id=pg,rank=s['rank'],group_score=s['group_score']); add(pg,'page')
        edges.append({'source':'trace_net:answer_draft','target':gid,'type':'HAS_PAGE_RESULT'}); edges.append({'source':gid,'target':pg,'type':'ANSWERS_WITH_PAGE'})
        for b in s['evidence_buckets']: bid='rag_bucket:'+b; add(bid,'rag_bucket'); edges.append({'source':gid,'target':bid,'type':'SUPPORTED_BY_BUCKET'})
        for ev in s['supporting_evidence']:
            cid=ev.get('candidate_id'); add(cid,'rag_candidate_chunk',rag_bucket=ev.get('rag_bucket'),evidence_layer=ev.get('evidence_layer')); edges.append({'source':gid,'target':cid,'type':'SUPPORTED_BY_CHUNK'})
    return list(nodes.values()),edges

def _md_table(headers,rows):
    out=['| '+' | '.join(headers)+' |','|'+'|'.join('---' for _ in headers)+'|']
    for row in rows: out.append('| '+' | '.join(_txt(c).replace('\n','<br>') for c in row)+' |')
    return '\n'.join(out)

def _render_md(payload):
    sm=_dict(payload.get('summary')); sections=_list(payload.get('sections'))
    lines=['# TRACE-Net Answer Composer v1','',f"Status: **{payload.get('status','UNKNOWN')}**  Version: `{payload.get('version',VERSION)}`",'',f"Query: `{payload.get('query','')}`",'','## Draft answer','',_txt(payload.get('answer')),'','## Summary','',_md_table(['Metric','Value'],[[k,sm.get(k)] for k in ('answer_page_records','answer_evidence_records','unsafe_answer_groups','groups_with_citations','missing_source_url_groups','missing_tiff_path_groups','missing_ocr_path_groups','top_group_score')]),'','## Page results','']
    lines.append(_md_table(['Rank','Page','Score','Evidence','Matches','Source URL'],[[s.get('rank'),s.get('page_id'),s.get('group_score'),', '.join(_list(s.get('evidence_buckets'))),', '.join(_list(s.get('matched_part_numbers'))[:8]) or ', '.join(_list(s.get('matched_terms'))[:8]),s.get('source_url')] for s in sections])); lines.append('')
    for s in sections:
        lines += [f"## {_txt(s.get('title'))}",'',_txt(s.get('answer_sentence')),'']
        if s.get('citation_markdown'): lines += ['Citation:','',_txt(s.get('citation_markdown')),'']
        if s.get('supporting_evidence'):
            lines += ['Supporting evidence:','']
            for ev in _list(s.get('supporting_evidence')):
                lines.append(f"- bucket={_txt(ev.get('rag_bucket'))}; layer={_txt(ev.get('evidence_layer'))}; trust={_txt(ev.get('trust_tier'))}; confidence={ev.get('usable_confidence')}")
                if ev.get('text_preview'): lines.append('  - preview: '+_txt(ev.get('text_preview')))
            lines.append('')
    lines += ['## Safety note','',_txt(payload.get('safety_note')),'']
    return '\n'.join(lines)

def _render_html(payload):
    body=[]; inlist=False
    for line in _render_md(payload).splitlines():
        if line.startswith('# '):
            if inlist: body.append('</ul>'); inlist=False
            body.append('<h1>'+html.escape(line[2:])+'</h1>')
        elif line.startswith('## '):
            if inlist: body.append('</ul>'); inlist=False
            body.append('<h2>'+html.escape(line[3:])+'</h2>')
        elif line.startswith('- '):
            if not inlist: body.append('<ul>'); inlist=True
            body.append('<li>'+html.escape(line[2:])+'</li>')
        elif line.startswith('|'):
            if inlist: body.append('</ul>'); inlist=False
            body.append('<pre>'+html.escape(line)+'</pre>')
        elif line.strip():
            if inlist: body.append('</ul>'); inlist=False
            body.append('<p>'+html.escape(line)+'</p>')
    if inlist: body.append('</ul>')
    return "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Answer Composer</title><style>body{font-family:Arial,sans-serif;max-width:1200px;margin:24px auto;line-height:1.45}pre{background:#f6f8fa;padding:6px;overflow:auto}li{margin:4px 0}</style></head><body>"+'\n'.join(body)+'</body></html>'

def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Build deterministic TRACE-Net answer draft from grouped search results.')
    p.add_argument('--grouped-results',type=Path,default=None); p.add_argument('--grouped-summary',type=Path,default=None); p.add_argument('--search-summary',type=Path,default=None); p.add_argument('--output-dir',type=Path,default=DEFAULT_OUTPUT_DIR); p.add_argument('--max-pages',type=int,default=10); p.add_argument('--max-evidence-per-page',type=int,default=6); p.add_argument('--max-preview-chars',type=int,default=450); p.add_argument('--open',action='store_true')
    a=p.parse_args(argv); paths=AnswerComposerPaths(output_dir=a.output_dir,grouped_results_path=a.grouped_results,grouped_summary_path=a.grouped_summary,search_summary_path=a.search_summary); opts=AnswerComposerOptions(max_pages=a.max_pages,max_evidence_per_page=a.max_evidence_per_page,max_preview_chars=a.max_preview_chars,open_report=a.open)
    res=compose_answer(paths,opts); sm=res['summary']
    print('TRACE-Net answer composer'); print(f"  Status: {sm.get('status')}"); print(f'  Output dir: {paths.output_dir}'); print('  Summary:')
    for k in ('query','answer_page_records','answer_evidence_records','unsafe_answer_groups','groups_with_citations','missing_source_url_groups','missing_tiff_path_groups','missing_ocr_path_groups'): print(f'    {k}: {sm.get(k)}')
    print('Files written:'); print(f'  answer_json: {paths.answer_json}'); print(f'  answer_md: {paths.answer_md}'); print(f'  answer_html: {paths.answer_html}'); print(f'  evidence_jsonl: {paths.evidence_jsonl}'); print(f'  summary: {paths.summary}'); print(f'  graph_nodes: {paths.graph_nodes}'); print(f'  graph_edges: {paths.graph_edges}')
    return 0 if sm.get('status')=='OK' else 1
if __name__=='__main__': raise SystemExit(main())
