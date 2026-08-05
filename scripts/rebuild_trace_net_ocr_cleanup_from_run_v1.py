#!/usr/bin/env python3
"""Fast Patch-5.1 reclassification, manifest rebuild, and cleanup validation.

No Tesseract call is made. Existing full OCR sidecars, stored PSM-11 text, image
features, artifact evidence, and ink-route evidence are reused. The script:

1. Reclassifies all completed scan-pack records with the patched algorithm.
2. Rebuilds the canonical page-route manifest.
3. Rebuilds Patch-5.1 cleanup records from full OCR sidecars.
4. Runs route and cleanup semantic acceptance gates.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--baseline-json", type=Path, required=True)
    parser.add_argument("--artifact-detector", type=Path)
    parser.add_argument("--page-ink-route-evidence", type=Path)
    parser.add_argument("--expected-pages", type=int, default=509)
    args = parser.parse_args()

    repo_root = Path.cwd()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from src.trace_net.ingestion.trace_net_page_route_manifest_v1 import (
        build_page_route_manifest_report,
    )
    from src.trace_net.ocr.trace_net_ocr_cleanup_extraction_v1 import (
        build_cleanup_extraction,
    )
    from src.trace_net.ocr.trace_net_ocr_route_scan_pack_v1 import (
        _classify_route,
        _supplemental_cross_psm_signal,
    )
    from src.trace_net.validation.trace_net_ocr_cleanup_semantic_checker_v1 import (
        evaluate_cleanup_semantics,
    )
    from src.trace_net.validation.trace_net_ocr_route_baseline_checker_v1 import (
        check_acceptance_gates,
        evaluate,
        load_baseline,
    )

    run_dir = args.run_dir.resolve()
    scan_path = run_dir / "scan_pack_records.jsonl"
    artifact_detector = (
        args.artifact_detector.resolve()
        if args.artifact_detector
        else repo_root
        / "local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json"
    )
    ink_evidence = (
        args.page_ink_route_evidence.resolve()
        if args.page_ink_route_evidence
        else repo_root
        / "local_data/organization/trace_net/page_ink_route_evidence/trace_net_page_ink_route_evidence_v1.json"
    )
    for required in (scan_path, args.baseline_json, artifact_detector, ink_evidence):
        if not required.exists():
            raise FileNotFoundError(required)

    source_records = read_jsonl(scan_path)
    if len(source_records) != args.expected_pages:
        raise RuntimeError(
            f"expected {args.expected_pages} scan records, found {len(source_records)}"
        )

    reclassified: list[dict[str, Any]] = []
    full_text_by_page: dict[int, str] = {}
    sidecar_status_by_page: dict[int, str] = {}
    for index, source in enumerate(source_records, 1):
        page = int(source["canonical_page_number"])
        text_path_value = source.get("ocr_text_path")
        text_path = Path(str(text_path_value)) if text_path_value else None
        if text_path and text_path.exists():
            primary_text = text_path.read_text(encoding="utf-8")
            sidecar_status = "present"
        elif (
            str(source.get("accepted_route")) == "blank_candidate"
            and int(source.get("ocr_text_word_count") or 0) == 0
        ):
            primary_text = ""
            sidecar_status = "missing_confirmed_blank"
        else:
            raise FileNotFoundError(
                f"nonblank OCR sidecar missing for page {page}: {text_path_value}"
            )

        supplemental = _supplemental_cross_psm_signal(
            primary_text,
            str(source.get("tesseract_supplemental_psm11_raw_text") or ""),
        )
        route, confidence, reasons = _classify_route(
            text=primary_text,
            image_features=source,
            tesseract_status=source.get("tesseract_execution_status"),
            supplemental=supplemental,
        )
        updated = dict(source)
        updated["accepted_route"] = route
        updated["route_confidence"] = round(float(confidence), 4)
        updated["route_reasons"] = reasons
        updated["ocr_sample_text"] = primary_text[:1000]
        updated["patch5_1_reclassified_without_tesseract"] = True
        reclassified.append(updated)
        full_text_by_page[page] = primary_text
        sidecar_status_by_page[page] = sidecar_status
        if index % 50 == 0 or index == len(source_records):
            print(f"RECLASSIFY {index}/{len(source_records)}", flush=True)

    scan_records_out = run_dir / "scan_pack_records_patch5_1.jsonl"
    scan_report_out = run_dir / "scan_pack_report_patch5_1.json"
    write_jsonl(scan_records_out, reclassified)
    write_json(
        scan_report_out,
        {
            "module": "trace_net_ocr_patch5_1_fast_reclassify",
            "status": "TRACE_NET_OCR_PATCH5_1_RECLASSIFIED",
            "record_count": len(reclassified),
            "records": reclassified,
            "tesseract_rerun": False,
        },
    )

    baseline_records = load_baseline(args.baseline_json)
    scan_predictions = {
        int(record["canonical_page_number"]): record.get("accepted_route")
        for record in reclassified
    }
    scan_evaluation = evaluate(baseline_records, scan_predictions)
    scan_gates = check_acceptance_gates(scan_evaluation)

    manifest_dir = run_dir / "canonical_manifest_patch5_1"
    manifest = build_page_route_manifest_report(
        artifact_detector=artifact_detector,
        output_dir=manifest_dir,
        page_ink_route_evidence=ink_evidence,
        write_outputs=True,
        ocr_route_scan_pack=scan_report_out,
    )
    final_routes = {
        int(card["page_number"]): card.get("final_route") or card.get("primary_route")
        for card in manifest.get("page_route_cards") or []
        if card.get("page_number")
    }
    manifest_evaluation = evaluate(baseline_records, final_routes)
    manifest_gates = check_acceptance_gates(manifest_evaluation)
    manifest_gates["accuracy_at_least_98_43"] = (
        manifest_evaluation["overall_coarse_route_accuracy"] >= 0.9843
    )
    manifest_gates["table_recall_at_least_99"] = (
        manifest_evaluation["table_recall"] >= 0.99
    )
    # Patch 5.1 specifically closes the two final known route mismatches. Do not
    # report the patch PASS merely because the older broad 98.43% gate still passes.
    manifest_gates["manifest_exact_509"] = (
        manifest_evaluation["total_pages"] == args.expected_pages
        and manifest_evaluation["exact_matches"] == args.expected_pages
    )
    manifest_gates["manifest_quality_pass"] = manifest.get("quality_status") == "PASS"
    scan_gates["scan_at_least_496_of_509"] = (
        scan_evaluation["total_pages"] == args.expected_pages
        and scan_evaluation["exact_matches"] >= min(args.expected_pages, 496)
    )
    scan_gates["all_passed"] = all(
        value for key, value in scan_gates.items() if key != "all_passed"
    )
    manifest_gates["all_passed"] = all(
        value for key, value in manifest_gates.items() if key != "all_passed"
    )
    route_mismatches = [
        {
            "page_number": int(row["page_number"]),
            "expected_route": row["expected_coarse_route"],
            "expected_subtype": row.get("expected_subtype"),
            "predicted_route": final_routes.get(int(row["page_number"])),
        }
        for row in baseline_records
        if final_routes.get(int(row["page_number"])) != row["expected_coarse_route"]
    ]

    cleanup_rows: list[dict[str, Any]] = []
    for index, record in enumerate(reclassified, 1):
        page = int(record["canonical_page_number"])
        primary_text = full_text_by_page[page]
        cleanup_input = dict(record)
        cleanup_input["primary_ocr_text"] = primary_text
        cleanup_input["best_ocr_text"] = primary_text
        cleanup_input["ocr_sample_text"] = primary_text
        final_route = final_routes.get(page) or record.get("accepted_route")
        cleanup = build_cleanup_extraction(
            cleanup_input,
            final_route=final_route,
            has_reconstructed_rows=False,
        )
        cleanup_rows.append(
            {
                "canonical_page_number": page,
                "page_id": record.get("page_id"),
                "source_page_id": record.get("source_page_id"),
                "scan_pack_route": record.get("accepted_route"),
                "canonical_final_route": final_route,
                "ocr_sidecar_status": sidecar_status_by_page[page],
                "primary_ocr_text_path": record.get("ocr_text_path"),
                "primary_ocr_text": primary_text,
                "cleanup_extraction": cleanup,
            }
        )
        if index % 50 == 0 or index == len(reclassified):
            print(f"CLEANUP {index}/{len(reclassified)}", flush=True)

    cleanup_out = run_dir / "cleanup_records_patch5_1.jsonl"
    semantic_out = run_dir / "cleanup_semantic_quality_patch5_1.json"
    route_out = run_dir / "route_quality_patch5_1.json"
    final_out = run_dir / "final_summary_patch5_1.json"
    write_jsonl(cleanup_out, cleanup_rows)
    semantic = evaluate_cleanup_semantics(cleanup_rows, baseline_records)
    write_json(semantic_out, semantic)
    write_json(
        route_out,
        {
            "scan_evaluation": scan_evaluation,
            "scan_gates": scan_gates,
            "manifest_evaluation": manifest_evaluation,
            "manifest_gates": manifest_gates,
            "remaining_mismatches": route_mismatches,
        },
    )

    overall_pass = bool(
        semantic.get("quality_status") == "PASS"
        and manifest_gates.get("all_passed")
    )
    final_summary = {
        "quality_status": "PASS" if overall_pass else "FAIL",
        "tesseract_rerun": False,
        "record_count": len(reclassified),
        "scan_evaluation": scan_evaluation,
        "manifest_evaluation": manifest_evaluation,
        "manifest_gates": manifest_gates,
        "remaining_mismatches": route_mismatches,
        "cleanup_semantic_quality": semantic,
        "artifacts": {
            "scan_records": str(scan_records_out),
            "scan_report": str(scan_report_out),
            "manifest_dir": str(manifest_dir),
            "cleanup_records": str(cleanup_out),
            "route_quality": str(route_out),
            "semantic_quality": str(semantic_out),
        },
    }
    write_json(final_out, final_summary)

    print("")
    print(
        "PATCH 5.1 FINAL:",
        final_summary["quality_status"],
        f"scan={scan_evaluation['exact_matches']}/{scan_evaluation['total_pages']}",
        f"manifest={manifest_evaluation['exact_matches']}/{manifest_evaluation['total_pages']}",
    )
    print("MISMATCHES:", route_mismatches)
    print("SUMMARY:", final_out)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
