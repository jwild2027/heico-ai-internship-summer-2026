"""Quality gate for model-assisted visual text extraction artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tiff.visual_text_extraction import DEFAULT_OUTPUT_DIR


@dataclass(frozen=True)
class VisualTextQualityPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR

    @property
    def records_path(self) -> Path:
        return self.output_dir / "visual_text_extraction.jsonl"

    @property
    def summary_path(self) -> Path:
        return self.output_dir / "visual_text_extraction_summary.json"

    @property
    def corpus_md_path(self) -> Path:
        return self.output_dir / "visual_text_corpus.md"

    @property
    def graph_nodes_path(self) -> Path:
        return self.output_dir / "visual_text_graph_nodes.json"

    @property
    def graph_edges_path(self) -> Path:
        return self.output_dir / "visual_text_graph_edges.json"

    @property
    def quality_path(self) -> Path:
        return self.output_dir / "visual_text_quality.json"


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _count_graph_items(path: Path, key: str) -> int:
    data = _load_json(path, default={})
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        value = data.get(key)
        if isinstance(value, list):
            return len(value)
        for fallback in ("items", "records"):
            if isinstance(data.get(fallback), list):
                return len(data[fallback])
    return 0


def _check(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "message": message}


def build_visual_text_extraction_quality(
    paths: VisualTextQualityPaths | None = None,
    *,
    min_records: int = 1,
    min_pages_with_visual_text: int = 1,
    max_error_records: int = 0,
    allow_planned: bool = True,
    allow_partial_status: bool = False,
    require_v2: bool = False,
    require_v2_2: bool = False,
    min_required_section_records: int = 0,
    max_summary_heavy_records: int | None = None,
    max_hallucination_risk_records: int | None = None,
    max_refusal_like_records: int | None = None,
    max_metadata_leakage_records: int | None = None,
) -> dict[str, Any]:
    paths = paths or VisualTextQualityPaths()
    summary_present = paths.summary_path.exists()
    records_present = paths.records_path.exists()
    corpus_present = paths.corpus_md_path.exists()
    graph_nodes_present = paths.graph_nodes_path.exists()
    graph_edges_present = paths.graph_edges_path.exists()

    summary = _as_dict(_load_json(paths.summary_path, default={})) if summary_present else {}
    records = _load_jsonl(paths.records_path)
    graph_nodes = _count_graph_items(paths.graph_nodes_path, "nodes") if graph_nodes_present else 0
    graph_edges = _count_graph_items(paths.graph_edges_path, "edges") if graph_edges_present else 0
    corpus_chars = len(paths.corpus_md_path.read_text(encoding="utf-8")) if corpus_present else 0

    status = str(summary.get("status") or "missing").upper()
    total_records = _to_int(summary.get("records"), len(records))
    ok_records = _to_int(summary.get("ok_records"))
    planned_records = _to_int(summary.get("planned_records"))
    error_records = _to_int(summary.get("error_records"))
    selected_pages = _to_int(summary.get("selected_pages"))
    pages_with_visual_text = _to_int(summary.get("pages_with_visual_text"))
    visual_text_char_total = _to_int(summary.get("visual_text_char_total"))
    avg_chars = _to_float(summary.get("visual_text_avg_chars"))
    v2_records = _to_int(summary.get("visual_text_v2_records"))
    v2_2_records = _to_int(summary.get("visual_text_v2_2_records"))
    required_section_records = _to_int(summary.get("visual_text_required_sections_records"))
    transcribed_records = _to_int(summary.get("visual_text_transcribed_records"))
    table_row_records = _to_int(summary.get("visual_text_table_row_records"))
    label_records = _to_int(summary.get("visual_text_label_callout_records"))
    part_number_records = _to_int(summary.get("visual_text_part_number_records"))
    ocr_context_note_records = _to_int(summary.get("visual_text_ocr_context_note_records"))
    metadata_leakage_records = _to_int(summary.get("visual_text_metadata_leakage_records"))
    metadata_leakage_marker_total = _to_int(summary.get("visual_text_metadata_leakage_marker_total"))
    summary_heavy_records = _to_int(summary.get("visual_text_summary_heavy_records"))
    hallucination_risk_records = _to_int(summary.get("visual_text_hallucination_risk_records"))
    refusal_like_records = _to_int(summary.get("visual_text_refusal_like_records"))

    accepted_records = ok_records + (planned_records if allow_planned else 0)
    status_ok = status == "OK" or (
        allow_partial_status
        and status in {"PARTIAL", "FAIL"}
        and accepted_records >= min_records
        and error_records <= max_error_records
    )
    summary_out = {
        "visual_text_summary_present": summary_present,
        "visual_text_records_present": records_present,
        "visual_text_corpus_present": corpus_present,
        "visual_text_status": status.lower(),
        "visual_text_status_accepted": status_ok,
        "visual_text_allow_partial_status": allow_partial_status,
        "visual_text_provider": summary.get("provider"),
        "visual_text_model": summary.get("model"),
        "visual_text_total_page_cards": _to_int(summary.get("total_page_cards")),
        "visual_text_selected_pages": selected_pages,
        "visual_text_records": total_records,
        "visual_text_ok_records": ok_records,
        "visual_text_planned_records": planned_records,
        "visual_text_accepted_records": accepted_records,
        "visual_text_error_records": error_records,
        "visual_text_pages_with_visual_text": pages_with_visual_text,
        "visual_text_char_total": visual_text_char_total,
        "visual_text_avg_chars": avg_chars,
        "visual_text_prompt_version": summary.get("prompt_version"),
        "visual_text_ocr_assist_enabled": summary.get("ocr_assist_enabled"),
        "visual_text_v2_records": v2_records,
        "visual_text_v2_2_records": v2_2_records,
        "visual_text_required_sections_records": required_section_records,
        "visual_text_transcribed_records": transcribed_records,
        "visual_text_table_row_records": table_row_records,
        "visual_text_label_callout_records": label_records,
        "visual_text_part_number_records": part_number_records,
        "visual_text_ocr_context_note_records": ocr_context_note_records,
        "visual_text_metadata_leakage_records": metadata_leakage_records,
        "visual_text_metadata_leakage_marker_total": metadata_leakage_marker_total,
        "visual_text_summary_heavy_records": summary_heavy_records,
        "visual_text_hallucination_risk_records": hallucination_risk_records,
        "visual_text_refusal_like_records": refusal_like_records,
        "visual_text_require_v2": require_v2,
        "visual_text_require_v2_2": require_v2_2,
        "visual_text_min_required_section_records": min_required_section_records,
        "visual_text_max_summary_heavy_records": max_summary_heavy_records,
        "visual_text_max_hallucination_risk_records": max_hallucination_risk_records,
        "visual_text_max_refusal_like_records": max_refusal_like_records,
        "visual_text_max_metadata_leakage_records": max_metadata_leakage_records,
        "visual_text_graph_nodes_present": graph_nodes_present,
        "visual_text_graph_edges_present": graph_edges_present,
        "visual_text_graph_nodes": graph_nodes,
        "visual_text_graph_edges": graph_edges,
        "visual_text_corpus_chars": corpus_chars,
        "visual_text_records_path": str(paths.records_path),
        "visual_text_summary_path": str(paths.summary_path),
        "visual_text_corpus_md_path": str(paths.corpus_md_path),
        "visual_text_graph_nodes_path": str(paths.graph_nodes_path),
        "visual_text_graph_edges_path": str(paths.graph_edges_path),
    }

    checks = [
        _check(
            "visual_text_artifacts_present",
            summary_present and records_present and corpus_present,
            f"summary={summary_present}; records={records_present}; corpus={corpus_present}.",
        ),
        _check(
            "visual_text_status",
            status_ok,
            f"Visual text extraction status is {status!r}; allow_partial_status={allow_partial_status}; max_error_records={max_error_records}.",
        ),
        _check(
            "visual_text_records",
            total_records >= min_records and len(records) >= min_records,
            f"records summary={total_records}, jsonl={len(records)}; minimum is {min_records}.",
        ),
        _check(
            "visual_text_accepted_records",
            accepted_records >= min_records,
            f"accepted records={accepted_records}; minimum is {min_records}; allow_planned={allow_planned}.",
        ),
        _check(
            "visual_text_pages_with_text",
            pages_with_visual_text >= min_pages_with_visual_text,
            f"pages_with_visual_text={pages_with_visual_text}; minimum is {min_pages_with_visual_text}.",
        ),
        _check(
            "visual_text_errors",
            error_records <= max_error_records,
            f"error_records={error_records}; max allowed={max_error_records}.",
        ),
        _check(
            "visual_text_chars",
            visual_text_char_total > 0 and corpus_chars > 0,
            f"visual_text_char_total={visual_text_char_total}; corpus_chars={corpus_chars}.",
        ),
        _check(
            "visual_text_v2_records",
            (not require_v2) or (v2_records >= accepted_records and accepted_records >= min_records),
            f"v2_records={v2_records}; accepted_records={accepted_records}; require_v2={require_v2}.",
        ),
        _check(
            "visual_text_v2_2_records",
            (not require_v2_2) or (v2_2_records >= accepted_records and accepted_records >= min_records),
            f"v2_2_records={v2_2_records}; accepted_records={accepted_records}; require_v2_2={require_v2_2}.",
        ),
        _check(
            "visual_text_required_sections",
            required_section_records >= min_required_section_records,
            f"required-section records={required_section_records}; minimum={min_required_section_records}.",
        ),
        _check(
            "visual_text_summary_heavy",
            max_summary_heavy_records is None or summary_heavy_records <= max_summary_heavy_records,
            f"summary-heavy records={summary_heavy_records}; max={max_summary_heavy_records}.",
        ),
        _check(
            "visual_text_hallucination_risk",
            max_hallucination_risk_records is None or hallucination_risk_records <= max_hallucination_risk_records,
            f"hallucination-risk records={hallucination_risk_records}; max={max_hallucination_risk_records}.",
        ),
        _check(
            "visual_text_refusal_like",
            max_refusal_like_records is None or refusal_like_records <= max_refusal_like_records,
            f"refusal-like records={refusal_like_records}; max={max_refusal_like_records}.",
        ),
        _check(
            "visual_text_metadata_leakage",
            max_metadata_leakage_records is None or metadata_leakage_records <= max_metadata_leakage_records,
            f"metadata-leakage records={metadata_leakage_records}; markers={metadata_leakage_marker_total}; max={max_metadata_leakage_records}.",
        ),
        _check(
            "visual_text_graph_overlay_nodes",
            graph_nodes_present and graph_nodes >= accepted_records,
            f"graph nodes present={graph_nodes_present}; nodes={graph_nodes}; accepted_records={accepted_records}.",
        ),
        _check(
            "visual_text_graph_overlay_edges",
            graph_edges_present and graph_edges >= accepted_records,
            f"graph edges present={graph_edges_present}; edges={graph_edges}; accepted_records={accepted_records}.",
        ),
    ]

    gate_status = "OK" if all(check["ok"] for check in checks) else "FAIL"
    return {"status": gate_status, "summary": summary_out, "checks": checks}


def write_visual_text_extraction_quality(
    paths: VisualTextQualityPaths | None = None,
    *,
    min_records: int = 1,
    min_pages_with_visual_text: int = 1,
    max_error_records: int = 0,
    allow_planned: bool = True,
    allow_partial_status: bool = False,
    require_v2: bool = False,
    require_v2_2: bool = False,
    min_required_section_records: int = 0,
    max_summary_heavy_records: int | None = None,
    max_hallucination_risk_records: int | None = None,
    max_refusal_like_records: int | None = None,
    max_metadata_leakage_records: int | None = None,
) -> dict[str, Any]:
    paths = paths or VisualTextQualityPaths()
    report = build_visual_text_extraction_quality(
        paths,
        min_records=min_records,
        min_pages_with_visual_text=min_pages_with_visual_text,
        max_error_records=max_error_records,
        allow_planned=allow_planned,
        allow_partial_status=allow_partial_status,
        require_v2=require_v2,
        require_v2_2=require_v2_2,
        min_required_section_records=min_required_section_records,
        max_summary_heavy_records=max_summary_heavy_records,
        max_hallucination_risk_records=max_hallucination_risk_records,
        max_refusal_like_records=max_refusal_like_records,
        max_metadata_leakage_records=max_metadata_leakage_records,
    )
    _write_json(paths.quality_path, report)
    return report


def format_visual_text_extraction_quality(report: Mapping[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "Visual text extraction quality gate",
        f"  Status: {report.get('status')}",
        "  Summary:",
    ]
    for key, value in summary.items():
        lines.append(f"    {key}: {value}")
    lines.append("  Checks:")
    for check_any in _as_list(report.get("checks")):
        check = _as_dict(check_any)
        prefix = "OK" if check.get("ok") else "FAIL"
        lines.append(f"    {prefix} {check.get('name')}: {check.get('message')}")
    return "\n".join(lines)


# Backwards-friendly aliases for shorter imports.
build_visual_text_quality = build_visual_text_extraction_quality
write_visual_text_quality = write_visual_text_extraction_quality
format_visual_text_quality = format_visual_text_extraction_quality


__all__ = [
    "VisualTextQualityPaths",
    "build_visual_text_extraction_quality",
    "write_visual_text_extraction_quality",
    "format_visual_text_extraction_quality",
    "build_visual_text_quality",
    "write_visual_text_quality",
    "format_visual_text_quality",
]
