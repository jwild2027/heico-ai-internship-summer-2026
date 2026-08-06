"""TRACE-Net ask orchestration CLI with feedback simulation mode.

Runs the safe deterministic retrieval path end-to-end:
  search -> citations -> grouping -> answer composer

Optional feedback mode:
  off      : default; normal deterministic ask path only
  simulate : normal ask path, then feedback-aware search simulation and
             feedback-aware answer simulation as advisory artifacts
  apply    : intentionally blocked in v1; production ranking is not mutated
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

ASK_VERSION = "trace_net_ask_v1_1_feedback_mode"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/ask")
DEFAULT_SEARCH_SUMMARY = Path("local_data/organization/trace_net/search/trace_net_search_summary.json")
DEFAULT_GROUP_SUMMARY = Path("local_data/organization/trace_net/search/trace_net_search_grouped_summary.json")
DEFAULT_CITATION_SUMMARY = Path("local_data/organization/trace_net/citations/trace_net_source_citation_summary.json")
DEFAULT_ANSWER_SUMMARY = Path("local_data/organization/trace_net/answers/trace_net_answer_summary.json")
DEFAULT_ANSWER_HTML = Path("local_data/organization/trace_net/answers/trace_net_answer_draft.html")
DEFAULT_ANSWER_MD = Path("local_data/organization/trace_net/answers/trace_net_answer_draft.md")
DEFAULT_ANSWER_JSON = Path("local_data/organization/trace_net/answers/trace_net_answer_draft.json")
DEFAULT_FEEDBACK_SEARCH_SIM_SUMMARY = Path("local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_summary.json")
DEFAULT_FEEDBACK_ASK_SIM_SUMMARY = Path("local_data/organization/trace_net/feedback_ask_simulation/trace_net_feedback_ask_simulation_summary.json")
DEFAULT_FEEDBACK_ASK_SIM_HTML = Path("local_data/organization/trace_net/feedback_ask_simulation/trace_net_feedback_ask_simulation_answer.html")
DEFAULT_FEEDBACK_ASK_SIM_MD = Path("local_data/organization/trace_net/feedback_ask_simulation/trace_net_feedback_ask_simulation_answer.md")

FEEDBACK_MODES = {"off", "simulate", "apply"}


@dataclass(frozen=True)
class AskOptions:
    query: str = ""
    part_number: str = ""
    page_id: str = ""
    bucket: str = ""
    top_k: int = 10
    feedback_mode: str = "off"
    feedback_top_k: int = 20
    feedback_boost_weight: float = 8.0
    feedback_demote_weight: float = 12.0
    feedback_review_penalty: float = 4.0
    open_result: bool = False
    dry_run: bool = False
    repo_root: Path = Path(".")
    output_dir: Path = DEFAULT_OUTPUT_DIR
    python_executable: str = sys.executable
    search_script: Path = Path("scripts/operations/s6_retrieval/search_trace_net_rag_candidates.py")
    citations_script: Path = Path("scripts/build/context/build_trace_net_source_citations.py")
    group_script: Path = Path("scripts/build/ingestion/group_trace_net_search_results.py")
    answer_script: Path = Path("scripts/operations/writing/compose_trace_net_answer.py")
    feedback_search_sim_script: Path = Path("scripts/operations/s6_retrieval/simulate_trace_net_feedback_search.py")
    feedback_ask_sim_script: Path = Path("scripts/operations/feedback/simulate_trace_net_feedback_ask.py")


@dataclass
class StageResult:
    name: str
    command: List[str]
    return_code: Optional[int]
    elapsed_seconds: float = 0.0
    stdout_tail: str = ""
    stderr_tail: str = ""
    status: str = "planned"


@dataclass
class AskResult:
    status: str
    version: str
    created_at: str
    effective_query: str
    options: Dict[str, Any]
    stages: List[StageResult] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if text else ""


def _as_repo_relative(path: Path) -> str:
    return str(path).replace("/", os.sep)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _effective_query(options: AskOptions) -> str:
    if options.part_number.strip():
        return options.part_number.strip()
    if options.page_id.strip():
        return options.page_id.strip()
    return options.query.strip()


def validate_options(options: AskOptions) -> None:
    if not _effective_query(options):
        raise ValueError("Provide --query, --part-number, or --page-id.")
    if options.top_k < 1:
        raise ValueError("--top-k must be at least 1.")
    if options.feedback_top_k < 1:
        raise ValueError("--feedback-top-k must be at least 1.")
    if options.feedback_mode not in FEEDBACK_MODES:
        raise ValueError(f"--feedback-mode must be one of {sorted(FEEDBACK_MODES)}.")
    if options.feedback_mode == "apply":
        raise ValueError("--feedback-mode apply is intentionally disabled in v1; use --feedback-mode simulate.")


def _add_query_args(command: List[str], options: AskOptions) -> List[str]:
    if options.query.strip():
        command += ["--query", options.query.strip()]
    if options.part_number.strip():
        command += ["--part-number", options.part_number.strip()]
    if options.page_id.strip():
        command += ["--page-id", options.page_id.strip()]
    return command


def build_stage_commands(options: AskOptions) -> List[tuple[str, List[str]]]:
    validate_options(options)
    py = options.python_executable
    search_cmd = [py, _as_repo_relative(options.search_script)]
    search_cmd = _add_query_args(search_cmd, options)
    if options.bucket.strip():
        search_cmd += ["--bucket", options.bucket.strip()]
    search_cmd += ["--top-k", str(options.top_k)]

    citation_cmd = [py, _as_repo_relative(options.citations_script)]
    group_cmd = [py, _as_repo_relative(options.group_script)]
    answer_cmd = [py, _as_repo_relative(options.answer_script)]
    if options.open_result and options.feedback_mode == "off":
        answer_cmd.append("--open")

    stages: List[tuple[str, List[str]]] = [
        ("search", search_cmd),
        ("citations", citation_cmd),
        ("group", group_cmd),
        ("answer", answer_cmd),
    ]

    if options.feedback_mode == "simulate":
        feedback_search_cmd = [
            py,
            _as_repo_relative(options.feedback_search_sim_script),
            "--top-k",
            str(options.feedback_top_k),
            "--boost-weight",
            str(options.feedback_boost_weight),
            "--demote-weight",
            str(options.feedback_demote_weight),
            "--review-penalty",
            str(options.feedback_review_penalty),
        ]
        feedback_search_cmd = _add_query_args(feedback_search_cmd, options)
        feedback_ask_cmd = [py, _as_repo_relative(options.feedback_ask_sim_script)]
        if options.open_result:
            feedback_ask_cmd.append("--open")
        stages.extend([
            ("feedback_search_simulation", feedback_search_cmd),
            ("feedback_ask_simulation", feedback_ask_cmd),
        ])

    return stages


def _run_subprocess(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    root = str(cwd.resolve())
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root + (os.pathsep + existing if existing else "")
    return subprocess.run(list(command), cwd=str(cwd), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _stage_to_dict(stage: StageResult) -> Dict[str, Any]:
    return {
        "name": stage.name,
        "command": stage.command,
        "return_code": stage.return_code,
        "elapsed_seconds": round(stage.elapsed_seconds, 3),
        "status": stage.status,
        "stdout_tail": stage.stdout_tail,
        "stderr_tail": stage.stderr_tail,
    }


def _result_to_dict(result: AskResult) -> Dict[str, Any]:
    return {
        "status": result.status,
        "version": result.version,
        "created_at": result.created_at,
        "effective_query": result.effective_query,
        "options": result.options,
        "stages": [_stage_to_dict(s) for s in result.stages],
        "artifacts": result.artifacts,
        "summary": result.summary,
        "warnings": result.warnings,
    }


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _collect_artifacts(repo_root: Path, output_dir: Path) -> Dict[str, str]:
    paths = {
        "ask_summary": output_dir / "trace_net_ask_summary.json",
        "ask_stages": output_dir / "trace_net_ask_stages.jsonl",
        "ask_report_md": output_dir / "trace_net_ask_report.md",
        "ask_report_html": output_dir / "trace_net_ask_report.html",
        "search_summary": DEFAULT_SEARCH_SUMMARY,
        "group_summary": DEFAULT_GROUP_SUMMARY,
        "citation_summary": DEFAULT_CITATION_SUMMARY,
        "answer_summary": DEFAULT_ANSWER_SUMMARY,
        "answer_json": DEFAULT_ANSWER_JSON,
        "answer_md": DEFAULT_ANSWER_MD,
        "answer_html": DEFAULT_ANSWER_HTML,
        "feedback_search_simulation_summary": DEFAULT_FEEDBACK_SEARCH_SIM_SUMMARY,
        "feedback_ask_simulation_summary": DEFAULT_FEEDBACK_ASK_SIM_SUMMARY,
        "feedback_ask_simulation_md": DEFAULT_FEEDBACK_ASK_SIM_MD,
        "feedback_ask_simulation_html": DEFAULT_FEEDBACK_ASK_SIM_HTML,
    }
    return {k: _as_repo_relative(p) for k, p in paths.items() if (repo_root / p).exists()}


def _collect_summary(repo_root: Path) -> Dict[str, Any]:
    search = _load_json(repo_root / DEFAULT_SEARCH_SUMMARY)
    grouped = _load_json(repo_root / DEFAULT_GROUP_SUMMARY)
    citations = _load_json(repo_root / DEFAULT_CITATION_SUMMARY)
    answer = _load_json(repo_root / DEFAULT_ANSWER_SUMMARY)
    feedback_search = _load_json(repo_root / DEFAULT_FEEDBACK_SEARCH_SIM_SUMMARY)
    feedback_ask = _load_json(repo_root / DEFAULT_FEEDBACK_ASK_SIM_SUMMARY)
    summary = {
        "search_result_records": search.get("result_records"),
        "search_pages_found": search.get("pages_found"),
        "grouped_page_records": grouped.get("grouped_page_records"),
        "grouped_supporting_result_records": grouped.get("supporting_result_records"),
        "citation_records": citations.get("citation_records"),
        "search_results_with_citations": citations.get("search_results_with_citations"),
        "answer_page_records": answer.get("answer_page_records"),
        "answer_evidence_records": answer.get("answer_evidence_records"),
        "unsafe_answer_groups": answer.get("unsafe_answer_groups"),
        "missing_source_url_groups": answer.get("missing_source_url_groups"),
        "missing_tiff_path_groups": answer.get("missing_tiff_path_groups"),
        "missing_ocr_path_groups": answer.get("missing_ocr_path_groups"),
    }
    if feedback_search:
        summary.update({
            "feedback_search_status": feedback_search.get("status"),
            "feedback_search_feedback_signals_used": feedback_search.get("feedback_signals_used"),
            "feedback_search_groups_adjusted": feedback_search.get("groups_with_feedback_adjustment"),
            "feedback_search_rank_changed_records": feedback_search.get("rank_changed_records"),
            "feedback_search_unsafe_results": feedback_search.get("unsafe_simulated_records"),
            "feedback_search_context_warning_signals_used": feedback_search.get("context_warning_signals_used"),
        })
    if feedback_ask:
        summary.update({
            "feedback_ask_status": feedback_ask.get("status"),
            "feedback_ask_simulated_answer_pages": feedback_ask.get("simulated_answer_page_records"),
            "feedback_ask_simulated_evidence_records": feedback_ask.get("simulated_answer_evidence_records"),
            "feedback_ask_feedback_signals_used": feedback_ask.get("feedback_signals_used"),
            "feedback_ask_groups_adjusted": feedback_ask.get("groups_adjusted"),
            "feedback_ask_rank_changed_records": feedback_ask.get("rank_changed_records"),
            "feedback_ask_answer_changed": feedback_ask.get("answer_changed"),
            "feedback_ask_unsafe_groups": feedback_ask.get("unsafe_simulated_answer_groups"),
            "feedback_ask_excluded_groups": feedback_ask.get("excluded_simulated_answer_groups"),
            "feedback_ask_source_truth_mutations": feedback_ask.get("source_truth_mutation_records"),
            "feedback_ask_context_warning_signals_used": feedback_ask.get("context_warning_signals_used"),
        })
    return summary


def _write_report(result: AskResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = _result_to_dict(result)
    (output_dir / "trace_net_ask_summary.json").write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    _write_jsonl(output_dir / "trace_net_ask_stages.jsonl", [_stage_to_dict(s) for s in result.stages])
    lines = [
        "# TRACE-Net Ask v1.1",
        "",
        f"Status: **{result.status}**",
        f"Version: `{result.version}`",
        f"Query: `{result.effective_query}`",
        f"Feedback mode: `{result.options.get('feedback_mode', 'off')}`",
        "",
        "## Summary",
    ]
    for key, value in result.summary.items():
        lines.append(f"- **{key}**: {value}")
    lines += ["", "## Stages"]
    for s in result.stages:
        rc = "planned" if s.return_code is None else str(s.return_code)
        lines.append(f"- `{s.name}`: {s.status} rc={rc} elapsed={s.elapsed_seconds:.3f}s")
    lines += ["", "## Artifacts"]
    for key, value in result.artifacts.items():
        lines.append(f"- **{key}**: `{value}`")
    if result.options.get("feedback_mode") == "simulate":
        lines += [
            "",
            "## Feedback simulation note",
            "Feedback mode `simulate` creates advisory feedback-aware search/answer artifacts only.",
            "It does not mutate production search ranking, source truth, Evidence Consensus, RAG eligibility, or trust tiers.",
        ]
    md = "\n".join(lines) + "\n"
    (output_dir / "trace_net_ask_report.md").write_text(md, encoding="utf-8")
    html = "<html><body>" + md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>\n") + "</body></html>\n"
    (output_dir / "trace_net_ask_report.html").write_text(html, encoding="utf-8")


def run_trace_net_ask(options: AskOptions) -> AskResult:
    validate_options(options)
    repo_root = options.repo_root.resolve()
    output_dir = repo_root / options.output_dir
    stages: List[StageResult] = []
    status = "OK"
    warnings: List[str] = []
    for name, command in build_stage_commands(options):
        if options.dry_run:
            stages.append(StageResult(name=name, command=command, return_code=None, status="planned"))
            continue
        start = time.time()
        done = _run_subprocess(command, repo_root)
        elapsed = time.time() - start
        stage_status = "OK" if done.returncode == 0 else "FAIL"
        stages.append(StageResult(name=name, command=command, return_code=done.returncode, elapsed_seconds=elapsed, stdout_tail=_tail(done.stdout), stderr_tail=_tail(done.stderr), status=stage_status))
        if done.returncode != 0:
            status = "FAIL"
            warnings.append(f"Stage {name} failed with return code {done.returncode}.")
            break
    if options.dry_run:
        status = "PLANNED"
    result = AskResult(
        status=status,
        version=ASK_VERSION,
        created_at=_utc_now(),
        effective_query=_effective_query(options),
        options={
            "query": options.query,
            "part_number": options.part_number,
            "page_id": options.page_id,
            "bucket": options.bucket,
            "top_k": options.top_k,
            "feedback_mode": options.feedback_mode,
            "feedback_top_k": options.feedback_top_k,
            "feedback_boost_weight": options.feedback_boost_weight,
            "feedback_demote_weight": options.feedback_demote_weight,
            "feedback_review_penalty": options.feedback_review_penalty,
            "dry_run": options.dry_run,
            "open": options.open_result,
        },
        stages=stages,
        summary={} if options.dry_run else _collect_summary(repo_root),
        artifacts={} if options.dry_run else _collect_artifacts(repo_root, options.output_dir),
        warnings=warnings,
    )
    _write_report(result, output_dir)
    result.artifacts = _collect_artifacts(repo_root, options.output_dir)
    _write_report(result, output_dir)
    if options.open_result and not options.dry_run:
        open_path = repo_root / (DEFAULT_FEEDBACK_ASK_SIM_HTML if options.feedback_mode == "simulate" else DEFAULT_ANSWER_HTML)
        if open_path.exists():
            try:
                webbrowser.open(open_path.resolve().as_uri())
            except Exception as exc:
                result.warnings.append(f"Could not open result HTML: {exc}")
                _write_report(result, output_dir)
    return result


def _print_result(result: AskResult, output_dir: Path) -> None:
    print("TRACE-Net ask")
    print(f"  Status: {result.status}")
    print(f"  Query: {result.effective_query}")
    print(f"  Feedback mode: {result.options.get('feedback_mode', 'off')}")
    print(f"  Output dir: {output_dir}")
    print("  Stages:")
    for stage in result.stages:
        rc = "planned" if stage.return_code is None else str(stage.return_code)
        print(f"    {stage.name}: {stage.status} rc={rc}")
    if result.summary:
        print("  Summary:")
        for key in [
            "search_result_records",
            "grouped_page_records",
            "answer_page_records",
            "answer_evidence_records",
            "unsafe_answer_groups",
            "feedback_ask_feedback_signals_used",
            "feedback_ask_groups_adjusted",
            "feedback_ask_rank_changed_records",
            "feedback_ask_answer_changed",
            "feedback_ask_unsafe_groups",
        ]:
            if key in result.summary:
                print(f"    {key}: {result.summary.get(key)}")
    print("Files written:")
    for key in ["ask_summary", "ask_report_md", "ask_report_html", "answer_md", "answer_html", "feedback_ask_simulation_md", "feedback_ask_simulation_html"]:
        if key in result.artifacts:
            print(f"  {key}: {result.artifacts[key]}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run TRACE-Net search -> citations -> group -> answer in one command, optionally with feedback simulation.")
    p.add_argument("--query", default="")
    p.add_argument("--part-number", default="")
    p.add_argument("--page-id", default="")
    p.add_argument("--bucket", default="")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--feedback-mode", choices=sorted(FEEDBACK_MODES), default="off", help="off=normal ask; simulate=also run feedback-aware simulations; apply=blocked in v1")
    p.add_argument("--feedback-top-k", type=int, default=20)
    p.add_argument("--feedback-boost-weight", type=float, default=8.0)
    p.add_argument("--feedback-demote-weight", type=float, default=12.0)
    p.add_argument("--feedback-review-penalty", type=float, default=4.0)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument("--python-executable", default=sys.executable)
    p.add_argument("--open", action="store_true", dest="open_result")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        options = AskOptions(
            query=args.query,
            part_number=args.part_number,
            page_id=args.page_id,
            bucket=args.bucket,
            top_k=args.top_k,
            feedback_mode=args.feedback_mode,
            feedback_top_k=args.feedback_top_k,
            feedback_boost_weight=args.feedback_boost_weight,
            feedback_demote_weight=args.feedback_demote_weight,
            feedback_review_penalty=args.feedback_review_penalty,
            open_result=args.open_result,
            dry_run=args.dry_run,
            repo_root=Path(args.repo_root),
            output_dir=Path(args.output_dir),
            python_executable=args.python_executable,
        )
        result = run_trace_net_ask(options)
        _print_result(result, options.output_dir)
        return 0 if result.status in {"OK", "PLANNED"} else 1
    except Exception as exc:
        print("TRACE-Net ask")
        print("  Status: FAIL")
        print(f"  Error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
