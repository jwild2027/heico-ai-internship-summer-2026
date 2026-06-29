"""TRACE-Net OCR/classifier single-command pipeline runner v1.

This module orchestrates the current dry-run OCR/classifier ingestion pipeline:
raw TIFF OCR scan -> route confidence resolver -> four-route resolver -> validators ->
retry/probe -> storage gate -> dry-run loader planner -> loader contract audit ->
retrieval payload audit.

It does not write to Postgres, Qdrant, or OpenSearch. It only calls existing dry-run
builders/checkers and writes a pipeline summary report.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

MODULE = "trace_net_ocr_classifier_pipeline_runner_v1"
VERSION = "v1"
PIPELINE_STATUS = "TRACE_NET_OCR_CLASSIFIER_PIPELINE_RUNNER_BUILT"

JsonDict = dict[str, Any]
CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class PipelinePaths:
    output_dir: Path
    ocr_dir: Path
    resolver_dir: Path
    four_route_dir: Path
    validator_dir: Path
    retry_dir: Path
    storage_dir: Path
    loader_dir: Path
    contract_dir: Path
    payload_audit_dir: Path

    @classmethod
    def from_output_dir(cls, output_dir: Path) -> "PipelinePaths":
        return cls(
            output_dir=output_dir,
            ocr_dir=output_dir / "ocr_route_scan_pack_tesseract_full",
            resolver_dir=output_dir / "route_confidence_resolver_visual_diagram_clamped",
            four_route_dir=output_dir / "four_route_operational_resolver",
            validator_dir=output_dir / "route_validator_runner",
            retry_dir=output_dir / "route_unresolved_retry_probe",
            storage_dir=output_dir / "four_route_storage_gate",
            loader_dir=output_dir / "dry_run_loader_planner",
            contract_dir=output_dir / "loader_contract_audit",
            payload_audit_dir=output_dir / "retrieval_payload_audit",
        )

    @property
    def report_paths(self) -> dict[str, Path]:
        return {
            "ocr": self.ocr_dir / "trace_net_ocr_route_scan_pack_v1.json",
            "resolver": self.resolver_dir / "trace_net_route_confidence_resolver_v1.json",
            "four_route": self.four_route_dir / "trace_net_four_route_operational_resolver_v1.json",
            "validator": self.validator_dir / "trace_net_route_validator_runner_v1.json",
            "retry": self.retry_dir / "trace_net_route_unresolved_retry_probe_v1.json",
            "storage": self.storage_dir / "trace_net_four_route_storage_gate_v1.json",
            "loader": self.loader_dir / "trace_net_dry_run_loader_planner_v1.json",
            "contract": self.contract_dir / "trace_net_loader_contract_audit_v1.json",
            "retrieval_payload_audit": self.payload_audit_dir / "trace_net_retrieval_payload_audit_v1.json",
        }


@dataclass(frozen=True)
class PipelineCommand:
    stage: str
    kind: str  # build or check
    command: list[str]
    expected_report: Path | None = None


def _read_json(path: Path) -> JsonDict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[JsonDict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _default_command_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True)


def _run_command(command: PipelineCommand, runner: CommandRunner) -> JsonDict:
    started = time.time()
    proc = runner(command.command)
    elapsed = round(time.time() - started, 3)
    stdout_tail = (proc.stdout or "")[-4000:]
    stderr_tail = (proc.stderr or "")[-4000:]
    record = {
        "stage": command.stage,
        "kind": command.kind,
        "command": command.command,
        "returncode": proc.returncode,
        "elapsed_seconds": elapsed,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "expected_report": str(command.expected_report) if command.expected_report else None,
        "command_status": "PASS" if proc.returncode == 0 else "FAIL",
    }
    if proc.returncode != 0:
        raise RuntimeError(
            f"Pipeline command failed at {command.stage}/{command.kind} with returncode {proc.returncode}\n"
            f"STDOUT tail:\n{stdout_tail}\nSTDERR tail:\n{stderr_tail}"
        )
    return record


def _count_summary_value(stage_payloads: dict[str, JsonDict], key: str) -> int:
    total = 0
    for payload in stage_payloads.values():
        summary = payload.get("summary") or {}
        value = summary.get(key)
        if isinstance(value, bool):
            total += int(value)
        elif isinstance(value, (int, float)):
            total += int(value)
    return total


def _max_summary_value(stage_payloads: dict[str, JsonDict], key: str) -> int:
    values: list[int] = []
    for payload in stage_payloads.values():
        summary = payload.get("summary") or {}
        value = summary.get(key)
        if isinstance(value, bool):
            values.append(int(value))
        elif isinstance(value, (int, float)):
            values.append(int(value))
    return max(values) if values else 0


def _stage_quality_statuses(stage_payloads: dict[str, JsonDict]) -> dict[str, str | None]:
    return {stage: payload.get("quality_status") for stage, payload in stage_payloads.items()}


def _build_command_plan(
    *,
    paths: PipelinePaths,
    source_package: Path,
    tesseract_cmd: Path,
    route_label_taxonomy: Path,
    psm_modes: str,
    request_timeout: int,
    python_executable: str,
) -> list[PipelineCommand]:
    reports = paths.report_paths
    py = python_executable
    commands: list[PipelineCommand] = []

    def add(stage: str, kind: str, args: list[str], report: Path | None = None) -> None:
        commands.append(PipelineCommand(stage=stage, kind=kind, command=[py, *args], expected_report=report))

    add(
        "ocr",
        "build",
        [
            "scripts/build_trace_net_ocr_route_scan_pack_v1.py",
            "--source-package",
            str(source_package),
            "--output-dir",
            str(paths.ocr_dir),
            "--run-tesseract",
            "--tesseract-cmd",
            str(tesseract_cmd),
            "--psm-modes",
            psm_modes,
            "--request-timeout",
            str(request_timeout),
            "--write-page-images",
            "--quality",
        ],
        reports["ocr"],
    )
    add(
        "ocr",
        "check",
        [
            "scripts/check_trace_net_ocr_route_scan_pack_v1_quality.py",
            "--report-path",
            str(reports["ocr"]),
            "--write-json",
            "--require-source-page-count",
            "509",
            "--min-route-records",
            "509",
            "--min-raw-image-hash-count",
            "509",
            "--require-comparison-manifest",
            "--max-unsafe",
            "0",
            "--require-no-answer-permission",
            "--require-no-source-truth-mutation",
            "--require-no-write-attempts",
        ],
        reports["ocr"],
    )

    add(
        "resolver",
        "build",
        [
            "scripts/build_trace_net_route_confidence_resolver_v1.py",
            "--scan-pack",
            str(reports["ocr"]),
            "--route-label-taxonomy",
            str(route_label_taxonomy),
            "--output-dir",
            str(paths.resolver_dir),
            "--high-threshold",
            "85",
            "--medium-threshold",
            "60",
            "--quality",
        ],
        reports["resolver"],
    )
    add(
        "resolver",
        "check",
        [
            "scripts/check_trace_net_route_confidence_resolver_v1_quality.py",
            "--report-path",
            str(reports["resolver"]),
            "--write-json",
            "--min-records",
            "509",
            "--min-auto-resolved",
            "100",
            "--min-multi-route-required",
            "1",
            "--min-validator-required",
            "1",
            "--max-cover-or-title-page-routes",
            "20",
            "--max-image-visual-diagram-routes",
            "80",
            "--require-source-quality-pass",
            "--require-no-human-review-required",
            "--max-unsafe",
            "0",
            "--require-no-answer-permission",
            "--require-no-source-truth-mutation",
            "--require-no-write-attempts",
        ],
        reports["resolver"],
    )

    add(
        "four_route",
        "build",
        [
            "scripts/build_trace_net_four_route_operational_resolver_v1.py",
            "--route-confidence-resolver",
            str(reports["resolver"]),
            "--output-dir",
            str(paths.four_route_dir),
            "--quality",
        ],
        reports["four_route"],
    )
    add(
        "four_route",
        "check",
        [
            "scripts/check_trace_net_four_route_operational_resolver_v1_quality.py",
            "--report-path",
            str(reports["four_route"]),
            "--write-json",
            "--min-records",
            "509",
            "--min-auto-resolved",
            "100",
            "--min-validator-required",
            "1",
            "--min-multi-route-required",
            "1",
            "--require-source-quality-pass",
            "--require-four-operational-routes-only",
            "--require-no-human-review-required",
            "--max-unknown-subtypes",
            "0",
            "--max-unsafe",
            "0",
            "--require-no-answer-permission",
            "--require-no-source-truth-mutation",
            "--require-no-write-attempts",
        ],
        reports["four_route"],
    )

    add(
        "validator",
        "build",
        [
            "scripts/build_trace_net_route_validator_runner_v1.py",
            "--four-route-resolver",
            str(reports["four_route"]),
            "--output-dir",
            str(paths.validator_dir),
            "--quality",
        ],
        reports["validator"],
    )
    add(
        "validator",
        "check",
        [
            "scripts/check_trace_net_route_validator_runner_v1_quality.py",
            "--report-path",
            str(reports["validator"]),
            "--write-json",
            "--min-records",
            "509",
            "--min-validated",
            "150",
            "--min-unresolved",
            "1",
            "--min-qdrant-allowed",
            "100",
            "--min-opensearch-allowed",
            "50",
            "--require-source-quality-pass",
            "--require-no-human-review-required",
            "--require-decision-files",
            "--require-four-validated-routes-only",
            "--max-unsafe",
            "0",
            "--require-no-answer-permission",
            "--require-no-source-truth-mutation",
            "--require-no-write-attempts",
        ],
        reports["validator"],
    )

    add(
        "retry",
        "build",
        [
            "scripts/build_trace_net_route_unresolved_retry_probe_v1.py",
            "--route-validator-runner",
            str(reports["validator"]),
            "--output-dir",
            str(paths.retry_dir),
            "--quality",
        ],
        reports["retry"],
    )
    add(
        "retry",
        "check",
        [
            "scripts/check_trace_net_route_unresolved_retry_probe_v1_quality.py",
            "--report-path",
            str(reports["retry"]),
            "--write-json",
            "--min-records",
            "509",
            "--min-final-validated",
            "359",
            "--min-retry-validated",
            "1",
            "--require-source-quality-pass",
            "--require-no-human-review-required",
            "--require-decision-files",
            "--require-four-validated-routes-only",
            "--max-unsafe",
            "0",
            "--require-no-answer-permission",
            "--require-no-source-truth-mutation",
            "--require-no-write-attempts",
        ],
        reports["retry"],
    )

    add(
        "storage",
        "build",
        [
            "scripts/build_trace_net_four_route_storage_gate_v1.py",
            "--route-unresolved-retry-probe",
            str(reports["retry"]),
            "--output-dir",
            str(paths.storage_dir),
            "--quality",
        ],
        reports["storage"],
    )
    add(
        "storage",
        "check",
        [
            "scripts/check_trace_net_four_route_storage_gate_v1_quality.py",
            "--report-path",
            str(reports["storage"]),
            "--write-json",
            "--min-records",
            "509",
            "--min-postgres-graph-records",
            "509",
            "--min-qdrant-allowed",
            "400",
            "--min-opensearch-allowed",
            "250",
            "--max-final-do-not-embed",
            "100",
            "--require-source-quality-pass",
            "--require-decision-files",
            "--require-no-human-review-required",
            "--max-unsafe",
            "0",
            "--require-no-answer-permission",
            "--require-no-source-truth-mutation",
            "--require-no-write-attempts",
        ],
        reports["storage"],
    )

    add(
        "loader",
        "build",
        [
            "scripts/build_trace_net_dry_run_loader_planner_v1.py",
            "--four-route-storage-gate",
            str(reports["storage"]),
            "--output-dir",
            str(paths.loader_dir),
            "--quality",
        ],
        reports["loader"],
    )
    add(
        "loader",
        "check",
        [
            "scripts/check_trace_net_dry_run_loader_planner_v1_quality.py",
            "--report-path",
            str(reports["loader"]),
            "--write-json",
            "--min-records",
            "509",
            "--min-postgres-plans",
            "509",
            "--min-qdrant-plans",
            "400",
            "--min-opensearch-plans",
            "250",
            "--max-blocked-records",
            "100",
            "--require-source-quality-pass",
            "--require-decision-files",
            "--require-dry-run-only",
            "--require-no-human-review-required",
            "--max-unsafe",
            "0",
            "--require-no-answer-permission",
            "--require-no-source-truth-mutation",
            "--require-no-write-attempts",
        ],
        reports["loader"],
    )

    add(
        "contract",
        "build",
        [
            "scripts/build_trace_net_loader_contract_audit_v1.py",
            "--dry-run-loader-planner",
            str(reports["loader"]),
            "--ocr-route-scan-pack",
            str(reports["ocr"]),
            "--output-dir",
            str(paths.contract_dir),
            "--quality",
        ],
        reports["contract"],
    )
    add(
        "contract",
        "check",
        [
            "scripts/check_trace_net_loader_contract_audit_v1_quality.py",
            "--report-path",
            str(reports["contract"]),
            "--write-json",
            "--min-records",
            "509",
            "--min-lineage-ready",
            "509",
            "--max-missing-lineage",
            "0",
            "--min-postgres-contract-ready",
            "509",
            "--min-qdrant-contract-ready",
            "400",
            "--min-opensearch-contract-ready",
            "250",
            "--require-source-quality-pass",
            "--require-dry-run-only",
            "--require-no-human-review-required",
            "--max-unsafe",
            "0",
            "--require-no-answer-permission",
            "--require-no-source-truth-mutation",
            "--require-no-write-attempts",
        ],
        reports["contract"],
    )

    add(
        "retrieval_payload_audit",
        "build",
        [
            "scripts/build_trace_net_retrieval_payload_audit_v1.py",
            "--loader-contract-audit",
            str(reports["contract"]),
            "--ocr-route-scan-pack",
            str(reports["ocr"]),
            "--output-dir",
            str(paths.payload_audit_dir),
            "--quality",
        ],
        reports["retrieval_payload_audit"],
    )
    add(
        "retrieval_payload_audit",
        "check",
        [
            "scripts/check_trace_net_retrieval_payload_audit_v1_quality.py",
            "--report-path",
            str(reports["retrieval_payload_audit"]),
            "--write-json",
            "--min-records",
            "509",
            "--min-route-separation-pass",
            "400",
            "--min-qdrant-payloads",
            "400",
            "--min-opensearch-payloads",
            "250",
            "--max-violation-records",
            "0",
            "--require-source-quality-pass",
            "--require-no-human-review-required",
            "--max-unsafe",
            "0",
            "--require-no-answer-permission",
            "--require-no-source-truth-mutation",
            "--require-no-write-attempts",
        ],
        reports["retrieval_payload_audit"],
    )

    return commands


def build_pipeline_runner(
    *,
    source_package: str | Path,
    output_dir: str | Path,
    tesseract_cmd: str | Path,
    route_label_taxonomy: str | Path = "local_data/organization/trace_net/route_label_taxonomy/trace_net_route_label_taxonomy_v1.json",
    psm_modes: str = "3,6,11",
    request_timeout: int = 180,
    python_executable: str | None = None,
    command_runner: CommandRunner | None = None,
    quality: bool = False,
) -> JsonDict:
    paths = PipelinePaths.from_output_dir(Path(output_dir))
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    runner = command_runner or _default_command_runner
    py = python_executable or sys.executable

    commands = _build_command_plan(
        paths=paths,
        source_package=Path(source_package),
        tesseract_cmd=Path(tesseract_cmd),
        route_label_taxonomy=Path(route_label_taxonomy),
        psm_modes=psm_modes,
        request_timeout=request_timeout,
        python_executable=py,
    )

    command_records: list[JsonDict] = []
    for command in commands:
        print(f"[{command.stage}] {command.kind}: {' '.join(command.command)}", flush=True)
        command_records.append(_run_command(command, runner))

    stage_payloads: dict[str, JsonDict] = {}
    missing_reports: list[str] = []
    for stage, report_path in paths.report_paths.items():
        if not report_path.exists():
            missing_reports.append(str(report_path))
            continue
        stage_payloads[stage] = _read_json(report_path)

    quality_statuses = _stage_quality_statuses(stage_payloads)
    all_quality_pass = bool(stage_payloads) and all(status == "PASS" for status in quality_statuses.values())

    storage_summary = (stage_payloads.get("storage", {}).get("summary") or {})
    loader_summary = (stage_payloads.get("loader", {}).get("summary") or {})
    contract_summary = (stage_payloads.get("contract", {}).get("summary") or {})
    payload_summary = (stage_payloads.get("retrieval_payload_audit", {}).get("summary") or {})

    write_attempt_count = (
        _max_summary_value(stage_payloads, "write_attempt_count")
        + _count_summary_value(stage_payloads, "postgres_write_attempt_count")
        + _count_summary_value(stage_payloads, "qdrant_write_attempt_count")
        + _count_summary_value(stage_payloads, "opensearch_write_attempt_count")
    )
    answer_permission_count = _count_summary_value(stage_payloads, "answer_permission_count")
    source_truth_mutation_allowed_count = _count_summary_value(stage_payloads, "source_truth_mutation_allowed_count")
    unsafe_record_count = _count_summary_value(stage_payloads, "unsafe_record_count")
    human_review_required_count = _count_summary_value(stage_payloads, "human_review_required_count") + _count_summary_value(stage_payloads, "manual_review_required_count")

    summary: JsonDict = {
        "module": MODULE,
        "version": VERSION,
        "source_package": str(source_package),
        "output_dir": str(paths.output_dir),
        "stage_count": len(paths.report_paths),
        "command_count": len(commands),
        "build_command_count": sum(1 for command in commands if command.kind == "build"),
        "check_command_count": sum(1 for command in commands if command.kind == "check"),
        "stage_report_count": len(stage_payloads),
        "missing_stage_report_count": len(missing_reports),
        "missing_stage_reports": missing_reports,
        "all_stage_quality_pass": all_quality_pass,
        "stage_quality_statuses": quality_statuses,
        "final_validated_route_counts": storage_summary.get("final_validated_route_counts", {}),
        "storage_gate_record_count": storage_summary.get("storage_gate_record_count", 0),
        "postgres_graph_record_count": storage_summary.get("postgres_graph_record_count", 0),
        "qdrant_embedding_allowed_count": storage_summary.get("qdrant_embedding_allowed_count", 0),
        "opensearch_index_allowed_count": storage_summary.get("opensearch_index_allowed_count", 0),
        "final_do_not_embed_count": storage_summary.get("final_do_not_embed_count", 0),
        "loader_plan_record_count": loader_summary.get("loader_plan_record_count", 0),
        "postgres_dry_run_plan_count": loader_summary.get("postgres_dry_run_plan_count", 0),
        "qdrant_dry_run_plan_count": loader_summary.get("qdrant_dry_run_plan_count", 0),
        "opensearch_dry_run_plan_count": loader_summary.get("opensearch_dry_run_plan_count", 0),
        "blocked_loader_record_count": loader_summary.get("blocked_loader_record_count", 0),
        "loader_contract_audit_record_count": contract_summary.get("loader_contract_audit_record_count", 0),
        "postgres_contract_ready_count": contract_summary.get("postgres_contract_ready_count", 0),
        "qdrant_contract_ready_count": contract_summary.get("qdrant_contract_ready_count", 0),
        "opensearch_contract_ready_count": contract_summary.get("opensearch_contract_ready_count", 0),
        "contract_blocked_record_count": contract_summary.get("contract_blocked_record_count", 0),
        "lineage_ready_count": contract_summary.get("lineage_ready_count", 0),
        "missing_lineage_count": contract_summary.get("missing_lineage_count", 0),
        "retrieval_payload_audit_record_count": payload_summary.get("retrieval_payload_audit_record_count", 0),
        "qdrant_payload_count": payload_summary.get("qdrant_payload_count", 0),
        "opensearch_payload_count": payload_summary.get("opensearch_payload_count", 0),
        "violation_record_count": payload_summary.get("violation_record_count", 0),
        "route_payload_mismatch_count": payload_summary.get("route_payload_mismatch_count", 0),
        "blank_payload_violation_count": payload_summary.get("blank_payload_violation_count", 0),
        "blocked_payload_violation_count": payload_summary.get("blocked_payload_violation_count", 0),
        "missing_lineage_payload_count": payload_summary.get("missing_lineage_payload_count", 0),
        "dry_run_only": True,
        "live_write_enabled": False,
        "write_attempt_count": write_attempt_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "unsafe_record_count": unsafe_record_count,
        "human_review_required_count": human_review_required_count,
    }

    failures: list[str] = []
    if missing_reports:
        failures.append("one or more stage reports are missing")
    if not all_quality_pass:
        failures.append("one or more stage quality statuses are not PASS")
    if write_attempt_count:
        failures.append("write attempts were recorded")
    if answer_permission_count:
        failures.append("answer permission was recorded")
    if source_truth_mutation_allowed_count:
        failures.append("source truth mutation permission was recorded")
    if unsafe_record_count:
        failures.append("unsafe records were recorded")
    if human_review_required_count:
        failures.append("human/manual review was recorded")

    quality_status = "PASS" if not failures else "FAIL"
    payload: JsonDict = {
        "status": PIPELINE_STATUS,
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "records": command_records,
        "stage_reports": {stage: str(path) for stage, path in paths.report_paths.items()},
    }

    report_path = paths.output_dir / "trace_net_ocr_classifier_pipeline_runner_v1.json"
    _write_json(report_path, payload)
    _write_json(paths.output_dir / "trace_net_ocr_classifier_pipeline_runner_v1_summary.json", summary)
    _write_jsonl(paths.output_dir / "trace_net_ocr_classifier_pipeline_runner_v1_command_records.jsonl", command_records)

    if quality:
        check_quality(report_path=report_path, write_json=True)

    print(f"Status: {PIPELINE_STATUS}")
    print(f"Quality status: {quality_status}")
    print("Summary:", json.dumps(summary, sort_keys=True))
    return payload


def check_quality(
    *,
    report_path: str | Path,
    write_json: bool = False,
    min_stage_reports: int = 9,
    min_postgres_contract_ready: int = 509,
    min_qdrant_contract_ready: int = 400,
    min_opensearch_contract_ready: int = 250,
    min_qdrant_payloads: int = 400,
    min_opensearch_payloads: int = 250,
    max_violation_records: int = 0,
    require_all_stage_quality_pass: bool = False,
    require_dry_run_only: bool = False,
    require_no_human_review_required: bool = False,
    max_unsafe: int | None = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> JsonDict:
    path = Path(report_path)
    payload = _read_json(path)
    summary = payload.get("summary") or {}
    failures: list[str] = []

    if payload.get("quality_status") != "PASS":
        failures.append("pipeline report quality_status is not PASS")
    if int(summary.get("stage_report_count") or 0) < min_stage_reports:
        failures.append(f"stage report count below minimum {min_stage_reports}")
    if int(summary.get("postgres_contract_ready_count") or 0) < min_postgres_contract_ready:
        failures.append(f"postgres contract ready count below minimum {min_postgres_contract_ready}")
    if int(summary.get("qdrant_contract_ready_count") or 0) < min_qdrant_contract_ready:
        failures.append(f"qdrant contract ready count below minimum {min_qdrant_contract_ready}")
    if int(summary.get("opensearch_contract_ready_count") or 0) < min_opensearch_contract_ready:
        failures.append(f"opensearch contract ready count below minimum {min_opensearch_contract_ready}")
    if int(summary.get("qdrant_payload_count") or 0) < min_qdrant_payloads:
        failures.append(f"qdrant payload count below minimum {min_qdrant_payloads}")
    if int(summary.get("opensearch_payload_count") or 0) < min_opensearch_payloads:
        failures.append(f"opensearch payload count below minimum {min_opensearch_payloads}")
    if int(summary.get("violation_record_count") or 0) > max_violation_records:
        failures.append(f"violation record count above maximum {max_violation_records}")
    if require_all_stage_quality_pass and not summary.get("all_stage_quality_pass"):
        failures.append("not all stage quality statuses are PASS")
    if require_dry_run_only and not summary.get("dry_run_only"):
        failures.append("dry_run_only is not true")
    if require_no_human_review_required and int(summary.get("human_review_required_count") or 0) != 0:
        failures.append("human/manual review count is not zero")
    if max_unsafe is not None and int(summary.get("unsafe_record_count") or 0) > max_unsafe:
        failures.append(f"unsafe record count above maximum {max_unsafe}")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer permission count is not zero")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source truth mutation allowed count is not zero")
    if require_no_write_attempts and int(summary.get("write_attempt_count") or 0) != 0:
        failures.append("write attempt count is not zero")

    result = {
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "failures": failures,
        "report_path": str(path),
    }
    if write_json:
        _write_json(path.with_name(path.stem + "_quality_check.json"), result)
        print("Wrote:", path.with_name(path.stem + "_quality_check.json"))
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(summary, sort_keys=True))
    if failures:
        print("Failures:", json.dumps(failures, indent=2))
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the TRACE-Net OCR/classifier dry-run pipeline in one command.")
    subparsers = parser.add_subparsers(dest="command")

    build = subparsers.add_parser("build")
    build.add_argument("--source-package", required=True)
    build.add_argument("--output-dir", required=True)
    build.add_argument("--tesseract-cmd", required=True)
    build.add_argument(
        "--route-label-taxonomy",
        default="local_data/organization/trace_net/route_label_taxonomy/trace_net_route_label_taxonomy_v1.json",
    )
    build.add_argument("--psm-modes", default="3,6,11")
    build.add_argument("--request-timeout", type=int, default=180)
    build.add_argument("--python-executable", default=sys.executable)
    build.add_argument("--quality", action="store_true")

    check = subparsers.add_parser("check")
    check.add_argument("--report-path", required=True)
    check.add_argument("--write-json", action="store_true")
    check.add_argument("--min-stage-reports", type=int, default=9)
    check.add_argument("--min-postgres-contract-ready", type=int, default=509)
    check.add_argument("--min-qdrant-contract-ready", type=int, default=400)
    check.add_argument("--min-opensearch-contract-ready", type=int, default=250)
    check.add_argument("--min-qdrant-payloads", type=int, default=400)
    check.add_argument("--min-opensearch-payloads", type=int, default=250)
    check.add_argument("--max-violation-records", type=int, default=0)
    check.add_argument("--require-all-stage-quality-pass", action="store_true")
    check.add_argument("--require-dry-run-only", action="store_true")
    check.add_argument("--require-no-human-review-required", action="store_true")
    check.add_argument("--max-unsafe", type=int)
    check.add_argument("--require-no-answer-permission", action="store_true")
    check.add_argument("--require-no-source-truth-mutation", action="store_true")
    check.add_argument("--require-no-write-attempts", action="store_true")
    return parser


def main_build() -> JsonDict:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command not in (None, "build"):
        raise SystemExit("Use the build subcommand or call the build script wrapper.")
    return build_pipeline_runner(
        source_package=args.source_package,
        output_dir=args.output_dir,
        tesseract_cmd=args.tesseract_cmd,
        route_label_taxonomy=args.route_label_taxonomy,
        psm_modes=args.psm_modes,
        request_timeout=args.request_timeout,
        python_executable=args.python_executable,
        quality=args.quality,
    )


def main_check() -> JsonDict:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command not in (None, "check"):
        raise SystemExit("Use the check subcommand or call the check script wrapper.")
    return check_quality(
        report_path=args.report_path,
        write_json=args.write_json,
        min_stage_reports=args.min_stage_reports,
        min_postgres_contract_ready=args.min_postgres_contract_ready,
        min_qdrant_contract_ready=args.min_qdrant_contract_ready,
        min_opensearch_contract_ready=args.min_opensearch_contract_ready,
        min_qdrant_payloads=args.min_qdrant_payloads,
        min_opensearch_payloads=args.min_opensearch_payloads,
        max_violation_records=args.max_violation_records,
        require_all_stage_quality_pass=args.require_all_stage_quality_pass,
        require_dry_run_only=args.require_dry_run_only,
        require_no_human_review_required=args.require_no_human_review_required,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )


if __name__ == "__main__":
    # Default to build behavior when invoked as a module.
    main_build()
