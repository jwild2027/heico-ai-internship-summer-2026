"""TRACE-Net Weighted Search Simulation v1.

Simulation-only layer that reads the official TRACE-Net weights policy and the
latest grouped search results, then computes a weighted ranking proposal.

This module does not mutate production search ranking, source truth, Evidence
Consensus, RAG eligibility, trust tiers, or feedback. It only writes a sidecar
simulation artifact for review and quality-gating.

Inputs:
  local_data/organization/trace_net/search/trace_net_search_grouped_results.jsonl
  local_data/organization/trace_net/search/trace_net_search_grouped_summary.json
  local_data/organization/trace_net/search/trace_net_search_summary.json
  local_data/organization/trace_net/weights/trace_net_weights_policy.json
  local_data/organization/trace_net/feedback/feedback_policy_signals.jsonl

Outputs:
  local_data/organization/trace_net/weighted_search/
"""
from __future__ import annotations

import argparse
import html
import json
import re
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_SEARCH_DIR = TRACE_NET_DIR / "search"
DEFAULT_WEIGHTS_DIR = TRACE_NET_DIR / "weights"
DEFAULT_FEEDBACK_DIR = TRACE_NET_DIR / "feedback"
DEFAULT_OUTPUT_DIR = TRACE_NET_DIR / "weighted_search"

VERSION = "trace_net_weighted_search_simulation_v1"
SAFE_BUCKETS = {"source_evidence", "source_text_evidence", "verified_part_evidence", "derived_context"}
UNSAFE_LAYERS = {"table_candidate", "table_tiles"}
SAFE_RAG_ACTIONS = {"include_as_source_evidence", "include_as_verified_part_evidence", "include_as_derived_context", "include_as_source_text_evidence"}
PART_RE = re.compile(r"\b(?:\d{3}-\d{4,6}-[A-Z0-9]{2,4}|\d{2,4}TP\d{4,8}[A-Z0-9.\-]*|[A-Z]{1,4}\d{2,6}[A-Z0-9.\-]{1,})\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+_p\d{6}\b")


@dataclass(frozen=True)
class WeightedSearchSimulationPaths:
    search_dir: Path = DEFAULT_SEARCH_DIR
    weights_dir: Path = DEFAULT_WEIGHTS_DIR
    feedback_dir: Path = DEFAULT_FEEDBACK_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    grouped_results_path: Path | None = None
    grouped_summary_path: Path | None = None
    search_summary_path: Path | None = None
    weights_policy_path: Path | None = None
    feedback_signals_path: Path | None = None
    simulation_path: Path | None = None
    simulation_jsonl_path: Path | None = None
    summary_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    quality_path: Path | None = None

    @property
    def grouped_results(self) -> Path:
        return self.grouped_results_path or (self.search_dir / "trace_net_search_grouped_results.jsonl")

    @property
    def grouped_summary(self) -> Path:
        return self.grouped_summary_path or (self.search_dir / "trace_net_search_grouped_summary.json")

    @property
    def search_summary(self) -> Path:
        return self.search_summary_path or (self.search_dir / "trace_net_search_summary.json")

    @property
    def weights_policy(self) -> Path:
        return self.weights_policy_path or (self.weights_dir / "trace_net_weights_policy.json")

    @property
    def feedback_signals(self) -> Path:
        return self.feedback_signals_path or (self.feedback_dir / "feedback_policy_signals.jsonl")

    @property
    def simulation(self) -> Path:
        return self.simulation_path or (self.output_dir / "trace_net_weighted_search_simulation.json")

    @property
    def simulation_jsonl(self) -> Path:
        return self.simulation_jsonl_path or (self.output_dir / "trace_net_weighted_search_simulation_results.jsonl")

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / "trace_net_weighted_search_simulation_summary.json")

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / "trace_net_weighted_search_simulation_review.md")

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / "trace_net_weighted_search_simulation_review.html")

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / "trace_net_weighted_search_simulation_graph_nodes.json")

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / "trace_net_weighted_search_simulation_graph_edges.json")

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / "trace_net_weighted_search_simulation_quality.json")


