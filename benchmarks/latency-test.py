"""Measure Ollama latency for 50 prompts and report p50/p95.

Default model: gemma3:4b

Examples:
  python latency-test.py
  python latency-test.py --model llama3.1:8b --count 50
  python latency-test.py --out latency-results.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from typing import Any

try:
    import ollama
except Exception as exc:  # pragma: no cover - import guard for local environments
    raise RuntimeError("Missing ollama Python package. Install it with: pip install ollama") from exc


MODEL = os.getenv("OLLAMA_LATENCY_MODEL", "phi3:mini")
SYSTEM_PROMPT = "You are a concise assistant. Answer in 1-2 short sentences."


def build_prompts(count: int) -> list[str]:
    """Return a deterministic list of simple prompts for benchmarking."""
    base_prompts = [
        "Explain what a database index does.",
        "What is the difference between precision and recall?",
        "Describe one way to reduce latency in a web app.",
        "What is a cache and why is it useful?",
        "Give one example of a good CLI command name.",
        "What is the purpose of a unit test?",
        "Explain why version control matters in teams.",
        "What is the benefit of structured logging?",
        "How would you explain a vector database to a beginner?",
        "What is one common cause of slow Python code?",
    ]

    if count <= len(base_prompts):
        return base_prompts[:count]

    prompts: list[str] = []
    while len(prompts) < count:
        for prompt in base_prompts:
            prompts.append(f"{prompt} (variation {len(prompts) + 1})")
            if len(prompts) >= count:
                break
    return prompts


def percentile(values: list[float], pct: float) -> float:
    """Compute a nearest-rank percentile from a sorted list of values."""
    if not values:
        raise ValueError("No values supplied")
    if pct <= 0:
        return values[0]
    if pct >= 100:
        return values[-1]
    rank = math.ceil((pct / 100.0) * len(values)) - 1
    rank = max(0, min(rank, len(values) - 1))
    return values[rank]


def call_model(model: str, prompt: str) -> dict[str, Any]:
    """Call Ollama once and measure wall-clock latency in milliseconds."""
    started = time.perf_counter()
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    message = response.get("message", {}) if isinstance(response, dict) else {}
    content = message.get("content") if isinstance(message, dict) else str(message)
    return {
        "prompt": prompt,
        "latency_ms": elapsed_ms,
        "response": content,
        "raw": response,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Ollama latency over 50 prompts.")
    parser.add_argument("--model", default=MODEL, help="Ollama model name, e.g. phi3:mini")
    parser.add_argument("--count", type=int, default=50, help="Number of prompts to run")
    parser.add_argument("--out", type=Path, help="Optional JSON output path")
    parser.add_argument("--show-prompts", action="store_true", help="Print each prompt and response")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prompts = build_prompts(args.count)

    print(f"Model: {args.model}")
    print(f"Prompts: {len(prompts)}")
    print("Running sequential requests so the timings reflect individual latency...\n")

    results: list[dict[str, Any]] = []
    latencies: list[float] = []

    for index, prompt in enumerate(prompts, start=1):
        try:
            result = call_model(args.model, prompt)
        except Exception as exc:
            result = {
                "prompt": prompt,
                "error": str(exc),
            }
        results.append(result)

        if "error" in result:
            print(f"[{index:02d}] ERROR: {result['error']}")
            continue

        latency_ms = float(result["latency_ms"])
        latencies.append(latency_ms)
        print(f"[{index:02d}] {latency_ms:8.1f} ms")
        if args.show_prompts:
            response = str(result.get("response") or "")
            preview = response[:180] + ("..." if len(response) > 180 else "")
            print(f"     prompt: {prompt}")
            print(f"     answer: {preview}")

    if not latencies:
        print("\nNo successful responses, so no latency stats were computed.")
        if args.out:
            args.out.write_text(json.dumps({"model": args.model, "results": results}, indent=2), encoding="utf-8")
        return 1

    latencies_sorted = sorted(latencies)
    p50 = percentile(latencies_sorted, 50)
    p95 = percentile(latencies_sorted, 95)
    average = sum(latencies_sorted) / len(latencies_sorted)
    minimum = latencies_sorted[0]
    maximum = latencies_sorted[-1]

    print("\nLatency summary")
    print(f"  count:   {len(latencies_sorted)}")
    print(f"  min:     {minimum:.1f} ms")
    print(f"  p50:     {p50:.1f} ms")
    print(f"  p95:     {p95:.1f} ms")
    print(f"  avg:     {average:.1f} ms")
    print(f"  max:     {maximum:.1f} ms")

    if args.out:
        payload = {
            "model": args.model,
            "count": len(prompts),
            "successful": len(latencies_sorted),
            "latencies_ms": latencies_sorted,
            "summary": {
                "min": minimum,
                "p50": p50,
                "p95": p95,
                "avg": average,
                "max": maximum,
            },
            "results": results,
        }
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved results to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())