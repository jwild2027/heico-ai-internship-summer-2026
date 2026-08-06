from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "v35.1"
MODULE = "trace_net_e2e_route_brain_image_page_audit_v35_1"
STATUS_READY = "E2E_ROUTE_BRAIN_IMAGE_PAGE_AUDIT_READY"

PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}", re.I)
TIFF_NAME_RE = re.compile(r"(?P<num>\d{1,8})\.(?:tif|tiff)$", re.I)
SIMPLE_ROUTE_VALUES = {
    "blank_candidate", "table", "image_visual", "normal_text", "review",
    "diagram", "diagram_candidate", "callout_diagram_candidate",
    "technical_drawing_candidate", "engineering_drawing_candidate", "mechanical_drawing_candidate",
}
VISUAL_ROUTE_VALUES = {
    "image_visual", "diagram", "diagram_candidate", "callout_diagram_candidate",
    "technical_drawing_candidate", "engineering_drawing_candidate", "mechanical_drawing_candidate",
}
NON_VISUAL_ROUTE_VALUES = {"table", "normal_text", "blank_candidate"}

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
    "route_brain_audit_only": True,
    "manual_screened_diagram_truthset_supported": True,
    "diagram_pages_are_guidance_labels_not_source_truth_claims": True,
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
    return ""


def _lower(value: Any) -> str:
    return _norm(value).lower()


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


def _read_json(path: str | Path | None) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _walk_json(obj: Any) -> Iterable[Any]:
    yield obj
    if isinstance(obj, Mapping):
        for v in obj.values():
            yield from _walk_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_json(v)


def _extract_page_id(value: Any) -> str:
    if isinstance(value, str):
        text = value
    elif isinstance(value, Mapping):
        # Prefer direct page fields before rendering nested records.
        for key in ("page_id", "source_page_id", "target_page_id"):
            pid = _norm(value.get(key))
            if PAGE_ID_RE.fullmatch(pid):
                return pid
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    m = PAGE_ID_RE.search(text)
    return m.group(0) if m else ""


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
        href = ""
        for child in elem:
            if _local_name(child.tag) == "FLocat":
                href = child.attrib.get("{http://www.w3.org/1999/xlink}href") or child.attrib.get("href") or ""
                break
        filename = href.replace("file://./", "").replace("file://", "").strip()
        m = TIFF_NAME_RE.search(Path(filename).name)
        if not m:
            continue
        page_number = int(m.group("num"))
        files.append({
            "page_id": _page_id(page_id_prefix, page_number),
            "page_number": page_number,
            "filename": Path(filename).name,
            "metadata_href": href,
            "declared_size": int(elem.attrib.get("SIZE", "0") or 0),
            "checksum_sha1": elem.attrib.get("CHECKSUM", ""),
        })
    files.sort(key=lambda r: int(r.get("page_number") or 0))
    return {"label": label, "objid": objid, "page_records": files}


def discover_tiff_pages_from_zip(zip_path: str | Path, *, page_id_prefix: str) -> Dict[str, Any]:
    with zipfile.ZipFile(zip_path) as zf:
        meta_name = next((n for n in zf.namelist() if Path(n).name.lower() == "metadata.xml"), "")
        if meta_name:
            manifest = _parse_metadata_xml(zf.read(meta_name).decode("utf-8", errors="replace"), page_id_prefix=page_id_prefix)
        else:
            records: List[Dict[str, Any]] = []
            for name in zf.namelist():
                m = TIFF_NAME_RE.search(Path(name).name)
                if not m:
                    continue
                n = int(m.group("num"))
                records.append({"page_id": _page_id(page_id_prefix, n), "page_number": n, "filename": Path(name).name})
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
                rec["actual_size"] = int(rec.get("declared_size") or 0)
        return manifest


