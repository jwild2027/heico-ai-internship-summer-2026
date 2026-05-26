"""tools/interactive_test.py — Interactive RAG test runner.

The user types questions, the system answers from the RAG pipeline,
and the user marks each answer pass/fail with optional notes.
Results are saved to a JSON file for regression comparison.

Usage:
    python tools/interactive_test.py
    python tools/interactive_test.py --out results/session_001.json
    python tools/interactive_test.py --top-k 8 --source "NIST-SP-800-53r5"
    python tools/interactive_test.py --replay results/session_001.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.langchain_adapter import ask

DEFAULT_OUT_DIR = Path("results")
SEPARATOR       = "─" * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _print_answer(result: dict, query: str, idx: int) -> None:
    print(f"\n{'═' * 60}")
    print(f"  Q{idx}: {query}")
    print(SEPARATOR)
    print(f"  Answer:\n")
    # Word-wrap at 72 chars
    words = result["answer"].split()
    line  = "  "
    for word in words:
        if len(line) + len(word) + 1 > 74:
            print(line)
            line = "  " + word
        else:
            line += (" " if line != "  " else "") + word
    if line.strip():
        print(line)
    print()

    if result["citations"]:
        print(f"  Sources:")
        for c in result["citations"]:
            src  = c.get("source", "unknown")
            p    = c.get("page_start", "?")
            p2   = c.get("page_end", p)
            dist = c.get("distance")
            page_str = f"p{p}" if p == p2 else f"p{p}-p{p2}"
            dist_str = f"  dist={dist:.4f}" if dist is not None else ""
            title = c.get("title", "")
            title_str = f"  [{title}]" if title else ""
            print(f"    {src} {page_str}{title_str}{dist_str}")

    grounded = result.get("grounded", False)
    latency  = result.get("latency_ms", 0)
    print(f"\n  Grounded: {'✓' if grounded else '✗'}  |  Latency: {latency:.0f}ms")
    print(SEPARATOR)


def _get_grade() -> tuple[str, str]:
    """Prompt user for pass/fail/skip and optional notes."""
    while True:
        raw = input("  Grade [p=pass / f=fail / s=skip / q=quit]: ").strip().lower()
        if raw in ("p", "pass"):
            grade = "pass"
            break
        elif raw in ("f", "fail"):
            grade = "fail"
            break
        elif raw in ("s", "skip"):
            grade = "skip"
            break
        elif raw in ("q", "quit", "exit"):
            grade = "quit"
            break
        else:
            print("  Enter p, f, s, or q.")

    notes = ""
    if grade in ("pass", "fail"):
        notes = input("  Notes (optional, press Enter to skip): ").strip()

    return grade, notes


def run_interactive(
    *,
    out_path: Path | None,
    top_k: int,
    source_filter: str | None,
    llm_model: str,
    embed_model: str,
    persist_dir: Path,
    collection_name: str,
) -> None:
    session = {
        "session_id":  _now_iso(),
        "llm_model":   llm_model,
        "embed_model": embed_model,
        "top_k":       top_k,
        "source_filter": source_filter,
        "cases":       [],
    }

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║           Interactive RAG Test Session                   ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print("║  Type a question → system answers → you grade it.       ║")
    print("║  Commands: 'done' to finish, 'quit' to exit without save ║")
    print("╚══════════════════════════════════════════════════════════╝")
    if source_filter:
        print(f"  Filtering citations to source: {source_filter}")
    print()

    idx = 0
    while True:
        try:
            query = input(f"  Question {idx+1} (or 'done'): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Interrupted.")
            break

        if not query:
            continue
        if query.lower() in ("done", "exit"):
            break
        if query.lower() == "quit":
            print("  Exiting without saving.")
            return

        idx += 1
        print(f"\n  Querying RAG pipeline...")
        t0 = time.perf_counter()

        try:
            result = ask(
                query,
                llm_model=llm_model,
                embed_model=embed_model,
                persist_dir=persist_dir,
                collection_name=collection_name,
                top_k=top_k,
            )
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            result = {
                "answer": f"ERROR: {exc}",
                "citations": [],
                "grounded": False,
                "latency_ms": (time.perf_counter() - t0) * 1000,
            }

        _print_answer(result, query, idx)
        grade, notes = _get_grade()

        if grade == "quit":
            break

        session["cases"].append({
            "idx":       idx,
            "query":     query,
            "answer":    result["answer"],
            "citations": result["citations"],
            "grounded":  result.get("grounded", False),
            "latency_ms":result.get("latency_ms", 0),
            "grade":     grade,
            "notes":     notes,
            "timestamp": _now_iso(),
        })

        # Running score
        graded   = [c for c in session["cases"] if c["grade"] != "skip"]
        passed   = sum(1 for c in graded if c["grade"] == "pass")
        if graded:
            print(f"\n  Running score: {passed}/{len(graded)} passed "
                  f"({passed/len(graded)*100:.0f}%)")
        print()

    # Save results
    if session["cases"] and out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(session, indent=2), encoding="utf-8"
        )
        print(f"\n  Session saved to {out_path}")

    # Final summary
    graded = [c for c in session["cases"] if c["grade"] != "skip"]
    passed = sum(1 for c in graded if c["grade"] == "pass")
    failed = sum(1 for c in graded if c["grade"] == "fail")
    skipped = sum(1 for c in session["cases"] if c["grade"] == "skip")

    print()
    print("═" * 60)
    print(f"  Session complete: {len(session['cases'])} questions asked")
    print(f"  Passed: {passed}  |  Failed: {failed}  |  Skipped: {skipped}")
    if graded:
        print(f"  Score:  {passed}/{len(graded)} ({passed/len(graded)*100:.0f}%)")
    print("═" * 60)


def replay_session(session_path: Path) -> None:
    """Print a saved session's questions, answers, and grades."""
    data = json.loads(session_path.read_text(encoding="utf-8"))
    print(f"\nReplaying session: {session_path.name}")
    print(f"Date: {data.get('session_id')}  |  Model: {data.get('llm_model')}")
    print()
    for case in data["cases"]:
        grade_sym = "✓" if case["grade"] == "pass" else ("✗" if case["grade"] == "fail" else "−")
        print(f"  [{grade_sym}] Q{case['idx']}: {case['query']}")
        if case["notes"]:
            print(f"       Note: {case['notes']}")
    graded  = [c for c in data["cases"] if c["grade"] != "skip"]
    passed  = sum(1 for c in graded if c["grade"] == "pass")
    print(f"\n  Score: {passed}/{len(graded)}")


