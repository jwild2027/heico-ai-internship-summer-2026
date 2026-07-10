#!/usr/bin/env python3
"""Launch the TRACE-Net local router stack with one command.

Starts three read-only local services:
  1. Normal TRACE-Net E2E endpoint on 8014 by default.
  2. Guided candidate discovery endpoint on 8016 by default.
  3. Router/proxy endpoint on 8017 by default.

This launcher is intentionally process-only. It does not mutate source truth, Postgres,
Qdrant, OpenSearch, or TRACE-Net artifact data.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

STATUS_READY = "TRACE_NET_ROUTER_STACK_LAUNCHER_V1_READY"
STATUS_STOPPED = "TRACE_NET_ROUTER_STACK_LAUNCHER_V1_STOPPED"
STATUS_FAILED = "TRACE_NET_ROUTER_STACK_LAUNCHER_V1_FAILED"

NORMAL_SCRIPT = Path("scripts/serve_trace_net_e2e_local_endpoint_v1.py")
GUIDED_SCRIPT = Path("scripts/serve_trace_net_guided_candidate_discovery_endpoint_v1.py")
ROUTER_SCRIPT = Path("scripts/serve_trace_net_guided_discovery_router_proxy_v3.py")


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    command: List[str]
    health_url: str
    log_path: Path


@dataclass
class ManagedProcess:
    spec: ServiceSpec
    process: subprocess.Popen
    log_handle: object


def _repo_root() -> Path:
    return Path.cwd().resolve()


def _require_script(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Required script not found: {path}. Pull/apply the latest TRACE-Net patches first."
        )


def _health_ok(url: str, timeout_seconds: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            return 200 <= int(response.status) < 300
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def _wait_for_health(name: str, url: str, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _health_ok(url):
            return True
        time.sleep(0.5)
    return False


def _process_alive(proc: subprocess.Popen) -> bool:
    return proc.poll() is None


def _new_process_kwargs() -> Dict[str, object]:
    kwargs: Dict[str, object] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["preexec_fn"] = os.setsid
    return kwargs


def _terminate_process(proc: subprocess.Popen, grace_seconds: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        proc.terminate()

    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.2)

    try:
        if os.name == "nt":
            proc.kill()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        return
    except Exception:
        proc.kill()


def build_specs(args: argparse.Namespace) -> List[ServiceSpec]:
    repo = _repo_root()
    for script in (NORMAL_SCRIPT, GUIDED_SCRIPT, ROUTER_SCRIPT):
        _require_script(repo / script)

    python_exe = args.python_exe or sys.executable
    log_dir = Path(args.output_root).expanduser() / "router_stack_launcher_v1" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    normal_base = f"http://{args.host}:{args.normal_port}"
    guided_base = f"http://{args.host}:{args.guided_port}"
    router_base = f"http://{args.host}:{args.router_port}"

    normal_cmd = [
        python_exe,
        "-B",
        str(NORMAL_SCRIPT),
        "--host",
        args.host,
        "--port",
        str(args.normal_port),
    ]

    guided_cmd = [
        python_exe,
        "-B",
        str(GUIDED_SCRIPT),
        "--host",
        args.host,
        "--port",
        str(args.guided_port),
        "--artifact-root",
        args.artifact_root,
        "--output-dir",
        str(Path(args.output_root).expanduser() / "guided_candidate_discovery_endpoint_v1"),
        "--top-k",
        str(args.top_k),
        "--loose-top-k",
        str(args.loose_top_k),
    ]

    router_cmd = [
        python_exe,
        "-B",
        str(ROUTER_SCRIPT),
        "--host",
        args.host,
        "--port",
        str(args.router_port),
        "--normal-base-url",
        normal_base,
        "--guided-base-url",
        guided_base,
        "--top-k",
        str(args.top_k),
        "--loose-top-k",
        str(args.loose_top_k),
    ]

    return [
        ServiceSpec(
            name="normal_endpoint_8014",
            command=normal_cmd,
            health_url=f"{normal_base}/health",
            log_path=log_dir / "normal_endpoint_8014.log",
        ),
        ServiceSpec(
            name="guided_discovery_endpoint_8016",
            command=guided_cmd,
            health_url=f"{guided_base}/health",
            log_path=log_dir / "guided_discovery_endpoint_8016.log",
        ),
        ServiceSpec(
            name="router_proxy_8017",
            command=router_cmd,
            health_url=f"{router_base}/health",
            log_path=log_dir / "router_proxy_8017.log",
        ),
    ]


def start_service(spec: ServiceSpec) -> ManagedProcess:
    spec.log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = spec.log_path.open("a", encoding="utf-8")
    handle.write("\n" + "=" * 100 + "\n")
    handle.write(f"Starting {spec.name} at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    handle.write("Command: " + " ".join(spec.command) + "\n")
    handle.flush()

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        spec.command,
        cwd=str(_repo_root()),
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=env,
        **_new_process_kwargs(),
    )
    return ManagedProcess(spec=spec, process=proc, log_handle=handle)


def stop_services(processes: Sequence[ManagedProcess]) -> None:
    for managed in reversed(processes):
        _terminate_process(managed.process)
    for managed in processes:
        try:
            managed.log_handle.flush()
            managed.log_handle.close()
        except Exception:
            pass


def _write_manifest(args: argparse.Namespace, specs: Sequence[ServiceSpec], started: Sequence[ManagedProcess], status: str) -> Path:
    manifest_dir = Path(args.output_root).expanduser() / "router_stack_launcher_v1"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "trace_net_router_stack_launcher_v1_manifest.json"
    payload = {
        "status": status,
        "quality_status": "PASS" if status == STATUS_READY else "WARN",
        "services": [
            {
                "name": spec.name,
                "command": spec.command,
                "health_url": spec.health_url,
                "log_path": str(spec.log_path),
            }
            for spec in specs
        ],
        "started_pids": [
            {"name": proc.spec.name, "pid": proc.process.pid}
            for proc in started
        ],
        "router_base_url": f"http://{args.host}:{args.router_port}/v1",
        "router_model": "trace-net-router-proxy-v3",
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def launch_stack(args: argparse.Namespace) -> int:
    specs = build_specs(args)
    started: List[ManagedProcess] = []

    try:
        for spec in specs:
            print(f"Starting {spec.name}...")
            managed = start_service(spec)
            started.append(managed)

            if not _wait_for_health(spec.name, spec.health_url, args.startup_timeout_seconds):
                code = managed.process.poll()
                print(f"ERROR: {spec.name} did not become healthy at {spec.health_url}", file=sys.stderr)
                print(f"Log: {spec.log_path}", file=sys.stderr)
                if code is not None:
                    print(f"Process exited with code {code}", file=sys.stderr)
                _write_manifest(args, specs, started, STATUS_FAILED)
                stop_services(started)
                return 2

            print(f"{spec.name} healthy: {spec.health_url}")

        manifest_path = _write_manifest(args, specs, started, STATUS_READY)
        print(f"status={STATUS_READY}")
        print("quality_status=PASS")
        print(f"normal=http://{args.host}:{args.normal_port}")
        print(f"guided=http://{args.host}:{args.guided_port}")
        print(f"router=http://{args.host}:{args.router_port}")
        print(f"web_ui_base_url=http://{args.host}:{args.router_port}/v1")
        print("web_ui_model=trace-net-router-proxy-v3")
        print(f"manifest={manifest_path}")
        for proc in started:
            print(f"log_{proc.spec.name}={proc.spec.log_path}")
        print("Press Ctrl+C to stop the TRACE-Net router stack.")

        while True:
            for proc in started:
                if not _process_alive(proc.process):
                    print(
                        f"ERROR: {proc.spec.name} exited with code {proc.process.returncode}. Log: {proc.spec.log_path}",
                        file=sys.stderr,
                    )
                    _write_manifest(args, specs, started, STATUS_FAILED)
                    stop_services(started)
                    return 3
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("Stopping TRACE-Net router stack...")
        stop_services(started)
        _write_manifest(args, specs, started, STATUS_STOPPED)
        print(f"status={STATUS_STOPPED}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        _write_manifest(args, specs, started, STATUS_FAILED)
        stop_services(started)
        return 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch TRACE-Net normal, guided, and router endpoints together.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--normal-port", type=int, default=8014)
    parser.add_argument("--guided-port", type=int, default=8016)
    parser.add_argument("--router-port", type=int, default=8017)
    parser.add_argument("--artifact-root", default="local_data/organization/trace_net")
    parser.add_argument("--output-root", default="/data/trace_net_runs")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--loose-top-k", type=int, default=8)
    parser.add_argument("--startup-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--python-exe", default=None, help="Optional Python executable. Defaults to current interpreter.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return launch_stack(args)


if __name__ == "__main__":
    raise SystemExit(main())
