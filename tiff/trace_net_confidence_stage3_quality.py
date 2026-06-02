"""Quality gate for TRACE-Net Layer Confidence Stage 3 policy."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_confidence_stage3_policy import DEFAULT_CONFIDENCE_DIR, DEFAULT_POLICY, POLICY_VERSION

DEFAULT_QUALITY = DEFAULT_CONFIDENCE_DIR / "trace_lc_confidence_policy_quality.json"


@dataclass
class PolicyQualityCheck:
    name: str
    ok: bool
    message: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConfidencePolicyQualityOptions:
    min_layers: int = 6
    require_source_trace_policy: bool = True
    require_table_tile_text_policy: bool = True
    require_visual_text_conservative: bool = True
    require_routing_only_table_candidate: bool = True


@dataclass
class ConfidencePolicyQualityReport:
    status: str
    summary: dict[str, Any]
    checks: list[PolicyQualityCheck] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "checks": [check.to_json() for check in self.checks],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _add(checks: list[PolicyQualityCheck], name: str, ok: bool, message: str) -> None:
    checks.append(PolicyQualityCheck(name=name, ok=bool(ok), message=message))


# ---------------------------------------------------------------------------
# Quality implementation
# ---------------------------------------------------------------------------


def build_confidence_policy_quality(
    policy_path: Path = DEFAULT_POLICY,
    options: ConfidencePolicyQualityOptions | None = None,
) -> ConfidencePolicyQualityReport:
    options = options or ConfidencePolicyQualityOptions()
    policy = _read_json(policy_path, {})
    present = isinstance(policy, Mapping) and bool(policy)
    policy = _as_dict(policy)
    layers = _as_dict(policy.get("layers"))
    checks: list[PolicyQualityCheck] = []

    _add(checks, "policy_present", present, f"Policy present at {policy_path}: {present}.")
    status_ok = _text(policy.get("status")).upper() == "OK"
    _add(checks, "policy_status", status_ok, f"Policy status is {policy.get('status')!r}.")
    version_ok = _text(policy.get("version")) == POLICY_VERSION
    _add(checks, "policy_version", version_ok, f"Policy version is {policy.get('version')!r}.")
    layer_count_ok = len(layers) >= options.min_layers
    _add(checks, "policy_layers", layer_count_ok, f"Layer count={len(layers)}; minimum={options.min_layers}.")

    source = _as_dict(layers.get("source_trace"))
    if options.require_source_trace_policy:
        ok = bool(source) and source.get("max_auto_trust_tier") == "A" and source.get("default_rag_action") == "include_as_source_evidence"
        _add(checks, "source_trace_policy", ok, f"source_trace policy max={source.get('max_auto_trust_tier')} rag={source.get('default_rag_action')}.")
        blocks = source.get("hard_blocks") or []
        block_ok = "missing_tiff" in blocks and "missing_source_url" in blocks
        _add(checks, "source_trace_hard_blocks", block_ok, f"source_trace hard blocks={blocks}.")

    table_text = _as_dict(layers.get("table_tile_text_refined"))
    if options.require_table_tile_text_policy:
        ok = bool(table_text) and table_text.get("min_rag_tier") == "B" and table_text.get("default_rag_action") == "include_as_derived_context"
        _add(checks, "table_tile_text_policy", ok, f"table_tile_text_refined min_rag={table_text.get('min_rag_tier')} rag={table_text.get('default_rag_action')}.")
        supports = table_text.get("required_supports_for_B") or []
        support_ok = "catalog_supported_part_number" in supports and "source_trace_verified" in supports
        _add(checks, "table_tile_text_supports", support_ok, f"table_tile_text_refined required B supports={supports}.")

    visual = _as_dict(layers.get("visual_text"))
    if options.require_visual_text_conservative:
        ok = bool(visual) and visual.get("max_auto_trust_tier") == "B" and _num(_as_dict(visual.get("thresholds")).get("A")) >= 0.90
        _add(checks, "visual_text_conservative", ok, f"visual_text max={visual.get('max_auto_trust_tier')} thresholds={visual.get('thresholds')}.")
        hard_blocks = visual.get("hard_blocks") or []
        blocks_ok = all(flag in hard_blocks for flag in ("metadata_leakage", "prompt_template_leakage", "refusal_like"))
        _add(checks, "visual_text_hard_blocks", blocks_ok, f"visual_text hard blocks={hard_blocks}.")

    table_candidate = _as_dict(layers.get("table_candidate"))
    if options.require_routing_only_table_candidate:
        ok = bool(table_candidate) and table_candidate.get("purpose") == "routing_signal" and table_candidate.get("min_rag_tier") in (None, "")
        _add(checks, "table_candidate_routing_only", ok, f"table_candidate purpose={table_candidate.get('purpose')} min_rag={table_candidate.get('min_rag_tier')}.")
        rag_ok = table_candidate.get("default_rag_action") == "exclude_until_table_tiles_exist"
        _add(checks, "table_candidate_no_direct_rag", rag_ok, f"table_candidate default rag={table_candidate.get('default_rag_action')}.")

    global_gates = policy.get("global_hard_safety_gates") or []
    gate_ok = "source_untraceable_records_must_not_enter_rag" in global_gates and "D_tier_records_must_not_enter_rag" in global_gates
    _add(checks, "global_safety_gates", gate_ok, f"global safety gates={global_gates}.")

    stage2_summary = _as_dict(policy.get("stage2_summary"))
    summary = {
        "trace_lc_policy_present": present,
        "trace_lc_policy_status": policy.get("status"),
        "trace_lc_policy_version": policy.get("version"),
        "trace_lc_policy_layers": len(layers),
        "trace_lc_policy_path": str(policy_path),
        "trace_lc_policy_stage2_present": stage2_summary.get("stage2_present"),
        "trace_lc_policy_stage2_agreement_rate": stage2_summary.get("agreement_rate"),
        "trace_lc_policy_stage2_within_one_tier_rate": stage2_summary.get("within_one_tier_rate"),
        "trace_lc_policy_source_trace_max_tier": source.get("max_auto_trust_tier"),
        "trace_lc_policy_part_catalog_max_tier": _as_dict(layers.get("part_catalog")).get("max_auto_trust_tier"),
        "trace_lc_policy_visual_text_max_tier": visual.get("max_auto_trust_tier"),
        "trace_lc_policy_table_tile_text_min_rag_tier": table_text.get("min_rag_tier"),
        "trace_lc_policy_table_candidate_purpose": table_candidate.get("purpose"),
    }
    status = "OK" if all(check.ok for check in checks) else "FAIL"
    return ConfidencePolicyQualityReport(status=status, summary=summary, checks=checks)


def write_confidence_policy_quality(
    quality_path: Path = DEFAULT_QUALITY,
    policy_path: Path = DEFAULT_POLICY,
    options: ConfidencePolicyQualityOptions | None = None,
) -> ConfidencePolicyQualityReport:
    report = build_confidence_policy_quality(policy_path, options)
    _write_json(quality_path, report.to_json())
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_report(report: ConfidencePolicyQualityReport, quality_path: Path) -> None:
    print("TRACE-Net Layer Confidence Stage 3 policy quality gate")
    print(f"  Status: {report.status}")
    print("  Summary:")
    for key, value in report.summary.items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in report.checks:
        label = "OK" if check.ok else "FAIL"
        print(f"    {label} {check.name}: {check.message}")
    print(f"\nJSON: {quality_path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Stage 3 confidence policy")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--quality", type=Path, default=DEFAULT_QUALITY)
    parser.add_argument("--min-layers", type=int, default=6)
    parser.add_argument("--no-require-source-trace-policy", action="store_true")
    parser.add_argument("--no-require-table-tile-text-policy", action="store_true")
    parser.add_argument("--no-require-visual-text-conservative", action="store_true")
    parser.add_argument("--no-require-routing-only-table-candidate", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    options = ConfidencePolicyQualityOptions(
        min_layers=args.min_layers,
        require_source_trace_policy=not args.no_require_source_trace_policy,
        require_table_tile_text_policy=not args.no_require_table_tile_text_policy,
        require_visual_text_conservative=not args.no_require_visual_text_conservative,
        require_routing_only_table_candidate=not args.no_require_routing_only_table_candidate,
    )
    report = build_confidence_policy_quality(args.policy, options)
    if args.write_json:
        _write_json(args.quality, report.to_json())
    _print_report(report, args.quality)
    return 0 if report.status == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
