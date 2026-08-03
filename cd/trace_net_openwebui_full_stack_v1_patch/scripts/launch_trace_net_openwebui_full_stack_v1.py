#!/usr/bin/env python3
"""TRACE-Net OpenWebUI full stack launcher v1.

Starts the services needed for OpenWebUI to use the full TRACE-Net router stack:

- 8014: normal exact/OCR/table answer endpoint
- 8016: guided discovery endpoint
- 8017: router/proxy front door with Gemma visual route

OpenWebUI should point only at 8017:

  Base URL: http://127.0.0.1:8017/v1
  Model:    trace-net-router-proxy-v6-gemma-visual-v1

If OpenWebUI is running in Docker, use the host-reachable address for the same
8017 port, commonly:

  http://host.docker.internal:8017/v1

or the Linux Docker bridge host address, commonly:

  http://172.17.0.1:8017/v1
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


MODULE_NAME = "trace_net_openwebui_full_stack_launcher_v1"
STATUS_READY = "TRACE_NET_OPENWEBUI_FULL_STACK_LAUNCHER_V1_READY"

DEFAULT_VISUAL_DOCS = (
    "local_data/organization/trace_net/confirmed_image_gemma_visual_retrieval_cleaner_v1_full/"
    "trace_net_confirmed_image_gemma_visual_clean_retrieval_documents_v1.jsonl"
)
DEFAULT_RUNTIME_DIR = "local_data/organization/trace_net/openwebui_full_stack_launcher_v1_runtime"


def repo_root() -> Path:
    return Path.cwd()


def port_open(host: str, port: int, *, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_get_json(url: str, *, timeout: float = 1.5) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except Exception:
            return {"raw": text[:1000]}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_script(path: str) -> None:
    p = repo_root() / path
    if not p.exists():
        raise SystemExit(f"missing required script: {path}")


def open_log(runtime_dir: Path, name: str):
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return (runtime_dir / f"{name}.log").open("a", encoding="utf-8")


def start_process(
    *,
    name: str,
    cmd: List[str],
    runtime_dir: Path,
    skip_if_port_open: Optional[int],
    host: str,
) -> Optional[subprocess.Popen]:
    if skip_if_port_open and port_open(host, skip_if_port_open):
        print(f"[{name}] port {skip_if_port_open} already open; not starting duplicate")
        return None

    log = open_log(runtime_dir, name)
    log.write("\n\n=== START " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===\n")
    log.write("CMD: " + " ".join(cmd) + "\n")
    log.flush()

    print(f"[{name}] starting")
    print("  " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_root()),
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return proc


def wait_for_health(name: str, url: str, *, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        last = http_get_json(url, timeout=1.0)
        if "error" not in last:
            print(f"[{name}] health ok")
            return True
        time.sleep(0.75)
    print(f"[{name}] health failed: {last}")
    return False


def build_commands(args: argparse.Namespace) -> Dict[str, List[str]]:
    py = sys.executable

    normal_cmd = [
        py,
        "-B",
        "scripts/operations/serving/serve_trace_net_e2e_local_endpoint_v1.py",
        "--host",
        args.host,
        "--port",
        str(args.normal_port),
    ]
    if args.normal_extra_args:
        normal_cmd.extend(args.normal_extra_args)

    guided_cmd = [
        py,
        "-B",
        "scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v6.py",
        "--host",
        args.host,
        "--port",
        str(args.guided_port),
        "--normal-base-url",
        f"http://{args.host}:{args.normal_port}",
        "--guided-base-url",
        f"http://{args.host}:{args.guided_port}",
        "--model",
        "trace-net-guided-discovery-router-proxy-v6",
    ]
    if args.guided_extra_args:
        guided_cmd.extend(args.guided_extra_args)

    router_cmd = [
        py,
        "-B",
        "scripts/operations/visual/serve_trace_net_router_proxy_v6_gemma_visual_v1.py",
        "--host",
        args.host,
        "--port",
        str(args.router_port),
        "--normal-base-url",
        f"http://{args.host}:{args.normal_port}",
        "--guided-base-url",
        f"http://{args.host}:{args.guided_port}",
        "--gemma-visual-retrieval-documents-jsonl",
        args.gemma_visual_retrieval_documents_jsonl,
        "--visual-top-k",
        str(args.visual_top_k),
        "--visual-min-score",
        str(args.visual_min_score),
        "--model",
        args.model,
    ]

    return {
        "normal": normal_cmd,
        "guided": guided_cmd,
        "router": router_cmd,
    }


def create_connection_info(args: argparse.Namespace, runtime_dir: Path) -> Dict[str, Any]:
    info = {
        "module": MODULE_NAME,
        "status": STATUS_READY,
        "openwebui": {
            "connect_to_one_front_door_only": True,
            "base_url_same_host": f"http://{args.host}:{args.router_port}/v1",
            "base_url_docker_option_1": f"http://host.docker.internal:{args.router_port}/v1",
            "base_url_docker_option_2_linux_bridge": f"http://172.17.0.1:{args.router_port}/v1",
            "api_key": "trace-net-local",
            "model": args.model,
        },
        "internal_routes": {
            "normal_exact_ocr_table": f"http://{args.host}:{args.normal_port}",
            "guided_discovery": f"http://{args.host}:{args.guided_port}",
            "router_front_door": f"http://{args.host}:{args.router_port}",
            "gemma_visual_route_inside_router": "gemma_confirmed_image_visual",
        },
        "test_prompts": [
            {
                "prompt": "Show figure references for passenger seat assembly diagram",
                "expected_route": "gemma_confirmed_image_visual",
            },
            {
                "prompt": "Find diagram for part number 120-41824-003",
                "expected_route": "gemma_confirmed_image_visual",
            },
            {
                "prompt": "Find part number 120-41824-003",
                "expected_route": "normal_ask",
            },
            {
                "prompt": "I only know the part starts with 24",
                "expected_route": "guided_discovery",
            },
        ],
        "runtime_dir": str(runtime_dir),
    }
    write_json(runtime_dir / "openwebui_connection_info.json", info)
    return info


def print_connection_info(info: Dict[str, Any]) -> None:
    ow = info["openwebui"]
    print("\n=== OpenWebUI connection ===")
    print("Use ONE connection, the router front door:")
    print(f"Base URL same host: {ow['base_url_same_host']}")
    print(f"Base URL Docker option 1: {ow['base_url_docker_option_1']}")
    print(f"Base URL Docker option 2 Linux bridge: {ow['base_url_docker_option_2_linux_bridge']}")
    print(f"API key: {ow['api_key']}")
    print(f"Model: {ow['model']}")
    print("\nDo not connect OpenWebUI separately to 8014 and 8016.")
    print("8014 and 8016 are internal tools behind the 8017 router.")


def validate_required_files(args: argparse.Namespace) -> None:
    ensure_script("scripts/operations/serving/serve_trace_net_e2e_local_endpoint_v1.py")
    ensure_script("scripts/operations/router/serve_trace_net_guided_discovery_router_proxy_v6.py")
    ensure_script("scripts/operations/visual/serve_trace_net_router_proxy_v6_gemma_visual_v1.py")
    docs = repo_root() / args.gemma_visual_retrieval_documents_jsonl
    if not docs.exists():
        raise SystemExit(f"missing Gemma visual retrieval docs: {args.gemma_visual_retrieval_documents_jsonl}")


def run_stack(args: argparse.Namespace) -> int:
    validate_required_files(args)

    runtime_dir = Path(args.runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    commands = build_commands(args)
    write_json(runtime_dir / "launch_commands.json", commands)

    processes: List[subprocess.Popen] = []
    try:
        if not args.skip_normal:
            proc = start_process(
                name="normal_8014",
                cmd=commands["normal"],
                runtime_dir=runtime_dir,
                skip_if_port_open=args.normal_port,
                host=args.host,
            )
            if proc:
                processes.append(proc)

        if not args.skip_guided:
            proc = start_process(
                name="guided_8016",
                cmd=commands["guided"],
                runtime_dir=runtime_dir,
                skip_if_port_open=args.guided_port,
                host=args.host,
            )
            if proc:
                processes.append(proc)

        proc = start_process(
            name="router_8017",
            cmd=commands["router"],
            runtime_dir=runtime_dir,
            skip_if_port_open=args.router_port if args.skip_if_router_running else None,
            host=args.host,
        )
        if proc:
            processes.append(proc)

        health = {
            "normal": wait_for_health("normal_8014", f"http://{args.host}:{args.normal_port}/health", timeout_seconds=args.health_timeout_seconds),
            "guided": wait_for_health("guided_8016", f"http://{args.host}:{args.guided_port}/health", timeout_seconds=args.health_timeout_seconds),
            "router": wait_for_health("router_8017", f"http://{args.host}:{args.router_port}/health", timeout_seconds=args.health_timeout_seconds),
        }
        write_json(runtime_dir / "health_summary.json", health)

        info = create_connection_info(args, runtime_dir)
        print_connection_info(info)

        if args.exit_after_health:
            return 0 if all(health.values()) else 2

        print("\nStack is running. Press Ctrl+C to stop processes started by this launcher.")
        while True:
            for proc in list(processes):
                if proc.poll() is not None:
                    print(f"process exited with code {proc.returncode}")
                    return int(proc.returncode or 0)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping TRACE-Net OpenWebUI stack...")
    finally:
        for proc in processes:
            if proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGTERM)
                except Exception:
                    proc.terminate()
        time.sleep(1.0)
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--normal-port", type=int, default=8014)
    p.add_argument("--guided-port", type=int, default=8016)
    p.add_argument("--router-port", type=int, default=8017)
    p.add_argument("--model", default="trace-net-router-proxy-v6-gemma-visual-v1")
    p.add_argument("--gemma-visual-retrieval-documents-jsonl", default=DEFAULT_VISUAL_DOCS)
    p.add_argument("--runtime-dir", default=DEFAULT_RUNTIME_DIR)
    p.add_argument("--visual-top-k", type=int, default=8)
    p.add_argument("--visual-min-score", type=float, default=0.001)
    p.add_argument("--health-timeout-seconds", type=float, default=20.0)
    p.add_argument("--skip-normal", action="store_true")
    p.add_argument("--skip-guided", action="store_true")
    p.add_argument("--skip-if-router-running", action="store_true")
    p.add_argument("--exit-after-health", action="store_true")
    p.add_argument("--normal-extra-args", nargs=argparse.REMAINDER, default=[])
    p.add_argument("--guided-extra-args", nargs=argparse.REMAINDER, default=[])
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return run_stack(args)


if __name__ == "__main__":
    raise SystemExit(main())
