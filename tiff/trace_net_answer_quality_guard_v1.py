"""Deterministic semantic quality checks for TRACE-Net user answers."""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

PREFIX_RE = re.compile(
    r"\b(?:starts?|begins?)\s+(?:with\s+)?([A-Z0-9][A-Z0-9.-]{1,15})",
    re.I,
)
PARTISH_RE = re.compile(r"\b[A-Z0-9][A-Z0-9.-]{3,24}\b", re.I)
REVISION_RE = re.compile(r"^(?:REV(?:ISION)?)[.\s_-]*\d+[A-Z]?$", re.I)
NOISE = (
    re.compile(r"^\d+\.\d+[A-Z]?$", re.I),
    re.compile(r"^\d{5,}[A-F]-\d{2}$", re.I),
    re.compile(r"^[N]\d{2,3}-\d{4,6}(?:-\d{3})?$", re.I),
    re.compile(r"^\d+E[+-]?\d+$", re.I),
)


def normalize_token(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def requested_prefix(query: str) -> str:
    match = PREFIX_RE.search(str(query or ""))
    return normalize_token(match.group(1)) if match else ""


def is_revision_metadata(value: str) -> bool:
    return bool(REVISION_RE.fullmatch(str(value or "").strip(" `*,:;()[]{}")))


def is_noise_candidate(value: str) -> bool:
    raw = str(value or "").strip(" `*,:;()[]{}")
    norm = normalize_token(raw)
    return (
        not raw
        or is_revision_metadata(raw)
        or any(pattern.fullmatch(raw) for pattern in NOISE)
        or len(norm) < 4
        or sum(char.isdigit() for char in norm) < 2
        or raw.upper() in {"25-IPL", "PER", "STOCK", "UNKNOWN"}
    )


def extract_candidate_tokens(answer: str) -> list[str]:
    output = []
    for token in PARTISH_RE.findall(str(answer or "")):
        token = token.strip(".,:;")
        if re.fullmatch(r"\d{2}-\d{2}-\d{2}", token):
            continue
        if is_revision_metadata(token):
            continue
        if any(char.isdigit() for char in token):
            output.append(token)
    return output


def normalize_followup_text(value: str) -> str:
    """Normalize presentation punctuation without collapsing distinct questions."""
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def duplicate_followup_count(answer: str, followups: Sequence[str]) -> int:
    """Count only full follow-up questions that appear more than once.

    Shared words across different questions are expected and are not duplicates.
    """
    normalized_answer = normalize_followup_text(answer)
    duplicated = 0
    seen = set()
    for raw in followups:
        normalized_question = normalize_followup_text(raw)
        if not normalized_question or normalized_question in seen:
            continue
        seen.add(normalized_question)
        if normalized_answer.count(normalized_question) > 1:
            duplicated += 1
    return duplicated


def evaluate_answer_quality(
    *,
    query: str,
    answer: str,
    trace: Mapping[str, Any],
) -> list[str]:
    failures = []
    prefix = requested_prefix(query)
    candidates = extract_candidate_tokens(answer)
    route = str(trace.get("route") or "")
    if prefix and route in {"guided_discovery", "guided_part_discovery"}:
        actual = [
            normalize_token(candidate)
            for candidate in candidates
            if not is_noise_candidate(candidate)
        ]
        bad = [
            candidate
            for candidate in actual
            if candidate and not candidate.startswith(prefix)
        ]
        if (
            bad
            and "no source-traceable" not in answer.lower()
            and "no exact" not in answer.lower()
        ):
            failures.append(
                "strict_prefix_candidate_mismatch:" + ",".join(bad[:5])
            )
    noisy = [
        candidate
        for candidate in candidates
        if is_noise_candidate(candidate)
    ]
    if noisy:
        failures.append(
            "user_visible_noise_candidates:" + ",".join(noisy[:5])
        )
    duplicate_count = duplicate_followup_count(
        answer,
        list(trace.get("follow_up_questions") or []),
    )
    if duplicate_count:
        failures.append(f"duplicate_followup_topics:{duplicate_count}")
    return failures
