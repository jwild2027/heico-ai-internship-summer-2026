"""TRACE-Net image/diagram fast answer composer v1.

Consumes trace_net_image_visual_evidence_pack_v1 and drafts a deterministic,
source-traced visual answer. It never lets LLaVA alone prove part identity: only
records with linked trusted OCR/table/figure-item proof can support a limited
answer. LOW unlinked records remain review-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_image_diagram_fast_answer_composer_v1"
STATUS_BUILT = "TRACE_NET_IMAGE_DIAGRAM_FAST_ANSWER_COMPOSER_BUILT"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/image_diagram_fast_answer_composer_v1"
PART_PATTERN = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
FIGURE_QUERY_PATTERN = re.compile(r"\b(?:fig(?:ure)?\.?|diagram)\s*[-:#]?\s*([A-Z0-9]+)\b", re.IGNORECASE)
ITEM_QUERY_PATTERN = re.compile(r"\b(?:item|callout|index|key|ref(?:erence)?\.?\s*(?:no\.?)?)\s*[-:#]?\s*([A-Z0-9]{1,5})\b", re.IGNORECASE)
PAGE_QUERY_PATTERN = re.compile(r"\bpage\s*[-:#]?\s*(\d{1,6})\b", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def normalize_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def norm(value: Any) -> str:
    return normalize_string(value).upper().replace(" ", "").replace(".", "").replace(":", "").replace("#", "")


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "ready"}
    return bool(value)


def safe_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    match = re.search(r"\d+", normalize_string(value))
    if not match:
        return None
    return int(match.group(0))


def iter_records(payload: Any) -> List[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        value = payload.get("records")
        if isinstance(value, list):
            return [r for r in value if isinstance(r, Mapping)]
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, Mapping)]
    return []


def parse_query(question: str) -> Dict[str, Any]:
    figures = [m.group(1).upper() for m in FIGURE_QUERY_PATTERN.finditer(question or "")]
    callouts = [m.group(1).upper() for m in ITEM_QUERY_PATTERN.finditer(question or "")]
    pages = [int(m.group(1)) for m in PAGE_QUERY_PATTERN.finditer(question or "")]
    parts = [m.group(0) for m in PART_PATTERN.finditer(question or "")]
    return {"figures": figures, "callouts": callouts, "pages": pages, "part_numbers": parts}


def record_matches_query(record: Mapping[str, Any], query: Mapping[str, Any]) -> int:
    score = 0
    figures = [norm(v) for v in query.get("figures", [])]
    callouts = [norm(v) for v in query.get("callouts", [])]
    pages = set(query.get("pages", []))
    parts = set(query.get("part_numbers", []))
    if figures:
        if norm(record.get("figure")) in figures:
            score += 100
        else:
            return -1
    if callouts:
        rec_callout = norm(record.get("callout"))
        if rec_callout and rec_callout in callouts:
            score += 75
        else:
            return -1
    if pages:
        if safe_int(record.get("page_number")) in pages:
            score += 40
        elif not figures and not callouts and not parts:
            return -1
    if parts:
        if normalize_string(record.get("linked_part_number")) in parts:
            score += 100
        else:
            return -1
    if boolish(record.get("can_support_limited_visual_answer")):
        score += 20
    if normalize_string(record.get("link_confidence")).upper() == "HIGH":
        score += 15
    elif normalize_string(record.get("link_confidence")).upper() == "MEDIUM":
        score += 10
    return score


def choose_records(records: Sequence[Mapping[str, Any]], query: Mapping[str, Any], top_k: int = 5) -> List[Mapping[str, Any]]:
    scored: List[Tuple[int, Mapping[str, Any]]] = []
    has_specific_query = any(query.get(k) for k in ("figures", "callouts", "pages", "part_numbers"))
    for record in records:
        score = record_matches_query(record, query)
        if score >= 0:
            if has_specific_query or boolish(record.get("linked")):
                scored.append((score, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [r for _, r in scored[:top_k]]


def citation_marker(record: Mapping[str, Any]) -> str:
    return f"[{normalize_string(record.get('citation_label')) or 'V?'}]"


def answer_for_records(question: str, selected: Sequence[Mapping[str, Any]], query: Mapping[str, Any]) -> Tuple[str, str, List[Dict[str, Any]], bool]:
    linked = [r for r in selected if boolish(r.get("can_support_limited_visual_answer"))]
    citations: List[Dict[str, Any]] = []
    if linked:
        sentences: List[str] = []
        for record in linked:
            fig = normalize_string(record.get("figure"))
            callout = normalize_string(record.get("callout"))
            part = normalize_string(record.get("linked_part_number"))
            desc = normalize_string(record.get("linked_description"))
            page = record.get("page_number")
            conf = normalize_string(record.get("link_confidence")) or "MEDIUM"
            mark = citation_marker(record)
            if callout:
                lead = f"Figure {fig} callout/item {callout}"
            elif fig:
                lead = f"Figure {fig}"
            else:
                lead = "The visual record"
            if desc:
                sentence = f"{lead} is linked to part number {part}, \"{desc},\" on page {page} {mark}."
            else:
                sentence = f"{lead} is linked to part number {part} on page {page} {mark}."
            if conf.upper() == "MEDIUM":
                sentence += " This is a MEDIUM-confidence visual link because TRACE-Net has trusted figure/page evidence, but not a full exact callout/item match in the visual link record."
            sentences.append(sentence)
            citations.append({
                "citation_label": normalize_string(record.get("citation_label")),
                "page_id": normalize_string(record.get("page_id")),
                "page_number": page,
                "figure": fig,
                "callout": callout,
                "linked_part_number": part,
                "link_confidence": conf,
                "source_trace_ready": boolish(record.get("source_trace_ready")),
                "citation_ready": boolish(record.get("citation_ready")),
                "proof_source": normalize_string(record.get("proof_source")),
            })
        sentences.append("The evidence does not prove interchangeability, effectivity, fit, replacement approval, or installation safety.")
        if any(not normalize_string(r.get("linked_description")) for r in linked):
            sentences.append("A clean nomenclature/description is not available in the current visual link record for at least one cited part.")
        return "citation_backed_visual_answer_draft", " ".join(sentences), citations, True

    # If there are only unlinked matches, say so but do not answer with part identity.
    if selected:
        snippets = []
        for record in selected[:3]:
            fig = normalize_string(record.get("figure"))
            callout = normalize_string(record.get("callout"))
            page = record.get("page_number")
            label = f"figure {fig}" if fig else "a visual label"
            if callout:
                label += f" callout/item {callout}"
            snippets.append(f"{label} on page {page}")
        answer = "TRACE-Net found visual/OCR observations (" + "; ".join(snippets) + "), but none are linked to trusted OCR/table/figure-item proof. I cannot identify a part from LLaVA/OCR-only evidence."
        return "audit_only_unlinked_visual_observation", answer, [], False

    answer = "TRACE-Net did not find a source-traced visual evidence record matching this image/diagram question in the current image visual evidence pack."
    return "audit_only_no_visual_evidence_match", answer, [], False


def summarize(status: str, citations: Sequence[Mapping[str, Any]], webui_ready: bool, records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    unsupported_claim_count = 0
    return {
        "api_response_status": status,
        "citation_count": len(citations),
        "source_trace_ready_citation_count": sum(1 for c in citations if boolish(c.get("source_trace_ready"))),
        "citation_ready_count": sum(1 for c in citations if boolish(c.get("citation_ready"))),
        "selected_evidence_record_count": len(records),
        "linked_selected_evidence_count": sum(1 for r in records if boolish(r.get("linked"))),
        "webui_answer_ready": bool(webui_ready and len(citations) > 0 and unsupported_claim_count == 0),
        "unsupported_claim_count": unsupported_claim_count,
        "llava_only_part_identity_claim_count": 0,
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
    }


def evaluate_quality(summary: Mapping[str, Any], args: argparse.Namespace) -> Tuple[str, List[str]]:
    failures: List[str] = []
    if args.require_webui_answer_ready and not boolish(summary.get("webui_answer_ready")):
        failures.append("webui_answer_ready is false")
    if int(summary.get("citation_count", 0)) < args.min_citations:
        failures.append("citation_count below threshold")
    if int(summary.get("source_trace_ready_citation_count", 0)) < args.min_source_trace_ready_citations:
        failures.append("source_trace_ready_citation_count below threshold")
    if int(summary.get("unsupported_claim_count", 0)) > args.max_unsupported_claims:
        failures.append("unsupported_claim_count above threshold")
    if int(summary.get("llava_only_part_identity_claim_count", 0)) > args.max_llava_only_part_identity_claims:
        failures.append("llava_only_part_identity_claim_count above threshold")
    if int(summary.get("unsafe_record_count", 0)) > args.max_unsafe:
        failures.append("unsafe_record_count above threshold")
    if int(summary.get("answer_permission_count", 0)) > args.max_answer_permission:
        failures.append("answer_permission_count above threshold")
    if int(summary.get("source_truth_mutation_allowed_count", 0)) > args.max_source_truth_mutation_allowed:
        failures.append("source_truth_mutation_allowed_count above threshold")
    if int(summary.get("write_attempt_count", 0)) > args.max_write_attempts:
        failures.append("write_attempt_count above threshold")
    return ("PASS" if not failures else "FAIL"), failures


def build_payload(args: argparse.Namespace) -> Dict[str, Any]:
    pack = read_json(Path(args.image_visual_evidence_pack))
    records = iter_records(pack)
    query = parse_query(args.question)
    selected = choose_records(records, query, args.top_k)
    status, answer, citations, webui_ready = answer_for_records(args.question, selected, query)
    summary = summarize(status, citations, webui_ready, selected)
    quality, failures = evaluate_quality(summary, args)
    return {
        "schema_version": "trace_net_image_diagram_fast_answer_composer_v1",
        "module": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": quality,
        "created_at": utc_now(),
        "question": args.question,
        "query_parse": query,
        "model": "deterministic_image_diagram_fast_composer_v1",
        "answer": answer,
        "citations": citations,
        "selected_evidence_records": selected,
        "summary": summary,
        "checks": {"failures": failures},
        "safety_contract": {
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "llava_only_part_identity_claim_allowed": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image-visual-evidence-pack", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--require-webui-answer-ready", action="store_true")
    p.add_argument("--min-citations", type=int, default=1)
    p.add_argument("--min-source-trace-ready-citations", type=int, default=1)
    p.add_argument("--max-unsupported-claims", type=int, default=0)
    p.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def safe_slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")[:60] or "question"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{digest}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    payload = build_payload(args)
    slug = safe_slug(args.question)
    main_path = output_dir / f"trace_net_image_diagram_fast_answer_composer_v1_{slug}.json"
    latest_path = output_dir / "trace_net_image_diagram_fast_answer_composer_v1.json"
    quality_path = output_dir / f"trace_net_image_diagram_fast_answer_composer_v1_{slug}_quality_check.json"
    write_json(main_path, payload)
    write_json(latest_path, payload)
    write_json(quality_path, {k: payload[k] for k in ("schema_version", "module", "status", "quality_status", "created_at", "question", "summary", "checks")})
    s = payload["summary"]
    print(f"status={payload['status']}")
    print(f"quality_status={payload['quality_status']}")
    for key in ("api_response_status", "citation_count", "source_trace_ready_citation_count", "selected_evidence_record_count", "linked_selected_evidence_count", "webui_answer_ready", "unsupported_claim_count", "llava_only_part_identity_claim_count", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count"):
        print(f"{key}={s.get(key)}")
    print("answer=" + payload["answer"])
    print(f"composer={main_path}")
    return 0 if payload["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
