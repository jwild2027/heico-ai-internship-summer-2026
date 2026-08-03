from __future__ import annotations

import argparse, json, re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

MODULE = "trace_net_v2_sample_runner_simple_v1"
VERSION = "1.0.0"
DEFAULT_CONTEXT_FILE = "local_data/organization/context/page_contexts.json"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/v2_sample_runner_simple_v1/sample_5"
REPORT = "trace_net_v2_sample_runner_simple_v1.json"
RECORDS = "trace_net_v2_sample_runner_simple_v1_records.jsonl"
PROMPTS = "trace_net_v2_sample_runner_simple_v1_prompts.jsonl"
MD = "trace_net_v2_sample_runner_simple_v1.md"
QUALITY = "trace_net_v2_sample_runner_simple_v1_quality.json"
PART_RE = re.compile(r"\b(?:\d{3}-\d{5}-\d{3}|[A-Z]{1,4}\d[\w.-]{2,}|\d{2,}-[A-Z0-9][A-Z0-9-]{2,})\b")


def norm(x: Any) -> str:
    return re.sub(r"\s+", " ", "" if x is None else str(x)).strip()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def as_list(x: Any) -> List[Any]:
    if x is None or x == "":
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, tuple):
        return list(x)
    if isinstance(x, set):
        return list(x)
    return [x]


def load_contexts(path: Path) -> Dict[str, Dict[str, Any]]:
    try:
        from tiff.trace_net_page_context_v2 import load_v1_context_file
        data = load_v1_context_file(path)
        if isinstance(data, Mapping):
            return {str(k): dict(v) for k, v in data.items() if isinstance(v, Mapping)}
    except Exception:
        pass
    raw = read_json(path, {})
    if isinstance(raw, Mapping):
        for key in ("records", "contexts", "page_contexts", "pages"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw, Mapping):
        for k, v in raw.items():
            if isinstance(v, Mapping):
                rec = dict(v); rec.setdefault("page_id", k); out[str(rec.get("page_id") or k)] = rec
    elif isinstance(raw, list):
        for i, v in enumerate(raw):
            if isinstance(v, Mapping):
                rec = dict(v); pid = str(rec.get("page_id") or rec.get("id") or f"page_{i+1:06d}"); rec.setdefault("page_id", pid); out[pid] = rec
    return out


def page_num(pid: str) -> int | None:
    m = re.search(r"p(\d{6})$", pid or "") or re.search(r"(\d{1,6})$", pid or "")
    return int(m.group(1)) if m else None


def wanted_id(n: int) -> str:
    return f"t_p_120_1176_p{int(n):06d}"


def pick_pages(contexts: Mapping[str, Mapping[str, Any]], max_pages: int, page_numbers: Sequence[int], page_ids: Sequence[str]) -> List[tuple[str, Mapping[str, Any]]]:
    wanted = {norm(x) for x in page_ids if norm(x)} | {wanted_id(n) for n in page_numbers}
    picked: List[tuple[str, Mapping[str, Any]]] = []
    if wanted:
        for k, rec in contexts.items():
            pid = norm(rec.get("page_id")) or str(k)
            aliases = {str(k), pid}
            n = page_num(pid) or page_num(str(k))
            if n is not None:
                aliases |= {str(n), wanted_id(n)}
            if aliases & wanted:
                picked.append((pid, rec))
                if len(picked) >= max_pages: break
        return picked
    for k, rec in contexts.items():
        pid = norm(rec.get("page_id")) or str(k)
        blob = " ".join(norm(rec.get(x)) for x in ("summary", "short_summary", "retrieval_summary", "ocr_text", "text", "ocr_sample"))
        if blob:
            picked.append((pid, rec))
            if len(picked) >= max_pages: break
    if len(picked) < max_pages:
        for k, rec in contexts.items():
            pid = norm(rec.get("page_id")) or str(k)
            if all(pid != p[0] for p in picked):
                picked.append((pid, rec))
                if len(picked) >= max_pages: break
    return picked[:max_pages]


