import argparse
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ollama import ResponseError, chat


# This script runs a small batch of independent prompts against Ollama at the same time.
# The goal is to compare response behavior and timing across several requests without
# waiting for each prompt to finish before starting the next one.
MODEL = "gemma3:4b"
SYSTEM_PROMPT = "You are a helpful assistant. Answer in one short paragraph."
# These prompts are intentionally general so they can be randomized into a batch of
# unrelated questions. When the requested batch size is larger than this list, the
# script reuses prompts at random.
DEFAULT_PROMPTS = [
    "What is a practical use for machine learning in a small business?",
    "Explain the difference between latency and throughput.",
    "What is one good way to debug a failing API request?",
    "Why is version control important in a team project?",
    "What is the simplest way to explain containers to a beginner?",
    "How would you improve a slow Python script?",
    "What makes a good prompt for an AI model?",
    "What is the purpose of a database index?",
    "How do you reduce noise in a technical estimate?",
    "What is one common reason a script fails on Windows but not Linux?",
    "How can you make a CLI tool more user friendly?",
    "What is the difference between a bug and a regression?",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line flags that control batch size and verbose output."""
    parser = argparse.ArgumentParser(description="Run five random Ollama prompts concurrently.")
    parser.add_argument("--verbose", action="store_true", help="Print Ollama timing and token metadata.")
    parser.add_argument("--count", type=int, default=5, help="Number of prompts to run at once.")
    return parser.parse_args()


def build_prompts(count: int) -> list[str]:
    """Return a randomized list of prompts for the current batch.

    If the requested count is small enough, the function selects unique prompts so the
    batch stays varied. If the requested count is larger than the available prompt pool,
    it falls back to sampling with replacement so the script can still produce the
    requested number of questions.
    """
    if count <= len(DEFAULT_PROMPTS):
        return random.sample(DEFAULT_PROMPTS, count)
    return [random.choice(DEFAULT_PROMPTS) for _ in range(count)]


def format_duration_ns(value: object) -> str:
    """Format Ollama duration values, which are reported in nanoseconds, into readable text."""
    if not isinstance(value, (int, float)):
        return str(value)
    return f"{value:,} ns ({value / 1_000_000:.2f} ms)"


def print_verbose_metadata(response: object, wall_time_seconds: float) -> None:
    """Print the response metadata that is useful when debugging or benchmarking.

    The Ollama response object exposes timing and token counters for the full request.
    This helper prints the raw values and adds units where they matter so the output is
    easy to scan in verbose mode.
    """
    metadata_fields = (
        ("model", None),
        ("created_at", None),
        ("done", None),
        ("done_reason", None),
        ("total_duration", "duration"),
        ("load_duration", "duration"),
        ("prompt_eval_count", "tokens"),
        ("prompt_eval_duration", "duration"),
        ("eval_count", "tokens"),
        ("eval_duration", "duration"),
    )

    print(f"wall_time: {wall_time_seconds:.2f} s")
    for field, unit_type in metadata_fields:
        value = getattr(response, field, None)
        if value is None:
            continue
        # Ollama reports duration fields in nanoseconds and count fields in tokens.
        if unit_type == "duration":
            print(f"{field}: {format_duration_ns(value)}")
        elif unit_type == "tokens":
            print(f"{field}: {value} tokens")
        else:
            print(f"{field}: {value}")


def run_prompt(prompt: str, verbose: bool) -> dict[str, object]:
    """Send a single prompt to Ollama and capture both content and timing data.

    The function returns a dictionary so the caller can print successful responses and
    failures using the same code path. When Ollama raises an error, we return a structured
    error record instead of crashing the whole batch.
    """
    started_at = time.perf_counter()
    try:
        response = chat(
            MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            stream=False,
        )
    except ResponseError as error:
        return {
            "prompt": prompt,
            "error": f"Ollama error: {error}",
        }

    # Measure the full wall-clock time for the request so it can be compared against
    # Ollama's own internal timing values in verbose mode.
    elapsed_seconds = time.perf_counter() - started_at
    result = {
        "prompt": prompt,
        "response": response["message"]["content"],
        "elapsed_seconds": elapsed_seconds,
        "raw_response": response,
    }

    # Keep the structure simple and explicit for the caller.
    if verbose:
        result["verbose"] = True

    return result


def main() -> None:
    """Build a randomized batch of prompts, run them concurrently, and print results."""
    args = parse_args()
    prompts = build_prompts(args.count)

    # Each prompt is independent, so a thread pool is a simple way to start all requests
    # together and wait for whichever one completes first.
    with ThreadPoolExecutor(max_workers=args.count) as executor:
        future_to_index = {
            executor.submit(run_prompt, prompt, args.verbose): index
            for index, prompt in enumerate(prompts, start=1)
        }

        # as_completed yields results in finish order, which makes it easy to see which
        # prompts returned first even though they all started at roughly the same time.
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            result = future.result()

            print(f"[{index}] Prompt: {result['prompt']}")
            if "error" in result:
                # Keep failures isolated to the prompt that triggered them so the rest of
                # the batch can still finish and print normally.
                print(result["error"])
                print()
                continue

            print(result["response"])
            if args.verbose:
                # In verbose mode, print both Ollama's internal timing data and the wall
                # clock time measured by this script.
                print_verbose_metadata(result["raw_response"], result["elapsed_seconds"])
            print()


if __name__ == "__main__":
    main()
