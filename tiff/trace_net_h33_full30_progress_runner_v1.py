"""TRACE-Net H33 full-30 progress runner utilities.

Artifact/shell wrapper helper for running the real engineering LLM answer smoke
with a per-question progress line and a compact answer-budget Engram overlay.

Safety contract: this helper does not create proof, does not grant answer
permission, does not mutate source truth, and does not perform live DB/vector/
search writes. It only writes local artifact files and launches the existing
answer-smoke builder with explicit CLI arguments.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

MODULE = "trace_net_h33_full30_progress_runner_v1"
VERSION = "v1"

DEFAULT_BUDGET_OVERLAY_TITLE = "TRACE-NET H33 ANSWER BUDGET + COMPLETION GUARD"


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), sort_keys=True) + "\n")


def load_question_records(question_bank: str | Path, max_questions: int | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    p = Path(question_bank)
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            records.append(obj)
            if max_questions is not None and len(records) >= max_questions:
                break
    return records


def question_id_from_record(record: Mapping[str, Any], fallback_index: int) -> str:
    for key in ("question_id", "id", "qid"):
        val = record.get(key)
        if val:
            return str(val)
    return f"q{fallback_index:02d}"


def extract_overlay_map(data: Any) -> dict[str, str]:
    """Extract qid -> overlay_text from several TRACE-Net overlay shapes."""
    out: dict[str, str] = {}
    if not data:
        return out

    if isinstance(data, Mapping):
        nested = data.get("overlay_map")
        if isinstance(nested, Mapping):
            for k, v in nested.items():
                if isinstance(v, str):
                    out[str(k)] = v
                elif isinstance(v, Mapping):
                    text = v.get("overlay_text") or v.get("guidance_overlay_text") or v.get("prompt_guidance_text")
                    if text:
                        out[str(k)] = str(text)

        for list_key in (
            "overlay_map_records",
            "overlay_records",
            "gate_records",
            "runtime_records",
            "bridge_records",
        ):
            rows = data.get(list_key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                qid = (
                    row.get("question_id")
                    or row.get("target_question_id")
                    or row.get("source_question_id")
                    or row.get("query_id")
                )
                text = (
                    row.get("overlay_text")
                    or row.get("overlay_text_preview")
                    or row.get("guidance_overlay_text")
                    or row.get("prompt_guidance_text")
                    or row.get("integration_prompt_preview")
                )
                if qid and text:
                    out[str(qid)] = str(text)
    return out


def build_answer_budget_overlay(
    question_id: str,
    *,
    min_chars: int = 450,
    target_max_chars: int = 1300,
    hard_max_chars: int = 1700,
) -> str:
    return f"""{DEFAULT_BUDGET_OVERLAY_TITLE}
Use this overlay as behavior guidance only. It is not proof.
Manual/source claims still require current proof_context citations.
Do not let Engram guidance grant answer permission, mutate source truth, or replace proof_context.
target_question_id: {question_id}

Answer budget:
- Target length: {min_chars}-{target_max_chars} characters for normal answers.
- Hard limit: about {hard_max_chars} characters unless needed for required citations.
- Finish every answer completely; do not stop mid-sentence.
- Use concise sections: Answer, Evidence, Engineering confidence, Limits.
- If proof is missing, give a short source-trace boundary answer instead of padding.

