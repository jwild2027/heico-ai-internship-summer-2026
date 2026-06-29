"""TRACE-Net raw-to-answer context-engineered native Gemma runner v1.

This runner integrates the context-engineering chain into the raw TIFF to answer
smoke path:

raw TIFF package -> OCR/classifier pipeline -> exact part-number probe -> anchor
injection -> anchor-aware graph/Leiden expansion -> Ollama native Gemma answer.

It remains dry-run only: it audits/manifests context and calls the local LLM, but
never writes to Postgres, Qdrant, or OpenSearch and never mutates source truth.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from tiff.trace_net_raw_to_answer_e2e_smoke_native_v1 import (
    SAFE_COUNTERS_ZERO,
    _coerce_bool,
    _find_pipeline_artifacts,
    _pipeline_command,
    _read_json as _native_read_json,
    _run_subprocess,
    call_ollama_native,
)
from tiff.trace_net_part_number_exact_retrieval_probe_v1 import build_part_number_exact_retrieval_probe
from tiff.trace_net_answer_context_anchor_injector_v1 import build_answer_context_anchor_injector
from tiff.trace_net_anchor_aware_graph_leiden_expander_v1 import build_anchor_aware_graph_leiden_expander

MODULE = "trace_net_raw_to_answer_context_engineered_native_v1"
VERSION = "v1"
REPORT_NAME = f"{MODULE}.json"
SUMMARY_NAME = f"{MODULE}_summary.json"
ANSWER_NAME = f"{MODULE}_answer.md"
STAGE_JSONL_NAME = f"{MODULE}_stage_reports.jsonl"
QUALITY_CHECK_NAME = f"{MODULE}_quality_check.json"

PIPELINE_REPORT_NAME = "trace_net_ocr_classifier_pipeline_runner_v1.json"
PART_NUMBER_RE = re.compile(r"\b\d{3}[- ]\d{5}[- ]\d{3}\b")

DEFAULT_TABLE_EXACT_SEARCH_ADAPTER = Path("local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json")
DEFAULT_TABLE_EVIDENCE_PACKAGE = Path("local_data/organization/trace_net/table_route_evidence_packager/trace_net_table_route_evidence_packager_v1.json")
DEFAULT_PAGE_CONTEXT_V2 = Path("local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json")
DEFAULT_LEIDEN_COMMUNITIES = Path("local_data/organization/trace_net/leiden_communities/trace_net_leiden_communities_v1.json")
DEFAULT_COMMUNITY_AWARE_RETRIEVAL = Path("local_data/organization/trace_net/community_aware_retrieval_v2/trace_net_community_aware_retrieval_v2.json")
DEFAULT_SUPPORT_EVIDENCE_ENRICHER = Path("local_data/organization/trace_net/answer_context_evidence_enricher_gemma4_native_001/trace_net_answer_context_evidence_enricher_v1.json")
DEFAULT_SUPPORT_GRAPH_LEIDEN_EXPANDER = Path("local_data/organization/trace_net/answer_context_graph_leiden_expander_gemma4_native_001/trace_net_answer_context_graph_leiden_expander_v1.json")


def _read_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
        for key in record:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def _extract_part_numbers(question: str, explicit: Sequence[str] | None = None) -> List[str]:
    out: List[str] = []
    for value in explicit or []:
        value = str(value).strip().replace(" ", "-")
        if value and value not in out:
            out.append(value)
    for match in PART_NUMBER_RE.findall(question or ""):
        value = match.replace(" ", "-")
        if value not in out:
            out.append(value)
    return out


def _existing_or_none(path: Path | str | None) -> Optional[Path]:
    if not path:
        return None
    p = Path(path)
    return p if p.exists() else None


def _stage_status(name: str, payload: Optional[Dict[str, Any]] = None, path: Optional[Path] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    summary = (payload or {}).get("summary") or {}
    record = {
        "stage": name,
        "status": "PASS" if (payload or {}).get("quality_status") == "PASS" else (payload or {}).get("quality_status", "UNKNOWN"),
        "quality_status": (payload or {}).get("quality_status"),
        "path": str(path) if path else None,
        "summary": summary,
    }
    if extra:
        record.update(extra)
    return record


def _fallback_answer(question: str, context_payload: Dict[str, Any], llm_status: Dict[str, Any]) -> str:
    summary = context_payload.get("summary") or {}
    records = context_payload.get("records") or []
    lines = [
        "TRACE-Net context-engineered E2E draft: anchor-aware context was built, but Gemma did not return final content.",
        f"Question: {question}",
        f"LLM fallback reason: {llm_status.get('llm_fallback_reason') or llm_status.get('llm_error')}",
        "Direct exact anchors:",
    ]
    count = 0
    for rec in records:
        if rec.get("anchor_aware_role") == "direct_exact_match_anchor":
            count += 1
            lines.append(
                f"[{rec.get('citation_label')}] page={rec.get('page_number')} page_id={rec.get('page_id')} "
                f"proof={rec.get('proof_strength')} relation={rec.get('anchor_relation_type')}"
            )
            if count >= 8:
                break
    lines.append(f"Context status: direct_exact_anchor_count={summary.get('direct_exact_anchor_count')}; anchor_community_count={summary.get('anchor_community_count')}.")
    lines.append("Safety: answer_permission=false; source_truth_mutation_allowed=false; dry_run_only=true.")
    return "\n".join(lines)


def _gemma_prompt(anchor_aware_payload: Dict[str, Any]) -> str:
    prompt = anchor_aware_payload.get("llm_context_prompt") or ""
    return (
        prompt.rstrip()
        + "\n\nFINAL RESPONSE REQUIREMENTS:\n"
        + "- Return only a concise final answer in Markdown.\n"
        + "- Cite factual claims with the evidence labels like [E1].\n"
        + "- Say the part is found only when direct_exact_match_anchor/direct_exact_proof evidence exists.\n"
        + "- Mention nearby/similar parts only as related variants, not interchangeable substitutes unless evidence states that.\n"
        + "\nFinal answer:"
    )


def build_raw_to_answer_context_engineered_native(
    *,
    source_package: Path,
    tesseract_cmd: Path,
    output_dir: Path,
    question: str,
    part_numbers: Optional[Sequence[str]] = None,
    table_exact_search_adapter: Optional[Path] = None,
    table_evidence_package: Optional[Path] = None,
    page_context_v2: Optional[Path] = None,
    leiden_communities: Optional[Path] = None,
    community_aware_retrieval: Optional[Path] = None,
    graph_report: Optional[Path] = None,
    support_evidence_enricher: Optional[Path] = None,
    support_graph_leiden_expander: Optional[Path] = None,
    llm_base_url: str = "http://127.0.0.1:11434",
    llm_model: str = "gemma4:26b",
    request_timeout: int = 600,
    llm_think: bool = False,
    llm_num_predict: int = 1200,
    llm_temperature: float = 0.0,
    excerpt_window_chars: int = 1200,
    max_direct_anchors: int = 12,
    max_reference_anchors: int = 8,
    max_family_variants: int = 12,
    max_support_context: int = 8,
    max_anchor_aware_records: int = 40,
    require_source_quality_pass: bool = False,
    require_anchor_communities: bool = False,
    require_llm_success: bool = False,
    skip_pipeline_if_present: bool = False,
    quality: bool = False,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stage_records: List[Dict[str, Any]] = []

    pipeline_artifacts = _find_pipeline_artifacts(output_dir)
    if skip_pipeline_if_present and pipeline_artifacts["pipeline"].exists():
        stage_records.append({"stage": "ocr_classifier_pipeline", "status": "PASS", "action": "skip_existing", "path": str(pipeline_artifacts["pipeline"])})
    else:
        cmd = _pipeline_command(source_package=source_package, tesseract_cmd=tesseract_cmd, output_dir=output_dir, quality=True)
        stage_records.append({"stage": "ocr_classifier_pipeline", "action": "build", **_run_subprocess(cmd, timeout=None)})
        if stage_records[-1].get("status") != "PASS":
            raise RuntimeError(f"OCR/classifier pipeline failed: {stage_records[-1].get('stderr_tail')}")

    for name, path in pipeline_artifacts.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing required pipeline artifact {name}: {path}")

    pipeline_payload = _read_json(pipeline_artifacts["pipeline"])
    contract_payload = _read_json(pipeline_artifacts["contract"])
    retrieval_payload = _read_json(pipeline_artifacts["retrieval_payload_audit"])
    pipeline_summary = pipeline_payload.get("summary") or {}
    contract_summary = contract_payload.get("summary") or {}
    retrieval_summary = retrieval_payload.get("summary") or {}

    context_dir = output_dir / "context_engineering"
    context_dir.mkdir(parents=True, exist_ok=True)
    exact_probe_dir = context_dir / "part_number_exact_retrieval_probe"
    anchor_injector_dir = context_dir / "answer_context_anchor_injector"
    anchor_aware_dir = context_dir / "anchor_aware_graph_leiden_expander"
    for child_dir in (exact_probe_dir, anchor_injector_dir, anchor_aware_dir):
        child_dir.mkdir(parents=True, exist_ok=True)

    query_parts = _extract_part_numbers(question, part_numbers)

    table_exact_search_adapter = _existing_or_none(table_exact_search_adapter or DEFAULT_TABLE_EXACT_SEARCH_ADAPTER)
    table_evidence_package = _existing_or_none(table_evidence_package or DEFAULT_TABLE_EVIDENCE_PACKAGE)
    page_context_v2 = _existing_or_none(page_context_v2 or DEFAULT_PAGE_CONTEXT_V2)
    leiden_communities = _existing_or_none(leiden_communities or DEFAULT_LEIDEN_COMMUNITIES)
    community_aware_retrieval = _existing_or_none(community_aware_retrieval or DEFAULT_COMMUNITY_AWARE_RETRIEVAL)
    graph_report = _existing_or_none(graph_report)
    support_evidence_enricher = _existing_or_none(support_evidence_enricher or DEFAULT_SUPPORT_EVIDENCE_ENRICHER)
    support_graph_leiden_expander = _existing_or_none(support_graph_leiden_expander or DEFAULT_SUPPORT_GRAPH_LEIDEN_EXPANDER)

    exact_probe_payload = build_part_number_exact_retrieval_probe(
        output_dir=exact_probe_dir,
        question=question,
        part_numbers=query_parts,
        ocr_route_scan_pack=pipeline_artifacts["scan_pack"],
        table_exact_search_adapter=table_exact_search_adapter,
        table_evidence_package=table_evidence_package,
        page_context_v2=page_context_v2,
        excerpt_window_chars=excerpt_window_chars,
        require_source_quality_pass=require_source_quality_pass,
        quality=quality,
    )
    exact_probe_path = exact_probe_dir / "trace_net_part_number_exact_retrieval_probe_v1.json"
    stage_records.append(_stage_status("part_number_exact_retrieval_probe", exact_probe_payload, exact_probe_path))

    anchor_payload = build_answer_context_anchor_injector(
        part_number_exact_retrieval_probe=exact_probe_path,
        output_dir=anchor_injector_dir,
        graph_leiden_expander=support_graph_leiden_expander,
        evidence_enricher=support_evidence_enricher,
        max_direct_anchors=max_direct_anchors,
        max_reference_anchors=max_reference_anchors,
        max_family_variants=max_family_variants,
        max_support_context=max_support_context,
        require_source_quality_pass=require_source_quality_pass,
        quality=quality,
    )
    anchor_path = anchor_injector_dir / "trace_net_answer_context_anchor_injector_v1.json"
    stage_records.append(_stage_status("answer_context_anchor_injector", anchor_payload, anchor_path))

    anchor_aware_payload = build_anchor_aware_graph_leiden_expander(
        anchor_injector=anchor_path,
        leiden_communities=leiden_communities,
        community_aware_retrieval=community_aware_retrieval,
        graph_report=graph_report,
        output_dir=anchor_aware_dir,
        max_records=max_anchor_aware_records,
        require_source_quality_pass=require_source_quality_pass,
        require_anchor_communities=require_anchor_communities,
        quality=quality,
    )
    anchor_aware_path = anchor_aware_dir / "trace_net_anchor_aware_graph_leiden_expander_v1.json"
    stage_records.append(_stage_status("anchor_aware_graph_leiden_expander", anchor_aware_payload, anchor_aware_path))

    final_prompt = _gemma_prompt(anchor_aware_payload)
    llm_status = call_ollama_native(
        base_url=llm_base_url,
        model=llm_model,
        prompt=final_prompt,
        request_timeout=request_timeout,
        think=llm_think,
        num_predict=llm_num_predict,
        temperature=llm_temperature,
    )
    llm_success = llm_status.get("llm_status") == "PASS" and bool((llm_status.get("answer_text") or "").strip())
    answer_text = llm_status.get("answer_text") or _fallback_answer(question, anchor_aware_payload, llm_status)

    anchor_summary = anchor_aware_payload.get("summary") or {}
    probe_summary = exact_probe_payload.get("summary") or {}
    injector_summary = anchor_payload.get("summary") or {}

    summary: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "question": question,
        "query_part_numbers": query_parts,
        "output_dir": str(output_dir),
        "source_package": str(source_package),
        "pipeline_report": str(pipeline_artifacts["pipeline"]),
        "context_engineering_enabled": True,
        "context_engineering_mode": "exact_probe_anchor_aware_graph_leiden",
        "part_number_exact_retrieval_probe": str(exact_probe_path),
        "answer_context_anchor_injector": str(anchor_path),
        "anchor_aware_graph_leiden_expander": str(anchor_aware_path),
        "stage_count": int(pipeline_summary.get("stage_count") or 9) + 3,
        "stage_report_count": int(pipeline_summary.get("stage_report_count") or 0) + 3,
        "all_stage_quality_pass": bool(pipeline_summary.get("all_stage_quality_pass")) and all(r.get("status") == "PASS" for r in stage_records),
        "stage_quality_statuses": {**(pipeline_summary.get("stage_quality_statuses") or {}), "part_number_exact_retrieval_probe": exact_probe_payload.get("quality_status"), "answer_context_anchor_injector": anchor_payload.get("quality_status"), "anchor_aware_graph_leiden_expander": anchor_aware_payload.get("quality_status")},
        "final_validated_route_counts": pipeline_summary.get("final_validated_route_counts") or contract_summary.get("route_counts") or {},
        "postgres_contract_ready_count": contract_summary.get("postgres_contract_ready_count", 0),
        "qdrant_contract_ready_count": contract_summary.get("qdrant_contract_ready_count", 0),
        "opensearch_contract_ready_count": contract_summary.get("opensearch_contract_ready_count", 0),
        "postgres_graph_record_count": pipeline_summary.get("postgres_graph_record_count", 0),
        "qdrant_payload_count": retrieval_summary.get("qdrant_payload_count", pipeline_summary.get("qdrant_payload_count", 0)),
        "opensearch_payload_count": retrieval_summary.get("opensearch_payload_count", pipeline_summary.get("opensearch_payload_count", 0)),
        "retrieval_payload_audit_record_count": retrieval_summary.get("retrieval_payload_audit_record_count", 0),
        "lineage_ready_count": contract_summary.get("lineage_ready_count", pipeline_summary.get("lineage_ready_count", 0)),
        "missing_lineage_count": contract_summary.get("missing_lineage_count", pipeline_summary.get("missing_lineage_count", 0)),
        "violation_record_count": int(retrieval_summary.get("violation_record_count") or 0) + int(probe_summary.get("violation_record_count") or 0) + int(injector_summary.get("violation_record_count") or 0) + int(anchor_summary.get("violation_record_count") or 0),
        "route_payload_mismatch_count": retrieval_summary.get("route_payload_mismatch_count", pipeline_summary.get("route_payload_mismatch_count", 0)),
        "exact_hit_count": probe_summary.get("exact_hit_count", 0),
        "exact_direct_hit_count": probe_summary.get("exact_direct_hit_count", 0),
        "direct_exact_anchor_count": anchor_summary.get("direct_exact_anchor_count", 0),
        "direct_exact_anchor_page_count": anchor_summary.get("direct_exact_anchor_page_count", 0),
        "direct_exact_anchor_page_numbers": anchor_summary.get("direct_exact_anchor_page_numbers") or [],
        "anchor_community_count": anchor_summary.get("anchor_community_count", 0),
        "same_anchor_leiden_community_count": anchor_summary.get("same_anchor_leiden_community_count", 0),
        "anchor_aware_record_count": anchor_summary.get("anchor_aware_record_count", 0),
        "context_prompt_char_count": anchor_summary.get("context_prompt_char_count", len(final_prompt)),
        "context_citation_count": anchor_summary.get("citation_count", 0),
        "retrieval_evidence_count": anchor_summary.get("anchor_aware_record_count", 0),
        "citation_count": anchor_summary.get("citation_count", 0),
        "ready_for_gemma_anchor_aware_prompt": bool(anchor_summary.get("ready_for_gemma_anchor_aware_prompt")),
        "ready_for_answer_quality_gate": bool(anchor_summary.get("ready_for_answer_quality_gate")),
        "dry_run_only": True,
        "live_write_enabled": False,
        "llm_mode": "ollama_native",
        "require_llm_success": require_llm_success,
        "answer_draft_char_count": len(answer_text),
        **SAFE_COUNTERS_ZERO,
    }
    for key in [
        "llm_called", "llm_status", "llm_model", "llm_base_url", "llm_endpoint", "llm_response_status",
        "llm_finish_reason", "llm_fallback_reason", "llm_answer_char_count", "llm_reasoning_char_count",
        "llm_num_predict", "llm_think", "llm_temperature", "llm_elapsed_seconds", "llm_error",
    ]:
        if key in llm_status:
            summary[key] = llm_status[key]

    failures: List[str] = []
    if not summary["all_stage_quality_pass"]:
        failures.append("not all pipeline/context stages are PASS")
    if int(summary.get("direct_exact_anchor_count") or 0) < 1:
        failures.append("no direct exact anchors were injected")
    if int(summary.get("citation_count") or 0) < 1:
        failures.append("no context citations were produced")
    if int(summary.get("violation_record_count") or 0) != 0:
        failures.append("violations are present")
    if int(summary.get("missing_lineage_count") or 0) != 0:
        failures.append("missing lineage is present")
    if require_anchor_communities and int(summary.get("anchor_community_count") or 0) < 1:
        failures.append("anchor community annotations are required but missing")
    if require_llm_success and not llm_success:
        failures.append("Gemma/Ollama native LLM did not return final answer content")

    quality_status = "PASS" if not failures else "FAIL"
    payload = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_RAW_TO_ANSWER_CONTEXT_ENGINEERED_NATIVE_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "stage_records": stage_records,
        "answer_draft": {"answer_text": answer_text, "llm_generated": llm_success, "citation_count": summary.get("citation_count")},
        "llm_request_context": {
            "prompt_char_count": len(final_prompt),
            "source_context_report": str(anchor_aware_path),
            "llm_mode": "ollama_native",
            "think": llm_think,
            "num_predict": llm_num_predict,
        },
        "safety_contract": {
            "dry_run_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "graph_leiden_proves_exact_identity": False,
            "exact_source_text_proves_identity": True,
        },
    }

    _write_json(output_dir / REPORT_NAME, payload)
    _write_json(output_dir / SUMMARY_NAME, summary)
    _write_jsonl(output_dir / STAGE_JSONL_NAME, stage_records)
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
    min_stage_reports: int = 12,
    min_postgres_contract_ready: int = 509,
    min_qdrant_contract_ready: int = 400,
    min_opensearch_contract_ready: int = 250,
    min_qdrant_payloads: int = 400,
    min_opensearch_payloads: int = 250,
    min_direct_exact_anchors: int = 1,
    min_anchor_communities: int = 0,
    min_citations: int = 1,
    min_prompt_chars: int = 500,
    max_violations: int = 0,
    require_all_stage_quality_pass: bool = False,
    require_context_engineering_enabled: bool = False,
    require_anchor_aware_prompt: bool = False,
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
        ("direct_exact_anchor_count", min_direct_exact_anchors),
        ("anchor_community_count", min_anchor_communities),
        ("citation_count", min_citations),
        ("context_prompt_char_count", min_prompt_chars),
    ]
    for key, minimum in checks:
        if int(summary.get(key) or 0) < minimum:
            failures.append(f"{key} is below minimum {minimum}: {summary.get(key)}")
    if int(summary.get("violation_record_count") or 0) > max_violations:
        failures.append("violation_record_count exceeds max")
    if require_all_stage_quality_pass and not summary.get("all_stage_quality_pass"):
        failures.append("all_stage_quality_pass is not true")
    if require_context_engineering_enabled and not summary.get("context_engineering_enabled"):
        failures.append("context_engineering_enabled is not true")
    if require_anchor_aware_prompt and not summary.get("ready_for_gemma_anchor_aware_prompt"):
        failures.append("ready_for_gemma_anchor_aware_prompt is not true")
    if require_dry_run_only and not summary.get("dry_run_only"):
        failures.append("dry_run_only is not true")
    if require_no_human_review_required and (int(summary.get("human_review_required_count") or 0) != 0 or int(summary.get("manual_review_required_count") or 0) != 0):
        failures.append("human/manual review required count is nonzero")
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
        _write_json(Path(report_path).parent / QUALITY_CHECK_NAME, result)
        print(f"Wrote: {Path(report_path).parent / QUALITY_CHECK_NAME}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Run TRACE-Net context-engineered raw-to-answer native E2E.")
    parser.add_argument("--source-package", required=True, type=Path)
    parser.add_argument("--tesseract-cmd", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--question", required=True)
    parser.add_argument("--part-number", action="append", dest="part_numbers", default=[])
    parser.add_argument("--table-exact-search-adapter", type=Path, default=DEFAULT_TABLE_EXACT_SEARCH_ADAPTER)
    parser.add_argument("--table-evidence-package", type=Path, default=DEFAULT_TABLE_EVIDENCE_PACKAGE)
    parser.add_argument("--page-context-v2", type=Path, default=DEFAULT_PAGE_CONTEXT_V2)
    parser.add_argument("--leiden-communities", type=Path, default=DEFAULT_LEIDEN_COMMUNITIES)
    parser.add_argument("--community-aware-retrieval", type=Path, default=DEFAULT_COMMUNITY_AWARE_RETRIEVAL)
    parser.add_argument("--graph-report", type=Path)
    parser.add_argument("--support-evidence-enricher", type=Path, default=DEFAULT_SUPPORT_EVIDENCE_ENRICHER)
    parser.add_argument("--support-graph-leiden-expander", type=Path, default=DEFAULT_SUPPORT_GRAPH_LEIDEN_EXPANDER)
    parser.add_argument("--llm-mode", default="ollama_native", choices=["ollama_native"])
    parser.add_argument("--llm-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--llm-model", default="gemma4:26b")
    parser.add_argument("--llm-think", default="false")
    parser.add_argument("--llm-num-predict", type=int, default=1200)
    parser.add_argument("--llm-temperature", type=float, default=0.0)
    parser.add_argument("--request-timeout", type=int, default=600)
    parser.add_argument("--excerpt-window-chars", type=int, default=1200)
    parser.add_argument("--max-direct-anchors", type=int, default=12)
    parser.add_argument("--max-reference-anchors", type=int, default=8)
    parser.add_argument("--max-family-variants", type=int, default=12)
    parser.add_argument("--max-support-context", type=int, default=8)
    parser.add_argument("--max-anchor-aware-records", type=int, default=40)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-anchor-communities", action="store_true")
    parser.add_argument("--require-llm-success", action="store_true")
    parser.add_argument("--skip-pipeline-if-present", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_raw_to_answer_context_engineered_native(
        source_package=args.source_package,
        tesseract_cmd=args.tesseract_cmd,
        output_dir=args.output_dir,
        question=args.question,
        part_numbers=args.part_numbers,
        table_exact_search_adapter=args.table_exact_search_adapter,
        table_evidence_package=args.table_evidence_package,
        page_context_v2=args.page_context_v2,
        leiden_communities=args.leiden_communities,
        community_aware_retrieval=args.community_aware_retrieval,
        graph_report=args.graph_report,
        support_evidence_enricher=args.support_evidence_enricher,
        support_graph_leiden_expander=args.support_graph_leiden_expander,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
        request_timeout=args.request_timeout,
        llm_think=_coerce_bool(args.llm_think),
        llm_num_predict=args.llm_num_predict,
        llm_temperature=args.llm_temperature,
        excerpt_window_chars=args.excerpt_window_chars,
        max_direct_anchors=args.max_direct_anchors,
        max_reference_anchors=args.max_reference_anchors,
        max_family_variants=args.max_family_variants,
        max_support_context=args.max_support_context,
        max_anchor_aware_records=args.max_anchor_aware_records,
        require_source_quality_pass=args.require_source_quality_pass,
        require_anchor_communities=args.require_anchor_communities,
        require_llm_success=args.require_llm_success,
        skip_pipeline_if_present=args.skip_pipeline_if_present,
        quality=args.quality,
    )


def main_check(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net context-engineered raw-to-answer native E2E quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-stage-reports", type=int, default=12)
    parser.add_argument("--min-postgres-contract-ready", type=int, default=509)
    parser.add_argument("--min-qdrant-contract-ready", type=int, default=400)
    parser.add_argument("--min-opensearch-contract-ready", type=int, default=250)
    parser.add_argument("--min-qdrant-payloads", type=int, default=400)
    parser.add_argument("--min-opensearch-payloads", type=int, default=250)
    parser.add_argument("--min-direct-exact-anchors", type=int, default=1)
    parser.add_argument("--min-anchor-communities", type=int, default=0)
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-prompt-chars", type=int, default=500)
    parser.add_argument("--max-violations", type=int, default=0)
    parser.add_argument("--require-all-stage-quality-pass", action="store_true")
    parser.add_argument("--require-context-engineering-enabled", action="store_true")
    parser.add_argument("--require-anchor-aware-prompt", action="store_true")
    parser.add_argument("--require-dry-run-only", action="store_true")
    parser.add_argument("--require-no-human-review-required", action="store_true")
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    parser.add_argument("--require-llm-success", action="store_true")
    args = parser.parse_args(argv)
    return check_quality(**vars(args))


if __name__ == "__main__":  # pragma: no cover
    main_build()
