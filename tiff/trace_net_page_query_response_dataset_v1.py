"""TRACE-Net Page Query Response Dataset v1.

Builds a read-only, source-bound page question/response dataset from
Page Retrieval Large Eval v2 records. The output is meant for browsing and
manual QA, not for granting answer permission.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_page_query_response_dataset_v1"
REPORT_NAME = "trace_net_page_query_response_dataset_v1.json"
QUALITY_NAME = "trace_net_page_query_response_dataset_v1_quality.json"
RECORDS_NAME = "trace_net_page_query_response_dataset_v1_records.jsonl"
RESPONSES_NAME = "trace_net_page_query_response_dataset_v1_responses.jsonl"
MARKDOWN_NAME = "trace_net_page_query_response_dataset_v1.md"

DEFAULT_MANUAL_LABEL = "EMB CMM ATA 25-21-00 REV.4"


def load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: str | Path, records: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def get_list(payload: Mapping[str, Any], keys: Sequence[str]) -> List[Dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
    return []


def compact_text(value: Any, max_chars: int = 800) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "..."
    return text


def page_number_from_id(page_id: str) -> Optional[int]:
    m = re.search(r"p(\d{6})$", page_id or "")
    if not m:
        return None
    return int(m.group(1))


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ok", "pass"}
    return bool(value)


def extract_source_entry_from_prompt(prompt: str) -> Optional[str]:
    if not prompt:
        return None
    match = re.search(r"Source package\s*entry\s*:\s*([0-9]{8}\.tif)", prompt, flags=re.I)
    if match:
        return match.group(1)
    match = re.search(r"Source packageentry\s*:\s*([0-9]{8}\.tif)", prompt, flags=re.I)
    if match:
        return match.group(1)
    return None


def extract_context_summary_from_prompt(prompt: str) -> str:
    if not prompt:
        return ""
    # Most cards use: Page context summary: ... Retrieval cues:
    patterns = [
        r"Page context summary:\s*(.*?)(?:\s+Retrieval cues:|\s+Expected behavior:|\s+Answer only|$)",
        r"Context summary:\s*(.*?)(?:\s+Retrieval cues:|\s+Expected behavior:|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.I | re.S)
        if match:
            return compact_text(match.group(1), max_chars=700)
    return ""


def find_nested_string(obj: Any, preferred_keys: Sequence[str]) -> str:
    if isinstance(obj, dict):
        for key in preferred_keys:
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return compact_text(value, max_chars=700)
            if isinstance(value, (dict, list)):
                nested = find_nested_string(value, preferred_keys)
                if nested:
                    return nested
        for value in obj.values():
            nested = find_nested_string(value, preferred_keys)
            if nested:
                return nested
    elif isinstance(obj, list):
        for value in obj:
            nested = find_nested_string(value, preferred_keys)
            if nested:
                return nested
    return ""


def index_by_page(records: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for record in records:
        page_id = record.get("page_id") or record.get("id") or record.get("page")
        if isinstance(page_id, str) and page_id:
            out[page_id] = dict(record)
    return out


def top_hits_for_record(eval_record: Mapping[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    hits = eval_record.get("top_hits")
    if not isinstance(hits, list):
        return []
    out: List[Dict[str, Any]] = []
    for hit in hits[:limit]:
        if not isinstance(hit, dict):
            continue
        out.append(
            {
                "rank": hit.get("rank"),
                "page_id": hit.get("page_id"),
                "score": hit.get("score"),
                "target_hit": bool(hit.get("target_hit")),
            }
        )
    return out


def get_source_identity(eval_record: Mapping[str, Any], card: Mapping[str, Any], page_number: Optional[int]) -> Dict[str, Any]:
    dc = eval_record.get("dublin_core_source_identity")
    if isinstance(dc, dict):
        source_package = dc.get("source_package") if isinstance(dc.get("source_package"), dict) else {}
        return {
            "source_identity_status": dc.get("source_identity_status") or "DUBLIN_CORE_SOURCE_IDENTITY_RESOLVED",
            "dc_identifier": dc.get("dc_identifier") or eval_record.get("page_id"),
            "dc_title": dc.get("dc_title"),
            "source_package_entry_name": source_package.get("trace_net:source_package_entry_name"),
            "source_package_entry_href": source_package.get("trace_net:source_package_entry_href"),
            "source_package_label": source_package.get("trace_net:source_package_label"),
            "source_package_page_number": source_package.get("trace_net:source_package_page_number"),
        }

    prompt = str(card.get("llm_graph_path_prompt") or "")
    entry = extract_source_entry_from_prompt(prompt)
    if not entry and page_number is not None:
        entry = f"{page_number:08d}.tif"
    return {
        "source_identity_status": "GRAPH_CARD_SOURCE_IDENTITY_RESOLVED" if entry else "SOURCE_IDENTITY_NOT_RESOLVED",
        "dc_identifier": eval_record.get("page_id") or card.get("page_id"),
        "dc_title": f"TRACE-Net page {page_number}" if page_number is not None else None,
        "source_package_entry_name": entry,
        "source_package_entry_href": f"file://./{entry}" if entry else None,
        "source_package_label": DEFAULT_MANUAL_LABEL,
        "source_package_page_number": page_number,
    }


def get_page_context_summary(eval_record: Mapping[str, Any], card: Mapping[str, Any], profile: Mapping[str, Any]) -> str:
    prompt_summary = extract_context_summary_from_prompt(str(card.get("llm_graph_path_prompt") or ""))
    if prompt_summary:
        return prompt_summary

    preferred = [
        "short_summary",
        "retrieval_summary",
        "page_context_summary",
        "context_summary",
        "summary",
        "embedding_text",
    ]
    profile_summary = find_nested_string(profile, preferred)
    if profile_summary:
        return profile_summary

    profile_signals = eval_record.get("profile_signals")
    if isinstance(profile_signals, dict):
        signal_summary = find_nested_string(profile_signals, preferred)
        if signal_summary:
            return signal_summary

    semantic_query = eval_record.get("semantic_retrieval_query")
    if isinstance(semantic_query, str) and semantic_query.strip():
        # Avoid echoing the full eval query. Pull out the Summary clause if present.
        m = re.search(r"Summary:\s*(.*?)(?:\.\s*Retrieval cues/questions:|$)", semantic_query, flags=re.I | re.S)
        if m:
            return compact_text(m.group(1), max_chars=700)
    return "No page-context summary was available in the source artifacts."


def infer_page_role(eval_record: Mapping[str, Any], profile: Mapping[str, Any], summary: str, blank_expected: bool) -> str:
    if blank_expected:
        return "blank"
    for source in (eval_record.get("profile_signals"), profile):
        if isinstance(source, dict):
            for key in ("role", "page_role", "subrole", "page_subrole"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    text = summary.lower()
    if "revision" in text or "title block" in text:
        return "front_matter"
    if "parts list" in text or "part number" in text:
        return "parts_list"
    if "diagram" in text or "figure" in text or "visual" in text:
        return "visual_or_diagram"
    if "table" in text:
        return "table_or_grid"
    return "page_context"


def make_natural_question(page_number: int, manual_label: str, summary: str, role: str, blank_expected: bool) -> str:
    if blank_expected:
        return f"What is on page {page_number} of {manual_label}? If it is blank, say the page is blank."

    low = summary.lower()
    if role == "front_matter" or "revision" in low or "title block" in low:
        return f"What revision or front-matter information is shown on page {page_number} of {manual_label}?"
    if "part number" in low or "parts list" in low or role == "parts_list":
        return f"Which parts-list or part-number information is covered on page {page_number} of {manual_label}?"
    if "diagram" in low or "figure" in low or role == "visual_or_diagram":
        return f"What diagram or visual information does page {page_number} of {manual_label} contain?"
    if "table" in low or role == "table_or_grid":
        return f"What table or structured information is on page {page_number} of {manual_label}?"
    return f"What does page {page_number} of {manual_label} contain?"


def make_source_bound_response(
    page_id: str,
    page_number: int,
    source_identity: Mapping[str, Any],
    summary: str,
    blank_expected: bool,
) -> Tuple[str, str]:
    entry = source_identity.get("source_package_entry_name") or f"{page_number:08d}.tif"
    anchor = f"Page {page_id} ({entry}) was resolved through the TRACE-Net graph/source package path."
    if blank_expected:
        answer = (
            f"{anchor} The page is blank or empty, so there is no page content to summarize. "
            "Do not infer any technical content from this page."
        )
        expected = "SOURCE_BOUND_RESPONSE_SHOULD_STATE_PAGE_IS_BLANK_OR_EMPTY"
    else:
        answer = (
            f"{anchor} The source-linked page appears to contain: {summary} "
            "This is a source-bound page summary for review and retrieval; it does not grant final-answer authority."
        )
        expected = "SOURCE_BOUND_RESPONSE_SHOULD_SUMMARIZE_SOURCE_LINKED_PAGE_ONLY"
    return answer, expected


def build_page_query_response_records(
    eval_payload: Mapping[str, Any],
    profile_payload: Optional[Mapping[str, Any]] = None,
    *,
    first_pages: int = 200,
    manual_label: str = DEFAULT_MANUAL_LABEL,
) -> List[Dict[str, Any]]:
    query_records = get_list(eval_payload, ["query_records", "records"])
    cards = get_list(eval_payload, ["llm_graph_path_cards", "cards"])
    profiles = get_list(profile_payload or {}, ["page_profiles", "profiles", "records"])

    by_page_record = index_by_page(query_records)
    by_page_card = index_by_page(cards)
    by_page_profile = index_by_page(profiles)

    # Prefer eval records because they include Qdrant results. If cards exist for pages without
    # eval records, include them as fallback.
    page_ids = set(by_page_record) | set(by_page_card)
    sorted_page_ids = sorted(
        page_ids,
        key=lambda p: (page_number_from_id(p) is None, page_number_from_id(p) or 10**9, p),
    )

    out: List[Dict[str, Any]] = []
    for page_id in sorted_page_ids:
        page_number = page_number_from_id(page_id)
        if page_number is None or page_number < 1 or page_number > first_pages:
            continue
        eval_record = by_page_record.get(page_id, {})
        card = by_page_card.get(page_id, {})
        profile = by_page_profile.get(page_id, {})

        blank_expected = normalize_bool(eval_record.get("blank_expected") or card.get("blank_expected"))
        graph_path_resolved = normalize_bool(eval_record.get("graph_path_resolved") or card.get("graph_path_resolved"))
        source_identity = get_source_identity(eval_record, card, page_number)
        source_resolved = source_identity.get("source_identity_status") not in {None, "SOURCE_IDENTITY_NOT_RESOLVED"}
        summary = get_page_context_summary(eval_record, card, profile)
        role = infer_page_role(eval_record, profile, summary, blank_expected)
        natural_question = make_natural_question(page_number, manual_label, summary, role, blank_expected)
        graph_path_question = card.get("llm_question") or eval_record.get("llm_question") or natural_question
        answer, expected_behavior = make_source_bound_response(page_id, page_number, source_identity, summary, blank_expected)

        target_rank = eval_record.get("target_rank")
        target_hit_at_k = normalize_bool(eval_record.get("target_hit_at_k")) if "target_hit_at_k" in eval_record else False
        evaluated = normalize_bool(eval_record.get("evaluated")) if "evaluated" in eval_record else False

        record = {
            "schema_version": SCHEMA_VERSION,
            "record_id": f"page_query_response::{page_id}",
            "page_id": page_id,
            "page_number": page_number,
            "manual_label": manual_label,
            "question": natural_question,
            "graph_path_question": graph_path_question,
            "response": answer,
            "expected_response_behavior": expected_behavior,
            "page_role": role,
            "blank_expected": blank_expected,
            "blank_detection": eval_record.get("blank_detection") if isinstance(eval_record.get("blank_detection"), dict) else {},
            "page_context_summary": summary,
            "graph_path": {
                "plan_id": "page_source_context_v1",
                "required_route": "Page -> SourceLink / Dublin Core source package entry -> source-resolved page evidence",
                "graph_path_resolved": graph_path_resolved,
                "source_identity_resolved": bool(source_resolved),
                "target_page_node": f"page:{page_id}",
                "source_package_entry_name": source_identity.get("source_package_entry_name"),
                "source_package_entry_href": source_identity.get("source_package_entry_href"),
            },
            "source_identity": source_identity,
            "qdrant_eval": {
                "evaluated": evaluated,
                "target_rank": target_rank,
                "target_hit_at_k": target_hit_at_k,
                "top_hits": top_hits_for_record(eval_record),
            },
            "safety_contract": {
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "postgres_write_attempt": False,
                "qdrant_write_attempt": False,
                "opensearch_write_attempt": False,
            },
            "review_flags": [],
        }
        if not graph_path_resolved:
            record["review_flags"].append("graph_path_not_resolved")
        if not source_resolved:
            record["review_flags"].append("source_identity_not_resolved")
        if blank_expected and "blank" not in answer.lower() and "empty" not in answer.lower():
            record["review_flags"].append("blank_response_missing_blank_statement")
        out.append(record)

    return out[:first_pages]


def summarize(records: Sequence[Mapping[str, Any]], eval_payload: Mapping[str, Any]) -> Dict[str, Any]:
    eval_summary = eval_payload.get("summary") if isinstance(eval_payload.get("summary"), dict) else {}
    role_counts = Counter(str(r.get("page_role")) for r in records)
    review_flags = Counter()
    for record in records:
        review_flags.update(record.get("review_flags") or [])

    qdrant_evaluated = sum(1 for r in records if (r.get("qdrant_eval") or {}).get("evaluated"))
    target_hit_count = sum(1 for r in records if (r.get("qdrant_eval") or {}).get("target_hit_at_k"))
    target_hit_rate = round(target_hit_count / qdrant_evaluated, 6) if qdrant_evaluated else 0.0

    return {
        "schema_version": SCHEMA_VERSION,
        "source_eval_quality_status": eval_payload.get("quality_status"),
        "source_eval_status": eval_payload.get("status"),
        "source_eval_query_record_count": eval_summary.get("query_record_count"),
        "source_eval_evaluated_record_count": eval_summary.get("evaluated_record_count"),
        "source_eval_context_v2_query_count": eval_summary.get("context_v2_query_count"),
        "source_eval_graph_path_resolved_count": eval_summary.get("graph_path_resolved_count"),
        "source_eval_target_hit_at_k_rate": eval_summary.get("target_hit_at_k_rate"),
        "record_count": len(records),
        "response_count": sum(1 for r in records if r.get("response")),
        "question_count": sum(1 for r in records if r.get("question")),
        "blank_record_count": sum(1 for r in records if r.get("blank_expected")),
        "blank_response_count": sum(1 for r in records if r.get("blank_expected") and ("blank" in str(r.get("response", "")).lower() or "empty" in str(r.get("response", "")).lower())),
        "graph_path_resolved_count": sum(1 for r in records if (r.get("graph_path") or {}).get("graph_path_resolved")),
        "source_identity_resolved_count": sum(1 for r in records if (r.get("graph_path") or {}).get("source_identity_resolved")),
        "qdrant_evaluated_record_count": qdrant_evaluated,
        "qdrant_target_hit_at_k_count": target_hit_count,
        "qdrant_target_hit_at_k_rate": target_hit_rate,
        "role_counts": dict(sorted(role_counts.items())),
        "review_flag_counts": dict(sorted(review_flags.items())),
        "unsafe_response_count": 0,
        "answer_capable_response_count": 0,
        "claim_proof_response_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def quality_checks(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("source_eval_quality_pass", summary.get("source_eval_quality_status") == "PASS" or not thresholds.get("require_eval_quality_pass"), f"source_eval_quality_status={summary.get('source_eval_quality_status')}")
    add("record_count", int(summary.get("record_count") or 0) >= int(thresholds.get("min_records") or 0), f"records={summary.get('record_count')}; minimum={thresholds.get('min_records')}")
    add("response_count", int(summary.get("response_count") or 0) >= int(thresholds.get("min_responses") or 0), f"responses={summary.get('response_count')}; minimum={thresholds.get('min_responses')}")
    add("blank_response_count", int(summary.get("blank_response_count") or 0) >= int(thresholds.get("min_blank_responses") or 0), f"blank_responses={summary.get('blank_response_count')}; minimum={thresholds.get('min_blank_responses')}")
    add("graph_path_resolved_count", int(summary.get("graph_path_resolved_count") or 0) >= int(thresholds.get("min_graph_path_resolved") or 0), f"graph_paths={summary.get('graph_path_resolved_count')}; minimum={thresholds.get('min_graph_path_resolved')}")
    add("source_identity_resolved_count", int(summary.get("source_identity_resolved_count") or 0) >= int(thresholds.get("min_source_identity_resolved") or 0), f"source_identity={summary.get('source_identity_resolved_count')}; minimum={thresholds.get('min_source_identity_resolved')}")
    add("qdrant_evaluated_record_count", int(summary.get("qdrant_evaluated_record_count") or 0) >= int(thresholds.get("min_qdrant_evaluated") or 0), f"qdrant_evaluated={summary.get('qdrant_evaluated_record_count')}; minimum={thresholds.get('min_qdrant_evaluated')}")
    add("unsafe_response_count", int(summary.get("unsafe_response_count") or 0) <= int(thresholds.get("max_unsafe_responses") or 0), f"unsafe={summary.get('unsafe_response_count')}; max={thresholds.get('max_unsafe_responses')}")
    add("answer_capable_response_count", int(summary.get("answer_capable_response_count") or 0) <= int(thresholds.get("max_answer_capable_responses") or 0), f"answer_capable={summary.get('answer_capable_response_count')}; max={thresholds.get('max_answer_capable_responses')}")
    add("claim_proof_response_count", int(summary.get("claim_proof_response_count") or 0) <= int(thresholds.get("max_claim_proof_responses") or 0), f"claim_proof={summary.get('claim_proof_response_count')}; max={thresholds.get('max_claim_proof_responses')}")
    add("source_truth_mutation_allowed_count", int(summary.get("source_truth_mutation_allowed_count") or 0) <= int(thresholds.get("max_source_truth_mutation_allowed") or 0), f"mutations={summary.get('source_truth_mutation_allowed_count')}; max={thresholds.get('max_source_truth_mutation_allowed')}")
    add("no_write_attempts", not any(int(summary.get(k) or 0) for k in ["postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]), "write attempts must be zero")
    if thresholds.get("require_no_answer_permission"):
        add("no_answer_permission", int(summary.get("can_answer_directly_count") or 0) == 0 and int(summary.get("can_prove_claims_count") or 0) == 0, "can_answer_directly/can_prove_claims must be zero")

    status = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    return status, checks


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# TRACE-Net Page Query Response Dataset v1",
        "",
        f"Status: `{payload.get('status')}`",
        f"Quality status: `{payload.get('quality_status')}`",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "record_count",
        "response_count",
        "blank_record_count",
        "blank_response_count",
        "graph_path_resolved_count",
        "source_identity_resolved_count",
        "qdrant_evaluated_record_count",
        "qdrant_target_hit_at_k_count",
        "qdrant_target_hit_at_k_rate",
        "unsafe_response_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.extend([
        "",
        "## Safety contract",
        "",
        "This artifact is a read-only viewing dataset. It does not grant answer permission, claim-proof authority, or source-truth mutation permission.",
        "",
        "## Outputs",
        "",
        f"- Records JSONL: `{payload.get('records_path')}`",
        f"- Responses JSONL: `{payload.get('responses_path')}`",
    ])
    return "\n".join(lines) + "\n"


def build_dataset(
    *,
    page_retrieval_large_eval_v2: str | Path,
    profiles_path: Optional[str | Path],
    output_dir: str | Path,
    first_pages: int,
    manual_label: str,
    thresholds: Mapping[str, Any],
) -> Dict[str, Any]:
    eval_payload = load_json(page_retrieval_large_eval_v2)
    profile_payload = load_json(profiles_path) if profiles_path else {}
    records = build_page_query_response_records(eval_payload, profile_payload, first_pages=first_pages, manual_label=manual_label)
    summary = summarize(records, eval_payload)
    quality_status, checks = quality_checks(summary, thresholds)

    out_dir = Path(output_dir)
    report_path = out_dir / REPORT_NAME
    quality_path = out_dir / QUALITY_NAME
    records_path = out_dir / RECORDS_NAME
    responses_path = out_dir / RESPONSES_NAME
    markdown_path = out_dir / MARKDOWN_NAME

    response_records = [
        {
            "record_id": r.get("record_id"),
            "page_id": r.get("page_id"),
            "page_number": r.get("page_number"),
            "question": r.get("question"),
            "response": r.get("response"),
            "blank_expected": r.get("blank_expected"),
            "source_package_entry_name": (r.get("source_identity") or {}).get("source_package_entry_name"),
            "graph_path_resolved": (r.get("graph_path") or {}).get("graph_path_resolved"),
            "source_identity_resolved": (r.get("graph_path") or {}).get("source_identity_resolved"),
        }
        for r in records
    ]

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PAGE_QUERY_RESPONSE_DATASET_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "quality_checks": checks,
        "source_paths": {
            "page_retrieval_large_eval_v2": str(page_retrieval_large_eval_v2),
            "profiles_path": str(profiles_path) if profiles_path else None,
        },
        "query_response_records": records,
        "records_path": str(records_path),
        "responses_path": str(responses_path),
        "report_path": str(report_path),
        "quality_path": str(quality_path),
    }

    write_json(report_path, payload)
    write_json(quality_path, {"quality_status": quality_status, "summary": summary, "quality_checks": checks})
    write_jsonl(records_path, records)
    write_jsonl(responses_path, response_records)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def parse_thresholds(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_records": args.min_records,
        "min_responses": args.min_responses,
        "min_blank_responses": args.min_blank_responses,
        "min_graph_path_resolved": args.min_graph_path_resolved,
        "min_source_identity_resolved": args.min_source_identity_resolved,
        "min_qdrant_evaluated": args.min_qdrant_evaluated,
        "max_unsafe_responses": args.max_unsafe_responses,
        "max_answer_capable_responses": args.max_answer_capable_responses,
        "max_claim_proof_responses": args.max_claim_proof_responses,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_eval_quality_pass": args.require_eval_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-responses", type=int, default=1)
    parser.add_argument("--min-blank-responses", type=int, default=0)
    parser.add_argument("--min-graph-path-resolved", type=int, default=0)
    parser.add_argument("--min-source-identity-resolved", type=int, default=0)
    parser.add_argument("--min-qdrant-evaluated", type=int, default=0)
    parser.add_argument("--max-unsafe-responses", type=int, default=0)
    parser.add_argument("--max-answer-capable-responses", type=int, default=0)
    parser.add_argument("--max-claim-proof-responses", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-eval-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net page query/response viewing dataset v1")
    parser.add_argument("--page-retrieval-large-eval-v2", required=True)
    parser.add_argument("--profiles-path")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--first-pages", type=int, default=200)
    parser.add_argument("--manual-label", default=DEFAULT_MANUAL_LABEL)
    parser.add_argument("--quality", action="store_true")
    add_common_args(parser)
    args = parser.parse_args(argv)

    payload = build_dataset(
        page_retrieval_large_eval_v2=args.page_retrieval_large_eval_v2,
        profiles_path=args.profiles_path,
        output_dir=args.output_dir,
        first_pages=args.first_pages,
        manual_label=args.manual_label,
        thresholds=parse_thresholds(args),
    )
    summary = payload["summary"]
    print("TRACE-Net Page Query Response Dataset v1")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in [
        "record_count",
        "response_count",
        "blank_record_count",
        "blank_response_count",
        "graph_path_resolved_count",
        "source_identity_resolved_count",
        "qdrant_evaluated_record_count",
        "qdrant_target_hit_at_k_count",
        "unsafe_response_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {payload.get('report_path')}")
    print(f" quality_path: {payload.get('quality_path')}")
    return 0 if payload.get("quality_status") == "PASS" or not args.quality else 1


def check_dataset_quality(report_path: str | Path, thresholds: Mapping[str, Any], write_json_report: bool = False) -> Dict[str, Any]:
    payload = load_json(report_path)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    quality_status, checks = quality_checks(summary, thresholds)
    payload["quality_status"] = quality_status
    payload["quality_checks"] = checks
    if write_json_report:
        report = Path(report_path)
        quality_path = report.with_name(QUALITY_NAME)
        write_json(quality_path, {"quality_status": quality_status, "summary": summary, "quality_checks": checks})
    return {"quality_status": quality_status, "summary": summary, "quality_checks": checks}


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net page query/response viewing dataset v1 quality")
    parser.add_argument("--report-path", required=True)
    add_common_args(parser)
    args = parser.parse_args(argv)
    report = check_dataset_quality(args.report_path, parse_thresholds(args), write_json_report=args.write_json)
    summary = report["summary"]
    print("TRACE-Net Page Query Response Dataset v1 quality")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "record_count",
        "response_count",
        "blank_response_count",
        "graph_path_resolved_count",
        "source_identity_resolved_count",
        "qdrant_evaluated_record_count",
        "unsafe_response_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