@dataclass(frozen=True)
class WeightedSearchSimulationOptions:
    query: str = ""
    part_number: str = ""
    page_id: str = ""
    top_k: int = 20
    use_feedback: bool = True
    open_report: bool = False


# ---------------------------------------------------------------------------
# IO/basic helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                rows.append(dict(value))
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) + "\n")


def _write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def _unique(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _count(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        text = _text(value)
        if not text:
            continue
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items()))


def _slug(value: Any) -> str:
    text = _text(value).lower()
    text = re.sub(r"[^a-z0-9._:-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def _clip(value: Any, max_chars: int = 600) -> str:
    text = _text(value)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "…"


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _normalize_part(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _query_fingerprint(query: str = "", part_number: str = "", page_id: str = "") -> str:
    if part_number:
        return "part_number:" + part_number.upper().strip()
    if page_id:
        return "page:" + page_id.strip()
    text = (query or "").strip()
    if not text:
        return "query:unknown"
    part_match = PART_RE.search(text.upper())
    if part_match:
        return "part_number:" + part_match.group(0)
    page_match = PAGE_RE.search(text)
    if page_match:
        return "page:" + page_match.group(0)
    toks = _tokens(text)
    return "query:" + "_".join(toks[:12]) if toks else "query:unknown"


def _infer_query(search_summary: Mapping[str, Any], options: WeightedSearchSimulationOptions) -> tuple[str, str, str, str]:
    query = _text(options.query)
    part_number = _text(options.part_number)
    page_id = _text(options.page_id)
    if not query and not part_number and not page_id:
        query = _text(search_summary.get("query")) or _text(search_summary.get("effective_query"))
        part_number = _text(search_summary.get("part_number"))
        page_id = _text(search_summary.get("page_id"))
    effective = part_number or page_id or query
    return query, part_number, page_id, effective


def _safe_group(group: Mapping[str, Any]) -> bool:
    if group.get("safe_group") is False:
        return False
    for bucket in _as_list(group.get("rag_buckets")):
        if _text(bucket) not in SAFE_BUCKETS:
            return False
    for layer in _as_list(group.get("evidence_layers")):
        if _text(layer) in UNSAFE_LAYERS:
            return False
    if int(group.get("unsafe_supporting_results") or 0) > 0:
        return False
    if int(group.get("excluded_supporting_results") or 0) > 0:
        return False
    return True


# ---------------------------------------------------------------------------
# Policy helpers
# ---------------------------------------------------------------------------


def _default_policy() -> dict[str, Any]:
    return {
        "version": "fallback_weights_policy",
        "retrieval_ranking": {
            "exact_match_bonuses": {
                "exact_part_number_match": 20.0,
                "exact_page_id_match": 25.0,
                "exact_phrase_match": 8.0,
                "all_query_terms_matched": 10.0,
                "per_matched_term": 2.0,
            },
            "bucket_bonuses": {
                "verified_part_evidence": 8.0,
                "source_text_evidence": 5.0,
                "derived_context": 3.0,
                "source_evidence": 2.0,
            },
            "evidence_diversity": {"per_bucket_bonus": 4.0, "max_bucket_bonus": 12.0},
            "confidence_bonus": {"multiplier": 3.0, "source": "usable_confidence"},
        },
        "feedback_ranking": {
            "reason_weights": {
                "answer_correct": 6.0,
                "source_helpful": 5.0,
                "citation_useful": 4.0,
                "wrong_page": -8.0,
                "wrong_part": -10.0,
                "citation_not_supporting_answer": -7.0,
                "answer_too_vague": -3.0,
                "expected_page_boost": 8.0,
            },
            "cap_min": -15.0,
            "cap_max": 15.0,
        },
    }


def _policy_section(policy: Mapping[str, Any], key: str) -> dict[str, Any]:
    section = policy.get(key)
    if isinstance(section, Mapping):
        return dict(section)
    return dict(_default_policy().get(key, {}))


def _retrieval_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    fallback = _default_policy()["retrieval_ranking"]
    out = dict(fallback)
    current = _policy_section(policy, "retrieval_ranking")
    for key, value in current.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            merged = dict(out[key])
            merged.update(value)
            out[key] = merged
        else:
            out[key] = value
    return out


def _feedback_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    fallback = _default_policy()["feedback_ranking"]
    out = dict(fallback)
    current = _policy_section(policy, "feedback_ranking")
    for key, value in current.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            merged = dict(out[key])
            merged.update(value)
            out[key] = merged
        else:
            out[key] = value
    return out


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _group_text_blob(group: Mapping[str, Any]) -> str:
    bits: list[str] = []
    for key in ("page_id", "source_url"):
        bits.append(_text(group.get(key)))
    bits.extend(_text(v) for v in _as_list(group.get("matched_terms")))
    bits.extend(_text(v) for v in _as_list(group.get("matched_part_numbers")))
    bits.extend(_text(v) for v in _as_list(group.get("rag_buckets")))
    bits.extend(_text(v) for v in _as_list(group.get("evidence_layers")))
    for res in _as_list(group.get("supporting_results")):
        if isinstance(res, Mapping):
            bits.append(_text(res.get("text_preview")))
            bits.extend(_text(v) for v in _as_list(res.get("matched_terms")))
            bits.extend(_text(v) for v in _as_list(res.get("matched_part_numbers")))
    return "\n".join(bits)


def _exact_part_match(group: Mapping[str, Any], part_number: str) -> bool:
    if not part_number:
        return False
    target = _normalize_part(part_number)
    for part in _as_list(group.get("matched_part_numbers")):
        if _normalize_part(_text(part)) == target:
            return True
    for res in _as_list(group.get("supporting_results")):
        if isinstance(res, Mapping):
            for part in _as_list(res.get("matched_part_numbers")):
                if _normalize_part(_text(part)) == target:
                    return True
    return target in _normalize_part(_group_text_blob(group))


def _query_match_components(group: Mapping[str, Any], query: str, part_number: str, page_id: str, retrieval: Mapping[str, Any]) -> dict[str, Any]:
    exact = dict(retrieval.get("exact_match_bonuses") or {})
    blob = _group_text_blob(group)
    blob_lower = blob.lower()
    matched_terms = _unique(_as_list(group.get("matched_terms")))
    query_terms = _tokens(query) if query else []
    if not query_terms and part_number:
        query_terms = [_normalize_part(part_number).lower()]
    if not query_terms and page_id:
        query_terms = [page_id.lower()]
    lower_terms_in_blob = set(_tokens(blob))
    terms_matched = _unique(list(matched_terms) + [term for term in query_terms if term in lower_terms_in_blob])
    part_match = _exact_part_match(group, part_number) or (bool(part_number) and part_number.lower() in blob_lower)
    page_match = bool(page_id) and (_text(group.get("page_id")) == page_id or page_id.lower() in blob_lower)
    phrase_match = bool(query and len(query.strip().split()) > 1 and query.lower().strip() in blob_lower)
    all_terms = bool(query_terms) and all(term in lower_terms_in_blob or term in [t.lower() for t in terms_matched] for term in query_terms)
    bonus = 0.0
    if part_match:
        bonus += _num(exact.get("exact_part_number_match"), 20.0)
    if page_match:
        bonus += _num(exact.get("exact_page_id_match"), 25.0)
    if phrase_match:
        bonus += _num(exact.get("exact_phrase_match"), 8.0)
    if all_terms:
        bonus += _num(exact.get("all_query_terms_matched"), 10.0)
    bonus += len(terms_matched) * _num(exact.get("per_matched_term"), 2.0)
    return {
        "exact_part_number_match": part_match,
        "exact_page_id_match": page_match,
        "exact_phrase_match": phrase_match,
        "all_query_terms_matched": all_terms,
        "matched_terms": terms_matched,
        "query_terms": query_terms,
        "exact_match_bonus": round(bonus, 6),
    }


def _feedback_signal_target(signal: Mapping[str, Any]) -> str:
    for key in ("page_id", "target_id", "target_page_id"):
        value = _text(signal.get(key))
        if value:
            return value
    return ""


def _signal_query_fingerprint(signal: Mapping[str, Any]) -> str:
    return _text(signal.get("query_fingerprint"))


def _signal_ranking_eligible(signal: Mapping[str, Any]) -> bool:
    if signal.get("ranking_eligible") is False:
        return False
    if signal.get("policy_signal_eligible") is False:
        return False
    if signal.get("mutates_source_truth") or signal.get("source_truth_mutation") or signal.get("ranking_mutation"):
        return False
    if int(signal.get("context_warning_count") or 0) > 0:
        return False
    rec = _text(signal.get("recommendation") or signal.get("signal"))
    if rec == "review_feedback_context_before_use":
        return False
    if signal.get("requires_review") is True and rec not in {"demote_for_query", "promote_expected_page_for_query"}:
        # Some demotions require review in the feedback graph but are still eligible after context validation.
        return False
    return True


def _feedback_adjustment_for_group(group: Mapping[str, Any], signals: Sequence[Mapping[str, Any]], query_fingerprint: str, feedback: Mapping[str, Any]) -> tuple[float, list[dict[str, Any]], int]:
    reason_weights = dict(feedback.get("reason_weights") or {})
    cap_min = _num(feedback.get("cap_min"), -15.0)
    cap_max = _num(feedback.get("cap_max"), 15.0)
    page_id = _text(group.get("page_id"))
    raw_total = 0.0
    used: list[dict[str, Any]] = []
    context_warning_used = 0
    for signal in signals:
        if _signal_query_fingerprint(signal) != query_fingerprint:
            continue
        if _feedback_signal_target(signal) != page_id:
            continue
        if not _signal_ranking_eligible(signal):
            # Ineligible/context-warning feedback is deliberately ignored and is not counted as used.
            continue
        recommendation = _text(signal.get("recommendation") or signal.get("signal"))
        reason_counts = _as_dict(signal.get("reason_counts"))
        strength = _num(signal.get("strength"), 1.0) or 1.0
        contribution = 0.0
        for reason, count in reason_counts.items():
            if reason in reason_weights:
                contribution += _num(reason_weights.get(reason)) * max(1, int(count or 1))
        if recommendation == "promote_expected_page_for_query":
            contribution += _num(reason_weights.get("expected_page_boost"), 8.0) * max(strength, 1.0)
        elif recommendation == "boost_for_query" and contribution == 0.0:
            contribution += _num(reason_weights.get("answer_correct"), 6.0) * max(strength, 1.0)
        elif recommendation == "demote_for_query" and contribution == 0.0:
            contribution += _num(reason_weights.get("wrong_page"), -8.0) * max(strength, 1.0)
        raw_total += contribution
        used.append({
            "signal_id": _text(signal.get("signal_id") or signal.get("id")),
            "recommendation": recommendation,
            "target_id": page_id,
            "strength": round(strength, 6),
            "reason_counts": reason_counts,
            "raw_contribution": round(contribution, 6),
        })
    adjusted = _clamp(raw_total, cap_min, cap_max)
    return round(adjusted, 6), used, context_warning_used


def _weighted_score_for_group(group: Mapping[str, Any], policy: Mapping[str, Any], signals: Sequence[Mapping[str, Any]], query_fingerprint: str, query: str, part_number: str, page_id: str, use_feedback: bool) -> dict[str, Any]:
    retrieval = _retrieval_policy(policy)
    feedback = _feedback_policy(policy)
    bucket_bonuses = dict(retrieval.get("bucket_bonuses") or {})
    diversity = dict(retrieval.get("evidence_diversity") or {})
    confidence = dict(retrieval.get("confidence_bonus") or {})
    buckets = _unique(_as_list(group.get("rag_buckets")))
    bucket_bonus = sum(_num(bucket_bonuses.get(bucket), 0.0) for bucket in buckets)
    diversity_bonus = min(max(0, len(buckets) - 1) * _num(diversity.get("per_bucket_bonus"), 4.0), _num(diversity.get("max_bucket_bonus"), 12.0))
    match = _query_match_components(group, query, part_number, page_id, retrieval)
    confidence_value = max(_num(group.get("max_usable_confidence")), _num(group.get("average_usable_confidence")))
    confidence_bonus = confidence_value * _num(confidence.get("multiplier"), 3.0)
    feedback_adjustment = 0.0
    feedback_signals_used: list[dict[str, Any]] = []
    context_warning_used = 0
    if use_feedback:
        feedback_adjustment, feedback_signals_used, context_warning_used = _feedback_adjustment_for_group(group, signals, query_fingerprint, feedback)
    base_score = _num(group.get("best_score"), _num(group.get("group_score")))
    weighted_score = base_score + bucket_bonus + diversity_bonus + _num(match.get("exact_match_bonus")) + confidence_bonus + feedback_adjustment
    return {
        "base_score": round(base_score, 6),
        "current_group_score": round(_num(group.get("group_score")), 6),
        "bucket_bonus": round(bucket_bonus, 6),
        "evidence_diversity_bonus": round(diversity_bonus, 6),
        "exact_match_bonus": round(_num(match.get("exact_match_bonus")), 6),
        "confidence_bonus": round(confidence_bonus, 6),
        "feedback_adjustment": round(feedback_adjustment, 6),
        "weighted_score": round(weighted_score, 6),
        "feedback_signals_used": feedback_signals_used,
        "context_warning_signals_used": context_warning_used,
        **match,
    }


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------


def simulate_weighted_search(paths: WeightedSearchSimulationPaths, options: WeightedSearchSimulationOptions | None = None) -> dict[str, Any]:
    options = options or WeightedSearchSimulationOptions()
    grouped = _read_jsonl(paths.grouped_results)
    grouped_summary = _read_json(paths.grouped_summary)
    search_summary = _read_json(paths.search_summary)
    policy = _read_json(paths.weights_policy) or _default_policy()
    feedback_signals = _read_jsonl(paths.feedback_signals)
    query, part_number, page_id, effective_query = _infer_query(search_summary, options)
    query_fingerprint = _query_fingerprint(query, part_number=part_number, page_id=page_id)

    rows: list[dict[str, Any]] = []
    for group in grouped:
        comps = _weighted_score_for_group(group, policy, feedback_signals, query_fingerprint, query, part_number, page_id, options.use_feedback)
        row = dict(group)
        row["original_rank"] = int(group.get("rank") or 0)
        row["weighted_score"] = comps["weighted_score"]
        row["weighted_score_components"] = comps
        row["weighted_simulation_safe"] = _safe_group(group)
        row["source_truth_mutation"] = False
        row["weighted_policy_version"] = _text(policy.get("version"), "unknown")
        row["query_fingerprint"] = query_fingerprint
        rows.append(row)

    rows.sort(key=lambda r: (-_num(r.get("weighted_score")), int(r.get("original_rank") or 999999), _text(r.get("page_id"))))
    top_k = max(1, int(options.top_k or 20))
    rows = rows[:top_k]
    for idx, row in enumerate(rows, start=1):
        row["weighted_rank"] = idx
        row["rank_changed"] = int(row.get("original_rank") or 0) != idx

    unsafe = sum(1 for row in rows if not row.get("weighted_simulation_safe"))
    excluded = sum(1 for row in rows if int(row.get("excluded_supporting_results") or 0) > 0)
    mutations = sum(1 for row in rows if row.get("source_truth_mutation"))
    feedback_used = sum(len(_as_list(_as_dict(row.get("weighted_score_components")).get("feedback_signals_used"))) for row in rows)
    groups_adjusted = sum(1 for row in rows if abs(_num(_as_dict(row.get("weighted_score_components")).get("feedback_adjustment"))) > 0.000001)
    rank_changed = sum(1 for row in rows if row.get("rank_changed"))
    context_warning_used = sum(int(_as_dict(row.get("weighted_score_components")).get("context_warning_signals_used") or 0) for row in rows)
    current_order = [_text(row.get("page_id")) for row in sorted(rows, key=lambda r: int(r.get("original_rank") or 999999))]
    weighted_order = [_text(row.get("page_id")) for row in rows]
    summary = {
        "status": "OK" if rows and unsafe == 0 and mutations == 0 else "FAIL",
        "version": VERSION,
        "created_at": _utc_now(),
        "query": effective_query,
        "query_fingerprint": query_fingerprint,
        "weights_policy_version": _text(policy.get("version"), "unknown"),
        "weights_policy_path": str(paths.weights_policy),
        "grouped_results_path": str(paths.grouped_results),
        "feedback_signals_path": str(paths.feedback_signals),
        "grouped_input_records": len(grouped),
        "weighted_group_records": len(rows),
        "pages": len(_unique(row.get("page_id") for row in rows)),
        "feedback_enabled": bool(options.use_feedback),
        "matching_feedback_signal_records": sum(1 for sig in feedback_signals if _signal_query_fingerprint(sig) == query_fingerprint),
        "feedback_signals_used": feedback_used,
        "groups_with_feedback_adjustment": groups_adjusted,
        "rank_changed_records": rank_changed,
        "unsafe_weighted_records": unsafe,
        "excluded_weighted_records": excluded,
        "source_truth_mutation_records": mutations,
        "context_warning_signals_used": context_warning_used,
        "top_page_before": current_order[0] if current_order else "",
        "top_page_after": weighted_order[0] if weighted_order else "",
        "top_page_changed": bool(current_order and weighted_order and current_order[0] != weighted_order[0]),
        "current_page_order": current_order,
        "weighted_page_order": weighted_order,
        "bucket_counts": _count(bucket for row in rows for bucket in _as_list(row.get("rag_buckets"))),
        "graph_nodes": 0,
        "graph_edges": 0,
        "production_ranking_changed": False,
        "source_truth_mutation_allowed": False,
    }
    graph_nodes, graph_edges = _build_graph(rows, summary)
    summary["graph_nodes"] = len(graph_nodes)
    summary["graph_edges"] = len(graph_edges)
    payload = {"summary": summary, "results": rows}
    _write_json(paths.simulation, payload)
    _write_jsonl(paths.simulation_jsonl, rows)
    _write_json(paths.summary, summary)
    _write_json(paths.graph_nodes, graph_nodes)
    _write_json(paths.graph_edges, graph_edges)
    _write_text(paths.review_md, _render_markdown(summary, rows))
    _write_text(paths.review_html, _render_html(summary, rows))
    if options.open_report:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return {"summary": summary, "results": rows, "graph_nodes": graph_nodes, "graph_edges": graph_edges}


# ---------------------------------------------------------------------------
# Graph/report
# ---------------------------------------------------------------------------


def _build_graph(rows: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def node(node_id: str, node_type: str, **attrs: Any) -> None:
        if not node_id:
            return
        current = nodes.setdefault(node_id, {"id": node_id, "type": node_type})
        current.update({k: v for k, v in attrs.items() if v not in (None, "", [])})

    root = "trace_net:weighted_search_simulation"
    qnode = f"query:{summary.get('query_fingerprint')}"
    pnode = f"weights_policy:{summary.get('weights_policy_version')}"
    node(root, "weighted_search_simulation", version=VERSION)
    node(qnode, "query_fingerprint", label=summary.get("query_fingerprint"))
    node(pnode, "weights_policy", version=summary.get("weights_policy_version"))
    edges.append({"source": root, "target": qnode, "type": "SIMULATES_QUERY"})
    edges.append({"source": root, "target": pnode, "type": "USES_WEIGHTS_POLICY"})
    for row in rows:
        gid = _text(row.get("group_id")) or f"search_group:{_slug(row.get('page_id'))}"
        page = _text(row.get("page_id"))
        node(gid, "weighted_search_group", page_id=page, weighted_score=row.get("weighted_score"), weighted_rank=row.get("weighted_rank"), original_rank=row.get("original_rank"))
        node(page, "page")
        edges.append({"source": root, "target": gid, "type": "HAS_WEIGHTED_GROUP"})
        edges.append({"source": gid, "target": page, "type": "RANKS_PAGE"})
        for bucket in _as_list(row.get("rag_buckets")):
            bid = f"rag_bucket:{bucket}"
            node(bid, "rag_bucket")
            edges.append({"source": gid, "target": bid, "type": "HAS_BUCKET"})
        comps = _as_dict(row.get("weighted_score_components"))
        for signal in _as_list(comps.get("feedback_signals_used")):
            if isinstance(signal, Mapping):
                sid = _text(signal.get("signal_id")) or f"feedback_signal:{_slug(page)}:{_slug(signal.get('recommendation'))}"
                node(sid, "feedback_policy_signal", recommendation=signal.get("recommendation"), contribution=signal.get("raw_contribution"))
                edges.append({"source": gid, "target": sid, "type": "ADJUSTED_BY_FEEDBACK"})
    return list(nodes.values()), edges


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_text(cell).replace("\n", "<br>") for cell in row) + " |")
    return "\n".join(lines)


def _render_markdown(summary: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# TRACE-Net Weighted Search Simulation v1",
        "",
        f"Status: **{summary.get('status', 'UNKNOWN')}**  Version: `{summary.get('version', VERSION)}`",
        "",
        "## Summary",
        "",
        _md_table(
            ["Metric", "Value"],
            [[key, summary.get(key)] for key in (
                "query_fingerprint",
                "weights_policy_version",
                "grouped_input_records",
                "weighted_group_records",
                "feedback_enabled",
                "matching_feedback_signal_records",
                "feedback_signals_used",
                "groups_with_feedback_adjustment",
                "rank_changed_records",
                "unsafe_weighted_records",
                "excluded_weighted_records",
                "source_truth_mutation_records",
                "context_warning_signals_used",
                "top_page_before",
                "top_page_after",
            )],
        ),
        "",
        "## Weighted ranking",
        "",
    ]
    ranking_rows = []
    for row in rows:
        comps = _as_dict(row.get("weighted_score_components"))
        ranking_rows.append([
            row.get("weighted_rank"),
            row.get("original_rank"),
            row.get("page_id"),
            row.get("weighted_score"),
            comps.get("current_group_score"),
            comps.get("bucket_bonus"),
            comps.get("evidence_diversity_bonus"),
            comps.get("exact_match_bonus"),
            comps.get("confidence_bonus"),
            comps.get("feedback_adjustment"),
            ", ".join(_as_list(row.get("rag_buckets"))),
        ])
    lines.append(_md_table(["Weighted rank", "Original rank", "Page", "Weighted score", "Current group", "Bucket", "Diversity", "Exact", "Confidence", "Feedback", "Buckets"], ranking_rows))
    lines.append("")
    lines.append("## Feedback adjustments")
    lines.append("")
    adjustment_rows = []
    for row in rows:
        comps = _as_dict(row.get("weighted_score_components"))
        if abs(_num(comps.get("feedback_adjustment"))) <= 0.000001:
            continue
        reasons = []
        for signal in _as_list(comps.get("feedback_signals_used")):
            if isinstance(signal, Mapping):
                reasons.append(f"{signal.get('recommendation')} {signal.get('raw_contribution')}")
        adjustment_rows.append([row.get("page_id"), comps.get("feedback_adjustment"), "; ".join(reasons)])
    lines.append(_md_table(["Page", "Feedback adjustment", "Signals"], adjustment_rows or [["None", "0", "No validated feedback signals applied"]]))
    return "\n".join(lines) + "\n"


def _render_html(summary: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    md = _render_markdown(summary, rows)
    return """<!doctype html><html><head><meta charset=\"utf-8\"><title>TRACE-Net Weighted Search Simulation</title>
<style>body{font-family:Arial,sans-serif;margin:24px;line-height:1.4}table{border-collapse:collapse;width:100%;margin:12px 0}td,th{border:1px solid #ddd;padding:6px;vertical-align:top}th{background:#f3f3f3}pre{white-space:pre-wrap;background:#f7f7f7;padding:12px}</style></head><body><pre>""" + html.escape(md) + "</pre></body></html>"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate TRACE-Net weighted search ranking using the official weights policy.")
    parser.add_argument("--search-dir", type=Path, default=DEFAULT_SEARCH_DIR)
    parser.add_argument("--weights-dir", type=Path, default=DEFAULT_WEIGHTS_DIR)
    parser.add_argument("--feedback-dir", type=Path, default=DEFAULT_FEEDBACK_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--grouped-results", type=Path, default=None)
    parser.add_argument("--grouped-summary", type=Path, default=None)
    parser.add_argument("--search-summary", type=Path, default=None)
    parser.add_argument("--weights-policy", type=Path, default=None)
    parser.add_argument("--feedback-signals", type=Path, default=None)
    parser.add_argument("--query", default="")
    parser.add_argument("--part-number", default="")
    parser.add_argument("--page-id", default="")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--no-feedback", action="store_true", help="Ignore feedback signals and simulate weights only.")
    parser.add_argument("--open", action="store_true", dest="open_report")
    args = parser.parse_args(argv)
    paths = WeightedSearchSimulationPaths(
        search_dir=args.search_dir,
        weights_dir=args.weights_dir,
        feedback_dir=args.feedback_dir,
        output_dir=args.output_dir,
        grouped_results_path=args.grouped_results,
        grouped_summary_path=args.grouped_summary,
        search_summary_path=args.search_summary,
        weights_policy_path=args.weights_policy,
        feedback_signals_path=args.feedback_signals,
    )
    options = WeightedSearchSimulationOptions(
        query=args.query,
        part_number=args.part_number,
        page_id=args.page_id,
        top_k=args.top_k,
        use_feedback=not args.no_feedback,
        open_report=args.open_report,
    )
    result = simulate_weighted_search(paths, options)
    summary = result["summary"]
    print("TRACE-Net weighted search simulation")
    print(f"  Status: {summary.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in [
        "query_fingerprint",
        "weights_policy_version",
        "grouped_input_records",
        "weighted_group_records",
        "feedback_enabled",
        "matching_feedback_signal_records",
        "feedback_signals_used",
        "groups_with_feedback_adjustment",
        "rank_changed_records",
        "unsafe_weighted_records",
        "excluded_weighted_records",
        "source_truth_mutation_records",
        "context_warning_signals_used",
        "top_page_before",
        "top_page_after",
    ]:
        print(f"    {key}: {summary.get(key)}")
    print("  Top weighted results:")
    for row in result["results"][:10]:
        comps = _as_dict(row.get("weighted_score_components"))
        print(f"    {row.get('weighted_rank')}. score={row.get('weighted_score')} page={row.get('page_id')} original_rank={row.get('original_rank')} feedback={comps.get('feedback_adjustment')} buckets={','.join(_as_list(row.get('rag_buckets')))}")
    print("Files written:")
    print(f"  simulation: {paths.simulation}")
    print(f"  simulation_jsonl: {paths.simulation_jsonl}")
    print(f"  summary: {paths.summary}")
    print(f"  review_html: {paths.review_html}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    return 0 if summary.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
