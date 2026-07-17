#!/usr/bin/env python3
"""Run focused or full semantic evaluation through the H30 OpenWebUI endpoint."""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from scripts.trace_net_h30_part_intent_source_resolution_v1 import (
    candidate_matches_intent,
    derive_part_intent,
    identifier_is_well_formed,
)

MODULE = "trace_net_h30_phase4_3_semantic_benchmark_v1"

FOCUSED_QUERIES = (
    "Find part 120-41824-003",
    "The P/N contains 41824",
    "The P/N starts with MS49",
    "Find the 120-41824 family",
    "Find the locking ring near the seat",
)


def compact(value: Any, limit: int = 1000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def candidate_value(row: Mapping[str, Any]) -> str:
    for key in ("candidate_value", "candidate_part_number", "part_number", "value", "matched_token"):
        value = compact(row.get(key), 300)
        if value:
            return value
    return ""


def answer_text(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], Mapping) else {}
    message = first.get("message") if isinstance(first.get("message"), Mapping) else {}
    return str(message.get("content") or "").strip()


def _duplicate_answer_lines(answer: str) -> List[str]:
    seen = set()
    duplicates = []
    for raw in answer.splitlines():
        line = re.sub(r"\s+", " ", raw).strip().casefold()
        if len(line) < 24 or line.startswith("## "):
            continue
        if line in seen and line not in duplicates:
            duplicates.append(line)
        seen.add(line)
    return duplicates


def evaluate_semantic_response(
    *,
    query: str,
    status_code: int,
    response: Mapping[str, Any],
    transport_error: str = "",
) -> Dict[str, Any]:
    answer = answer_text(response)
    trace = dict(response.get("trace_net")) if isinstance(response.get("trace_net"), Mapping) else {}
    atoms = dict(trace.get("query_atoms")) if isinstance(trace.get("query_atoms"), Mapping) else {}
    envelope = dict(trace.get("evidence_envelope")) if isinstance(trace.get("evidence_envelope"), Mapping) else {}
    candidates = [dict(row) for row in envelope.get("candidate_evidence", []) if isinstance(row, Mapping)]
    direct = [dict(row) for row in envelope.get("direct_evidence", []) if isinstance(row, Mapping)]
    resolutions = [dict(row) for row in envelope.get("source_resolution", []) if isinstance(row, Mapping)]
    claim_evidence = dict(envelope.get("claim_evidence")) if isinstance(envelope.get("claim_evidence"), Mapping) else {}
    citations = [dict(row) for row in trace.get("citations", []) if isinstance(row, Mapping)]
    failures: List[str] = []
    warnings: List[str] = []

    if status_code != 200:
        failures.append(f"http_status:{status_code}")
    if transport_error:
        failures.append(f"transport_error:{transport_error}")
    if not answer:
        failures.append("empty_answer")
    if answer.startswith("{") or "TRACE-NET LIVE CONTEXT PACK" in answer:
        failures.append("internal_or_json_leak")
    if "confirmed visual guidance" in answer.lower():
        failures.append("misleading_confirmed_guidance_wording")

    duplicates = _duplicate_answer_lines(answer)
    if duplicates:
        failures.append(f"duplicated_answer_lines:{len(duplicates)}")

    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed",
    ):
        if trace.get(key) is not False:
            failures.append(f"unsafe_or_missing_false_flag:{key}")

    intent = derive_part_intent(query)
    expected_mode = str(intent.get("identifier_mode") or "none")
    actual_mode = str(atoms.get("identifier_mode") or "none")
    if expected_mode != "none" and actual_mode != expected_mode:
        failures.append(f"identifier_mode:{actual_mode}!={expected_mode}")

    for row in candidates:
        value = candidate_value(row)
        if not identifier_is_well_formed(value):
            failures.append(f"invalid_or_ocr_noise_candidate:{value}")
            continue
        if expected_mode != "none" and not candidate_matches_intent(value, intent):
            failures.append(f"candidate_violates_{expected_mode}_clue:{value}")
        if row.get("guidance_only") is not True:
            failures.append(f"candidate_not_marked_guidance:{value}")
        if row.get("final_answer_allowed") is not False:
            failures.append(f"candidate_final_answer_flag_not_false:{value}")

    if expected_mode != "none" and not resolutions:
        failures.append("missing_source_resolution_metadata")
    if any(row.get("source_truth_mutation_allowed") is not False for row in resolutions):
        failures.append("unsafe_source_resolution_record")

    citation_count = int(trace.get("citation_count") or 0)
    if citation_count != len(citations):
        failures.append(f"citation_count_mismatch:{citation_count}!={len(citations)}")
    if direct and not citations:
        failures.append("direct_evidence_without_citations")
    if citations and "[1]" not in answer:
        failures.append("citation_not_visible_in_answer")

    low = query.lower()
    requested_claim = None
    if any(term in low for term in ("nomenclature", "part name", "description", "what is it called")):
        requested_claim = "nomenclature"
    elif any(term in low for term in ("warning", "caution")):
        requested_claim = "warning_or_caution"
    elif any(term in low for term in ("approved", "effectivity", "interchange", "eligible", "safe to install")):
        requested_claim = "authority"
    elif any(term in low for term in ("procedure", "remove", "install", "steps")):
        requested_claim = "procedure_step"
    if requested_claim and direct and requested_claim not in claim_evidence:
        warnings.append(f"direct_evidence_missing_requested_claim_bucket:{requested_claim}")

    if not direct and any(term in low for term in ("approved", "effectivity", "interchange", "safe to install")):
        if not any(term in answer.lower() for term in ("not found", "did not locate", "no explicit authority", "no approval")):
            failures.append("authority_query_not_fail_closed")

    failures = list(dict.fromkeys(failures))
    warnings = list(dict.fromkeys(warnings))
    return {
        "query": query,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "route": trace.get("route"),
        "identifier_mode": actual_mode,
        "expected_identifier_mode": expected_mode,
        "candidate_count": len(candidates),
        "direct_evidence_count": len(direct),
        "citation_count": citation_count,
        "source_resolution_count": len(resolutions),
        "resolved_source_count": sum(row.get("resolution_status") == "resolved" for row in resolutions),
        "claim_evidence_buckets": sorted(claim_evidence),
        "answer": answer,
        "trace_net": trace,
    }


