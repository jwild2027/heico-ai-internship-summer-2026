"""tools/citation_checker.py — Post-process RAG answers to verify every claim
has a verifiable source in the retrieved chunks.

For each sentence in the answer:
  1. Check if it is a factual claim (skip filler, hedges, transitions)
  2. Try to match it against the retrieved chunks via exact substring,
     normalized overlap, and soft token overlap
  3. Flag unverifiable claims
  4. If too many claims are unverifiable → refuse the answer entirely

Usage (standalone):
    python tools/citation_checker.py --query "What are sponsons?"

Usage (Python):
    from tools.citation_checker import check_answer, CheckedAnswer
    from tools.langchain_adapter import ask

    result  = ask("What are sponsons?")
    checked = check_answer(result["answer"], result["chunks"])
    if checked.verified:
        print(checked.annotated_answer)
    else:
        print("REFUSED:", checked.refusal_reason)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ClaimVerdict:
    sentence: str
    is_claim: bool          # False = filler/transition, skip verification
    verified: bool          # True = found support in chunks
    support_page: str       # e.g. "p5" or "p5-p6"
    support_snippet: str    # the matching text from the chunk
    match_type: str         # "exact" | "overlap" | "soft" | "none"
    overlap_score: float    # 0.0–1.0


@dataclass
class CheckedAnswer:
    original_answer: str
    verified: bool                          # overall pass/fail
    annotated_answer: str                   # answer with [UNVERIFIED] tags
    verdicts: list[ClaimVerdict]
    verified_count: int
    claim_count: int
    refusal_reason: str = ""
    verification_rate: float = 0.0


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving citation tags like [p5]."""
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Split on . ! ? followed by space+capital or end of string
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", text)
    sentences = []
    for part in parts:
        part = part.strip()
        if part:
            sentences.append(part)
    return sentences


# ---------------------------------------------------------------------------
# Claim detection — is this sentence a factual assertion?
# ---------------------------------------------------------------------------

FILLER_PATTERNS = [
    r"^(according to|based on|as (stated|mentioned|noted|described|shown|indicated))",
    r"^(in (summary|conclusion|general|other words|addition|particular))",
    r"^(this (means|shows|indicates|suggests|demonstrates))",
    r"^(note that|please note|it (is|was|should be) (worth|important|noted))",
    r"^(i don'?t have|i (cannot|can'?t)|there (is|are) no|no information)",
    r"^\[p\d",        # pure citation marker
    r"^(yes|no|okay|sure|certainly|absolutely)",
]

FILLER_RE = re.compile("|".join(FILLER_PATTERNS), re.IGNORECASE)


def is_factual_claim(sentence: str) -> bool:
    """Return True if the sentence makes a verifiable factual claim."""
    s = sentence.strip()
    if len(s.split()) < 5:
        return False
    if FILLER_RE.match(s):
        return False
    # Sentences ending in ? are questions not claims
    if s.endswith("?"):
        return False
    return True


# ---------------------------------------------------------------------------
# Text normalization for matching
# ---------------------------------------------------------------------------

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "they", "their", "also", "as", "when",
    "which", "who", "what", "where", "how", "if", "not", "no", "so",
}


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"\[p[\d\-]+\]", "", text)   # strip inline citations
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def content_tokens(text: str) -> set[str]:
    """Return meaningful (non-stopword) tokens from text."""
    return {w for w in normalize(text).split() if w not in STOPWORDS and len(w) > 2}


# ---------------------------------------------------------------------------
# Matching strategies
# ---------------------------------------------------------------------------

def try_exact_match(claim: str, chunk_text: str) -> tuple[bool, str]:
    """Check if a 6+ word substring of the claim appears verbatim in the chunk."""
    words = normalize(claim).split()
    chunk_norm = normalize(chunk_text)
    # Try progressively shorter windows
    for window in range(min(len(words), 10), 5, -1):
        for start in range(len(words) - window + 1):
            phrase = " ".join(words[start: start + window])
            if phrase in chunk_norm:
                return True, phrase
    return False, ""


def overlap_score(claim: str, chunk_text: str) -> float:
    """Fraction of claim's content tokens found in chunk."""
    claim_tokens = content_tokens(claim)
    if not claim_tokens:
        return 0.0
    chunk_tokens = content_tokens(chunk_text)
    hits = claim_tokens & chunk_tokens
    return len(hits) / len(claim_tokens)


def soft_match(claim: str, chunk_text: str, threshold: float = 0.55) -> tuple[bool, float]:
    """Return (matched, score) using token overlap with a threshold."""
    score = overlap_score(claim, chunk_text)
    return score >= threshold, score


# ---------------------------------------------------------------------------
# Core verification
# ---------------------------------------------------------------------------

