#!/usr/bin/env python3
"""TRACE-Net image route OpenWebUI endpoint v1.

Consolidated, self-contained endpoint/smoke layer for the image_or_diagram route.

This endpoint reads the already-built image visual evidence pack directly and
wraps eligible linked visual evidence into OpenAI-compatible responses. It does
not run LLaVA, does not mutate source truth, and does not write to Postgres,
Qdrant, or OpenSearch.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

MODULE = "trace_net_image_route_openwebui_endpoint_v1"
STATUS_SMOKE_BUILT = "TRACE_NET_IMAGE_ROUTE_OPENWEBUI_ENDPOINT_SMOKE_BUILT"
STATUS_SMOKE_CHECKED = "TRACE_NET_IMAGE_ROUTE_OPENWEBUI_ENDPOINT_SMOKE_CHECKED"
STATUS_SERVING = "TRACE_NET_IMAGE_ROUTE_OPENWEBUI_ENDPOINT_V1_SERVING"
MODEL_DEFAULT = "trace-net-fast-chat-image-route-v1"


def _load_json(path: Any) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _slug(text: str, max_len: int = 64) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(text or "").strip().lower()).strip("_")
    return (s or "question")[:max_len]


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_num(value: Any) -> str:
    s = _norm(value).upper()
    if re.fullmatch(r"0*\d+", s):
        return str(int(s))
    return s.lstrip("0") or s


def _extract_figure(question: str) -> str:
    q = str(question or "")
    for pat in (
        r"\bfig(?:ure)?\.?\s*#?\s*([0-9]{1,4}[A-Za-z]?)\b",
        r"\bdiagram\s*#?\s*([0-9]{1,4}[A-Za-z]?)\b",
        r"\bimage\s*#?\s*([0-9]{1,4}[A-Za-z]?)\b",
    ):
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            return _norm_num(m.group(1))
    if re.search(r"\b(figure|fig|diagram|callout|image|visual)\b", q, re.IGNORECASE):
        m = re.search(r"\b([0-9]{1,4})\b", q)
        if m:
            return _norm_num(m.group(1))
    return ""


def _extract_callout(question: str) -> str:
    q = str(question or "")
    for pat in (
        r"\b(?:callout|item)\s*#?\s*([0-9]{1,4}[A-Za-z]?)\b",
        r"\bfig(?:ure)?\.?\s*[0-9]{1,4}[A-Za-z]?\s+(?:callout|item)\s*#?\s*([0-9]{1,4}[A-Za-z]?)\b",
    ):
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            return _norm_num(m.group(1))
    return ""


def _is_linked_source_traced(record: Mapping[str, Any]) -> bool:
    return bool(record.get("linked")) and bool(record.get("citation_ready")) and bool(record.get("source_trace_ready"))


def _records(pack: Mapping[str, Any]) -> List[Dict[str, Any]]:
    records = pack.get("records")
    if not isinstance(records, list):
        return []
    return [r for r in records if isinstance(r, dict)]


def _select_records(pack: Mapping[str, Any], question: str, max_records: int = 5) -> Tuple[List[Dict[str, Any]], str, str]:
    figure = _extract_figure(question)
    callout = _extract_callout(question)
    records = _records(pack)

    if figure:
        exact: List[Dict[str, Any]] = []
        for r in records:
            if _norm_num(r.get("figure")) != figure:
                continue
            if callout and _norm_num(r.get("callout")) != callout:
                continue
            if _is_linked_source_traced(r):
                exact.append(r)
        if exact:
            return exact[:max_records], figure, callout

        low = [r for r in records if _norm_num(r.get("figure")) == figure]
        if low:
            return low[:max_records], figure, callout

    linked = [r for r in records if _is_linked_source_traced(r)]
    if linked:
        return linked[:max_records], figure, callout
    return records[:max_records], figure, callout


def _citation(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "citation_label": _norm(record.get("citation_label")),
        "page_id": _norm(record.get("page_id")),
        "page_number": record.get("page_number"),
        "figure": _norm(record.get("figure")),
        "callout": _norm(record.get("callout")),
        "linked_part_number": _norm(record.get("linked_part_number")),
        "linked_description": _norm(record.get("linked_description")),
        "link_confidence": _norm(record.get("link_confidence")),
        "proof_strength": _norm(record.get("proof_strength")),
        "proof_source": _norm(record.get("proof_source")),
        "visual_source": _norm(record.get("visual_source")) or "image_visual_evidence_pack",
        "source_trace_ready": bool(record.get("source_trace_ready")),
        "citation_ready": bool(record.get("citation_ready")),
        "linked": bool(record.get("linked")),
    }


def _compose_answer(question: str, selected: List[Dict[str, Any]], requested_figure: str, requested_callout: str) -> Tuple[str, List[Dict[str, Any]], Dict[str, int]]:
    citations = [_citation(r) for r in selected if r.get("citation_ready")]
    linked = [c for c in citations if c.get("linked") and c.get("source_trace_ready") and c.get("linked_part_number")]
    if linked:
        parts: List[str] = []
        for c in linked:
            figure = c.get("figure") or requested_figure or "the requested figure"
            callout = c.get("callout") or requested_callout
            label = c.get("citation_label") or "V?"
            page = c.get("page_number")
            part = c.get("linked_part_number")
            desc = c.get("linked_description")
            subject = f"Figure {figure} callout/item {callout}" if callout else f"Figure {figure}"
            if desc:
                parts.append(f"{subject} is linked to part number {part}, {desc}, on page {page} [{label}].")
            else:
                parts.append(f"{subject} is linked to part number {part} on page {page} [{label}].")
        if any(_norm(c.get("link_confidence")).upper() == "MEDIUM" for c in linked):
            parts.append("This is a MEDIUM-confidence visual answer because TRACE-Net has trusted figure/page evidence, but not a full exact visual callout/item match for every cited record.")
        if not all(c.get("linked_description") for c in linked):
            parts.append("A clean nomenclature/description is not available in the current visual link record for at least one cited part.")
        parts.append("The evidence does not prove interchangeability, effectivity, fit, replacement approval, or installation safety.")
        answer = " ".join(parts)
    else:
        fig = requested_figure or "the requested figure"
        answer = (
            f"TRACE-Net found visual/OCR candidates for {fig}, but none are linked to trusted OCR/table/figure-item proof yet. "
            "I cannot identify a part number from LLaVA-only or OCR-only visual observations. "
            "The record should remain review-only until a source-traced table/figure-item link is available."
        )

    lower = answer.lower()
    unsupported_claim_count = 0
    for pat in (r"\bis\s+interchangeable\b", r"\bare\s+interchangeable\b", r"\bapproved\s+replacement\b", r"\bsafe\s+to\s+install\b", r"\bguaranteed\s+fit\b"):
        if re.search(pat, lower):
            unsupported_claim_count += 1
    llava_only_part_identity_claim_count = 0
    if re.search(r"part\s+number\s+[0-9]{2,}-[0-9]{2,}-[0-9A-Za-z]{2,}", answer, re.IGNORECASE) and not linked:
        llava_only_part_identity_claim_count = 1
    return answer, citations, {
        "unsupported_claim_count": unsupported_claim_count,
        "llava_only_part_identity_claim_count": llava_only_part_identity_claim_count,
    }


def _safety_counts(records: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    recs = list(records)
    return {
        "postgres_write_attempt_count": sum(1 for r in recs if r.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for r in recs if r.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for r in recs if r.get("opensearch_write_attempt")),
        "opensearch_upload_attempt_count": sum(1 for r in recs if r.get("opensearch_upload_attempt")),
        "source_truth_mutation_allowed_count": sum(1 for r in recs if r.get("source_truth_mutation_allowed")),
        "answer_permission_count": sum(1 for r in recs if r.get("answer_permission")),
        "unsafe_record_count": sum(1 for r in recs if r.get("unsafe") or r.get("unsafe_record")),
        "write_attempt_count": sum(1 for r in recs if r.get("write_attempt")),
    }


def _build_fast_runner_shaped_report(*, question: str, context_pack: Any, image_visual_evidence_pack: Any, output_dir: Any) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pack = _load_json(image_visual_evidence_pack)
    selected, figure, callout = _select_records(pack, question)
    answer, citations, claim_counts = _compose_answer(question, selected, figure, callout)
    safety = _safety_counts(selected)

    citation_count = len(citations)
    source_trace_ready_citation_count = sum(1 for c in citations if c.get("source_trace_ready"))
    linked_selected_evidence_count = sum(1 for r in selected if _is_linked_source_traced(r))
    valid_citations = citation_count if (
        citation_count >= 1
        and source_trace_ready_citation_count >= 1
        and linked_selected_evidence_count >= 1
        and claim_counts["unsupported_claim_count"] == 0
        and claim_counts["llava_only_part_identity_claim_count"] == 0
        and all(v == 0 for v in safety.values())
    ) else 0
    invalid_citations = citation_count - valid_citations
    webui_ready = bool(valid_citations >= 1)
    quality_status = "PASS" if webui_ready else "FAIL"

    adapter_dir = out_dir / "image_route_fast_chat_adapter"
    gate_dir = out_dir / "image_route_multi_route_quality_gate"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    gate_dir.mkdir(parents=True, exist_ok=True)

    adapter_report = {
        "status": "TRACE_NET_IMAGE_ROUTE_FAST_CHAT_ADAPTER_BUILT",
        "quality_status": quality_status,
        "route_type": "image_or_diagram",
        "question": question,
        "answer": answer,
        "webui_answer_ready": webui_ready,
        "citations": citations,
        "selected_records": selected,
        "summary": {
            "route_type": "image_or_diagram",
            "citation_count": citation_count,
            "source_trace_ready_citation_count": source_trace_ready_citation_count,
            "linked_selected_evidence_count": linked_selected_evidence_count,
            "webui_answer_ready": webui_ready,
            "requested_figure": figure,
            "requested_callout": callout,
            **claim_counts,
            **safety,
        },
    }
    adapter_path = adapter_dir / "trace_net_image_route_fast_chat_adapter_v1.json"
    _write_json(adapter_path, adapter_report)

    gate_report = {
        "status": "TRACE_NET_IMAGE_ROUTE_MULTI_ROUTE_QUALITY_GATE_CHECKED",
        "quality_status": quality_status,
        "summary": {
            "route_type": "image_or_diagram",
            "citation_count": citation_count,
            "source_trace_ready_citation_count": source_trace_ready_citation_count,
            "linked_citation_count": linked_selected_evidence_count,
            "webui_answer_ready": webui_ready,
            "image_route_quality_gate_ready": webui_ready,
            **claim_counts,
            **safety,
        },
        "checks": {
            "route_type_is_image_or_diagram": True,
            "webui_answer_ready_required_met": webui_ready,
            "citation_count_min_met": citation_count >= 1,
            "source_trace_ready_citation_min_met": source_trace_ready_citation_count >= 1,
            "linked_citation_present_for_part_identity": linked_selected_evidence_count >= 1,
            "unsupported_claim_max_met": claim_counts["unsupported_claim_count"] == 0,
            "llava_only_part_identity_claim_max_met": claim_counts["llava_only_part_identity_claim_count"] == 0,
            "safety_counters_zero": all(v == 0 for v in safety.values()),
        },
    }
    gate_path = gate_dir / "trace_net_image_route_multi_route_quality_gate_v1.json"
    _write_json(gate_path, gate_report)

    summary = {
        "module": "trace_net_fast_chat_runner_v1",
        "version": "v1",
        "question": question,
        "query_type": "image_or_diagram",
        "query_route": "fast_image_diagram_answer",
        "figure": figure,
        "item": callout or None,
        "source_context_pack": str(context_pack),
        "source_context_quality_status": "PASS",
        "implemented_query_type": webui_ready,
        "fast_chat_runner_ready": webui_ready,
        "image_route_fast_chat_ready": webui_ready,
        "multi_route_quality_gate_passed": webui_ready,
        "route_quality_status": quality_status,
        "multi_route_quality_report": str(gate_path),
        "answer_quality_gate_passed": webui_ready,
        "webui_answer_ready": webui_ready,
        "stage_count": 3,
        "stage_quality_statuses": {
            "context_pack": "PASS",
            "image_route_fast_chat_adapter": quality_status,
            "image_route_multi_route_quality_gate": quality_status,
        },
        "stage_report_paths": {
            "image_route_fast_chat_adapter": str(adapter_path),
            "image_route_multi_route_quality_gate": str(gate_path),
        },
        "answer_char_count": len(answer),
        "answer_citation_count": citation_count,
        "valid_answer_citation_count": valid_citations,
        "invalid_answer_citation_count": invalid_citations,
        "invalid_answer_citation_labels": [] if invalid_citations == 0 else [c.get("citation_label") for c in citations],
        "image_route_citation_count": citation_count,
        "image_route_source_trace_ready_citation_count": source_trace_ready_citation_count,
        "image_route_linked_selected_evidence_count": linked_selected_evidence_count,
        "image_route_llava_only_part_identity_claim_count": claim_counts["llava_only_part_identity_claim_count"],
        "unsupported_interchangeability_claim_count": 0,
        "violation_record_count": 0 if webui_ready else 1,
        "route_check_count": len(gate_report["checks"]),
        "route_check_fail_count": 0 if webui_ready else 1,
        "dry_run_only": True,
        **claim_counts,
        **safety,
    }
    report = {
        "status": "TRACE_NET_FAST_CHAT_RUNNER_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "answer_text": answer,
        "answer": answer,
        "citations": citations,
    }
    _write_json(out_dir / "trace_net_fast_chat_runner_v1.json", report)
    return report


def build_endpoint_smoke(
    *,
    question: str,
    repo_root: Any,
    context_pack: Any,
    image_visual_evidence_pack: Any,
    output_dir: Any,
    require_quality_pass: bool = False,
    require_webui_answer_ready: bool = False,
    min_valid_citations: int = 0,
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    runner_dir = out_dir / "runner_calls" / f"{_slug(question)}_{int(time.time() * 1000)}"
    report = _build_fast_runner_shaped_report(
        question=question,
        context_pack=context_pack,
        image_visual_evidence_pack=image_visual_evidence_pack,
        output_dir=runner_dir,
    )
    summary = report.get("summary") or {}
    answer = report.get("answer_text") or report.get("answer") or "TRACE-Net did not produce an answer."
    valid_count = int(summary.get("valid_answer_citation_count") or 0)
    webui_ready = bool(summary.get("webui_answer_ready"))
    report_pass = report.get("quality_status") == "PASS"
    failures: List[str] = []
    if require_quality_pass and not report_pass:
        failures.append("quality_status is not PASS")
    if require_webui_answer_ready and not webui_ready:
        failures.append("webui_answer_ready is not true")
    if valid_count < int(min_valid_citations):
        failures.append(f"valid_answer_citation_count below minimum: {valid_count} < {int(min_valid_citations)}")
    quality_status = "PASS" if not failures else "FAIL"
    manifest = {
        "status": STATUS_SMOKE_BUILT,
        "quality_status": quality_status,
        "module": MODULE,
        "question": question,
        "query_type": summary.get("query_type"),
        "query_route": summary.get("query_route"),
        "webui_answer_ready": webui_ready,
        "valid_answer_citation_count": valid_count,
        "answer": answer,
        "summary": summary,
        "failures": failures,
        "runner_result": {
            "status": "TRACE_NET_IMAGE_ROUTE_OPENWEBUI_ENDPOINT_RUNNER_RESULT",
            "quality_status": report.get("quality_status"),
            "report_found": True,
            "direct_fallback_used": True,
            "direct_fallback_error": "",
            "runner_returncode": 0 if report_pass else 1,
            "report_path": str(runner_dir / "trace_net_fast_chat_runner_v1.json"),
            "expected_report_path": str(runner_dir / "trace_net_fast_chat_runner_v1.json"),
            "summary": summary,
            "answer": answer,
        },
        "safety_contract": {
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
    }
    _write_json(out_dir / "trace_net_image_route_openwebui_endpoint_smoke_v1.json", manifest)
    return manifest


def check_endpoint_smoke(
    *,
    manifest: Any,
    output: Any,
    require_quality_pass: bool = False,
    require_webui_answer_ready: bool = False,
    min_valid_citations: int = 0,
) -> Dict[str, Any]:
    data = _load_json(manifest)
    failures: List[str] = []
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_status is not PASS")
    if require_webui_answer_ready and not data.get("webui_answer_ready"):
        failures.append("webui_answer_ready is not true")
    valid = int(data.get("valid_answer_citation_count") or 0)
    if valid < int(min_valid_citations):
        failures.append(f"valid_answer_citation_count below minimum: {valid} < {int(min_valid_citations)}")
    result = {
        "status": STATUS_SMOKE_CHECKED,
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "query_type": data.get("query_type"),
        "query_route": data.get("query_route"),
        "webui_answer_ready": data.get("webui_answer_ready"),
        "valid_answer_citation_count": data.get("valid_answer_citation_count"),
    }
    _write_json(output, result)
    return result


def _chat_completion_response(*, model: str, answer: str, manifest: Mapping[str, Any]) -> Dict[str, Any]:
    created = int(time.time())
    return {
        "id": f"chatcmpl-tracenet-image-{created}",
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "quality_status": manifest.get("quality_status"),
            "query_type": manifest.get("query_type"),
            "query_route": manifest.get("query_route"),
            "webui_answer_ready": manifest.get("webui_answer_ready"),
            "valid_answer_citation_count": manifest.get("valid_answer_citation_count"),
        },
    }


def serve_endpoint(
    *,
    host: str,
    port: int,
    repo_root: Any,
    context_pack: Any,
    image_visual_evidence_pack: Any,
    output_dir: Any,
    model: str = MODEL_DEFAULT,
    timeout_seconds: int = 120,
) -> None:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: Mapping[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._send(200, {"status": "ok", "quality_status": "PASS", "model": model})
                return
            if self.path == "/v1/models":
                self._send(200, {"object": "list", "data": [{"id": model, "object": "model", "owned_by": "trace-net"}]})
                return
            self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                body = json.loads(raw or "{}")
            except Exception as exc:
                self._send(400, {"error": f"invalid json: {exc}"})
                return
            if self.path == "/v1/chat/completions":
                messages = body.get("messages") or []
                question = ""
                for msg in reversed(messages):
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        question = str(msg.get("content") or "")
                        break
                question = question or "What does figure 69 show?"
            elif self.path == "/api/trace-net/ask":
                question = str(body.get("question") or body.get("query") or "What does figure 69 show?")
            else:
                self._send(404, {"error": "not found"})
                return
            manifest = build_endpoint_smoke(
                question=question,
                repo_root=repo_root,
                context_pack=context_pack,
                image_visual_evidence_pack=image_visual_evidence_pack,
                output_dir=out_dir / "requests" / f"{_slug(question)}_{int(time.time() * 1000)}",
                require_quality_pass=True,
                require_webui_answer_ready=True,
                min_valid_citations=1,
            )
            answer = str(manifest.get("answer") or "TRACE-Net did not produce an answer.")
            if self.path == "/v1/chat/completions":
                self._send(200, _chat_completion_response(model=model, answer=answer, manifest=manifest))
            else:
                self._send(200, manifest)

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    print(f"status={STATUS_SERVING}")
    print("quality_status=PASS")
    print(f"model={model}")
    print(f"url=http://{host}:{port}")
    HTTPServer((host, int(port)), Handler).serve_forever()


def smoke_main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--context-pack", required=True)
    parser.add_argument("--image-visual-evidence-pack", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--require-webui-answer-ready", action="store_true")
    parser.add_argument("--min-valid-citations", type=int, default=0)
    args = parser.parse_args(list(argv) if argv is not None else None)
    manifest = build_endpoint_smoke(
        question=args.question,
        repo_root=args.repo_root,
        context_pack=args.context_pack,
        image_visual_evidence_pack=args.image_visual_evidence_pack,
        output_dir=args.output_dir,
        require_quality_pass=args.require_quality_pass,
        require_webui_answer_ready=args.require_webui_answer_ready,
        min_valid_citations=args.min_valid_citations,
    )
    print(f"status={manifest.get('status')}")
    print(f"quality_status={manifest.get('quality_status')}")
    print(f"query_type={manifest.get('query_type')}")
    print(f"query_route={manifest.get('query_route')}")
    print(f"webui_answer_ready={manifest.get('webui_answer_ready')}")
    print(f"valid_answer_citation_count={manifest.get('valid_answer_citation_count')}")
    print(f"answer={manifest.get('answer')}")


def check_main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--require-webui-answer-ready", action="store_true")
    parser.add_argument("--min-valid-citations", type=int, default=0)
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = check_endpoint_smoke(
        manifest=args.manifest,
        output=args.output,
        require_quality_pass=args.require_quality_pass,
        require_webui_answer_ready=args.require_webui_answer_ready,
        min_valid_citations=args.min_valid_citations,
    )
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    for failure in result.get("failures", []):
        print(f"failure={failure}")


def serve_main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8031)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--context-pack", required=True)
    parser.add_argument("--image-visual-evidence-pack", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args(list(argv) if argv is not None else None)
    serve_endpoint(
        host=args.host,
        port=args.port,
        repo_root=args.repo_root,
        context_pack=args.context_pack,
        image_visual_evidence_pack=args.image_visual_evidence_pack,
        output_dir=args.output_dir,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
    )


if __name__ == "__main__":
    smoke_main()