def make_page(pid: str, rec: Mapping[str, Any], max_ocr_chars: int) -> Dict[str, Any]:
    ocr = norm(rec.get("ocr_text") or rec.get("text") or rec.get("ocr_sample") or rec.get("source_text") or rec.get("raw_ocr"))[:max_ocr_chars]
    return {
        "page_id": pid,
        "document_id": rec.get("document_id") or "unknown_document",
        "v1": dict(rec),
        "ocr_text": ocr,
        "ocr_classification": rec.get("ocr_classification") or rec.get("classification"),
        "source_url": rec.get("source_url") or rec.get("url") or "",
        "tiff_path": rec.get("tiff_path") or rec.get("source_file") or rec.get("image_path") or "",
        "ocr_path": rec.get("ocr_path") or "",
        "max_ocr_chars": max_ocr_chars,
    }


def safe_card(card: Mapping[str, Any], page: Mapping[str, Any], prompt_version: str) -> Dict[str, Any]:
    out = dict(card)
    v1 = page.get("v1") if isinstance(page.get("v1"), Mapping) else {}
    ocr = norm(page.get("ocr_text"))
    summary = norm(out.get("short_summary") or out.get("summary") or v1.get("summary") or v1.get("short_summary")) or ("Page has OCR text available for V2 retrieval guidance." if ocr else "Page has V2 retrieval guidance.")
    out["page_id"] = norm(out.get("page_id") or page.get("page_id") or v1.get("page_id")) or "unknown_page"
    out["role"] = norm(out.get("role") or v1.get("role") or v1.get("page_role") or v1.get("type")) or "unknown"
    out["subrole"] = norm(out.get("subrole")) or "general"
    out["confidence"] = norm(out.get("confidence") or v1.get("confidence")) or ("medium" if ocr else "low")
    out["short_summary"] = summary
    out["retrieval_summary"] = norm(out.get("retrieval_summary")) or f"Use this page as V2 retrieval/query guidance. {summary}"
    for f in ("answerable_questions", "retrieval_cues", "important_entities", "component_families", "not_good_for"):
        out[f] = [x for x in as_list(out.get(f)) if norm(x)]
    if not out["answerable_questions"]: out["answerable_questions"] = ["Which source page may be relevant to this query?"]
    if not out["retrieval_cues"]: out["retrieval_cues"] = ["page context"]
    if not out["not_good_for"]: out["not_good_for"] = ["proving source truth without checking the cited source page"]
    sg = dict(out.get("source_grounding") if isinstance(out.get("source_grounding"), Mapping) else {})
    sg["has_ocr"] = bool(sg.get("has_ocr")) or bool(ocr)
    sg["source_url_present"] = bool(sg.get("source_url_present")) or bool(norm(page.get("source_url")))
    sg["supporting_ocr_phrases"] = as_list(sg.get("supporting_ocr_phrases"))[:8]
    out["source_grounding"] = sg
    auth = dict(out.get("authority") if isinstance(out.get("authority"), Mapping) else {})
    auth["trust_scope"] = norm(auth.get("trust_scope")) or "page_context_summary"
    auth["can_answer_directly"] = False
    auth["canonical_source_truth"] = False
    auth["requires_source_check"] = True
    out["authority"] = auth
    out["prompt_version"] = norm(out.get("prompt_version")) or prompt_version
    out["guidance_only"] = True
    out["can_prove_claims"] = False
    out["source_truth_mutation_allowed"] = False
    blob = " ".join(map(norm, [summary, out["retrieval_summary"], ocr]))
    parts = []
    for m in PART_RE.finditer(blob):
        val = m.group(0).upper()
        if val not in parts: parts.append(val)
    out["v3_preview"] = {
        "page_type": out["role"],
        "route_signals": out["retrieval_cues"][:10],
        "part_numbers": parts[:25],
        "candidate_evidence_usefulness_for_rag": "guidance_only_candidate; requires proof_context/source_trace before factual use",
        "engram_guidance": "behavior/proof-boundary guidance only; not factual proof",
        "leiden_community_guidance": "not joined in this V2 sample runner",
        "dublin_core": {"type": "PageContextGuidance", "format": "application/json", "identifier": out["page_id"], "source": norm(page.get("source_url") or page.get("tiff_path")) or "unknown"},
    }
    return out


