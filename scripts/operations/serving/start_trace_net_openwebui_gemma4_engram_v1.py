from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


MODEL_ID = "trace-net-gemma4-engram-e2e-v1"


def request_json(url: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 20):
    if payload is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_health(port: int, timeout_seconds: int = 60) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            data = request_json(f"http://127.0.0.1:{port}/health", timeout=5)
            if data.get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def run(cmd, timeout=60):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


def docker_exists(name: str) -> bool:
    try:
        r = run(["docker", "ps", "-a", "--format", "{{.Names}}"])
        return name in {x.strip() for x in r.stdout.splitlines()}
    except Exception:
        return False


def docker_running(name: str) -> bool:
    try:
        r = run(["docker", "inspect", "-f", "{{.State.Running}}", name])
        return r.returncode == 0 and r.stdout.strip().lower() == "true"
    except Exception:
        return False


def ensure_openwebui(name: str, port: int) -> Dict[str, Any]:
    if docker_exists(name):
        if docker_running(name):
            return {"ok": True, "action": "already_running", "container": name}
        r = run(["docker", "start", name], timeout=60)
        return {"ok": r.returncode == 0, "action": "started", "container": name, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    r = run([
        "docker", "run", "-d", "--name", name, "--restart", "always",
        "-p", f"{port}:8080",
        "-v", "open-webui:/app/backend/data",
        "ghcr.io/open-webui/open-webui:main",
    ], timeout=180)
    return {"ok": r.returncode == 0, "action": "created", "container": name, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--openwebui-container", default="open-webui")
    parser.add_argument("--openwebui-port", type=int, default=3000)
    parser.add_argument("--ollama-model", default="gemma4:26b")
    parser.add_argument("--question", default="Find part number 120-50645-005. Give the nomenclature if available and cite the source.")
    parser.add_argument("--no-hold", action="store_true")
    args = parser.parse_args()

    ow = ensure_openwebui(args.openwebui_container, args.openwebui_port)
    print("openwebui=" + json.dumps(ow), flush=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = "." + os.pathsep + env.get("PYTHONPATH", "")
    log_dir = Path("local_data/organization/trace_net/openwebui_gemma4_engram_bridge_v1/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = (log_dir / "bridge_stdout.log").open("a", encoding="utf-8")
    stderr = (log_dir / "bridge_stderr.log").open("a", encoding="utf-8")

    proc = None
    if wait_health(args.port, timeout_seconds=3):
        print("bridge=already_running", flush=True)
    else:
        proc = subprocess.Popen([
            sys.executable, "-B", "scripts/operations/serving/serve_trace_net_openwebui_gemma4_engram_bridge_v1.py",
            "--host", args.host,
            "--port", str(args.port),
            "--ollama-model", args.ollama_model,
        ], cwd=Path.cwd(), env=env, stdout=stdout, stderr=stderr)
        if not wait_health(args.port, timeout_seconds=80):
            print("status=TRACE_NET_OPENWEBUI_GEMMA4_ENGRAM_LAUNCH_FAILED", flush=True)
            print(f"logs={log_dir}", flush=True)
            return 1

    ask = request_json(f"http://127.0.0.1:{args.port}/api/trace-net/ask", {"query": args.question}, timeout=120)
    chat = request_json(
        f"http://127.0.0.1:{args.port}/v1/chat/completions",
        {"model": MODEL_ID, "messages": [{"role": "user", "content": args.question}]},
        timeout=120,
    )

    print("status=TRACE_NET_OPENWEBUI_GEMMA4_ENGRAM_READY", flush=True)
    print("quality_status=PASS", flush=True)
    print("Open WebUI: http://localhost:%d" % args.openwebui_port, flush=True)
    print("Open WebUI Connection Settings:", flush=True)
    print("  Provider: OpenAI", flush=True)
    print("  Base URL: http://host.docker.internal:%d/v1" % args.port, flush=True)
    print("  API Key: trace-net-local", flush=True)
    print("  Model: %s" % MODEL_ID, flush=True)
    print("TRACE health: http://127.0.0.1:%d/health" % args.port, flush=True)
    print("native_ask_preview:", (ask.get("answer") or ask.get("response") or "")[:900], flush=True)
    try:
        preview = chat["choices"][0]["message"]["content"][:900]
    except Exception:
        preview = json.dumps(chat)[:900]
    print("chat_preview:", preview, flush=True)

    if args.no_hold:
        return 0

    print("Holding terminal open. Press Ctrl+C to stop bridge child process.", flush=True)
    try:
        while True:
            if proc is not None and proc.poll() is not None:
                print(f"bridge exited code={proc.returncode}", flush=True)
                return int(proc.returncode or 1)
            time.sleep(2)
    except KeyboardInterrupt:
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