def post_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    query: str,
    timeout: int,
) -> Tuple[int, Dict[str, Any], float, str]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": query}],
        "temperature": 0,
        "stream": False,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8", errors="replace"))
            elapsed = round((time.perf_counter() - started) * 1000.0, 3)
            return response.status, value if isinstance(value, dict) else {}, elapsed, ""
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            value = {}
        elapsed = round((time.perf_counter() - started) * 1000.0, 3)
        return exc.code, value if isinstance(value, dict) else {}, elapsed, str(exc)
    except Exception as exc:
        elapsed = round((time.perf_counter() - started) * 1000.0, 3)
        return 599, {}, elapsed, f"{type(exc).__name__}: {exc}"


def load_queries(path: Path) -> List[Dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    rows = value.get("records") if isinstance(value, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError(f"Expected records list in {path}")
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://172.17.0.1:8131")
    parser.add_argument("--api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-v1")
    parser.add_argument("--question-bank", default="tests/data/trace_net_router_followup_question_bank_v1.json")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/h30_phase4_3_semantic_benchmark_v1")
    parser.add_argument("--request-timeout", type=int, default=1200)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--focused", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.focused:
        records = [{"question_id": f"phase43_{index:02d}", "query": query} for index, query in enumerate(FOCUSED_QUERIES, 1)]
    else:
        records = load_queries(Path(args.question_bank))
    if args.limit > 0:
        records = records[: args.limit]

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records_path = output / "records.jsonl"
    answers_path = output / "answers.txt"
    results = []

    with records_path.open("w", encoding="utf-8") as record_handle, answers_path.open("w", encoding="utf-8") as answer_handle:
        for index, record in enumerate(records, 1):
            query = str(record.get("query") or "")
            qid = str(record.get("question_id") or f"q{index:03d}")
            print(f"[{index}/{len(records)}] USER {qid} {query[:180]}", flush=True)
            status, response, latency, error = post_chat(
                base_url=args.base_url,
                api_key=args.api_key,
                model=args.model,
                query=query,
                timeout=args.request_timeout,
            )
            result = evaluate_semantic_response(
                query=query,
                status_code=status,
                response=response,
                transport_error=error,
            )
            result.update({
                "question_id": qid,
                "category": record.get("category"),
                "latency_ms": latency,
                "http_status": status,
            })
            results.append(result)
            record_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            record_handle.flush()
            answer_handle.write(f"===== {qid} =====\nQUERY: {query}\n\n{result['answer']}\n\n")
            answer_handle.flush()
            print(
                f"[{index}/{len(records)}] {result['quality_status']} route={result['route']} "
                f"mode={result['identifier_mode']} candidates={result['candidate_count']} "
                f"direct={result['direct_evidence_count']} citations={result['citation_count']} "
                f"latency_ms={latency:.1f}",
                flush=True,
            )
            if status == 599 and not args.continue_on_error:
                break

    failed = [row for row in results if row["quality_status"] != "PASS"]
    summary = {
        "module": MODULE,
        "quality_status": "PASS" if not failed and len(results) == len(records) else "FAIL",
        "requested_record_count": len(records),
        "completed_record_count": len(results),
        "pass_count": len(results) - len(failed),
        "fail_count": len(failed),
        "route_counts": dict(Counter(str(row.get("route") or "unknown") for row in results)),
        "identifier_mode_counts": dict(Counter(str(row.get("identifier_mode") or "none") for row in results)),
        "failure_counts": dict(Counter(item for row in failed for item in row.get("failures", []))),
        "records_path": str(records_path),
        "answers_path": str(answers_path),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
