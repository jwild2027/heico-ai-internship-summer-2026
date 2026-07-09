from __future__ import annotations

"""TRACE-Net real answer smoke Engram overlay flag shim v1.

This module keeps the existing real-answer smoke builder as the source of truth,
but allows the CLI wrapper to accept an explicit
``--engram-answer-runner-overlay-map`` flag. When that flag is present, the base
real-answer smoke runs first. After it succeeds, this shim builds the
LLM-readable Engram work-order/context-pack artifact against the produced real
answer-smoke manifest.

Safety contract:
- Engram overlay is behavior guidance only; it is not proof.
- Manual/source claims still require current proof_context citations.
- This shim does not grant answer permission.
- This shim does not write to Postgres, Qdrant, or OpenSearch.
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

MODULE = "trace_net_engineering_real_answer_smoke_overlay_flag_v1"
VERSION = "v1"

BASE_SMOKE_FILENAME = "trace_net_engineering_real_answer_smoke_test_v1.json"
CONTEXT_PACK_SCRIPT = "scripts/build_trace_net_engineering_answer_runner_overlay_context_pack_v1.py"

OVERLAY_HELP = """
Engram overlay options added by trace_net_engineering_real_answer_smoke_overlay_flag_v1:
  --engram-answer-runner-overlay-map PATH
      Optional explicit Engram answer-runner overlay map. When supplied, the base
      real answer-smoke builder runs first, then a work-order context pack is
      built from the produced smoke manifest and this overlay map.
  --engram-overlay-context-output-dir PATH
      Optional output directory for the generated overlay context pack. Defaults
      to <base --output-dir>/engram_answer_runner_overlay_context_pack_v1.
  --engram-overlay-question-ids IDS
      Optional comma-separated target question ids for the overlay context pack.
      If omitted, the context pack builder may process all records it can match.
  --engram-overlay-max-chars N
      Max Engram overlay chars passed to the context pack builder. Default: 1800.
  --engram-overlay-max-source-prompt-chars N
      Max source prompt chars passed to the context pack builder. Default: 3600.
  --engram-overlay-min-records N
      Minimum context-pack records required. Default: 1.
  --engram-overlay-min-matched-overlays N
      Minimum matched overlays required. Default: 1.
