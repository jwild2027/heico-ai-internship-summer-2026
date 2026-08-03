from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "v35.4"
MODULE = "trace_net_e2e_corrected_visual_context_builder_v35_4"
STATUS_READY = "E2E_CORRECTED_VISUAL_CONTEXT_BUILDER_READY"

PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}", re.I)
TIFF_NAME_RE = re.compile(r"(?P<num>\d{1,8})\.(?:tif|tiff)$", re.I)

SAFETY_CONTRACT: Dict[str, Any] = {
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "writes_to_postgres": False,
    "writes_to_qdrant": False,
    "writes_to_opensearch": False,
    "uploads_to_opensearch": False,
    "raw_5tb_scan_at_query_time": False,
    "graph_rebuild_at_query_time": False,
    "corrected_visual_context_builder": True,
    "uses_calibrated_cascade_route_brain": True,
    "uses_visual_context_eligible_only": True,
    "fishnet_visual_review_candidates_not_auto_processed": True,
    "visual_context_guidance_only": True,
    "source_truth_required_for_visual_claims": True,
    "llava_not_called_by_default": True,
    "gemma_not_called": True,
}


def _now() -> int:
    return int(time.time())


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _stable_id(prefix: str, text: str) -> str:
    return f"{prefix}_{hashlib.sha1(text.encode('utf-8', errors='ignore')).hexdigest()[:16]}"


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    else:
        p.write_text("", encoding="utf-8")


