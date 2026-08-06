"""TRACE-Net H16D conservative LLM reliability helpers.

H16C correctly exposed the need to handle truncated local-LLM output, but the
first incomplete-answer detector was too aggressive: normal answers missing a
preferred section could be treated as failures, pushing the full smoke into
retry/fallback paths.

H16D keeps only conservative signals for genuine generation failures. It does
not grade answers and does not grant answer permission. It is guidance for the
smoke runner only.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

SAFETY_CONTRACT: Dict[str, Any] = {
    "module": "trace_net_h16d_llm_answer_reliability_v1",
    "version": "v1",
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
    "opensearch_upload_attempt": False,
    "source_truth_mutation_allowed": False,
    "answer_permission": False,
}

# These tails indicate the model stopped in the middle of a clause/token.
# This is intentionally narrow. Missing optional sections is not enough to call
# an answer incomplete; grading should decide quality after generation.
DANGLING_TAILS: Sequence[str] = (
    " which allows the system to",
    " which allows trace-net to",
    " allows the system to",
    " the nomenclature merger can then carry this ocr-backed",
    " can then carry this ocr-backed",
    " this ocr-backed",
    " ocr-backed",
    " source-trace-ready nomenclature",
    " because",
    " therefore",
    " while",
    " although",
    " which",
    " that",
    " with",
    " and",
    " or",
    " to",
    " for",
    " from",
    ",",
    ":",
    ";",
    "-",
    "(",
    "[",
)


def safety_contract_summary() -> Dict[str, Any]:
    """Return an explicit non-mutating safety contract."""
    return dict(SAFETY_CONTRACT)


def looks_truncated_llm_answer(text: Any, *, min_chars: int = 40) -> bool:
    """Return True only for strongly truncated or empty generations.

    Unlike H16C, this function does not require Evidence/Confidence/Limits
    sections. Those are quality preferences checked by the smoke grader, not
    low-level generation-failure signals.
    """
    if not isinstance(text, str):
        return False

    raw = text.strip()
    if not raw:
        return True

    compact = " ".join(raw.lower().split())
    if compact in {"answer", "answer:", "evidence", "evidence:"}:
        return True

    # Very short answers that start but do not identify/cite anything are likely
    # model cutoffs. Keep this threshold low to avoid H16C's over-triggering.
    if len(raw) < min_chars:
        return True

    tail = compact[-180:].rstrip()
    if any(tail.endswith(t) for t in DANGLING_TAILS):
        return True

    # A dangling citation opener means the generated answer stopped before a
    # parseable citation label completed.
    if tail.endswith("[") or tail.endswith("[") or tail.endswith("["):
        return True

    return False


# Backward-compatible name used by H16C patch attempts. Keep the signature loose
# so older calls cannot crash on non-string objects.
def looks_incomplete_llm_answer(text: Any, require_sections: bool = False, min_chars: int = 40) -> bool:
    return looks_truncated_llm_answer(text, min_chars=min(min_chars, 40))


def filter_question_records(records: Iterable[Dict[str, Any]], question_ids: Sequence[str]) -> List[Dict[str, Any]]:
    """Filter JSONL question records by question_id while preserving order."""
    wanted = {str(q).strip() for q in question_ids if str(q).strip()}
    if not wanted:
        return list(records)
    return [dict(r) for r in records if str(r.get("question_id", "")).strip() in wanted]
