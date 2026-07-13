#!/usr/bin/env python3
"""Launch TRACE-Net truthful OpenWebUI full stack v2.

8014: v27 live source-truth normal route
8016: real guided candidate-discovery endpoint
8017: authenticated unified OpenWebUI front door

Only 8017 may be exposed to the network. Keep 8014 and 8016 on 127.0.0.1.
Qdrant is optional by default for coworker/API use and may be required explicitly
with --require-qdrant.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MODEL_ID = "trace-net-openwebui-unified-rag-v2"
RUNTIME_DIR = Path("local_data/organization/trace_net/openwebui_truthful_live_stack_v2_runtime")
DEFAULT_V27 = "local_data/organization/trace_net/e2e_live_orchestrator_stage_timing_fastpath/trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.json"
DEFAULT_VISUAL = "local_data/organization/trace_net/confirmed_image_gemma_visual_retrieval_cleaner_v1_full/trace_net_confirmed_image_gemma_visual_clean_retrieval_documents_v1.jsonl"
DEFAULT_ENGRAM = "local_data/organization/trace_net/engineering_engram_core_v1/trace_net_engineering_engram_core_v1.json"


def http_json(url: str, api_key: Optional[str] = None, timeout: float = 3.0) -> Tuple[int, Dict[str, Any]]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            value = json.loads(resp.read().decode("utf-8"))
            return resp.status, value if isinstance(value, dict) else {}
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def ensure(path: str) -> None:
    if not Path(path).exists():
        raise SystemExit(f"Missing required path: {path}")


def expected_identity(port: int) -> Optional[str]:
    return {
        8014: "trace_net_live_rag_normal_v2",
        8016: "trace_net_guided_candidate_discovery_endpoint_v1",
        8017: "trace_net_openwebui_unified_rag_v2",
    }.get(port)


def service_identity(health: Mapping[str, Any]) -> str:
    return str(health.get("module") or health.get("service") or "")


def start(name: str, cmd: List[str], port: int, api_key: str, processes: List[subprocess.Popen], runtime_dir: Path) -> None:
    if port_open("127.0.0.1", port):
        status, health = http_json(f"http://127.0.0.1:{port}/health", timeout=2)
        identity = service_identity(health)
        if status == 200 and identity == expected_identity(port):
            print(f"[{name}] already running with correct identity; reusing")
            return
        raise SystemExit(
            f"Port {port} is occupied by the wrong or unhealthy service. "
            f"Expected {expected_identity(port)!r}, observed {identity!r}. Stop the old stack first."
        )
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log = (runtime_dir / f"{name}.log").open("a", encoding="utf-8")
    log.write("\n=== START " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===\n")
    log.write("CMD: " + " ".join(cmd) + "\n")
    log.flush()
    print(f"[{name}] starting")
    proc = subprocess.Popen(cmd, cwd=str(Path.cwd()), stdout=log, stderr=subprocess.STDOUT, text=True)
    processes.append(proc)


def wait_identity(name: str, port: int, timeout: float) -> Dict[str, Any]:
    deadline = time.time() + timeout
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        status, last = http_json(f"http://127.0.0.1:{port}/health", timeout=2)
        if status == 200 and service_identity(last) == expected_identity(port) and last.get("quality_status") == "PASS":
            print(f"[{name}] health and identity PASS")
            return last
        time.sleep(0.75)
    raise SystemExit(f"{name} failed health/identity check: {last}")


def build_commands(args: argparse.Namespace) -> Dict[str, List[str]]:
    py = sys.executable
    normal = [
        py, "-B", "scripts/serve_trace_net_live_rag_normal_v2.py",
        "--host", "127.0.0.1", "--port", "8014",
        "--live-orchestrator-stage-timing-fastpath", args.v27_manifest,
        "--llm-mode", "ollama",
        "--llm-base-url", args.llm_base_url,
        "--llm-model", args.llm_model,
        "--llm-api-key", args.llm_api_key,
        "--request-timeout", str(args.request_timeout),
        "--fast-path-mode", "exact",
        "--api-key", args.api_key,
    ]
    guided = [
        py, "-B", "scripts/serve_trace_net_guided_candidate_discovery_endpoint_v1.py",
        "--host", "127.0.0.1", "--port", "8016",
        "--artifact-root", args.artifact_root,
        "--output-dir", "",
        "--max-files", str(args.guided_max_files),
        "--top-k", "8", "--loose-top-k", "8",
        "--no-view",
    ]
    unified = [
        py, "-B", "scripts/serve_trace_net_openwebui_unified_rag_v2.py",
        "--host", args.front_door_host, "--port", "8017",
        "--normal-base-url", "http://127.0.0.1:8014",
        "--guided-base-url", "http://127.0.0.1:8016",
        "--visual-documents-jsonl", args.visual_documents,
        "--engram-core-json", args.engram_core,
        "--qdrant-url", args.qdrant_url,
        "--qdrant-collection", args.qdrant_collection,
        "--ollama-url", args.ollama_url,
        "--embedding-model", args.embedding_model,
        "--api-key", args.api_key,
        "--downstream-api-key", args.api_key,
        "--timeout-seconds", str(args.request_timeout),
    ]
    if args.require_qdrant:
        unified.append("--require-qdrant")
    return {"normal_8014": normal, "guided_8016": guided, "unified_8017": unified}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v27-manifest", default=DEFAULT_V27)
    p.add_argument("--visual-documents", default=DEFAULT_VISUAL)
    p.add_argument("--engram-core", default=DEFAULT_ENGRAM)
    p.add_argument("--artifact-root", default="local_data/organization/trace_net")
    p.add_argument("--api-key", default=os.environ.get("TRACE_NET_API_KEY", "trace-net-local"))
    p.add_argument(
        "--front-door-host",
        default=os.environ.get("TRACE_NET_FRONT_DOOR_HOST", "127.0.0.1"),
        help="Bind address for external port 8017 only. Use 0.0.0.0 for LAN access.",
    )
    p.add_argument(
        "--require-qdrant",
        action="store_true",
        help="Fail startup unless Qdrant is healthy. Omit for coworker/API mode where Qdrant is optional guidance.",
    )
    p.add_argument("--llm-base-url", default="http://127.0.0.1:11434/v1")
    p.add_argument("--llm-model", default="gemma4:26b")
    p.add_argument("--llm-api-key", default="ollama")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    p.add_argument("--embedding-model", default="bge-m3:latest")
    p.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    p.add_argument("--qdrant-collection", default="trace_net_ocr_v2_v3_bge_m3")
    p.add_argument("--request-timeout", type=int, default=240)
    p.add_argument("--guided-max-files", type=int, default=250000)
    p.add_argument("--health-timeout", type=float, default=30.0)
    p.add_argument("--exit-after-health", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.front_door_host not in {"127.0.0.1", "0.0.0.0", "::"}:
        raise SystemExit(
            "--front-door-host must be 127.0.0.1, 0.0.0.0, or ::. "
            "Use 0.0.0.0 for IPv4 LAN access."
        )

    for path in (
        args.v27_manifest, args.visual_documents, args.engram_core,
        "scripts/serve_trace_net_live_rag_normal_v2.py",
        "scripts/serve_trace_net_guided_candidate_discovery_endpoint_v1.py",
        "scripts/serve_trace_net_openwebui_unified_rag_v2.py",
    ):
        ensure(path)

    commands = build_commands(args)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "launch_commands.json").write_text(json.dumps(commands, indent=2), encoding="utf-8")
    processes: List[subprocess.Popen] = []
    try:
        start("normal_8014", commands["normal_8014"], 8014, args.api_key, processes, RUNTIME_DIR)
        normal_health = wait_identity("normal_8014", 8014, args.health_timeout)
        start("guided_8016", commands["guided_8016"], 8016, args.api_key, processes, RUNTIME_DIR)
        guided_health = wait_identity("guided_8016", 8016, args.health_timeout)
        start("unified_8017", commands["unified_8017"], 8017, args.api_key, processes, RUNTIME_DIR)
        unified_health = wait_identity("unified_8017", 8017, args.health_timeout)

        network_url = (
            "http://10.100.1.238:8017/v1"
            if args.front_door_host in {"0.0.0.0", "::"}
            else "not exposed; bound to localhost"
        )
        summary = {
            "status": "TRACE_NET_OPENWEBUI_TRUTHFUL_LIVE_STACK_V2_READY",
            "quality_status": "PASS",
            "services": {"normal": normal_health, "guided": guided_health, "unified": unified_health},
            "openwebui": {
                "base_url": "http://127.0.0.1:8017/v1",
                "network_base_url": network_url,
                "front_door_host": args.front_door_host,
                "api_key": args.api_key,
                "model": MODEL_ID,
            },
            "qdrant": {
                "required": bool(args.require_qdrant),
                "mode": "required" if args.require_qdrant else "optional_guidance",
            },
        }
        (RUNTIME_DIR / "health_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("\nstatus=TRACE_NET_OPENWEBUI_TRUTHFUL_LIVE_STACK_V2_READY")
        print("quality_status=PASS")
        print("OpenWebUI Base URL: http://127.0.0.1:8017/v1")
        print(f"Front-door bind: {args.front_door_host}:8017")
        print(f"Network Base URL: {network_url}")
        print(f"Qdrant mode: {'required' if args.require_qdrant else 'optional guidance'}")
        print(f"API key: {args.api_key}")
        print(f"Model: {MODEL_ID}")
        if args.exit_after_health:
            return 0
        print("Stack is running. Press Ctrl+C to stop processes started by this launcher.")
        while True:
            for proc in processes:
                if proc.poll() is not None:
                    raise SystemExit(f"A stack process exited with code {proc.returncode}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping TRACE-Net truthful live stack v2...")
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        time.sleep(1)
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
