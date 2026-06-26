
"""TRACE-Net Engineering WebUI Answer Server v1.3.

Small quality layer over v1/v1.2 server.

v1.3 fixes the remaining weak spot from the v1.2 rerun:
- if Gemma4 returns empty on artifact-search questions, fallback is now a clean
  deterministic mini-answer instead of raw page-lead text
- repair/material/table pages are summarized as "what TRACE-Net found"
- visible source notes are always included
- keeps exact lookup and random page behavior from v1.2
"""

from __future__ import annotations

import argparse
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from tiff.trace_net_engineering_webui_answer_server_v1 import (
    DEFAULT_FINAL_GATE,
    DEFAULT_FISHNET,
    DEFAULT_PAGE_CONTEXT,
    DEFAULT_ROUTE_HANDOFF,
    DEFAULT_RUNNER,
    LLMConfig,
    MODEL_ID,
    _add_llm_args,
    _clean_trace_text,
    _compose_with_llm,
    _extractive_summary,
    _llm_config_from_args,
    _part_numbers,
    _read_json,
    _records_from_payload,
    _response_record,
    _search_pages,
    _source_notes,
    _write_json,
    _write_jsonl,
    answer_gated_lookup,
    answer_random_page_summary,
    answer_v2_summary_inventory,
    load_gated_drafts,
    load_page_index,
)


MODULE_VERSION = "trace_net_engineering_webui_answer_server_v1_3"
REPORT_NAME = "trace_net_engineering_webui_answer_server_v1_3.json"


def _query_type(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ["repair", "doubler", "rivet", "fastener", "leg"]):
        return "repair_materials"
    if any(w in q for w in ["diagram", "visual", "callout", "figure", "looks like"]):
        return "visual_or_figure_leads"
    if any(w in q for w in ["nomenclature", "part number", "lateral structure", "assy", "assembly"]):
        return "parts_list"
    return "artifact_search"


def _extract_key_terms(text: str) -> List[str]:
    cleaned = _clean_trace_text(text, max_chars=1400)
    terms = []

    # Preserve part numbers and material/procedure phrases.
    for part in sorted(set(re.findall(r"\b\d{3}-\d{5}-\d{3}\b", cleaned))):
        terms.append(part)

    phrase_patterns = [
        r"(repair doubler)",
        r"(original fastener)",
        r"(reinforcement doubler)",
        r"(alclad plate[^.;,]*)",
        r"(lateral structure[^.;,]*)",
        r"(lateral leg[^.;,]*)",
        r"(double passenger seat assy)",
        r"(single passenger seat assy)",
        r"(triple passenger seat[^.;,]*)",
        r"(typical repair[^.;,]*)",
        r"(figure\s+\d+[A-Z]?)",
    ]
    low = cleaned.lower()
    for pattern in phrase_patterns:
        for hit in re.findall(pattern, low, flags=re.I):
            pretty = _clean_trace_text(hit, max_chars=120)
            if pretty and pretty.lower() not in {t.lower() for t in terms}:
                terms.append(pretty)
            if len(terms) >= 10:
                break
        if len(terms) >= 10:
            break
    return terms[:10]


def build_clean_search_fallback(
    *,
    question: str,
    hits: Sequence[Mapping[str, Any]],
    citations: Sequence[Mapping[str, Any]],
) -> str:
    qtype = _query_type(question)
    lines = []

    if qtype == "repair_materials":
        opener = "TRACE-Net found repair-related manual pages. The strongest leads are:"
    elif qtype == "visual_or_figure_leads":
        opener = "TRACE-Net found pages that may be figure, callout, or illustrated-parts-list leads. The current server is still using text/OCR evidence, not true image understanding:"
    elif qtype == "parts_list":
        opener = "TRACE-Net found parts-list style evidence. The strongest leads are:"
    else:
        opener = "TRACE-Net found artifact-backed page leads:"

    lines.append(opener)

    for page in hits[:3]:
        page_id = page.get("page_id")
        page_number = page.get("page_number")
        route = page.get("route")
        summary = _extractive_summary(page, max_chars=420)
        terms = _extract_key_terms(str(page.get("text") or ""))
        terms_text = f" Key terms: {', '.join(terms[:6])}." if terms else ""
        lines.append(f"- `{page_id}` (page {page_number}, route={route}): {summary}{terms_text}")

    if qtype == "visual_or_figure_leads":
        lines.append("Because this is OCR/text-led evidence, treat diagram interpretation as a candidate lead until the image/visual route verifies it.")
    else:
        lines.append("Treat these as source leads for review, not as proof of approval, interchangeability, fit, or safety.")

    return "\n".join(lines)


