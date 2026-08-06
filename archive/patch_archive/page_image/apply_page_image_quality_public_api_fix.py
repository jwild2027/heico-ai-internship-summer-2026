from __future__ import annotations

from pathlib import Path

MODULE = Path('tiff/page_image_recognition_quality.py')
CHECK_SCRIPT = Path('scripts/maintenance/ingestion/check_page_image_recognition_quality.py')

MODULE_CODE = r'''from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

DEFAULT_AUDIT_PATH = Path("local_data/organization/image_recognition/page_image_recognition_audit.json")
DEFAULT_QUALITY_PATH = Path("local_data/organization/image_recognition/page_image_recognition_quality.json")


@dataclass
class QualityCheck:
    name: str
    status: str
    message: str

    @property
    def ok(self) -> bool:
        return self.status.upper() in {"OK", "INFO"}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PageImageRecognitionQualityReport:
    status: str
    summary: Dict[str, Any]
    checks: List[QualityCheck]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.lower(),
            "summary": self.summary,
            "checks": [check.to_dict() for check in self.checks],
        }

    def write_json(self, path: Path = DEFAULT_QUALITY_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _section(data: Mapping[str, Any], *names: str) -> Mapping[str, Any]:
    for name in names:
        value = data.get(name)
        if isinstance(value, Mapping):
            return value
    return data


def _get_any(data: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _count_json_items(path_value: Any) -> int:
    if not path_value:
        return 0
    path = Path(str(path_value))
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, Mapping):
        for key in ("nodes", "edges", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
        return len(data)
    return 0


def summarize_page_image_recognition_audit(audit: Mapping[str, Any] | Path | str) -> Dict[str, Any]:
    if isinstance(audit, (str, Path)):
        audit_data: Mapping[str, Any] = _load_json(Path(audit))
    else:
        audit_data = audit

    counts = _section(audit_data, "counts", "summary")
    signals = _section(audit_data, "image_recognition_signals", "visual_signals", "signals")
    classes = _section(audit_data, "classification_counts", "by_classification", "classes")
    roles = _section(audit_data, "page_roles", "role_counts", "roles")
    overlay = _section(audit_data, "graph_overlay", "graph_overlay_files", "graph")

    pages_checked = _as_int(_get_any(counts, "pages_checked", "total_pages", "pages"))
    missing_paths = _as_int(_get_any(counts, "missing_image_paths", "missing_paths"))
    missing_files = _as_int(_get_any(counts, "missing_image_files", "missing_files"))
    unreadable = _as_int(_get_any(counts, "unreadable_images", "unreadable_image_files"))
    readable = _as_int(_get_any(counts, "readable_images", "readable_image_files", "readable_files"))
    if readable <= 0 and pages_checked > 0:
        readable = max(0, pages_checked - missing_paths - missing_files - unreadable)

    blank_pages = _as_int(_get_any(counts, "blank_nearly_blank_pages", "blank_pages", "nearly_blank_pages"))
    if blank_pages <= 0:
        blank_pages = _as_int(_get_any(classes, "likely_blank"))

    likely_visual = _as_int(_get_any(signals, "likely_visual_pages", "visual_pages"))
    likely_table = _as_int(_get_any(signals, "likely_table_grid_pages", "likely_table_pages", "table_grid_pages"))
    if likely_table <= 0:
        likely_table = _as_int(_get_any(classes, "likely_table_or_grid"))

    likely_figure = _as_int(_get_any(signals, "likely_figure_diagram_pages", "likely_figure_pages", "likely_figure_or_diagram_pages"))
    if likely_figure <= 0:
        class_figure = _as_int(_get_any(classes, "likely_figure_or_diagram"))
        class_table = _as_int(_get_any(classes, "likely_table_or_grid"))
        # In this audit, table/grid pages are also visual/diagram-like pages.
        likely_figure = class_figure + class_table
    if likely_visual <= 0:
        likely_visual = max(likely_figure, likely_table, _as_int(_get_any(classes, "likely_figure_or_diagram")) + _as_int(_get_any(classes, "likely_table_or_grid")))

    likely_image_heavy = _as_int(_get_any(signals, "likely_image_heavy_pages", "image_heavy_pages"))
    likely_text = _as_int(_get_any(signals, "likely_text_parts_list_pages", "likely_text_pages", "text_parts_list_pages"))
    if likely_text <= 0:
        likely_text = _as_int(_get_any(classes, "likely_text_or_parts_list"))

    class_blank = _as_int(_get_any(classes, "likely_blank"))
    class_figure = _as_int(_get_any(classes, "likely_figure_or_diagram"))
    class_table = _as_int(_get_any(classes, "likely_table_or_grid"))
    class_text = _as_int(_get_any(classes, "likely_text_or_parts_list"))
    classified = class_blank + class_figure + class_table + class_text
    if classified <= 0:
        classified = _as_int(_get_any(counts, "classified_pages"))

    role_counts = {str(k): _as_int(v) for k, v in roles.items() if isinstance(v, (int, float, str))}
    role_pages = sum(role_counts.values())
    role_unknown = role_counts.get("unknown", 0)

    nodes_path = _get_any(overlay, "nodes_path", "graph_overlay_nodes_path", "image_recognition_graph_nodes_path")
    edges_path = _get_any(overlay, "edges_path", "graph_overlay_edges_path", "image_recognition_graph_edges_path")
    nodes_present = bool(nodes_path and Path(str(nodes_path)).exists())
    edges_present = bool(edges_path and Path(str(edges_path)).exists())
    nodes_count = _as_int(_get_any(overlay, "nodes", "node_count", "graph_overlay_nodes")) or _count_json_items(nodes_path)
    edges_count = _as_int(_get_any(overlay, "edges", "edge_count", "graph_overlay_edges")) or _count_json_items(edges_path)

    summary: Dict[str, Any] = {
        "page_image_recognition_audit_present": bool(audit_data),
        "page_image_recognition_audit_status": str(_get_any(audit_data, "status", default="missing")).lower(),
        "page_image_pages_checked": pages_checked,
        "page_image_readable_images": readable,
        "page_image_missing_image_paths": missing_paths,
        "page_image_missing_image_files": missing_files,
        "page_image_unreadable_images": unreadable,
        "page_image_blank_pages": blank_pages,
        "page_image_likely_visual_pages": likely_visual,
        "page_image_likely_figure_pages": likely_figure,
        "page_image_likely_table_pages": likely_table,
        "page_image_likely_image_heavy_pages": likely_image_heavy,
        "page_image_likely_text_pages": likely_text,
        "page_image_avg_ink_ratio": round(_as_float(_get_any(signals, "avg_ink_ratio", "average_ink_ratio")), 6),
        "page_image_median_ink_ratio": round(_as_float(_get_any(signals, "median_ink_ratio")), 6),
        "page_image_total_large_components": _as_int(_get_any(signals, "total_large_components", "large_components")),
        "page_image_classified_pages": classified,
        "page_image_class_likely_blank": class_blank,
        "page_image_class_likely_figure_or_diagram": class_figure,
        "page_image_class_likely_table_or_grid": class_table,
        "page_image_class_likely_text_or_parts_list": class_text,
        "page_image_role_pages": role_pages,
        "page_image_role_unknown": role_unknown,
        "page_image_graph_overlay_nodes_present": nodes_present,
        "page_image_graph_overlay_edges_present": edges_present,
        "page_image_graph_overlay_nodes": nodes_count,
        "page_image_graph_overlay_edges": edges_count,
        "page_image_graph_overlay_nodes_path": str(nodes_path or ""),
        "page_image_graph_overlay_edges_path": str(edges_path or ""),
    }
    for role, count in role_counts.items():
        summary[f"page_image_role_{role}"] = count
    return summary


def _check(name: str, ok: bool, message: str) -> QualityCheck:
    return QualityCheck(name=name, status="OK" if ok else "FAIL", message=message)


def build_page_image_recognition_quality_report(
    audit_path: Path | str = DEFAULT_AUDIT_PATH,
    *,
    max_missing_image_paths: int = 0,
    max_missing_image_files: int = 0,
    max_unreadable_images: int = 0,
    max_blank_pages: int = 20,
    min_pages: int = 1,
) -> PageImageRecognitionQualityReport:
    audit_path = Path(audit_path)
    audit = _load_json(audit_path)
    summary = summarize_page_image_recognition_audit(audit)
    summary["page_image_recognition_audit_path"] = str(audit_path)

    pages = _as_int(summary.get("page_image_pages_checked"))
    readable = _as_int(summary.get("page_image_readable_images"))
    missing_paths = _as_int(summary.get("page_image_missing_image_paths"))
    missing_files = _as_int(summary.get("page_image_missing_image_files"))
    unreadable = _as_int(summary.get("page_image_unreadable_images"))
    blank = _as_int(summary.get("page_image_blank_pages"))
    classified = _as_int(summary.get("page_image_classified_pages"))
    role_pages = _as_int(summary.get("page_image_role_pages"))
    role_unknown = _as_int(summary.get("page_image_role_unknown"))
    likely_visual = _as_int(summary.get("page_image_likely_visual_pages"))
    likely_figure = _as_int(summary.get("page_image_likely_figure_pages"))
    likely_table = _as_int(summary.get("page_image_likely_table_pages"))
    avg_ink = _as_float(summary.get("page_image_avg_ink_ratio"))
    large_components = _as_int(summary.get("page_image_total_large_components"))
    nodes_present = bool(summary.get("page_image_graph_overlay_nodes_present"))
    edges_present = bool(summary.get("page_image_graph_overlay_edges_present"))
    nodes = _as_int(summary.get("page_image_graph_overlay_nodes"))
    edges = _as_int(summary.get("page_image_graph_overlay_edges"))

    checks = [
        _check("page_image_audit_present", bool(audit), f"Page image-recognition audit JSON is present at {audit_path}."),
        _check("page_image_audit_status", summary.get("page_image_recognition_audit_status") == "ok", f"Page image-recognition audit status is {summary.get('page_image_recognition_audit_status')}.") ,
        _check("page_image_pages_checked", pages >= min_pages, f"Pages checked={pages}; minimum is {min_pages}."),
        _check("page_image_readable_coverage", readable == pages and pages > 0, f"Readable images={readable}/{pages}."),
        _check("page_image_missing_paths", missing_paths <= max_missing_image_paths, f"Missing image paths={missing_paths}; max allowed={max_missing_image_paths}."),
        _check("page_image_missing_files", missing_files <= max_missing_image_files, f"Missing image files={missing_files}; max allowed={max_missing_image_files}."),
        _check("page_image_unreadable", unreadable <= max_unreadable_images, f"Unreadable images={unreadable}; max allowed={max_unreadable_images}."),
        _check("page_image_blank_count", blank <= max_blank_pages, f"Blank/nearly blank pages={blank}; max allowed={max_blank_pages}."),
        _check("page_image_classification_counts", classified == pages and pages > 0, f"Classified pages={classified}; pages checked={pages}."),
        _check("page_image_role_counts", role_pages == pages and role_unknown == 0, f"Role pages={role_pages}; unknown roles={role_unknown}; pages checked={pages}."),
        _check("page_image_visual_signals", likely_visual > 0 and likely_figure > 0, f"Likely visual pages={likely_visual}; likely figure/diagram pages={likely_figure}."),
        _check("page_image_table_signals", likely_table > 0, f"Likely table/grid pages={likely_table}.") ,
        _check("page_image_ink_signal", avg_ink > 0 and large_components > 0, f"Average ink ratio={avg_ink:.4f}; large components={large_components}."),
        _check("page_image_graph_overlay_nodes", nodes_present and nodes > 0, f"Graph overlay nodes present={nodes_present} count={nodes}."),
        _check("page_image_graph_overlay_edges", edges_present and edges > 0, f"Graph overlay edges present={edges_present} count={edges}."),
    ]
    status = "OK" if all(check.ok for check in checks) else "FAIL"
    return PageImageRecognitionQualityReport(status=status, summary=summary, checks=checks)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TIFF page image-recognition quality.")
    parser.add_argument("--audit-json", default=str(DEFAULT_AUDIT_PATH))
    parser.add_argument("--json-output", default=str(DEFAULT_QUALITY_PATH))
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--max-blank-pages", type=int, default=20)
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_page_image_recognition_quality_report(args.audit_json, max_blank_pages=args.max_blank_pages)
    print("Page image-recognition quality gate")
    print(f"  Status: {report.status}")
    print("  Summary:")
    for key in sorted(report.summary):
        print(f"    {key}: {report.summary[key]}")
    print("  Checks:")
    for check in report.checks:
        print(f"    {check.status} {check.name}: {check.message}")
    if args.write_json:
        path = report.write_json(Path(args.json_output))
        print(f"\nJSON: {path}")
    return 0 if report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''

CHECK_SCRIPT_CODE = r'''from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.page_image_recognition_quality import main

if __name__ == "__main__":
    raise SystemExit(main())
'''


def main() -> int:
    if not MODULE.parent.exists():
        raise SystemExit(f"Missing module directory: {MODULE.parent}")
    MODULE.write_text(MODULE_CODE, encoding="utf-8")
    CHECK_SCRIPT.write_text(CHECK_SCRIPT_CODE, encoding="utf-8")
    print(f"Replaced {MODULE} with compatibility-safe page image-recognition quality implementation.")
    print(f"Updated {CHECK_SCRIPT}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
