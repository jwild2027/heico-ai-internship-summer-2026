from __future__ import annotations

import argparse
import csv
import html
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MODULE = "trace_net_gold_label_review_workbook_v1"
VERSION = "v1"
STATUS = "TRACE_NET_GOLD_LABEL_REVIEW_WORKBOOK_BUILT"
REPORT_NAME = "trace_net_gold_label_review_workbook_v1.json"
RECORDS_NAME = "trace_net_gold_label_review_workbook_v1_records.jsonl"
CSV_NAME = "trace_net_gold_label_review_workbook_v1.csv"
XLSX_NAME = "trace_net_gold_label_review_workbook_v1.xlsx"
HTML_NAME = "trace_net_gold_label_review_workbook_v1.html"
SUMMARY_NAME = "trace_net_gold_label_review_workbook_v1_summary.json"
MARKDOWN_NAME = "trace_net_gold_label_review_workbook_v1.md"
QUALITY_NAME = "trace_net_gold_label_review_workbook_v1_quality_check.json"

REVIEW_COLUMNS = [
    "page_number",
    "page_id",
    "source_member",
    "source_image_path",
    "source_image_sha256",
    "legacy_route",
    "suggested_canonical_route",
    "suggested_route_confidence",
    "suggested_route_reasons",
    "gold_route_label",
    "review_status",
    "review_notes",
    "ocr_word_count",
    "ocr_char_count",
    "part_number_count",
    "part_number_sample",
    "ocr_sample_text",
    "raw_route_reasons",
    "processor_contract",
    "answer_permission",
    "source_truth_mutation_allowed",
]

