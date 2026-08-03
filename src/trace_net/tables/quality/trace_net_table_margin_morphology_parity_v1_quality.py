"""Quality entrypoint for TRACE-Net Table Margin Morphology Parity v1."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from tiff.trace_net_table_margin_morphology_parity_v1 import Thresholds, apply_quality, load_json, write_json, utc_now_iso


def check_quality(report_path: Path, thresholds: Thresholds, write_quality: bool = False) -> Dict[str, Any]:
    report = load_json(report_path)
    summary = dict(report.get("summary") or {})
    summary = apply_quality(summary, thresholds)
    quality = {
        "schema_version": "trace_net_table_margin_morphology_parity_v1_quality",
        "generated_at": utc_now_iso(),
        "quality_status": summary["quality_status"],
        "status": summary["quality_status"],
        "summary": summary,
        "checks": summary.get("checks", {}),
    }
    if write_quality:
        write_json(report_path.with_name("trace_net_table_margin_morphology_parity_v1_quality.json"), quality)
    return quality