def _add_route(routes: List[str], value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _add_route(routes, item)
        return
    if isinstance(value, Mapping):
        # Route policy maps have nested objects. Only extract explicit route labels
        # from the nested records, never stringify the whole dict as a route.
        if "route" in value:
            _add_route(routes, value.get("route"))
        if "primary_route" in value:
            _add_route(routes, value.get("primary_route"))
        if "primary_dispatch_route" in value:
            _add_route(routes, value.get("primary_dispatch_route"))
        if "dispatch_routes" in value:
            _add_route(routes, value.get("dispatch_routes"))
        return
    route = _lower(value)
    if not route:
        return
    if route in SIMPLE_ROUTE_VALUES or any(token in route for token in ("image_visual", "diagram", "drawing", "callout")):
        if route not in routes:
            routes.append(route)


def _route_fields_from_obj(obj: Mapping[str, Any]) -> Tuple[List[str], int]:
    routes: List[str] = []
    # v35.1 hotfix: nested route/policy structures are normal in the
    # route dispatch manifest. They should not be counted as malformed just
    # because a particular nested object/list does not itself add a new route.
    # Malformed is reserved for route values that are actually stringified JSON
    # or unsafe/non-route objects leaked into route labels.
    malformed = 0
    for key in (
        "primary_dispatch_route", "primary_route", "page_route", "route", "route_label", "route_type",
        "dispatch_route", "dispatch_routes", "allowed_dispatch_routes", "secondary_routes", "visual_type",
    ):
        if key in obj:
            value = obj.get(key)
            if isinstance(value, str) and value.strip().startswith(("{", "[")):
                malformed += 1
                continue
            _add_route(routes, value)
    # Also inspect route_policies safely.
    policies = obj.get("route_policies")
    if isinstance(policies, Mapping):
        for policy in policies.values():
            _add_route(routes, policy)
    return routes, malformed


def load_route_index(route_manifest_path: str | Path | None) -> Tuple[Dict[str, Dict[str, Any]], int]:
    data = _read_json(route_manifest_path)
    out: Dict[str, Dict[str, Any]] = {}
    malformed_route_value_count = 0
    if not data:
        return out, malformed_route_value_count
    for obj in _walk_json(data):
        if not isinstance(obj, Mapping):
            continue
        pid = _extract_page_id(obj)
        if not pid:
            continue
        routes, malformed = _route_fields_from_obj(obj)
        malformed_route_value_count += malformed
        if not routes:
            continue
        rec = out.setdefault(pid, {"page_id": pid, "routes": [], "source_records": 0})
        for route in routes:
            if route not in rec["routes"]:
                rec["routes"].append(route)
        rec["source_records"] += 1
    return out, malformed_route_value_count


def load_manual_diagram_truthset(path: str | Path | None) -> Dict[str, Dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = _norm(row.get("page_id")) or _page_id("t_p_120_1176", int(row.get("page_number") or 0))
            if not PAGE_ID_RE.fullmatch(pid):
                continue
            out[pid] = dict(row)
    return out


def _has_route(routes: Sequence[str], names: set[str]) -> bool:
    lowered = [_lower(r) for r in routes]
    for r in lowered:
        if r in names:
            return True
        if names & VISUAL_ROUTE_VALUES and any(tok in r for tok in ("image_visual", "diagram", "drawing", "callout")):
            return True
    return False


def _choose_corrected_route(*, is_manual_diagram: bool, manifest_routes: Sequence[str]) -> Tuple[str, str, List[str]]:
    reasons: List[str] = []
    if is_manual_diagram:
        if _has_route(manifest_routes, VISUAL_ROUTE_VALUES):
            return "image_visual", "keep_visual_route_confirmed_by_manual_screen", ["manual_screen_confirms_diagram_page"]
        return "image_visual", "promote_to_image_visual_from_manual_screen", ["manual_screen_finds_missed_diagram_page"]
    if _has_route(manifest_routes, VISUAL_ROUTE_VALUES):
        # Do not force a table/text route without deeper classifier evidence. Put it into review/non-diagram bucket.
        return "review", "demote_overbroad_image_visual_to_review_non_diagram", ["manual_screen_rejects_diagram_page", "existing_image_visual_was_overbroad"]
    if _has_route(manifest_routes, {"table"}):
        return "table", "keep_table_route_non_diagram", ["manual_screen_non_diagram", "route_manifest_table"]
    if _has_route(manifest_routes, {"normal_text"}):
        return "normal_text", "keep_normal_text_route_non_diagram", ["manual_screen_non_diagram", "route_manifest_normal_text"]
    if _has_route(manifest_routes, {"blank_candidate"}):
        return "blank_candidate", "keep_blank_candidate_route_non_diagram", ["manual_screen_non_diagram", "route_manifest_blank"]
    return "review", "manual_screen_non_diagram_unclassified_review", ["manual_screen_non_diagram", "no_strong_non_visual_route"]


def build_route_brain_audit(
    *,
    output_dir: str | Path,
    page_bundle_zip: str | Path,
    route_dispatch_manifest: str | Path | None,
    manual_screened_diagram_pages_csv: str | Path,
    page_id_prefix: str = "t_p_120_1176",
) -> Dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    source_manifest = discover_tiff_pages_from_zip(page_bundle_zip, page_id_prefix=page_id_prefix)
    route_index, malformed_route_value_count = load_route_index(route_dispatch_manifest)
    manual_diagrams = load_manual_diagram_truthset(manual_screened_diagram_pages_csv)
    source_pages = source_manifest.get("page_records") or []

    corrected_records: List[Dict[str, Any]] = []
    actual_diagram_records: List[Dict[str, Any]] = []
    overbroad_records: List[Dict[str, Any]] = []
    missed_records: List[Dict[str, Any]] = []

    for page in source_pages:
        pid = _norm(page.get("page_id"))
        manifest_routes = list((route_index.get(pid) or {}).get("routes") or [])
        manifest_image_visual = _has_route(manifest_routes, VISUAL_ROUTE_VALUES)
        manual = manual_diagrams.get(pid)
        is_manual_diagram = bool(manual)
        corrected_route, action, reasons = _choose_corrected_route(is_manual_diagram=is_manual_diagram, manifest_routes=manifest_routes)
        record = {
            "route_brain_audit_record_id": _stable_id("route_brain_image_audit_v35_1", pid),
            "page_id": pid,
            "page_number": page.get("page_number"),
            "filename": page.get("filename"),
            "manifest_routes": manifest_routes,
            "manifest_image_visual_candidate": manifest_image_visual,
            "manual_screen_diagram_page": is_manual_diagram,
            "manual_screen_category": (manual or {}).get("manual_screen_category", "non_diagram_or_unlabeled"),
            "corrected_primary_route": corrected_route,
            "route_brain_repair_action": action,
            "repair_reasons": reasons,
            "guidance_only": True,
            "proof_authority": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        corrected_records.append(record)
        if is_manual_diagram:
            actual_diagram_records.append(record)
        if manifest_image_visual and not is_manual_diagram:
            overbroad_records.append(record)
        if is_manual_diagram and not manifest_image_visual:
            missed_records.append(record)

    actual_diagram_path = out / "trace_net_actual_diagram_pages_v35_1.jsonl"
    corrections_path = out / "trace_net_route_brain_corrections_v35_1.jsonl"
    overbroad_path = out / "trace_net_overbroad_image_visual_candidates_v35_1.jsonl"
    missed_path = out / "trace_net_missed_diagram_pages_v35_1.jsonl"
    report_path = out / "trace_net_route_brain_image_page_audit_v35_1.json"
    inspect_md_path = out / "trace_net_route_brain_image_page_audit_v35_1.md"

    _write_jsonl(actual_diagram_path, actual_diagram_records)
    _write_jsonl(corrections_path, corrected_records)
    _write_jsonl(overbroad_path, overbroad_records)
    _write_jsonl(missed_path, missed_records)

    route_counts = Counter(r.get("corrected_primary_route") for r in corrected_records)
    action_counts = Counter(r.get("route_brain_repair_action") for r in corrected_records)
    manifest_visual_count = sum(1 for r in corrected_records if r.get("manifest_image_visual_candidate"))
    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": STATUS_READY,
        "quality_status": "UNKNOWN",
        "created_at": _now(),
        "contract": SAFETY_CONTRACT,
        "source_page_count": len(source_pages),
        "route_index_page_count": len(route_index),
        "route_candidate_count": len(corrected_records),
        "manual_screened_diagram_page_count": len(manual_diagrams),
        "actual_diagram_page_count": len(actual_diagram_records),
        "route_manifest_image_visual_candidate_count": manifest_visual_count,
        "corrected_image_visual_count": int(route_counts.get("image_visual", 0)),
        "overbroad_image_visual_candidate_count": len(overbroad_records),
        "missed_diagram_page_count": len(missed_records),
        "malformed_route_value_count": malformed_route_value_count,
        "corrected_route_counts": dict(sorted(route_counts.items())),
        "route_brain_repair_action_counts": dict(sorted(action_counts.items())),
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "visual_proof_authority_violation_count": 0,
        "post_gate_issue_count": 0,
        "report_path": str(report_path),
        "actual_diagram_pages_jsonl_path": str(actual_diagram_path),
        "route_brain_corrections_jsonl_path": str(corrections_path),
        "overbroad_image_visual_candidates_jsonl_path": str(overbroad_path),
        "missed_diagram_pages_jsonl_path": str(missed_path),
        "inspect_md_path": str(inspect_md_path),
        "sample_actual_diagram_pages": actual_diagram_records[:10],
        "sample_overbroad_image_visual_candidates": overbroad_records[:10],
        "sample_missed_diagram_pages": missed_records[:10],
    }
    _write_json(report_path, report)
    _write_inspect_md(inspect_md_path, report)
    return report


def _write_inspect_md(path: str | Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# TRACE-Net Route Brain Image Page Audit v35.1",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
    ]
    for key in [
        "source_page_count", "route_index_page_count", "route_candidate_count", "manual_screened_diagram_page_count",
        "actual_diagram_page_count", "route_manifest_image_visual_candidate_count", "corrected_image_visual_count",
        "overbroad_image_visual_candidate_count", "missed_diagram_page_count", "malformed_route_value_count",
        "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {report.get(key)}")
    lines += ["", "## Corrected route counts"]
    for k, v in (report.get("corrected_route_counts") or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Repair action counts"]
    for k, v in (report.get("route_brain_repair_action_counts") or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Contract", "- This audit does not mutate source truth.", "- Manual-screened diagram labels are used to calibrate routing, not to prove manual/part claims."]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate_quality(
    report: Mapping[str, Any],
    *,
    min_source_pages: int = 1,
    min_route_candidates: int = 1,
    min_manual_screened_diagram_pages: int = 1,
    expected_actual_diagram_pages: int | None = None,
    max_image_visual_candidates_after_correction: int | None = None,
    min_overbroad_image_visual_candidates: int = 0,
    max_malformed_route_values: int = 0,
    max_visual_proof_authority_violations: int = 0,
    max_post_gate_issue_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
) -> Tuple[str, List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []
    def ge(name: str, observed: Any, expected: int) -> None:
        ok = int(observed or 0) >= expected
        checks.append({"name": name, "observed": observed, "expected": f">= {expected}", "status": "PASS" if ok else "FAIL"})
    def le(name: str, observed: Any, expected: int) -> None:
        ok = int(observed or 0) <= expected
        checks.append({"name": name, "observed": observed, "expected": f"<= {expected}", "status": "PASS" if ok else "FAIL"})
    def eq(name: str, observed: Any, expected: int) -> None:
        ok = int(observed or 0) == expected
        checks.append({"name": name, "observed": observed, "expected": f"== {expected}", "status": "PASS" if ok else "FAIL"})

    ge("source_page_count", report.get("source_page_count"), min_source_pages)
    ge("route_candidate_count", report.get("route_candidate_count"), min_route_candidates)
    ge("manual_screened_diagram_page_count", report.get("manual_screened_diagram_page_count"), min_manual_screened_diagram_pages)
    if expected_actual_diagram_pages is not None:
        eq("actual_diagram_page_count", report.get("actual_diagram_page_count"), expected_actual_diagram_pages)
        eq("corrected_image_visual_count", report.get("corrected_image_visual_count"), expected_actual_diagram_pages)
    if max_image_visual_candidates_after_correction is not None:
        le("corrected_image_visual_count", report.get("corrected_image_visual_count"), max_image_visual_candidates_after_correction)
    ge("overbroad_image_visual_candidate_count", report.get("overbroad_image_visual_candidate_count"), min_overbroad_image_visual_candidates)
    le("malformed_route_value_count", report.get("malformed_route_value_count"), max_malformed_route_values)
    le("visual_proof_authority_violation_count", report.get("visual_proof_authority_violation_count"), max_visual_proof_authority_violations)
    le("post_gate_issue_count", report.get("post_gate_issue_count"), max_post_gate_issue_count)
    le("answer_permission_count", report.get("answer_permission_count"), max_answer_permission_count)
    le("source_truth_mutation_allowed_count", report.get("source_truth_mutation_allowed_count"), max_source_truth_mutation_allowed)
    if require_no_answer_permission:
        eq("require_no_answer_permission", report.get("answer_permission_count"), 0)
    status = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    return status, checks


def print_report(report: Mapping[str, Any]) -> None:
    print("TRACE-Net Route Brain Image Page Audit v35.1")
    print(" Status:", report.get("status"))
    print(" Quality status:", report.get("quality_status"))
    for key in [
        "source_page_count", "route_candidate_count", "manual_screened_diagram_page_count", "actual_diagram_page_count",
        "route_manifest_image_visual_candidate_count", "corrected_image_visual_count", "overbroad_image_visual_candidate_count",
        "missed_diagram_page_count", "malformed_route_value_count", "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {report.get(key)}")
    print(" report_path:", report.get("report_path"))
    print(" actual_diagram_pages_jsonl_path:", report.get("actual_diagram_pages_jsonl_path"))
    print(" route_brain_corrections_jsonl_path:", report.get("route_brain_corrections_jsonl_path"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Route brain image/page audit v35.1")
    ap.add_argument("--page-bundle-zip", required=True)
    ap.add_argument("--route-dispatch-manifest", required=True)
    ap.add_argument("--manual-screened-diagram-pages", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--page-id-prefix", default="t_p_120_1176")
    ap.add_argument("--min-source-pages", type=int, default=1)
    ap.add_argument("--min-route-candidates", type=int, default=1)
    ap.add_argument("--min-manual-screened-diagram-pages", type=int, default=1)
    ap.add_argument("--expected-actual-diagram-pages", type=int, default=None)
    ap.add_argument("--max-image-visual-candidates-after-correction", type=int, default=None)
    ap.add_argument("--min-overbroad-image-visual-candidates", type=int, default=0)
    ap.add_argument("--max-malformed-route-values", type=int, default=0)
    ap.add_argument("--max-visual-proof-authority-violations", type=int, default=0)
    ap.add_argument("--max-post-gate-issue-count", type=int, default=0)
    ap.add_argument("--max-answer-permission-count", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--require-no-answer-permission", action="store_true")
    ap.add_argument("--quality", action="store_true")
    args = ap.parse_args(argv)

    report = build_route_brain_audit(
        output_dir=args.output_dir,
        page_bundle_zip=args.page_bundle_zip,
        route_dispatch_manifest=args.route_dispatch_manifest,
        manual_screened_diagram_pages_csv=args.manual_screened_diagram_pages,
        page_id_prefix=args.page_id_prefix,
    )
    if args.quality:
        status, checks = evaluate_quality(
            report,
            min_source_pages=args.min_source_pages,
            min_route_candidates=args.min_route_candidates,
            min_manual_screened_diagram_pages=args.min_manual_screened_diagram_pages,
            expected_actual_diagram_pages=args.expected_actual_diagram_pages,
            max_image_visual_candidates_after_correction=args.max_image_visual_candidates_after_correction,
            min_overbroad_image_visual_candidates=args.min_overbroad_image_visual_candidates,
            max_malformed_route_values=args.max_malformed_route_values,
            max_visual_proof_authority_violations=args.max_visual_proof_authority_violations,
            max_post_gate_issue_count=args.max_post_gate_issue_count,
            max_answer_permission_count=args.max_answer_permission_count,
            max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
            require_no_answer_permission=args.require_no_answer_permission,
        )
        report["quality_status"] = status
        report["quality_checks"] = checks
        _write_json(report["report_path"], report)
        _write_inspect_md(report["inspect_md_path"], report)
    print_report(report)
    return 0 if report.get("quality_status") != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