def answer_search_summary_v13(question: str, pages: Sequence[Mapping[str, Any]], *, llm_config: LLMConfig) -> Dict[str, Any]:
    hits = _search_pages(question, pages)
    if not hits:
        response = (
            "TRACE-Net did not find enough artifact text to answer that question yet. "
            "Try an exact part number, a repair/material term, a nomenclature term, or ask for a random page summary."
        )
        return _response_record(
            question=question,
            response_text=response,
            intent="fallback_search",
            evidence_status="no_page_text_hits",
            citations=[],
            response_kind="controlled_no_answer",
            llm_config=llm_config,
            llm_called=False,
            llm_error=None,
        )

    citations = [
        {
            "page_id": page.get("page_id"),
            "page_number": page.get("page_number"),
            "route": page.get("route"),
            "source": "page_context_v2_or_fishnet",
        }
        for page in hits[:3]
    ]

    evidence_blocks = []
    for page in hits[:3]:
        evidence_blocks.append(
            f"page_id={page.get('page_id')}; page_number={page.get('page_number')}; "
            f"route={page.get('route')}; text={_extractive_summary(page, max_chars=800)}"
        )
    evidence = "\n\n".join(evidence_blocks)

    fallback = build_clean_search_fallback(question=question, hits=hits, citations=citations)
    llm_text, llm_called, llm_error, attempts = _compose_with_llm(
        question=question,
        evidence_text=evidence,
        intent="fallback_search",
        citations=citations,
        config=llm_config,
    )

    if llm_config.enabled and llm_called and not llm_error:
        response_text = llm_text
        kind = "gemma4_composed_artifact_search"
    else:
        response_text = fallback
        kind = "clean_controlled_artifact_search"

    return _response_record(
        question=question,
        response_text=response_text,
        intent="fallback_search",
        evidence_status="page_text_hits",
        citations=citations,
        response_kind=kind,
        llm_config=llm_config,
        llm_called=llm_called,
        llm_error=llm_error,
        llm_attempt_count=attempts,
    )


def answer_question_v13(
    *,
    question: str,
    pages: Sequence[Mapping[str, Any]],
    gated_drafts: Sequence[Mapping[str, Any]],
    llm_config: LLMConfig,
) -> Dict[str, Any]:
    q = question.lower()

    if "v2 summary" in q or "v2 summaries" in q:
        return answer_v2_summary_inventory(question, pages, llm_config=llm_config)

    if _part_numbers(question) or "part number" in q or "nearby similar" in q:
        lookup = answer_gated_lookup(question, gated_drafts, llm_config=llm_config)
        if lookup:
            return lookup

    if ("random" in q or "choose" in q or "pick" in q) and ("page" in q or "manual" in q) and any(word in q for word in ["summarize", "summary", "say", "tell me", "explain"]):
        return answer_random_page_summary(question, pages, llm_config=llm_config)

    lookup = answer_gated_lookup(question, gated_drafts, llm_config=llm_config)
    if lookup:
        return lookup

    return answer_search_summary_v13(question, pages, llm_config=llm_config)


