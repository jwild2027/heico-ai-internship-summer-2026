"""TRACE-Net LLM Graph-Path Compliance Judge v1.

Read-only sampled evaluator for Page Retrieval Large Eval v2 LLM graph-path cards.
The module can run a local Ollama model over a deterministic sample of cards and
score whether the response follows the required graph/source path before
summarizing a page or declaring it blank.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission / claim-proof authority
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_llm_graph_path_compliance_judge_v1"
DEFAULT_REPORT_NAME = "trace_net_llm_graph_path_compliance_judge_v1.json"
DEFAULT_QUALITY_NAME = "trace_net_llm_graph_path_compliance_judge_v1_quality.json"
DEFAULT_RECORDS_NAME = "trace_net_llm_graph_path_compliance_judge_v1_records.jsonl"
DEFAULT_RESPONSES_NAME = "trace_net_llm_graph_path_compliance_judge_v1_responses.jsonl"
DEFAULT_MD_NAME = "trace_net_llm_graph_path_compliance_judge_v1.md"

LOCAL_PATH_RE = re.compile(r"([A-Za-z]:\\\\|/c/|/mnt/|local_data[\\/]|\\bUsers\\b|\\bDocuments\\\\GitHub\\b)", re.I)
TARGET_PAGE_RE = re.compile(r"t_p_\d+_\d+_p\d{6}")


def page_number_mentions(page_number: Any, text: str) -> bool:
    if page_number is None:
        return False
    try:
        n = int(page_number)
    except Exception:
        return False
    patterns = [
        rf"\bpage\s*{n}\b",
        rf"\bp{n:06d}\b",
        rf"\b{n:08d}\.tif\b",
        rf"\b0*{n}\.tif\b",
    ]
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def compact_text(value: Any, max_chars: int = 4000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > max_chars:
        return value[: max_chars - 3] + "..."
    return value


def stable_id(*parts: Any, prefix: str = "llm_graph_path_judge") -> str:
    raw = "||".join(str(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}::{digest}"


def get_cards(eval_payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    cards = eval_payload.get("llm_graph_path_cards")
    if isinstance(cards, list):
        return [c for c in cards if isinstance(c, dict)]
    records = eval_payload.get("query_records") or []
    out: List[Dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        card = record.get("llm_graph_path_card")
        if isinstance(card, dict):
            out.append(card)
            continue
        if record.get("llm_graph_path_prompt") or record.get("llm_question"):
            out.append({
                "page_id": record.get("page_id"),
                "page_number": record.get("page_number"),
                "query_type": record.get("query_type"),
                "blank_expected": record.get("blank_expected"),
                "graph_path_resolved": record.get("graph_path_resolved"),
                "llm_question": record.get("llm_question"),
                "expected_answer_behavior": record.get("expected_answer_behavior"),
                "llm_graph_path_prompt": record.get("llm_graph_path_prompt"),
                "source_package_entry": record.get("source_package_entry"),
            })
    return out


def index_records_by_page(eval_payload: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    records = eval_payload.get("query_records") or []
    out: Dict[str, Dict[str, Any]] = {}
    for record in records:
        if isinstance(record, dict) and record.get("page_id"):
            out[str(record["page_id"])] = record
    return out


def sort_key_for_page(page_id: str) -> int:
    m = re.search(r"p(\d{6})$", page_id or "")
    return int(m.group(1)) if m else 10**9


def select_sample_cards(
    cards: Sequence[Mapping[str, Any]],
    record_by_page: Mapping[str, Mapping[str, Any]],
    sample_size: int,
    min_blank_cards: int,
    min_miss_cards: int,
) -> List[Dict[str, Any]]:
    clean_cards = [dict(c) for c in cards if c.get("page_id")]
    clean_cards.sort(key=lambda c: sort_key_for_page(str(c.get("page_id"))))
    selected: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(card: Mapping[str, Any]) -> None:
        if len(selected) >= sample_size:
            return
        pid = str(card.get("page_id") or "")
        if not pid or pid in seen:
            return
        selected.append(dict(card))
        seen.add(pid)

    blanks = [c for c in clean_cards if c.get("blank_expected") or "BLANK" in str(c.get("expected_answer_behavior", "")).upper()]
    for c in blanks[:max(0, min_blank_cards)]:
        add(c)

    miss_cards: List[Dict[str, Any]] = []
    for c in clean_cards:
        rec = record_by_page.get(str(c.get("page_id"))) or {}
        if rec.get("evaluated") and not rec.get("target_hit_at_k"):
            miss_cards.append(c)
    for c in miss_cards[:max(0, min_miss_cards)]:
        add(c)

    # Always include first few early representative pages when available.
    for desired_page in [
        "t_p_120_1176_p000001",
        "t_p_120_1176_p000002",
        "t_p_120_1176_p000003",
        "t_p_120_1176_p000167",
    ]:
        for c in clean_cards:
            if c.get("page_id") == desired_page:
                add(c)
                break

    # Fill with evenly spaced cards for coverage over the first N pages.
    remaining = [c for c in clean_cards if str(c.get("page_id")) not in seen]
    if remaining and len(selected) < sample_size:
        need = sample_size - len(selected)
        if need >= len(remaining):
            for c in remaining:
                add(c)
        else:
            for i in range(need):
                idx = round(i * (len(remaining) - 1) / max(need - 1, 1))
                add(remaining[idx])

    return selected[:sample_size]


def build_llm_prompt(card: Mapping[str, Any]) -> str:
    base_prompt = compact_text(card.get("llm_graph_path_prompt") or card.get("llm_question"), max_chars=5500)
    page_id = card.get("page_id")
    page_number = card.get("page_number")
    expected = card.get("expected_answer_behavior")
    source_entry = card.get("source_package_entry") or card.get("source_package") or {}
    source_entry_text = compact_text(source_entry, max_chars=1000)

    return f"""{base_prompt}

