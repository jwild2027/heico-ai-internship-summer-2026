"""API + storage-adapter readiness quality checks.

This module is intentionally read-only. It validates the API readiness report and
storage-adapter readiness report that are produced by the existing scripts:

    scripts/maintenance/serving/check_tiff_api_ready.py --write-json
    scripts/maintenance/ingestion/check_tiff_storage_adapters.py --write-json

The readiness reports have evolved over time. Some versions store probe results
as machine-readable dictionaries, while others store human-readable strings such
as "120-37313-001 | ok | pages=28". This checker accepts both shapes so the
quality gate remains stable while the API boundary is still being refined.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
import json
import re

DEFAULT_API_READY_JSON = Path("local_data/api/tiff_api_ready.json")
DEFAULT_STORAGE_READY_JSON = Path("local_data/api/storage_adapter_ready.json")
DEFAULT_API_ADAPTER_QUALITY_JSON = Path("local_data/api/api_adapter_quality.json")


@dataclass
class QualityCheck:
    name: str
    status: str
    message: str

    @property
    def ok(self) -> bool:
        return self.status.lower() == "ok"


@dataclass
class ApiAdapterQualityReport:
    status: str
    summary: dict[str, Any]
    checks: list[QualityCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "checks": [asdict(check) for check in self.checks],
            "warnings": list(self.warnings),
        }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else {"value": data}


def _norm_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _norm_status(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if text in {"ok", "pass", "passed", "true", "yes", "ready", "success", "succeeded"}:
        return "ok"
    if text in {"warn", "warning", "needs_attention"}:
        return "needs_attention"
    if text in {"fail", "failed", "false", "no", "error", "errored"}:
        return "fail"
    return text


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "yes", "ok", "pass", "passed", "ready", "success", "1"}


def _iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _find_value(data: dict[str, Any] | None, *names: str) -> Any:
    if data is None:
        return None
    wanted = {_norm_key(name) for name in names}
    for dct in _iter_dicts(data):
        for key, value in dct.items():
            if _norm_key(str(key)) in wanted:
                return value
    return None


def _direct_value(data: dict[str, Any] | None, *names: str) -> Any:
    if data is None:
        return None
    wanted = {_norm_key(name) for name in names}
    for key, value in data.items():
        if _norm_key(str(key)) in wanted:
            return value
    return None


def _find_int(data: dict[str, Any] | None, *names: str) -> int | None:
    value = _find_value(data, *names)
    return _int_value(value)


def _int_value(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _find_status(data: dict[str, Any] | None, *names: str) -> str | None:
    value = _find_value(data, *names)
    return _norm_status(value)


def _probe_value(data: dict[str, Any] | None, *names: str) -> Any:
    """Return a named probe from a readiness report.

    Probes are normally top-level fields. Prefer direct lookup so generic fields
    like ``found`` or ``source`` inside an unrelated nested dict do not get mixed
    into the wrong probe.
    """
    return _direct_value(data, *names)


def _probe_text_has_ok(text: str) -> bool:
    lower = text.lower()
    return bool(
        re.search(r"(?:^|[|,;\s])ok(?:$|[|,;\s])", lower)
        or re.search(r"(?:status|probe)\s*[:=]\s*ok", lower)
        or re.search(r"(?:found|source|context|ready|success)\s*=\s*true", lower)
        or " status: ok" in lower
    )


def _probe_ok_from_value(value: Any) -> bool:
    if isinstance(value, dict):
        for key in ("ok", "found", "success", "ready", "source", "source_present", "source_link_present", "context", "context_present"):
            if key in value and _truthy(value.get(key)):
                return True
        status = _norm_status(value.get("status"))
        return status == "ok"
    if isinstance(value, str):
        return _probe_text_has_ok(value)
    return _truthy(value)


def _probe_source_from_value(value: Any) -> bool:
    if isinstance(value, dict):
        for key in ("source", "source_present", "source_link", "source_link_present", "has_source", "has_source_link"):
            if key in value and _truthy(value.get(key)):
                return True
        return _probe_ok_from_value(value)
    if isinstance(value, str):
        lower = value.lower()
        return "source=true" in lower or "source: true" in lower or "source_link=true" in lower or _probe_text_has_ok(value)
    return _truthy(value)


def _probe_pages_from_value(value: Any) -> int | None:
    if isinstance(value, dict):
        for key in ("pages", "page_count", "total_pages", "pages_found", "count"):
            result = _int_value(value.get(key))
            if result is not None:
                return result
        return None
    if isinstance(value, str):
        for pattern in (r"pages\s*[=:]\s*(\d+)", r"page_count\s*[=:]\s*(\d+)", r"pages_found\s*[=:]\s*(\d+)"):
            match = re.search(pattern, value, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))
    return _int_value(value)


def _api_summary(api_data: dict[str, Any] | None) -> dict[str, Any]:
    part_probe = _probe_value(api_data, "part_probe", "Part probe")
    page_probe = _probe_value(api_data, "page_probe", "Page probe")
    vector_probe = _probe_value(api_data, "vector_trace_probe", "vector_probe", "Vector trace probe")

    return {
        "api_ready_present": api_data is not None,
        "api_ready_status": _find_status(api_data, "status", "Status"),
        "api_backend_quality": _find_status(api_data, "backend_quality", "backend_quality_status", "quality_status", "Backend quality"),
        "api_graph_nodes": _find_int(api_data, "graph_nodes", "nodes_total", "Graph nodes"),
        "api_page_contexts": _find_int(api_data, "page_contexts", "page_context_nodes", "Page contexts"),
        "api_source_links": _find_int(api_data, "source_links", "source_link_nodes", "Source links"),
        "api_part_probe_ok": _probe_ok_from_value(part_probe) or _truthy(_find_value(api_data, "part_probe_ok", "part_probe_found")),
        "api_part_probe_pages": _probe_pages_from_value(part_probe) or _find_int(api_data, "part_probe_pages", "part_pages"),
        "api_page_probe_ok": _probe_ok_from_value(page_probe) or _truthy(_find_value(api_data, "page_probe_ok", "page_probe_found")),
        "api_vector_trace_probe_ok": _probe_ok_from_value(vector_probe) or _truthy(_find_value(api_data, "vector_trace_probe_ok", "vector_trace_ok")),
    }


def _storage_summary(storage_data: dict[str, Any] | None) -> dict[str, Any]:
    part_probe = _probe_value(storage_data, "part_probe", "Part probe")
    page_probe = _probe_value(storage_data, "page_probe", "Page probe")

    return {
        "storage_adapter_ready_present": storage_data is not None,
        "storage_adapter_status": _find_status(storage_data, "status", "Status"),
        "storage_adapter_mode": _find_value(storage_data, "mode", "Mode"),
        "storage_adapter_org_summary_present": _truthy(_find_value(storage_data, "organization_summary_present", "org_summary_present", "Organization summary present")),
        "storage_adapter_quality_status": _find_status(storage_data, "quality_status", "quality", "backend_quality", "Quality status"),
        "storage_adapter_part_probe_found": _probe_ok_from_value(part_probe) or _truthy(_find_value(storage_data, "part_probe_found", "part_found")),
        "storage_adapter_part_probe_pages": _probe_pages_from_value(part_probe) or _find_int(storage_data, "part_probe_pages", "part_pages"),
        "storage_adapter_page_probe_found": _probe_ok_from_value(page_probe) or _truthy(_find_value(storage_data, "page_probe_found", "page_found")),
        "storage_adapter_page_probe_source": _probe_source_from_value(page_probe) or _truthy(_find_value(storage_data, "page_probe_source", "page_probe_source_present", "page_source", "source_present", "source_link_present")),
    }


def build_api_adapter_quality_report(
    api_ready_json: Path = DEFAULT_API_READY_JSON,
    storage_ready_json: Path = DEFAULT_STORAGE_READY_JSON,
) -> ApiAdapterQualityReport:
    api_data = _read_json(api_ready_json)
    storage_data = _read_json(storage_ready_json)
    summary: dict[str, Any] = {}
    summary.update(_api_summary(api_data))
    summary.update(_storage_summary(storage_data))

    checks: list[QualityCheck] = []

    def add(name: str, ok: bool, message: str) -> None:
        checks.append(QualityCheck(name=name, status="OK" if ok else "FAIL", message=message))

    add(
        "api_ready_report_present",
        bool(summary["api_ready_present"]),
        f"API readiness report present at {api_ready_json}.",
    )
    add(
        "api_ready_status",
        summary["api_ready_status"] == "ok",
        f"API readiness status is {summary['api_ready_status']!r}.",
    )
    add(
        "api_backend_quality",
        summary["api_backend_quality"] in {"ok", None},
        f"API backend quality status is {summary['api_backend_quality']!r}.",
    )
    add(
        "api_graph_counts",
        (summary["api_graph_nodes"] or 0) >= 1
        and (summary["api_page_contexts"] or 0) >= 1
        and (summary["api_source_links"] or 0) >= 1,
        "API readiness has nonzero graph/page-context/source-link counts.",
    )
    add(
        "api_part_probe",
        bool(summary["api_part_probe_ok"]),
        f"API part probe ok={summary['api_part_probe_ok']} pages={summary['api_part_probe_pages']}.",
    )
    add(
        "api_page_probe",
        bool(summary["api_page_probe_ok"]),
        f"API page probe ok={summary['api_page_probe_ok']}.",
    )
    add(
        "api_vector_trace_probe",
        bool(summary["api_vector_trace_probe_ok"]),
        f"API vector trace probe ok={summary['api_vector_trace_probe_ok']}.",
    )

    add(
        "storage_adapter_ready_report_present",
        bool(summary["storage_adapter_ready_present"]),
        f"Storage-adapter readiness report present at {storage_ready_json}.",
    )
    add(
        "storage_adapter_status",
        summary["storage_adapter_status"] == "ok",
        f"Storage-adapter readiness status is {summary['storage_adapter_status']!r}.",
    )
    add(
        "storage_adapter_org_summary",
        bool(summary["storage_adapter_org_summary_present"]),
        "Storage adapter can read organization summary.",
    )
    add(
        "storage_adapter_part_probe",
        bool(summary["storage_adapter_part_probe_found"]),
        f"Storage adapter part probe found={summary['storage_adapter_part_probe_found']} pages={summary['storage_adapter_part_probe_pages']}.",
    )
    add(
        "storage_adapter_page_probe",
        bool(summary["storage_adapter_page_probe_found"]) and bool(summary["storage_adapter_page_probe_source"]),
        f"Storage adapter page probe found={summary['storage_adapter_page_probe_found']} source={summary['storage_adapter_page_probe_source']}.",
    )
    add(
        "storage_adapter_quality_status",
        summary["storage_adapter_quality_status"] in {"ok", None},
        f"Storage adapter quality status is {summary['storage_adapter_quality_status']!r}.",
    )

    status = "OK" if all(check.ok for check in checks) else "FAIL"
    warnings: list[str] = []
    if summary["api_ready_present"] and summary["api_ready_status"] != "ok":
        warnings.append("API readiness report is present but not OK.")
    if summary["storage_adapter_ready_present"] and summary["storage_adapter_status"] != "ok":
        warnings.append("Storage-adapter readiness report is present but not OK.")

    return ApiAdapterQualityReport(status=status, summary=summary, checks=checks, warnings=warnings)


def write_api_adapter_quality_report(
    report: ApiAdapterQualityReport,
    output_path: Path = DEFAULT_API_ADAPTER_QUALITY_JSON,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return output_path
