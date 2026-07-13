#!/usr/bin/env python3
"""TRACE-Net demo stack launcher v1.

Starts the three local demo services in one terminal:

- 8014 normal ask endpoint
- 8016 guided candidate discovery endpoint
- 8017 router/proxy with gated visual route v1.1

This is a convenience launcher for local demos. It does not change route logic
or source-truth artifacts.

Safety:
- does not mutate source truth
- does not write Postgres/Qdrant/OpenSearch
- writes only local runtime logs/summary under --output-dir
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
from typing import Any, Dict, List, Optional, Sequence


MODULE_NAME = "trace_net_demo_stack_launcher_v1"
STATUS_READY = "TRACE_NET_DEMO_STACK_LAUNCHER_V1_READY"
STATUS_STOPPED = "TRACE_NET_DEMO_STACK_LAUNCHER_V1_STOPPED"


@dataclass
class ServiceSpec:
    name: str
    port: int
    health_url: str
    command: List[str]
    log_path: Path


@dataclass
class RunningService:
    spec: ServiceSpec
    process: subprocess.Popen
    log_handle: Any


def repo_root() -> Path:
    return Path.cwd()


def required_script(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required script not found: {path}")


def required_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required artifact not found: {path}")


def build_service_specs(args: argparse.Namespace, *, root: Path) -> List[ServiceSpec]:
    scripts = root / "scripts"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    normal_script = scripts / "serve_trace_net_e2e_local_endpoint_v1.py"
    guided_script = scripts / "serve_trace_net_guided_candidate_discovery_endpoint_v1.py"
    router_script = scripts / "serve_trace_net_router_proxy_v6_gated_visual_v1_1.py"

    required_script(normal_script)
    required_script(guided_script)
    required_script(router_script)

    gated_visual_docs = root / args.gated_visual_retrieval_documents_jsonl
    review_docs = root / args.review_only_documents_jsonl
    required_file(gated_visual_docs)
    required_file(review_docs)

    python = sys.executable

    normal_cmd = [
        python,
        "-B",
        str(normal_script),
        "--host",
        args.host,
        "--port",
        str(args.normal_port),
    ]

    guided_cmd = [
        python,
        "-B",
        str(guided_script),
        "--host",
        args.host,
        "--port",
        str(args.guided_port),
        "--artifact-root",
        args.artifact_root,
        "--output-dir",
        args.guided_output_dir,
        "--top-k",
        str(args.top_k),
        "--loose-top-k",
        str(args.loose_top_k),
        "--no-view",
    ]

    router_cmd = [
        python,
        "-B",
        str(router_script),
        "--gated-visual-retrieval-documents-jsonl",
        args.gated_visual_retrieval_documents_jsonl,
        "--review-only-documents-jsonl",
        args.review_only_documents_jsonl,
        "--normal-base-url",
        f"http://{args.host}:{args.normal_port}",
        "--guided-base-url",
        f"http://{args.host}:{args.guided_port}",
        "--host",
        args.host,
        "--port",
        str(args.router_port),
        "--model",
        args.model,
        "--top-k",
        str(args.top_k),
        "--loose-top-k",
        str(args.loose_top_k),
        "--visual-top-k",
        str(args.visual_top_k),
    ]

    return [
        ServiceSpec(
            name="normal_ask",
            port=args.normal_port,
            health_url=f"http://{args.host}:{args.normal_port}/health",
            command=normal_cmd,
            log_path=output_dir / "normal_8014.log",
        ),
        ServiceSpec(
            name="guided_discovery",
            port=args.guided_port,
            health_url=f"http://{args.host}:{args.guided_port}/health",
            command=guided_cmd,
            log_path=output_dir / "guided_8016.log",
        ),
        ServiceSpec(
            name="router_proxy",
            port=args.router_port,
            health_url=f"http://{args.host}:{args.router_port}/health",
            command=router_cmd,
            log_path=output_dir / "router_8017.log",
        ),
    ]


def get_json(url: str, timeout_seconds: float = 2.0) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_seconds) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except Exception:
        return {"raw": raw}
    return data if isinstance(data, dict) else {"data": data}


def wait_for_health(
    service: RunningService,
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        if service.process.poll() is not None:
            raise RuntimeError(
                f"{service.spec.name} exited early with code {service.process.returncode}; "
                f"see log {service.spec.log_path}"
            )
        try:
            return get_json(service.spec.health_url)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(poll_seconds)
    raise TimeoutError(
        f"{service.spec.name} did not become healthy at {service.spec.health_url}: {last_error}; "
        f"see log {service.spec.log_path}"
    )


def start_service(spec: ServiceSpec, *, env: Optional[Dict[str, str]] = None) -> RunningService:
    spec.log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = spec.log_path.open("w", encoding="utf-8", errors="replace")
    log_handle.write(f"$ {' '.join(spec.command)}\n\n")
    log_handle.flush()
    process = subprocess.Popen(
        spec.command,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        cwd=str(repo_root()),
        env=env,
        text=True,
    )
    return RunningService(spec=spec, process=process, log_handle=log_handle)


def stop_services(services: Sequence[RunningService], *, grace_seconds: float = 5.0) -> None:
    for service in reversed(list(services)):
        proc = service.process
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    deadline = time.time() + grace_seconds
    for service in reversed(list(services)):
        proc = service.process
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    for service in services:
        try:
            service.log_handle.flush()
            service.log_handle.close()
        except Exception:
            pass


def write_summary(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def print_ready(args: argparse.Namespace, health: Dict[str, Any], output_dir: Path) -> None:
    print(f"status={STATUS_READY}")
    print("quality_status=PASS")
    print(f"module={MODULE_NAME}")
    print(f"normal=http://{args.host}:{args.normal_port}")
    print(f"guided=http://{args.host}:{args.guided_port}")
    print(f"router=http://{args.host}:{args.router_port}")
    print(f"openai_base_url=http://{args.host}:{args.router_port}/v1")
    print(f"model={args.model}")
    print(f"logs={output_dir}")
    print("")
    print("Demo prompts:")
    print("1) Show figure references for passenger seat assembly diagram")
    print("2) I only know the part starts with 24")
    print("3) Find part number 120-36833-001")
    print("")
    print("Health summary:")
    for name, data in health.items():
        status = data.get("status") or data.get("quality_status") or "ok"
        print(f"- {name}: {status}")
    print("")
    print("Press Ctrl+C to stop all three services.")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Start TRACE-Net local demo stack in one terminal.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--normal-port", type=int, default=8014)
    p.add_argument("--guided-port", type=int, default=8016)
    p.add_argument("--router-port", type=int, default=8017)
    p.add_argument("--artifact-root", default="local_data/organization/trace_net")
    p.add_argument(
        "--output-dir",
        default="local_data/organization/trace_net/demo_stack_launcher_v1_runtime",
    )
    p.add_argument(
        "--guided-output-dir",
        default="local_data/organization/trace_net/guided_candidate_discovery_endpoint_v1_runtime",
    )
    p.add_argument(
        "--gated-visual-retrieval-documents-jsonl",
        default="local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/trace_net_gated_visual_retrieval_documents_v1_1.jsonl",
    )
    p.add_argument(
        "--review-only-documents-jsonl",
        default="local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/trace_net_gated_visual_candidate_review_documents_v1_1.jsonl",
    )
    p.add_argument("--model", default="trace-net-router-proxy-v6-gated-visual-v1-1")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--loose-top-k", type=int, default=8)
    p.add_argument("--visual-top-k", type=int, default=8)
    p.add_argument("--health-timeout-seconds", type=float, default=90.0)
    p.add_argument("--health-poll-seconds", type=float, default=1.0)
    p.add_argument(
        "--exit-after-ready",
        action="store_true",
        help="For tests/preflight: start services, wait for health, write summary, then stop.",
    )
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    specs = build_service_specs(args, root=root)

    services: List[RunningService] = []
    health: Dict[str, Any] = {}
    summary_path = output_dir / "summary.json"

    try:
        for spec in specs:
            print(f"Starting {spec.name} on port {spec.port}...")
            service = start_service(spec, env=os.environ.copy())
            services.append(service)
            health[spec.name] = wait_for_health(
                service,
                timeout_seconds=args.health_timeout_seconds,
                poll_seconds=args.health_poll_seconds,
            )
            print(f"  healthy: {spec.health_url}")

        summary = {
            "module": MODULE_NAME,
            "status": STATUS_READY,
            "quality_status": "PASS",
            "services": {
                service.spec.name: {
                    "port": service.spec.port,
                    "health_url": service.spec.health_url,
                    "log_path": str(service.spec.log_path),
                    "pid": service.process.pid,
                    "health": health.get(service.spec.name, {}),
                }
                for service in services
            },
            "openai_base_url": f"http://{args.host}:{args.router_port}/v1",
            "model": args.model,
            "safety_contract": {
                "source_truth_mutation_allowed": False,
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
            },
        }
        write_summary(summary_path, summary)
        print_ready(args, health, output_dir)

        if args.exit_after_ready:
            return 0

        while True:
            for service in services:
                if service.process.poll() is not None:
                    raise RuntimeError(
                        f"{service.spec.name} exited with code {service.process.returncode}; "
                        f"see {service.spec.log_path}"
                    )
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nStopping TRACE-Net demo stack...")
        return 0
    finally:
        stop_services(services)
        stopped = {
            "module": MODULE_NAME,
            "status": STATUS_STOPPED,
            "stopped_at": time.time(),
            "summary": str(summary_path),
        }
        write_summary(output_dir / "stopped.json", stopped)
        print(f"status={STATUS_STOPPED}")


if __name__ == "__main__":
    raise SystemExit(main())
