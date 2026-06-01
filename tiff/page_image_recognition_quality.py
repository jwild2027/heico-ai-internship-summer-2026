from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_AUDIT_PATH = Path("local_data/organization/image_recognition/page_image_recognition_audit.json")
DEFAULT_QUALITY_PATH = Path("local_data/organization/image_recognition/page_image_recognition_quality.json")
DEFAULT_GRAPH_NODES_PATH = Path("local_data/organization/image_recognition/image_recognition_graph_nodes.json")
DEFAULT_GRAPH_EDGES_PATH = Path("local_data/organization/image_recognition/image_recognition_graph_edges.json")


@dataclass
class QualityCheck:
    name: str
    status: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "message": self.message}


@dataclass
class QualityReport:
    status: str
    summary: dict[str, Any]
    checks: list[QualityCheck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "checks": [check.to_dict() for check in self.checks],
        }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"ok", "pass", "passed", "true"}:
        return "ok"
    if text in {"fail", "failed", "error", "needs attention", "needs_attention"}:
        return text
    return text


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = 0) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        text = str(value).replace(",", "").strip()
        if not text:
            return default
        return int(float(text))
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).replace(",", "").strip()
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_json_items(path: Path | str | None) -> tuple[bool, int, str | None]:
    if not path:
        return False, 0, None

    p = Path(path)
    if not p.exists():
        return False, 0, str(p)

    try:
        data = _load_json(p)
    except Exception:
        return False, 0, str(p)

    if isinstance(data, list):
        return True, len(data), str(p)

    if isinstance(data, dict):
        for key in ("nodes", "edges", "items", "records"):
            if isinstance(data.get(key), list):
                return True, len(data[key]), str(p)
        return True, len(data), str(p)

    return True, 0, str(p)


def _top_summary(audit: Mapping[str, Any]) -> dict[str, Any]:
    return _as_dict(audit.get("summary"))


def _top_counts(audit: Mapping[str, Any]) -> dict[str, Any]:
    """Return the counter block from all supported audit JSON shapes.

    Supported shapes:
      1. Older/normalized tests: {"counts": {...}}
      2. Nested summary: {"summary": {"counts": {...}}}
      3. Current generated audit: {"summary": {"pages_checked": ..., ...}}
    """

    counts = _as_dict(audit.get("counts"))
    summary = _top_summary(audit)

    if not counts:
        counts = _as_dict(summary.get("counts"))

    if not counts:
        counts = summary

    return counts


def _top_signals(audit: Mapping[str, Any]) -> dict[str, Any]:
    """Return the visual/ink signal block from all supported audit shapes."""

    summary = _top_summary(audit)

    signals = _as_dict(audit.get("image_recognition_signals"))
    if not signals:
        signals = _as_dict(audit.get("signals"))
    if not signals:
        signals = _as_dict(summary.get("image_recognition_signals"))
    if not signals:
        signals = _as_dict(summary.get("signals"))

    # Current generated audits keep likely_* and ink metrics directly under
    # summary instead of under image_recognition_signals.
    if not signals:
        signals = summary

    return signals


def _top_classes(audit: Mapping[str, Any]) -> dict[str, Any]:
    summary = _top_summary(audit)

    classes = _as_dict(audit.get("classification_counts"))
    if not classes:
        classes = _as_dict(audit.get("by_classification"))
    if not classes:
        classes = _as_dict(summary.get("classification_counts"))
    if not classes:
        classes = _as_dict(summary.get("by_classification"))

    return classes


def _top_roles(audit: Mapping[str, Any]) -> dict[str, Any]:
    summary = _top_summary(audit)

    roles = _as_dict(audit.get("page_roles"))
    if not roles:
        roles = _as_dict(audit.get("role_counts"))
    if not roles:
        roles = _as_dict(summary.get("page_roles"))
    if not roles:
        roles = _as_dict(summary.get("role_counts"))

    return roles


def _rows(audit: Mapping[str, Any]) -> list[Any]:
    for key in ("rows", "records", "pages", "sample_rows"):
        value = audit.get(key)
        if isinstance(value, list):
            return value

    # Some tools write a nested detail block. Only use it if it is clearly a
    # list of page records.
    detail = _as_dict(audit.get("detail"))
    for key in ("rows", "records", "pages"):
        value = detail.get(key)
        if isinstance(value, list):
            return value

    return []


