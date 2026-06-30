"""TRACE-Net v2 summary guidance index v1.

Builds a guidance-only index from page-level v2/page-context summaries.
Summaries are allowed to guide planning, but never to prove answer claims.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STATUS_BUILT = "TRACE_NET_V2_SUMMARY_GUIDANCE_INDEX_BUILT"
STATUS_CHECKED = "TRACE_NET_V2_SUMMARY_GUIDANCE_INDEX_QUALITY_CHECKED"
MODULE = "trace_net_v2_summary_guidance_index_v1"
VERSION = "v1"

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
FIGURE_RE = re.compile(r"\b(?:fig(?:ure)?\.?|figure)\s*[-#:]*\s*(\d{1,4})\b", re.IGNORECASE)
PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}")
PAGE_NUM_RE = re.compile(r"p(\d{6})$")

SUMMARY_FIELD_HINTS = {
    "page_context_v2_summary",
    "context_v2_summary",
    "page_summary_v2",
    "summary_v2",
    "v2_summary",
    "page_summary",
    "summary_text",
    "summary",
    "visual_summary",
    "route_summary",
}

BAD_SUMMARY_FIELDS = {
    "quality_summary",
    "summary_counts",
    "count_summary",
    "run_summary",
}

BAD_SUMMARY_FIELD_SUBSTRINGS = {
    "summary_path",
    "path",
    "file_path",
    "markdown_path",
    "consensus_summary_path",
}

NON_PAGE_SUMMARY_FIELD_SUBSTRINGS = {
    "feedback_summary",
    "community_summary",
    "retrieval_summary",
    "answer_summary",
}

PATHLIKE_RE = re.compile(r"(?:^|[\\/])(?:local_data|trace_net|docs|scripts|tiff|tests)[\\/].*\.(?:json|md|txt|csv)$", re.IGNORECASE)

TOPIC_RULES = [
    ("illustrated parts list", ["illustrated parts list", "ipl", "parts list"]),
    ("figure", ["figure", "fig.", "fig "]),
    ("diagram", ["diagram", "visual", "callout"]),
    ("table", ["table", "row", "column"]),
    ("maintenance manual", ["maintenance manual", "manual"]),
    ("double passenger seat", ["double passenger seat"]),
    ("seat assembly", ["seat assy", "seat assembly"]),
    ("structure", ["structure", "assy"]),
    ("armrest", ["armrest"]),
    ("effectivity", ["effectivity", "airline eff", "usage code"]),
    ("attaching parts", ["attaching parts"]),
]


def _load_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _iter_json_files(root: Path, max_json_files: int, max_artifact_bytes: int) -> Iterable[Path]:
    root = Path(root)
    if root.is_file() and root.suffix.lower() == ".json":
        yield root
        return
    count = 0
    skip_parts = {"__pycache__", ".pytest_cache"}
    for p in sorted(root.rglob("*.json")):
        if count >= max_json_files:
            break
        if any(part in skip_parts for part in p.parts):
            continue
        try:
            if p.stat().st_size > max_artifact_bytes:
                continue
        except OSError:
            continue
        count += 1
        yield p


def _walk(obj: Any, path: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            child = f"{path}.{k}" if path else str(k)
            yield from _walk(v, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def _first_str(*values: Any) -> str:
    for v in values:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _first_int(*values: Any) -> Optional[int]:
    for v in values:
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            m = re.search(r"\d+", v)
            if m:
                try:
                    return int(m.group(0))
                except ValueError:
                    pass
    return None


def _source_trace(obj: Mapping[str, Any]) -> Mapping[str, Any]:
    st = obj.get("source_trace")
    return st if isinstance(st, dict) else {}


def _page_id_from_obj(obj: Mapping[str, Any]) -> str:
    st = _source_trace(obj)
    nested = obj.get("page") if isinstance(obj.get("page"), dict) else {}
    value = _first_str(
        obj.get("page_id"), obj.get("source_page_id"), obj.get("trace_page_id"),
        st.get("page_id"), st.get("source_page_id"), nested.get("page_id"),
    )
    if value:
        return value
    s = json.dumps(obj, ensure_ascii=False)
    m = PAGE_ID_RE.search(s)
    return m.group(0) if m else ""


def _page_number_from_obj(obj: Mapping[str, Any], page_id: str = "") -> Optional[int]:
    st = _source_trace(obj)
    nested = obj.get("page") if isinstance(obj.get("page"), dict) else {}
    n = _first_int(
        obj.get("page_number"), obj.get("canonical_page_number"), obj.get("source_page_number"),
        st.get("page_number"), st.get("canonical_page_number"), nested.get("page_number"),
    )
    if n is not None:
        return n
    if page_id:
        m = PAGE_NUM_RE.search(page_id)
        if m:
            return int(m.group(1))
    return None


def _route_label_from_obj(obj: Mapping[str, Any]) -> str:
    st = _source_trace(obj)
    raw = obj.get("route_label") or obj.get("primary_route") or obj.get("route") or st.get("route")
    if isinstance(raw, list):
        return ",".join(str(x) for x in raw)
    if isinstance(raw, str):
        return raw
    return "unknown"


def _is_bad_summary_field(field_name: str) -> bool:
    kl = str(field_name).lower()
    if kl in BAD_SUMMARY_FIELDS:
        return True
    if "summary" in kl and any(bad in kl for bad in BAD_SUMMARY_FIELD_SUBSTRINGS):
        return True
    if any(bad in kl for bad in NON_PAGE_SUMMARY_FIELD_SUBSTRINGS):
        return True
    return False


def _is_guidance_summary_text(text: str) -> bool:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) < 20:
        return False
    if s.startswith("{") or s.startswith("["):
        return False
    low = s.lower()
    # Do not index paths, artifact pointers, page-id ranges, or generic feedback/community labels as page guidance.
    if PATHLIKE_RE.search(s) or re.search(r"\.(json|md|txt|csv)$", low):
        return False
    if PAGE_ID_RE.fullmatch(s):
        return False
    if re.fullmatch(r"t_p_\d+_\d+_p\d{6}(?:\s+to\s+t_p_\d+_\d+_p\d{6})?", low):
        return False
    if low.startswith("prior feedback marked"):
        return False
    if "helpful_community" in low or "helpful answer" in low:
        return False
    if "local_data" in low and ("summary" in low or "trace_net" in low):
        return False
    return True


def _summary_candidates(obj: Mapping[str, Any]) -> Iterable[Tuple[str, str]]:
    for k, v in obj.items():
        kl = str(k).lower()
        if _is_bad_summary_field(kl):
            continue
        if kl in SUMMARY_FIELD_HINTS or ("summary" in kl and "count" not in kl and "quality" not in kl):
            if isinstance(v, str):
                text = re.sub(r"\s+", " ", v).strip()
                if _is_guidance_summary_text(text):
                    yield str(k), text
            elif isinstance(v, dict):
                for kk in ("text", "summary", "page_summary", "content"):
                    vv = v.get(kk)
                    if isinstance(vv, str):
                        text = re.sub(r"\s+", " ", vv).strip()
                        if _is_guidance_summary_text(text):
                            yield f"{k}.{kk}", text


def _detect_figures(text: str) -> List[str]:
    return sorted(set(m.group(1).lstrip("0") or "0" for m in FIGURE_RE.finditer(text)))


def _detect_parts(text: str) -> List[str]:
    return sorted(set(PART_RE.findall(text)))


def _detect_topics(text: str) -> List[str]:
    low = text.lower()
    topics: List[str] = []
    for topic, needles in TOPIC_RULES:
        if any(n in low for n in needles):
            topics.append(topic)
    return sorted(set(topics))


def _manual_section_hint(text: str, route_label: str) -> str:
    low = f"{text} {route_label}".lower()
    if "illustrated parts list" in low or "ipl" in low or "fig." in low or "figure" in low:
        return "illustrated_parts_list"
    if "diagram" in low or "image" in low or "visual" in low:
        return "visual_diagram"
    if "table" in low:
        return "table"
    if "maintenance manual" in low or "procedure" in low:
        return "maintenance_manual"
    return "unknown"


def _record_id(page_id: str, page_number: Optional[int], summary_text: str, source_artifact: str, object_path: str) -> str:
    key = "|".join([page_id, str(page_number or ""), summary_text, source_artifact, object_path])
    return "v2_summary_guidance__" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def collect_summary_records(
    artifact_root: Path,
    *,
    max_json_files: int = 500,
    max_artifact_bytes: int = 25_000_000,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    scanned = 0
    candidate_object_count = 0
    seen = set()
    rejected_summary_candidate_count = 0

    for artifact in _iter_json_files(Path(artifact_root), max_json_files, max_artifact_bytes):
        scanned += 1
        try:
            data = _load_json(artifact)
        except Exception:
            continue
        for object_path, obj in _walk(data):
            if not isinstance(obj, dict):
                continue
            raw_summary_like_count = sum(1 for k in obj.keys() if "summary" in str(k).lower())
            summaries = list(_summary_candidates(obj))
            rejected_summary_candidate_count += max(0, raw_summary_like_count - len(summaries))
            if not summaries:
                continue
            page_id = _page_id_from_obj(obj)
            page_number = _page_number_from_obj(obj, page_id)
            if not page_id and page_number is None:
                # Guidance must still be tied to a page/source trace.
                continue
            candidate_object_count += 1
            route_label = _route_label_from_obj(obj)
            source_member = _first_str(obj.get("source_member"), obj.get("file_name"), obj.get("tiff_member"), _source_trace(obj).get("source_member"))
            for field, summary_text in summaries:
                # Dedupe across copied/rebuilt artifacts. Guidance should not become louder just because
                # the same summary was copied into many stage reports.
                normalized_summary = re.sub(r"\s+", " ", summary_text.lower()).strip()
                key = (page_id, page_number, normalized_summary)
                if key in seen:
                    rejected_summary_candidate_count += 1
                    continue
                seen.add(key)
                figures = _detect_figures(summary_text)
                parts = _detect_parts(summary_text)
                topics = _detect_topics(summary_text)
                source_trace_ready = bool(page_id or page_number)
                records.append({
                    "record_id": _record_id(page_id, page_number, summary_text, str(artifact), object_path),
                    "module": MODULE,
                    "version": VERSION,
                    "page_id": page_id,
                    "page_number": page_number,
                    "source_member": source_member,
                    "route_label": route_label,
                    "summary_field": field,
                    "summary_text": summary_text,
                    "summary_char_count": len(summary_text),
                    "detected_figures": figures,
                    "detected_part_numbers": parts,
                    "detected_topics": topics,
                    "manual_section_hint": _manual_section_hint(summary_text, route_label),
                    "source_artifact": str(artifact),
                    "object_path": object_path,
                    "guidance_only": True,
                    "source_trace_ready": source_trace_ready,
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                    "unsafe": False,
                    "write_attempt_count": 0,
                })

    records.sort(key=lambda r: (r.get("page_number") is None, r.get("page_number") or 10**9, r.get("page_id") or "", r.get("source_artifact") or ""))
    meta = {"source_artifact_scan_count": scanned, "candidate_summary_object_count": candidate_object_count, "rejected_summary_candidate_count": rejected_summary_candidate_count}
    return records, meta


def summarize(records: Sequence[Mapping[str, Any]], meta: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    summary_record_count = len(records)
    source_trace_ready_count = sum(1 for r in records if r.get("source_trace_ready"))
    guidance_only_count = sum(1 for r in records if r.get("guidance_only") is True)
    answer_permission_count = sum(1 for r in records if r.get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for r in records if r.get("source_truth_mutation_allowed"))
    unsafe_record_count = sum(1 for r in records if r.get("unsafe"))
    figure_hint_record_count = sum(1 for r in records if r.get("detected_figures"))
    part_hint_record_count = sum(1 for r in records if r.get("detected_part_numbers"))
    topic_hint_record_count = sum(1 for r in records if r.get("detected_topics"))
    page_count = len({r.get("page_id") or r.get("page_number") for r in records if r.get("page_id") or r.get("page_number")})
    out = {
        "summary_record_count": summary_record_count,
        "page_with_summary_count": page_count,
        "source_trace_ready_count": source_trace_ready_count,
        "guidance_only_count": guidance_only_count,
        "figure_hint_record_count": figure_hint_record_count,
        "part_hint_record_count": part_hint_record_count,
        "topic_hint_record_count": topic_hint_record_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": unsafe_record_count,
        "ready_for_engineering_query_planner": bool(summary_record_count and source_trace_ready_count and not answer_permission_count and not source_truth_mutation_allowed_count and not unsafe_record_count),
    }
    if meta:
        out.update(dict(meta))
    return out


def _quality_failures(summary: Mapping[str, Any], *, min_summary_records: int, min_source_trace_ready: int, max_unsafe: int, max_answer_permission: int, max_source_truth_mutation_allowed: int, max_write_attempts: int, require_guidance_only: bool = True) -> List[str]:
    failures: List[str] = []
    if int(summary.get("summary_record_count") or 0) < min_summary_records:
        failures.append(f"summary_record_count below minimum: {summary.get('summary_record_count', 0)} < {min_summary_records}")
    if int(summary.get("source_trace_ready_count") or 0) < min_source_trace_ready:
        failures.append(f"source_trace_ready_count below minimum: {summary.get('source_trace_ready_count', 0)} < {min_source_trace_ready}")
    if int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append(f"unsafe_record_count above maximum: {summary.get('unsafe_record_count', 0)} > {max_unsafe}")
    if int(summary.get("answer_permission_count") or 0) > max_answer_permission:
        failures.append(f"answer_permission_count above maximum: {summary.get('answer_permission_count', 0)} > {max_answer_permission}")
    if int(summary.get("source_truth_mutation_allowed_count") or 0) > max_source_truth_mutation_allowed:
        failures.append(f"source_truth_mutation_allowed_count above maximum: {summary.get('source_truth_mutation_allowed_count', 0)} > {max_source_truth_mutation_allowed}")
    if int(summary.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append(f"write_attempt_count above maximum: {summary.get('write_attempt_count', 0)} > {max_write_attempts}")
    if require_guidance_only and int(summary.get("guidance_only_count") or 0) != int(summary.get("summary_record_count") or 0):
        failures.append("not all summary records are marked guidance_only")
    return failures


def write_records_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "record_id", "page_id", "page_number", "source_member", "route_label", "summary_field",
        "manual_section_hint", "detected_figures", "detected_part_numbers", "detected_topics",
        "source_trace_ready", "guidance_only", "source_artifact", "object_path", "summary_text",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            row = dict(r)
            for k in ("detected_figures", "detected_part_numbers", "detected_topics"):
                row[k] = ";".join(str(x) for x in row.get(k, []) or [])
            writer.writerow({k: row.get(k, "") for k in fields})


def build_guidance_index(
    *,
    artifact_root: Path,
    output_dir: Path,
    max_json_files: int = 500,
    max_artifact_bytes: int = 25_000_000,
    min_summary_records: int = 1,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records, meta = collect_summary_records(artifact_root, max_json_files=max_json_files, max_artifact_bytes=max_artifact_bytes)
    summary = summarize(records, meta)
    failures = _quality_failures(
        summary,
        min_summary_records=min_summary_records,
        min_source_trace_ready=min_source_trace_ready,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    quality_status = "PASS" if not failures else "FAIL"
    result: Dict[str, Any] = {
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "module": MODULE,
        "version": VERSION,
        "source_artifact_root": str(artifact_root),
        "summary": summary,
        "failures": failures,
        "records": records,
    }
    index_path = output_dir / f"{MODULE}.json"
    quality_path = output_dir / f"{MODULE}_quality_check.json"
    csv_path = output_dir / f"{MODULE}_records.csv"
    _write_json(index_path, result)
    _write_json(quality_path, {"status": STATUS_CHECKED, "quality_status": quality_status, "summary": summary, "failures": failures})
    write_records_csv(csv_path, records)
    result["paths"] = {"index": str(index_path), "quality_check": str(quality_path), "records_csv": str(csv_path)}
    _write_json(index_path, result)
    return result


def check_guidance_index(
    *,
    index: Path,
    output: Path,
    require_quality_pass: bool = False,
    min_summary_records: int = 1,
    min_source_trace_ready: int = 1,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _load_json(Path(index))
    records = data.get("records") if isinstance(data.get("records"), list) else []
    summary = summarize(records, {k: v for k, v in (data.get("summary") or {}).items() if k.endswith("scan_count") or k.endswith("object_count")})
    failures = _quality_failures(
        summary,
        min_summary_records=min_summary_records,
        min_source_trace_ready=min_source_trace_ready,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.insert(0, "quality_status is not PASS")
    quality_status = "PASS" if not failures else "FAIL"
    result = {"status": STATUS_CHECKED, "quality_status": quality_status, "source_index": str(index), "summary": summary, "failures": failures}
    _write_json(Path(output), result)
    return result


def _print_build(result: Mapping[str, Any]) -> None:
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    for k in ["summary_record_count", "page_with_summary_count", "source_trace_ready_count", "guidance_only_count", "figure_hint_record_count", "part_hint_record_count", "topic_hint_record_count", "rejected_summary_candidate_count", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count"]:
        print(f"{k}={s.get(k, 0)}")
    print(f"index={result.get('paths', {}).get('index', '')}")


def _print_check(result: Mapping[str, Any]) -> None:
    s = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    for k in ["summary_record_count", "page_with_summary_count", "source_trace_ready_count", "guidance_only_count", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count"]:
        print(f"{k}={s.get(k, 0)}")
    for f in result.get("failures", []) or []:
        print(f"failure={f}")


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Build TRACE-Net v2 summary guidance index v1")
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-json-files", type=int, default=500)
    ap.add_argument("--max-artifact-bytes", type=int, default=25_000_000)
    ap.add_argument("--min-summary-records", type=int, default=1)
    ap.add_argument("--min-source-trace-ready", type=int, default=1)
    ap.add_argument("--max-unsafe", type=int, default=0)
    ap.add_argument("--max-answer-permission", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--max-write-attempts", type=int, default=0)
    return ap


def check_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Check TRACE-Net v2 summary guidance index v1")
    ap.add_argument("--index", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--require-quality-pass", action="store_true")
    ap.add_argument("--min-summary-records", type=int, default=1)
    ap.add_argument("--min-source-trace-ready", type=int, default=1)
    ap.add_argument("--max-unsafe", type=int, default=0)
    ap.add_argument("--max-answer-permission", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--max-write-attempts", type=int, default=0)
    return ap


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = build_guidance_index(
        artifact_root=Path(args.artifact_root),
        output_dir=Path(args.output_dir),
        max_json_files=args.max_json_files,
        max_artifact_bytes=args.max_artifact_bytes,
        min_summary_records=args.min_summary_records,
        min_source_trace_ready=args.min_source_trace_ready,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    _print_build(result)
    return 0 if result.get("quality_status") == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    args = check_arg_parser().parse_args(argv)
    result = check_guidance_index(
        index=Path(args.index),
        output=Path(args.output),
        require_quality_pass=args.require_quality_pass,
        min_summary_records=args.min_summary_records,
        min_source_trace_ready=args.min_source_trace_ready,
        max_unsafe=args.max_unsafe,
        max_answer_permission=args.max_answer_permission,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        max_write_attempts=args.max_write_attempts,
    )
    _print_check(result)
    return 0 if result.get("quality_status") == "PASS" else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    return main_build(argv)


if __name__ == "__main__":
    raise SystemExit(main_build())
