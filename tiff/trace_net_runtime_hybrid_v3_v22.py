"""TRACE-Net Hybrid v3 final-return runtime launcher v2.2.

This module is a small runtime-control layer for the current TRACE-Net default
path:

    Open WebUI -> final-return policy Hybrid v3 v2.2 API -> Hybrid Retrieval v3

It deliberately does not retrieve, answer, mutate source truth, or write to
Postgres/Qdrant/OpenSearch.  Its responsibilities are limited to:

* validate the required PASS artifacts exist;
* write a small runtime manifest/quality report;
* optionally start/check local Docker services;
* launch the existing final-return policy Hybrid v3 v2.2 API with sane defaults;
* print the Open WebUI connection settings.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import URLError
from urllib.request import urlopen

SCHEMA_VERSION = "trace_net_runtime_hybrid_v3_v22"
QUALITY_SCHEMA_VERSION = "trace_net_runtime_hybrid_v3_v22_quality"
STATUS_BUILT = "RUNTIME_HYBRID_V3_V22_CONFIG_BUILT"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/runtime_hybrid_v3_v22")
DEFAULT_HYBRID_V3_REPORT = Path(
    "local_data/organization/trace_net/hybrid_retrieval_v3/trace_net_hybrid_retrieval_v3.json"
)
DEFAULT_FINAL_RETURN_CONFIG = Path(
    "local_data/organization/trace_net/ask_api_final_return_policy_hybrid_v3_v22/"
    "trace_net_ask_api_final_return_policy_hybrid_v3_v22.json"
)
DEFAULT_FINAL_ANSWER_REPORT = Path(
    "local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json"
)
DEFAULT_FINAL_ANSWER_MARKDOWN = Path(
    "local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1_answer.md"
)
DEFAULT_MODEL_NAME = "trace-net-final-return-policy-hybrid-v3-v2.2"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8016
DEFAULT_OPEN_WEBUI_BASE_URL = "http://host.docker.internal:8016/v1"
DEFAULT_DOCKER_SERVICES = ("trace-net-postgres", "trace-net-qdrant", "open-webui")

HARD_ZERO_COUNTERS = (
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "source_truth_mutation_allowed_count",
    "answer_permission_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "retrieval_only_answer_allowed_count",
    "feedback_as_proof_count",
    "community_as_proof_count",
    "category_as_proof_count",
    "corrective_action_as_proof_count",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def quality_status_of(payload: dict[str, Any]) -> str:
    for key in ("quality_status", "status"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            if value.upper() in {"PASS", "FAIL", "REVIEW", "UNKNOWN"}:
                return value.upper()
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in ("quality_status", "status"):
            value = summary.get(key)
            if isinstance(value, str) and value:
                if value.upper() in {"PASS", "FAIL", "REVIEW", "UNKNOWN"}:
                    return value.upper()
    return "UNKNOWN"


def bool_from_quality(status: str) -> bool:
    return str(status).upper() == "PASS"


def safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def artifact_meta(path: Path, *, required: bool = True) -> dict[str, Any]:
    exists = path.exists()
    meta: dict[str, Any] = {
        "path": path.as_posix(),
        "required": required,
        "exists": exists,
    }
    if exists:
        meta["size_bytes"] = path.stat().st_size
    return meta


def summarize_artifact(path: Path, *, required: bool = True) -> dict[str, Any]:
    meta = artifact_meta(path, required=required)
    if not meta["exists"]:
        meta["quality_status"] = "MISSING" if required else "OPTIONAL_MISSING"
        return meta
    try:
        payload = read_json(path)
        meta["quality_status"] = quality_status_of(payload)
        summary = payload.get("summary")
        if isinstance(summary, dict):
            for key in (
                "query_count",
                "queries_with_results_count",
                "hybrid_v3_group_count",
                "corrective_group_count",
                "review_routed_group_count",
                "unsafe_group_count",
                "final_answer_quality_status",
            ):
                if key in summary:
                    meta[key] = summary[key]
    except Exception as exc:  # pragma: no cover - defensive, exercised in real runtime only
        meta["quality_status"] = "UNREADABLE"
        meta["read_error"] = str(exc)
    return meta


@dataclass(frozen=True)
class RuntimePaths:
    hybrid_v3_report: Path
    final_return_config: Path
    final_answer_report: Path
    final_answer_markdown: Path
    output_dir: Path


@dataclass(frozen=True)
class RuntimeConfig:
    model_name: str
    host: str
    port: int
    max_groups: int
    open_webui_base_url: str
    docker_services: tuple[str, ...]
    start_docker_supported: bool = True
    api_key: str = "blank"


def build_report(paths: RuntimePaths, config: RuntimeConfig, *, require_hybrid_v3_quality_pass: bool = True) -> dict[str, Any]:
    hybrid_meta = summarize_artifact(paths.hybrid_v3_report, required=True)
    final_return_meta = summarize_artifact(paths.final_return_config, required=False)
    final_answer_meta = summarize_artifact(paths.final_answer_report, required=False)
    final_answer_markdown_meta = artifact_meta(paths.final_answer_markdown, required=False)

    source_quality_statuses = {
        "hybrid_retrieval_v3": hybrid_meta.get("quality_status", "UNKNOWN"),
        "final_return_policy_hybrid_v3_v22": final_return_meta.get("quality_status", "OPTIONAL_MISSING"),
        "final_answer_gate": final_answer_meta.get("quality_status", "OPTIONAL_MISSING"),
    }

    checks = {
        "hybrid_v3_report_present": bool(hybrid_meta.get("exists")),
        "hybrid_v3_report_quality_pass": bool_from_quality(str(hybrid_meta.get("quality_status"))),
        "final_return_config_present": bool(final_return_meta.get("exists")),
        "final_answer_report_present": bool(final_answer_meta.get("exists")),
        "runtime_is_read_only": True,
        "open_webui_base_url_present": bool(config.open_webui_base_url),
        "model_name_present": bool(config.model_name),
        "api_port_present": config.port > 0,
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "model_name": config.model_name,
        "api_host": config.host,
        "api_port": config.port,
        "open_webui_base_url": config.open_webui_base_url,
        "open_webui_model": config.model_name,
        "open_webui_api_key": config.api_key,
        "max_groups": config.max_groups,
        "docker_service_count": len(config.docker_services),
        "docker_services": list(config.docker_services),
        "hybrid_v3_quality_status": source_quality_statuses["hybrid_retrieval_v3"],
        "hybrid_v3_group_count": safe_int(hybrid_meta.get("hybrid_v3_group_count")),
        "corrective_group_count": safe_int(hybrid_meta.get("corrective_group_count")),
        "review_routed_group_count": safe_int(hybrid_meta.get("review_routed_group_count")),
        "read_only_runtime": True,
    }
    summary.update({counter: 0 for counter in HARD_ZERO_COUNTERS})

    fail_reasons: list[str] = []
    if not checks["hybrid_v3_report_present"]:
        fail_reasons.append("hybrid_v3_report_missing")
    if require_hybrid_v3_quality_pass and not checks["hybrid_v3_report_quality_pass"]:
        fail_reasons.append("hybrid_v3_quality_not_pass")
    if not checks["runtime_is_read_only"]:
        fail_reasons.append("runtime_not_read_only")
    if not checks["model_name_present"]:
        fail_reasons.append("model_name_missing")
    if not checks["api_port_present"]:
        fail_reasons.append("api_port_missing")

    quality_status = "PASS" if not fail_reasons else "FAIL"
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = fail_reasons

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "summary": summary,
        "checks": checks,
        "source_quality_statuses": source_quality_statuses,
        "artifacts": {
            "hybrid_v3_report": hybrid_meta,
            "final_return_config": final_return_meta,
            "final_answer_report": final_answer_meta,
            "final_answer_markdown": final_answer_markdown_meta,
        },
        "runtime_commands": {
            "health": f"curl -s http://localhost:{config.port}/health | python -m json.tool",
            "openai_chat": f"curl -s -X POST http://localhost:{config.port}/v1/chat/completions -H 'Content-Type: application/json' -d '{{\"model\":\"{config.model_name}\",\"messages\":[{{\"role\":\"user\",\"content\":\"120-46137-001\"}}]}}' | python -m json.tool",
        },
        "open_webui": {
            "base_url": config.open_webui_base_url,
            "model": config.model_name,
            "api_key": config.api_key,
        },
        "safety_contract": {
            "read_only_runtime": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission_from_runtime": True,
            "hybrid_v3_routing_is_not_proof": True,
            "final_gate_remains_answer_authority": True,
        },
    }
    return report


def evaluate_quality(report: dict[str, Any], *, require_hybrid_v3_quality_pass: bool = True) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    checks = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "runtime_is_read_only": summary.get("read_only_runtime") is True,
        "hybrid_v3_report_present": bool((report.get("checks") or {}).get("hybrid_v3_report_present")),
        "hybrid_v3_quality_pass": bool((report.get("checks") or {}).get("hybrid_v3_report_quality_pass")),
        "write_attempts_zero": all(safe_int(summary.get(key)) == 0 for key in (
            "postgres_write_attempt_count",
            "qdrant_write_attempt_count",
            "opensearch_write_attempt_count",
        )),
        "source_truth_mutation_allowed_zero": safe_int(summary.get("source_truth_mutation_allowed_count")) == 0,
        "answer_permission_zero": safe_int(summary.get("answer_permission_count")) == 0,
        "can_answer_directly_zero": safe_int(summary.get("can_answer_directly_count")) == 0,
        "can_prove_claims_zero": safe_int(summary.get("can_prove_claims_count")) == 0,
        "retrieval_only_answer_allowed_zero": safe_int(summary.get("retrieval_only_answer_allowed_count")) == 0,
        "corrective_action_as_proof_zero": safe_int(summary.get("corrective_action_as_proof_count")) == 0,
        "open_webui_settings_present": bool((report.get("open_webui") or {}).get("base_url")) and bool((report.get("open_webui") or {}).get("model")),
    }
    fail_reasons = [key for key, ok in checks.items() if not ok]
    if not require_hybrid_v3_quality_pass and "hybrid_v3_quality_pass" in fail_reasons:
        fail_reasons.remove("hybrid_v3_quality_pass")
    quality_status = "PASS" if not fail_reasons else "FAIL"
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = fail_reasons
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": quality_status,
        "quality_status": quality_status,
        "summary": summary,
        "checks": checks,
    }


def write_report_bundle(report: dict[str, Any], output_dir: Path) -> None:
    report_path = output_dir / "trace_net_runtime_hybrid_v3_v22.json"
    quality_path = output_dir / "trace_net_runtime_hybrid_v3_v22_quality.json"
    summary_path = output_dir / "trace_net_runtime_hybrid_v3_v22_summary.json"
    manifest_path = output_dir / "trace_net_runtime_hybrid_v3_v22_manifest.json"

    quality = evaluate_quality(report)
    write_json(report_path, report)
    write_json(quality_path, quality)
    write_json(summary_path, report["summary"])
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now(),
        "files": {
            "report": report_path.as_posix(),
            "quality": quality_path.as_posix(),
            "summary": summary_path.as_posix(),
        },
        "open_webui": report.get("open_webui"),
    })


def docker_start_services(services: Iterable[str], *, dry_run: bool = False) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for service in services:
        command = ["docker", "start", service]
        if dry_run:
            results.append({"service": service, "command": command, "status": "DRY_RUN"})
            continue
        proc = subprocess.run(command, text=True, capture_output=True)
        results.append({
            "service": service,
            "command": command,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "status": "PASS" if proc.returncode == 0 else "FAIL",
        })
    return results


def run_command(command: list[str], *, timeout: int = 20) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        return {
            "command": command,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "status": "PASS" if proc.returncode == 0 else "FAIL",
        }
    except Exception as exc:  # pragma: no cover - external environment only
        return {"command": command, "status": "FAIL", "error": str(exc)}


def http_check(url: str, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout_seconds) as response:  # nosec - local runtime check only
            body = response.read(500).decode("utf-8", errors="replace")
            return {"url": url, "status_code": response.status, "status": "PASS", "body_preview": body}
    except URLError as exc:
        return {"url": url, "status": "FAIL", "error": str(exc)}
    except Exception as exc:  # pragma: no cover - external environment only
        return {"url": url, "status": "FAIL", "error": str(exc)}


def collect_service_checks(port: int) -> dict[str, Any]:
    return {
        "docker_ps": run_command(["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"]),
        "postgres_pg_isready": run_command(["docker", "exec", "trace-net-postgres", "pg_isready", "-U", "tracenet", "-d", "tracenet_dev"]),
        "qdrant_collections": http_check("http://localhost:6333/collections"),
        "open_webui_health": http_check("http://localhost:3000/health"),
        "api_health": http_check(f"http://localhost:{port}/health"),
    }


def final_policy_api_command(args: argparse.Namespace) -> list[str]:
    script = Path("scripts/run_trace_net_ask_api_final_return_policy_hybrid_v3_v22.py")
    return [
        sys.executable,
        script.as_posix(),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--hybrid-v3-report",
        Path(args.hybrid_v3_report).as_posix(),
        "--final-answer-report",
        Path(args.final_answer_report).as_posix(),
        "--final-answer-markdown",
        Path(args.final_answer_markdown).as_posix(),
        "--output-dir",
        Path(args.final_return_output_dir).as_posix(),
        "--model-name",
        args.model_name,
        "--max-groups",
        str(args.max_groups),
    ]


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--hybrid-v3-report", type=Path, default=DEFAULT_HYBRID_V3_REPORT)
    parser.add_argument("--final-return-config", type=Path, default=DEFAULT_FINAL_RETURN_CONFIG)
    parser.add_argument("--final-answer-report", type=Path, default=DEFAULT_FINAL_ANSWER_REPORT)
    parser.add_argument("--final-answer-markdown", type=Path, default=DEFAULT_FINAL_ANSWER_MARKDOWN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--max-groups", type=int, default=8)
    parser.add_argument("--open-webui-base-url", default=DEFAULT_OPEN_WEBUI_BASE_URL)
    parser.add_argument("--docker-service", action="append", dest="docker_services", default=[])
    parser.add_argument("--require-hybrid-v3-quality-pass", action="store_true")


def make_paths(args: argparse.Namespace) -> RuntimePaths:
    return RuntimePaths(
        hybrid_v3_report=Path(args.hybrid_v3_report),
        final_return_config=Path(args.final_return_config),
        final_answer_report=Path(args.final_answer_report),
        final_answer_markdown=Path(args.final_answer_markdown),
        output_dir=Path(args.output_dir),
    )


def make_config(args: argparse.Namespace) -> RuntimeConfig:
    services = tuple(args.docker_services or DEFAULT_DOCKER_SERVICES)
    return RuntimeConfig(
        model_name=args.model_name,
        host=args.host,
        port=args.port,
        max_groups=args.max_groups,
        open_webui_base_url=args.open_webui_base_url,
        docker_services=services,
    )


def build_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Hybrid v3 v2.2 runtime manifest.")
    add_common_args(parser)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    paths = make_paths(args)
    config = make_config(args)
    report = build_report(paths, config, require_hybrid_v3_quality_pass=args.require_hybrid_v3_quality_pass)
    write_report_bundle(report, paths.output_dir)

    print("TRACE-Net Hybrid v3 v2.2 Runtime")
    print(" Status:", report["status"])
    print(" Quality status:", report["quality_status"])
    print(" model_name:", config.model_name)
    print(" api:", f"http://localhost:{config.port}")
    print(" Open WebUI Base URL:", config.open_webui_base_url)
    print(" Open WebUI Model:", config.model_name)
    print(" report_path:", paths.output_dir / "trace_net_runtime_hybrid_v3_v22.json")
    if args.quality and report["quality_status"] != "PASS":
        return 1
    return 0


def check_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Hybrid v3 v2.2 runtime manifest quality.")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--require-hybrid-v3-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    report = read_json(args.report_path)
    quality = evaluate_quality(report, require_hybrid_v3_quality_pass=args.require_hybrid_v3_quality_pass)
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_runtime_hybrid_v3_v22_quality.json"), quality)
    print(json.dumps(quality, indent=2, sort_keys=True))
    return 0 if quality["quality_status"] == "PASS" else 1


def run_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run TRACE-Net default Hybrid v3 final-return runtime.")
    add_common_args(parser)
    parser.add_argument("--final-return-output-dir", type=Path, default=Path("local_data/organization/trace_net/ask_api_final_return_policy_hybrid_v3_v22"))
    parser.add_argument("--start-docker", action="store_true", help="Run docker start for Postgres, Qdrant, and Open WebUI before launching the API.")
    parser.add_argument("--check-services", action="store_true", help="Run local service health checks before launching the API.")
    parser.add_argument("--check-only", action="store_true", help="Write runtime manifest and print checks without launching the blocking API server.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands but do not execute Docker starts or API launch.")
    parser.add_argument("--sleep-after-docker", type=float, default=2.0)
    args = parser.parse_args(argv)

    paths = make_paths(args)
    config = make_config(args)
    report = build_report(paths, config, require_hybrid_v3_quality_pass=True)

    docker_results: list[dict[str, Any]] = []
    if args.start_docker:
        docker_results = docker_start_services(config.docker_services, dry_run=args.dry_run)
        report["docker_start_results"] = docker_results
        if not args.dry_run:
            time.sleep(max(0.0, args.sleep_after_docker))

    if args.check_services:
        report["service_checks"] = collect_service_checks(config.port)

    write_report_bundle(report, paths.output_dir)

    print("TRACE-Net default runtime: Hybrid v3 final-return policy v2.2")
    print(" Quality status:", report["quality_status"])
    print(" API URL:", f"http://localhost:{config.port}")
    print(" Open WebUI Base URL:", config.open_webui_base_url)
    print(" Open WebUI Model:", config.model_name)
    print(" Open WebUI API Key:", config.api_key)
    print(" Report:", paths.output_dir / "trace_net_runtime_hybrid_v3_v22.json")

    api_command = final_policy_api_command(args)
    print(" API command:", " ".join(api_command))

    if report["quality_status"] != "PASS":
        print("Runtime manifest did not pass quality; refusing to launch API.", file=sys.stderr)
        return 1
    if args.check_only or args.dry_run:
        return 0

    # Blocking launch: this process becomes the API server until interrupted.
    return subprocess.call(api_command)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_main())