def validate_card(card: Mapping[str, Any]) -> Dict[str, Any]:
    required = ["page_id", "role", "subrole", "confidence", "short_summary", "retrieval_summary", "answerable_questions", "retrieval_cues", "source_grounding", "authority", "prompt_version"]
    missing = [f for f in required if f not in card]
    empty = [f for f in ("page_id", "role", "subrole", "confidence", "short_summary", "retrieval_summary") if not norm(card.get(f))]
    auth = card.get("authority") if isinstance(card.get("authority"), Mapping) else {}
    unsafe = []
    if bool(auth.get("can_answer_directly")) or bool(card.get("can_answer_directly")): unsafe.append("answer_permission_true")
    if bool(auth.get("canonical_source_truth")) or bool(card.get("canonical_source_truth")): unsafe.append("canonical_source_truth_true")
    if bool(card.get("source_truth_mutation_allowed")): unsafe.append("source_truth_mutation_allowed_true")
    failures = []
    if missing: failures.append("missing_required_fields")
    if empty: failures.append("empty_required_fields")
    failures += unsafe
    return {"quality_status": "PASS" if not failures else "FAIL", "failure_reasons": failures, "missing_fields": missing, "empty_required_fields": empty}


def build_one(page: Mapping[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    from tiff.trace_net_page_context_v2 import PROMPT_VERSION, build_prompt, heuristic_context_v2, sanitize_context_v2
    h = heuristic_context_v2(dict(page))
    prompt = build_prompt(dict(page), h)
    card = safe_card(sanitize_context_v2(h, h), page, PROMPT_VERSION)
    return card, {"page_id": card["page_id"], "prompt_version": card["prompt_version"], "prompt_length": len(prompt), "prompt_preview": prompt[:3000]}


def build_sample(context_file: str | Path, output_dir: str | Path, max_pages: int = 5, page_numbers: Sequence[int] = (), page_ids: Sequence[str] = (), max_ocr_chars: int = 6000) -> Dict[str, Any]:
    ctx_path, out_dir = Path(context_file), Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    contexts = load_contexts(ctx_path)
    selected = pick_pages(contexts, max_pages=max_pages, page_numbers=page_numbers, page_ids=page_ids)
    records, prompts, validations, errors = [], [], [], []
    for pid, rec in selected:
        try:
            card, prompt_rec = build_one(make_page(pid, rec, max_ocr_chars))
            records.append(card); prompts.append(prompt_rec); validations.append({"page_id": card["page_id"], "validation": validate_card(card)})
        except Exception as e:
            errors.append({"page_id": pid, "error_type": type(e).__name__, "error": str(e)[:500]})
    fail_count = sum(1 for v in validations if v["validation"]["quality_status"] != "PASS")
    failures = []
    if len(records) < max_pages: failures.append(f"sample_record_count_below_requested:{len(records)}<{max_pages}")
    if fail_count: failures.append(f"validation_failure_count_nonzero:{fail_count}")
    if errors: failures.append(f"error_count_nonzero:{len(errors)}")
    summary = {"context_file": str(ctx_path), "context_file_exists": ctx_path.exists(), "context_record_count": len(contexts), "requested_max_pages": max_pages, "sample_record_count": len(records), "prompt_record_count": len(prompts), "validation_failure_count": fail_count, "error_count": len(errors), "answer_permission_count": 0, "source_truth_mutation_allowed_count": 0, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "opensearch_write_attempt_count": 0, "v3_preview_attached": True}
    report = {"module": MODULE, "version": VERSION, "status": "TRACE_NET_V2_SAMPLE_BUILT", "quality_status": "PASS" if not failures else "FAIL", "failure_reasons": failures, "summary": summary, "records": records, "prompt_records": prompts, "validations": validations, "errors": errors, "records_path": str(out_dir / RECORDS), "prompts_path": str(out_dir / PROMPTS), "safety_contract": {"answer_permission": False, "source_truth_mutation_allowed": False, "v2_summary_is_proof": False, "v2_summary_role": "retrieval_guidance_only"}}
    write_jsonl(out_dir / RECORDS, records); write_jsonl(out_dir / PROMPTS, prompts); write_json(out_dir / REPORT, report); (out_dir / MD).write_text(render_md(report), encoding="utf-8")
    return report


def render_md(report: Mapping[str, Any]) -> str:
    lines = ["# TRACE-Net V2 sample", "", f"Quality status: **{report.get('quality_status')}**", "", "## Summary"]
    for k, v in (report.get("summary") or {}).items(): lines.append(f"- `{k}`: `{v}`")
    lines += ["", "## Records"]
    for r in report.get("records", [])[:10]:
        lines += ["", f"### {r.get('page_id')}", f"- role/subrole: `{r.get('role')}` / `{r.get('subrole')}`", f"- summary: {r.get('short_summary')}", f"- retrieval: {r.get('retrieval_summary')}", f"- v3_preview: `{bool(r.get('v3_preview'))}`"]
    lines += ["", "V2 summaries are guidance only, not proof."]
    return "\n".join(lines) + "\n"


def check_report(report_path: str | Path, output: str | Path = "", min_records: int = 5) -> Dict[str, Any]:
    data = read_json(Path(report_path), {}) or {}; s = data.get("summary") or {}; failures = []
    if data.get("quality_status") != "PASS": failures.append("source_report_quality_status_not_pass")
    if int(s.get("sample_record_count") or 0) < min_records: failures.append("sample_record_count_below_min")
    if int(s.get("answer_permission_count") or 0): failures.append("answer_permission_count_nonzero")
    if int(s.get("source_truth_mutation_allowed_count") or 0): failures.append("source_truth_mutation_allowed_count_nonzero")
    q = {"module": MODULE, "status": "TRACE_NET_V2_SAMPLE_QUALITY_CHECKED", "quality_status": "PASS" if not failures else "FAIL", "failure_reasons": failures, "summary": s}
    if output: write_json(Path(output), q)
    return q


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build a 5-page sample from existing TRACE-Net V2 guide")
    p.add_argument("--context-file", default=DEFAULT_CONTEXT_FILE); p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR); p.add_argument("--max-pages", type=int, default=5); p.add_argument("--page-number", type=int, action="append", default=[]); p.add_argument("--page-id", action="append", default=[]); p.add_argument("--max-ocr-chars", type=int, default=6000)
    a = p.parse_args(argv)
    r = build_sample(a.context_file, a.output_dir, max_pages=a.max_pages, page_numbers=a.page_number, page_ids=a.page_id, max_ocr_chars=a.max_ocr_chars)
    print(f"Wrote: {Path(a.output_dir)/REPORT}"); print(f"Wrote: {Path(a.output_dir)/RECORDS}"); print(f"Wrote: {Path(a.output_dir)/PROMPTS}"); print(f"quality_status: {r['quality_status']}"); print(f"failure_reasons: {r['failure_reasons']}"); print("summary:", json.dumps(r["summary"], sort_keys=True))
    return 0 if r["quality_status"] == "PASS" else 2


def check_main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Check V2 sample quality")
    p.add_argument("--report", required=True); p.add_argument("--output", default=""); p.add_argument("--min-records", type=int, default=5)
    a = p.parse_args(argv); q = check_report(a.report, a.output, a.min_records)
    print(f"Wrote: {a.output or '<not written>'}"); print(f"quality_status: {q['quality_status']}"); print(f"failure_reasons: {q['failure_reasons']}")
    return 0 if q["quality_status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
