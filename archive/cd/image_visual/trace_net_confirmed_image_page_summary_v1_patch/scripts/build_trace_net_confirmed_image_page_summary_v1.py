#!/usr/bin/env python3
"""TRACE-Net confirmed image page summary v1.

Front-half image understanding layer.

Input:
- gated visual retrieval documents for confirmed image pages

Output:
- one clean visual summary card per confirmed image page
- one retrieval-ready summary document per confirmed image page
- summary/report

Default mode is adapter-only and read-only:
- no OCR rerun
- no LLaVA call
- no Gemma call
- no DB writes
- no source-truth mutation

Optional model mode is available through explicit flags:
- --call-ollama-llava
- --call-ollama-gemma

Contract:
- OCR/text evidence remains source text authority.
- LLaVA observation is visual-layout guidance only.
- Gemma structuring is normalization only, not source truth.
"""

from __future__ import annotations

import argparse
import ast
import base64
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MODULE_NAME = "trace_net_confirmed_image_page_summary_v1"
STATUS_BUILT = "TRACE_NET_CONFIRMED_IMAGE_PAGE_SUMMARY_V1_BUILT"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

PART_RE = re.compile(r"\b[A-Z0-9]{1,6}[-/][A-Z0-9][A-Z0-9./-]{1,24}\b|\b\d{3}-\d{5}-\d{3}\b", re.I)
FIG_RE = re.compile(r"\bfig(?:ure)?\.?\s*[0-9]+[a-z]?(?:\s+sheet\s+[0-9]+)?\b", re.I)
PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}", re.I)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                if isinstance(data, dict):
                    yield data


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n


