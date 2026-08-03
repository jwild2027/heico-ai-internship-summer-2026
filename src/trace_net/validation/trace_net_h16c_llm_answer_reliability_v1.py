"""TRACE-Net H16C LLM answer reliability helpers.

This module is intentionally source-truth safe: it only classifies answer text
shape and prepares local Ollama generation options. It does not mutate source
truth, does not write to Postgres/Qdrant/OpenSearch, and does not grant answer
permission.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

MODULE = "trace_net_h16c_llm_answer_reliability_v1"
VERSION = "v1"

DEFAULT_OLLAMA_NUM_PREDICT = 900
DEFAULT_OLLAMA_TEMPERATURE = 0.1

_INCOMPLETE_TAILS = (
    " which allows the system to",
    " which allows trace-net to",
    " allows the system to",
    " can then carry this ocr-backed",
    " this ocr-backed",
    " ocr-backed",
    " because",
    " and",
    " or",
    " to",
    " with",
    " while",
    " that",
    " which",
    ",",
    ":",
    ";",
    "-",
)

_REQUIRED_SECTIONS = (
    "answer",
    "evidence",
    "engineering confidence",
    "limits",
)


def build_h16c_ollama_options(
    *,
    num_predict: int = DEFAULT_OLLAMA_NUM_PREDICT,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
) -> Dict[str, Any]:
    """Return deterministic-ish Ollama options for complete smoke answers."""

    return {
        "num_predict": int(num_predict),
        "temperature": float(temperature),
    }


def merge_h16c_ollama_options(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Merge H16C defaults into an Ollama /api/generate payload.

    Existing caller-provided options are preserved. Missing options get safe
    defaults that help avoid mid-sentence truncation in local Gemma/Ollama runs.
    """

    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    options = payload.setdefault("options", {})
    if not isinstance(options, dict):
        options = {}
        payload["options"] = options
    options.setdefault("num_predict", DEFAULT_OLLAMA_NUM_PREDICT)
    options.setdefault("temperature", DEFAULT_OLLAMA_TEMPERATURE)
    return payload


def _normalize_answer_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def looks_incomplete_llm_answer(
    text: str,
    *,
    require_sections: bool = True,
    min_chars: int = 350,
) -> bool:
    """Return True when an LLM answer looks truncated or structurally incomplete.

    The detector is intentionally conservative and is meant to trigger retry,
    not to grade or approve an answer. It catches the H16B q18 failure pattern:
    the answer stopped at tails such as "which allows the system to" or
    "OCR-backed" before Evidence / Engineering confidence / Limits sections.
    """

    raw = (text or "").strip()
    if not raw:
        return True

    normalized = _normalize_answer_text(raw)
    lowered = normalized.lower()

    if len(normalized) < int(min_chars):
        return True

    tail = lowered[-160:].rstrip()
    if tail.endswith(_INCOMPLETE_TAILS):
        return True

    if require_sections:
        missing = [section for section in _REQUIRED_SECTIONS if section not in lowered]
        if missing:
            return True

    return False


def filter_question_records(records: Iterable[Dict[str, Any]], question_ids: Iterable[str]) -> List[Dict[str, Any]]:
    """Filter JSONL question-bank records by question_id while preserving order."""

    wanted = [str(q).strip() for q in question_ids if str(q).strip()]
    wanted_set = set(wanted)
    out: List[Dict[str, Any]] = []
    seen = set()
    for record in records:
        qid = str(record.get("question_id", "")).strip()
        if qid in wanted_set:
            out.append(record)
            seen.add(qid)
    missing = [qid for qid in wanted if qid not in seen]
    if missing:
        raise ValueError("missing question_id(s): " + ", ".join(missing))
    return out


def safety_contract_summary() -> Dict[str, Any]:
    """Machine-readable safety contract for H16C helper behavior."""

    return {
        "module": MODULE,
        "version": VERSION,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "proof_role": "generation_reliability_only_guidance_not_source_proof",
    }
