"""TRACE-Net Human Review Workbench Source/Image Preview Wiring v1.

This module enriches the Human Review Workbench View Model with source-package
and TIFF preview metadata from the Dublin Core Source Package Extension.

It is intentionally read-only and does not load image bytes. It only wires
page-scoped review cards to page/source package identifiers, TIFF entry names,
METS hrefs, checksums, and reviewer-viewer hints.

Safety contract:
- preview records cannot answer directly
- preview records cannot prove claims
- preview records cannot mutate source truth
- preview records do not write Postgres, Qdrant, or OpenSearch
- preview records do not expose raw feedback to the LLM
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_human_review_workbench_preview_wiring_v1"
AUTHORITY = "human_review_workbench_preview_metadata_only"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/human_review_workbench_preview")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def stable_id(prefix: str, *parts: Any) -> str:
    data = "||".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha256(data.encode('utf-8')).hexdigest()[:16]}"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def str_list(value: Any, *, limit: int | None = None) -> list[str]:
    items: list[str] = []
    for item in as_list(value):
        if item is None:
            continue
        text = str(item).strip()
        if text:
            items.append(text)
    out = sorted(set(items))
    return out[:limit] if limit is not None else out


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue
        if isinstance(value, dict) and not value:
            continue
        return value
    return None


def load_records(payload: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        records = payload.get(key)
        if isinstance(records, list):
            return [r for r in records if isinstance(r, dict)]
    return []


def source_quality(payload: dict[str, Any]) -> str:
    return str(payload.get("quality_status") or payload.get("summary", {}).get("quality_status") or payload.get("status") or "").upper()


def page_id_from_record(record: dict[str, Any]) -> str:
    dc = record.get("dc") if isinstance(record.get("dc"), dict) else {}
    trace = record.get("trace_net") if isinstance(record.get("trace_net"), dict) else {}
    props = record.get("properties") if isinstance(record.get("properties"), dict) else {}
    return str(
        first_nonempty(
            record.get("page_id"),
            props.get("page_id"),
            dc.get("dc:identifier"),
            trace.get("trace_net:page_id"),
            "",
        )
    )


def index_source_pages(dublin_source_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in load_records(dublin_source_payload, ("page_records", "pages")):
        page_id = page_id_from_record(record)
        if page_id:
            index[page_id] = record
    return index


def document_source_package_summary(dublin_source_payload: dict[str, Any]) -> dict[str, Any]:
    summary = dublin_source_payload.get("summary") if isinstance(dublin_source_payload.get("summary"), dict) else {}
    docs = load_records(dublin_source_payload, ("document_records", "documents"))
    doc_summary = docs[0].get("source_package_summary", {}) if docs and isinstance(docs[0].get("source_package_summary"), dict) else {}
    merged = {**summary, **doc_summary}
    return {
        "available": bool(merged.get("source_package_label") or merged.get("source_package_objid") or merged.get("metadata_xml_present")),
        "source_package_label": merged.get("source_package_label"),
        "source_package_objid": merged.get("source_package_objid"),
        "source_package_type": merged.get("source_package_type"),
        "source_package_record_status": merged.get("source_package_record_status"),
        "source_package_created_at": merged.get("source_package_created_at"),
        "source_package_date_captured": merged.get("source_package_date_captured"),
        "source_package_language_code": merged.get("source_package_language_code"),
        "source_package_tiff_count": merged.get("source_package_tiff_count"),
        "source_package_entry_count": merged.get("source_package_entry_count"),
        "metadata_xml_present": bool(merged.get("metadata_xml_present")),
    }


def source_package_block_for_page(page_record: dict[str, Any] | None, package_summary: dict[str, Any]) -> dict[str, Any]:
    if not page_record:
        return {"available": False}
    source = page_record.get("source_package") if isinstance(page_record.get("source_package"), dict) else {}
    dc = page_record.get("dc") if isinstance(page_record.get("dc"), dict) else {}
    trace = page_record.get("trace_net") if isinstance(page_record.get("trace_net"), dict) else {}

    entry_name = source.get("trace_net:source_package_entry_name")
    href = source.get("trace_net:source_package_entry_href")
    page_number = source.get("trace_net:source_package_page_number")
    available = bool(entry_name or href or source.get("trace_net:source_package_objid") or package_summary.get("available"))
    return {
        "available": available,
        "dc_identifier": dc.get("dc:identifier") or page_id_from_record(page_record),
        "dc_type": str_list(dc.get("dc:type"), limit=20),
        "dc_source": dc.get("dc:source") or dc.get("dcterms:source"),
        "dc_language": dc.get("dc:language"),
        "source_package_id": source.get("trace_net:source_package_id"),
        "source_package_label": source.get("trace_net:source_package_label") or package_summary.get("source_package_label"),
        "source_package_objid": source.get("trace_net:source_package_objid") or package_summary.get("source_package_objid"),
        "source_package_type": source.get("trace_net:source_package_type") or package_summary.get("source_package_type"),
        "source_package_record_status": source.get("trace_net:source_package_record_status") or package_summary.get("source_package_record_status"),
        "source_package_created_at": source.get("trace_net:source_package_created_at") or package_summary.get("source_package_created_at"),
        "source_package_date_captured": source.get("trace_net:source_package_date_captured") or package_summary.get("source_package_date_captured"),
        "source_package_language_code": source.get("trace_net:source_package_language_code") or package_summary.get("source_package_language_code"),
        "metadata_xml_present": bool(package_summary.get("metadata_xml_present")),
        "source_package_entry_name": entry_name,
        "source_package_entry_suffix": source.get("trace_net:source_package_entry_suffix"),
        "source_package_entry_href": href,
        "source_package_page_number": page_number,
        "source_package_entry_size_bytes": source.get("trace_net:source_package_entry_size_bytes"),
        "source_package_entry_size_bytes_mets": source.get("trace_net:source_package_entry_size_bytes_mets"),
        "source_package_checksum_sha1": source.get("trace_net:source_package_entry_checksum_sha1"),
        "source_package_checksum_sha1_computed": source.get("trace_net:source_package_entry_checksum_sha1_computed"),
        "source_package_checksum_match": source.get("trace_net:source_package_entry_checksum_match"),
        "source_package_match_method": source.get("trace_net:source_package_match_method"),
        "source_traceability_status": source.get("trace_net:source_traceability_status") or trace.get("trace_net:source_package_traceability_status"),
    }


def preview_for_page(page_id: str, source_summary: dict[str, Any]) -> dict[str, Any]:
    if not page_id:
        return {"available": False}
    entry_name = source_summary.get("source_package_entry_name")
    href = source_summary.get("source_package_entry_href")
    has_entry = bool(entry_name or href)
    return {
        "available": has_entry,
        "has_source_package_entry": has_entry,
        "page_id": page_id,
        "page_number": source_summary.get("source_package_page_number"),
        "image_entry_name": entry_name,
        "image_entry_suffix": source_summary.get("source_package_entry_suffix"),
        "image_href": href,
        "entry_size_bytes": source_summary.get("source_package_entry_size_bytes"),
        "entry_size_bytes_mets": source_summary.get("source_package_entry_size_bytes_mets"),
        "checksum_sha1": source_summary.get("source_package_checksum_sha1"),
        "checksum_sha1_computed": source_summary.get("source_package_checksum_sha1_computed"),
        "checksum_match": source_summary.get("source_package_checksum_match"),
        "traceability": source_summary.get("source_traceability_status"),
        "source_label": first_nonempty(
            source_summary.get("source_package_label"),
            source_summary.get("dc_source"),
            href,
            entry_name,
        ),
        "dc_type": source_summary.get("dc_type") or [],
        "dc_language": source_summary.get("dc_language"),
        "viewer_hint": "Use image_href or a resolved local TIFF path in the review UI; this view model does not load image bytes.",
    }


def enriched_card(card: dict[str, Any], source_by_page: dict[str, dict[str, Any]], package_summary: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(card))
    page_id = str(first_nonempty(out.get("primary_page_id"), (out.get("page_ids") or [None])[0] if isinstance(out.get("page_ids"), list) and out.get("page_ids") else None, ""))
    if not page_id:
        out["source_package_summary"] = {"available": False}
        out["page_preview"] = {"available": False}
    else:
        source_summary = source_package_block_for_page(source_by_page.get(page_id), package_summary)
        out["source_package_summary"] = source_summary
        out["page_preview"] = preview_for_page(page_id, source_summary)
    out["preview_wiring_authority"] = AUTHORITY
    out["can_answer_directly"] = False
    out["can_prove_claims"] = False
    out["can_mutate_source_truth"] = False
    out["source_truth_mutation_allowed"] = False
    out["source_truth_mutations_performed"] = 0
    out["final_answer_allowed"] = False
    out["raw_feedback_direct_to_llm"] = False
    out["unsafe_preview_card"] = False
    return out


def enriched_page_profile(profile: dict[str, Any], source_by_page: dict[str, dict[str, Any]], package_summary: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(profile))
    page_id = str(out.get("page_id") or "")
    source_summary = source_package_block_for_page(source_by_page.get(page_id), package_summary)
    out["source_package_summary"] = source_summary
    out["page_preview"] = preview_for_page(page_id, source_summary)
    out["preview_wiring_authority"] = AUTHORITY
    out["can_answer_directly"] = False
    out["can_prove_claims"] = False
    out["can_mutate_source_truth"] = False
    out["source_truth_mutation_allowed"] = False
    out["final_answer_allowed"] = False
    return out


def compute_summary(
    *,
    workbench: dict[str, Any],
    dublin_source: dict[str, Any],
    cards: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    page_scoped_cards = [c for c in cards if c.get("primary_page_id") or c.get("page_ids")]
    cards_with_preview = [c for c in page_scoped_cards if c.get("page_preview", {}).get("has_source_package_entry")]
    cards_with_summary = [c for c in page_scoped_cards if c.get("source_package_summary", {}).get("available")]
    cards_with_checksum_match = [c for c in page_scoped_cards if c.get("page_preview", {}).get("checksum_match") is True]
    cards_with_checksum_mismatch = [c for c in page_scoped_cards if c.get("page_preview", {}).get("checksum_match") is False]
    pages_with_preview = [p for p in pages if p.get("page_preview", {}).get("has_source_package_entry")]
    pages_with_summary = [p for p in pages if p.get("source_package_summary", {}).get("available")]
    priority_counts = Counter(c.get("priority") for c in cards)
    card_type_counts = Counter(c.get("card_type") for c in cards)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "algorithm": "trace_net_human_review_workbench_source_image_preview_wiring_v1",
        "source_workbench_quality_status": source_quality(workbench),
        "source_dublin_core_source_package_quality_status": source_quality(dublin_source),
        "source_package_label": dublin_source.get("summary", {}).get("source_package_label"),
        "source_package_objid": dublin_source.get("summary", {}).get("source_package_objid"),
        "source_package_tiff_count": dublin_source.get("summary", {}).get("source_package_tiff_count"),
        "metadata_xml_present": bool(dublin_source.get("summary", {}).get("metadata_xml_present")),
        "workbench_card_count": len(cards),
        "page_workbench_profile_count": len(pages),
        "page_scoped_workbench_card_count": len(page_scoped_cards),
        "cards_with_page_preview_count": len(cards_with_preview),
        "cards_with_source_package_summary_count": len(cards_with_summary),
        "cards_with_checksum_match_count": len(cards_with_checksum_match),
        "cards_with_checksum_mismatch_count": len(cards_with_checksum_mismatch),
        "missing_page_preview_for_page_scoped_card_count": len(page_scoped_cards) - len(cards_with_preview),
        "page_profiles_with_page_preview_count": len(pages_with_preview),
        "page_profiles_with_source_package_summary_count": len(pages_with_summary),
        "critical_workbench_card_count": priority_counts.get("critical", 0),
        "high_priority_workbench_card_count": priority_counts.get("high", 0) + priority_counts.get("critical", 0),
        "unsafe_preview_card_count": len([c for c in cards if c.get("unsafe_preview_card")]),
        "preview_can_answer_directly_count": len([c for c in cards if c.get("can_answer_directly")]),
        "preview_can_prove_claims_count": len([c for c in cards if c.get("can_prove_claims")]),
        "source_truth_mutation_allowed_count": len([c for c in cards if c.get("source_truth_mutation_allowed") or c.get("can_mutate_source_truth")]),
        "raw_feedback_direct_to_llm_count": len([c for c in cards if c.get("raw_feedback_direct_to_llm")]),
        "final_answer_allowed_count": len([c for c in cards if c.get("final_answer_allowed")]),
        "priority_counts": dict(sorted(priority_counts.items())),
        "card_type_counts": dict(sorted(card_type_counts.items())),
    }


def compute_quality(
    report: dict[str, Any],
    *,
    min_workbench_cards: int = 1,
    min_page_profiles: int = 1,
    min_page_scoped_cards: int = 1,
    min_cards_with_page_preview: int = 1,
    min_cards_with_source_package_summary: int = 1,
    min_page_profiles_with_preview: int = 1,
    require_source_workbench_quality_pass: bool = False,
    require_source_package_quality_pass: bool = False,
) -> dict[str, Any]:
    s = report.get("summary", {}) or {}
    checks: dict[str, bool] = {
        "min_workbench_cards": int(s.get("workbench_card_count") or 0) >= min_workbench_cards,
        "min_page_profiles": int(s.get("page_workbench_profile_count") or 0) >= min_page_profiles,
        "min_page_scoped_cards": int(s.get("page_scoped_workbench_card_count") or 0) >= min_page_scoped_cards,
        "min_cards_with_page_preview": int(s.get("cards_with_page_preview_count") or 0) >= min_cards_with_page_preview,
        "min_cards_with_source_package_summary": int(s.get("cards_with_source_package_summary_count") or 0) >= min_cards_with_source_package_summary,
        "min_page_profiles_with_preview": int(s.get("page_profiles_with_page_preview_count") or 0) >= min_page_profiles_with_preview,
        "no_missing_preview_for_page_scoped_cards": int(s.get("missing_page_preview_for_page_scoped_card_count") or 0) == 0,
        "checksum_mismatch_count_zero": int(s.get("cards_with_checksum_mismatch_count") or 0) == 0,
        "unsafe_preview_card_count_zero": int(s.get("unsafe_preview_card_count") or 0) == 0,
        "preview_can_answer_directly_count_zero": int(s.get("preview_can_answer_directly_count") or 0) == 0,
        "preview_can_prove_claims_count_zero": int(s.get("preview_can_prove_claims_count") or 0) == 0,
        "source_truth_mutation_allowed_count_zero": int(s.get("source_truth_mutation_allowed_count") or 0) == 0,
        "raw_feedback_direct_to_llm_count_zero": int(s.get("raw_feedback_direct_to_llm_count") or 0) == 0,
        "final_answer_allowed_count_zero": int(s.get("final_answer_allowed_count") or 0) == 0,
    }
    if require_source_workbench_quality_pass:
        checks["source_workbench_quality_pass"] = str(s.get("source_workbench_quality_status") or "").upper() == "PASS"
    if require_source_package_quality_pass:
        checks["source_package_quality_pass"] = str(s.get("source_dublin_core_source_package_quality_status") or "").upper() == "PASS"
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "checks": checks,
        "summary": s,
        "generated_at": utc_now(),
    }


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# TRACE-Net Human Review Workbench Source/Image Preview Wiring v1",
        "",
        f"**Status:** {report['status']}",
        f"**Quality:** {report['quality_status']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "workbench_card_count",
        "page_scoped_workbench_card_count",
        "cards_with_page_preview_count",
        "cards_with_source_package_summary_count",
        "missing_page_preview_for_page_scoped_card_count",
        "cards_with_checksum_match_count",
        "cards_with_checksum_mismatch_count",
        "unsafe_preview_card_count",
        "preview_can_answer_directly_count",
        "preview_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {s.get(key)}")
    lines.extend(["", "## Example Preview Cards", ""])
    lines.append("| Priority | Card type | Page | TIFF entry | Page number | Checksum match |")
    lines.append("|---|---|---|---|---:|---|")
    for card in report.get("workbench_cards", [])[:50]:
        preview = card.get("page_preview", {})
        lines.append(
            "| {priority} | {card_type} | {page} | {entry} | {num} | {checksum} |".format(
                priority=card.get("priority"),
                card_type=str(card.get("card_type") or "").replace("|", "\\|"),
                page=card.get("primary_page_id") or "-",
                entry=preview.get("image_entry_name") or "-",
                num=preview.get("page_number") or "",
                checksum=preview.get("checksum_match") if preview else "",
            )
        )
    return "\n".join(lines) + "\n"


def render_html(markdown_text: str) -> str:
    return "<html><body><pre>" + html.escape(markdown_text) + "</pre></body></html>"


def build_preview_wiring(
    *,
    human_review_workbench_path: str | Path,
    dublin_core_source_package_extension_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    min_workbench_cards: int = 1,
    min_page_profiles: int = 1,
    min_page_scoped_cards: int = 1,
    min_cards_with_page_preview: int = 1,
    min_cards_with_source_package_summary: int = 1,
    min_page_profiles_with_preview: int = 1,
    require_source_workbench_quality_pass: bool = False,
    require_source_package_quality_pass: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    workbench = read_json(human_review_workbench_path, {})
    dublin_source = read_json(dublin_core_source_package_extension_path, {})
    package_summary = document_source_package_summary(dublin_source)
    source_by_page = index_source_pages(dublin_source)

    base_cards = load_records(workbench, ("workbench_cards", "cards"))
    base_pages = load_records(workbench, ("page_workbench_profiles", "page_profiles"))
    cards = [enriched_card(card, source_by_page, package_summary) for card in base_cards]
    pages = [enriched_page_profile(profile, source_by_page, package_summary) for profile in base_pages]

    summary = compute_summary(workbench=workbench, dublin_source=dublin_source, cards=cards, pages=pages)
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "HUMAN_REVIEW_WORKBENCH_PREVIEW_WIRING_BUILT",
        "generated_at": utc_now(),
        "source_paths": {
            "human_review_workbench": str(human_review_workbench_path),
            "dublin_core_source_package_extension": str(dublin_core_source_package_extension_path),
        },
        "summary": summary,
        "workbench_cards": cards,
        "page_workbench_profiles": pages,
        "preview_wiring_authority": AUTHORITY,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "final_answer_allowed": False,
    }
    quality = compute_quality(
        report,
        min_workbench_cards=min_workbench_cards,
        min_page_profiles=min_page_profiles,
        min_page_scoped_cards=min_page_scoped_cards,
        min_cards_with_page_preview=min_cards_with_page_preview,
        min_cards_with_source_package_summary=min_cards_with_source_package_summary,
        min_page_profiles_with_preview=min_page_profiles_with_preview,
        require_source_workbench_quality_pass=require_source_workbench_quality_pass,
        require_source_package_quality_pass=require_source_package_quality_pass,
    )
    report["quality_status"] = quality["status"]

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_human_review_workbench_preview_wiring_v1.json"
    cards_path = out / "trace_net_human_review_workbench_preview_wiring_v1_cards.jsonl"
    pages_path = out / "trace_net_human_review_workbench_preview_wiring_v1_pages.jsonl"
    summary_path = out / "trace_net_human_review_workbench_preview_wiring_v1_summary.json"
    quality_path = out / "trace_net_human_review_workbench_preview_wiring_v1_quality.json"
    manifest_path = out / "trace_net_human_review_workbench_preview_wiring_v1_manifest.json"
    md_path = out / "trace_net_human_review_workbench_preview_wiring_v1.md"
    html_path = out / "trace_net_human_review_workbench_preview_wiring_v1.html"

    report["report_path"] = str(report_path)
    report["cards_path"] = str(cards_path)
    report["pages_path"] = str(pages_path)
    report["quality_path"] = str(quality_path)
    quality["quality_path"] = str(quality_path)

    write_json(report_path, report)
    write_jsonl(cards_path, cards)
    write_jsonl(pages_path, pages)
    write_json(summary_path, summary)
    write_json(quality_path, quality)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now(),
        "inputs": report["source_paths"],
        "outputs": {
            "report": str(report_path),
            "cards": str(cards_path),
            "pages": str(pages_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
        },
    })
    md = render_markdown(report)
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    return report


def quality_report(
    *,
    report_path: str | Path,
    min_workbench_cards: int = 1,
    min_page_profiles: int = 1,
    min_page_scoped_cards: int = 1,
    min_cards_with_page_preview: int = 1,
    min_cards_with_source_package_summary: int = 1,
    min_page_profiles_with_preview: int = 1,
    require_source_workbench_quality_pass: bool = False,
    require_source_package_quality_pass: bool = False,
    write_json_report: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path, {})
    quality = compute_quality(
        report,
        min_workbench_cards=min_workbench_cards,
        min_page_profiles=min_page_profiles,
        min_page_scoped_cards=min_page_scoped_cards,
        min_cards_with_page_preview=min_cards_with_page_preview,
        min_cards_with_source_package_summary=min_cards_with_source_package_summary,
        min_page_profiles_with_preview=min_page_profiles_with_preview,
        require_source_workbench_quality_pass=require_source_workbench_quality_pass,
        require_source_package_quality_pass=require_source_package_quality_pass,
    )
    if write_json_report:
        quality_path = Path(report_path).with_name("trace_net_human_review_workbench_preview_wiring_v1_quality.json")
        write_json(quality_path, quality)
        quality["quality_path"] = str(quality_path)
    return quality


def print_build_summary(report: dict[str, Any]) -> None:
    s = report["summary"]
    print("TRACE-Net Human Review Workbench Source/Image Preview Wiring v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "workbench_card_count",
        "page_scoped_workbench_card_count",
        "cards_with_page_preview_count",
        "cards_with_source_package_summary_count",
        "missing_page_preview_for_page_scoped_card_count",
        "cards_with_checksum_match_count",
        "cards_with_checksum_mismatch_count",
        "unsafe_preview_card_count",
        "preview_can_answer_directly_count",
        "preview_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" cards_path: {report.get('cards_path')}")
    print(f" pages_path: {report.get('pages_path')}")
    print(f" quality_path: {report.get('quality_path')}")


def print_quality_summary(quality: dict[str, Any]) -> None:
    s = quality.get("summary", {})
    print("TRACE-Net Human Review Workbench Source/Image Preview Wiring v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "workbench_card_count",
        "page_scoped_workbench_card_count",
        "cards_with_page_preview_count",
        "cards_with_source_package_summary_count",
        "missing_page_preview_for_page_scoped_card_count",
        "cards_with_checksum_mismatch_count",
        "unsafe_preview_card_count",
        "preview_can_answer_directly_count",
        "preview_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {s.get(key)}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality.get('quality_path')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Human Review Workbench Source/Image Preview Wiring v1")
    parser.add_argument("--human-review-workbench", required=True)
    parser.add_argument("--dublin-core-source-package-extension", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-workbench-cards", type=int, default=1)
    parser.add_argument("--min-page-profiles", type=int, default=1)
    parser.add_argument("--min-page-scoped-cards", type=int, default=1)
    parser.add_argument("--min-cards-with-page-preview", type=int, default=1)
    parser.add_argument("--min-cards-with-source-package-summary", type=int, default=1)
    parser.add_argument("--min-page-profiles-with-preview", type=int, default=1)
    parser.add_argument("--require-source-workbench-quality-pass", action="store_true")
    parser.add_argument("--require-source-package-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_preview_wiring(
        human_review_workbench_path=args.human_review_workbench,
        dublin_core_source_package_extension_path=args.dublin_core_source_package_extension,
        output_dir=args.output_dir,
        min_workbench_cards=args.min_workbench_cards,
        min_page_profiles=args.min_page_profiles,
        min_page_scoped_cards=args.min_page_scoped_cards,
        min_cards_with_page_preview=args.min_cards_with_page_preview,
        min_cards_with_source_package_summary=args.min_cards_with_source_package_summary,
        min_page_profiles_with_preview=args.min_page_profiles_with_preview,
        require_source_workbench_quality_pass=args.require_source_workbench_quality_pass,
        require_source_package_quality_pass=args.require_source_package_quality_pass,
        write_quality=args.quality,
    )
    print_build_summary(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
