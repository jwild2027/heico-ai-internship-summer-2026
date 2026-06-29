"""TRACE-Net raw TIFF to answer E2E smoke runner v1.

This module is intentionally dry-run first. It can orchestrate the raw OCR/classifier
pipeline and then performs a local artifact-backed retrieval + answer draft over the
resulting payload audit artifacts. It does not write to Postgres, Qdrant, or OpenSearch.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib import request as urlrequest

MODULE = "trace_net_raw_to_answer_e2e_smoke_v1"
VERSION = "v1"
DEFAULT_MODEL = "gemma4:26b"

ROUTE_ORDER = ["blank", "plain_text", "table", "image"]


def _read_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path | str, payload: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path | str, rows: Iterable[Dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_csv(path: Path | str, rows: Sequence[Dict[str, Any]]) -> None:
    import csv

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return value


def _safe_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def _count_truthy(rows: Sequence[Dict[str, Any]], key: str) -> int:
    return sum(1 for row in rows if row.get(key))


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-_/]{1,}", text or "")]


def _part_numbers(text: str) -> List[str]:
    # Conservative technical-manual part number shape. Keeps this generic but useful.
    seen = []
    for match in re.findall(r"\b\d{2,4}[- ][A-Z0-9]{2,8}[- ][A-Z0-9]{2,8}\b", text or "", flags=re.I):
        normalized = match.replace(" ", "-").upper()
        if normalized not in seen:
            seen.append(normalized)
    return seen


def _record_text(record: Dict[str, Any]) -> str:
    for key in (
        "ocr_text",
        "best_ocr_text",
        "combined_ocr_text",
        "page_text",
        "text",
        "ocr_sample_text",
        "sample_text",
        "visual_summary_text",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    # Some scan records keep text inside nested OCR payloads.
    for key in ("tesseract_payload", "ocr_payload", "best_tesseract_payload"):
        value = record.get(key)
        if isinstance(value, dict):
            for nested_key in ("text", "ocr_text", "stdout", "best_text"):
                nested = value.get(nested_key)
                if isinstance(nested, str) and nested.strip():
                    return nested
    return ""


def _page_number_from_id(page_id: str) -> Optional[int]:
    m = re.search(r"p(\d{6})$", page_id or "")
    return int(m.group(1)) if m else None


def _key(page_id: Optional[str], page_number: Optional[int]) -> str:
    if page_id:
        return str(page_id)
    return f"page_number:{page_number}"


def _index_by_page(records: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in records:
        page_id = row.get("page_id")
        page_number = row.get("page_number") or row.get("canonical_page_number")
        out[_key(page_id, page_number)] = row
    return out


@dataclass(frozen=True)
class StagePaths:
    output_dir: Path

    @property
    def pipeline_report(self) -> Path:
        return self.output_dir / "trace_net_ocr_classifier_pipeline_runner_v1.json"

    @property
    def ocr_scan_pack(self) -> Path:
        return self.output_dir / "ocr_route_scan_pack_tesseract_full" / "trace_net_ocr_route_scan_pack_v1.json"

    @property
    def retrieval_payload_audit(self) -> Path:
        return self.output_dir / "retrieval_payload_audit" / "trace_net_retrieval_payload_audit_v1.json"

    @property
    def storage_gate(self) -> Path:
        return self.output_dir / "four_route_storage_gate" / "trace_net_four_route_storage_gate_v1.json"

    @property
    def loader_contract_audit(self) -> Path:
        return self.output_dir / "loader_contract_audit" / "trace_net_loader_contract_audit_v1.json"


def build_pipeline_command(
    *,
    source_package: Path,
    tesseract_cmd: Path,
    output_dir: Path,
    quality: bool = True,
) -> List[str]:
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


def run_command(cmd: Sequence[str], *, cwd: Optional[Path] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
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
        "command": list(cmd),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-6000:],
        "stderr_tail": (proc.stderr or "")[-6000:],
        "elapsed_seconds": round(time.time() - started, 3),
        "status": "PASS" if proc.returncode == 0 else "FAIL",
    }


def _load_artifacts(paths: StagePaths) -> Dict[str, Dict[str, Any]]:
    required = {
        "pipeline": paths.pipeline_report,
        "ocr": paths.ocr_scan_pack,
        "retrieval_payload_audit": paths.retrieval_payload_audit,
        "storage": paths.storage_gate,
        "contract": paths.loader_contract_audit,
    }
    artifacts: Dict[str, Dict[str, Any]] = {}
    missing = []
    for name, path in required.items():
        if not path.exists():
            missing.append({"name": name, "path": str(path)})
        else:
            artifacts[name] = _read_json(path)
    if missing:
        raise FileNotFoundError(f"Missing required E2E artifacts: {missing}")
    return artifacts


def _candidate_score(query: str, row: Dict[str, Any], scan_record: Optional[Dict[str, Any]]) -> Tuple[int, List[str]]:
    q_tokens = set(_tokens(query))
    q_parts = set(_part_numbers(query))
    text = _record_text(scan_record or {})
    joined = " ".join(
        str(row.get(k) or "")
        for k in (
            "page_id",
            "raw_tiff_reference",
            "source_member",
            "route",
            "storage_decision",
            "payload_id",
        )
    )
    haystack = f"{joined}\n{text}".lower()
    score = 0
    reasons: List[str] = []

    for part in q_parts:
        if part.lower() in haystack:
            score += 100
            reasons.append(f"matched_part_number:{part}")

    overlap = sorted(t for t in q_tokens if len(t) >= 3 and t in haystack)
    if overlap:
        score += min(40, len(overlap) * 5)
        reasons.append("matched_query_terms:" + ",".join(overlap[:8]))

    route = row.get("route")
    if route == "table" and (q_parts or any(t in q_tokens for t in ("part", "parts", "number", "similar", "item"))):
        score += 25
        reasons.append("table_route_relevant_to_part_query")
    if route == "plain_text" and any(t in q_tokens for t in ("procedure", "description", "manual", "warning")):
        score += 20
        reasons.append("plain_text_route_relevant_to_text_query")
    if route == "image" and any(t in q_tokens for t in ("figure", "image", "diagram", "callout")):
        score += 20
        reasons.append("image_route_relevant_to_visual_query")

    part_count = row.get("part_number_count")
    if isinstance(part_count, int) and part_count > 0:
        score += min(20, part_count // 3)
        reasons.append(f"part_number_density:{part_count}")

    return score, reasons


def local_retrieve(
    *,
    question: str,
    retrieval_payload: Dict[str, Any],
    ocr_payload: Dict[str, Any],
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    qdrant = retrieval_payload.get("qdrant_payload_audit_records") or []
    opensearch = retrieval_payload.get("opensearch_payload_audit_records") or []
    scan_records = ocr_payload.get("records") or []
    scan_by_page = _index_by_page(scan_records)

    combined: Dict[str, Dict[str, Any]] = {}
    for target_name, rows in (("qdrant", qdrant), ("opensearch", opensearch)):
        for row in rows:
            page_key = _key(row.get("page_id"), row.get("page_number"))
            current = combined.setdefault(
                page_key,
                {
                    "page_id": row.get("page_id"),
                    "page_number": row.get("page_number"),
                    "route": row.get("route"),
                    "source_member": row.get("source_member"),
                    "raw_tiff_reference": row.get("raw_tiff_reference"),
                    "source_image_sha256": row.get("source_image_sha256"),
                    "storage_decision": row.get("storage_decision"),
                    "targets": [],
                    "payload_ids": [],
                    "part_number_count": row.get("part_number_count", 0),
                    "ocr_char_count": row.get("ocr_char_count", 0),
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                },
            )
            if target_name not in current["targets"]:
                current["targets"].append(target_name)
            if row.get("payload_id"):
                current["payload_ids"].append(row.get("payload_id"))
            if isinstance(row.get("part_number_count"), int):
                current["part_number_count"] = max(current.get("part_number_count") or 0, row["part_number_count"])
            if isinstance(row.get("ocr_char_count"), int):
                current["ocr_char_count"] = max(current.get("ocr_char_count") or 0, row["ocr_char_count"])

    scored: List[Dict[str, Any]] = []
    for page_key, row in combined.items():
        scan_record = scan_by_page.get(page_key)
        score, reasons = _candidate_score(question, row, scan_record)
        if score <= 0:
            continue
        text = _record_text(scan_record or {})
        row = dict(row)
        row.update(
            {
                "retrieval_score": score,
                "retrieval_reasons": reasons,
                "ocr_excerpt": _excerpt(text, max_chars=420),
                "citation": {
                    "page_id": row.get("page_id"),
                    "page_number": row.get("page_number"),
                    "source_member": row.get("source_member"),
                    "source_image_sha256": row.get("source_image_sha256"),
                },
            }
        )
        scored.append(row)

    scored.sort(key=lambda r: (-int(r.get("retrieval_score") or 0), int(r.get("page_number") or 999999)))
    return scored[:top_k]


def _excerpt(text: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def build_answer_draft(
    *,
    question: str,
    evidence: Sequence[Dict[str, Any]],
    llm_mode: str = "local_draft",
    llm_base_url: str = "http://127.0.0.1:11434/v1",
    llm_model: str = DEFAULT_MODEL,
    llm_api_key: str = "ollama",
    request_timeout: int = 120,
    llm_max_tokens: int = 1024,
) -> Tuple[str, Dict[str, Any]]:
    if llm_mode == "ollama_openai":
        prompt = _answer_prompt(question, evidence)
        llm_result = _call_openai_compatible(
            base_url=llm_base_url,
            model=llm_model,
            api_key=llm_api_key,
            prompt=prompt,
            timeout=request_timeout,
            max_tokens=llm_max_tokens,
        )
        if llm_result.get("ok") and llm_result.get("content"):
            return str(llm_result["content"]), {"llm_called": True, "llm_status": "PASS", **llm_result}
        # Fail closed into deterministic draft rather than losing the smoke result.
        draft = _deterministic_answer(question, evidence, llm_note="LLM call failed; deterministic citation draft used.")
        return draft, {"llm_called": True, "llm_status": "FALLBACK", **llm_result}

    return _deterministic_answer(question, evidence), {"llm_called": False, "llm_status": "not_requested"}


def _answer_prompt(question: str, evidence: Sequence[Dict[str, Any]]) -> str:
    evidence_lines = []
    for idx, row in enumerate(evidence, start=1):
        citation = row.get("citation") or {}
        evidence_lines.append(
            json.dumps(
                {
                    "citation_id": f"E{idx}",
                    "page_id": citation.get("page_id"),
                    "page_number": citation.get("page_number"),
                    "source_member": citation.get("source_member"),
                    "route": row.get("route"),
                    "targets": row.get("targets"),
                    "excerpt": row.get("ocr_excerpt"),
                },
                sort_keys=True,
            )
        )
    return (
        "You are drafting a TRACE-Net citation-backed answer. Use only the supplied evidence. "
        "Do not claim source-truth mutation or answer permission. If evidence is weak, say so.\n\n"
        f"Question: {question}\n\nEvidence:\n" + "\n".join(evidence_lines)
    )


def _call_openai_compatible(*, base_url: str, model: str, api_key: str, prompt: str, timeout: int, max_tokens: int = 1024) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are TRACE-Net's E2E smoke answer drafter."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    data = json.dumps(body).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content")
        reasoning = message.get("reasoning")
        finish_reason = choice.get("finish_reason")
        result = {
            "ok": bool(isinstance(content, str) and content.strip()),
            "content": content if isinstance(content, str) else None,
            "raw_status": "response_received",
            "llm_model": payload.get("model") or model,
            "llm_base_url": base_url,
            "llm_finish_reason": finish_reason,
            "llm_reasoning_char_count": len(reasoning) if isinstance(reasoning, str) else 0,
            "llm_content_char_count": len(content) if isinstance(content, str) else 0,
            "llm_max_tokens": max_tokens,
        }
        if not result["ok"]:
            if isinstance(reasoning, str) and reasoning.strip() and finish_reason == "length":
                result["llm_fallback_reason"] = "empty_content_reasoning_truncated_increase_llm_max_tokens"
            elif isinstance(reasoning, str) and reasoning.strip():
                result["llm_fallback_reason"] = "empty_content_reasoning_only"
            else:
                result["llm_fallback_reason"] = "empty_content"
        return result
    except Exception as exc:  # pragma: no cover - local runtime dependent
        return {
            "ok": False,
            "content": None,
            "error": f"{type(exc).__name__}: {exc}",
            "llm_model": model,
            "llm_base_url": base_url,
            "llm_max_tokens": max_tokens,
            "llm_fallback_reason": "exception",
        }


def _deterministic_answer(question: str, evidence: Sequence[Dict[str, Any]], llm_note: Optional[str] = None) -> str:
    if not evidence:
        return (
            "TRACE-Net E2E smoke draft: no validated retrieval evidence matched the question. "
            "No answer is authorized from the current retrieval payloads."
        )
    lines = [
        "TRACE-Net E2E smoke draft: validated retrieval evidence was found for the question.",
        f"Question: {question}",
    ]
    if llm_note:
        lines.append(llm_note)
    lines.append("Top cited evidence:")
    for idx, row in enumerate(evidence[:5], start=1):
        citation = row.get("citation") or {}
        lines.append(
            f"E{idx}: page_id={citation.get('page_id')}, page={citation.get('page_number')}, "
            f"source_member={citation.get('source_member')}, route={row.get('route')}, "
            f"targets={','.join(row.get('targets') or [])}, score={row.get('retrieval_score')}."
        )
    lines.append("Safety: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.")
    return "\n".join(lines)


def build_raw_to_answer_e2e_smoke(
    *,
    source_package: Path,
    tesseract_cmd: Path,
    output_dir: Path,
    question: str,
    route_label_taxonomy: Path = Path("local_data/organization/trace_net/route_label_taxonomy/trace_net_route_label_taxonomy_v1.json"),
    top_k: int = 8,
    skip_pipeline: bool = False,
    quality: bool = False,
    llm_mode: str = "local_draft",
    llm_base_url: str = "http://127.0.0.1:11434/v1",
    llm_model: str = DEFAULT_MODEL,
    llm_api_key: str = "ollama",
    request_timeout: int = 240,
    llm_max_tokens: int = 1024,
    require_llm_success: bool = False,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = StagePaths(output_dir=output_dir)

    command_records: List[Dict[str, Any]] = []
    if not skip_pipeline:
        cmd = build_pipeline_command(
            source_package=Path(source_package),
            tesseract_cmd=Path(tesseract_cmd),
            output_dir=output_dir,
            quality=True,
        )
        command_records.append({"stage": "ocr_classifier_pipeline", "command": cmd})
        result = run_command(cmd, timeout=max(request_timeout, 240) * 10)
        command_records[-1].update(result)
        if result["returncode"] != 0:
            payload = _failure_payload(
                output_dir=output_dir,
                question=question,
                command_records=command_records,
                error="pipeline_runner_failed",
            )
            _write_outputs(output_dir, payload)
            return payload

    artifacts = _load_artifacts(paths)
    pipeline_summary = _safe_summary(artifacts["pipeline"])
    retrieval_summary = _safe_summary(artifacts["retrieval_payload_audit"])
    storage_summary = _safe_summary(artifacts["storage"])
    contract_summary = _safe_summary(artifacts["contract"])

    evidence = local_retrieve(
        question=question,
        retrieval_payload=artifacts["retrieval_payload_audit"],
        ocr_payload=artifacts["ocr"],
        top_k=top_k,
    )
    answer_text, llm_result = build_answer_draft(
        question=question,
        evidence=evidence,
        llm_mode=llm_mode,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        request_timeout=request_timeout,
        llm_max_tokens=llm_max_tokens,
    )

    citation_count = sum(1 for row in evidence if row.get("citation", {}).get("page_id"))
    stage_quality_statuses = pipeline_summary.get("stage_quality_statuses") or {}
    all_stage_quality_pass = bool(pipeline_summary.get("all_stage_quality_pass"))

    summary: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "question": question,
        "output_dir": str(output_dir),
        "source_package": str(source_package),
        "pipeline_report": str(paths.pipeline_report),
        "all_stage_quality_pass": all_stage_quality_pass,
        "stage_count": pipeline_summary.get("stage_count", 0),
        "stage_report_count": pipeline_summary.get("stage_report_count", 0),
        "stage_quality_statuses": stage_quality_statuses,
        "final_validated_route_counts": storage_summary.get("final_validated_route_counts", {}),
        "postgres_graph_record_count": storage_summary.get("postgres_graph_record_count", 0),
        "postgres_contract_ready_count": contract_summary.get("postgres_contract_ready_count", 0),
        "qdrant_embedding_allowed_count": storage_summary.get("qdrant_embedding_allowed_count", 0),
        "qdrant_payload_count": retrieval_summary.get("qdrant_payload_count", 0),
        "qdrant_contract_ready_count": contract_summary.get("qdrant_contract_ready_count", 0),
        "opensearch_index_allowed_count": storage_summary.get("opensearch_index_allowed_count", 0),
        "opensearch_payload_count": retrieval_summary.get("opensearch_payload_count", 0),
        "opensearch_contract_ready_count": contract_summary.get("opensearch_contract_ready_count", 0),
        "lineage_ready_count": contract_summary.get("lineage_ready_count", 0),
        "missing_lineage_count": contract_summary.get("missing_lineage_count", 0),
        "retrieval_evidence_count": len(evidence),
        "citation_count": citation_count,
        "answer_draft_char_count": len(answer_text),
        "llm_mode": llm_mode,
        "llm_called": bool(llm_result.get("llm_called")),
        "llm_status": llm_result.get("llm_status"),
        "llm_model": llm_result.get("llm_model") or llm_model,
        "llm_base_url": llm_result.get("llm_base_url") or llm_base_url,
        "llm_answer_char_count": int(llm_result.get("llm_content_char_count") or len(str(llm_result.get("content") or ""))),
        "llm_finish_reason": llm_result.get("llm_finish_reason"),
        "llm_fallback_reason": llm_result.get("llm_fallback_reason"),
        "llm_reasoning_char_count": int(llm_result.get("llm_reasoning_char_count") or 0),
        "llm_max_tokens": llm_max_tokens,
        "require_llm_success": require_llm_success,
        "dry_run_only": True,
        "live_write_enabled": False,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "write_attempt_count": 0,
        "human_review_required_count": 0,
        "unsafe_record_count": 0,
        "violation_record_count": retrieval_summary.get("violation_record_count", 0),
        "route_payload_mismatch_count": retrieval_summary.get("route_payload_mismatch_count", 0),
        "ready_for_live_db_round_trip_patch": bool(citation_count and all_stage_quality_pass),
    }

    payload: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_RAW_TO_ANSWER_E2E_SMOKE_BUILT",
        "quality_status": "PASS" if _quality_pass(summary, require_llm_success=require_llm_success) else "FAIL",
        "summary": summary,
        "command_records": command_records,
        "retrieval_evidence_records": evidence,
        "answer_draft": {
            "question": question,
            "answer_text": answer_text,
            "citation_count": citation_count,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "dry_run_only": True,
        },
        "llm_result": llm_result,
        "safety": {
            "dry_run_only": True,
            "live_write_enabled": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }
    if quality and payload["quality_status"] != "PASS":
        payload["quality_failures"] = _quality_failures(summary, require_llm_success=require_llm_success)
    _write_outputs(output_dir, payload)
    return payload


def _quality_pass(summary: Dict[str, Any], *, require_llm_success: bool = False) -> bool:
    return not _quality_failures(summary, require_llm_success=require_llm_success)


def _quality_failures(summary: Dict[str, Any], *, require_llm_success: bool = False) -> List[str]:
    failures = []
    if not summary.get("all_stage_quality_pass"):
        failures.append("not all pipeline stages passed")
    if int(summary.get("stage_report_count") or 0) < 9:
        failures.append("stage_report_count below 9")
    if int(summary.get("postgres_contract_ready_count") or 0) < 509:
        failures.append("postgres_contract_ready_count below 509")
    if int(summary.get("qdrant_contract_ready_count") or 0) < 400:
        failures.append("qdrant_contract_ready_count below 400")
    if int(summary.get("opensearch_contract_ready_count") or 0) < 250:
        failures.append("opensearch_contract_ready_count below 250")
    if int(summary.get("qdrant_payload_count") or 0) < 400:
        failures.append("qdrant_payload_count below 400")
    if int(summary.get("opensearch_payload_count") or 0) < 250:
        failures.append("opensearch_payload_count below 250")
    if int(summary.get("retrieval_evidence_count") or 0) < 1:
        failures.append("retrieval_evidence_count below 1")
    if int(summary.get("citation_count") or 0) < 1:
        failures.append("citation_count below 1")
    for key in (
        "missing_lineage_count",
        "violation_record_count",
        "route_payload_mismatch_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "write_attempt_count",
        "human_review_required_count",
        "unsafe_record_count",
    ):
        if int(summary.get(key) or 0) != 0:
            failures.append(f"{key} is not zero")
    if not summary.get("dry_run_only"):
        failures.append("dry_run_only is false")
    if summary.get("live_write_enabled"):
        failures.append("live_write_enabled is true")
    if require_llm_success:
        if summary.get("llm_status") != "PASS":
            failures.append("llm_status is not PASS")
        if int(summary.get("llm_answer_char_count") or 0) <= 0:
            failures.append("llm_answer_char_count is zero")
    return failures


def _failure_payload(*, output_dir: Path, question: str, command_records: List[Dict[str, Any]], error: str) -> Dict[str, Any]:
    summary = {
        "module": MODULE,
        "version": VERSION,
        "question": question,
        "output_dir": str(output_dir),
        "error": error,
        "all_stage_quality_pass": False,
        "dry_run_only": True,
        "live_write_enabled": False,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0,
        "human_review_required_count": 0,
        "unsafe_record_count": 0,
    }
    return {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_RAW_TO_ANSWER_E2E_SMOKE_ERROR",
        "quality_status": "FAIL",
        "summary": summary,
        "command_records": command_records,
        "retrieval_evidence_records": [],
        "answer_draft": {"question": question, "answer_text": "", "citation_count": 0},
        "quality_failures": _quality_failures(summary),
    }


def _write_outputs(output_dir: Path, payload: Dict[str, Any]) -> None:
    report_path = output_dir / "trace_net_raw_to_answer_e2e_smoke_v1.json"
    _write_json(report_path, payload)
    _write_json(output_dir / "trace_net_raw_to_answer_e2e_smoke_v1_summary.json", payload.get("summary", {}))
    _write_jsonl(output_dir / "trace_net_raw_to_answer_e2e_smoke_v1_retrieval_evidence.jsonl", payload.get("retrieval_evidence_records") or [])
    _write_jsonl(output_dir / "trace_net_raw_to_answer_e2e_smoke_v1_command_records.jsonl", payload.get("command_records") or [])
    _write_csv(output_dir / "trace_net_raw_to_answer_e2e_smoke_v1_retrieval_evidence.csv", payload.get("retrieval_evidence_records") or [])
    answer = payload.get("answer_draft", {}).get("answer_text", "")
    (output_dir / "trace_net_raw_to_answer_e2e_smoke_v1_answer.md").write_text(answer, encoding="utf-8")
    # Keep quality check colocated for the same UX as other modules.
    _write_json(output_dir / "trace_net_raw_to_answer_e2e_smoke_v1_quality_check.json", {
        "quality_status": payload.get("quality_status"),
        "summary": payload.get("summary", {}),
        "failures": payload.get("quality_failures", []),
    })


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
    max_unsafe: Optional[int] = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    require_llm_success: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = _safe_summary(payload)
    failures: List[str] = []

    if int(summary.get("stage_report_count") or 0) < min_stage_reports:
        failures.append(f"stage_report_count below minimum {min_stage_reports}")
    if int(summary.get("postgres_contract_ready_count") or 0) < min_postgres_contract_ready:
        failures.append(f"postgres_contract_ready_count below minimum {min_postgres_contract_ready}")
    if int(summary.get("qdrant_contract_ready_count") or 0) < min_qdrant_contract_ready:
        failures.append(f"qdrant_contract_ready_count below minimum {min_qdrant_contract_ready}")
    if int(summary.get("opensearch_contract_ready_count") or 0) < min_opensearch_contract_ready:
        failures.append(f"opensearch_contract_ready_count below minimum {min_opensearch_contract_ready}")
    if int(summary.get("qdrant_payload_count") or 0) < min_qdrant_payloads:
        failures.append(f"qdrant_payload_count below minimum {min_qdrant_payloads}")
    if int(summary.get("opensearch_payload_count") or 0) < min_opensearch_payloads:
        failures.append(f"opensearch_payload_count below minimum {min_opensearch_payloads}")
    if int(summary.get("retrieval_evidence_count") or 0) < min_retrieval_evidence:
        failures.append(f"retrieval_evidence_count below minimum {min_retrieval_evidence}")
    if int(summary.get("citation_count") or 0) < min_citations:
        failures.append(f"citation_count below minimum {min_citations}")
    if int(summary.get("violation_record_count") or 0) > max_violations:
        failures.append(f"violation_record_count above maximum {max_violations}")
    if require_all_stage_quality_pass and not summary.get("all_stage_quality_pass"):
        failures.append("all_stage_quality_pass is not true")
    if require_dry_run_only and not summary.get("dry_run_only"):
        failures.append("dry_run_only is not true")
    if require_no_human_review_required and int(summary.get("human_review_required_count") or 0) != 0:
        failures.append("human_review_required_count is not zero")
    if max_unsafe is not None and int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append(f"unsafe_record_count above maximum {max_unsafe}")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count is not zero")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source_truth_mutation_allowed_count is not zero")
    if require_no_write_attempts and int(summary.get("write_attempt_count") or 0) != 0:
        failures.append("write_attempt_count is not zero")
    if require_llm_success:
        if summary.get("llm_status") != "PASS":
            failures.append("llm_status is not PASS")
        if int(summary.get("llm_answer_char_count") or 0) <= 0:
            failures.append("llm_answer_char_count is zero")

    result = {
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "failures": failures,
    }
    if write_json:
        out = Path(report_path).with_name(Path(report_path).stem + "_quality_check.json")
        _write_json(out, result)
        print(f"Wrote: {out}")
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Run TRACE-Net raw TIFF to answer E2E smoke.")
    parser.add_argument("--source-package", required=True, type=Path)
    parser.add_argument("--tesseract-cmd", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--question", default="Find part number 120-29073-001 and nearby similar parts. Use TRACE-Net evidence and cite pages.")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--skip-pipeline", action="store_true")
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--llm-mode", choices=["local_draft", "ollama_openai"], default="local_draft")
    parser.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--llm-model", default=DEFAULT_MODEL)
    parser.add_argument("--llm-api-key", default="ollama")
    parser.add_argument("--request-timeout", type=int, default=240)
    parser.add_argument("--llm-max-tokens", type=int, default=1024)
    parser.add_argument("--require-llm-success", action="store_true")
    args = parser.parse_args(argv)

    payload = build_raw_to_answer_e2e_smoke(
        source_package=args.source_package,
        tesseract_cmd=args.tesseract_cmd,
        output_dir=args.output_dir,
        question=args.question,
        top_k=args.top_k,
        skip_pipeline=args.skip_pipeline,
        quality=args.quality,
        llm_mode=args.llm_mode,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
        llm_api_key=args.llm_api_key,
        request_timeout=args.request_timeout,
        llm_max_tokens=args.llm_max_tokens,
        require_llm_success=args.require_llm_success,
    )
    print(f"Status: {payload['status']}")
    print(f"Quality status: {payload['quality_status']}")
    print("Summary:", json.dumps(payload.get("summary", {}), sort_keys=True))
    return payload


def main_check(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net raw to answer E2E smoke quality.")
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
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    parser.add_argument("--require-llm-success", action="store_true")
    args = parser.parse_args(argv)
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
