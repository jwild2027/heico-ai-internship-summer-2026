#!/usr/bin/env python3
"""Build TRACE-Net Patch-6A coordinate evidence for a route-balanced page set.

The command is intentionally laptop-first and file-only. It reads a TIFF ZIP or
image directory plus the frozen Patch-5.1 manifest, runs route-specific Tesseract
TSV, and writes derived coordinate evidence under ``--output-dir``.

No route is changed. No database or source-truth write is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_PAGE_NUMBERS = "24,48,82,155,228,297,420,509,17,81,202,454,492,494,23,468,478,505,2,12"


def _normalize_git_bash_path(value: str | Path) -> Path:
    text = str(value)
    if re.match(r"^/[A-Za-z]/", text):
        text = f"{text[1].upper()}:{text[2:]}"
    return Path(text)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) + "\n")


def _parse_page_numbers(value: str) -> list[int]:
    pages: list[int] = []
    seen: set[int] = set()
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = (int(part.strip()) for part in chunk.split("-", 1))
            values = range(start, end + 1)
        else:
            values = [int(chunk)]
        for page in values:
            if page not in seen:
                seen.add(page)
                pages.append(page)
    return pages


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise RuntimeError(f"Non-object JSONL record at {path}:{line_no}")
        rows.append(value)
    return rows


def _page_number_from_card(card: Mapping[str, Any]) -> int | None:
    for key in ("page_number", "canonical_page_number", "source_page_number"):
        try:
            number = int(card.get(key) or 0)
        except (TypeError, ValueError):
            number = 0
        if number > 0:
            return number
    for key in ("page_id", "source_page_id"):
        match = re.search(r"p(\d{6})", str(card.get(key) or ""), flags=re.I)
        if match:
            return int(match.group(1))
    return None


def _load_manifest_cards(path: Path) -> dict[int, dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        cards = _read_jsonl(path)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cards = (
            payload.get("page_route_cards")
            or payload.get("records")
            or payload.get("cards")
            or []
        )
    out: dict[int, dict[str, Any]] = {}
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        page = _page_number_from_card(card)
        if page:
            out[page] = dict(card)
    return out


def _image_size(image_bytes: bytes) -> tuple[int, int]:
    from PIL import Image
    with Image.open(BytesIO(image_bytes)) as image:
        return int(image.width), int(image.height)


def _psm_plan(route: str) -> tuple[int, ...]:
    from src.trace_net.ocr.trace_net_coordinate_evidence_v1 import (
        BLANK_ROUTES,
        TABLE_ROUTES,
        TEXT_ROUTES,
        VISUAL_ROUTES,
    )
    if route in TABLE_ROUTES:
        return (6,)
    if route in VISUAL_ROUTES:
        return (3, 11)
    if route in TEXT_ROUTES or route in BLANK_ROUTES:
        return (3,)
    return (3,)


def _run_tsv(
    image_path: Path,
    *,
    tesseract_cmd: str,
    psm: int,
    timeout_seconds: int,
) -> tuple[str, str | None]:
    from src.trace_net.tables.trace_net_table_ocr_bbox_sidecar_generator_v1 import (
        run_tesseract_tsv,
    )
    tsv_text, error = run_tesseract_tsv(
        image_path,
        tesseract_cmd=tesseract_cmd,
        lang="eng",
        psm=str(psm),
        oem=None,
        timeout_seconds=timeout_seconds,
    )
    return tsv_text or "", error


def build_coordinate_smoke(
    *,
    source_package: Path,
    manifest_cards_path: Path,
    output_dir: Path,
    tesseract_cmd: str,
    page_numbers: Sequence[int],
    timeout_seconds: int,
    expected_nonblank_pages: int,
    expected_blank_pages: int,
) -> dict[str, Any]:
    from src.trace_net.ocr.trace_net_coordinate_evidence_v1 import (
        BLANK_ROUTES,
        build_page_coordinate_evidence,
        summarize_coordinate_evidence,
    )
    from src.trace_net.ocr.trace_net_ocr_route_scan_pack_v1 import _iter_source_pages
    from src.trace_net.validation.trace_net_coordinate_evidence_quality_v1 import (
        evaluate_coordinate_evidence_quality,
    )

    manifest_by_page = _load_manifest_cards(manifest_cards_path)
    missing_manifest = [page for page in page_numbers if page not in manifest_by_page]
    if missing_manifest:
        raise RuntimeError(f"Manifest is missing selected pages: {missing_manifest}")

    pages = _iter_source_pages(source_package, page_numbers=set(page_numbers))
    page_by_number = {page.page_number: page for page in pages}
    missing_source = [page for page in page_numbers if page not in page_by_number]
    if missing_source:
        raise RuntimeError(f"Source package is missing selected pages: {missing_source}")

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_tsv_dir = output_dir / "raw_tsv"
    raw_tsv_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for completed, page_number in enumerate(page_numbers, 1):
        source_page = page_by_number[page_number]
        manifest_card = manifest_by_page[page_number]
        route = str(
            manifest_card.get("final_route")
            or manifest_card.get("primary_route")
            or ""
        )
        width, height = _image_size(source_page.image_bytes)
        payloads: dict[int, dict[str, Any]] = {}

        with tempfile.TemporaryDirectory(prefix="trace_net_coord6a_") as temp_dir:
            image_path = Path(temp_dir) / source_page.file_name
            image_path.write_bytes(source_page.image_bytes)

            for psm in _psm_plan(route):
                tsv_text, error = _run_tsv(
                    image_path,
                    tesseract_cmd=tesseract_cmd,
                    psm=psm,
                    timeout_seconds=timeout_seconds,
                )
                tsv_path = raw_tsv_dir / f"page_{page_number:03d}_psm{psm}.tsv"
                # Preserve a TSV sidecar even for a confirmed blank page.
                tsv_path.write_text(tsv_text, encoding="utf-8", newline="\n")
                payloads[psm] = {
                    "tsv_text": tsv_text,
                    "raw_tsv_path": str(tsv_path),
                    "raw_tsv_sha256": hashlib.sha256(
                        tsv_text.encode("utf-8")
                    ).hexdigest(),
                    "tesseract_status": "ok" if not error else "error",
                    "tesseract_error": error,
                }
                if error:
                    failures.append({
                        "page_number": page_number,
                        "psm": psm,
                        "error": error,
                    })

        record = build_page_coordinate_evidence(
            page_id=source_page.canonical_page_id,
            page_number=page_number,
            source_member=source_page.source_member,
            source_image_sha256=source_page.sha256,
            image_width=width,
            image_height=height,
            source_manifest_route=route,
            route_tsv_payloads=payloads,
        )
        record["manifest_card_source"] = str(manifest_cards_path)
        record["manifest_route_confidence"] = manifest_card.get("route_confidence")
        record["manifest_final_route_authority"] = manifest_card.get(
            "final_route_authority"
        )
        record["tesseract_failure_count"] = sum(
            1 for item in payloads.values() if item.get("tesseract_status") != "ok"
        )
        records.append(record)

        print(
            f"{completed}/{len(page_numbers)} "
            f"page={page_number} route={route} "
            f"words={record['coordinate_word_count']} "
            f"rows={record['table_row_candidate_count']} "
            f"callouts={record['visual_callout_candidate_count']} "
            f"blocks={record['normal_text_block_count']}",
            flush=True,
        )

    summary = summarize_coordinate_evidence(records)
    summary.update({
        "expected_page_count": len(page_numbers),
        "selected_pages": list(page_numbers),
        "tesseract_failure_count": len(failures),
        "raw_tsv_sidecar_count": len(list(raw_tsv_dir.glob("*.tsv"))),
        "source_package": str(source_package),
        "manifest_cards_path": str(manifest_cards_path),
        "output_dir": str(output_dir),
    })
    report = {
        "schema_version": "trace_net_coordinate_evidence_smoke_v1",
        "status": "TRACE_NET_COORDINATE_EVIDENCE_BUILT",
        "quality_status": "PENDING",
        "summary": summary,
        "records": records,
        "failures": failures,
        "safety_contract": {
            "routing_layer_frozen": True,
            "read_only_source_truth": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_answer_permission": True,
            "coordinate_records_are_derived_guidance": True,
        },
    }

    quality = evaluate_coordinate_evidence_quality(
        report,
        expected_pages=len(page_numbers),
        expected_nonblank_pages=expected_nonblank_pages,
        expected_blank_pages=expected_blank_pages,
    )
    if failures:
        quality["checks"]["tesseract_failures_zero"] = False
        quality["failures"].append("tesseract_failures_zero")
        quality["quality_status"] = "FAIL"
    else:
        quality["checks"]["tesseract_failures_zero"] = True

    report["quality_status"] = quality["quality_status"]
    report["status"] = (
        "TRACE_NET_COORDINATE_EVIDENCE_PASS"
        if quality["quality_status"] == "PASS"
        else "TRACE_NET_COORDINATE_EVIDENCE_NOT_READY"
    )
    report["quality"] = quality
    report["summary"]["quality_status"] = quality["quality_status"]

    _write_json(output_dir / "trace_net_coordinate_evidence_v1.json", report)
    _write_jsonl(
        output_dir / "trace_net_coordinate_evidence_v1_records.jsonl",
        records,
    )
    _write_json(
        output_dir / "trace_net_coordinate_evidence_v1_summary.json",
        summary,
    )
    _write_json(
        output_dir / "trace_net_coordinate_evidence_v1_quality.json",
        quality,
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build TRACE-Net Patch-6A route-aware coordinate evidence"
    )
    parser.add_argument("--source-package", required=True)
    parser.add_argument("--manifest-cards", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--tesseract-cmd", required=True)
    parser.add_argument("--page-numbers", default=DEFAULT_PAGE_NUMBERS)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--expected-nonblank-pages", type=int, default=18)
    parser.add_argument("--expected-blank-pages", type=int, default=2)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_coordinate_smoke(
        source_package=_normalize_git_bash_path(args.source_package),
        manifest_cards_path=_normalize_git_bash_path(args.manifest_cards),
        output_dir=_normalize_git_bash_path(args.output_dir),
        tesseract_cmd=str(_normalize_git_bash_path(args.tesseract_cmd)),
        page_numbers=_parse_page_numbers(args.page_numbers),
        timeout_seconds=args.timeout_seconds,
        expected_nonblank_pages=args.expected_nonblank_pages,
        expected_blank_pages=args.expected_blank_pages,
    )
    summary = report["summary"]
    print("")
    print(
        f"PATCH 6A FINAL: {report['quality_status']} "
        f"pages={summary['selected_page_count']} "
        f"words={summary['coordinate_word_count']} "
        f"rows={summary['table_row_candidate_count']} "
        f"callouts={summary['visual_callout_candidate_count']} "
        f"blocks={summary['normal_text_block_count']}",
        flush=True,
    )
    if report["quality_status"] != "PASS":
        print("FAILURES:", report["quality"]["failures"], flush=True)
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