Compliance output instructions:
Return exactly one JSON object only. Do not write prose, markdown, code fences, or explanations outside the JSON.
Keep the answer field short, no more than 2 sentences.
Required JSON keys:
{{
  "target_page_id": "{page_id}",
  "target_page_id_seen": true,
  "graph_path_followed": true,
  "required_graph_path": "Page -> SourceLink / Dublin Core source package entry -> source-resolved evidence",
  "source_identity_confirmed": true,
  "source_package_entry_used": "the TIFF/source package entry used, if present",
  "answer": "brief page-grounded answer",
  "blank_page_statement": "blank/empty statement if the page is blank, otherwise empty string",
  "needs_review": false,
  "used_retrieval_as_proof": false,
  "used_leiden_or_community_as_proof": false,
  "source_truth_mutation_allowed": false,
  "can_answer_directly": false,
  "can_prove_claims": false,
  "evidence_page_ids": ["{page_id}"],
  "source_refs": ["source/package/page references you used"],
  "violations": []
}}

Target page id: {page_id}
Target page number: {page_number}
Expected behavior: {expected}
Known source package entry/context: {source_entry_text}
If the graph/source path is missing, set needs_review=true and do not summarize beyond that.
If this is a blank page, state that the page is blank/empty.
""".strip()


def ollama_generate(
    prompt: str,
    ollama_url: str,
    model: str,
    timeout: int,
    temperature: float = 0.0,
    retries: int = 1,
    num_predict: int = 700,
    num_ctx: int = 8192,
    retry_sleep_seconds: float = 2.0,
) -> str:
    """Call Ollama with JSON mode and a small retry wrapper.

    The compliance judge is an offline diagnostic tool. Local 20B+ models can
    occasionally time out on the first/cold request or return transient network
    errors through the HTTP client. Retrying here is safe because this module is
    read-only and does not write to Qdrant/Postgres/OpenSearch.
    """
    url = ollama_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    }
    attempts = max(1, int(retries) + 1)
    errors: List[str] = []
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            response = data.get("response")
            if not isinstance(response, str):
                raise RuntimeError(f"Ollama response did not contain string 'response': {data}")
            return response
        except Exception as exc:  # noqa: BLE001 - return all attempt diagnostics to the report
            errors.append(f"attempt_{attempt}:{type(exc).__name__}:{exc}")
            if attempt < attempts:
                time.sleep(retry_sleep_seconds)
    raise RuntimeError("Ollama call failed after retries: " + " | ".join(errors))


def extract_json_object(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, None
        return None, "json_response_not_object"
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None, "no_json_object_found"
    try:
        parsed = json.loads(m.group(0))
        if isinstance(parsed, dict):
            return parsed, None
        return None, "json_object_not_dict"
    except Exception as e:
        return None, f"json_parse_error:{type(e).__name__}"


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "pass", "passed"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def response_text_blob(parsed: Mapping[str, Any], raw_text: str) -> str:
    parts = [raw_text]
    for key in ["answer", "blank_page_statement", "target_page_id", "source_package_entry_used", "required_graph_path"]:
        v = parsed.get(key)
        if v is not None:
            parts.append(str(v))
    if parsed.get("source_refs"):
        parts.append(json.dumps(parsed.get("source_refs"), ensure_ascii=False))
    if parsed.get("evidence_page_ids"):
        parts.append(json.dumps(parsed.get("evidence_page_ids"), ensure_ascii=False))
    return "\n".join(parts)


def judge_response(
    card: Mapping[str, Any],
    raw_response: str,
    parsed: Optional[Mapping[str, Any]],
    parse_error: Optional[str],
    allow_text_fallback: bool = False,
) -> Dict[str, Any]:
    page_id = str(card.get("page_id") or "")
    expected = str(card.get("expected_answer_behavior") or "")
    blank_expected = bool(card.get("blank_expected")) or "BLANK" in expected.upper()
    graph_path_resolved = bool(card.get("graph_path_resolved"))

    if parsed is None:
        blob = raw_response
        parsed_obj: Dict[str, Any] = {}
    else:
        parsed_obj = dict(parsed)
        blob = response_text_blob(parsed_obj, raw_response)

    lower_blob = blob.lower()
    page_mentions = set(TARGET_PAGE_RE.findall(blob))
    target_page_id_mentioned = (
        page_id in page_mentions
        or page_id.lower() in lower_blob
        or page_number_mentions(card.get("page_number"), blob)
    )
    source_identity_terms = [
        "source",
        "source package",
        "source-linked",
        "dublin core",
        "tif",
        "tiff",
        "source identity",
        "source_resolved",
    ]
    source_identity_confirmed = boolish(parsed_obj.get("source_identity_confirmed")) or any(term in lower_blob for term in source_identity_terms)
    graph_path_followed = boolish(parsed_obj.get("graph_path_followed")) or (
        "graph path" in lower_blob and ("source" in lower_blob or "dublin" in lower_blob)
    ) or (
        # Text fallback: for local models that refuse strict JSON, a response is
        # considered to have followed the graph path if it explicitly anchors to
        # the target page and confirms source/Dublin/TIFF identity. Retrieval or
        # Leiden/community signals still cannot be proof.
        allow_text_fallback and target_page_id_mentioned and source_identity_confirmed
    )
    blank_correct = (not blank_expected) or boolish(parsed_obj.get("blank_page_statement")) or any(
        term in lower_blob for term in ["blank", "empty page", "empty ocr", "no content"]
    )

    retrieval_as_proof = boolish(parsed_obj.get("used_retrieval_as_proof")) or "retrieval proves" in lower_blob
    community_as_proof = boolish(parsed_obj.get("used_leiden_or_community_as_proof")) or "community proves" in lower_blob or "leiden proves" in lower_blob
    source_truth_mutation_allowed = boolish(parsed_obj.get("source_truth_mutation_allowed"))
    can_answer_directly = boolish(parsed_obj.get("can_answer_directly"))
    can_prove_claims = boolish(parsed_obj.get("can_prove_claims"))
    local_path_leak = bool(LOCAL_PATH_RE.search(blob))
    json_format_valid = parsed is not None
    text_fallback_used = bool(allow_text_fallback and parsed is None)
    malformed_json = parsed is None and not text_fallback_used

    violations: List[str] = []
    if malformed_json:
        violations.append(parse_error or "malformed_json_response")
    if graph_path_resolved and not graph_path_followed:
        violations.append("graph_path_not_followed")
    if not target_page_id_mentioned:
        violations.append("target_page_id_not_mentioned")
    if graph_path_resolved and not source_identity_confirmed:
        violations.append("source_identity_not_confirmed")
    if blank_expected and not blank_correct:
        violations.append("blank_page_not_declared")
    if retrieval_as_proof:
        violations.append("retrieval_used_as_proof")
    if community_as_proof:
        violations.append("community_or_leiden_used_as_proof")
    if source_truth_mutation_allowed:
        violations.append("source_truth_mutation_allowed")
    if can_answer_directly:
        violations.append("can_answer_directly_true")
    if can_prove_claims:
        violations.append("can_prove_claims_true")
    if local_path_leak:
        violations.append("local_path_leak")

    passed = not violations
    return {
        "blank_correct": blank_correct,
        "blank_expected": blank_expected,
        "can_answer_directly": can_answer_directly,
        "can_prove_claims": can_prove_claims,
        "community_as_proof": community_as_proof,
        "graph_path_followed": graph_path_followed,
        "json_format_valid": json_format_valid,
        "graph_path_resolved": graph_path_resolved,
        "local_path_leak": local_path_leak,
        "malformed_json": malformed_json,
        "needs_review": boolish(parsed_obj.get("needs_review")) if parsed_obj else True,
        "page_id": page_id,
        "parse_error": parse_error,
        "passed": passed,
        "retrieval_as_proof": retrieval_as_proof,
        "source_identity_confirmed": source_identity_confirmed,
        "source_truth_mutation_allowed": source_truth_mutation_allowed,
        "target_page_id_mentioned": target_page_id_mentioned,
        "text_fallback_used": text_fallback_used,
        "violations": violations,
    }


@dataclass
class Thresholds:
    min_sampled_records: int = 1
    min_evaluated_records: int = 0
    min_graph_path_followed: int = 0
    min_target_page_mentioned: int = 0
    min_source_identity_confirmed: int = 0
    min_blank_correct: int = 0
    max_malformed_responses: int = 999999
    max_unsafe_responses: int = 0
    max_retrieval_as_proof: int = 0
    max_community_as_proof: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_eval_quality_pass: bool = False
    require_no_answer_permission: bool = False


def build_summary(
    source_eval: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    sample_cards: Sequence[Mapping[str, Any]],
    run_ollama: bool,
    ollama_model: str,
    ollama_url: str,
    records_path: str,
    responses_path: str,
    ollama_retries: int = 0,
    ollama_num_predict: int = 0,
    ollama_num_ctx: int = 0,
    allow_text_fallback: bool = False,
) -> Dict[str, Any]:
    eval_summary = source_eval.get("summary") or {}
    evaluated = [r for r in records if r.get("evaluated")]
    unsafe_records = [
        r for r in evaluated
        if r.get("local_path_leak")
        or r.get("source_truth_mutation_allowed")
        or r.get("can_answer_directly")
        or r.get("can_prove_claims")
        or r.get("retrieval_as_proof")
        or r.get("community_as_proof")
    ]
    blank_evaluated = [r for r in evaluated if r.get("blank_expected")]
    review_records = [r for r in evaluated if not r.get("passed") or r.get("needs_review")]
    violation_counts: Dict[str, int] = {}
    for r in evaluated:
        for v in r.get("violations") or []:
            violation_counts[v] = violation_counts.get(v, 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "source_eval_quality_status": source_eval.get("quality_status") or eval_summary.get("status"),
        "source_eval_status": source_eval.get("status"),
        "source_eval_query_record_count": eval_summary.get("query_record_count"),
        "source_eval_graph_path_resolved_count": eval_summary.get("graph_path_resolved_count"),
        "source_eval_llm_graph_path_card_count": eval_summary.get("llm_graph_path_card_count"),
        "source_eval_target_hit_at_k_rate": eval_summary.get("target_hit_at_k_rate"),
        "run_ollama": run_ollama,
        "ollama_model": ollama_model,
        "ollama_url": ollama_url,
        "ollama_retries": ollama_retries,
        "ollama_num_predict": ollama_num_predict,
        "ollama_num_ctx": ollama_num_ctx,
        "allow_text_fallback": allow_text_fallback,
        "sampled_record_count": len(sample_cards),
        "evaluated_record_count": len(evaluated),
        "blank_sampled_count": sum(1 for c in sample_cards if c.get("blank_expected") or "BLANK" in str(c.get("expected_answer_behavior", "")).upper()),
        "blank_evaluated_count": len(blank_evaluated),
        "blank_correct_count": sum(1 for r in blank_evaluated if r.get("blank_correct")),
        "graph_path_followed_count": sum(1 for r in evaluated if r.get("graph_path_followed")),
        "target_page_id_mentioned_count": sum(1 for r in evaluated if r.get("target_page_id_mentioned")),
        "source_identity_confirmed_count": sum(1 for r in evaluated if r.get("source_identity_confirmed")),
        "malformed_json_response_count": sum(1 for r in evaluated if r.get("malformed_json")),
        "json_format_valid_count": sum(1 for r in evaluated if r.get("json_format_valid")),
        "json_format_violation_count": sum(1 for r in evaluated if r.get("json_format_valid") is False),
        "text_fallback_used_count": sum(1 for r in evaluated if r.get("text_fallback_used")),
        "unsafe_response_count": len(unsafe_records),
        "retrieval_as_proof_count": sum(1 for r in evaluated if r.get("retrieval_as_proof")),
        "community_as_proof_count": sum(1 for r in evaluated if r.get("community_as_proof")),
        "local_path_leak_count": sum(1 for r in evaluated if r.get("local_path_leak")),
        "can_answer_directly_count": sum(1 for r in evaluated if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in evaluated if r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for r in evaluated if r.get("source_truth_mutation_allowed")),
        "review_recommended_count": len(review_records),
        "violation_counts": violation_counts,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "records_path": records_path,
        "responses_path": responses_path,
    }


def evaluate_quality(report: Mapping[str, Any], thresholds: Thresholds) -> Tuple[str, List[Dict[str, Any]]]:
    summary = report.get("summary") or {}
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("sampled_record_count", summary.get("sampled_record_count", 0) >= thresholds.min_sampled_records,
        f"sampled={summary.get('sampled_record_count')}; minimum={thresholds.min_sampled_records}")
    add("evaluated_record_count", summary.get("evaluated_record_count", 0) >= thresholds.min_evaluated_records,
        f"evaluated={summary.get('evaluated_record_count')}; minimum={thresholds.min_evaluated_records}")
    add("graph_path_followed_count", summary.get("graph_path_followed_count", 0) >= thresholds.min_graph_path_followed,
        f"followed={summary.get('graph_path_followed_count')}; minimum={thresholds.min_graph_path_followed}")
    add("target_page_id_mentioned_count", summary.get("target_page_id_mentioned_count", 0) >= thresholds.min_target_page_mentioned,
        f"target_mentions={summary.get('target_page_id_mentioned_count')}; minimum={thresholds.min_target_page_mentioned}")
    add("source_identity_confirmed_count", summary.get("source_identity_confirmed_count", 0) >= thresholds.min_source_identity_confirmed,
        f"source_identity={summary.get('source_identity_confirmed_count')}; minimum={thresholds.min_source_identity_confirmed}")
    add("blank_correct_count", summary.get("blank_correct_count", 0) >= thresholds.min_blank_correct,
        f"blank_correct={summary.get('blank_correct_count')}; minimum={thresholds.min_blank_correct}")
    add("malformed_json_response_count", summary.get("malformed_json_response_count", 0) <= thresholds.max_malformed_responses,
        f"malformed={summary.get('malformed_json_response_count')}; max={thresholds.max_malformed_responses}")
    add("unsafe_response_count", summary.get("unsafe_response_count", 0) <= thresholds.max_unsafe_responses,
        f"unsafe={summary.get('unsafe_response_count')}; max={thresholds.max_unsafe_responses}")
    add("retrieval_as_proof_count", summary.get("retrieval_as_proof_count", 0) <= thresholds.max_retrieval_as_proof,
        f"retrieval_as_proof={summary.get('retrieval_as_proof_count')}; max={thresholds.max_retrieval_as_proof}")
    add("community_as_proof_count", summary.get("community_as_proof_count", 0) <= thresholds.max_community_as_proof,
        f"community_as_proof={summary.get('community_as_proof_count')}; max={thresholds.max_community_as_proof}")
    add("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0) <= thresholds.max_source_truth_mutation_allowed,
        f"source_truth_mutation_allowed={summary.get('source_truth_mutation_allowed_count')}; max={thresholds.max_source_truth_mutation_allowed}")
    if thresholds.require_eval_quality_pass:
        add("source_eval_quality_pass", summary.get("source_eval_quality_status") == "PASS",
            f"source_eval_quality_status={summary.get('source_eval_quality_status')}")
    if thresholds.require_no_answer_permission:
        ok = summary.get("can_answer_directly_count", 0) == 0 and summary.get("can_prove_claims_count", 0) == 0
        add("no_answer_permission", ok,
            f"can_answer_directly={summary.get('can_answer_directly_count')}; can_prove_claims={summary.get('can_prove_claims_count')}")

    return ("PASS" if all(c["ok"] for c in checks) else "FAIL"), checks


def build_compliance_judge(
    eval_report_path: str | Path,
    output_dir: str | Path,
    sample_size: int,
    min_blank_cards: int,
    min_miss_cards: int,
    run_ollama: bool,
    ollama_url: str,
    ollama_model: str,
    ollama_timeout: int,
    quality: bool,
    thresholds: Thresholds,
    ollama_retries: int = 1,
    ollama_num_predict: int = 700,
    ollama_num_ctx: int = 8192,
    allow_text_fallback: bool = False,
) -> Dict[str, Any]:
    eval_payload = load_json(eval_report_path)
    cards = get_cards(eval_payload)
    record_by_page = index_records_by_page(eval_payload)
    sample_cards = select_sample_cards(cards, record_by_page, sample_size, min_blank_cards, min_miss_cards)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records_path = out_dir / DEFAULT_RECORDS_NAME
    responses_path = out_dir / DEFAULT_RESPONSES_NAME
    report_path = out_dir / DEFAULT_REPORT_NAME
    quality_path = out_dir / DEFAULT_QUALITY_NAME
    md_path = out_dir / DEFAULT_MD_NAME

    records: List[Dict[str, Any]] = []
    response_rows: List[Dict[str, Any]] = []

    for idx, card in enumerate(sample_cards, 1):
        record: Dict[str, Any] = {
            "judge_record_id": stable_id(card.get("page_id"), card.get("llm_question"), prefix="llm_graph_path_judge"),
            "sample_index": idx,
            "page_id": card.get("page_id"),
            "page_number": card.get("page_number"),
            "query_type": card.get("query_type"),
            "blank_expected": bool(card.get("blank_expected")) or "BLANK" in str(card.get("expected_answer_behavior", "")).upper(),
            "expected_answer_behavior": card.get("expected_answer_behavior"),
            "graph_path_resolved": bool(card.get("graph_path_resolved")),
            "llm_question": card.get("llm_question"),
            "evaluated": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        }
        prompt = build_llm_prompt(card)
        record["prompt_preview"] = compact_text(prompt, max_chars=900)

        if run_ollama:
            started = time.time()
            try:
                raw_response = ollama_generate(
                    prompt,
                    ollama_url,
                    ollama_model,
                    timeout=ollama_timeout,
                    retries=ollama_retries,
                    num_predict=ollama_num_predict,
                    num_ctx=ollama_num_ctx,
                )
                elapsed = round(time.time() - started, 3)
                parsed, parse_error = extract_json_object(raw_response)
                judged = judge_response(card, raw_response, parsed, parse_error, allow_text_fallback=allow_text_fallback)
                record.update(judged)
                record["evaluated"] = True
                record["elapsed_seconds"] = elapsed
                record["raw_response_preview"] = compact_text(raw_response, max_chars=1200)
                if parsed is not None:
                    record["parsed_response"] = parsed
                response_rows.append({
                    "judge_record_id": record["judge_record_id"],
                    "page_id": card.get("page_id"),
                    "raw_response": raw_response,
                    "parsed_response": parsed,
                    "parse_error": parse_error,
                    "elapsed_seconds": elapsed,
                })
            except (urllib.error.URLError, TimeoutError, RuntimeError, Exception) as exc:
                elapsed = round(time.time() - started, 3)
                record.update({
                    "evaluated": True,
                    "passed": False,
                    "malformed_json": True,
                    "json_format_valid": False,
                    "text_fallback_used": False,
                    "parse_error": f"ollama_error:{type(exc).__name__}:{exc}",
                    "violations": ["ollama_call_failed"],
                    "elapsed_seconds": elapsed,
                    "unsafe_response_count": 0,
                })
                response_rows.append({
                    "judge_record_id": record["judge_record_id"],
                    "page_id": card.get("page_id"),
                    "raw_response": "",
                    "parsed_response": None,
                    "parse_error": record["parse_error"],
                    "elapsed_seconds": elapsed,
                })
        records.append(record)

    write_jsonl(records_path, records)
    write_jsonl(responses_path, response_rows)

    summary = build_summary(
        eval_payload,
        records,
        sample_cards,
        run_ollama,
        ollama_model,
        ollama_url,
        str(records_path),
        str(responses_path),
        ollama_retries=ollama_retries,
        ollama_num_predict=ollama_num_predict,
        ollama_num_ctx=ollama_num_ctx,
        allow_text_fallback=allow_text_fallback,
    )
    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "LLM_GRAPH_PATH_COMPLIANCE_JUDGE_BUILT",
        "quality_status": "NOT_RUN",
        "summary": summary,
        "sampled_cards": sample_cards,
        "judge_records": records,
        "source_artifacts": {
            "eval_report_path": str(eval_report_path),
        },
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "source_truth_mutation": False,
            "answer_permission": False,
            "claim_proof_authority": False,
        },
    }
    q_status, checks = evaluate_quality(report, thresholds)
    if quality:
        report["quality_status"] = q_status
    report["quality_checks"] = checks
    write_json(report_path, report)
    write_json(quality_path, {
        "schema_version": SCHEMA_VERSION,
        "status": report["status"],
        "quality_status": report["quality_status"],
        "summary": summary,
        "quality_checks": checks,
    })
    md_path.write_text(build_markdown(report), encoding="utf-8")
    return report


def build_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# TRACE-Net LLM Graph-Path Compliance Judge v1",
        "",
        f"Status: `{report.get('status')}`",
        f"Quality status: `{report.get('quality_status')}`",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "sampled_record_count",
        "evaluated_record_count",
        "blank_sampled_count",
        "blank_correct_count",
        "graph_path_followed_count",
        "target_page_id_mentioned_count",
        "source_identity_confirmed_count",
        "malformed_json_response_count",
        "json_format_violation_count",
        "text_fallback_used_count",
        "ollama_retries",
        "ollama_num_predict",
        "unsafe_response_count",
        "retrieval_as_proof_count",
        "community_as_proof_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.extend([
        "",
        "## Safety",
        "",
        "This artifact is read-only. It evaluates sampled LLM behavior and does not grant answer permission or claim-proof authority.",
    ])
    return "\n".join(lines) + "\n"


def check_compliance_quality(
    report_path: str | Path,
    thresholds: Thresholds,
    write_json_report: bool = False,
) -> Dict[str, Any]:
    report = load_json(report_path)
    q_status, checks = evaluate_quality(report, thresholds)
    report = dict(report)
    report["quality_status"] = q_status
    report["quality_checks"] = checks
    if write_json_report:
        write_json(Path(report_path).with_name(DEFAULT_QUALITY_NAME), {
            "schema_version": SCHEMA_VERSION,
            "status": report.get("status"),
            "quality_status": q_status,
            "summary": report.get("summary", {}),
            "quality_checks": checks,
        })
    return report


def parse_thresholds(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_sampled_records=args.min_sampled_records,
        min_evaluated_records=args.min_evaluated_records,
        min_graph_path_followed=args.min_graph_path_followed,
        min_target_page_mentioned=args.min_target_page_mentioned,
        min_source_identity_confirmed=args.min_source_identity_confirmed,
        min_blank_correct=args.min_blank_correct,
        max_malformed_responses=args.max_malformed_responses,
        max_unsafe_responses=args.max_unsafe_responses,
        max_retrieval_as_proof=args.max_retrieval_as_proof,
        max_community_as_proof=args.max_community_as_proof,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_eval_quality_pass=args.require_eval_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def add_common_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-sampled-records", type=int, default=1)
    parser.add_argument("--min-evaluated-records", type=int, default=0)
    parser.add_argument("--min-graph-path-followed", type=int, default=0)
    parser.add_argument("--min-target-page-mentioned", type=int, default=0)
    parser.add_argument("--min-source-identity-confirmed", type=int, default=0)
    parser.add_argument("--min-blank-correct", type=int, default=0)
    parser.add_argument("--max-malformed-responses", type=int, default=999999)
    parser.add_argument("--max-unsafe-responses", type=int, default=0)
    parser.add_argument("--max-retrieval-as-proof", type=int, default=0)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-eval-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net LLM Graph-Path Compliance Judge v1")
    parser.add_argument("--page-retrieval-large-eval-v2", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sample-size", type=int, default=12)
    parser.add_argument("--min-blank-cards-in-sample", type=int, default=3)
    parser.add_argument("--min-miss-cards-in-sample", type=int, default=1)
    parser.add_argument("--run-ollama", action="store_true")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-model", default="gemma4:26b")
    parser.add_argument("--ollama-timeout", type=int, default=300)
    parser.add_argument("--ollama-retries", type=int, default=1)
    parser.add_argument("--ollama-num-predict", type=int, default=700)
    parser.add_argument("--ollama-num-ctx", type=int, default=8192)
    parser.add_argument("--allow-text-fallback", action="store_true", help="Accept non-JSON Ollama prose if it still mentions the target page and confirms source identity.")
    parser.add_argument("--quality", action="store_true")
    add_common_threshold_args(parser)
    args = parser.parse_args(argv)

    report = build_compliance_judge(
        eval_report_path=args.page_retrieval_large_eval_v2,
        output_dir=args.output_dir,
        sample_size=args.sample_size,
        min_blank_cards=args.min_blank_cards_in_sample,
        min_miss_cards=args.min_miss_cards_in_sample,
        run_ollama=args.run_ollama,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        ollama_timeout=args.ollama_timeout,
        ollama_retries=args.ollama_retries,
        ollama_num_predict=args.ollama_num_predict,
        ollama_num_ctx=args.ollama_num_ctx,
        allow_text_fallback=args.allow_text_fallback,
        quality=args.quality,
        thresholds=parse_thresholds(args),
    )
    summary = report.get("summary", {})
    print("TRACE-Net LLM Graph-Path Compliance Judge v1")
    print(" Status:", report.get("status"))
    print(" Quality status:", report.get("quality_status"))
    for key in [
        "source_eval_quality_status",
        "sampled_record_count",
        "evaluated_record_count",
        "blank_sampled_count",
        "blank_correct_count",
        "graph_path_followed_count",
        "target_page_id_mentioned_count",
        "source_identity_confirmed_count",
        "malformed_json_response_count",
        "json_format_violation_count",
        "text_fallback_used_count",
        "unsafe_response_count",
        "retrieval_as_proof_count",
        "community_as_proof_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}:", summary.get(key))
    print(" report_path:", str(Path(args.output_dir) / DEFAULT_REPORT_NAME))
    print(" quality_path:", str(Path(args.output_dir) / DEFAULT_QUALITY_NAME))
    return 0 if report.get("quality_status") in {"PASS", "NOT_RUN"} else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net LLM Graph-Path Compliance Judge v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_common_threshold_args(parser)
    args = parser.parse_args(argv)
    report = check_compliance_quality(
        report_path=args.report_path,
        thresholds=parse_thresholds(args),
        write_json_report=args.write_json,
    )
    summary = report.get("summary", {})
    print("TRACE-Net LLM Graph-Path Compliance Judge v1 quality")
    print(" Status:", report.get("status"))
    print(" Quality status:", report.get("quality_status"))
    for key in [
        "source_eval_quality_status",
        "sampled_record_count",
        "evaluated_record_count",
        "blank_correct_count",
        "graph_path_followed_count",
        "target_page_id_mentioned_count",
        "source_identity_confirmed_count",
        "malformed_json_response_count",
        "json_format_violation_count",
        "text_fallback_used_count",
        "unsafe_response_count",
        "retrieval_as_proof_count",
        "community_as_proof_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}:", summary.get(key))
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