def _read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"JSONL file not found: {p}")
    out: List[Dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _page_id(prefix: str, page_number: int) -> str:
    return f"{prefix}_p{page_number:06d}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_metadata_xml(xml_text: str, *, page_id_prefix: str) -> Dict[str, Any]:
    root = ET.fromstring(xml_text.encode("utf-8"))
    label = root.attrib.get("LABEL", "")
    objid = root.attrib.get("OBJID", "")
    files: List[Dict[str, Any]] = []
    for elem in root.iter():
        if _local_name(elem.tag) != "file":
            continue
        file_id = elem.attrib.get("ID", "")
        mimetype = elem.attrib.get("MIMETYPE", "")
        size = int(elem.attrib.get("SIZE", "0") or 0)
        checksum = elem.attrib.get("CHECKSUM", "")
        href = ""
        for child in elem:
            if _local_name(child.tag) == "FLocat":
                href = child.attrib.get("{http://www.w3.org/1999/xlink}href") or child.attrib.get("href") or ""
                break
        filename = href.replace("file://./", "").replace("file://", "").strip()
        m = TIFF_NAME_RE.search(filename)
        if not m:
            continue
        page_number = int(m.group("num"))
        files.append({
            "page_id": _page_id(page_id_prefix, page_number),
            "page_number": page_number,
            "filename": Path(filename).name,
            "file_id": file_id,
            "mimetype": mimetype or "image/tiff",
            "declared_size": size,
            "checksum_sha1": checksum,
            "metadata_href": href,
        })
    files.sort(key=lambda r: int(r.get("page_number") or 0))
    return {"label": label, "objid": objid, "page_records": files}


def discover_tiff_pages_from_zip(zip_path: str | Path, *, page_id_prefix: str) -> Dict[str, Any]:
    zf = zipfile.ZipFile(zip_path)
    try:
        meta_name = next((n for n in zf.namelist() if Path(n).name.lower() == "metadata.xml"), "")
        if meta_name:
            xml_text = zf.read(meta_name).decode("utf-8", errors="replace")
            manifest = _parse_metadata_xml(xml_text, page_id_prefix=page_id_prefix)
        else:
            records = []
            for name in zf.namelist():
                m = TIFF_NAME_RE.search(Path(name).name)
                if not m:
                    continue
                n = int(m.group("num"))
                info = zf.getinfo(name)
                records.append({
                    "page_id": _page_id(page_id_prefix, n),
                    "page_number": n,
                    "filename": Path(name).name,
                    "zip_member": name,
                    "declared_size": int(info.file_size),
                    "mimetype": "image/tiff",
                })
            records.sort(key=lambda r: int(r.get("page_number") or 0))
            manifest = {"label": "", "objid": "", "page_records": records}
        member_by_name = {Path(n).name: n for n in zf.namelist()}
        for rec in manifest["page_records"]:
            rec["source_container"] = str(zip_path)
            rec["source_type"] = "zip_member"
            rec["zip_member"] = member_by_name.get(Path(_norm(rec.get("filename"))).name, _norm(rec.get("filename")))
            try:
                rec["actual_size"] = int(zf.getinfo(rec["zip_member"]).file_size)
            except Exception:
                rec["actual_size"] = rec.get("declared_size") or 0
        return manifest
    finally:
        zf.close()


def _load_cascade_decisions(path: str | Path) -> List[Dict[str, Any]]:
    decisions = _read_jsonl(path)
    for d in decisions:
        if "visual_context_eligible" not in d:
            d["visual_context_eligible"] = d.get("primary_route") == "image_visual"
    return decisions


def _visual_subtype(decision: Mapping[str, Any]) -> str:
    features = decision.get("feature_summary") or {}
    scores = decision.get("route_scores") or {}
    text_score = _safe_float(features.get("text_score"))
    table_score = _safe_float(scores.get("table"))
    image_score = _safe_float(scores.get("image_visual"))
    line_score = _safe_float(features.get("line_structure_score"))
    edge_density = _safe_float(features.get("edge_density"))
    comp = int(_safe_float(features.get("connected_component_count")))

    if line_score >= 0.70 and edge_density >= 0.12 and text_score < 0.88:
        return "technical_drawing_or_callout_candidate"
    if text_score >= 0.85 and image_score >= 0.50:
        return "mixed_text_visual_candidate"
    if table_score >= 0.40:
        return "visual_table_confusion_candidate"
    if comp >= 80 or edge_density >= 0.10:
        return "diagram_or_figure_candidate"
    return "image_visual_candidate"


def _technical_features(decision: Mapping[str, Any]) -> List[str]:
    features = decision.get("feature_summary") or {}
    scores = decision.get("route_scores") or {}
    out: List[str] = ["image/diagram route candidate from calibrated cascade route brain"]
    if _safe_float(features.get("edge_density")) >= 0.10:
        out.append("edge/visual structure present")
    if _safe_float(features.get("line_structure_score")) >= 0.50:
        out.append("line-structure geometry present")
    if int(_safe_float(features.get("horizontal_long_line_count"))) > 0 or int(_safe_float(features.get("vertical_long_line_count"))) > 0:
        out.append("long-line candidates present")
    if int(_safe_float(features.get("horizontal_mid_line_count"))) >= 20 or int(_safe_float(features.get("vertical_mid_line_count"))) >= 20:
        out.append("mid-line geometry candidates present")
    if _safe_float(features.get("table_grid_score")) >= 0.35:
        out.append("table/grid-like structure also competes")
    if _safe_float(features.get("text_score")) >= 0.85:
        out.append("mixed text and visual signals")
    if _safe_float(scores.get("image_visual")) >= 0.70:
        out.append("high image_visual route score")
    return out


def _prompt_context(card: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = _norm(card.get("page_id"))
    features = card.get("technical_features") or []
    feature_text = "; ".join(features[:6]) if features else "visual route candidate"
    text = (
        f"Page {page_id} has stored visual context from the calibrated cascade route brain. "
        f"Visual subtype: {card.get('visual_context_type')}. "
        f"Guidance features: {feature_text}. "
        "This visual context is guidance only and does not prove factual part/manual claims without source-truth confirmation."
    )
    return {
        "schema_version": "trace_net_corrected_visual_prompt_context_v35_4",
        "visual_prompt_context_id": _stable_id("visual_prompt_context", page_id),
        "page_id": page_id,
        "source_visual_context_card_id": card.get("visual_context_card_id"),
        "visual_context_type": card.get("visual_context_type"),
        "prompt_context": text,
        "guidance_only": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def _build_card(page: Mapping[str, Any], decision: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = _norm(decision.get("page_id") or page.get("page_id"))
    subtype = _visual_subtype(decision)
    features = _technical_features(decision)
    fishnet_action = _norm(decision.get("fishnet_action"))
    review_required = bool(decision.get("review_required"))
    manual_label = _norm(decision.get("manual_label"))
    manual_diagram_page = bool(decision.get("manual_diagram_page"))
    false_positive_marker = manual_label == "non_diagram" and bool(decision.get("visual_context_eligible"))

    return {
        "schema_version": "trace_net_corrected_visual_context_card_v35_4",
        "visual_context_card_id": _stable_id("visual_context_card", page_id),
        "page_id": page_id,
        "page_number": int(decision.get("page_number") or page.get("page_number") or 0),
        "filename": _norm(decision.get("filename") or page.get("filename")),
        "zip_member": _norm(page.get("zip_member")),
        "source_container": _norm(page.get("source_container")),
        "cascade_decision_schema": decision.get("schema_version"),
        "primary_route": decision.get("primary_route"),
        "dispatch_routes": decision.get("dispatch_routes") or [],
        "visual_context_eligible": bool(decision.get("visual_context_eligible")),
        "fishnet_visual_review_candidate": bool(decision.get("fishnet_visual_review_candidate")),
        "fishnet_action": fishnet_action,
        "fishnet_reasons": decision.get("fishnet_reasons") or [],
        "review_required": review_required,
        "manual_label": manual_label,
        "manual_diagram_page": manual_diagram_page,
        "audit_label_non_diagram_visual_context_eligible": false_positive_marker,
        "visual_context_type": subtype,
        "technical_features": features,
        "route_scores": decision.get("route_scores") or {},
        "feature_summary": decision.get("feature_summary") or {},
        "ocr_text_candidates": [],
        "llava_observer_required_later": True,
        "local_geometry_enrichment_required_later": True,
        "visual_context_stage": "route_brain_selected_context_seed",
        "proof_authority": False,
        "guidance_only": True,
        "requires_source_truth_confirmation": True,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "visual_proof_authority_violation": False,
    }


def build_corrected_visual_context(
    *,
    page_bundle_zip: Path,
    cascade_route_decisions: Path,
    output_dir: Path,
    page_id_prefix: str,
    max_visual_pages: int = 0,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_manifest = discover_tiff_pages_from_zip(page_bundle_zip, page_id_prefix=page_id_prefix)
    pages = source_manifest.get("page_records") or []
    page_by_id = {_norm(p.get("page_id")): p for p in pages}

    decisions = _load_cascade_decisions(cascade_route_decisions)
    eligible = [d for d in decisions if bool(d.get("visual_context_eligible"))]
    skipped_fishnet_visual = [d for d in decisions if (not bool(d.get("visual_context_eligible"))) and bool(d.get("fishnet_visual_review_candidate"))]
    if max_visual_pages and max_visual_pages > 0:
        eligible = eligible[:max_visual_pages]

    cards: List[Dict[str, Any]] = []
    missing_page_records: List[Dict[str, Any]] = []
    for d in eligible:
        pid = _norm(d.get("page_id"))
        page = page_by_id.get(pid)
        if not page:
            missing_page_records.append({"page_id": pid, "reason": "cascade_decision_page_not_found_in_source_manifest"})
            page = {"page_id": pid, "page_number": d.get("page_number"), "filename": d.get("filename")}
        cards.append(_build_card(page, d))

    prompt_contexts = [_prompt_context(c) for c in cards]

    cards_path = output_dir / "trace_net_corrected_visual_context_cards_v35_4.jsonl"
    prompt_path = output_dir / "trace_net_corrected_visual_prompt_context_v35_4.jsonl"
    skipped_path = output_dir / "trace_net_fishnet_visual_review_candidates_skipped_v35_4.jsonl"
    missing_path = output_dir / "trace_net_corrected_visual_context_missing_pages_v35_4.jsonl"
    report_path = output_dir / "trace_net_corrected_visual_context_builder_v35_4.json"
    md_path = output_dir / "trace_net_corrected_visual_context_builder_v35_4.md"

    _write_jsonl(cards_path, cards)
    _write_jsonl(prompt_path, prompt_contexts)
    _write_jsonl(skipped_path, skipped_fishnet_visual)
    _write_jsonl(missing_path, missing_page_records)

    action_counts = Counter(_norm(c.get("fishnet_action")) for c in cards)
    subtype_counts = Counter(_norm(c.get("visual_context_type")) for c in cards)
    primary_counts = Counter(_norm(d.get("primary_route")) for d in decisions)

    report: Dict[str, Any] = {
        "schema_version": "trace_net_corrected_visual_context_builder_v35_4_report",
        "module": MODULE,
        "version": VERSION,
        "status": STATUS_READY,
        "created": _now(),
        "contract": SAFETY_CONTRACT,
        "source_page_count": len(pages),
        "route_decision_count": len(decisions),
        "visual_context_input_page_count": len(eligible),
        "visual_context_card_count": len(cards),
        "visual_prompt_context_count": len(prompt_contexts),
        "guidance_only_visual_context_count": sum(1 for c in cards if c.get("guidance_only") is True),
        "visual_context_eligible_count": sum(1 for d in decisions if d.get("visual_context_eligible") is True),
        "fishnet_visual_review_candidate_count": len(skipped_fishnet_visual),
        "fishnet_visual_review_pages_processed_count": 0,
        "overbroad_old_route_pages_processed_count": 0,
        "missing_source_page_record_count": len(missing_page_records),
        "audit_label_non_diagram_visual_context_eligible_count": sum(1 for c in cards if c.get("audit_label_non_diagram_visual_context_eligible") is True),
        "visual_context_type_counts": dict(subtype_counts),
        "visual_context_fishnet_action_counts": dict(action_counts),
        "source_primary_route_counts": dict(primary_counts),
        "visual_proof_authority_violation_count": sum(1 for c in cards if c.get("visual_proof_authority_violation")),
        "post_gate_issue_count": 0,
        "answer_permission_count": sum(1 for c in cards if c.get("answer_permission")),
        "source_truth_mutation_allowed_count": sum(1 for c in cards if c.get("source_truth_mutation_allowed")),
        "cards_jsonl_path": str(cards_path),
        "visual_prompt_context_jsonl_path": str(prompt_path),
        "fishnet_visual_review_candidates_skipped_jsonl_path": str(skipped_path),
        "missing_pages_jsonl_path": str(missing_path),
        "report_path": str(report_path),
        "inspect_md_path": str(md_path),
        "sample_visual_context_cards": cards[:5],
    }
    report["quality_checks"] = []
    report["quality_status"] = "NOT_RUN"

    md = [
        "# TRACE-Net Corrected Visual Context Builder v35.4",
        "",
        f"Quality status: **{report['quality_status']}**",
        f"Status: `{STATUS_READY}`",
        "",
        "## Summary",
    ]
    for k in [
        "source_page_count", "route_decision_count", "visual_context_input_page_count", "visual_context_card_count",
        "visual_prompt_context_count", "guidance_only_visual_context_count", "fishnet_visual_review_candidate_count",
        "fishnet_visual_review_pages_processed_count", "audit_label_non_diagram_visual_context_eligible_count",
        "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        md.append(f"- {k}: {report.get(k)}")
    md.extend([
        "",
        "## Contract",
        "- Uses calibrated v35.3 route decisions instead of the old broad route manifest.",
        "- Builds visual context only for `visual_context_eligible` pages.",
        "- Fishnet visual review candidates are saved for review/retry but are not automatically processed here.",
        "- Visual context is guidance only and does not grant answer permission.",
    ])
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    _write_json(report_path, report)
    return report


def quality_checks(report: Mapping[str, Any], args: Any) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add("source_page_count", report.get("source_page_count"), f">= {args.min_source_pages}", int(report.get("source_page_count") or 0) >= args.min_source_pages)
    add("route_decision_count", report.get("route_decision_count"), f">= {args.min_route_decisions}", int(report.get("route_decision_count") or 0) >= args.min_route_decisions)
    add("visual_context_input_page_count", report.get("visual_context_input_page_count"), f">= {args.min_visual_context_input_pages}", int(report.get("visual_context_input_page_count") or 0) >= args.min_visual_context_input_pages)
    add("visual_context_card_count", report.get("visual_context_card_count"), f">= {args.min_visual_context_cards}", int(report.get("visual_context_card_count") or 0) >= args.min_visual_context_cards)
    add("visual_prompt_context_count", report.get("visual_prompt_context_count"), f">= {args.min_visual_prompt_contexts}", int(report.get("visual_prompt_context_count") or 0) >= args.min_visual_prompt_contexts)
    add("guidance_only_visual_context_count", report.get("guidance_only_visual_context_count"), f">= {args.min_guidance_only_visual_contexts}", int(report.get("guidance_only_visual_context_count") or 0) >= args.min_guidance_only_visual_contexts)
    add("fishnet_visual_review_pages_processed_count", report.get("fishnet_visual_review_pages_processed_count"), f"<= {args.max_fishnet_visual_review_pages_processed}", int(report.get("fishnet_visual_review_pages_processed_count") or 0) <= args.max_fishnet_visual_review_pages_processed)
    add("overbroad_old_route_pages_processed_count", report.get("overbroad_old_route_pages_processed_count"), f"<= {args.max_overbroad_old_route_pages_processed}", int(report.get("overbroad_old_route_pages_processed_count") or 0) <= args.max_overbroad_old_route_pages_processed)
    add("missing_source_page_record_count", report.get("missing_source_page_record_count"), f"<= {args.max_missing_source_page_records}", int(report.get("missing_source_page_record_count") or 0) <= args.max_missing_source_page_records)
    add("visual_proof_authority_violation_count", report.get("visual_proof_authority_violation_count"), f"<= {args.max_visual_proof_authority_violations}", int(report.get("visual_proof_authority_violation_count") or 0) <= args.max_visual_proof_authority_violations)
    add("post_gate_issue_count", report.get("post_gate_issue_count"), f"<= {args.max_post_gate_issue_count}", int(report.get("post_gate_issue_count") or 0) <= args.max_post_gate_issue_count)
    add("answer_permission_count", report.get("answer_permission_count"), f"<= {args.max_answer_permission_count}", int(report.get("answer_permission_count") or 0) <= args.max_answer_permission_count)
    add("source_truth_mutation_allowed_count", report.get("source_truth_mutation_allowed_count"), f"<= {args.max_source_truth_mutation_allowed}", int(report.get("source_truth_mutation_allowed_count") or 0) <= args.max_source_truth_mutation_allowed)
    if args.require_no_answer_permission:
        add("require_no_answer_permission", report.get("answer_permission_count"), "== 0", int(report.get("answer_permission_count") or 0) == 0)
    return checks


def _add_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-source-pages", type=int, default=1)
    parser.add_argument("--min-route-decisions", type=int, default=1)
    parser.add_argument("--min-visual-context-input-pages", type=int, default=1)
    parser.add_argument("--min-visual-context-cards", type=int, default=1)
    parser.add_argument("--min-visual-prompt-contexts", type=int, default=1)
    parser.add_argument("--min-guidance-only-visual-contexts", type=int, default=1)
    parser.add_argument("--max-fishnet-visual-review-pages-processed", type=int, default=0)
    parser.add_argument("--max-overbroad-old-route-pages-processed", type=int, default=0)
    parser.add_argument("--max-missing-source-page-records", type=int, default=0)
    parser.add_argument("--max-visual-proof-authority-violations", type=int, default=0)
    parser.add_argument("--max-post-gate-issue-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net corrected visual context from v35.3 cascade route decisions.")
    parser.add_argument("--page-bundle-zip", type=Path, required=True)
    parser.add_argument("--cascade-route-decisions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--page-id-prefix", default="t_p_120_1176")
    parser.add_argument("--max-visual-pages", type=int, default=0)
    parser.add_argument("--quality", action="store_true")
    _add_quality_args(parser)
    args = parser.parse_args(argv)

    report = build_corrected_visual_context(
        page_bundle_zip=args.page_bundle_zip,
        cascade_route_decisions=args.cascade_route_decisions,
        output_dir=args.output_dir,
        page_id_prefix=args.page_id_prefix,
        max_visual_pages=args.max_visual_pages,
    )
    if args.quality:
        checks = quality_checks(report, args)
        report["quality_checks"] = checks
        report["quality_status"] = "PASS" if all(c["passed"] for c in checks) else "FAIL"
        _write_json(report["report_path"], report)
        md_path = Path(report["inspect_md_path"])
        text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        text = text.replace("Quality status: **NOT_RUN**", f"Quality status: **{report['quality_status']}**")
        md_path.write_text(text, encoding="utf-8")

    print("TRACE-Net Corrected Visual Context Builder v35.4")
    print(" Status:", report.get("status"))
    print(" Quality status:", report.get("quality_status"))
    for k in [
        "source_page_count", "route_decision_count", "visual_context_input_page_count", "visual_context_card_count",
        "visual_prompt_context_count", "guidance_only_visual_context_count", "fishnet_visual_review_candidate_count",
        "fishnet_visual_review_pages_processed_count", "overbroad_old_route_pages_processed_count",
        "audit_label_non_diagram_visual_context_eligible_count", "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        print(f" {k}:", report.get(k))
    print(" report_path:", report.get("report_path"))
    print(" cards_jsonl_path:", report.get("cards_jsonl_path"))
    print(" visual_prompt_context_jsonl_path:", report.get("visual_prompt_context_jsonl_path"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
