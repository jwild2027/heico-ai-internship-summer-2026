from pathlib import Path

from tiff.trace_net_ask import AskOptions, build_stage_commands, run_trace_net_ask


def test_build_stage_commands_part_number_default_off():
    options = AskOptions(part_number="120-50645-009", top_k=7, python_executable="python")
    commands = build_stage_commands(options)
    names = [name for name, _ in commands]
    assert names == ["search", "citations", "group", "answer"]
    search = commands[0][1]
    assert "--part-number" in search
    assert "120-50645-009" in search
    assert "--top-k" in search
    assert "7" in search


def test_build_stage_commands_feedback_simulate_adds_two_safe_stages():
    options = AskOptions(part_number="120-50645-009", feedback_mode="simulate", feedback_top_k=12, python_executable="python")
    commands = build_stage_commands(options)
    names = [name for name, _ in commands]
    assert names == ["search", "citations", "group", "answer", "feedback_search_simulation", "feedback_ask_simulation"]
    feedback_search = dict(commands)["feedback_search_simulation"]
    assert "--part-number" in feedback_search
    assert "120-50645-009" in feedback_search
    assert "--top-k" in feedback_search
    assert "12" in feedback_search


def test_build_stage_commands_feedback_apply_is_blocked():
    options = AskOptions(query="seat bottom", feedback_mode="apply", python_executable="python")
    try:
        build_stage_commands(options)
    except ValueError as exc:
        assert "apply" in str(exc)
        assert "simulate" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_stage_commands_open_goes_to_feedback_answer_when_simulate():
    options = AskOptions(query="seat bottom", feedback_mode="simulate", open_result=True, python_executable="python")
    commands = build_stage_commands(options)
    by_name = {name: command for name, command in commands}
    assert "--open" not in by_name["search"]
    assert "--open" not in by_name["group"]
    assert "--open" not in by_name["answer"]
    assert "--open" in by_name["feedback_ask_simulation"]


def test_run_trace_net_ask_dry_run_feedback_simulate(tmp_path):
    options = AskOptions(query="seat bottom backrest", feedback_mode="simulate", dry_run=True, repo_root=tmp_path, output_dir=Path("ask_out"), python_executable="python")
    result = run_trace_net_ask(options)
    assert result.status == "PLANNED"
    assert len(result.stages) == 6
    assert (tmp_path / "ask_out" / "trace_net_ask_summary.json").exists()
    assert result.effective_query == "seat bottom backrest"
    assert result.options["feedback_mode"] == "simulate"


def test_run_trace_net_ask_requires_query(tmp_path):
    options = AskOptions(dry_run=True, repo_root=tmp_path)
    try:
        run_trace_net_ask(options)
    except ValueError as exc:
        assert "--query" in str(exc)
    else:
        raise AssertionError("expected ValueError")
