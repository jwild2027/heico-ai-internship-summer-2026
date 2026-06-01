from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

DEFAULT_AUDIT_PATH = Path("local_data/organization/page_visual_objects_audit.json")
DEFAULT_QUALITY_PATH = Path("local_data/organization/page_visual_object_quality.json")


@dataclass(frozen=True)
class QualityCheck:
    name: str
    ok: bool
    message: str

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "message": self.message}


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_ok_status(value: Any) -> bool:
    return _lower(value) in {"ok", "pass", "passed", "success", "successful"}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _summary_from_audit(audit: Mapping[str, Any]) -> Dict[str, Any]:
    summary = audit.get("summary") if isinstance(audit.get("summary"), Mapping) else audit
    return dict(summary or {})


def summarize_page_visual_object_audit(
    audit: Mapping[str, Any],
    *,
    max_pages_without_ocr_text: int = 20,
) -> Tuple[Dict[str, Any], List[QualityCheck]]:
    source = _summary_from_audit(audit)
    role_counts = source.get("role_counts") if isinstance(source.get("role_counts"), Mapping) else {}

    status = source.get("status", audit.get("status", "unknown"))
    pages_checked = _as_int(source.get("pages_checked"))
    pages_with_context = _as_int(source.get("pages_with_context"))
    pages_without_context = _as_int(source.get("pages_without_context"), max(0, pages_checked - pages_with_context))
    pages_with_source_url = _as_int(source.get("pages_with_source_url"))
    pages_with_ocr_text = _as_int(source.get("pages_with_ocr_text"))
    pages_without_ocr_text = _as_int(source.get("pages_without_ocr_text"), max(0, pages_checked - pages_with_ocr_text))

    figure_role_pages = _as_int(source.get("figure_role_pages"), _as_int(role_counts.get("figure")))
    table_role_pages = _as_int(source.get("table_role_pages"), _as_int(role_counts.get("table")))
    parts_list_role_pages = _as_int(source.get("parts_list_role_pages"), _as_int(role_counts.get("parts_list")))
    procedure_role_pages = _as_int(source.get("procedure_role_pages"), _as_int(role_counts.get("procedure")))
    blank_role_pages = _as_int(source.get("blank_role_pages"), _as_int(role_counts.get("blank")))

    likely_visual_pages = _as_int(source.get("likely_visual_pages"))
    likely_figure_pages = _as_int(source.get("likely_figure_pages"))
    likely_table_pages = _as_int(source.get("likely_table_pages"))
    pages_with_figure_refs = _as_int(source.get("pages_with_figure_refs"))
    pages_with_sheet_refs = _as_int(source.get("pages_with_sheet_refs"))
    pages_with_table_refs = _as_int(source.get("pages_with_table_refs"))
    pages_with_illustration_refs = _as_int(source.get("pages_with_illustration_refs"))
    pages_with_image_terms = _as_int(source.get("pages_with_image_terms"))
    total_figure_refs = _as_int(source.get("total_figure_refs"))
    total_sheet_refs = _as_int(source.get("total_sheet_refs"))
    total_table_refs = _as_int(source.get("total_table_refs"))
    total_illustration_refs = _as_int(source.get("total_illustration_refs"))
    total_part_refs = _as_int(source.get("total_part_refs"))

    graph_page_context_nodes = _as_int(source.get("graph_page_context_nodes"))
    graph_has_context_edges = _as_int(source.get("graph_has_context_edges"))
    graph_tagged_as_edges = _as_int(source.get("graph_tagged_as_edges"))
    graph_highlights_part_edges = _as_int(source.get("graph_highlights_part_edges"))

    warnings = source.get("warnings") if isinstance(source.get("warnings"), list) else []

    out: Dict[str, Any] = {
        "page_visual_audit_present": True,
        "page_visual_audit_status": _lower(status),
        "page_visual_pages_checked": pages_checked,
        "page_visual_pages_with_context": pages_with_context,
        "page_visual_pages_without_context": pages_without_context,
        "page_visual_pages_with_source_url": pages_with_source_url,
        "page_visual_pages_with_ocr_text": pages_with_ocr_text,
        "page_visual_pages_without_ocr_text": pages_without_ocr_text,
        "page_visual_blank_role_pages": blank_role_pages,
        "page_visual_figure_role_pages": figure_role_pages,
        "page_visual_table_role_pages": table_role_pages,
        "page_visual_parts_list_role_pages": parts_list_role_pages,
        "page_visual_procedure_role_pages": procedure_role_pages,
        "page_visual_likely_visual_pages": likely_visual_pages,
        "page_visual_likely_figure_pages": likely_figure_pages,
        "page_visual_likely_table_pages": likely_table_pages,
        "page_visual_pages_with_figure_refs": pages_with_figure_refs,
        "page_visual_pages_with_sheet_refs": pages_with_sheet_refs,
        "page_visual_pages_with_table_refs": pages_with_table_refs,
        "page_visual_pages_with_illustration_refs": pages_with_illustration_refs,
        "page_visual_pages_with_image_terms": pages_with_image_terms,
        "page_visual_total_figure_refs": total_figure_refs,
        "page_visual_total_sheet_refs": total_sheet_refs,
        "page_visual_total_table_refs": total_table_refs,
        "page_visual_total_illustration_refs": total_illustration_refs,
        "page_visual_total_part_refs": total_part_refs,
        "page_visual_graph_page_context_nodes": graph_page_context_nodes,
        "page_visual_graph_has_context_edges": graph_has_context_edges,
        "page_visual_graph_tagged_as_edges": graph_tagged_as_edges,
        "page_visual_graph_highlights_part_edges": graph_highlights_part_edges,
        "page_visual_warnings": len(warnings),
    }

    checks = [
        QualityCheck("page_visual_audit_status", _is_ok_status(status), f"Page visual/object audit status is {status}."),
        QualityCheck("page_visual_pages_checked", pages_checked > 0, f"Pages checked={pages_checked}; minimum is 1."),
        QualityCheck("page_visual_context_coverage", pages_without_context == 0 and pages_with_context == pages_checked, f"Pages with context={pages_with_context}/{pages_checked}; pages without context={pages_without_context}."),
        QualityCheck("page_visual_source_coverage", pages_with_source_url == pages_checked, f"Pages with source URLs={pages_with_source_url}/{pages_checked}."),
        QualityCheck("page_visual_ocr_visibility", pages_without_ocr_text <= max_pages_without_ocr_text, f"Pages without visible OCR text={pages_without_ocr_text}; max allowed={max_pages_without_ocr_text}."),
        QualityCheck("page_visual_role_counts", sum(_as_int(v) for v in role_counts.values()) == pages_checked, f"Role counts sum={sum(_as_int(v) for v in role_counts.values())}; pages checked={pages_checked}."),
        QualityCheck("page_visual_visual_signals", likely_visual_pages > 0 and pages_with_figure_refs > 0, f"Likely visual pages={likely_visual_pages}; pages with figure refs={pages_with_figure_refs}."),
        QualityCheck("page_visual_table_signals", table_role_pages > 0 or likely_table_pages > 0 or pages_with_table_refs > 0, f"Table-role pages={table_role_pages}; likely table pages={likely_table_pages}; pages with table refs={pages_with_table_refs}."),
        QualityCheck("page_visual_graph_context_nodes", graph_page_context_nodes >= pages_checked, f"Graph page_context nodes={graph_page_context_nodes}; pages checked={pages_checked}."),
        QualityCheck("page_visual_graph_has_context_edges", graph_has_context_edges >= pages_checked, f"Graph HAS_CONTEXT edges={graph_has_context_edges}; pages checked={pages_checked}."),
        QualityCheck("page_visual_graph_context_edges", graph_tagged_as_edges > 0 and graph_highlights_part_edges > 0, f"TAGGED_AS edges={graph_tagged_as_edges}; HIGHLIGHTS_PART edges={graph_highlights_part_edges}."),
    ]
    return out, checks


def build_page_visual_object_quality(
    audit_path: Path = DEFAULT_AUDIT_PATH,
    *,
    max_pages_without_ocr_text: int = 20,
) -> Dict[str, Any]:
    if not audit_path.exists():
        summary = {
            "page_visual_audit_present": False,
            "page_visual_pages_checked": 0,
        }
        checks = [QualityCheck("page_visual_audit_present", False, f"Page visual/object audit JSON is missing: {audit_path}")]
        return {"status": "fail", "summary": summary, "checks": [check.as_dict() for check in checks]}

    audit = _load_json(audit_path)
    summary, checks = summarize_page_visual_object_audit(audit, max_pages_without_ocr_text=max_pages_without_ocr_text)
    checks.insert(0, QualityCheck("page_visual_audit_present", True, f"Page visual/object audit JSON is present at {audit_path}."))
    status = "ok" if all(check.ok for check in checks) else "fail"
    return {"status": status, "summary": summary, "checks": [check.as_dict() for check in checks]}


def write_page_visual_object_quality(report: Mapping[str, Any], output_path: Path = DEFAULT_QUALITY_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
