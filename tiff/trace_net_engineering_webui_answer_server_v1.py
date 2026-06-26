
"""TRACE-Net Engineering WebUI Answer Server v1.2.

OpenAI-compatible local server for Open WebUI.

v1.2 quality patch:
- retries Gemma4 once when the first LLM response is empty
- cleans OCR/fishnet/router debug text before prompts and fallback output
- only uses gated lookup when requested seed part matches the gated draft
- adds visible source notes to answers
- preserves exact lookup, random page summary, and fallback artifact search

Safety:
- no Postgres/Qdrant/OpenSearch writes
- no source-truth mutation
- no final answer permission
- Gemma4 composes only from TRACE-Net evidence
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import time
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MODULE_VERSION = "trace_net_engineering_webui_answer_server_v1"
REPORT_NAME = "trace_net_engineering_webui_answer_server_v1.json"
MODEL_ID = "trace-net-engineering-webui-v1"

DEFAULT_FINAL_GATE = Path("local_data/organization/trace_net/engineering_draft_final_gate_retry_micro/trace_net_engineering_draft_final_gate_v1.json")
DEFAULT_RUNNER = Path("local_data/organization/trace_net/engineering_gemma_draft_runner_retry_micro/trace_net_engineering_gemma_draft_runner_v1.json")
DEFAULT_PAGE_CONTEXT = Path("local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json")
DEFAULT_FISHNET = Path("local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json")
DEFAULT_ROUTE_HANDOFF = Path("local_data/organization/trace_net/fishnet_route_dispatch_handoff/trace_net_fishnet_route_dispatch_handoff_v1.json")

@dataclass(frozen=True)
class LLMConfig:
    mode: str = "off"
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "gemma4:26b"
    api_key: str = "ollama"
    request_timeout: int = 240
    temperature: float = 0.0
    max_tokens: int = 900
    retry_empty_response: bool = True
    @property
    def enabled(self) -> bool:
        return self.mode != "off"

def _read_json(path: Path, *, required: bool=False) -> Dict[str, Any]:
    if not path.exists():
        if required: raise FileNotFoundError(f"missing JSON file: {path}")
        return {}
    return json.loads(path.read_text(encoding='utf-8'))

def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')

def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in records: f.write(json.dumps(r, sort_keys=True) + '\n')

def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or '').strip())

def _lower(text: Any) -> str:
    return _norm(text).lower()

def _path(path_text: Any) -> Path:
    return Path(str(path_text or '').replace('\\', '/'))

def _part_numbers(text: Any) -> List[str]:
    return sorted(set(re.findall(r"\b\d{3}-\d{5}-\d{3}\b", str(text or ''))))

def _clean_trace_text(text: Any, *, max_chars: int = 1800) -> str:
    s = str(text or '')
    for token in [
        'trace_net_fishnet_ocr_grid_v1', 'fishnet_page_grid_card',
        'FISHNET_ROUTE_SIGNALS_BUILT', 'FISHNET_ROUTE_SIGNALS_REVIEW_REQUIRED',
        'router_classifier_input_only'
    ]:
        s = s.replace(token, ' ')
    s = re.sub(r"\bsource_p\d{6}_r\d{2}_c\d{2}\b", " ", s)
    s = re.sub(r"\bt_p_\d+_\d+_p\d{6}_r\d{2}_c\d{2}\b", " ", s)
    s = re.sub(r"(\d{3})-\s*(\d{5})-\s*(\d{3})", r"\1-\2-\3", s)
    s = re.sub(r"\bCleane\b", "Cleaner", s)
    s = re.sub(r"\bPassanger\b", "Passenger", s)
    s = re.sub(r"\s*[<€-]*\s*EMBRAER\s+MAINTENANCE\s+MANUAL\s+WITH\s+ILLUSTRATED\s+PARTS\s+LIST\s*", " EMBRAER MAINTENANCE MANUAL WITH ILLUSTRATED PARTS LIST ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_chars].strip()

def _flatten_strings(value: Any, *, max_items: int = 80) -> List[str]:
    out: List[str] = []
    def walk(v: Any) -> None:
        if len(out) >= max_items: return
        if isinstance(v, str):
            txt = _clean_trace_text(v, max_chars=1000)
            if len(txt) >= 20: out.append(txt)
        elif isinstance(v, Mapping):
            for key in ['v2_summary','summary','page_summary','text','ocr_text','content','sample','fishnet_ocr_sample_text','source_text_excerpt','excerpt','title','heading']:
                if key in v: walk(v[key])
            for key, child in v.items():
                if key not in {'embedding','vector','pixels','image_bytes'}: walk(child)
        elif isinstance(v, list):
            for item in v: walk(item)
    walk(value)
    return out[:max_items]

def _records_from_payload(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ['records','pages','page_records','items','documents']:
        value = payload.get(key)
        if isinstance(value, list): return [dict(v) for v in value if isinstance(v, dict)]
    records = []
    for key, value in payload.items():
        if isinstance(value, dict) and ('page_id' in value or key.startswith(('source_','t_p_','metadata_page'))):
            clone = dict(value); clone.setdefault('page_id', key); records.append(clone)
    return records

def _page_id(record: Mapping[str, Any], index: int) -> str:
    for key in ['page_id','source_page_id','id','page_key']:
        if record.get(key): return str(record.get(key))
    return f"page_{index+1:06d}"

def _page_num(record: Mapping[str, Any], index: int) -> Optional[int]:
    for key in ['page_number','page_index','source_page_number','page']:
        v = record.get(key)
        if isinstance(v, int): return v
        if isinstance(v, str) and v.isdigit(): return int(v)
    m = re.search(r"p0*(\d+)", str(record.get('page_id') or ''))
    return int(m.group(1)) if m else index+1

def _route(record: Mapping[str, Any]) -> str:
    for key in ['accepted_route','route','route_candidate','fishnet_route_candidate','current_route','page_route']:
        if record.get(key): return str(record.get(key))
    return 'unknown'

def load_page_index(*, page_context_path: Path=DEFAULT_PAGE_CONTEXT, fishnet_path: Path=DEFAULT_FISHNET, route_handoff_path: Path=DEFAULT_ROUTE_HANDOFF) -> List[Dict[str, Any]]:
    page_context = _read_json(page_context_path)
    fishnet = _read_json(fishnet_path)
    route_handoff = _read_json(route_handoff_path)
    route_by_page: Dict[str, str] = {}
    for r in _records_from_payload(route_handoff):
        pid = str(r.get('page_id') or r.get('source_page_id') or '')
        if pid: route_by_page[pid] = str(r.get('accepted_route') or r.get('route') or '')
    raw = _records_from_payload(page_context)
    fish_records = _records_from_payload(fishnet)
    if not raw and fish_records: raw = fish_records
    fish_by_page = {_page_id(r, i): r for i, r in enumerate(fish_records)}
    pages = []
    for i, r in enumerate(raw):
        pid = _page_id(r, i); fish = fish_by_page.get(pid, {})
        strings = _flatten_strings(r)
        if fish: strings += _flatten_strings(fish, max_items=20)
        text = _clean_trace_text(' '.join(strings), max_chars=3000)
        pages.append({'page_id': pid, 'page_number': _page_num(r, i), 'route': route_by_page.get(pid) or _route(r) or _route(fish), 'text': text, 'source_record_index': i, 'has_text': bool(text), 'has_v2_summary': any(k in r for k in ['v2_summary','summary','page_summary'])})
    return pages

def _read_gated_draft_text(runner_record: Mapping[str, Any]) -> str:
    path_text = runner_record.get('draft_response_path')
    if not path_text: return ''
    path = _path(path_text)
    if not path.exists(): return ''
    return _clean_trace_text(_read_json(path).get('draft_text') or '', max_chars=6000)

def load_gated_drafts(*, final_gate_path: Path=DEFAULT_FINAL_GATE, runner_path: Path=DEFAULT_RUNNER) -> List[Dict[str, Any]]:
    final_gate = _read_json(final_gate_path); runner = _read_json(runner_path)
    rr = _records_from_payload(runner)
    by_id = {str(r.get('runner_record_id')): r for r in rr if r.get('runner_record_id')}
    by_packet = {str(r.get('source_draft_packet_id')): r for r in rr if r.get('source_draft_packet_id')}
    out = []
    for r in _records_from_payload(final_gate):
        if not r.get('ready_for_manual_review'): continue
        rid = str(r.get('source_runner_record_id') or ''); pid = str(r.get('source_draft_packet_id') or '')
        draft = _read_gated_draft_text(by_id.get(rid) or by_packet.get(pid) or {})
        out.append({'user_question': r.get('user_question'), 'seed_part_numbers': _part_numbers(str(r.get('user_question') or '') + ' ' + draft), 'final_gate_status': r.get('final_gate_status'), 'final_gate_record_id': r.get('final_gate_record_id'), 'source_runner_record_id': rid, 'source_draft_packet_id': pid, 'draft_text': draft, 'draft_text_char_count': len(draft), 'answer_permission': False, 'ready_for_final_answer': False})
    return out

def _match_score(query: str, candidate: str) -> int:
    q = _lower(query); c = _lower(candidate)
    if not q or not c: return 0
    if q == c: return 100
    if q in c or c in q: return 85
    q_terms = set(re.findall(r"[a-z0-9-]+", q)); c_terms = set(re.findall(r"[a-z0-9-]+", c))
    return int(65 * (len(q_terms & c_terms) / max(1, len(q_terms)))) if q_terms else 0

def _choose_random_page(pages: Sequence[Mapping[str, Any]], question: str, *, truly_random: bool=True) -> Optional[Mapping[str, Any]]:
    text_pages = [p for p in pages if p.get('has_text') and str(p.get('text') or '').strip()]
    if not text_pages: return pages[0] if pages else None
    if truly_random: return random.choice(text_pages)
    seed = int(hashlib.sha256(question.encode()).hexdigest()[:8], 16)
    return text_pages[seed % len(text_pages)]

def _extractive_summary(page: Mapping[str, Any], *, max_chars: int=1200) -> str:
    text = _clean_trace_text(page.get('text') or '', max_chars=max_chars+500)
    if not text: return 'No readable text was found for this page in the currently loaded artifacts.'
    sentences = re.split(r"(?<=[.!?])\s+", text)
    useful, seen = [], set()
    for s in sentences:
        s = _clean_trace_text(s, max_chars=500); key = s.lower()
        if len(s) < 30 or key in seen: continue
        useful.append(s); seen.add(key)
        if sum(len(x) for x in useful) >= max_chars: break
    return (' '.join(useful) if useful else text[:max_chars])[:max_chars]

def _source_notes(citations: Sequence[Mapping[str, Any]]) -> str:
    parts = []
    for c in citations[:5]:
        if c.get('page_id'): parts.append(f"{c.get('page_id')} (page {c.get('page_number')}, route={c.get('route')})")
        elif c.get('final_gate_record_id'): parts.append(f"final_gate={c.get('final_gate_record_id')}")
    return '\n\nSource notes: ' + '; '.join(parts) + '.' if parts else ''

def _llm_endpoint(config: LLMConfig) -> str:
    base = config.base_url.rstrip('/')
    return base if base.endswith('/chat/completions') else f"{base}/chat/completions"

def _call_openai_compatible_llm(*, config: LLMConfig, messages: Sequence[Mapping[str, str]]) -> Tuple[str, Optional[str]]:
    if not config.enabled: return '', 'llm_mode_off'
    payload = {'model': config.model, 'messages': list(messages), 'temperature': config.temperature, 'max_tokens': config.max_tokens, 'stream': False}
    req = urllib.request.Request(_llm_endpoint(config), data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {config.api_key}'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=config.request_timeout) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='replace'))
        choices = data.get('choices') or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get('message') or {}; content = msg.get('content') if isinstance(msg, dict) else None
            if content and str(content).strip(): return _clean_trace_text(content, max_chars=6000), None
            if choices[0].get('text') and str(choices[0].get('text')).strip(): return _clean_trace_text(choices[0].get('text'), max_chars=6000), None
        return '', 'llm_empty_response'
    except Exception as exc:
        return '', f"{type(exc).__name__}: {exc}"

def _compose_with_llm(*, question: str, evidence_text: str, intent: str, citations: Sequence[Mapping[str, Any]], config: LLMConfig) -> Tuple[str, bool, Optional[str], int]:
    if not config.enabled: return evidence_text, False, 'llm_mode_off', 0
    evidence = _clean_trace_text(evidence_text, max_chars=6000); citation_text = json.dumps(list(citations), indent=2, sort_keys=True)
    system = 'You are Gemma4 writing as TRACE-Net controlled engineering assistant. Use only provided TRACE-Net evidence. Do not expose raw OCR/debug strings. Do not claim engineering approval, approved replacement, guaranteed fit, interchangeability, airworthiness, or safety to install. Include visible source page identifiers.'
    user = f"Question: {question}\n\nIntent: {intent}\n\nTRACE-Net evidence/context:\n{evidence[:6000]}\n\nCitation/source notes:\n{citation_text[:2500]}\n\nWrite a concise useful answer. Do not include debug tokens such as router_classifier_input_only."
    text, error = _call_openai_compatible_llm(config=config, messages=[{'role':'system','content':system},{'role':'user','content':user}])
    if not error and text.strip(): return text.strip(), True, None, 1
    if config.retry_empty_response and error == 'llm_empty_response':
        retry_user = f"Question: {question}\nEvidence:\n{evidence[:2200]}\nSources:\n{citation_text[:1200]}\nWrite 3-6 complete sentences or 5 bullets. No debug text."
        retry_text, retry_error = _call_openai_compatible_llm(config=config, messages=[{'role':'system','content':'Write a concise TRACE-Net answer from evidence. Include page IDs. No approval/safety claims.'},{'role':'user','content':retry_user}])
        if not retry_error and retry_text.strip(): return retry_text.strip(), True, None, 2
        return '', True, retry_error or error, 2
    return '', True, error or 'llm_empty_response', 1

def _response_record(*, question: str, response_text: str, intent: str, evidence_status: str, citations: Sequence[Mapping[str, Any]], response_kind: str, llm_config: LLMConfig, llm_called: bool, llm_error: Optional[str], llm_attempt_count: int=0) -> Dict[str, Any]:
    text = _clean_trace_text(response_text, max_chars=6000)
    if _source_notes(citations) and 'Source notes:' not in text: text += _source_notes(citations)
    return {'server_record_version': MODULE_VERSION, 'question': question, 'intent': intent, 'evidence_status': evidence_status, 'response_kind': response_kind, 'response_text': text, 'response_text_char_count': len(text), 'citations': list(citations), 'citation_count': len(citations), 'llm_mode': llm_config.mode, 'llm_model': llm_config.model if llm_config.enabled else None, 'llm_base_url': llm_config.base_url if llm_config.enabled else None, 'llm_called': llm_called, 'llm_error': llm_error, 'llm_attempt_count': llm_attempt_count, 'ready_for_webui_response': True, 'manual_review_required': True, 'ready_for_final_answer': False, 'answer_permission': False, 'can_answer_directly': False, 'can_prove_claims': False, 'llm_call_allowed': llm_config.enabled, 'retrieval_execution_allowed': False, 'source_truth_mutation_allowed': False, 'postgres_write_attempt': False, 'qdrant_write_attempt': False, 'opensearch_write_attempt': False, 'unsafe': False}

def answer_random_page_summary(question: str, pages: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Dict[str, Any]:
    page = _choose_random_page(pages, question, truly_random=True)
    if not page: return _response_record(question=question, response_text='TRACE-Net could not find loaded page records to summarize.', intent='random_page_summary', evidence_status='missing_page_records', citations=[], response_kind='controlled_no_answer', llm_config=llm_config, llm_called=False, llm_error=None)
    summary = _extractive_summary(page, max_chars=1800)
    citations = [{'page_id': page.get('page_id'), 'page_number': page.get('page_number'), 'route': page.get('route'), 'source': 'page_context_v2_or_fishnet'}]
    evidence = f"Selected page_id={page.get('page_id')}; page_number={page.get('page_number')}; route={page.get('route')}.\nExtracted page text:\n{summary}"
    fallback = f"TRACE-Net picked page `{page.get('page_id')}` (page_number={page.get('page_number')}, route={page.get('route')}).\n\n{summary}\n\nBoundary: this is an artifact-grounded page summary, not engineering approval or final maintenance instruction."
    llm_text, llm_called, llm_error, attempts = _compose_with_llm(question=question, evidence_text=evidence, intent='random_page_summary', citations=citations, config=llm_config)
    return _response_record(question=question, response_text=llm_text if llm_config.enabled and llm_called and not llm_error else fallback, intent='random_page_summary', evidence_status='page_record_selected', citations=citations, response_kind='gemma4_composed_page_summary' if llm_config.enabled and not llm_error else 'controlled_artifact_summary', llm_config=llm_config, llm_called=llm_called, llm_error=llm_error, llm_attempt_count=attempts)

def answer_gated_lookup(question: str, gated_drafts: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Optional[Dict[str, Any]]:
    requested = set(_part_numbers(question)); best = None; best_score = 0
    for draft in gated_drafts:
        seed = set(draft.get('seed_part_numbers') or [])
        if requested and not (requested & seed): continue
        score = _match_score(question, str(draft.get('user_question') or '')) + (25 if requested and requested & seed else 0)
        if score > best_score: best, best_score = draft, score
    if not best or best_score < 40 or not best.get('draft_text'): return None
    citations = [{'final_gate_record_id': best.get('final_gate_record_id'), 'source_runner_record_id': best.get('source_runner_record_id'), 'source_draft_packet_id': best.get('source_draft_packet_id')}]
    evidence = str(best.get('draft_text') or '')
    fallback = evidence + '\n\nBoundary: this is a TRACE-Net manual-review-ready controlled draft. Final answer permission is still off; verify before operational use.'
    llm_text, llm_called, llm_error, attempts = _compose_with_llm(question=question, evidence_text=evidence, intent='gated_lookup', citations=citations, config=llm_config)
    return _response_record(question=question, response_text=llm_text if llm_config.enabled and llm_called and not llm_error else fallback, intent='gated_lookup', evidence_status='manual_review_ready_final_gate_record', citations=citations, response_kind='gemma4_composed_gated_lookup' if llm_config.enabled and not llm_error else 'manual_review_ready_draft', llm_config=llm_config, llm_called=llm_called, llm_error=llm_error, llm_attempt_count=attempts)

def _search_pages(question: str, pages: Sequence[Mapping[str, Any]], *, top_k: int=3) -> List[Mapping[str, Any]]:
    q_terms = set(re.findall(r"[a-z0-9-]+", _lower(question)))
    if not q_terms: return []
    if q_terms & {'diagram','visual','callout'}: q_terms |= {'figure','illustrated','item','assy','assembly','view'}
    if 'repair' in q_terms: q_terms |= {'doubler','rivet','leg','lateral','epoxy'}
    scored = []
    for page in pages:
        text = _lower(page.get('text') or '')
        if not text: continue
        score = sum(1 for term in q_terms if term in text)
        for part in _part_numbers(question):
            if part.lower() in text: score += 15
        if score: scored.append((score, page))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [p for _, p in scored[:top_k]]

def answer_v2_summary_inventory(question: str, pages: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Dict[str, Any]:
    v2_pages = [p for p in pages if p.get('has_v2_summary') or p.get('has_text')]
    citations = [{'page_id': p.get('page_id'), 'page_number': p.get('page_number'), 'route': p.get('route'), 'source': 'page_context_v2_or_fishnet'} for p in v2_pages[:5]]
    lines = [f"- {p.get('page_id')} (page {p.get('page_number')}, route={p.get('route')})" for p in v2_pages[:10]]
    text = f"TRACE-Net has page-summary/text artifacts for {len(v2_pages)} pages. Here are the first few page records available for summary-style responses:\n" + '\n'.join(lines) + '\n\nBoundary: this reports artifact availability, not engineering content approval.'
    return _response_record(question=question, response_text=text, intent='v2_summary_inventory', evidence_status='page_summary_inventory', citations=citations, response_kind='controlled_inventory', llm_config=llm_config, llm_called=False, llm_error=None)

def answer_search_summary(question: str, pages: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Dict[str, Any]:
    hits = _search_pages(question, pages)
    if not hits: return _response_record(question=question, response_text='TRACE-Net did not find enough artifact text to answer that question yet. Try an exact part lookup, a random page summary, or a more specific term.', intent='fallback_search', evidence_status='no_page_text_hits', citations=[], response_kind='controlled_no_answer', llm_config=llm_config, llm_called=False, llm_error=None)
    citations = [{'page_id': p.get('page_id'), 'page_number': p.get('page_number'), 'route': p.get('route'), 'source': 'page_context_v2_or_fishnet'} for p in hits]
    blocks = [f"page_id={p.get('page_id')}; page_number={p.get('page_number')}; route={p.get('route')}; text={_extractive_summary(p, max_chars=750)}" for p in hits]
    evidence = '\n\n'.join(blocks)
    fallback = 'TRACE-Net found these artifact-backed page leads:\n\n' + '\n'.join(f"- `{c['page_id']}` (page {c.get('page_number')}, route={c.get('route')}): {_clean_trace_text(b, max_chars=550)}" for c, b in zip(citations, blocks)) + '\n\nBoundary: these are search/summarization leads, not proof of fit, replacement, safety, or engineering approval.'
    llm_text, llm_called, llm_error, attempts = _compose_with_llm(question=question, evidence_text=evidence, intent='fallback_search', citations=citations, config=llm_config)
    return _response_record(question=question, response_text=llm_text if llm_config.enabled and llm_called and not llm_error else fallback, intent='fallback_search', evidence_status='page_text_hits', citations=citations, response_kind='gemma4_composed_artifact_search' if llm_config.enabled and not llm_error else 'controlled_artifact_search', llm_config=llm_config, llm_called=llm_called, llm_error=llm_error, llm_attempt_count=attempts)

def answer_question(*, question: str, pages: Sequence[Mapping[str, Any]], gated_drafts: Sequence[Mapping[str, Any]], llm_config: LLMConfig) -> Dict[str, Any]:
    q = _lower(question)
    if 'v2 summary' in q or 'v2 summaries' in q: return answer_v2_summary_inventory(question, pages, llm_config=llm_config)
    if _part_numbers(question) or 'part number' in q or 'nearby similar' in q:
        lookup = answer_gated_lookup(question, gated_drafts, llm_config=llm_config)
        if lookup: return lookup
    if (('random' in q or 'choose' in q or 'pick' in q) and ('page' in q or 'manual' in q) and any(w in q for w in ['summarize','summary','say','tell me','explain'])):
        return answer_random_page_summary(question, pages, llm_config=llm_config)
    lookup = answer_gated_lookup(question, gated_drafts, llm_config=llm_config)
    if lookup: return lookup
    return answer_search_summary(question, pages, llm_config=llm_config)

def build_engineering_webui_answer_manifest(*, output_dir: Path, final_gate_path: Path=DEFAULT_FINAL_GATE, runner_path: Path=DEFAULT_RUNNER, page_context_path: Path=DEFAULT_PAGE_CONTEXT, fishnet_path: Path=DEFAULT_FISHNET, route_handoff_path: Path=DEFAULT_ROUTE_HANDOFF, sample_question: str='pick a random page to summarize', llm_config: LLMConfig=LLMConfig(), sample_call_llm: bool=False) -> Dict[str, Any]:
    pages = load_page_index(page_context_path=page_context_path, fishnet_path=fishnet_path, route_handoff_path=route_handoff_path)
    gated = load_gated_drafts(final_gate_path=final_gate_path, runner_path=runner_path)
    manifest_llm = llm_config if sample_call_llm else LLMConfig(mode='off', model=llm_config.model, base_url=llm_config.base_url, api_key=llm_config.api_key, request_timeout=llm_config.request_timeout, retry_empty_response=llm_config.retry_empty_response)
    sample = answer_question(question=sample_question, pages=pages, gated_drafts=gated, llm_config=manifest_llm)
    records = [sample]
    summary = {'page_record_count': len(pages), 'page_with_text_count': sum(1 for p in pages if p.get('has_text')), 'gated_draft_count': len(gated), 'sample_response_kind': sample.get('response_kind'), 'sample_response_char_count': sample.get('response_text_char_count'), 'sample_llm_called': sample.get('llm_called'), 'server_llm_mode': llm_config.mode, 'server_llm_model': llm_config.model if llm_config.enabled else None, 'server_llm_base_url': llm_config.base_url if llm_config.enabled else None, 'retry_empty_response_enabled': llm_config.retry_empty_response, 'webui_route_count': 4, 'openai_compatible_chat_completions_route': True, 'openwebui_api_chat_completions_route': True, 'models_route': True, 'health_route': True, 'ready_for_webui': True, 'answer_permission_count': sum(1 for r in records if r.get('answer_permission')), 'can_answer_directly_count': sum(1 for r in records if r.get('can_answer_directly')), 'can_prove_claims_count': sum(1 for r in records if r.get('can_prove_claims')), 'llm_call_allowed_count': 1 if llm_config.enabled else 0, 'retrieval_execution_allowed_count': sum(1 for r in records if r.get('retrieval_execution_allowed')), 'source_truth_mutation_allowed_count': sum(1 for r in records if r.get('source_truth_mutation_allowed')), 'postgres_write_attempt_count': sum(1 for r in records if r.get('postgres_write_attempt')), 'qdrant_write_attempt_count': sum(1 for r in records if r.get('qdrant_write_attempt')), 'opensearch_write_attempt_count': sum(1 for r in records if r.get('opensearch_write_attempt')), 'unsafe_record_count': sum(1 for r in records if r.get('unsafe'))}
    quality_status = 'PASS' if (summary['page_record_count'] > 0 or summary['gated_draft_count'] > 0) and summary['unsafe_record_count'] == 0 and summary['answer_permission_count'] == 0 else 'FAIL'
    payload = {'module': MODULE_VERSION, 'status': 'ENGINEERING_WEBUI_ANSWER_SERVER_MANIFEST_BUILT', 'quality_status': quality_status, 'summary': summary, 'model_id': MODEL_ID, 'llm_config': {'mode': llm_config.mode, 'base_url': llm_config.base_url, 'model': llm_config.model, 'api_key_mode': 'provided_to_server_runtime', 'request_timeout': llm_config.request_timeout, 'temperature': llm_config.temperature, 'max_tokens': llm_config.max_tokens, 'retry_empty_response': llm_config.retry_empty_response}, 'artifact_paths': {'final_gate': str(final_gate_path), 'runner': str(runner_path), 'page_context': str(page_context_path), 'fishnet': str(fishnet_path), 'route_handoff': str(route_handoff_path)}, 'routes': {'health': '/health', 'models': '/v1/models', 'chat_completions': '/v1/chat/completions', 'openwebui_chat_completions': '/api/chat/completions'}, 'records': records, 'safety_contract': {'artifact_authority': 'gemma4_connected_controlled_webui_response_server', 'manual_review_required': True, 'answers_are_controlled_responses': True, 'llm_call_allowed_when_runtime_llm_mode_enabled': True, 'retrieval_execution_allowed': False, 'source_truth_mutation_allowed': False, 'answer_permission': False, 'can_answer_directly': False, 'can_prove_claims': False, 'ready_for_final_answer': False, 'postgres_write_allowed': False, 'qdrant_write_allowed': False, 'opensearch_write_allowed': False}}
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload); _write_jsonl(output_dir / 'trace_net_engineering_webui_answer_server_v1_records.jsonl', records); _write_json(output_dir / 'trace_net_engineering_webui_answer_server_v1_summary.json', summary); _write_json(output_dir / 'trace_net_engineering_webui_answer_server_v1_quality.json', {'quality_status': quality_status, 'summary': summary})
    return payload

def check_engineering_webui_answer_server_quality(*, report_path: Path, min_page_records: int=1, min_gated_drafts: int=0, require_ready_for_webui: bool=False, require_llm_mode: Optional[str]=None, require_llm_model: Optional[str]=None, require_retry_empty_response: bool=False, max_unsafe: int=0, require_no_answer_permission: bool=False, require_no_retrieval_execution: bool=False, require_no_source_truth_mutation: bool=False) -> Dict[str, Any]:
    payload = _read_json(report_path, required=True); s = payload.get('summary') or {}; failures = []
    def fail_if(cond: bool, msg: str):
        if cond: failures.append(msg)
    fail_if(s.get('page_record_count', 0) < min_page_records, 'not enough page records')
    fail_if(s.get('gated_draft_count', 0) < min_gated_drafts, 'not enough gated drafts')
    if require_ready_for_webui:
        fail_if(not s.get('ready_for_webui'), 'not ready for WebUI'); fail_if(not s.get('openai_compatible_chat_completions_route'), 'missing OpenAI-compatible chat route')
    if require_llm_mode: fail_if(s.get('server_llm_mode') != require_llm_mode, f'server llm mode is not {require_llm_mode}')
    if require_llm_model: fail_if(s.get('server_llm_model') != require_llm_model, f'server llm model is not {require_llm_model}')
    if require_retry_empty_response: fail_if(not s.get('retry_empty_response_enabled'), 'retry empty response is not enabled')
    fail_if(s.get('unsafe_record_count', 0) > max_unsafe, 'unsafe record count exceeded')
    if require_no_answer_permission:
        fail_if(s.get('answer_permission_count', 0) != 0, 'answer permission count not zero'); fail_if(s.get('can_answer_directly_count', 0) != 0, 'can answer directly count not zero'); fail_if(s.get('can_prove_claims_count', 0) != 0, 'can prove claims count not zero')
    if require_no_retrieval_execution: fail_if(s.get('retrieval_execution_allowed_count', 0) != 0, 'retrieval execution allowed count not zero')
    if require_no_source_truth_mutation: fail_if(s.get('source_truth_mutation_allowed_count', 0) != 0, 'source truth mutation allowed count not zero')
    return {'quality_status': 'FAIL' if failures else 'PASS', 'summary': s, 'failures': failures, 'checked_report_path': str(report_path)}

class TraceNetWebUIHandler(BaseHTTPRequestHandler):
    server_version = 'TraceNetWebUIAnswerServer/1.2'
    def _json_response(self, status: int, payload: Mapping[str, Any]) -> None:
        raw = json.dumps(payload).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def _read_body_json(self) -> Dict[str, Any]:
        n = int(self.headers.get('Content-Length','0') or '0')
        return json.loads(self.rfile.read(n).decode('utf-8', errors='replace')) if n > 0 else {}
    def do_GET(self) -> None:
        if self.path in {'/health','/'}:
            self._json_response(200, {'status':'ok','module':MODULE_VERSION,'server_version':'v1.2','model_id':MODEL_ID,'page_record_count':len(self.server.pages),'gated_draft_count':len(self.server.gated_drafts),'llm_mode':self.server.llm_config.mode,'llm_model':self.server.llm_config.model if self.server.llm_config.enabled else None,'llm_base_url':self.server.llm_config.base_url if self.server.llm_config.enabled else None,'retry_empty_response':self.server.llm_config.retry_empty_response,'ready_for_webui':True}); return
        if self.path in {'/v1/models','/api/models'}:
            self._json_response(200, {'object':'list','data':[{'id':MODEL_ID,'object':'model','created':int(time.time()),'owned_by':'trace-net'}]}); return
        self._json_response(404, {'error': f'not found: {self.path}'})
    def do_POST(self) -> None:
        if self.path not in {'/v1/chat/completions','/api/chat/completions'}:
            self._json_response(404, {'error': f'not found: {self.path}'}); return
        try:
            body = self._read_body_json(); messages = body.get('messages') or []; question = ''
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get('role') == 'user': question = str(msg.get('content') or ''); break
            if not question: question = 'pick a random page to summarize'
            record = answer_question(question=question, pages=self.server.pages, gated_drafts=self.server.gated_drafts, llm_config=self.server.llm_config)
            self._json_response(200, {'id': f'chatcmpl-trace-net-{int(time.time()*1000)}','object':'chat.completion','created':int(time.time()),'model':body.get('model') or MODEL_ID,'choices':[{'index':0,'message':{'role':'assistant','content':record['response_text']},'finish_reason':'stop'}],'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0},'trace_net':record})
        except Exception as exc:
            self._json_response(500, {'error': f'{type(exc).__name__}: {exc}'})

class TraceNetHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: Tuple[str, int], handler_class: Any, *, pages: Sequence[Mapping[str, Any]], gated_drafts: Sequence[Mapping[str, Any]], llm_config: LLMConfig):
        super().__init__(server_address, handler_class); self.pages = list(pages); self.gated_drafts = list(gated_drafts); self.llm_config = llm_config

def run_server(*, host: str, port: int, final_gate_path: Path, runner_path: Path, page_context_path: Path, fishnet_path: Path, route_handoff_path: Path, llm_config: LLMConfig) -> None:
    pages = load_page_index(page_context_path=page_context_path, fishnet_path=fishnet_path, route_handoff_path=route_handoff_path); gated = load_gated_drafts(final_gate_path=final_gate_path, runner_path=runner_path)
    server = TraceNetHTTPServer((host, port), TraceNetWebUIHandler, pages=pages, gated_drafts=gated, llm_config=llm_config)
    print(f'TRACE-Net WebUI answer server v1.2 running on http://{host}:{port}'); print(f'Model ID exposed to WebUI: {MODEL_ID}'); print(f'Runtime LLM mode: {llm_config.mode}'); print(f'Runtime LLM model: {llm_config.model if llm_config.enabled else "off"}'); print(f'Runtime LLM base URL: {llm_config.base_url if llm_config.enabled else "off"}'); print(f'Retry empty LLM response: {llm_config.retry_empty_response}'); print(f'Pages loaded: {len(pages)}'); print(f'Gated drafts loaded: {len(gated)}'); server.serve_forever()

def _add_llm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--llm-mode', choices=['off','ollama_openai','openai_compatible'], default='off'); parser.add_argument('--llm-base-url', default='http://127.0.0.1:11434/v1'); parser.add_argument('--llm-model', default='gemma4:26b'); parser.add_argument('--llm-api-key', default='ollama'); parser.add_argument('--request-timeout', type=int, default=240); parser.add_argument('--llm-temperature', type=float, default=0.0); parser.add_argument('--llm-max-tokens', type=int, default=900); parser.add_argument('--disable-empty-response-retry', action='store_true')

def _llm_config_from_args(args: argparse.Namespace) -> LLMConfig:
    return LLMConfig(mode=args.llm_mode, base_url=args.llm_base_url, model=args.llm_model, api_key=args.llm_api_key, request_timeout=args.request_timeout, temperature=args.llm_temperature, max_tokens=args.llm_max_tokens, retry_empty_response=not args.disable_empty_response_retry)

def main_build(argv: Optional[Sequence[str]]=None) -> int:
    p = argparse.ArgumentParser(description='Build TRACE-Net engineering WebUI answer server manifest v1.2.'); p.add_argument('--output-dir', required=True); p.add_argument('--final-gate', default=str(DEFAULT_FINAL_GATE)); p.add_argument('--runner-report', default=str(DEFAULT_RUNNER)); p.add_argument('--page-context-v2', default=str(DEFAULT_PAGE_CONTEXT)); p.add_argument('--fishnet-ocr-grid', default=str(DEFAULT_FISHNET)); p.add_argument('--route-handoff', default=str(DEFAULT_ROUTE_HANDOFF)); p.add_argument('--sample-question', default='pick a random page to summarize'); p.add_argument('--sample-call-llm', action='store_true'); _add_llm_args(p); p.add_argument('--quality', action='store_true'); args = p.parse_args(argv)
    payload = build_engineering_webui_answer_manifest(output_dir=Path(args.output_dir), final_gate_path=Path(args.final_gate), runner_path=Path(args.runner_report), page_context_path=Path(args.page_context_v2), fishnet_path=Path(args.fishnet_ocr_grid), route_handoff_path=Path(args.route_handoff), sample_question=args.sample_question, llm_config=_llm_config_from_args(args), sample_call_llm=args.sample_call_llm)
    print('Status:', payload['status']); print('Quality status:', payload['quality_status']); print('Summary:', json.dumps(payload['summary'], sort_keys=True)); return 0 if payload['quality_status'] == 'PASS' else 1

def main_check(argv: Optional[Sequence[str]]=None) -> int:
    p = argparse.ArgumentParser(description='Check TRACE-Net engineering WebUI answer server quality v1.2.'); p.add_argument('--report-path', required=True); p.add_argument('--write-json', action='store_true'); p.add_argument('--min-page-records', type=int, default=1); p.add_argument('--min-gated-drafts', type=int, default=0); p.add_argument('--require-ready-for-webui', action='store_true'); p.add_argument('--require-llm-mode'); p.add_argument('--require-llm-model'); p.add_argument('--require-retry-empty-response', action='store_true'); p.add_argument('--max-unsafe', type=int, default=0); p.add_argument('--require-no-answer-permission', action='store_true'); p.add_argument('--require-no-retrieval-execution', action='store_true'); p.add_argument('--require-no-source-truth-mutation', action='store_true'); args = p.parse_args(argv)
    result = check_engineering_webui_answer_server_quality(report_path=Path(args.report_path), min_page_records=args.min_page_records, min_gated_drafts=args.min_gated_drafts, require_ready_for_webui=args.require_ready_for_webui, require_llm_mode=args.require_llm_mode, require_llm_model=args.require_llm_model, require_retry_empty_response=args.require_retry_empty_response, max_unsafe=args.max_unsafe, require_no_answer_permission=args.require_no_answer_permission, require_no_retrieval_execution=args.require_no_retrieval_execution, require_no_source_truth_mutation=args.require_no_source_truth_mutation)
    print('Quality status:', result['quality_status']); print('Summary:', json.dumps(result['summary'], sort_keys=True));
    if result['failures']: print('Failures:', json.dumps(result['failures'], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name('trace_net_engineering_webui_answer_server_v1_quality_check.json'); _write_json(out, result); print('Wrote:', out)
    return 0 if result['quality_status'] == 'PASS' else 1

def main_run(argv: Optional[Sequence[str]]=None) -> int:
    p = argparse.ArgumentParser(description='Run TRACE-Net engineering WebUI answer server v1.2.'); p.add_argument('--host', default='127.0.0.1'); p.add_argument('--port', type=int, default=8044); p.add_argument('--final-gate', default=str(DEFAULT_FINAL_GATE)); p.add_argument('--runner-report', default=str(DEFAULT_RUNNER)); p.add_argument('--page-context-v2', default=str(DEFAULT_PAGE_CONTEXT)); p.add_argument('--fishnet-ocr-grid', default=str(DEFAULT_FISHNET)); p.add_argument('--route-handoff', default=str(DEFAULT_ROUTE_HANDOFF)); _add_llm_args(p); args = p.parse_args(argv)
    run_server(host=args.host, port=args.port, final_gate_path=Path(args.final_gate), runner_path=Path(args.runner_report), page_context_path=Path(args.page_context_v2), fishnet_path=Path(args.fishnet_ocr_grid), route_handoff_path=Path(args.route_handoff), llm_config=_llm_config_from_args(args)); return 0

if __name__ == '__main__': raise SystemExit(main_build())
