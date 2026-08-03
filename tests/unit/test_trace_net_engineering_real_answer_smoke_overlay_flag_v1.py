from __future__ import annotations

from pathlib import Path

from tiff.trace_net_engineering_real_answer_smoke_overlay_flag_v1 import (
    build_context_pack_command,
    call_base_main,
    parse_output_dir,
    split_overlay_args,
)


def test_split_overlay_args_strips_overlay_flags_and_keeps_base_args():
    parsed = split_overlay_args([
        "--v2-summary-guidance-index", "v2.json",
        "--output-dir", "out",
        "--engram-answer-runner-overlay-map", "overlay.json",
        "--engram-overlay-question-ids", "q1,q2",
        "--engram-overlay-max-chars", "900",
        "--max-questions", "2",
    ])

    assert parsed.overlay_map == "overlay.json"
    assert parsed.question_ids == "q1,q2"
    assert parsed.max_overlay_chars == 900
    assert "--engram-answer-runner-overlay-map" not in parsed.base_argv
    assert parsed.base_argv == [
        "--v2-summary-guidance-index", "v2.json",
        "--output-dir", "out",
        "--max-questions", "2",
    ]


def test_parse_output_dir_supports_space_and_equals_forms():
    assert parse_output_dir(["--output-dir", "abc"]) == Path("abc")
    assert parse_output_dir(["--output-dir=def"]) == Path("def")


def test_call_base_main_supports_argv_main_and_sys_argv_main():
    seen = {}

    def argv_main(argv):
        seen["argv"] = argv
        return 0

    assert call_base_main(argv_main, ["--x", "1"]) == 0
    assert seen["argv"] == ["--x", "1"]

    def noarg_main():
        return 0

    assert call_base_main(noarg_main, ["--x", "1"]) == 0


def test_build_context_pack_command_contains_safety_flags():
    parsed = split_overlay_args([
        "--output-dir", "out",
        "--engram-answer-runner-overlay-map", "overlay.json",
        "--engram-overlay-question-ids", "q1",
    ])
    cmd = build_context_pack_command(parsed, Path("out/trace_net_engineering_real_answer_smoke_test_v1.json"), Path("out"))
    joined = " ".join(cmd)
    assert "scripts/build/context/build_trace_net_engineering_answer_runner_overlay_context_pack_v1.py" in joined
    assert "--engram-answer-runner-overlay-map overlay.json" in joined
    assert "--require-no-answer-permission" in joined
    assert "--max-write-attempts 0" in joined
    assert "--question-ids q1" in joined
