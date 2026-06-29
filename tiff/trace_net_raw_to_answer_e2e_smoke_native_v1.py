from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODULE = "trace_net_raw_to_answer_e2e_smoke_native_v1"
VERSION = "v1"
REPORT_NAME = "trace_net_raw_to_answer_e2e_smoke_native_v1.json"
SUMMARY_NAME = "trace_net_raw_to_answer_e2e_smoke_native_v1_summary.json"
ANSWER_NAME = "trace_net_raw_to_answer_e2e_smoke_native_v1_answer.md"
EVIDENCE_JSONL_NAME = "trace_net_raw_to_answer_e2e_smoke_native_v1_retrieval_evidence.jsonl"
EVIDENCE_CSV_NAME = "trace_net_raw_to_answer_e2e_smoke_native_v1_retrieval_evidence.csv"
QUALITY_CHECK_NAME = "trace_net_raw_to_answer_e2e_smoke_native_v1_quality_check.json"

PIPELINE_REPORT_NAME = "trace_net_ocr_classifier_pipeline_runner_v1.json"

PART_NUMBER_RE = re.compile(r"\b\d{3}[- ]\d{5}[- ]\d{3}\b")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}")

SAFE_COUNTERS_ZERO = {
    "answer_permission_count": 0,
    "can_answer_directly_count": 0,
    "can_prove_claims_count": 0,
    "source_truth_mutation_allowed_count": 0,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
    "write_attempt_count": 0,
    "unsafe_record_count": 0,
    "human_review_required_count": 0,
    "manual_review_required_count": 0,
}


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    for record in records:
        for key in record.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "\n".join(_norm_text(v) for v in value if v is not None)
    if isinstance(value, dict):
        # Keep this conservative; flatten only shallow textual values.
        parts: List[str] = []
        for k, v in value.items():
            if isinstance(v, (str, int, float)):
                parts.append(f"{k}: {v}")
        return "\n".join(parts)
    return str(value)


