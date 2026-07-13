#!/usr/bin/env python3
"""TRACE-Net confirmed image LLaVA observations v1.1.

Runs LLaVA against confirmed image/diagram pages and writes one visual
observation record per page.

This is the model-running stage between:
- confirmed_image_page_summary_v1_1 adapter cards
- final visual summary cards / retrieval docs

Safety contract:
- LLaVA observation is visual guidance only.
- LLaVA does not replace OCR.
- LLaVA does not prove fit/interchangeability/effectivity/approval/install authority.
- no Postgres/Qdrant/OpenSearch writes
- no source-truth mutation
- no answer permission

The runner is resumable:
- output JSONL is appended page-by-page
- reruns skip pages already present unless --overwrite is set
"""

from __future__ import annotations

import argparse
import ast
import base64
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


MODULE_NAME = "trace_net_confirmed_image_llava_observations_v1_1"
STATUS_BUILT = "TRACE_NET_CONFIRMED_IMAGE_LLAVA_OBSERVATIONS_V1_1_BUILT"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}", re.I)


def compact_ws(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            value = str(value)
    return " ".join(value.split())[:limit]


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                if isinstance(data, dict):
                    yield data


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def stable_unique(values: Iterable[Any], *, limit: int = 100) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        text = compact_ws(value, limit=500)
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


def load_cards(path: Path) -> List[Dict[str, Any]]:
    rows = []
    for row in read_jsonl(path):
        page_id = str(row.get("page_id") or "")
        if PAGE_ID_RE.fullmatch(page_id):
            rows.append(row)
    return rows


def existing_page_ids(path: Path) -> Set[str]:
    out: Set[str] = set()
    for row in read_jsonl(path):
        page_id = str(row.get("page_id") or "")
        status = str(row.get("llava_status") or "")
        if page_id and status == "ollama_llava_observation_created":
            out.add(page_id)
    return out


def choose_cards(
    cards: Sequence[Dict[str, Any]],
    *,
    page_ids: Sequence[str],
    limit: int,
    overwrite: bool,
    output_jsonl: Path,
) -> List[Dict[str, Any]]:
    wanted = {p.strip() for p in page_ids if p.strip()}
    done = set() if overwrite else existing_page_ids(output_jsonl)

    selected = []
    for card in cards:
        page_id = str(card.get("page_id") or "")
        if wanted and page_id not in wanted:
            continue
        if page_id in done:
            continue
        selected.append(card)
        if limit and limit > 0 and len(selected) >= limit:
            break
    return selected


def image_candidates(page_id: str, roots: Sequence[Path]) -> Iterable[Path]:
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
                yield direct
        for suffix in ("*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff"):
            for path in root.rglob(suffix):
                if path.stem.lower() == page_id.lower():
                    yield path


def find_image(page_id: str, roots: Sequence[Path]) -> Optional[Path]:
    seen = set()
    for path in image_candidates(page_id, roots):
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        return path
    return None


def convert_image_for_ollama(image_path: Path, *, converted_dir: Path) -> Tuple[Optional[Path], str]:
    """Return a PNG/JPEG path accepted by Ollama vision models.

    TIFF often fails in vision APIs, so convert TIFF/TIF to PNG. PNG/JPEG are
    passed through unchanged.
    """
    suffix = image_path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg"}:
        return image_path, "source_image_passed_through"

    if suffix in {".tif", ".tiff"}:
        try:
            from PIL import Image
        except Exception as exc:
            return None, f"pillow_import_failed_for_tiff_conversion: {type(exc).__name__}: {exc}"
        converted_dir.mkdir(parents=True, exist_ok=True)
        out = converted_dir / f"{image_path.stem}.png"
        try:
            with Image.open(image_path) as im:
                if getattr(im, "n_frames", 1) > 1:
                    im.seek(0)
                if im.mode not in {"RGB", "L"}:
                    im = im.convert("RGB")
                im.save(out)
            return out, "converted_tiff_to_png_with_pillow"
        except Exception as exc:
            return None, f"tiff_conversion_failed: {type(exc).__name__}: {exc}"

    return None, f"unsupported_image_format: {suffix}"


HEADER_OR_BOILERPLATE_TOKENS = {
    "25",
    "21",
    "00",
    "06",
    "12",
    "377",
    "ocr/table/figure-item",
    "visual/ocr",
    "review-only",
    "summary",
    "table",
    "visual",
}


def strip_json_fence(text: str) -> str:
    value = compact_ws(text, limit=20000)
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    return value.strip()


def parse_llava_jsonish(text: str) -> Optional[Dict[str, Any]]:
    value = strip_json_fence(text)
    if not value:
        return None
    # If the model adds prose before/after JSON, take the first object.
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        value = value[start : end + 1]
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    try:
        data = ast.literal_eval(value)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def flatten_label_values(value: Any) -> List[str]:
    out: List[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        return [compact_ws(value, limit=250)]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, dict):
        # Prefer explicit visible label/callout text. Avoid turning whole dicts
        # into labels because that preserves noisy model structure as a label.
        for key in ("label", "callout", "text", "part_number", "figure", "description"):
            if key in value:
                out.extend(flatten_label_values(value.get(key)))
        return out
    if isinstance(value, list):
        for item in value:
            out.extend(flatten_label_values(item))
        return out
    return [compact_ws(value, limit=250)]


def is_boilerplate_or_header_label(value: str) -> bool:
    text = compact_ws(value, limit=200).strip()
    low = text.lower()
    if not text:
        return True
    if low in HEADER_OR_BOILERPLATE_TOKENS:
        return True
    # ATA-style/system/page-header fragments are often emitted as callouts.
    if re.fullmatch(r"(25|21|00|06|12|377)", text):
        return True
    if re.fullmatch(r"(ata\s*)?25[-\s]?21[-\s]?00", low):
        return True
    if low in {"page", "figure", "sheet", "rev", "revision", "date"}:
        return True
    return False


def cleanup_llava_observation(raw_text: str) -> Dict[str, Any]:
    """Parse and clean model output without deleting the original text.

    The raw observation is preserved. This deterministic layer separates common
    manual header/page metadata from likely callout labels so downstream Gemma
    does not make page headers look official.
    """
    parsed = parse_llava_jsonish(raw_text)
    if not parsed:
        return {
            "parsed": False,
            "visible_callouts_or_labels_cleaned": [],
            "filtered_out_possible_header_or_boilerplate_labels": [],
            "cleanup_notes": ["LLaVA output was not parseable JSON; raw observation preserved"],
        }

    raw_labels = flatten_label_values(parsed.get("visible_callouts_or_labels"))
    clean: List[str] = []
    filtered: List[str] = []
    for label in raw_labels:
        if is_boilerplate_or_header_label(label):
            filtered.append(label)
        else:
            clean.append(label)

    return {
        "parsed": True,
        "visual_page_type": compact_ws(parsed.get("visual_page_type"), limit=300),
        "diagram_subject_guess": compact_ws(parsed.get("diagram_subject_guess"), limit=500),
        "figure_title_or_sheet_text_if_clearly_visible": compact_ws(
            parsed.get("figure_title_or_sheet_text_if_clearly_visible"),
            limit=500,
        ),
        "visible_callouts_or_labels_cleaned": stable_unique(clean, limit=80),
        "filtered_out_possible_header_or_boilerplate_labels": stable_unique(filtered, limit=80),
        "visual_uncertainty": compact_ws(parsed.get("visual_uncertainty"), limit=1200),
        "retrieval_keywords": stable_unique(flatten_label_values(parsed.get("retrieval_keywords")), limit=50),
        "cleanup_notes": [
            "Raw LLaVA output preserved.",
            "Known ATA/page/header/status tokens are separated from cleaned visible-callout candidates.",
            "Cleaned callouts are still visual guidance only, not source-truth proof.",
        ],
    }


def llava_prompt(card: Dict[str, Any]) -> str:
    page_id = card.get("page_id")
    visual = card.get("visual_page_summary") if isinstance(card.get("visual_page_summary"), dict) else {}
    hints = {
        "page_id": page_id,
        "existing_visual_page_type": visual.get("visual_page_type"),
        "existing_subject_hint": visual.get("likely_diagram_subject"),
        "figure_refs_hint": visual.get("figure_refs_clean"),
        "part_numbers_from_ocr_or_artifacts_hint": visual.get("part_numbers"),
        "safety": [
            "Do not prove fit/interchangeability/effectivity/approval/installation.",
            "Do not replace OCR.",
            "Mark uncertain text or labels as uncertain.",
            "Do not copy non-authoritative hints unless the image visibly supports them.",
        ],
    }
    return f"""You are TRACE-Net's visual observation specialist for scanned aircraft technical-manual pages.

Task: inspect the image page and describe only visual evidence from the image.

Return ONLY valid compact JSON. Do not wrap it in markdown fences.

Required JSON fields:
- visual_page_type
- diagram_subject_guess
- visual_layout_description
- visible_callouts_or_labels
- page_header_or_boilerplate_text
- arrows_lines_or_relationships
- figure_title_or_sheet_text_if_clearly_visible
- visual_uncertainty
- retrieval_keywords
- safety_note

Strict rules:
- Use the image as the primary source for visual layout.
- Do NOT copy the existing hints into your answer unless visibly supported by the image.
- If the diagram subject is not clear, write "unknown" instead of guessing.
- Do NOT invent subjects such as engine, aircraft structure, support, mounting point, component, or assembly unless visually obvious.
- Do NOT list page headers, ATA numbers, revision/date blocks, page numbers, or repeated manual boilerplate as callouts.
- Treat common header tokens such as 25, 21, 00, 06, 12, and 377 as page/header metadata unless visibly attached to a leader line, bubble, item number, or part label.
- Only put a value in visible_callouts_or_labels if it is visibly attached to an arrow, leader line, bubble, item marker, or part label.
- Put header/page/ATA/date/title-block tokens in page_header_or_boilerplate_text, not visible_callouts_or_labels.
- Treat text and part numbers as uncertain unless clearly legible.
- OCR/table/source evidence remains the authority for exact text and part numbers.
- Do not make fit, interchangeability, effectivity, approval, eligibility, or installation claims.

Existing non-authoritative hints:
{json.dumps(hints, ensure_ascii=False, sort_keys=True)[:3000]}
"""


def ollama_generate(
    *,
    base_url: str,
    model: str,
    prompt: str,
    image_path: Path,
    timeout_seconds: float,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [base64.b64encode(image_path.read_bytes()).decode("ascii")],
        "stream": False,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return compact_ws(data.get("response") if isinstance(data, dict) else data, limit=12000)


def build_record(
    card: Dict[str, Any],
    *,
    image_roots: Sequence[Path],
    output_dir: Path,
    ollama_base_url: str,
    llava_model: str,
    timeout_seconds: float,
    dry_run: bool,
) -> Dict[str, Any]:
    page_id = str(card.get("page_id") or "")
    started = time.time()
    raw_image = find_image(page_id, image_roots)

    base_record: Dict[str, Any] = {
        "module": MODULE_NAME,
        "page_id": page_id,
        "source_card_document_id": card.get("document_id"),
        "llava_model": llava_model,
        "ollama_base_url": ollama_base_url,
        "llava_status": "not_started",
        "llava_visual_observation": "",
        "llava_observation_cleaned": {},
        "source_image_path": str(raw_image) if raw_image else "",
        "source_image_media_type": "",
        "source_image_note": "",
        "elapsed_seconds": 0.0,
        "safety_contract": {
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "visual_context_is_retrieval_guidance_only": True,
            "requires_non_visual_source_trace_for_final_claims": True,
            "source_truth_mutation_allowed": False,
        },
        "runtime_counts": {
            "ollama_llava_call_attempt": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }

    if raw_image is None:
        base_record["llava_status"] = "image_not_found"
        base_record["elapsed_seconds"] = round(time.time() - started, 3)
        return base_record

    image_for_ollama, note = convert_image_for_ollama(
        raw_image,
        converted_dir=output_dir / "converted_images",
    )
    base_record["source_image_note"] = note
    if image_for_ollama is None:
        base_record["llava_status"] = note
        base_record["elapsed_seconds"] = round(time.time() - started, 3)
        return base_record

    base_record["source_image_path_for_ollama"] = str(image_for_ollama)
    base_record["source_image_media_type"] = image_for_ollama.suffix.lower().lstrip(".")

    if dry_run:
        base_record["llava_status"] = "dry_run_image_ready"
        base_record["elapsed_seconds"] = round(time.time() - started, 3)
        return base_record

    base_record["runtime_counts"]["ollama_llava_call_attempt"] = True
    try:
        observation = ollama_generate(
            base_url=ollama_base_url,
            model=llava_model,
            prompt=llava_prompt(card),
            image_path=image_for_ollama,
            timeout_seconds=timeout_seconds,
        )
        base_record["llava_status"] = "ollama_llava_observation_created"
        base_record["llava_visual_observation"] = observation
        base_record["llava_observation_cleaned"] = cleanup_llava_observation(observation)
    except Exception as exc:
        base_record["llava_status"] = f"ollama_llava_error: {type(exc).__name__}: {exc}"

    base_record["elapsed_seconds"] = round(time.time() - started, 3)
    return base_record


def summarize(output_jsonl: Path, output_dir: Path, selected_count: int, dry_run: bool) -> Dict[str, Any]:
    rows = list(read_jsonl(output_jsonl))
    success = [r for r in rows if r.get("llava_status") == "ollama_llava_observation_created"]
    image_ready = [r for r in rows if r.get("llava_status") == "dry_run_image_ready"]
    image_missing = [r for r in rows if r.get("llava_status") == "image_not_found"]
    errors = [r for r in rows if "error" in str(r.get("llava_status") or "").lower()]
    cleaned_rows = [r for r in rows if (r.get("llava_observation_cleaned") or {}).get("parsed")]
    filtered_label_count = sum(
        len((r.get("llava_observation_cleaned") or {}).get("filtered_out_possible_header_or_boilerplate_labels") or [])
        for r in rows
    )
    cleaned_callout_count = sum(
        len((r.get("llava_observation_cleaned") or {}).get("visible_callouts_or_labels_cleaned") or [])
        for r in rows
    )
    answer_permission_count = sum(bool((r.get("safety_contract") or {}).get("answer_permission")) for r in rows)
    final_allowed_count = sum(bool((r.get("safety_contract") or {}).get("final_answer_allowed")) for r in rows)
    source_mutation_count = sum(bool((r.get("safety_contract") or {}).get("source_truth_mutation_allowed")) for r in rows)

    quality_status = QUALITY_PASS
    quality_reasons: List[str] = []
    if answer_permission_count or final_allowed_count or source_mutation_count:
        quality_status = QUALITY_FAIL
        quality_reasons.append("safety contract violation")
    if selected_count > 0 and dry_run and not image_ready:
        quality_status = QUALITY_FAIL
        quality_reasons.append("dry run selected pages but no image-ready records were created")
    if selected_count > 0 and not dry_run and not success:
        quality_status = QUALITY_FAIL
        quality_reasons.append("non-dry run selected pages but no successful LLaVA observations were created")

    summary = {
        "module": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "quality_reasons": quality_reasons,
        "selected_page_count_this_run": selected_count,
        "total_record_count": len(rows),
        "successful_observation_count": len(success),
        "dry_run_image_ready_count": len(image_ready),
        "image_not_found_count": len(image_missing),
        "error_count": len(errors),
        "ollama_llava_call_attempt_count": sum(bool((r.get("runtime_counts") or {}).get("ollama_llava_call_attempt")) for r in rows),
        "parsed_clean_observation_count": len(cleaned_rows),
        "cleaned_visible_callout_count": cleaned_callout_count,
        "filtered_out_possible_header_or_boilerplate_label_count": filtered_label_count,
        "answer_permission_count": answer_permission_count,
        "final_answer_allowed_true_count": final_allowed_count,
        "source_truth_mutation_allowed_count": source_mutation_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "outputs": {
            "observations": str(output_jsonl),
            "summary": str(output_dir / "summary.json"),
            "report": str(output_dir / "trace_net_confirmed_image_llava_observations_v1_1_report.txt"),
        },
    }
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run LLaVA visual observations for confirmed image pages.")
    p.add_argument("--confirmed-image-summary-jsonl", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--image-roots", nargs="+", required=True)
    p.add_argument("--page-ids", nargs="*", default=[])
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    p.add_argument("--llava-model", default="llava:13b")
    p.add_argument("--timeout-seconds", type=float, default=240.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args(argv)


def build(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_jsonl = output_dir / "trace_net_confirmed_image_llava_observations_v1_1.jsonl"
    if args.overwrite and output_jsonl.exists():
        output_jsonl.unlink()

    cards = load_cards(Path(args.confirmed_image_summary_jsonl))
    selected = choose_cards(
        cards,
        page_ids=args.page_ids,
        limit=args.limit,
        overwrite=args.overwrite,
        output_jsonl=output_jsonl,
    )
    roots = [Path(p) for p in args.image_roots]

    for i, card in enumerate(selected, 1):
        page_id = card.get("page_id")
        print(f"[{i}/{len(selected)}] LLaVA page {page_id}...")
        record = build_record(
            card,
            image_roots=roots,
            output_dir=output_dir,
            ollama_base_url=args.ollama_base_url,
            llava_model=args.llava_model,
            timeout_seconds=args.timeout_seconds,
            dry_run=bool(args.dry_run),
        )
        append_jsonl(output_jsonl, record)
        print(f"  {record['llava_status']} ({record['elapsed_seconds']}s)")

    summary = summarize(output_jsonl, output_dir, len(selected), bool(args.dry_run))
    write_json(output_dir / "summary.json", summary)
    report_lines = [
        f"status={summary['status']}",
        f"quality_status={summary['quality_status']}",
        f"selected_page_count_this_run={summary['selected_page_count_this_run']}",
        f"total_record_count={summary['total_record_count']}",
        f"successful_observation_count={summary['successful_observation_count']}",
        f"dry_run_image_ready_count={summary['dry_run_image_ready_count']}",
        f"image_not_found_count={summary['image_not_found_count']}",
        f"error_count={summary['error_count']}",
        f"ollama_llava_call_attempt_count={summary['ollama_llava_call_attempt_count']}",
        f"parsed_clean_observation_count={summary['parsed_clean_observation_count']}",
        f"cleaned_visible_callout_count={summary['cleaned_visible_callout_count']}",
        f"filtered_out_possible_header_or_boilerplate_label_count={summary['filtered_out_possible_header_or_boilerplate_label_count']}",
        f"answer_permission_count={summary['answer_permission_count']}",
        f"final_answer_allowed_true_count={summary['final_answer_allowed_true_count']}",
        f"source_truth_mutation_allowed_count={summary['source_truth_mutation_allowed_count']}",
        f"observations={output_jsonl}",
    ]
    (output_dir / "trace_net_confirmed_image_llava_observations_v1_1_report.txt").write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    summary = build(args)
    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    print(f"selected_page_count_this_run={summary['selected_page_count_this_run']}")
    print(f"total_record_count={summary['total_record_count']}")
    print(f"successful_observation_count={summary['successful_observation_count']}")
    print(f"dry_run_image_ready_count={summary['dry_run_image_ready_count']}")
    print(f"image_not_found_count={summary['image_not_found_count']}")
    print(f"error_count={summary['error_count']}")
    print(f"ollama_llava_call_attempt_count={summary['ollama_llava_call_attempt_count']}")
    print(f"parsed_clean_observation_count={summary['parsed_clean_observation_count']}")
    print(f"cleaned_visible_callout_count={summary['cleaned_visible_callout_count']}")
    print(f"filtered_out_possible_header_or_boilerplate_label_count={summary['filtered_out_possible_header_or_boilerplate_label_count']}")
    print(f"answer_permission_count={summary['answer_permission_count']}")
    print(f"final_answer_allowed_true_count={summary['final_answer_allowed_true_count']}")
    print(f"source_truth_mutation_allowed_count={summary['source_truth_mutation_allowed_count']}")
    print(f"output_dir={Path(args.output_dir)}")
    return 0 if summary["quality_status"] == QUALITY_PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