def build_manifest_v13(
    *,
    output_dir: Path,
    final_gate_path: Path,
    runner_path: Path,
    page_context_path: Path,
    fishnet_path: Path,
    route_handoff_path: Path,
    sample_question: str,
    llm_config: LLMConfig,
) -> Dict[str, Any]:
    pages = load_page_index(
        page_context_path=page_context_path,
        fishnet_path=fishnet_path,
        route_handoff_path=route_handoff_path,
    )
    gated_drafts = load_gated_drafts(final_gate_path=final_gate_path, runner_path=runner_path)
    sample_record = answer_question_v13(
        question=sample_question,
        pages=pages,
        gated_drafts=gated_drafts,
        llm_config=LLMConfig(mode="off", model=llm_config.model, base_url=llm_config.base_url),
    )

    records = [sample_record]
    summary = {
        "page_record_count": len(pages),
        "page_with_text_count": sum(1 for p in pages if p.get("has_text")),
        "gated_draft_count": len(gated_drafts),
        "sample_response_kind": sample_record.get("response_kind"),
        "sample_response_char_count": sample_record.get("response_text_char_count"),
        "server_llm_mode": llm_config.mode,
        "server_llm_model": llm_config.model if llm_config.enabled else None,
        "server_llm_base_url": llm_config.base_url if llm_config.enabled else None,
        "retry_empty_response_enabled": llm_config.retry_empty_response,
        "clean_fallback_enabled": True,
        "ready_for_webui": True,
        "openai_compatible_chat_completions_route": True,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "retrieval_execution_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "unsafe_record_count": 0,
    }
    quality_status = "PASS" if (summary["page_record_count"] or summary["gated_draft_count"]) else "FAIL"

    payload = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_WEBUI_ANSWER_SERVER_V1_3_MANIFEST_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "model_id": MODEL_ID,
        "records": records,
        "routes": {"health": "/health", "models": "/v1/models", "chat_completions": "/v1/chat/completions"},
        "safety_contract": {
            "manual_review_required": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / "trace_net_engineering_webui_answer_server_v1_3_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_webui_answer_server_v1_3_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_webui_answer_server_v1_3_quality.json", {"quality_status": quality_status, "summary": summary})
    return payload