def verify_claim(
    sentence: str,
    chunks: list[dict[str, Any]],
) -> ClaimVerdict:
    """Try to find support for a claim sentence in the retrieved chunks."""
    best_exact   = (False, "")
    best_soft    = (False, 0.0)
    best_page    = ""
    best_snippet = ""
    best_type    = "none"
    best_score   = 0.0

    for chunk in chunks:
        doc  = chunk.get("document", "")
        meta = chunk.get("metadata", {})
        page_start = meta.get("page_start", "?")
        page_end   = meta.get("page_end", page_start)
        page_label = (
            f"p{page_start}" if page_start == page_end
            else f"p{page_start}-p{page_end}"
        )

        # Strategy 1: exact substring
        found, snippet = try_exact_match(sentence, doc)
        if found:
            return ClaimVerdict(
                sentence=sentence,
                is_claim=True,
                verified=True,
                support_page=page_label,
                support_snippet=snippet,
                match_type="exact",
                overlap_score=1.0,
            )

        # Strategy 2: soft token overlap
        matched, score = soft_match(sentence, doc)
        if score > best_score:
            best_score   = score
            best_soft    = (matched, score)
            best_page    = page_label
            best_snippet = doc[:120].replace("\n", " ")
            best_type    = "soft" if matched else "none"

    verified = best_soft[0]
    return ClaimVerdict(
        sentence=sentence,
        is_claim=True,
        verified=verified,
        support_page=best_page if verified else "",
        support_snippet=best_snippet if verified else "",
        match_type=best_type,
        overlap_score=round(best_score, 3),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_answer(
    answer: str,
    chunks: list[dict[str, Any]],
    *,
    refusal_threshold: float = 0.40,   # refuse if < 40% of claims verified
    min_claims_to_check: int = 1,
) -> CheckedAnswer:
    """Post-process a RAG answer — verify every claim against retrieved chunks.

    Args:
        answer:             The LLM-generated answer string.
        chunks:             Retrieved chunk dicts from ask() (each has
                            "document" and "metadata" keys).
        refusal_threshold:  If verified_rate < this, refuse the answer.
        min_claims_to_check: Minimum factual claims before applying threshold.

    Returns:
        CheckedAnswer with annotated text and overall pass/fail verdict.
    """
    sentences = split_sentences(answer)
    verdicts: list[ClaimVerdict] = []

    for sentence in sentences:
        if not is_factual_claim(sentence):
            verdicts.append(ClaimVerdict(
                sentence=sentence,
                is_claim=False,
                verified=True,           # non-claims pass trivially
                support_page="",
                support_snippet="",
                match_type="n/a",
                overlap_score=0.0,
            ))
            continue

        verdict = verify_claim(sentence, chunks)
        verdicts.append(verdict)

    # Count only actual claims
    claim_verdicts = [v for v in verdicts if v.is_claim]
    claim_count    = len(claim_verdicts)
    verified_count = sum(1 for v in claim_verdicts if v.verified)
    verification_rate = (
        verified_count / claim_count if claim_count >= min_claims_to_check
        else 1.0
    )

    # Build annotated answer
    annotated_parts = []
    for v in verdicts:
        if not v.is_claim or v.verified:
            # Append sentence as-is (add page tag if verified claim)
            if v.is_claim and v.verified and v.support_page:
                # Strip any existing citation tags then re-add clean one
                clean = re.sub(r"\s*\[p[\d\-]+\]", "", v.sentence).strip()
                annotated_parts.append(f"{clean} [{v.support_page}]")
            else:
                annotated_parts.append(v.sentence)
        else:
            annotated_parts.append(f"{v.sentence} [UNVERIFIED]")

    annotated_answer = " ".join(annotated_parts)

    # Decide overall verdict
    overall_verified = verification_rate >= refusal_threshold
    refusal_reason = ""
    if not overall_verified:
        unverified = [v.sentence for v in claim_verdicts if not v.verified]
        refusal_reason = (
            f"Answer refused: {verified_count}/{claim_count} claims verified "
            f"({verification_rate:.0%}). "
            f"Unverifiable: {unverified[:2]}"
        )

    return CheckedAnswer(
        original_answer=answer,
        verified=overall_verified,
        annotated_answer=annotated_answer,
        verdicts=verdicts,
        verified_count=verified_count,
        claim_count=claim_count,
        refusal_reason=refusal_reason,
        verification_rate=round(verification_rate, 3),
    )


def format_checked_answer(checked: CheckedAnswer, *, verbose: bool = False) -> str:
    """Pretty-print a CheckedAnswer for CLI or Streamlit display."""
    lines = []

    if not checked.verified:
        lines.append(f"⛔ REFUSED — {checked.refusal_reason}")
        lines.append("")

    lines.append(checked.annotated_answer)
    lines.append("")
    lines.append(
        f"Verification: {checked.verified_count}/{checked.claim_count} claims "
        f"verified ({checked.verification_rate:.0%})"
    )

    if verbose:
        lines.append("")
        lines.append("--- Claim details ---")
        for v in checked.verdicts:
            if not v.is_claim:
                continue
            status = "✓" if v.verified else "✗"
            lines.append(
                f"{status} [{v.match_type} score={v.overlap_score}] "
                f"{v.support_page or 'no source'}"
            )
            lines.append(f"  CLAIM:   {v.sentence[:120]}")
            if v.support_snippet:
                lines.append(f"  SUPPORT: {v.support_snippet[:120]}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify RAG answer claims against retrieved chunks."
    )
    parser.add_argument("--query", required=True, help="Query to ask and verify.")
    parser.add_argument("--llm-model",   default="gemma3:4b")
    parser.add_argument("--embed-model", default="bge-large")
    parser.add_argument("--top-k",       type=int, default=6)
    parser.add_argument("--threshold",   type=float, default=0.40,
                        help="Min verified claim rate before refusing (0.0-1.0)")
    parser.add_argument("--verbose",     action="store_true",
                        help="Show per-claim match details.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from src.rag.langchain_adapter import ask

    print(f"Query: {args.query}\n")
    print("Retrieving and generating answer...")
    result = ask(
        args.query,
        llm_model=args.llm_model,
        embed_model=args.embed_model,
        top_k=args.top_k,
    )

    print(f"Raw answer:\n{result['answer']}\n")
    print("Verifying claims...\n")

    checked = check_answer(
        result["answer"],
        result["chunks"],
        refusal_threshold=args.threshold,
    )

    print(format_checked_answer(checked, verbose=args.verbose))


if __name__ == "__main__":
    main()