""".strip()


@dataclass(frozen=True)
class OverlayShimArgs:
    base_argv: List[str]
    overlay_map: Optional[str] = None
    context_output_dir: Optional[str] = None
    question_ids: Optional[str] = None
    max_overlay_chars: int = 1800
    max_source_prompt_chars: int = 3600
    min_records: int = 1
    min_matched_overlays: int = 1


def _take_value(argv: Sequence[str], index: int, flag: str) -> Tuple[Optional[str], int]:
    token = argv[index]
    if token.startswith(flag + "="):
        return token.split("=", 1)[1], index + 1
    if index + 1 >= len(argv):
        raise SystemExit(f"{flag} requires a value")
    return argv[index + 1], index + 2


def _as_int(value: Optional[str], flag: str) -> int:
    try:
        return int(value or "")
    except Exception as exc:  # pragma: no cover - defensive
        raise SystemExit(f"{flag} must be an integer, got {value!r}") from exc


def split_overlay_args(argv: Sequence[str]) -> OverlayShimArgs:
    """Strip overlay-only flags, leaving argv safe for the base real-smoke builder."""
    base: List[str] = []
    overlay_map: Optional[str] = None
    context_output_dir: Optional[str] = None
    question_ids: Optional[str] = None
    max_overlay_chars = 1800
    max_source_prompt_chars = 3600
    min_records = 1
    min_matched_overlays = 1

    i = 0
    while i < len(argv):
        token = argv[i]

        if token == "--engram-answer-runner-overlay-map" or token.startswith("--engram-answer-runner-overlay-map="):
            overlay_map, i = _take_value(argv, i, "--engram-answer-runner-overlay-map")
            continue
        if token == "--engram-overlay-context-output-dir" or token.startswith("--engram-overlay-context-output-dir="):
            context_output_dir, i = _take_value(argv, i, "--engram-overlay-context-output-dir")
            continue
        if token == "--engram-overlay-question-ids" or token.startswith("--engram-overlay-question-ids="):
            question_ids, i = _take_value(argv, i, "--engram-overlay-question-ids")
            continue
        if token == "--engram-overlay-max-chars" or token.startswith("--engram-overlay-max-chars="):
            raw, i = _take_value(argv, i, "--engram-overlay-max-chars")
            max_overlay_chars = _as_int(raw, "--engram-overlay-max-chars")
            continue
        if token == "--engram-overlay-max-source-prompt-chars" or token.startswith("--engram-overlay-max-source-prompt-chars="):
            raw, i = _take_value(argv, i, "--engram-overlay-max-source-prompt-chars")
            max_source_prompt_chars = _as_int(raw, "--engram-overlay-max-source-prompt-chars")
            continue
        if token == "--engram-overlay-min-records" or token.startswith("--engram-overlay-min-records="):
            raw, i = _take_value(argv, i, "--engram-overlay-min-records")
            min_records = _as_int(raw, "--engram-overlay-min-records")
            continue
        if token == "--engram-overlay-min-matched-overlays" or token.startswith("--engram-overlay-min-matched-overlays="):
            raw, i = _take_value(argv, i, "--engram-overlay-min-matched-overlays")
            min_matched_overlays = _as_int(raw, "--engram-overlay-min-matched-overlays")
            continue

        base.append(token)
        i += 1

    return OverlayShimArgs(
        base_argv=base,
        overlay_map=overlay_map,
        context_output_dir=context_output_dir,
        question_ids=question_ids,
        max_overlay_chars=max_overlay_chars,
        max_source_prompt_chars=max_source_prompt_chars,
        min_records=min_records,
        min_matched_overlays=min_matched_overlays,
    )


def parse_output_dir(argv: Sequence[str]) -> Path:
    for i, token in enumerate(argv):
        if token == "--output-dir" and i + 1 < len(argv):
            return Path(argv[i + 1])
        if token.startswith("--output-dir="):
            return Path(token.split("=", 1)[1])
    raise SystemExit("Base real-answer smoke args must include --output-dir when --engram-answer-runner-overlay-map is used")


def _normalize_exit_code(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return 1


def call_base_main(base_main: Callable[..., object], base_argv: Sequence[str]) -> int:
    """Call the existing builder main whether it accepts argv or reads sys.argv."""
    try:
        return _normalize_exit_code(base_main(list(base_argv)))
    except TypeError:
        old_argv = sys.argv[:]
        sys.argv = [old_argv[0]] + list(base_argv)
        try:
            return _normalize_exit_code(base_main())
        except SystemExit as exc:
            return _normalize_exit_code(exc.code)
        finally:
            sys.argv = old_argv
    except SystemExit as exc:
        return _normalize_exit_code(exc.code)


def build_context_pack_command(args: OverlayShimArgs, source_answer_smoke: Path, output_dir: Path) -> List[str]:
    if not args.overlay_map:
        raise SystemExit("overlay_map is required")

    context_out = Path(args.context_output_dir) if args.context_output_dir else output_dir / "engram_answer_runner_overlay_context_pack_v1"

    cmd = [
        sys.executable,
        CONTEXT_PACK_SCRIPT,
        "--source-answer-smoke",
        str(source_answer_smoke),
        "--engram-answer-runner-overlay-map",
        str(args.overlay_map),
        "--output-dir",
        str(context_out),
        "--max-overlay-chars",
        str(args.max_overlay_chars),
        "--max-source-prompt-chars",
        str(args.max_source_prompt_chars),
        "--min-records",
        str(args.min_records),
        "--require-source-quality-pass",
        "--require-no-answer-permission",
        "--max-write-attempts",
        "0",
    ]
    if args.question_ids:
        cmd.extend(["--question-ids", args.question_ids])
    # Only require matched overlays when the caller is explicitly using this flag.
    cmd.extend(["--min-matched-overlays", str(args.min_matched_overlays)])
    return cmd


def run_overlay_context_pack(args: OverlayShimArgs, output_dir: Path) -> int:
    source_answer_smoke = output_dir / BASE_SMOKE_FILENAME
    if not source_answer_smoke.exists():
        print(f"engram_overlay_error=missing_source_answer_smoke:{source_answer_smoke}")
        return 1

    cmd = build_context_pack_command(args, source_answer_smoke, output_dir)
    print("engram_overlay_context_pack_command=" + " ".join(str(x) for x in cmd))
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        return int(completed.returncode)

    context_out = Path(args.context_output_dir) if args.context_output_dir else output_dir / "engram_answer_runner_overlay_context_pack_v1"
    print("engram_overlay_context_pack=" + str(context_out / "trace_net_engineering_answer_runner_overlay_context_pack_v1.json"))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parsed = split_overlay_args(raw_argv)

    # Make the new flag discoverable while preserving the base builder's help.
    if "--help" in raw_argv or "-h" in raw_argv:
        print(OVERLAY_HELP)
        print()

    from tiff.trace_net_engineering_real_answer_smoke_test_v1 import main as base_main

    base_exit = call_base_main(base_main, parsed.base_argv)
    if base_exit != 0:
        return base_exit

    if not parsed.overlay_map:
        return 0

    output_dir = parse_output_dir(parsed.base_argv)
    return run_overlay_context_pack(parsed, output_dir)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