def check_manifest_v13(
    *,
    report_path: Path,
    min_page_records: int = 1,
    min_gated_drafts: int = 0,
    require_llm_model: Optional[str] = None,
    require_clean_fallback: bool = False,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path, required=True)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def fail_if(condition: bool, msg: str) -> None:
        if condition:
            failures.append(msg)

    fail_if(summary.get("page_record_count", 0) < min_page_records, "not enough page records")
    fail_if(summary.get("gated_draft_count", 0) < min_gated_drafts, "not enough gated drafts")
    if require_llm_model:
        fail_if(summary.get("server_llm_model") != require_llm_model, f"server llm model is not {require_llm_model}")
    if require_clean_fallback:
        fail_if(not summary.get("clean_fallback_enabled"), "clean fallback is not enabled")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
        fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
        fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")

    return {
        "quality_status": "FAIL" if failures else "PASS",
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


class TraceNetWebUIHandlerV13(BaseHTTPRequestHandler):
    server_version = "TraceNetWebUIAnswerServer/1.3"

    def _json_response(self, status: int, payload: Mapping[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/"}:
            self._json_response(200, {
                "status": "ok",
                "module": MODULE_VERSION,
                "server_version": "v1.3",
                "model_id": MODEL_ID,
                "page_record_count": len(self.server.pages),  # type: ignore[attr-defined]
                "gated_draft_count": len(self.server.gated_drafts),  # type: ignore[attr-defined]
                "llm_mode": self.server.llm_config.mode,  # type: ignore[attr-defined]
                "llm_model": self.server.llm_config.model if self.server.llm_config.enabled else None,  # type: ignore[attr-defined]
                "clean_fallback_enabled": True,
                "ready_for_webui": True,
            })
            return
        if self.path in {"/v1/models", "/api/models"}:
            self._json_response(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": int(time.time()), "owned_by": "trace-net"}]})
            return
        self._json_response(404, {"error": f"not found: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/v1/chat/completions", "/api/chat/completions"}:
            self._json_response(404, {"error": f"not found: {self.path}"})
            return
        try:
            body = self._read_body_json()
            messages = body.get("messages") or []
            question = ""
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    question = str(msg.get("content") or "")
                    break
            if not question:
                question = "pick a random page to summarize"

            record = answer_question_v13(
                question=question,
                pages=self.server.pages,  # type: ignore[attr-defined]
                gated_drafts=self.server.gated_drafts,  # type: ignore[attr-defined]
                llm_config=self.server.llm_config,  # type: ignore[attr-defined]
            )
            response = {
                "id": f"chatcmpl-trace-net-{int(time.time() * 1000)}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model") or MODEL_ID,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": record["response_text"]}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "trace_net": record,
            }
            self._json_response(200, response)
        except Exception as exc:
            self._json_response(500, {"error": f"{type(exc).__name__}: {exc}"})


class TraceNetHTTPServerV13(ThreadingHTTPServer):
    def __init__(self, server_address: Tuple[str, int], handler_class: Any, *, pages: Sequence[Mapping[str, Any]], gated_drafts: Sequence[Mapping[str, Any]], llm_config: LLMConfig):
        super().__init__(server_address, handler_class)
        self.pages = list(pages)
        self.gated_drafts = list(gated_drafts)
        self.llm_config = llm_config


def run_server_v13(
    *,
    host: str,
    port: int,
    final_gate_path: Path,
    runner_path: Path,
    page_context_path: Path,
    fishnet_path: Path,
    route_handoff_path: Path,
    llm_config: LLMConfig,
) -> None:
    pages = load_page_index(page_context_path=page_context_path, fishnet_path=fishnet_path, route_handoff_path=route_handoff_path)
    gated_drafts = load_gated_drafts(final_gate_path=final_gate_path, runner_path=runner_path)
    server = TraceNetHTTPServerV13((host, port), TraceNetWebUIHandlerV13, pages=pages, gated_drafts=gated_drafts, llm_config=llm_config)
    print(f"TRACE-Net WebUI answer server v1.3 running on http://{host}:{port}")
    print(f"Model ID exposed to WebUI: {MODEL_ID}")
    print(f"Runtime LLM model: {llm_config.model if llm_config.enabled else 'off'}")
    print("Clean fallback enabled: True")
    print(f"Pages loaded: {len(pages)}")
    print(f"Gated drafts loaded: {len(gated_drafts)}")
    server.serve_forever()


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering WebUI answer server manifest v1.3.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--final-gate", default=str(DEFAULT_FINAL_GATE))
    parser.add_argument("--runner-report", default=str(DEFAULT_RUNNER))
    parser.add_argument("--page-context-v2", default=str(DEFAULT_PAGE_CONTEXT))
    parser.add_argument("--fishnet-ocr-grid", default=str(DEFAULT_FISHNET))
    parser.add_argument("--route-handoff", default=str(DEFAULT_ROUTE_HANDOFF))
    parser.add_argument("--sample-question", default="find repair information for passenger seat legs")
    _add_llm_args(parser)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_manifest_v13(
        output_dir=Path(args.output_dir),
        final_gate_path=Path(args.final_gate),
        runner_path=Path(args.runner_report),
        page_context_path=Path(args.page_context_v2),
        fishnet_path=Path(args.fishnet_ocr_grid),
        route_handoff_path=Path(args.route_handoff),
        sample_question=args.sample_question,
        llm_config=_llm_config_from_args(args),
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering WebUI answer server v1.3 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-page-records", type=int, default=1)
    parser.add_argument("--min-gated-drafts", type=int, default=0)
    parser.add_argument("--require-llm-model")
    parser.add_argument("--require-clean-fallback", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_manifest_v13(
        report_path=Path(args.report_path),
        min_page_records=args.min_page_records,
        min_gated_drafts=args.min_gated_drafts,
        require_llm_model=args.require_llm_model,
        require_clean_fallback=args.require_clean_fallback,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_engineering_webui_answer_server_v1_3_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


def main_run(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run TRACE-Net engineering WebUI answer server v1.3.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8044)
    parser.add_argument("--final-gate", default=str(DEFAULT_FINAL_GATE))
    parser.add_argument("--runner-report", default=str(DEFAULT_RUNNER))
    parser.add_argument("--page-context-v2", default=str(DEFAULT_PAGE_CONTEXT))
    parser.add_argument("--fishnet-ocr-grid", default=str(DEFAULT_FISHNET))
    parser.add_argument("--route-handoff", default=str(DEFAULT_ROUTE_HANDOFF))
    _add_llm_args(parser)
    args = parser.parse_args(argv)

    run_server_v13(
        host=args.host,
        port=args.port,
        final_gate_path=Path(args.final_gate),
        runner_path=Path(args.runner_report),
        page_context_path=Path(args.page_context_v2),
        fishnet_path=Path(args.fishnet_ocr_grid),
        route_handoff_path=Path(args.route_handoff),
        llm_config=_llm_config_from_args(args),
    )
    return 0