CANONICAL_ROUTE_ORDER = [
    "blank_candidate",
    "cover_or_title_page",
    "normal_text",
    "procedure_or_description",
    "table_or_index",
    "detailed_parts_list",
    "image_visual_diagram",
    "mixed_text_and_figure",
    "review_required",
]


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("records", "scan_records", "page_records", "cards"):
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
    return []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _text_blob(record: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in ("ocr_sample_text", "sample_text", "route_reasons", "part_number_tokens"):
        value = record.get(key)
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif value is not None:
            parts.append(str(value))
    return "\n".join(parts)


def _contains_any(text: str, patterns: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(p.lower() in lowered for p in patterns)


def _part_numbers(record: Mapping[str, Any]) -> list[str]:
    value = record.get("part_number_tokens") or []
    if isinstance(value, list):
        return sorted({str(v) for v in value if str(v).strip()})
    text = str(value)
    return sorted(set(re.findall(r"\b\d{3}-\d{5}-\d{3}\b", text)))


def _strong_contains_any(text: str, patterns: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(p.lower() in lowered for p in patterns)


def _has_regex(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None


def _suggest_canonical_route(record: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    """Suggest the 9-label canonical route conservatively.

    Tuning intent: do not let generic IPL/header words ("figure", "illustrated parts list",
    "item") turn hundreds of tabular/detail pages into image_visual_diagram. Visual routing
    requires either an existing image_visual route with limited text or concrete diagram-label
    signals. Part-number and table/index structure win before visual hints.
    """
    legacy = str(record.get("accepted_route") or record.get("route") or "review_required")
    page = _as_int(record.get("canonical_page_number"))
    words = _as_int(record.get("ocr_text_word_count"))
    chars = _as_int(record.get("ocr_text_char_count"))
    pns = _part_numbers(record)
    pn_count = len(pns)
    blob = _text_blob(record)
    lowered = blob.lower()
    reasons: list[str] = []

    if legacy == "blank_candidate" or (words == 0 and chars == 0):
        reasons.append("empty_or_near_empty_ocr")
        return "blank_candidate", "high", reasons

    cover_terms = [
        "component maintenance manual",
        "this publication supersedes",
        "revision 4",
        "passenger seats",
        "empresa brasileira",
        "embraer",
    ]
    if page <= 2 and _contains_any(blob, cover_terms) and pn_count < 3 and words < 180:
        reasons.extend(["front_matter_page_number", "publication_identity_terms", "low_part_number_count"])
        return "cover_or_title_page", "high", reasons

    detailed_terms = [
        "part number",
        "nomenclature",
        "units per assy",
        "units per assembly",
        "airline part number",
        "fig - item",
        "figure item",
        "detailed parts list",
        "vendor code",
    ]
    # Part-number evidence is stronger than generic figure/item text. This prevents IPL
    # tables from being misclassified as diagrams just because they mention figures/items.
    if pn_count >= 8:
        reasons.extend(["high_part_number_density", "detailed_parts_list_candidate"])
        return "detailed_parts_list", "high", reasons
    if pn_count >= 2 and _contains_any(blob, detailed_terms):
        reasons.extend(["multiple_part_numbers", "ipl_column_terms"])
        return "detailed_parts_list", "high", reasons
    if pn_count >= 1 and _contains_any(blob, ["part number", "nomenclature", "units", "vendor code"]):
        reasons.extend(["part_number_present", "ipl_column_terms"])
        return "detailed_parts_list", "medium", reasons

    table_terms = [
        "chapter",
        "section",
        "subject",
        "page date",
        "lep",
        "contents",
        "vendor code",
        "vendor's list",
        "numerical index",
        "service bulletin record",
        "issued",
        "revisions",
        "column",
        "ttl reg",
        "airline stock number",
    ]
    procedure_terms = [
        "description and operation",
        "general",
        "description",
        "removal",
        "installation",
        "inspection",
        "repair",
        "cleaning",
        "the passenger seats are arranged",
        "the purpose of this index",
        "this section lists",
    ]
    figure_caption = _has_regex(blob, r"\bfigure\s+\d+[a-z]?\b")
    visual_label_terms = [
        "seat backrest",
        "seat backrests",
        "seat belt",
        "ashtray",
        "floatable seat bottom",
        "single passenger seat",
        "double passenger seat",
        "triple passenger seat",
        ".mce",
        ".mci",
    ]
    visual_label_signal = _contains_any(blob, visual_label_terms)
    generic_figure_only = "figure" in lowered and not visual_label_signal and not figure_caption
    prose_signal = _contains_any(blob, procedure_terms) and words >= 80
    table_index_signal = _contains_any(blob, table_terms)

    # Procedures/prose with a figure reference are mixed only when there is a concrete figure
    # caption/visual label. Generic IPL references to figures/items are not diagrams.
    if prose_signal and pn_count == 0:
        if (figure_caption or visual_label_signal) and words >= 120:
            reasons.extend(["visual_signal_present", "meaningful_prose_present", "low_part_number_count"])
            return "mixed_text_and_figure", "medium", reasons
        reasons.extend(["procedure_or_description_terms", "paragraph_text_present", "low_part_number_count"])
        return "procedure_or_description", "high", reasons

    # Visual diagram is intentionally conservative. In this manual, hundreds of IPL/table
    # records mention figures/items, so figure captions alone are not enough to call a page a
    # diagram. A page becomes image_visual_diagram only when the upstream OCR router already
    # identified it as visual, or when concrete diagram label text appears on a sparse, non-table,
    # no-part-number page. Otherwise figure references remain table/prose/mixed evidence.
    if legacy == "image_visual":
        reasons.extend(["legacy_image_visual_route", "figure_or_visual_label_signal"])
        return "image_visual_diagram", "high", reasons

    sparse_visual_candidate = (
        visual_label_signal
        and words <= 90
        and pn_count == 0
        and not table_index_signal
        and not _contains_any(blob, ["assy number", "ch-sec-un-fig", "item] assy", "nomenclature", "vendor code"])
    )
    if sparse_visual_candidate:
        reasons.extend(["concrete_visual_label_signal", "sparse_non_table_text"])
        return "image_visual_diagram", "medium", reasons

    if (figure_caption or visual_label_signal) and prose_signal and pn_count == 0:
        reasons.extend(["visual_signal_present", "meaningful_prose_present", "not_sparse_enough_for_diagram"])
        return "mixed_text_and_figure", "medium", reasons

    if table_index_signal:
        reasons.append("table_index_terms")
        if legacy == "table":
            reasons.append("legacy_table_route")
        return "table_or_index", "high" if legacy == "table" and words >= 50 else "medium", reasons

    if legacy == "table":
        reasons.append("legacy_table_route_without_strong_detail_or_visual_signal")
        return "table_or_index", "medium", reasons

    if legacy == "normal_text" or words >= 80:
        reasons.append("paragraph_or_general_text_density")
        return "normal_text", "medium" if legacy != "normal_text" else "high", reasons

    if generic_figure_only:
        reasons.append("generic_figure_reference_without_visual_label")
        return "review_required", "low", reasons

    reasons.append("insufficient_or_conflicting_signals")
    return "review_required", "low", reasons

def _make_review_record(scan_record: Mapping[str, Any], index: int) -> dict[str, Any]:
    suggested, confidence, reasons = _suggest_canonical_route(scan_record)
    pns = _part_numbers(scan_record)
    legacy_route = scan_record.get("accepted_route") or scan_record.get("route") or "unknown"
    route_reasons = scan_record.get("route_reasons") or []
    if not isinstance(route_reasons, list):
        route_reasons = [str(route_reasons)]
    sample = str(scan_record.get("ocr_sample_text") or scan_record.get("sample_text") or "")
    review_status = "needs_review"
    if suggested in {"blank_candidate", "image_visual_diagram"} and confidence == "high":
        review_status = "auto_suggested_review_recommended"
    return {
        "record_type": "gold_label_review_row",
        "module": MODULE,
        "version": VERSION,
        "suggestion_tuning_version": "route_suggestion_tuning_v3_visual_clamp",
        "review_row_id": f"gold_label_review_{index:06d}",
        "page_number": _as_int(scan_record.get("canonical_page_number"), index),
        "page_id": scan_record.get("page_id") or f"page_{index:06d}",
        "source_member": scan_record.get("source_member"),
        "source_image_path": scan_record.get("source_image_path"),
        "source_image_sha256": scan_record.get("source_image_sha256"),
        "legacy_route": legacy_route,
        "suggested_canonical_route": suggested,
        "suggested_route_confidence": confidence,
        "suggested_route_reasons": reasons,
        "gold_route_label": "",
        "review_status": review_status,
        "review_notes": "",
        "ocr_word_count": _as_int(scan_record.get("ocr_text_word_count")),
        "ocr_char_count": _as_int(scan_record.get("ocr_text_char_count")),
        "part_number_count": len(pns),
        "part_number_sample": pns[:20],
        "ocr_sample_text": sample[:1200],
        "raw_route_reasons": route_reasons,
        "processor_contract": scan_record.get("route_processor") or scan_record.get("processor_contract"),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def _csv_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value)


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({column: _csv_value(record.get(column)) for column in REVIEW_COLUMNS})


def _xlsx_col_name(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def _xml_escape(value: Any) -> str:
    return html.escape(_csv_value(value), quote=True)


def _sheet_xml(rows: Sequence[Sequence[Any]], widths: Sequence[int] | None = None) -> str:
    cols = ""
    if widths:
        col_bits = []
        for idx, width in enumerate(widths, 1):
            col_bits.append(f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>')
        cols = "<cols>" + "".join(col_bits) + "</cols>"
    row_xml: list[str] = []
    for r_idx, row in enumerate(rows, 1):
        cells = []
        for c_idx, value in enumerate(row, 1):
            ref = f"{_xlsx_col_name(c_idx)}{r_idx}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{_xml_escape(value)}</t></is></c>')
        row_xml.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'{cols}<sheetData>{"".join(row_xml)}</sheetData></worksheet>'
    )


def _write_xlsx(path: Path, records: Sequence[Mapping[str, Any]], taxonomy_records: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary_rows = [["Metric", "Value"]] + [[key, json.dumps(value) if isinstance(value, (list, dict)) else value] for key, value in summary.items()]
    review_rows: list[list[Any]] = [REVIEW_COLUMNS]
    for record in records:
        review_rows.append([_csv_value(record.get(column)) for column in REVIEW_COLUMNS])
    taxonomy_columns = ["label", "display_name", "family", "definition", "default_processor_contract", "review_policy"]
    taxonomy_rows = [taxonomy_columns]
    for record in taxonomy_records:
        taxonomy_rows.append([_csv_value(record.get(column)) for column in taxonomy_columns])

    workbook_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Summary" sheetId="1" r:id="rId1"/><sheet name="Gold Review" sheetId="2" r:id="rId2"/><sheet name="Taxonomy" sheetId="3" r:id="rId3"/></sheets></workbook>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/></Relationships>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml(summary_rows, widths=[32, 48]))
        zf.writestr("xl/worksheets/sheet2.xml", _sheet_xml(review_rows, widths=[10, 24, 18, 48, 18, 16, 24, 16, 40, 24, 18, 36, 14, 14, 14, 44, 64, 40, 32, 16, 18]))
        zf.writestr("xl/worksheets/sheet3.xml", _sheet_xml(taxonomy_rows, widths=[24, 28, 18, 60, 36, 48]))


def _write_html(path: Path, records: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(record.get('page_number')))}</td>"
            f"<td>{html.escape(str(record.get('page_id')))}</td>"
            f"<td>{html.escape(str(record.get('legacy_route')))}</td>"
            f"<td>{html.escape(str(record.get('suggested_canonical_route')))}</td>"
            f"<td>{html.escape(str(record.get('suggested_route_confidence')))}</td>"
            f"<td>{html.escape(str(record.get('ocr_word_count')))}</td>"
            f"<td>{html.escape(str(record.get('part_number_count')))}</td>"
            f"<td><code>{html.escape(str(record.get('source_image_path') or ''))}</code></td>"
            f"<td><pre>{html.escape(str(record.get('ocr_sample_text') or '')[:500])}</pre></td>"
            "</tr>"
        )
    text = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>TRACE-Net Gold Label Review Workbook</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:6px;vertical-align:top}}th{{background:#f3f5f7}}pre{{white-space:pre-wrap;max-width:520px}}</style></head>
<body><h1>TRACE-Net Gold Label Review Workbook</h1><pre>{html.escape(json.dumps(summary, indent=2, sort_keys=True))}</pre><table><thead><tr><th>Page</th><th>Page ID</th><th>Legacy</th><th>Suggested canonical</th><th>Confidence</th><th>Words</th><th>Parts</th><th>Image path</th><th>OCR sample</th></tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""
    path.write_text(text, encoding="utf-8")


def _quality_status(summary: Mapping[str, Any], min_review_rows: int = 1) -> str:
    if summary.get("review_row_count", 0) < min_review_rows:
        return "FAIL"
    if summary.get("canonical_route_label_count", 0) < 1:
        return "FAIL"
    if summary.get("answer_permission_count", 0) != 0:
        return "FAIL"
    if summary.get("source_truth_mutation_allowed_count", 0) != 0:
        return "FAIL"
    if summary.get("unsafe_record_count", 0) != 0:
        return "FAIL"
    return "PASS"


def build_gold_label_review_workbook(
    *,
    scan_pack_path: str | Path,
    route_label_taxonomy_path: str | Path,
    output_dir: str | Path,
    source_package: str | Path | None = None,
    quality: bool = False,
) -> dict[str, Any]:
    scan_path = Path(scan_pack_path)
    taxonomy_path = Path(route_label_taxonomy_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    scan_payload = _load_json(scan_path)
    taxonomy_payload = _load_json(taxonomy_path)
    scan_records = _records(scan_payload)
    taxonomy_records = _records(taxonomy_payload)
    labels = {str(record.get("label")) for record in taxonomy_records}

    review_records = [_make_review_record(record, idx) for idx, record in enumerate(scan_records, 1)]
    suggested_counts = Counter(record["suggested_canonical_route"] for record in review_records)
    legacy_counts = Counter(str(record["legacy_route"]) for record in review_records)
    confidence_counts = Counter(str(record["suggested_route_confidence"]) for record in review_records)
    invalid_suggestions = sorted({label for label in suggested_counts if label not in labels})

    summary: dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "source_scan_pack": str(scan_path),
        "source_scan_pack_quality_status": scan_payload.get("quality_status"),
        "source_scan_record_count": len(scan_records),
        "source_package": str(source_package) if source_package else scan_payload.get("summary", {}).get("source_package"),
        "route_label_taxonomy": str(taxonomy_path),
        "route_label_taxonomy_quality_status": taxonomy_payload.get("quality_status"),
        "canonical_route_label_count": len(labels),
        "review_row_count": len(review_records),
        "suggested_route_counts": dict(sorted(suggested_counts.items())),
        "legacy_route_counts": dict(sorted(legacy_counts.items())),
        "suggested_confidence_counts": dict(sorted(confidence_counts.items())),
        "invalid_suggested_route_label_count": len(invalid_suggestions),
        "invalid_suggested_route_labels": invalid_suggestions,
        "ready_for_human_gold_labeling": True,
        "workbook_path": str(output / XLSX_NAME),
        "csv_path": str(output / CSV_NAME),
        "html_path": str(output / HTML_NAME),
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unsafe_record_count": 0,
    }
    summary["quality_status"] = _quality_status(summary)

    _write_csv(output / CSV_NAME, review_records)
    _write_xlsx(output / XLSX_NAME, review_records, taxonomy_records, summary)
    _write_html(output / HTML_NAME, review_records, summary)
    _write_jsonl(output / RECORDS_NAME, review_records)
    _write_json(output / SUMMARY_NAME, summary)

    markdown = "\n".join(
        [
            "# TRACE-Net Gold Label Review Workbook v1",
            "",
            f"Quality status: {summary['quality_status']}",
            f"Review rows: {summary['review_row_count']}",
            "",
            "## Suggested route counts",
            "",
            json.dumps(summary["suggested_route_counts"], indent=2, sort_keys=True),
            "",
            "This artifact has no answer permission and does not mutate source truth.",
        ]
    )
    _write_text(output / MARKDOWN_NAME, markdown)

    payload: dict[str, Any] = {
        "status": STATUS,
        "quality_status": summary["quality_status"],
        "summary": summary,
        "records": review_records,
        "canonical_route_labels": sorted(labels),
        "review_columns": REVIEW_COLUMNS,
    }
    _write_json(output / REPORT_NAME, payload)
    if quality:
        _write_json(output / QUALITY_NAME, {"quality_status": summary["quality_status"], "summary": summary, "failures": [] if summary["quality_status"] == "PASS" else ["quality checks failed"]})
    print(f"Status: {STATUS}")
    print(f"Quality status: {summary['quality_status']}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_gold_label_review_workbook_quality(
    *,
    report_path: str | Path,
    min_review_rows: int = 1,
    min_route_labels: int = 1,
    require_source_scan_pack_quality_pass: bool = False,
    require_taxonomy_quality_pass: bool = False,
    require_workbook: bool = False,
    require_review_columns: bool = False,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    max_unsafe: int | None = None,
    max_suggested_image_visual_diagram: int | None = None,
    min_suggested_detailed_parts_list: int | None = None,
    write_json: bool = False,
) -> dict[str, Any]:
    path = Path(report_path)
    payload = _load_json(path)
    summary = payload.get("summary") or {}
    failures: list[str] = []
    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if _as_int(summary.get("review_row_count")) < min_review_rows:
        failures.append("not enough review rows")
    if _as_int(summary.get("canonical_route_label_count")) < min_route_labels:
        failures.append("not enough canonical route labels")
    if require_source_scan_pack_quality_pass and summary.get("source_scan_pack_quality_status") != "PASS":
        failures.append("source scan pack quality_status is not PASS")
    if require_taxonomy_quality_pass and summary.get("route_label_taxonomy_quality_status") != "PASS":
        failures.append("route label taxonomy quality_status is not PASS")
    if require_workbook:
        for key in ("workbook_path", "csv_path", "html_path"):
            candidate = summary.get(key)
            if not candidate or not Path(candidate).exists():
                failures.append(f"missing output file: {key}")
    if require_review_columns:
        columns = payload.get("review_columns") or []
        missing = [column for column in ("gold_route_label", "review_status", "review_notes") if column not in columns]
        if missing:
            failures.append("missing review columns: " + ", ".join(missing))
    if max_unsafe is not None and _as_int(summary.get("unsafe_record_count")) > max_unsafe:
        failures.append("too many unsafe records")
    suggested_counts = summary.get("suggested_route_counts") or {}
    if max_suggested_image_visual_diagram is not None and _as_int(suggested_counts.get("image_visual_diagram")) > max_suggested_image_visual_diagram:
        failures.append("too many suggested image_visual_diagram routes")
    if min_suggested_detailed_parts_list is not None and _as_int(suggested_counts.get("detailed_parts_list")) < min_suggested_detailed_parts_list:
        failures.append("not enough suggested detailed_parts_list routes")
    if require_no_answer_permission and _as_int(summary.get("answer_permission_count")) != 0:
        failures.append("answer permission present")
    if require_no_source_truth_mutation and _as_int(summary.get("source_truth_mutation_allowed_count")) != 0:
        failures.append("source truth mutation allowed")
    if require_no_write_attempts:
        for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
            if _as_int(summary.get(key)) != 0:
                failures.append(f"{key} is not zero")
    status = "PASS" if not failures else "FAIL"
    result = {"quality_status": status, "summary": summary, "failures": failures}
    if write_json:
        _write_json(path.with_name("trace_net_gold_label_review_workbook_v1_quality_check.json"), result)
        print(f"Wrote: {path.with_name('trace_net_gold_label_review_workbook_v1_quality_check.json')}")
    print(f"Quality status: {status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def main_build(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build TRACE-Net gold-label review workbook v1")
    parser.add_argument("--scan-pack", required=True)
    parser.add_argument("--route-label-taxonomy", required=True)
    parser.add_argument("--source-package")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    return build_gold_label_review_workbook(
        scan_pack_path=args.scan_pack,
        route_label_taxonomy_path=args.route_label_taxonomy,
        source_package=args.source_package,
        output_dir=args.output_dir,
        quality=args.quality,
    )


def main_check(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net gold-label review workbook v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-review-rows", type=int, default=1)
    parser.add_argument("--min-route-labels", type=int, default=1)
    parser.add_argument("--require-source-scan-pack-quality-pass", action="store_true")
    parser.add_argument("--require-taxonomy-quality-pass", action="store_true")
    parser.add_argument("--require-workbook", action="store_true")
    parser.add_argument("--require-review-columns", action="store_true")
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--max-suggested-image-visual-diagram", type=int)
    parser.add_argument("--min-suggested-detailed-parts-list", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    return check_gold_label_review_workbook_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_review_rows=args.min_review_rows,
        min_route_labels=args.min_route_labels,
        require_source_scan_pack_quality_pass=args.require_source_scan_pack_quality_pass,
        require_taxonomy_quality_pass=args.require_taxonomy_quality_pass,
        require_workbook=args.require_workbook,
        require_review_columns=args.require_review_columns,
        max_unsafe=args.max_unsafe,
        max_suggested_image_visual_diagram=args.max_suggested_image_visual_diagram,
        min_suggested_detailed_parts_list=args.min_suggested_detailed_parts_list,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":
    main_build()