def _derive_from_rows(audit: Mapping[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    class_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}

    for row in _rows(audit):
        if not isinstance(row, dict):
            continue

        cls = row.get("classification") or row.get("class") or row.get("image_class")
        role = row.get("role") or row.get("page_role")

        if cls:
            class_counts[str(cls)] = class_counts.get(str(cls), 0) + 1
        if role:
            role_counts[str(role)] = role_counts.get(str(role), 0) + 1

    return class_counts, role_counts


def _overlay_paths_from_audit(audit: Mapping[str, Any]) -> tuple[Any, Any]:
    summary = _top_summary(audit)

    overlay = _as_dict(audit.get("graph_overlay"))
    nodes = _first(
        overlay,
        "nodes",
        "nodes_path",
        "graph_nodes",
        "graph_nodes_path",
        default=None,
    )
    edges = _first(
        overlay,
        "edges",
        "edges_path",
        "graph_edges",
        "graph_edges_path",
        default=None,
    )

    if not nodes or not edges:
        files = _as_dict(audit.get("graph_overlay_files"))
        nodes = nodes or _first(files, "nodes", "nodes_path", default=None)
        edges = edges or _first(files, "edges", "edges_path", default=None)

    # Current generated audit summary fields.
    nodes = nodes or _first(
        summary,
        "overlay_nodes_path",
        "graph_overlay_nodes_path",
        "nodes_path",
        default=None,
    )
    edges = edges or _first(
        summary,
        "overlay_edges_path",
        "graph_overlay_edges_path",
        "edges_path",
        default=None,
    )

    return nodes, edges


def summarize_page_image_recognition_audit(
    audit: Mapping[str, Any],
    *,
    audit_path: Path | str | None = None,
    graph_nodes_path: Path | str | None = None,
    graph_edges_path: Path | str | None = None,
) -> dict[str, Any]:
    counts = _top_counts(audit)
    signals = _top_signals(audit)
    class_counts = _top_classes(audit)
    role_counts = _top_roles(audit)

    if not class_counts or not role_counts:
        derived_classes, derived_roles = _derive_from_rows(audit)
        if not class_counts:
            class_counts = derived_classes
        if not role_counts:
            role_counts = derived_roles

    overlay_nodes, overlay_edges = _overlay_paths_from_audit(audit)
    nodes_path = graph_nodes_path or overlay_nodes or DEFAULT_GRAPH_NODES_PATH
    edges_path = graph_edges_path or overlay_edges or DEFAULT_GRAPH_EDGES_PATH
    nodes_present, nodes_count, nodes_path_text = _count_json_items(nodes_path)
    edges_present, edges_count, edges_path_text = _count_json_items(edges_path)

    top_summary = _top_summary(audit)
    status = _norm_status(audit.get("status") or top_summary.get("status"))

    pages_checked = _to_int(_first(counts, "pages_checked", "pages", "page_count", "total_pages"))
    readable = _to_int(
        _first(
            counts,
            "readable_images",
            "images_readable",
            "readable_image_files",
            "images_readable_files",
            default=0,
        )
    )
    missing_paths = _to_int(_first(counts, "missing_image_paths", "missing_paths"))
    missing_files = _to_int(_first(counts, "missing_image_files", "missing_files"))
    unreadable = _to_int(_first(counts, "unreadable_images", "unreadable_image_files"))
    blank = _to_int(_first(counts, "blank_nearly_blank_pages", "blank_pages", "nearly_blank_pages"))

    likely_visual = _to_int(_first(signals, "likely_visual_pages", "visual_pages"))
    likely_figure = _to_int(
        _first(
            signals,
            "likely_figure_diagram_pages",
            "likely_figure_or_diagram_pages",
            "likely_figure_pages",
            "figure_pages",
        )
    )
    likely_table = _to_int(
        _first(
            signals,
            "likely_table_grid_pages",
            "likely_table_or_grid_pages",
            "likely_table_pages",
            "table_pages",
        )
    )
    likely_image_heavy = _to_int(_first(signals, "likely_image_heavy_pages", "image_heavy_pages"))
    likely_text = _to_int(
        _first(
            signals,
            "likely_text_heavy_pages",
            "likely_text_parts_list_pages",
            "likely_text_or_parts_list_pages",
            "likely_text_pages",
        )
    )
    avg_ink = _to_float(_first(signals, "avg_ink_ratio", "average_ink_ratio"))
    median_ink = _to_float(_first(signals, "median_ink_ratio"))
    large_components = _to_int(_first(signals, "total_large_components", "large_components"))

    class_counts_int = {str(k): _to_int(v) for k, v in class_counts.items()}
    role_counts_int = {str(k): _to_int(v) for k, v in role_counts.items()}
    classified_pages = sum(class_counts_int.values())
    role_pages = sum(role_counts_int.values())

    summary: dict[str, Any] = {
        "page_image_recognition_audit_present": True,
        "page_image_recognition_audit_path": str(audit_path or DEFAULT_AUDIT_PATH),
        "page_image_recognition_audit_status": status,
        "page_image_pages_checked": pages_checked,
        "page_image_readable_images": readable,
        "page_image_missing_image_paths": missing_paths,
        "page_image_missing_image_files": missing_files,
        "page_image_unreadable_images": unreadable,
        "page_image_blank_pages": blank,
        "page_image_likely_visual_pages": likely_visual,
        "page_image_likely_figure_pages": likely_figure,
        "page_image_likely_table_pages": likely_table,
        "page_image_likely_image_heavy_pages": likely_image_heavy,
        "page_image_likely_text_pages": likely_text,
        "page_image_avg_ink_ratio": round(avg_ink, 6),
        "page_image_median_ink_ratio": round(median_ink, 6),
        "page_image_total_large_components": large_components,
        "page_image_classified_pages": classified_pages,
        "page_image_role_pages": role_pages,
        "page_image_role_unknown": role_counts_int.get("unknown", 0),
        "page_image_graph_overlay_nodes_present": nodes_present,
        "page_image_graph_overlay_nodes": nodes_count,
        "page_image_graph_overlay_nodes_path": nodes_path_text or str(nodes_path),
        "page_image_graph_overlay_edges_present": edges_present,
        "page_image_graph_overlay_edges": edges_count,
        "page_image_graph_overlay_edges_path": edges_path_text or str(edges_path),
    }

    for key, value in class_counts_int.items():
        summary[f"page_image_class_{key}"] = value
    for key, value in role_counts_int.items():
        summary[f"page_image_role_{key}"] = value

    return summary


def _check(name: str, ok: bool, message: str) -> QualityCheck:
    return QualityCheck(name=name, status="OK" if ok else "FAIL", message=message)


def build_page_image_recognition_quality_report(
    audit_path: Path | str = DEFAULT_AUDIT_PATH,
    *,
    graph_nodes_path: Path | str | None = None,
    graph_edges_path: Path | str | None = None,
    max_blank_pages: int = 20,
) -> QualityReport:
    path = Path(audit_path)
    if not path.exists():
        summary = {
            "page_image_recognition_audit_present": False,
            "page_image_recognition_audit_path": str(path),
        }
        checks = [
            _check(
                "page_image_audit_present",
                False,
                f"Page image-recognition audit JSON is missing at {path}.",
            )
        ]
        return QualityReport(status="FAIL", summary=summary, checks=checks)

    audit = _load_json(path)
    if not isinstance(audit, dict):
        summary = {
            "page_image_recognition_audit_present": True,
            "page_image_recognition_audit_path": str(path),
            "page_image_recognition_audit_status": "invalid",
        }
        checks = [
            _check("page_image_audit_status", False, "Page image-recognition audit JSON is not an object.")
        ]
        return QualityReport(status="FAIL", summary=summary, checks=checks)

    summary = summarize_page_image_recognition_audit(
        audit,
        audit_path=path,
        graph_nodes_path=graph_nodes_path,
        graph_edges_path=graph_edges_path,
    )

    pages = _to_int(summary.get("page_image_pages_checked"))
    readable = _to_int(summary.get("page_image_readable_images"))
    missing_paths = _to_int(summary.get("page_image_missing_image_paths"))
    missing_files = _to_int(summary.get("page_image_missing_image_files"))
    unreadable = _to_int(summary.get("page_image_unreadable_images"))
    blank = _to_int(summary.get("page_image_blank_pages"))
    classified = _to_int(summary.get("page_image_classified_pages"))
    role_pages = _to_int(summary.get("page_image_role_pages"))
    unknown_roles = _to_int(summary.get("page_image_role_unknown"))
    likely_visual = _to_int(summary.get("page_image_likely_visual_pages"))
    likely_figure = _to_int(summary.get("page_image_likely_figure_pages"))
    likely_table = _to_int(summary.get("page_image_likely_table_pages"))
    table_class = _to_int(summary.get("page_image_class_likely_table_or_grid"))
    avg_ink = _to_float(summary.get("page_image_avg_ink_ratio"))
    large_components = _to_int(summary.get("page_image_total_large_components"))
    overlay_nodes_present = bool(summary.get("page_image_graph_overlay_nodes_present"))
    overlay_edges_present = bool(summary.get("page_image_graph_overlay_edges_present"))
    overlay_nodes = _to_int(summary.get("page_image_graph_overlay_nodes"))
    overlay_edges = _to_int(summary.get("page_image_graph_overlay_edges"))

    checks = [
        _check("page_image_audit_present", True, f"Page image-recognition audit JSON is present at {path}."),
        _check(
            "page_image_audit_status",
            summary.get("page_image_recognition_audit_status") == "ok",
            f"Page image-recognition audit status is {summary.get('page_image_recognition_audit_status')} .",
        ),
        _check("page_image_pages_checked", pages >= 1, f"Pages checked={pages}; minimum is 1."),
        _check("page_image_readable_coverage", readable == pages, f"Readable images={readable}/{pages}."),
        _check("page_image_missing_paths", missing_paths == 0, f"Missing image paths={missing_paths}; max allowed=0."),
        _check("page_image_missing_files", missing_files == 0, f"Missing image files={missing_files}; max allowed=0."),
        _check("page_image_unreadable", unreadable == 0, f"Unreadable images={unreadable}; max allowed=0."),
        _check(
            "page_image_blank_count",
            blank <= max_blank_pages,
            f"Blank/nearly blank pages={blank}; max allowed={max_blank_pages}.",
        ),
        _check(
            "page_image_classification_counts",
            classified == pages,
            f"Classified pages={classified}; pages checked={pages}.",
        ),
        _check(
            "page_image_role_counts",
            role_pages == pages and unknown_roles == 0,
            f"Role pages={role_pages}; unknown roles={unknown_roles}; pages checked={pages}.",
        ),
        _check(
            "page_image_visual_signals",
            likely_visual > 0 and likely_figure > 0,
            f"Likely visual pages={likely_visual}; likely figure/diagram pages={likely_figure}.",
        ),
        _check(
            "page_image_table_signals",
            likely_table > 0 and table_class > 0,
            f"Likely table/grid pages={likely_table}; table/grid classifications={table_class}.",
        ),
        _check(
            "page_image_ink_signal",
            avg_ink > 0 and large_components > 0,
            f"Average ink ratio={avg_ink:.4f}; large components={large_components}.",
        ),
        _check(
            "page_image_graph_overlay_nodes",
            overlay_nodes_present and overlay_nodes > 0,
            f"Graph overlay nodes present={overlay_nodes_present} count={overlay_nodes}.",
        ),
        _check(
            "page_image_graph_overlay_edges",
            overlay_edges_present and overlay_edges > 0,
            f"Graph overlay edges present={overlay_edges_present} count={overlay_edges}.",
        ),
    ]

    status = "OK" if all(check.status == "OK" for check in checks) else "FAIL"
    return QualityReport(status=status, summary=summary, checks=checks)


def build_page_image_recognition_quality(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return build_page_image_recognition_quality_report(*args, **kwargs).to_dict()


def page_image_recognition_quality(*args: Any, **kwargs: Any) -> QualityReport:
    return build_page_image_recognition_quality_report(*args, **kwargs)


def _print_report(report: QualityReport) -> None:
    print("Page image-recognition quality gate")
    print(f"  Status: {report.status}")
    print("  Summary:")
    for key in sorted(report.summary):
        print(f"    {key}: {report.summary[key]}")
    print("  Checks:")
    for check in report.checks:
        print(f"    {check.status} {check.name}: {check.message}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TIFF page image-recognition audit quality.")
    parser.add_argument("--audit-json", default=str(DEFAULT_AUDIT_PATH))
    parser.add_argument("--json-output", default=str(DEFAULT_QUALITY_PATH))
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--max-blank-pages", type=int, default=20)
    args = parser.parse_args(argv)

    report = build_page_image_recognition_quality_report(
        audit_path=Path(args.audit_json),
        max_blank_pages=args.max_blank_pages,
    )
    _print_report(report)

    if args.write_json:
        out = Path(args.json_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        print(f"\nJSON: {out}")

    return 0 if report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