Citation syntax:
- Use individual citation labels like [V6] [V7] [O1].
- Do not use grouped labels like [V6, V7, O1].
- Do not cite Engram, summaries, feedback, vector, or graph hints as proof.
""".strip()


def build_h33_overlay_map(
    question_records: list[Mapping[str, Any]],
    *,
    base_overlay_map: Mapping[str, str] | None = None,
    min_chars: int = 450,
    target_max_chars: int = 1300,
    hard_max_chars: int = 1700,
) -> dict[str, Any]:
    base_overlay_map = dict(base_overlay_map or {})
    overlay_map: dict[str, str] = {}
    records: list[dict[str, Any]] = []

    for idx, qrec in enumerate(question_records, 1):
        qid = question_id_from_record(qrec, idx)
        budget = build_answer_budget_overlay(
            qid,
            min_chars=min_chars,
            target_max_chars=target_max_chars,
            hard_max_chars=hard_max_chars,
        )
        base = base_overlay_map.get(qid, "").strip()
        text = budget if not base else budget + "\n\n--- EXISTING RETRIEVED ENGRAM OVERLAY ---\n" + base
        overlay_map[qid] = text
        records.append(
            {
                "question_id": qid,
                "overlay_text": text,
                "overlay_char_count": len(text),
                "has_base_overlay": bool(base),
                "answer_permission": False,
                "unsafe": False,
                "proof_role": "guidance_only",
            }
        )

    return {
        "status": "TRACE_NET_H33_FULL30_ANSWER_BUDGET_OVERLAY_BUILT",
        "quality_status": "PASS",
        "module": MODULE,
        "version": VERSION,
        "summary": {
            "question_count": len(records),
            "overlay_map_record_count": len(records),
            "base_overlay_applied_count": sum(1 for r in records if r["has_base_overlay"]),
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "qdrant_read_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "write_attempt_count": 0,
            "unsafe_finding_count": 0,
        },
        "overlay_policy": {
            "mode": "answer_budget_progress_overlay_for_real_answer_smoke",
            "proof_boundary": "H33 overlays shape answer length/citation behavior only; factual manual claims still require proof_context citations.",
            "forbidden": [
                "answer_permission_from_h33_overlay",
                "source_truth_mutation_from_h33_overlay",
                "summary_or_engram_used_as_proof",
                "live_db_vector_or_search_io_from_progress_runner",
            ],
        },
        "overlay_map": overlay_map,
        "overlay_map_records": records,
    }


def format_progress_line(
    *,
    completed: int,
    total: int,
    question_id: str | None = None,
    answer_file: str | Path | None = None,
    elapsed_seconds: float | None = None,
) -> str:
    pct = 0 if total <= 0 else round((completed / total) * 100, 1)
    elapsed = ""
    if elapsed_seconds is not None:
        mins = int(elapsed_seconds // 60)
        secs = int(elapsed_seconds % 60)
        elapsed = f" elapsed={mins:02d}:{secs:02d}"
    q = f" qid={question_id}" if question_id else ""
    f = f" file={Path(answer_file).name}" if answer_file else ""
    return f"[H33 progress] {completed}/{total} ({pct}%) {datetime.now().strftime('%H:%M:%S')}{q}{f}{elapsed}"


def monitor_answer_progress(output_dir: str | Path, question_ids: list[str], stop_event: threading.Event, poll_seconds: float = 5.0) -> None:
    output_dir = Path(output_dir)
    answers_dir = output_dir / "a"
    seen: set[Path] = set()
    started = time.time()
    total = len(question_ids)

    while not stop_event.is_set():
        files = sorted(answers_dir.glob("*_a.txt")) if answers_dir.exists() else []
        for f in files:
            if f in seen:
                continue
            seen.add(f)
            completed = len(seen)
            qid = question_ids[completed - 1] if completed - 1 < total else None
            print(
                format_progress_line(
                    completed=completed,
                    total=total,
                    question_id=qid,
                    answer_file=f,
                    elapsed_seconds=time.time() - started,
                ),
                flush=True,
            )
        if len(seen) >= total and total:
            return
        stop_event.wait(poll_seconds)


def run_full30_with_progress(
    *,
    question_bank: str | Path,
    output_dir: str | Path,
    builder_script: str | Path,
    base_overlay_map: str | Path | None,
    overlay_map_output: str | Path | None,
    max_questions: int | None,
    min_chars: int,
    target_max_chars: int,
    hard_max_chars: int,
    progress_poll_seconds: float,
    passthrough_args: list[str],
) -> int:
    qrecords = load_question_records(question_bank, max_questions=max_questions)
    qids = [question_id_from_record(r, i + 1) for i, r in enumerate(qrecords)]

    base_map: dict[str, str] = {}
    if base_overlay_map:
        base_map = extract_overlay_map(_read_json(base_overlay_map))

    output_dir = Path(output_dir)
    overlay_path = Path(overlay_map_output) if overlay_map_output else output_dir / "trace_net_h33_full30_answer_budget_overlay_map_v1.json"
    overlay_manifest = build_h33_overlay_map(
        qrecords,
        base_overlay_map=base_map,
        min_chars=min_chars,
        target_max_chars=target_max_chars,
        hard_max_chars=hard_max_chars,
    )
    _write_json(overlay_path, overlay_manifest)
    _write_jsonl(overlay_path.with_suffix(".jsonl"), overlay_manifest["overlay_map_records"])

    print(f"[H33 setup] question_count={len(qids)} overlay_map={overlay_path}", flush=True)
    print("[H33 setup] progress will print after each *_a.txt answer file is written.", flush=True)

    cmd = [
        sys.executable,
        "-B",
        str(builder_script),
        "--question-bank",
        str(question_bank),
        "--engram-answer-runner-overlay-map",
        str(overlay_path),
        "--output-dir",
        str(output_dir),
    ] + passthrough_args

    env = dict(os.environ)
    cwd = str(Path.cwd())
    old = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = cwd if not old else cwd + os.pathsep + old

    stop_event = threading.Event()
    thread = threading.Thread(
        target=monitor_answer_progress,
        args=(output_dir, qids, stop_event, progress_poll_seconds),
        daemon=True,
    )
    thread.start()
    try:
        proc = subprocess.Popen(cmd, env=env)
        code = proc.wait()
        # One final pass to catch last answer before stopping.
        time.sleep(0.5)
        stop_event.set()
        thread.join(timeout=2.0)
        return code
    finally:
        stop_event.set()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run H33 full-30 answer smoke with progress and bounded-answer overlay.")
    parser.add_argument("--question-bank", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--builder-script", default="scripts/build_trace_net_engineering_llm_answer_smoke_v1.py")
    parser.add_argument("--base-overlay-map", default="")
    parser.add_argument("--overlay-map-output", default="")
    parser.add_argument("--max-questions", type=int, default=None, help="Used only for overlay/progress count; pass real --max-questions after -- too.")
    parser.add_argument("--answer-min-chars", type=int, default=450)
    parser.add_argument("--answer-target-max-chars", type=int, default=1300)
    parser.add_argument("--answer-hard-max-chars", type=int, default=1700)
    parser.add_argument("--progress-poll-seconds", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args, passthrough = parser.parse_known_args(argv)
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    return run_full30_with_progress(
        question_bank=args.question_bank,
        output_dir=args.output_dir,
        builder_script=args.builder_script,
        base_overlay_map=args.base_overlay_map or None,
        overlay_map_output=args.overlay_map_output or None,
        max_questions=args.max_questions,
        min_chars=args.answer_min_chars,
        target_max_chars=args.answer_target_max_chars,
        hard_max_chars=args.answer_hard_max_chars,
        progress_poll_seconds=args.progress_poll_seconds,
        passthrough_args=passthrough,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