def parse_args() -> argparse.Namespace:
    import tools.pymupdf_bge_chroma_cli as base
    from tools.langchain_adapter import (
        DEFAULT_LLM_MODEL, DEFAULT_EMBED_MODEL,
        DEFAULT_COLLECTION, DEFAULT_PERSIST_DIR, DEFAULT_TOP_K,
    )

    parser = argparse.ArgumentParser(
        description="Interactive RAG test session with user grading."
    )
    parser.add_argument("--out",        type=Path,
                        default=DEFAULT_OUT_DIR / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        help="Path to save session JSON (default: results/session_<timestamp>.json)")
    parser.add_argument("--top-k",      type=int,   default=DEFAULT_TOP_K)
    parser.add_argument("--source",     default=None,
                        help="Filter display to citations from this source doc stem (e.g. NIST-SP-800-53r5)")
    parser.add_argument("--llm-model",  default=DEFAULT_LLM_MODEL)
    parser.add_argument("--embed-model",default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--persist-dir",type=Path,  default=DEFAULT_PERSIST_DIR)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--replay",     type=Path,  default=None,
                        help="Replay a saved session JSON instead of running live.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.replay:
        if not args.replay.exists():
            print(f"[error] Session file not found: {args.replay}")
            sys.exit(1)
        replay_session(args.replay)
        return

    run_interactive(
        out_path=args.out,
        top_k=args.top_k,
        source_filter=args.source,
        llm_model=args.llm_model,
        embed_model=args.embed_model,
        persist_dir=args.persist_dir,
        collection_name=args.collection,
    )


if __name__ == "__main__":
    main()