def compact_ws(text: Any, limit: int = 2000) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        try:
            text = json.dumps(text, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(text)
    return " ".join(text.split())[:limit]


def stable_unique(values: Iterable[Any], *, limit: int = 100) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        text = compact_ws(value, limit=400)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def parse_dict_like_string(value: str) -> Optional[Dict[str, Any]]:
    text = value.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        parsed = ast.literal_eval(text)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def clean_figure_refs(raw_values: Iterable[Any]) -> Tuple[List[str], List[Dict[str, Any]]]:
    clean: List[str] = []
    structured: List[Dict[str, Any]] = []
    for raw in raw_values or []:
        if raw is None:
            continue
        if isinstance(raw, dict):
            structured.append(raw)
            desc = compact_ws(raw.get("description") or raw.get("type") or "", limit=300)
            if desc and "figure" in desc.lower():
                clean.append(desc)
            continue
        text = compact_ws(raw, limit=300)
        if not text:
            continue
        parsed = parse_dict_like_string(text)
        if parsed:
            structured.append(parsed)
            # Do not put long dict-like summaries into figure_refs_clean.
            continue
        if FIG_RE.search(text):
            clean.append(FIG_RE.search(text).group(0).lower())
        elif text.isdigit() and len(text) <= 4:
            # Bare small figure/item numbers are useful, but keep them distinct.
            clean.append(text)
        elif len(text) <= 80 and not text.startswith("{"):
            clean.append(text)
    return stable_unique(clean, limit=25), structured


def clean_callouts(raw_values: Iterable[Any]) -> List[str]:
    values: List[str] = []
    for raw in raw_values or []:
        text = compact_ws(raw, limit=200)
        if not text:
            continue
        if parse_dict_like_string(text):
            # Dict-like visual metadata belongs in observations, not callouts.
            continue
        # Avoid ATA/page boilerplate dominating the card.
        values.append(text)
    return stable_unique(values, limit=40)


def extract_part_numbers(*groups: Iterable[Any]) -> List[str]:
    found: List[str] = []
    for group in groups:
        for value in group or []:
            text = compact_ws(value, limit=500)
            found.extend(m.group(0).upper() for m in PART_RE.finditer(text))
    return stable_unique(found, limit=40)


def infer_visual_page_type(doc: Dict[str, Any], summary_text: str, figure_refs: List[str]) -> str:
    summary = summary_text.lower()
    subtype = str(doc.get("visual_subtype") or "").lower()
    if "illustrated" in summary or "parts_diagram" in summary or "parts diagram" in summary:
        return "illustrated_parts_list_or_parts_diagram"
    if "exploded" in summary:
        return "exploded_view_or_assembly_diagram"
    if "diagram" in summary or "drawing" in summary or "figure" in summary or figure_refs:
        return "technical_diagram_or_figure"
    if "confirmed_diagram" in subtype:
        return "technical_diagram_or_figure"
    return "image_visual_page"


def infer_subject(doc: Dict[str, Any], summary_text: str, part_numbers: List[str]) -> str:
    candidates = [
        doc.get("nomenclature"),
        doc.get("subject"),
        doc.get("title"),
        doc.get("page_title"),
        summary_text,
    ]
    for c in candidates:
        text = compact_ws(c, limit=180)
        if text and text.lower() not in {"unknown", "parts_diagram_or_illustrated_parts_list"}:
            return text
    if part_numbers:
        return f"visual page associated with part number(s): {', '.join(part_numbers[:5])}"
    return "confirmed image/diagram page; subject not explicitly identified"


def find_text_values(doc: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for key in ("summary", "search_text", "text", "ocr_text", "page_context", "description"):
        value = doc.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(compact_ws(v, limit=500) for v in value)
    # Nested identifiers / extracted fields.
    ids = doc.get("identifiers")
    if isinstance(ids, dict):
        for key in ("figure_refs", "part_numbers", "nomenclature"):
            v = ids.get(key)
            if isinstance(v, list):
                values.extend(compact_ws(x, limit=300) for x in v)
            elif isinstance(v, str):
                values.append(v)
    return values


def find_page_image(page_id: str, roots: Sequence[Path]) -> Optional[Path]:
    if not page_id:
        return None
    names = [
        f"{page_id}.png",
        f"{page_id}.jpg",
        f"{page_id}.jpeg",
        f"{page_id}.tif",
        f"{page_id}.tiff",
    ]
    for root in roots:
        if not root.exists():
            continue
        for name in names:
            direct = root / name
            if direct.exists():
                return direct
        # Bounded recursive search: expected local_data tree; stop after first.
        for suffix in ("*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff"):
            for path in root.rglob(suffix):
                if path.stem.lower() == page_id.lower():
                    return path
    return None


def ollama_generate(
    *,
    base_url: str,
    model: str,
    prompt: str,
    image_path: Optional[Path] = None,
    timeout_seconds: float = 180.0,
) -> str:
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if image_path is not None:
        payload["images"] = [base64.b64encode(image_path.read_bytes()).decode("ascii")]
    url = base_url.rstrip("/") + "/api/generate"
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return compact_ws(data.get("response") if isinstance(data, dict) else data, limit=6000)


def llava_prompt(page_id: str, doc: Dict[str, Any]) -> str:
    return f"""You are TRACE-Net's visual observation specialist for scanned technical-manual pages.

Page ID: {page_id}

Describe only what is visually observable in the page image:
- page visual type
- diagram/figure layout
- visible callouts/arrows/labels
- visible part relationships
- figure/sheet/title signals if clearly visible
- uncertainty

Do not make fit, interchangeability, effectivity, approval, installation, or eligibility claims.
Do not replace OCR. If text is unclear, mark it uncertain.
Return concise JSON-like text.
Existing retrieval hints, not source truth:
{json.dumps(doc, ensure_ascii=False)[:2500]}
"""


def gemma_prompt(card: Dict[str, Any]) -> str:
    return f"""You are TRACE-Net's schema normalizer.

Clean this image-page summary card into concise JSON fields.
Do not add new evidence. Do not invent part numbers or figure references.
Keep OCR/text, LLaVA visual observation, and summary guidance separated.
Keep safety: visual guidance only; no fit/interchangeability/effectivity/approval/installation claims.

CARD:
{json.dumps(card, ensure_ascii=False, sort_keys=True)[:7000]}
"""


def load_llava_observations(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if not path or not path.exists():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in read_jsonl(path):
        page_id = str(row.get("page_id") or "")
        if page_id:
            out[page_id] = row
    return out


def build_summary_card(
    doc: Dict[str, Any],
    *,
    llava_observation: Optional[Dict[str, Any]],
    call_ollama_llava: bool,
    call_ollama_gemma: bool,
    image_roots: Sequence[Path],
    ollama_base_url: str,
    llava_model: str,
    gemma_model: str,
    ollama_timeout_seconds: float,
) -> Dict[str, Any]:
    page_id = str(doc.get("page_id") or "")
    source_summary = compact_ws(doc.get("summary") or "", limit=1600)
    raw_figure_refs = doc.get("figure_refs") or []
    raw_callouts = doc.get("callouts") or []
    raw_part_numbers = doc.get("part_numbers") or []

    figure_refs_clean, structured_figure_metadata = clean_figure_refs(raw_figure_refs)
    callouts_clean = clean_callouts(raw_callouts)
    text_values = find_text_values(doc)
    part_numbers = stable_unique(
        list(raw_part_numbers or []) + extract_part_numbers(text_values, raw_callouts, raw_figure_refs),
        limit=40,
    )

    image_path = find_page_image(page_id, image_roots) if call_ollama_llava else None
    llava_text = ""
    llava_status = "not_requested"
    llava_call_attempt = False

    if llava_observation:
        llava_text = compact_ws(
            llava_observation.get("llava_visual_observation")
            or llava_observation.get("visual_observation")
            or llava_observation.get("response")
            or llava_observation.get("summary")
            or llava_observation,
            limit=6000,
        )
        llava_status = "loaded_from_existing_observation"
    elif call_ollama_llava:
        llava_call_attempt = True
        if image_path is None:
            llava_status = "image_not_found"
        else:
            try:
                llava_text = ollama_generate(
                    base_url=ollama_base_url,
                    model=llava_model,
                    prompt=llava_prompt(page_id, doc),
                    image_path=image_path,
                    timeout_seconds=ollama_timeout_seconds,
                )
                llava_status = "ollama_llava_observation_created"
            except Exception as exc:
                llava_status = f"ollama_llava_error: {type(exc).__name__}: {exc}"

    visual_page_type = infer_visual_page_type(doc, source_summary + " " + llava_text, figure_refs_clean)
    subject = infer_subject(doc, source_summary + " " + llava_text, part_numbers)

    visual_observations = []
    if structured_figure_metadata:
        for item in structured_figure_metadata[:8]:
            visual_observations.append(compact_ws(item.get("description") or item.get("type") or item, limit=300))
    if llava_text:
        visual_observations.append(llava_text)
    elif source_summary:
        visual_observations.append(source_summary)

    uncertainty = []
    if not figure_refs_clean:
        uncertainty.append("figure reference not cleanly identified")
    if not part_numbers:
        uncertainty.append("part number not cleanly identified")
    if not llava_text:
        uncertainty.append("no fresh LLaVA observation attached for this card")
    if any(str(x).strip().startswith("{") for x in raw_figure_refs or []):
        uncertainty.append("upstream figure_refs contained dict-like visual metadata; moved to observations/metadata")

    retrieval_terms = stable_unique(
        [
            visual_page_type,
            subject,
            *figure_refs_clean,
            *part_numbers,
            *callouts_clean[:12],
            compact_ws(source_summary, limit=500),
            compact_ws(llava_text, limit=700),
        ],
        limit=80,
    )

    card: Dict[str, Any] = {
        "module": MODULE_NAME,
        "page_id": page_id,
        "document_id": doc.get("document_id"),
        "source_visual_route": doc.get("visual_route") or doc.get("route"),
        "source_visual_subtype": doc.get("visual_subtype"),
        "route_confidence": doc.get("route_confidence"),
        "visual_page_summary": {
            "visual_page_type": visual_page_type,
            "likely_diagram_subject": subject,
            "figure_refs_clean": figure_refs_clean,
            "part_numbers": part_numbers,
            "visible_callouts_clean": callouts_clean,
            "visual_observations": stable_unique(visual_observations, limit=12),
            "ocr_text_signals": stable_unique(text_values, limit=12),
            "structured_visual_metadata": structured_figure_metadata[:12],
            "uncertainty": stable_unique(uncertainty, limit=20),
            "retrieval_usefulness": "useful_for_visual_diagram_retrieval",
        },
        "model_layers": {
            "ocr_role": "source_text_authority_when_available",
            "llava_role": "visual_layout_observation_only",
            "gemma_role": "schema_normalization_only",
            "llava_status": llava_status,
            "gemma_status": "not_requested",
        },
        "retrieval_document": {
            "document_id": f"{MODULE_NAME}::{page_id}",
            "page_id": page_id,
            "route_name": "confirmed_image_page_summary",
            "search_text": compact_ws(" | ".join(retrieval_terms), limit=8000),
            "figure_refs": figure_refs_clean,
            "part_numbers": part_numbers,
            "visual_page_type": visual_page_type,
            "likely_diagram_subject": subject,
            "final_answer_allowed": False,
            "answer_permission": False,
            "visual_guidance_only": True,
        },
        "safety_contract": {
            "final_answer_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "visual_context_is_retrieval_guidance_only": True,
            "requires_non_visual_source_trace_for_final_claims": True,
            "source_truth_mutation_allowed": False,
        },
        "runtime_counts": {
            "ollama_llava_call_attempt": llava_call_attempt,
            "ollama_gemma_call_attempt": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }

    if call_ollama_gemma:
        card["runtime_counts"]["ollama_gemma_call_attempt"] = True
        try:
            gemma_text = ollama_generate(
                base_url=ollama_base_url,
                model=gemma_model,
                prompt=gemma_prompt(card),
                image_path=None,
                timeout_seconds=ollama_timeout_seconds,
            )
            card["model_layers"]["gemma_status"] = "ollama_gemma_summary_created"
            card["gemma_structured_summary_text"] = gemma_text
        except Exception as exc:
            card["model_layers"]["gemma_status"] = f"ollama_gemma_error: {type(exc).__name__}: {exc}"

    return card


def build(args: argparse.Namespace) -> Dict[str, Any]:
    started = time.time()
    input_path = Path(args.gated_visual_documents_jsonl)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    docs = list(read_jsonl(input_path))
    if args.limit and args.limit > 0:
        docs = docs[: args.limit]

    llava_by_page = load_llava_observations(Path(args.llava_observations_jsonl) if args.llava_observations_jsonl else None)
    image_roots = [Path(x) for x in args.image_roots] if args.image_roots else []

    cards: List[Dict[str, Any]] = []
    for doc in docs:
        page_id = str(doc.get("page_id") or "")
        cards.append(
            build_summary_card(
                doc,
                llava_observation=llava_by_page.get(page_id),
                call_ollama_llava=bool(args.call_ollama_llava),
                call_ollama_gemma=bool(args.call_ollama_gemma),
                image_roots=image_roots,
                ollama_base_url=args.ollama_base_url,
                llava_model=args.llava_model,
                gemma_model=args.gemma_model,
                ollama_timeout_seconds=args.ollama_timeout_seconds,
            )
        )

    retrieval_docs = [card["retrieval_document"] for card in cards]

    cards_path = output_dir / "trace_net_confirmed_image_page_summary_v1.jsonl"
    retrieval_path = output_dir / "trace_net_confirmed_image_page_summary_v1_retrieval_documents.jsonl"
    report_path = output_dir / "trace_net_confirmed_image_page_summary_v1_report.txt"
    summary_path = output_dir / "summary.json"

    write_jsonl(cards_path, cards)
    write_jsonl(retrieval_path, retrieval_docs)

    count = len(cards)
    pages_with_clean_figure_refs = sum(bool(c["visual_page_summary"]["figure_refs_clean"]) for c in cards)
    pages_with_part_numbers = sum(bool(c["visual_page_summary"]["part_numbers"]) for c in cards)
    llava_call_attempt_count = sum(bool(c["runtime_counts"]["ollama_llava_call_attempt"]) for c in cards)
    gemma_call_attempt_count = sum(bool(c["runtime_counts"]["ollama_gemma_call_attempt"]) for c in cards)
    source_truth_mutation_allowed_count = sum(bool(c["safety_contract"]["source_truth_mutation_allowed"]) for c in cards)
    answer_permission_count = sum(bool(c["safety_contract"]["answer_permission"]) for c in cards)
    final_answer_allowed_true_count = sum(bool(c["safety_contract"]["final_answer_allowed"]) for c in cards)

    quality_status = QUALITY_PASS
    quality_reasons: List[str] = []
    if count < args.min_summary_count:
        quality_status = QUALITY_FAIL
        quality_reasons.append(f"summary_count {count} < min_summary_count {args.min_summary_count}")
    if answer_permission_count:
        quality_status = QUALITY_FAIL
        quality_reasons.append("answer_permission_count must be 0")
    if final_answer_allowed_true_count:
        quality_status = QUALITY_FAIL
        quality_reasons.append("final_answer_allowed_true_count must be 0")
    if source_truth_mutation_allowed_count:
        quality_status = QUALITY_FAIL
        quality_reasons.append("source_truth_mutation_allowed_count must be 0")

    summary = {
        "module": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "quality_reasons": quality_reasons,
        "input_document_count": len(docs),
        "confirmed_image_summary_count": count,
        "retrieval_document_count": len(retrieval_docs),
        "pages_with_clean_figure_refs": pages_with_clean_figure_refs,
        "pages_with_part_numbers": pages_with_part_numbers,
        "llava_observation_loaded_count": sum(c["model_layers"]["llava_status"] == "loaded_from_existing_observation" for c in cards),
        "llava_call_attempt_count": llava_call_attempt_count,
        "gemma_call_attempt_count": gemma_call_attempt_count,
        "answer_permission_count": answer_permission_count,
        "final_answer_allowed_true_count": final_answer_allowed_true_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "elapsed_seconds": round(time.time() - started, 3),
        "outputs": {
            "cards": str(cards_path),
            "retrieval_documents": str(retrieval_path),
            "report": str(report_path),
            "summary": str(summary_path),
        },
        "contract": {
            "front_half_layer": True,
            "ocr_role": "source_text_authority_when_available",
            "llava_role": "visual_layout_observation_only",
            "gemma_role": "schema_normalization_only",
            "visual_context_is_retrieval_guidance_only": True,
            "requires_non_visual_source_trace_for_final_claims": True,
        },
    }
    write_json(summary_path, summary)

    lines = [
        f"status={STATUS_BUILT}",
        f"quality_status={quality_status}",
        f"confirmed_image_summary_count={count}",
        f"retrieval_document_count={len(retrieval_docs)}",
        f"pages_with_clean_figure_refs={pages_with_clean_figure_refs}",
        f"pages_with_part_numbers={pages_with_part_numbers}",
        f"llava_call_attempt_count={llava_call_attempt_count}",
        f"gemma_call_attempt_count={gemma_call_attempt_count}",
        f"answer_permission_count={answer_permission_count}",
        f"final_answer_allowed_true_count={final_answer_allowed_true_count}",
        f"source_truth_mutation_allowed_count={source_truth_mutation_allowed_count}",
        f"cards={cards_path}",
        f"retrieval_documents={retrieval_path}",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build clean confirmed image page summaries.")
    p.add_argument("--gated-visual-documents-jsonl", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--llava-observations-jsonl", default="")
    p.add_argument("--image-roots", nargs="*", default=[])
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--min-summary-count", type=int, default=1)
    p.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    p.add_argument("--llava-model", default="llava:13b")
    p.add_argument("--gemma-model", default="gemma4:26b")
    p.add_argument("--ollama-timeout-seconds", type=float, default=180.0)
    p.add_argument("--call-ollama-llava", action="store_true")
    p.add_argument("--call-ollama-gemma", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    summary = build(args)
    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    print(f"confirmed_image_summary_count={summary['confirmed_image_summary_count']}")
    print(f"retrieval_document_count={summary['retrieval_document_count']}")
    print(f"pages_with_clean_figure_refs={summary['pages_with_clean_figure_refs']}")
    print(f"pages_with_part_numbers={summary['pages_with_part_numbers']}")
    print(f"llava_call_attempt_count={summary['llava_call_attempt_count']}")
    print(f"gemma_call_attempt_count={summary['gemma_call_attempt_count']}")
    print(f"answer_permission_count={summary['answer_permission_count']}")
    print(f"final_answer_allowed_true_count={summary['final_answer_allowed_true_count']}")
    print(f"source_truth_mutation_allowed_count={summary['source_truth_mutation_allowed_count']}")
    print(f"output_dir={Path(args.output_dir)}")
    return 0 if summary["quality_status"] == QUALITY_PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
