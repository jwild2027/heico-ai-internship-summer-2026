"""TRACE-Net Layer Confidence Stage 2 evaluation.

Stage 1 adds advisory TRACE-LC scores to Evidence Consensus records.
Stage 2 does not change routing. It compares the current rule-based trust tiers
against the score-based confidence tiers so the confidence policy can be tuned
before it controls any RAG/repair decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import argparse
import html
import json
import math
import os
import subprocess
import sys

TIER_ORDER = {"D": 0, "C": 1, "B": 2, "A": 3}
TIERS = ["A", "B", "C", "D"]


@dataclass(frozen=True)
class ConfidenceStage2Paths:
    consensus_records: Path = Path(
        "local_data/organization/trace_net/evidence_consensus/evidence_consensus_records.jsonl"
    )
    consensus_summary: Path = Path(
        "local_data/organization/trace_net/evidence_consensus/evidence_consensus_summary.json"
    )
    output_dir: Path = Path("local_data/organization/trace_net/confidence")
    eval_json: Path = field(init=False)
    report_md: Path = field(init=False)
    report_html: Path = field(init=False)

    def __post_init__(self) -> None:  # pragma: no cover - dataclass plumbing
        object.__setattr__(self, "eval_json", self.output_dir / "trace_lc_stage2_eval.json")
        object.__setattr__(self, "report_md", self.output_dir / "trace_lc_stage2_eval.md")
        object.__setattr__(self, "report_html", self.output_dir / "trace_lc_stage2_eval.html")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    return records


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tier(value: Any) -> str:
    if isinstance(value, str) and value.upper() in TIER_ORDER:
        return value.upper()
    return "D"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(value)
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except Exception:
        return default


def _count_map(items: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return dict(sorted(out.items()))


def _add_matrix(matrix: dict[str, dict[str, int]], current: str, confidence: str) -> None:
    matrix.setdefault(current, {t: 0 for t in TIERS})
    matrix[current][confidence] = matrix[current].get(confidence, 0) + 1


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _rate(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _record_id(record: Mapping[str, Any]) -> str:
    return str(
        record.get("record_id")
        or record.get("consensus_id")
        or f"{record.get('page_id', 'unknown')}:{record.get('evidence_layer', 'unknown')}"
    )


def _rag_includes(action: Any) -> bool:
    return str(action or "").startswith("include_")


def _is_blocked(record: Mapping[str, Any]) -> bool:
    if record.get("unsafe_rag_include") is True:
        return True
    if record.get("source_untraceable") is True:
        return True
    risk = str(record.get("hallucination_risk") or "").lower()
    if risk in {"blocked", "high_risk"}:
        return True
    scores = _as_dict(record.get("confidence_scores"))
    if scores.get("hard_gate_blocked") is True:
        return True
    return False


def evaluate_confidence_stage2(
    paths: ConfidenceStage2Paths,
    *,
    max_samples: int = 25,
) -> dict[str, Any]:
    records = _read_jsonl(paths.consensus_records)
    consensus_summary = _read_json(paths.consensus_summary, default={}) or {}

    total = len(records)
    scored: list[dict[str, Any]] = []
    missing_confidence: list[dict[str, Any]] = []

    layer_buckets: dict[str, dict[str, Any]] = {}
    confusion: dict[str, dict[str, int]] = {t: {u: 0 for u in TIERS} for t in TIERS}

    exact_matches = 0
    within_one_tier = 0
    disagreement = 0
    confidence_higher = 0
    confidence_lower = 0
    rule_includes_confidence_low = 0
    rule_excludes_confidence_high = 0
    blocked_high_confidence = 0
    source_trace_confidence_below_a = 0

    usable_values: list[float] = []
    support_values: list[float] = []
    risk_values: list[float] = []

    promotion_candidates: list[dict[str, Any]] = []
    demotion_candidates: list[dict[str, Any]] = []
    blocked_high_confidence_samples: list[dict[str, Any]] = []
    largest_disagreements: list[dict[str, Any]] = []

    for record in records:
        scores = _as_dict(record.get("confidence_scores"))
        if not scores:
            missing_confidence.append(dict(record))
            continue

        current_tier = _tier(record.get("trust_tier"))
        confidence_tier = _tier(scores.get("confidence_tier"))
        current_rank = TIER_ORDER[current_tier]
        confidence_rank = TIER_ORDER[confidence_tier]
        tier_delta = confidence_rank - current_rank

        usable = _num(scores.get("usable_confidence"))
        support = _num(scores.get("support_score"))
        risk = _num(scores.get("risk_score"))
        layer = str(record.get("evidence_layer") or "unknown")
        rag_action = str(record.get("rag_action") or "")
        page_id = str(record.get("page_id") or "")
        blocked = _is_blocked(record)

        usable_values.append(usable)
        support_values.append(support)
        risk_values.append(risk)
        scored.append(dict(record))
        _add_matrix(confusion, current_tier, confidence_tier)

        bucket = layer_buckets.setdefault(
            layer,
            {
                "records": 0,
                "current_tier_counts": {},
                "confidence_tier_counts": {},
                "exact_matches": 0,
                "disagreements": 0,
                "confidence_higher": 0,
                "confidence_lower": 0,
                "rule_includes_confidence_low": 0,
                "rule_excludes_confidence_high": 0,
                "usable_values": [],
                "support_values": [],
                "risk_values": [],
            },
        )
        bucket["records"] += 1
        bucket["current_tier_counts"][current_tier] = bucket["current_tier_counts"].get(current_tier, 0) + 1
        bucket["confidence_tier_counts"][confidence_tier] = bucket["confidence_tier_counts"].get(confidence_tier, 0) + 1
        bucket["usable_values"].append(usable)
        bucket["support_values"].append(support)
        bucket["risk_values"].append(risk)

        if current_tier == confidence_tier:
            exact_matches += 1
            bucket["exact_matches"] += 1
        else:
            disagreement += 1
            bucket["disagreements"] += 1

        if abs(tier_delta) <= 1:
            within_one_tier += 1

        if tier_delta > 0:
            confidence_higher += 1
            bucket["confidence_higher"] += 1
        elif tier_delta < 0:
            confidence_lower += 1
            bucket["confidence_lower"] += 1

        if _rag_includes(rag_action) and confidence_tier in {"C", "D"}:
            rule_includes_confidence_low += 1
            bucket["rule_includes_confidence_low"] += 1
            if len(demotion_candidates) < max_samples:
                demotion_candidates.append(
                    {
                        "record_id": _record_id(record),
                        "page_id": page_id,
                        "evidence_layer": layer,
                        "trust_tier": current_tier,
                        "confidence_tier": confidence_tier,
                        "usable_confidence": usable,
                        "rag_action": rag_action,
                        "reason": "current rule includes, confidence tier is C/D",
                    }
                )

        if (not _rag_includes(rag_action)) and confidence_tier in {"A", "B"} and not blocked:
            rule_excludes_confidence_high += 1
            bucket["rule_excludes_confidence_high"] += 1
            if len(promotion_candidates) < max_samples:
                promotion_candidates.append(
                    {
                        "record_id": _record_id(record),
                        "page_id": page_id,
                        "evidence_layer": layer,
                        "trust_tier": current_tier,
                        "confidence_tier": confidence_tier,
                        "usable_confidence": usable,
                        "rag_action": rag_action,
                        "reason": "current rule excludes, confidence tier is A/B",
                    }
                )

        if blocked and confidence_tier in {"A", "B"}:
            blocked_high_confidence += 1
            if len(blocked_high_confidence_samples) < max_samples:
                blocked_high_confidence_samples.append(
                    {
                        "record_id": _record_id(record),
                        "page_id": page_id,
                        "evidence_layer": layer,
                        "trust_tier": current_tier,
                        "confidence_tier": confidence_tier,
                        "usable_confidence": usable,
                        "rag_action": rag_action,
                        "reason": "confidence high but hard/risk gate is blocked",
                    }
                )

        if layer == "source_trace" and current_tier == "A" and confidence_tier != "A":
            source_trace_confidence_below_a += 1

        if tier_delta != 0 and len(largest_disagreements) < max_samples:
            largest_disagreements.append(
                {
                    "record_id": _record_id(record),
                    "page_id": page_id,
                    "evidence_layer": layer,
                    "trust_tier": current_tier,
                    "confidence_tier": confidence_tier,
                    "tier_delta": tier_delta,
                    "usable_confidence": usable,
                    "support_score": support,
                    "risk_score": risk,
                    "rag_action": rag_action,
                }
            )

    per_layer: dict[str, Any] = {}
    for layer, bucket in sorted(layer_buckets.items()):
        records_count = int(bucket["records"])
        per_layer[layer] = {
            "records": records_count,
            "current_tier_counts": dict(sorted(bucket["current_tier_counts"].items())),
            "confidence_tier_counts": dict(sorted(bucket["confidence_tier_counts"].items())),
            "exact_matches": bucket["exact_matches"],
            "disagreements": bucket["disagreements"],
            "agreement_rate": _rate(bucket["exact_matches"], records_count),
            "confidence_higher": bucket["confidence_higher"],
            "confidence_lower": bucket["confidence_lower"],
            "rule_includes_confidence_low": bucket["rule_includes_confidence_low"],
            "rule_excludes_confidence_high": bucket["rule_excludes_confidence_high"],
            "avg_usable_confidence": _mean(bucket["usable_values"]),
            "avg_support_score": _mean(bucket["support_values"]),
            "avg_risk_score": _mean(bucket["risk_values"]),
        }

    score_records = len(scored)
    summary = {
        "status": "OK",
        "version": "trace_lc_stage2_eval_v1",
        "created_at": _utc_now(),
        "consensus_records_path": str(paths.consensus_records),
        "consensus_summary_path": str(paths.consensus_summary),
        "records": total,
        "scored_records": score_records,
        "missing_confidence_records": len(missing_confidence),
        "consensus_status": consensus_summary.get("status"),
        "pages_loaded": consensus_summary.get("pages_loaded") or consensus_summary.get("page_count"),
        "current_trust_tier_counts": consensus_summary.get("trust_tier_counts", _count_map([_tier(r.get("trust_tier")) for r in records])),
        "confidence_tier_counts": _count_map([_tier(_as_dict(r.get("confidence_scores")).get("confidence_tier")) for r in scored]),
        "confusion_matrix": confusion,
        "exact_match_records": exact_matches,
        "disagreement_records": disagreement,
        "agreement_rate": _rate(exact_matches, score_records),
        "within_one_tier_records": within_one_tier,
        "within_one_tier_rate": _rate(within_one_tier, score_records),
        "confidence_higher_records": confidence_higher,
        "confidence_lower_records": confidence_lower,
        "rule_includes_confidence_low_records": rule_includes_confidence_low,
        "rule_excludes_confidence_high_records": rule_excludes_confidence_high,
        "blocked_high_confidence_records": blocked_high_confidence,
        "source_trace_confidence_below_A_records": source_trace_confidence_below_a,
        "avg_usable_confidence": _mean(usable_values),
        "avg_support_score": _mean(support_values),
        "avg_risk_score": _mean(risk_values),
        "per_layer": per_layer,
        "promotion_candidate_samples": promotion_candidates,
        "demotion_candidate_samples": demotion_candidates,
        "blocked_high_confidence_samples": blocked_high_confidence_samples,
        "largest_disagreement_samples": largest_disagreements,
        "interpretation": {
            "stage": "advisory_comparison_only",
            "routing_changed": False,
            "recommendation": _recommendation(source_trace_confidence_below_a, rule_includes_confidence_low, rule_excludes_confidence_high, score_records),
        },
    }

    report_md = render_confidence_stage2_markdown(summary)
    report_html = render_confidence_stage2_html(report_md)

    _write_json(paths.eval_json, summary)
    _write_text(paths.report_md, report_md)
    _write_text(paths.report_html, report_html)
    return summary


def _recommendation(source_trace_below_a: int, includes_low: int, excludes_high: int, total: int) -> str:
    if source_trace_below_a > 0:
        return "calibrate_layer_specific_thresholds_before_using_scores_for_routing"
    if includes_low > 0:
        return "review_potential_over_inclusion_before_enabling_score_routing"
    if excludes_high > max(10, total // 10):
        return "review_potential_under_inclusion_and_layer_weights"
    return "scores_are_ready_for_manual_calibration_review"


def render_confidence_stage2_markdown(summary: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# TRACE-Net Layer Confidence Stage 2 Evaluation")
    lines.append("")
    lines.append(f"Status: **{summary.get('status')}**")
    lines.append(f"Version: `{summary.get('version')}`")
    lines.append("")
    lines.append("## Summary")
    for key in [
        "records",
        "scored_records",
        "missing_confidence_records",
        "agreement_rate",
        "disagreement_records",
        "within_one_tier_rate",
        "confidence_higher_records",
        "confidence_lower_records",
        "rule_includes_confidence_low_records",
        "rule_excludes_confidence_high_records",
        "blocked_high_confidence_records",
        "source_trace_confidence_below_A_records",
        "avg_usable_confidence",
        "avg_support_score",
        "avg_risk_score",
    ]:
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.append("")
    interpretation = _as_dict(summary.get("interpretation"))
    lines.append(f"Recommendation: `{interpretation.get('recommendation')}`")
    lines.append("")
    lines.append("## Confusion Matrix")
    lines.append("")
    lines.append("Rows are current rule-based trust tiers. Columns are TRACE-LC confidence tiers.")
    lines.append("")
    lines.append("| Current \\ Confidence | A | B | C | D |")
    lines.append("|---|---:|---:|---:|---:|")
    confusion = _as_dict(summary.get("confusion_matrix"))
    for current in TIERS:
        row = _as_dict(confusion.get(current))
        lines.append(f"| {current} | {row.get('A', 0)} | {row.get('B', 0)} | {row.get('C', 0)} | {row.get('D', 0)} |")
    lines.append("")
    lines.append("## Per-layer metrics")
    lines.append("")
    lines.append("| Layer | Records | Agreement | Current tiers | Confidence tiers | Avg usable | Avg risk |")
    lines.append("|---|---:|---:|---|---|---:|---:|")
    for layer, item in _as_dict(summary.get("per_layer")).items():
        lines.append(
            "| {layer} | {records} | {agreement} | `{current}` | `{confidence}` | {usable} | {risk} |".format(
                layer=layer,
                records=item.get("records"),
                agreement=item.get("agreement_rate"),
                current=item.get("current_tier_counts"),
                confidence=item.get("confidence_tier_counts"),
                usable=item.get("avg_usable_confidence"),
                risk=item.get("avg_risk_score"),
            )
        )
    lines.append("")
    _append_samples(lines, "Promotion candidate samples", summary.get("promotion_candidate_samples"))
    _append_samples(lines, "Demotion candidate samples", summary.get("demotion_candidate_samples"))
    _append_samples(lines, "Blocked high-confidence samples", summary.get("blocked_high_confidence_samples"))
    _append_samples(lines, "Largest disagreement samples", summary.get("largest_disagreement_samples"))
    return "\n".join(lines) + "\n"


def _append_samples(lines: list[str], title: str, value: Any) -> None:
    samples = value if isinstance(value, list) else []
    lines.append(f"## {title}")
    lines.append("")
    if not samples:
        lines.append("None.")
        lines.append("")
        return
    for sample in samples:
        if not isinstance(sample, Mapping):
            continue
        lines.append(
            "- `{record_id}` page=`{page_id}` layer=`{layer}` trust=`{trust}` confidence=`{confidence}` usable=`{usable}` action=`{action}`".format(
                record_id=sample.get("record_id"),
                page_id=sample.get("page_id"),
                layer=sample.get("evidence_layer"),
                trust=sample.get("trust_tier"),
                confidence=sample.get("confidence_tier"),
                usable=sample.get("usable_confidence"),
                action=sample.get("rag_action"),
            )
        )
    lines.append("")


def render_confidence_stage2_html(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    body = escaped.replace("\n", "<br>\n")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>TRACE-Net Layer Confidence Stage 2</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;line-height:1.45}"
        "code{background:#f4f4f4;padding:2px 4px;border-radius:4px}"
        "pre{white-space:pre-wrap;background:#f7f7f7;padding:16px;border-radius:8px}</style>"
        "</head><body><pre>" + escaped + "</pre></body></html>"
    )


def _open_file(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path.resolve()))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path.resolve())], check=False)
        else:
            subprocess.run(["xdg-open", str(path.resolve())], check=False)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate TRACE-Net Layer Confidence Stage 2 calibration.")
    parser.add_argument("--records", type=Path, default=ConfidenceStage2Paths.consensus_records)
    parser.add_argument("--summary", type=Path, default=ConfidenceStage2Paths.consensus_summary)
    parser.add_argument("--output-dir", type=Path, default=ConfidenceStage2Paths.output_dir)
    parser.add_argument("--samples", type=int, default=25)
    parser.add_argument("--open", action="store_true", dest="open_report")
    args = parser.parse_args(argv)

    paths = ConfidenceStage2Paths(
        consensus_records=args.records,
        consensus_summary=args.summary,
        output_dir=args.output_dir,
    )
    report = evaluate_confidence_stage2(paths, max_samples=args.samples)

    print("TRACE-Net Layer Confidence Stage 2 evaluation")
    print(f"  Status: {report.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in [
        "records",
        "scored_records",
        "agreement_rate",
        "disagreement_records",
        "within_one_tier_rate",
        "confidence_higher_records",
        "confidence_lower_records",
        "rule_includes_confidence_low_records",
        "rule_excludes_confidence_high_records",
        "source_trace_confidence_below_A_records",
        "avg_usable_confidence",
    ]:
        print(f"    {key}: {report.get(key)}")
    print("  Per-layer agreement:")
    for layer, item in _as_dict(report.get("per_layer")).items():
        print(
            f"    {layer}: records={item.get('records')} agreement={item.get('agreement_rate')} "
            f"avg_usable={item.get('avg_usable_confidence')}"
        )
    print("Files written:")
    print(f"  eval_json: {paths.eval_json}")
    print(f"  report_md: {paths.report_md}")
    print(f"  report_html: {paths.report_html}")

    if args.open_report:
        _open_file(paths.report_html)
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
