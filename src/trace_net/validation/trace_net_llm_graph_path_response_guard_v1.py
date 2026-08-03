"""TRACE-Net LLM Graph-Path Response Guard v1.

This module is intentionally different from the compliance judge: it does not ask
an LLM to self-report booleans about whether it followed the graph path.  TRACE-Net
already resolves the graph path in Page Retrieval Large Eval v2.  This guard gives
an LLM a compact source-bound card and then deterministically checks whether the
response anchors to the target page/source and avoids forbidden proof/permission
claims.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_llm_graph_path_response_guard_v1"
STATUS = "LLM_GRAPH_PATH_RESPONSE_GUARD_BUILT"

PROHIBITED_RETRIEVAL_AS_PROOF = [
    "qdrant proves",
    "qdrant confirms",
    "semantic similarity proves",
    "retrieval proves",
    "vector search proves",
]
PROHIBITED_COMMUNITY_AS_PROOF = [
    "leiden proves",
    "community proves",
    "category proves",
    "navigation hint proves",
]
PROHIBITED_PERMISSION = [
    "can answer directly: true",
    "can_answer_directly true",
    "can_answer_directly: true",
    "can prove claims: true",
    "can_prove_claims true",
    "can_prove_claims: true",
    "final answer allowed",
    "answer permission granted",
]
PROHIBITED_SOURCE_MUTATION = [
    "source_truth_mutation_allowed true",
    "source_truth_mutation_allowed: true",
    "source truth mutation allowed",
    "mutate source truth",
]
LOCAL_PATH_PATTERNS = [
    "c:\\\\",
    "/c/users/",
    "local_data\\",
    "local_data/",
    "\\users\\",
]


def load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def compact_text(value: Any, max_chars: int = 1200) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def extract_source_entry(card: Mapping[str, Any], record: Mapping[str, Any]) -> Optional[str]:
    for key in ["source_package_entry", "source_package_entry_name", "source_entry"]:
        value = card.get(key) or record.get(key)
        if value:
            return str(value)
    prompt = str(card.get("llm_graph_path_prompt") or "")
    m = re.search(r"Source package\s*entry\s*:\s*([^\s]+)", prompt, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(".,;")
    m = re.search(r"(\d{8}\.tif)", prompt, re.IGNORECASE)
    if m:
        return m.group(1)
    page_number = record.get("page_number") or card.get("page_number")
    if isinstance(page_number, int):
        return f"{page_number:08d}.tif"
    return None


def extract_context_summary(card: Mapping[str, Any], record: Mapping[str, Any], max_chars: int = 700) -> str:
    for source in [card, record, record.get("profile_signals") or {}]:
        for key in ["page_context_summary", "context_summary", "short_summary", "retrieval_summary", "semantic_retrieval_query"]:
            value = source.get(key) if isinstance(source, Mapping) else None
            if value:
                return compact_text(value, max_chars)
    prompt = str(card.get("llm_graph_path_prompt") or "")
    m = re.search(r"Page context summary:\s*(.*?)(?:Retrieval cues:|Expected|Return|$)", prompt, re.IGNORECASE | re.DOTALL)
    if m:
        return compact_text(m.group(1), max_chars)
    return "No page context summary available in the eval card."


def find_card_for_record(cards_by_page: Mapping[str, Mapping[str, Any]], record: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = str(record.get("page_id") or "")
    card = dict(cards_by_page.get(page_id) or {})
    if not card:
        card = {
            "page_id": page_id,
            "page_number": record.get("page_number"),
            "llm_question": record.get("llm_question") or record.get("semantic_retrieval_query") or f"Summarize {page_id}.",
            "expected_answer_behavior": record.get("expected_answer_behavior"),
            "graph_path_resolved": record.get("graph_path_resolved"),
        }
    return card


def select_sample_records(
    records: Sequence[Mapping[str, Any]],
    sample_size: int,
    min_blank_cards: int,
    min_miss_cards: int,
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    seen = set()

    def add(items: Iterable[Mapping[str, Any]], count: int) -> None:
        nonlocal selected
        for item in items:
            if len([r for r in selected if r.get("_bucket") == item.get("_bucket")]) >= count:
                break
            page_id = item.get("page_id")
            if page_id in seen:
                continue
            selected.append(dict(item))
            seen.add(page_id)

    blanks = []
    misses = []
    others = []
    for record in records:
        r = dict(record)
        if r.get("blank_expected"):
            r["_bucket"] = "blank"
            blanks.append(r)
        elif r.get("evaluated") and not r.get("target_hit_at_k"):
            r["_bucket"] = "miss"
            misses.append(r)
        else:
            r["_bucket"] = "regular"
            others.append(r)

    add(blanks, min_blank_cards)
    add(misses, min_miss_cards)
    for collection in [others, blanks, misses]:
        for item in collection:
            if len(selected) >= sample_size:
                break
            page_id = item.get("page_id")
            if page_id in seen:
                continue
            selected.append(dict(item))
            seen.add(page_id)
        if len(selected) >= sample_size:
            break
    return selected[:sample_size]


def build_response_prompt(record: Mapping[str, Any], card: Mapping[str, Any]) -> str:
    page_id = str(record.get("page_id") or card.get("page_id") or "")
    page_number = record.get("page_number") or card.get("page_number")
    blank_expected = bool(record.get("blank_expected"))
    source_entry = extract_source_entry(card, record) or "UNKNOWN_SOURCE_ENTRY"
    question = compact_text(card.get("llm_question") or record.get("llm_question") or "Summarize this page.", 500)
    context_summary = extract_context_summary(card, record, max_chars=700)
    expected = card.get("expected_answer_behavior") or record.get("expected_answer_behavior") or "GRAPH_PATH_SOURCE_BOUND_RESPONSE_ONLY"

    blank_rule = (
        "This target page is expected to be blank/empty. Your answer must explicitly say the source-linked page is blank or empty."
        if blank_expected
        else "This target page is not expected to be blank. Summarize only the source-linked page context."
    )

    return (
        "You are TRACE-Net responding from a source-bound graph card.\n"
        "Do not self-grade. Do not output JSON. Do not output markdown.\n"
        "Use only the target page/source values below.\n\n"
        f"TARGET_PAGE_ID: {page_id}\n"
        f"TARGET_PAGE_NUMBER: {page_number}\n"
        f"SOURCE_PACKAGE_ENTRY: {source_entry}\n"
        "REQUIRED_GRAPH_PATH: Page node -> SourceLink / Dublin Core source package entry -> source-resolved evidence\n"
        f"BLANK_EXPECTED: {str(blank_expected).lower()}\n"
        f"EXPECTED_BEHAVIOR: {expected}\n"
        f"USER_QUESTION: {question}\n"
        f"SOURCE_BOUND_PAGE_CONTEXT: {context_summary}\n\n"
        "Response rules:\n"
        f"1. Start with exactly: Page {page_id} ({source_entry}) was resolved through the graph/source package path.\n"
        "2. Continue with the source-linked page summary only.\n"
        f"3. {blank_rule}\n"
        "4. Never say Qdrant, retrieval, Leiden, community, or category proves the answer.\n"
        "5. Never claim final answer permission or claim-proof authority.\n"
        "6. Use 1-3 short sentences only.\n"
    )


def build_source_anchor_prefix(record: Mapping[str, Any], card: Mapping[str, Any]) -> str:
    page_id = str(record.get("page_id") or card.get("page_id") or "")
    source_entry = extract_source_entry(card, record) or "UNKNOWN_SOURCE_ENTRY"
    blank_expected = bool(record.get("blank_expected"))
    suffix = ""
    if blank_expected:
        suffix = " This source-linked page is blank or empty."
    return (
        f"Page {page_id} ({source_entry}) was resolved through the graph/source package path."
        f"{suffix}"
    )


def apply_source_anchor_prefix(record: Mapping[str, Any], card: Mapping[str, Any], response_text: str, enabled: bool) -> Tuple[str, bool]:
    if not enabled:
        return response_text or "", False
    prefix = build_source_anchor_prefix(record, card)
    text = (response_text or "").strip()
    if text.lower().startswith(prefix.lower()):
        return text, False
    if text:
        return f"{prefix} {text}", True
    return prefix, True


def ollama_generate(
    prompt: str,
    ollama_url: str,
    model: str,
    timeout: int,
    retries: int,
    num_predict: int,
    num_ctx: int,
) -> Tuple[bool, str, Optional[str], int]:
    endpoint = ollama_url.rstrip("/") + "/api/generate"
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": num_predict,
            "num_ctx": num_ctx,
            "temperature": 0,
            "top_p": 0.1,
        },
    }
    last_error: Optional[str] = None
    attempts = 0
    for attempt in range(retries + 1):
        attempts += 1
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return True, str(payload.get("response") or ""), None, attempts
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(min(5, 1 + attempt))
    return False, "", last_error, attempts


def contains_any(text: str, patterns: Sequence[str]) -> bool:
    lower = text.lower()
    return any(p.lower() in lower for p in patterns)


def normalize_for_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def score_response(record: Mapping[str, Any], card: Mapping[str, Any], response_text: str, call_ok: bool, call_error: Optional[str]) -> Dict[str, Any]:
    page_id = str(record.get("page_id") or card.get("page_id") or "")
    page_number = record.get("page_number") or card.get("page_number")
    source_entry = extract_source_entry(card, record) or ""
    blank_expected = bool(record.get("blank_expected"))
    text = response_text or ""
    lower = text.lower()
    normalized = normalize_for_match(text)

    page_id_anchored = page_id.lower() in lower or normalize_for_match(page_id) in normalized
    page_number_anchored = bool(page_number is not None and re.search(rf"\bpage\s+{int(page_number)}\b", lower)) if isinstance(page_number, int) else False
    source_entry_anchored = bool(source_entry and source_entry.lower() in lower)
    source_identity_anchored = source_entry_anchored or ("source" in lower and ("graph" in lower or "dublin" in lower or "package" in lower))
    graph_path_anchored = "graph" in lower and ("source" in lower or "dublin" in lower or "package" in lower)
    blank_correct = True
    if blank_expected:
        blank_correct = "blank" in lower or "empty" in lower

    retrieval_as_proof = contains_any(text, PROHIBITED_RETRIEVAL_AS_PROOF)
    community_as_proof = contains_any(text, PROHIBITED_COMMUNITY_AS_PROOF)
    permission_claim = contains_any(text, PROHIBITED_PERMISSION)
    source_truth_mutation_allowed = contains_any(text, PROHIBITED_SOURCE_MUTATION)
    local_path_leak = contains_any(text, LOCAL_PATH_PATTERNS)
    unsafe = (not call_ok) or retrieval_as_proof or community_as_proof or permission_claim or source_truth_mutation_allowed or local_path_leak

    violations: List[str] = []
    if not call_ok:
        violations.append("ollama_call_failed")
    if not graph_path_anchored:
        violations.append("graph_path_not_anchored")
    if not page_id_anchored:
        violations.append("target_page_id_not_anchored")
    if not source_identity_anchored:
        violations.append("source_identity_not_anchored")
    if blank_expected and not blank_correct:
        violations.append("blank_page_not_declared")
    if retrieval_as_proof:
        violations.append("retrieval_as_proof")
    if community_as_proof:
        violations.append("community_as_proof")
    if permission_claim:
        violations.append("llm_claimed_answer_permission_or_claim_proof")
    if source_truth_mutation_allowed:
        violations.append("source_truth_mutation_allowed")
    if local_path_leak:
        violations.append("local_path_leak")

    passed = (
        call_ok
        and graph_path_anchored
        and page_id_anchored
        and source_identity_anchored
        and blank_correct
        and not unsafe
    )
    return {
        "page_id": page_id,
        "page_number": page_number,
        "blank_expected": blank_expected,
        "response_text": text,
        "raw_response_preview": compact_text(text, 700),
        "call_ok": call_ok,
        "call_error": call_error,
        "graph_path_anchored": graph_path_anchored,
        "target_page_id_anchored": page_id_anchored,
        "target_page_number_anchored": page_number_anchored,
        "source_identity_anchored": source_identity_anchored,
        "source_entry_anchored": source_entry_anchored,
        "blank_correct": blank_correct,
        "retrieval_as_proof": retrieval_as_proof,
        "community_as_proof": community_as_proof,
        "llm_claimed_answer_permission": permission_claim,
        "llm_claimed_claim_proof_authority": permission_claim,
        "source_truth_mutation_allowed": source_truth_mutation_allowed,
        "local_path_leak": local_path_leak,
        "unsafe_response": unsafe,
        "passed": passed,
        "violations": violations,
    }


def build_records(
    eval_payload: Mapping[str, Any],
    sample_size: int,
    min_blank_cards: int,
    min_miss_cards: int,
    run_ollama: bool,
    ollama_url: str,
    ollama_model: str,
    ollama_timeout: int,
    ollama_retries: int,
    ollama_num_predict: int,
    ollama_num_ctx: int,
    progress: bool = False,
    enforce_source_anchor_prefix: bool = False,
) -> List[Dict[str, Any]]:
    query_records = eval_payload.get("query_records") or []
    cards = eval_payload.get("llm_graph_path_cards") or []
    cards_by_page = {str(c.get("page_id")): c for c in cards if c.get("page_id")}
    sampled = select_sample_records(query_records, sample_size, min_blank_cards, min_miss_cards)
    output: List[Dict[str, Any]] = []
    for idx, record in enumerate(sampled, start=1):
        card = find_card_for_record(cards_by_page, record)
        prompt = build_response_prompt(record, card)
        call_ok = False
        call_error = None
        response = ""
        attempts = 0
        if run_ollama:
            if progress:
                print(f"TRACE-Net response guard: running Ollama {idx}/{len(sampled)} page={record.get('page_id')}")
            call_ok, response, call_error, attempts = ollama_generate(
                prompt=prompt,
                ollama_url=ollama_url,
                model=ollama_model,
                timeout=ollama_timeout,
                retries=ollama_retries,
                num_predict=ollama_num_predict,
                num_ctx=ollama_num_ctx,
            )
        raw_scored = score_response(record, card, response, call_ok if run_ollama else False, call_error)
        guarded_response, prefix_applied = apply_source_anchor_prefix(
            record,
            card,
            response,
            enabled=bool(run_ollama and enforce_source_anchor_prefix and call_ok),
        )
        scored = score_response(record, card, guarded_response, call_ok if run_ollama else False, call_error)
        result = {
            "schema_version": SCHEMA_VERSION,
            "record_id": f"response_guard::{record.get('page_id')}",
            "page_id": record.get("page_id"),
            "page_number": record.get("page_number"),
            "query_type": record.get("query_type"),
            "blank_expected": bool(record.get("blank_expected")),
            "target_hit_at_k": record.get("target_hit_at_k"),
            "graph_path_resolved": bool(record.get("graph_path_resolved")),
            "llm_question": card.get("llm_question") or record.get("llm_question"),
            "source_package_entry": extract_source_entry(card, record),
            "prompt_mode": "source_bound_plain_text_response_guard",
            "llm_prompt": prompt,
            "evaluated": bool(run_ollama),
            "ollama_attempt_count": attempts,
            "system_anchor_prefix_applied": prefix_applied,
            "model_response_text": response,
            "model_raw_response_preview": compact_text(response, 700),
            "model_response_graph_path_anchored": raw_scored.get("graph_path_anchored"),
            "model_response_target_page_id_anchored": raw_scored.get("target_page_id_anchored"),
            "model_response_source_identity_anchored": raw_scored.get("source_identity_anchored"),
            "model_response_blank_correct": raw_scored.get("blank_correct"),
            "guarded_response_text": guarded_response,
            **scored,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "retrieval_only": True,
        }
        output.append(result)
    return output


def summarize(eval_payload: Mapping[str, Any], records: Sequence[Mapping[str, Any]], run_ollama: bool, args: argparse.Namespace) -> Dict[str, Any]:
    eval_summary = eval_payload.get("summary") or {}
    evaluated = [r for r in records if r.get("evaluated")]
    blank_evaluated = [r for r in evaluated if r.get("blank_expected")]
    def count(key: str, value: Any = True) -> int:
        return sum(1 for r in evaluated if r.get(key) == value)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "source_eval_quality_status": eval_payload.get("quality_status") or eval_summary.get("quality_status"),
        "source_eval_query_record_count": eval_summary.get("query_record_count"),
        "source_eval_graph_path_resolved_count": eval_summary.get("graph_path_resolved_count"),
        "source_eval_llm_graph_path_card_count": eval_summary.get("llm_graph_path_card_count"),
        "source_eval_target_hit_at_k_rate": eval_summary.get("target_hit_at_k_rate"),
        "run_ollama": bool(run_ollama),
        "ollama_url": args.ollama_url if run_ollama else None,
        "ollama_model": args.ollama_model if run_ollama else None,
        "ollama_timeout": args.ollama_timeout if run_ollama else None,
        "ollama_retries": args.ollama_retries if run_ollama else None,
        "ollama_num_predict": args.ollama_num_predict if run_ollama else None,
        "ollama_num_ctx": args.ollama_num_ctx if run_ollama else None,
        "enforce_source_anchor_prefix": bool(getattr(args, "enforce_source_anchor_prefix", False)),
        "sampled_record_count": len(records),
        "evaluated_record_count": len(evaluated),
        "blank_sampled_count": sum(1 for r in records if r.get("blank_expected")),
        "blank_evaluated_count": len(blank_evaluated),
        "blank_correct_count": sum(1 for r in blank_evaluated if r.get("blank_correct")),
        "graph_path_bound_count": sum(1 for r in records if r.get("graph_path_resolved")),
        "graph_path_anchored_count": count("graph_path_anchored"),
        "target_page_id_anchored_count": count("target_page_id_anchored"),
        "target_page_number_anchored_count": count("target_page_number_anchored"),
        "source_identity_anchored_count": count("source_identity_anchored"),
        "source_entry_anchored_count": count("source_entry_anchored"),
        "system_anchor_prefix_applied_count": sum(1 for r in evaluated if r.get("system_anchor_prefix_applied")),
        "model_response_graph_path_anchored_count": sum(1 for r in evaluated if r.get("model_response_graph_path_anchored")),
        "model_response_target_page_id_anchored_count": sum(1 for r in evaluated if r.get("model_response_target_page_id_anchored")),
        "model_response_source_identity_anchored_count": sum(1 for r in evaluated if r.get("model_response_source_identity_anchored")),
        "ollama_call_failed_count": sum(1 for r in evaluated if not r.get("call_ok")),
        "unsafe_response_count": count("unsafe_response"),
        "retrieval_as_proof_count": count("retrieval_as_proof"),
        "community_as_proof_count": count("community_as_proof"),
        "llm_claimed_answer_permission_count": count("llm_claimed_answer_permission"),
        "llm_claimed_claim_proof_authority_count": count("llm_claimed_claim_proof_authority"),
        "local_path_leak_count": count("local_path_leak"),
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": count("source_truth_mutation_allowed"),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def build_quality_checks(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
    add("sampled_record_count", summary.get("sampled_record_count", 0) >= thresholds.get("min_sampled_records", 0), f"records={summary.get('sampled_record_count')}; minimum={thresholds.get('min_sampled_records')}")
    add("evaluated_record_count", summary.get("evaluated_record_count", 0) >= thresholds.get("min_evaluated_records", 0), f"evaluated={summary.get('evaluated_record_count')}; minimum={thresholds.get('min_evaluated_records')}")
    add("graph_path_bound_count", summary.get("graph_path_bound_count", 0) >= thresholds.get("min_graph_path_bound", 0), f"bound={summary.get('graph_path_bound_count')}; minimum={thresholds.get('min_graph_path_bound')}")
    add("graph_path_anchored_count", summary.get("graph_path_anchored_count", 0) >= thresholds.get("min_graph_path_anchored", 0), f"anchored={summary.get('graph_path_anchored_count')}; minimum={thresholds.get('min_graph_path_anchored')}")
    add("target_page_id_anchored_count", summary.get("target_page_id_anchored_count", 0) >= thresholds.get("min_target_page_id_anchored", 0), f"target={summary.get('target_page_id_anchored_count')}; minimum={thresholds.get('min_target_page_id_anchored')}")
    add("source_identity_anchored_count", summary.get("source_identity_anchored_count", 0) >= thresholds.get("min_source_identity_anchored", 0), f"source={summary.get('source_identity_anchored_count')}; minimum={thresholds.get('min_source_identity_anchored')}")
    add("blank_correct_count", summary.get("blank_correct_count", 0) >= thresholds.get("min_blank_correct", 0), f"blank={summary.get('blank_correct_count')}; minimum={thresholds.get('min_blank_correct')}")
    add("unsafe_response_count", summary.get("unsafe_response_count", 0) <= thresholds.get("max_unsafe_responses", 0), f"unsafe={summary.get('unsafe_response_count')}; max={thresholds.get('max_unsafe_responses')}")
    add("retrieval_as_proof_count", summary.get("retrieval_as_proof_count", 0) <= thresholds.get("max_retrieval_as_proof", 0), f"retrieval_as_proof={summary.get('retrieval_as_proof_count')}; max={thresholds.get('max_retrieval_as_proof')}")
    add("community_as_proof_count", summary.get("community_as_proof_count", 0) <= thresholds.get("max_community_as_proof", 0), f"community_as_proof={summary.get('community_as_proof_count')}; max={thresholds.get('max_community_as_proof')}")
    add("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0) <= thresholds.get("max_source_truth_mutation_allowed", 0), f"source_truth_mutation_allowed={summary.get('source_truth_mutation_allowed_count')}; max={thresholds.get('max_source_truth_mutation_allowed')}")
    if thresholds.get("require_eval_quality_pass"):
        add("source_eval_quality_status", summary.get("source_eval_quality_status") == "PASS", f"source_eval_quality_status={summary.get('source_eval_quality_status')}")
    if thresholds.get("require_no_answer_permission"):
        add("no_answer_permission", summary.get("can_answer_directly_count") == 0 and summary.get("can_prove_claims_count") == 0, f"can_answer_directly={summary.get('can_answer_directly_count')}; can_prove_claims={summary.get('can_prove_claims_count')}")
    return checks


def quality_status(checks: Sequence[Mapping[str, Any]]) -> str:
    return "PASS" if all(c.get("ok") for c in checks) else "FAIL"


def build_response_guard(
    page_retrieval_large_eval_v2: str | Path,
    output_dir: str | Path,
    sample_size: int,
    min_blank_cards_in_sample: int,
    min_miss_cards_in_sample: int,
    run_ollama: bool,
    ollama_url: str,
    ollama_model: str,
    ollama_timeout: int,
    ollama_retries: int,
    ollama_num_predict: int,
    ollama_num_ctx: int,
    progress: bool,
    thresholds: Mapping[str, Any],
) -> Dict[str, Any]:
    eval_payload = load_json(page_retrieval_large_eval_v2)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    args = argparse.Namespace(
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        ollama_timeout=ollama_timeout,
        ollama_retries=ollama_retries,
        ollama_num_predict=ollama_num_predict,
        ollama_num_ctx=ollama_num_ctx,
        enforce_source_anchor_prefix=thresholds.get("enforce_source_anchor_prefix", False),
    )
    records = build_records(
        eval_payload=eval_payload,
        sample_size=sample_size,
        min_blank_cards=min_blank_cards_in_sample,
        min_miss_cards=min_miss_cards_in_sample,
        run_ollama=run_ollama,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        ollama_timeout=ollama_timeout,
        ollama_retries=ollama_retries,
        ollama_num_predict=ollama_num_predict,
        ollama_num_ctx=ollama_num_ctx,
        progress=progress,
        enforce_source_anchor_prefix=thresholds.get("enforce_source_anchor_prefix", False),
    )
    summary = summarize(eval_payload, records, run_ollama, args)
    checks = build_quality_checks(summary, thresholds)
    qstatus = quality_status(checks)
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "quality_status": qstatus,
        "source_eval_path": str(page_retrieval_large_eval_v2),
        "summary": summary,
        "quality_checks": checks,
        "response_guard_records": records,
    }
    report_path = out / "trace_net_llm_graph_path_response_guard_v1.json"
    quality_path = out / "trace_net_llm_graph_path_response_guard_v1_quality.json"
    records_path = out / "trace_net_llm_graph_path_response_guard_v1_records.jsonl"
    responses_path = out / "trace_net_llm_graph_path_response_guard_v1_responses.jsonl"
    write_json(report_path, payload)
    write_json(quality_path, {"schema_version": SCHEMA_VERSION, "status": STATUS, "quality_status": qstatus, "summary": summary, "quality_checks": checks})
    write_jsonl(records_path, records)
    write_jsonl(responses_path, [{"page_id": r.get("page_id"), "response_text": r.get("response_text"), "violations": r.get("violations")} for r in records])
    payload["report_path"] = str(report_path)
    payload["quality_path"] = str(quality_path)
    payload["records_path"] = str(records_path)
    payload["responses_path"] = str(responses_path)
    write_markdown(out / "trace_net_llm_graph_path_response_guard_v1.md", payload)
    return payload


def write_markdown(path: str | Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net LLM Graph-Path Response Guard v1",
        "",
        f"Status: {payload.get('status')}",
        f"Quality status: {payload.get('quality_status')}",
        "",
        "This artifact checks source-bound LLM responses with deterministic guards. It does not allow the LLM to grant answer/proof authority.",
        "",
        "## Summary",
    ]
    for key in [
        "sampled_record_count",
        "evaluated_record_count",
        "graph_path_bound_count",
        "graph_path_anchored_count",
        "target_page_id_anchored_count",
        "source_identity_anchored_count",
        "blank_correct_count",
        "unsafe_response_count",
        "retrieval_as_proof_count",
        "community_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_thresholds(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_sampled_records": args.min_sampled_records,
        "min_evaluated_records": args.min_evaluated_records,
        "min_graph_path_bound": args.min_graph_path_bound,
        "min_graph_path_anchored": args.min_graph_path_anchored,
        "min_target_page_id_anchored": args.min_target_page_id_anchored,
        "min_source_identity_anchored": args.min_source_identity_anchored,
        "min_blank_correct": args.min_blank_correct,
        "max_unsafe_responses": args.max_unsafe_responses,
        "max_retrieval_as_proof": args.max_retrieval_as_proof,
        "max_community_as_proof": args.max_community_as_proof,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_eval_quality_pass": args.require_eval_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
        "enforce_source_anchor_prefix": getattr(args, "enforce_source_anchor_prefix", False),
    }


def check_response_guard_quality(report_path: str | Path, thresholds: Mapping[str, Any], write_json_report: bool = False) -> Dict[str, Any]:
    report = load_json(report_path)
    summary = report.get("summary") or {}
    checks = build_quality_checks(summary, thresholds)
    qstatus = quality_status(checks)
    out = {"schema_version": SCHEMA_VERSION, "status": report.get("status"), "quality_status": qstatus, "summary": summary, "quality_checks": checks}
    if write_json_report:
        quality_path = Path(report_path).with_name("trace_net_llm_graph_path_response_guard_v1_quality.json")
        write_json(quality_path, out)
    return out


def add_common_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-sampled-records", type=int, default=1)
    parser.add_argument("--min-evaluated-records", type=int, default=0)
    parser.add_argument("--min-graph-path-bound", type=int, default=1)
    parser.add_argument("--min-graph-path-anchored", type=int, default=0)
    parser.add_argument("--min-target-page-id-anchored", type=int, default=0)
    parser.add_argument("--min-source-identity-anchored", type=int, default=0)
    parser.add_argument("--min-blank-correct", type=int, default=0)
    parser.add_argument("--max-unsafe-responses", type=int, default=0)
    parser.add_argument("--max-retrieval-as-proof", type=int, default=0)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-eval-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net LLM Graph-Path Response Guard v1")
    parser.add_argument("--page-retrieval-large-eval-v2", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sample-size", type=int, default=5)
    parser.add_argument("--min-blank-cards-in-sample", type=int, default=1)
    parser.add_argument("--min-miss-cards-in-sample", type=int, default=0)
    parser.add_argument("--run-ollama", action="store_true")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-model", default="gemma4:26b")
    parser.add_argument("--ollama-timeout", type=int, default=300)
    parser.add_argument("--ollama-retries", type=int, default=1)
    parser.add_argument("--ollama-num-predict", type=int, default=220)
    parser.add_argument("--ollama-num-ctx", type=int, default=4096)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--enforce-source-anchor-prefix", action="store_true", help="Prefix the scored response with the deterministic page/source graph anchor before guard scoring.")
    parser.add_argument("--quality", action="store_true")
    add_common_threshold_args(parser)
    return parser


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = build_response_guard(
        page_retrieval_large_eval_v2=args.page_retrieval_large_eval_v2,
        output_dir=args.output_dir,
        sample_size=args.sample_size,
        min_blank_cards_in_sample=args.min_blank_cards_in_sample,
        min_miss_cards_in_sample=args.min_miss_cards_in_sample,
        run_ollama=args.run_ollama,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        ollama_timeout=args.ollama_timeout,
        ollama_retries=args.ollama_retries,
        ollama_num_predict=args.ollama_num_predict,
        ollama_num_ctx=args.ollama_num_ctx,
        progress=args.progress,
        thresholds=parse_thresholds(args),
    )
    summary = payload.get("summary") or {}
    print("TRACE-Net LLM Graph-Path Response Guard v1")
    print(" Status:", payload.get("status"))
    print(" Quality status:", payload.get("quality_status"))
    for key in [
        "source_eval_quality_status",
        "sampled_record_count",
        "evaluated_record_count",
        "blank_sampled_count",
        "blank_correct_count",
        "graph_path_bound_count",
        "graph_path_anchored_count",
        "target_page_id_anchored_count",
        "source_identity_anchored_count",
        "system_anchor_prefix_applied_count",
        "model_response_graph_path_anchored_count",
        "model_response_target_page_id_anchored_count",
        "model_response_source_identity_anchored_count",
        "ollama_call_failed_count",
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
    print(" report_path:", payload.get("report_path"))
    print(" quality_path:", payload.get("quality_path"))
    return 0 if payload.get("quality_status") == "PASS" else 1


def check_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net LLM Graph-Path Response Guard v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_common_threshold_args(parser)
    return parser


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = check_arg_parser()
    args = parser.parse_args(argv)
    report = check_response_guard_quality(args.report_path, parse_thresholds(args), write_json_report=args.write_json)
    summary = report.get("summary") or {}
    print("TRACE-Net LLM Graph-Path Response Guard v1")
    print(" Status:", report.get("status"))
    print(" Quality status:", report.get("quality_status"))
    for key in [
        "source_eval_quality_status",
        "sampled_record_count",
        "evaluated_record_count",
        "blank_correct_count",
        "graph_path_bound_count",
        "graph_path_anchored_count",
        "target_page_id_anchored_count",
        "source_identity_anchored_count",
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