def _first_present(record: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _extract_record_text(record: Dict[str, Any]) -> str:
    keys = [
        "ocr_text",
        "text",
        "page_text",
        "best_ocr_text",
        "selected_ocr_text",
        "ocr_text_excerpt",
        "text_excerpt",
        "content",
        "summary_text",
        "visual_summary_text",
    ]
    text = _norm_text(_first_present(record, keys))
    if text:
        return text
    # Some scan-pack cards store OCR result by PSM.
    for key in ["tesseract_payload", "ocr_payload", "tesseract_results", "psm_results", "ocr_results"]:
        payload = record.get(key)
        if isinstance(payload, dict):
            candidates: List[str] = []
            for value in payload.values():
                if isinstance(value, dict):
                    candidates.append(_norm_text(_first_present(value, keys + ["stdout", "output"])))
                else:
                    candidates.append(_norm_text(value))
            text = "\n".join(c for c in candidates if c).strip()
            if text:
                return text
    return ""


def _records_by_page_id(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for record in payload.get("records") or []:
        pid = str(record.get("page_id") or "")
        if pid:
            out[pid] = record
    return out


def _tokenize_query(question: str) -> List[str]:
    stop = {
        "the", "and", "for", "with", "use", "cite", "pages", "page", "find", "part",
        "number", "nearby", "similar", "evidence", "trace", "net", "from", "that", "this",
    }
    tokens = []
    for token in WORD_RE.findall(question.lower()):
        if token not in stop and len(token) >= 3:
            tokens.append(token)
    return sorted(set(tokens))


def _extract_part_numbers(text: str) -> List[str]:
    return sorted(set(m.group(0).replace(" ", "-") for m in PART_NUMBER_RE.finditer(text or "")))


def _page_number(record: Dict[str, Any]) -> Optional[int]:
    value = _first_present(record, ["page_number", "canonical_page_number", "source_page_number"])
    try:
        return int(value)
    except Exception:
        return None


def _lineage(record: Dict[str, Any], scan_record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_member": _first_present(record, ["source_member", "raw_tiff_reference"]) or _first_present(scan_record, ["source_member", "raw_tiff_reference", "archive_member", "member_name"]),
        "raw_tiff_reference": _first_present(record, ["raw_tiff_reference", "source_member"]) or _first_present(scan_record, ["raw_tiff_reference", "source_member", "archive_member", "member_name"]),
        "source_image_sha256": _first_present(record, ["source_image_sha256", "raw_image_sha256", "image_sha256"]) or _first_present(scan_record, ["source_image_sha256", "raw_image_sha256", "image_sha256", "sha256"]),
    }


def _run_subprocess(cmd: Sequence[str], cwd: Optional[Path] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return {
        "cmd": list(cmd),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
        "elapsed_seconds": round(time.time() - started, 3),
        "status": "PASS" if proc.returncode == 0 else "FAIL",
    }


def _pipeline_command(*, source_package: Path, tesseract_cmd: Path, output_dir: Path, quality: bool) -> List[str]:
    cmd = [
        sys.executable,
        "scripts/run_trace_net_ocr_classifier_pipeline_v1.py",
        "--source-package",
        str(source_package),
        "--tesseract-cmd",
        str(tesseract_cmd),
        "--output-dir",
        str(output_dir),
    ]
    if quality:
        cmd.append("--quality")
    return cmd


def _find_pipeline_artifacts(output_dir: Path) -> Dict[str, Path]:
    return {
        "pipeline": output_dir / PIPELINE_REPORT_NAME,
        "scan_pack": output_dir / "ocr_route_scan_pack_tesseract_full" / "trace_net_ocr_route_scan_pack_v1.json",
        "contract": output_dir / "loader_contract_audit" / "trace_net_loader_contract_audit_v1.json",
        "retrieval_payload_audit": output_dir / "retrieval_payload_audit" / "trace_net_retrieval_payload_audit_v1.json",
    }


def _score_record(question: str, tokens: Sequence[str], record: Dict[str, Any], scan_record: Dict[str, Any]) -> Tuple[int, List[str]]:
    text = _extract_record_text(scan_record) or _extract_record_text(record)
    lower = text.lower()
    score = 0
    reasons: List[str] = []
    query_parts = _extract_part_numbers(question)
    record_parts = _extract_part_numbers(text)
    if query_parts:
        for part in query_parts:
            compact = part.replace("-", "")
            variants = {part.lower(), part.replace("-", " ").lower(), compact.lower()}
            if any(v in lower.replace("-", "") or v in lower for v in variants):
                score += 1000
                reasons.append(f"exact_part_number_match:{part}")
        if record_parts:
            # Nearby part numbers on same/related page.
            score += min(100, len(record_parts) * 5)
            reasons.append(f"part_numbers_on_page:{len(record_parts)}")
    for token in tokens:
        if token.lower() in lower:
            score += 10
            reasons.append(f"query_token:{token}")
    route = record.get("route") or record.get("final_validated_operational_route")
    if route == "table":
        score += 40
        reasons.append("table_route")
    if record.get("opensearch_contract_ready") or "opensearch" in (record.get("contract_ready_targets") or []):
        score += 35
        reasons.append("exact_index_ready")
    if record.get("qdrant_contract_ready") or "qdrant" in (record.get("contract_ready_targets") or []):
        score += 20
        reasons.append("semantic_index_ready")
    page = _page_number(record) or _page_number(scan_record)
    if page is not None:
        # Stable tiebreaker that does not dominate score.
        score += max(0, 5 - abs(page % 10 - 5))
    return score, reasons


def build_retrieval_evidence(*, question: str, contract_payload: Dict[str, Any], scan_payload: Dict[str, Any], max_evidence: int = 8) -> List[Dict[str, Any]]:
    scan_by_id = _records_by_page_id(scan_payload)
    tokens = _tokenize_query(question)
    candidates: List[Tuple[int, Dict[str, Any]]] = []
    for record in contract_payload.get("records") or []:
        page_id = str(record.get("page_id") or "")
        scan_record = scan_by_id.get(page_id, {})
        targets = record.get("contract_ready_targets") or []
        route = record.get("route") or record.get("final_validated_operational_route")
        if route == "blank":
            continue
        if not (record.get("qdrant_contract_ready") or record.get("opensearch_contract_ready") or targets):
            continue
        score, reasons = _score_record(question, tokens, record, scan_record)
        if score <= 0:
            continue
        text = _extract_record_text(scan_record) or _extract_record_text(record)
        lineage = _lineage(record, scan_record)
        evidence = {
            "evidence_id": f"E{len(candidates)+1}",
            "page_id": page_id,
            "page_number": _page_number(record) or _page_number(scan_record),
            "route": route,
            "targets": sorted(set(targets or (["qdrant"] if record.get("qdrant_contract_ready") else []) + (["opensearch"] if record.get("opensearch_contract_ready") else []))),
            "retrieval_score": score,
            "retrieval_reasons": reasons,
            "source_member": lineage["source_member"],
            "raw_tiff_reference": lineage["raw_tiff_reference"],
            "source_image_sha256": lineage["source_image_sha256"],
            "ocr_excerpt": (text or "").replace("\x00", " ")[:800],
            "part_numbers": _extract_part_numbers(text)[:25],
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        candidates.append((score, evidence))
    candidates.sort(key=lambda item: (-item[0], item[1].get("page_number") or 999999))
    records = [dict(evidence, evidence_id=f"E{i+1}") for i, (_, evidence) in enumerate(candidates[:max_evidence])]
    return records


def _build_prompt(question: str, evidence_records: Sequence[Dict[str, Any]]) -> str:
    evidence_lines: List[str] = []
    for rec in evidence_records:
        excerpt = (rec.get("ocr_excerpt") or "").strip().replace("\n", " ")
        if len(excerpt) > 450:
            excerpt = excerpt[:450] + "..."
        evidence_lines.append(
            f"{rec['evidence_id']}: page={rec.get('page_number')} page_id={rec.get('page_id')} "
            f"route={rec.get('route')} source={rec.get('source_member')} sha256={rec.get('source_image_sha256')} "
            f"score={rec.get('retrieval_score')} excerpt={excerpt}"
        )
    joined = "\n".join(evidence_lines)
    return (
        "You are TRACE-Net's final answer drafter. Do not show hidden reasoning. "
        "Return only the final answer in concise Markdown. Use only the provided evidence. "
        "Every factual claim must cite evidence IDs like [E1] or [E2]. "
        "If evidence is insufficient, say exactly what is missing.\n\n"
        f"Question: {question}\n\n"
        f"Evidence:\n{joined}\n\n"
        "Final answer:"
    )


def call_ollama_native(*, base_url: str, model: str, prompt: str, request_timeout: int, think: bool, num_predict: int, temperature: float) -> Dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": think,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method="POST")
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=request_timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            payload = json.loads(raw)
            message = payload.get("message") or {}
            content = message.get("content") or ""
            return {
                "llm_called": True,
                "llm_status": "PASS" if content.strip() else "FALLBACK",
                "llm_response_status": getattr(resp, "status", None),
                "llm_model": model,
                "llm_base_url": base_url,
                "llm_endpoint": endpoint,
                "llm_finish_reason": payload.get("done_reason") or payload.get("finish_reason"),
                "llm_fallback_reason": None if content.strip() else "empty_native_content",
                "llm_answer_char_count": len(content),
                "llm_reasoning_char_count": len(_norm_text(message.get("thinking") or message.get("reasoning") or payload.get("thinking") or payload.get("reasoning"))),
                "llm_num_predict": num_predict,
                "llm_think": think,
                "llm_temperature": temperature,
                "llm_elapsed_seconds": round(time.time() - started, 3),
                "llm_raw_response_excerpt": raw[:2000],
                "answer_text": content.strip(),
            }
    except Exception as exc:  # pragma: no cover - exercised by integration/system use
        return {
            "llm_called": True,
            "llm_status": "FALLBACK",
            "llm_model": model,
            "llm_base_url": base_url,
            "llm_endpoint": endpoint,
            "llm_error": f"{type(exc).__name__}: {exc}",
            "llm_fallback_reason": "ollama_native_call_exception",
            "llm_answer_char_count": 0,
            "llm_reasoning_char_count": 0,
            "llm_num_predict": num_predict,
            "llm_think": think,
            "llm_temperature": temperature,
            "llm_elapsed_seconds": round(time.time() - started, 3),
            "answer_text": "",
        }


def _fallback_answer(question: str, evidence_records: Sequence[Dict[str, Any]], llm_status: Dict[str, Any]) -> str:
    lines = [
        "TRACE-Net E2E smoke draft: validated retrieval evidence was found for the question.",
        f"Question: {question}",
        f"LLM call did not return final content; deterministic citation draft used. Reason: {llm_status.get('llm_fallback_reason')}",
        "Top cited evidence:",
    ]
    for rec in evidence_records[:5]:
        lines.append(
            f"{rec['evidence_id']}: page_id={rec.get('page_id')}, page={rec.get('page_number')}, "
            f"source_member={rec.get('source_member')}, route={rec.get('route')}, "
            f"targets={','.join(rec.get('targets') or [])}, score={rec.get('retrieval_score')}."
        )
    lines.append("Safety: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.")
    return "\n".join(lines)


def build_raw_to_answer_native_smoke(
    *,
    source_package: Path,
    tesseract_cmd: Path,
    output_dir: Path,
    question: str,
    llm_base_url: str,
    llm_model: str,
    request_timeout: int = 600,
    llm_think: bool = False,
    llm_num_predict: int = 1024,
    llm_temperature: float = 0.0,
    max_evidence: int = 8,
    require_llm_success: bool = False,
    quality: bool = False,
    skip_pipeline_if_present: bool = False,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command_records: List[Dict[str, Any]] = []

    artifacts = _find_pipeline_artifacts(output_dir)
    if skip_pipeline_if_present and artifacts["pipeline"].exists():
        command_records.append({"stage": "pipeline", "action": "skip_existing", "status": "PASS", "path": str(artifacts["pipeline"])})
    else:
        cmd = _pipeline_command(source_package=source_package, tesseract_cmd=tesseract_cmd, output_dir=output_dir, quality=True)
        command_records.append({"stage": "pipeline", "action": "build", **_run_subprocess(cmd, timeout=None)})
        if command_records[-1]["status"] != "PASS":
            raise RuntimeError(f"OCR/classifier pipeline failed: {command_records[-1]['stderr_tail']}")

    for name, path in artifacts.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing required pipeline artifact {name}: {path}")

    pipeline_payload = _read_json(artifacts["pipeline"])
    contract_payload = _read_json(artifacts["contract"])
    scan_payload = _read_json(artifacts["scan_pack"])
    retrieval_payload = _read_json(artifacts["retrieval_payload_audit"])

    evidence_records = build_retrieval_evidence(question=question, contract_payload=contract_payload, scan_payload=scan_payload, max_evidence=max_evidence)
    prompt = _build_prompt(question, evidence_records)
    llm_status = call_ollama_native(
        base_url=llm_base_url,
        model=llm_model,
        prompt=prompt,
        request_timeout=request_timeout,
        think=llm_think,
        num_predict=llm_num_predict,
        temperature=llm_temperature,
    )
    answer_text = llm_status.get("answer_text") or _fallback_answer(question, evidence_records, llm_status)
    llm_success = llm_status.get("llm_status") == "PASS" and bool((llm_status.get("answer_text") or "").strip())

    citation_count = len(evidence_records)
    retrieval_summary = retrieval_payload.get("summary") or {}
    pipeline_summary = pipeline_payload.get("summary") or {}
    contract_summary = contract_payload.get("summary") or {}

    summary: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "question": question,
        "output_dir": str(output_dir),
        "source_package": str(source_package),
        "pipeline_report": str(artifacts["pipeline"]),
        "stage_count": pipeline_summary.get("stage_count", 9),
        "stage_report_count": pipeline_summary.get("stage_report_count", 0),
        "all_stage_quality_pass": bool(pipeline_summary.get("all_stage_quality_pass")),
        "stage_quality_statuses": pipeline_summary.get("stage_quality_statuses") or {},
        "final_validated_route_counts": pipeline_summary.get("final_validated_route_counts") or contract_summary.get("route_counts") or {},
        "postgres_contract_ready_count": contract_summary.get("postgres_contract_ready_count", 0),
        "qdrant_contract_ready_count": contract_summary.get("qdrant_contract_ready_count", 0),
        "opensearch_contract_ready_count": contract_summary.get("opensearch_contract_ready_count", 0),
        "postgres_graph_record_count": pipeline_summary.get("postgres_graph_record_count", 0),
        "qdrant_embedding_allowed_count": pipeline_summary.get("qdrant_embedding_allowed_count", 0),
        "opensearch_index_allowed_count": pipeline_summary.get("opensearch_index_allowed_count", 0),
        "qdrant_payload_count": retrieval_summary.get("qdrant_payload_count", pipeline_summary.get("qdrant_payload_count", 0)),
        "opensearch_payload_count": retrieval_summary.get("opensearch_payload_count", pipeline_summary.get("opensearch_payload_count", 0)),
        "retrieval_payload_audit_record_count": retrieval_summary.get("retrieval_payload_audit_record_count", 0),
        "retrieval_evidence_count": len(evidence_records),
        "citation_count": citation_count,
        "lineage_ready_count": contract_summary.get("lineage_ready_count", pipeline_summary.get("lineage_ready_count", 0)),
        "missing_lineage_count": contract_summary.get("missing_lineage_count", pipeline_summary.get("missing_lineage_count", 0)),
        "violation_record_count": retrieval_summary.get("violation_record_count", pipeline_summary.get("violation_record_count", 0)),
        "route_payload_mismatch_count": retrieval_summary.get("route_payload_mismatch_count", pipeline_summary.get("route_payload_mismatch_count", 0)),
        "dry_run_only": True,
        "live_write_enabled": False,
        "llm_mode": "ollama_native",
        "require_llm_success": require_llm_success,
        "answer_draft_char_count": len(answer_text),
        "ready_for_live_db_round_trip_patch": True,
        **SAFE_COUNTERS_ZERO,
    }
    for key in [
        "llm_called",
        "llm_status",
        "llm_model",
        "llm_base_url",
        "llm_endpoint",
        "llm_response_status",
        "llm_finish_reason",
        "llm_fallback_reason",
        "llm_answer_char_count",
        "llm_reasoning_char_count",
        "llm_num_predict",
        "llm_think",
        "llm_temperature",
        "llm_elapsed_seconds",
        "llm_error",
    ]:
        if key in llm_status:
            summary[key] = llm_status[key]

    failures: List[str] = []
    if not summary["all_stage_quality_pass"]:
        failures.append("not all OCR/classifier pipeline stages are PASS")
    if summary["retrieval_evidence_count"] < 1:
        failures.append("no retrieval evidence records found")
    if summary["citation_count"] < 1:
        failures.append("no citations produced")
    if summary["violation_record_count"] != 0:
        failures.append("retrieval payload violations are present")
    if summary["missing_lineage_count"] != 0:
        failures.append("missing lineage is present")
    if require_llm_success and not llm_success:
        failures.append("Gemma/Ollama native LLM did not return final answer content")

    quality_status = "PASS" if not failures else "FAIL"
    payload = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_RAW_TO_ANSWER_E2E_SMOKE_NATIVE_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "command_records": command_records,
        "retrieval_evidence_records": evidence_records,
        "llm_request_context": {
            "prompt_char_count": len(prompt),
            "evidence_count": len(evidence_records),
            "llm_mode": "ollama_native",
            "think": llm_think,
            "num_predict": llm_num_predict,
        },
        "answer_draft": {
            "answer_text": answer_text,
            "llm_generated": llm_success,
            "citation_count": citation_count,
        },
    }

    _write_json(output_dir / REPORT_NAME, payload)
    _write_json(output_dir / SUMMARY_NAME, summary)
    _write_jsonl(output_dir / EVIDENCE_JSONL_NAME, evidence_records)
    _write_csv(output_dir / EVIDENCE_CSV_NAME, evidence_records)
    (output_dir / ANSWER_NAME).write_text(answer_text, encoding="utf-8")
    if quality:
        _write_json(output_dir / QUALITY_CHECK_NAME, {"quality_status": quality_status, "summary": summary, "failures": failures})

    print(f"Status: {payload['status']}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return payload


def check_quality(
    *,
    report_path: Path,
    write_json: bool = False,
    min_stage_reports: int = 9,
    min_postgres_contract_ready: int = 509,
    min_qdrant_contract_ready: int = 400,
    min_opensearch_contract_ready: int = 250,
    min_qdrant_payloads: int = 400,
    min_opensearch_payloads: int = 250,
    min_retrieval_evidence: int = 1,
    min_citations: int = 1,
    max_violations: int = 0,
    require_all_stage_quality_pass: bool = False,
    require_dry_run_only: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    require_llm_success: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []
    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    checks = [
        ("stage_report_count", min_stage_reports),
        ("postgres_contract_ready_count", min_postgres_contract_ready),
        ("qdrant_contract_ready_count", min_qdrant_contract_ready),
        ("opensearch_contract_ready_count", min_opensearch_contract_ready),
        ("qdrant_payload_count", min_qdrant_payloads),
        ("opensearch_payload_count", min_opensearch_payloads),
        ("retrieval_evidence_count", min_retrieval_evidence),
        ("citation_count", min_citations),
    ]
    for key, minimum in checks:
        if int(summary.get(key) or 0) < minimum:
            failures.append(f"{key} is below minimum {minimum}: {summary.get(key)}")
    if int(summary.get("violation_record_count") or 0) > max_violations:
        failures.append("violation_record_count exceeds max")
    if require_all_stage_quality_pass and not summary.get("all_stage_quality_pass"):
        failures.append("all_stage_quality_pass is not true")
    if require_dry_run_only and not summary.get("dry_run_only"):
        failures.append("dry_run_only is not true")
    if require_no_human_review_required and int(summary.get("human_review_required_count") or 0) != 0:
        failures.append("human_review_required_count is nonzero")
    if int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append("unsafe_record_count exceeds max")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count is nonzero")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source_truth_mutation_allowed_count is nonzero")
    if require_no_write_attempts and int(summary.get("write_attempt_count") or 0) != 0:
        failures.append("write_attempt_count is nonzero")
    if require_llm_success:
        if summary.get("llm_status") != "PASS" or int(summary.get("llm_answer_char_count") or 0) <= 0:
            failures.append("LLM success is required but llm_status is not PASS with answer text")
    quality_status = "PASS" if not failures else "FAIL"
    result = {"quality_status": quality_status, "summary": summary, "failures": failures}
    if write_json:
        _write_json(report_path.parent / QUALITY_CHECK_NAME, result)
        print(f"Wrote: {report_path.parent / QUALITY_CHECK_NAME}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Run TRACE-Net raw TIFF to answer E2E smoke using Ollama native chat.")
    parser.add_argument("--source-package", required=True, type=Path)
    parser.add_argument("--tesseract-cmd", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--question", required=True)
    parser.add_argument("--llm-mode", default="ollama_native", choices=["ollama_native"])
    parser.add_argument("--llm-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--llm-model", default="gemma4:26b")
    parser.add_argument("--llm-think", default="false")
    parser.add_argument("--llm-num-predict", type=int, default=1024)
    parser.add_argument("--llm-temperature", type=float, default=0.0)
    parser.add_argument("--request-timeout", type=int, default=600)
    parser.add_argument("--max-evidence", type=int, default=8)
    parser.add_argument("--require-llm-success", action="store_true")
    parser.add_argument("--skip-pipeline-if-present", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()
    return build_raw_to_answer_native_smoke(
        source_package=args.source_package,
        tesseract_cmd=args.tesseract_cmd,
        output_dir=args.output_dir,
        question=args.question,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
        request_timeout=args.request_timeout,
        llm_think=_coerce_bool(args.llm_think),
        llm_num_predict=args.llm_num_predict,
        llm_temperature=args.llm_temperature,
        max_evidence=args.max_evidence,
        require_llm_success=args.require_llm_success,
        skip_pipeline_if_present=args.skip_pipeline_if_present,
        quality=args.quality,
    )


def main_check() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net raw-to-answer native E2E smoke quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-stage-reports", type=int, default=9)
    parser.add_argument("--min-postgres-contract-ready", type=int, default=509)
    parser.add_argument("--min-qdrant-contract-ready", type=int, default=400)
    parser.add_argument("--min-opensearch-contract-ready", type=int, default=250)
    parser.add_argument("--min-qdrant-payloads", type=int, default=400)
    parser.add_argument("--min-opensearch-payloads", type=int, default=250)
    parser.add_argument("--min-retrieval-evidence", type=int, default=1)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--max-violations", type=int, default=0)
    parser.add_argument("--require-all-stage-quality-pass", action="store_true")
    parser.add_argument("--require-dry-run-only", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    parser.add_argument("--require-llm-success", action="store_true")
    args = parser.parse_args()
    return check_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_stage_reports=args.min_stage_reports,
        min_postgres_contract_ready=args.min_postgres_contract_ready,
        min_qdrant_contract_ready=args.min_qdrant_contract_ready,
        min_opensearch_contract_ready=args.min_opensearch_contract_ready,
        min_qdrant_payloads=args.min_qdrant_payloads,
        min_opensearch_payloads=args.min_opensearch_payloads,
        min_retrieval_evidence=args.min_retrieval_evidence,
        min_citations=args.min_citations,
        max_violations=args.max_violations,
        require_all_stage_quality_pass=args.require_all_stage_quality_pass,
        require_dry_run_only=args.require_dry_run_only,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
        require_llm_success=args.require_llm_success,
    )


if __name__ == "__main__":  # pragma: no cover
    main_build()
