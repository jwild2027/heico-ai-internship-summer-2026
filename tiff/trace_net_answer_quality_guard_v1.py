"""Deterministic semantic quality checks for TRACE-Net user answers."""
from __future__ import annotations
import re
from typing import Any, Mapping, Sequence
PREFIX_RE=re.compile(r"\b(?:starts?|begins?)\s+(?:with\s+)?([A-Z0-9][A-Z0-9.-]{1,15})",re.I)
PARTISH_RE=re.compile(r"\b[A-Z0-9][A-Z0-9.-]{3,24}\b",re.I)
NOISE=(re.compile(r"^\d+\.\d+[A-Z]?$",re.I),re.compile(r"^\d{5,}[A-F]-\d{2}$",re.I),re.compile(r"^[N]\d{2,3}-\d{4,6}(?:-\d{3})?$",re.I),re.compile(r"^\d+E[+-]?\d+$",re.I))

def normalize_token(v:str)->str:return re.sub(r"[^A-Z0-9]","",str(v or '').upper())
def requested_prefix(q:str)->str:
 m=PREFIX_RE.search(str(q or ''));return normalize_token(m.group(1)) if m else ''
def is_noise_candidate(v:str)->bool:
 raw=str(v or '').strip(' `*,:;()[]{}');norm=normalize_token(raw)
 return (not raw or any(p.fullmatch(raw) for p in NOISE) or len(norm)<4 or sum(c.isdigit() for c in norm)<2 or raw.upper() in {'25-IPL','PER','STOCK','UNKNOWN'})
def extract_candidate_tokens(a:str)->list[str]:
 out=[]
 for x in PARTISH_RE.findall(str(a or '')):
  x=x.strip('.,:;')
  if re.fullmatch(r"\d{2}-\d{2}-\d{2}",x):continue
  if any(c.isdigit() for c in x):out.append(x)
 return out
def duplicate_followup_count(answer:str,followups:Sequence[str])->int:
 low=re.sub(r"\s+"," ",str(answer or '').lower());n=0
 for q in followups:
  words=[w for w in re.findall(r"[a-z0-9]+",str(q).lower()) if len(w)>=5][:5]
  if words and sum(low.count(w)>=2 for w in words)>=max(2,len(words)//2):n+=1
 return n
def evaluate_answer_quality(*,query:str,answer:str,trace:Mapping[str,Any])->list[str]:
 failures=[];prefix=requested_prefix(query);cands=extract_candidate_tokens(answer)
 if prefix and str(trace.get('route') or '')=='guided_discovery':
  actual=[normalize_token(c) for c in cands if not is_noise_candidate(c)]
  bad=[c for c in actual if c and not c.startswith(prefix)]
  if bad and 'no source-traceable' not in answer.lower() and 'no exact' not in answer.lower():failures.append('strict_prefix_candidate_mismatch:'+','.join(bad[:5]))
 noisy=[c for c in cands if is_noise_candidate(c)]
 if noisy:failures.append('user_visible_noise_candidates:'+','.join(noisy[:5]))
 dup=duplicate_followup_count(answer,list(trace.get('follow_up_questions') or []))
 if dup:failures.append(f'duplicate_followup_topics:{dup}')
 return failures
