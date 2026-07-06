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
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MODULE = "trace_net_openwebui_e2e_launcher_v1"
VERSION = "v1"
DEFAULT_MODEL = "trace-net-e2e-local-endpoint-v1"
DEFAULT_QUESTION = "Find part number 120-50645-005. Give the nomenclature if available and cite the source."


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _run(cmd: List[str], timeout: int = 60, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=check,
    )


def _json_request(url: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 20) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        if payload is None:
            req = urllib.request.Request(url)
        else:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body), ""
        except Exception:
            return {"raw_body": body}, ""
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return None, f"HTTPError {exc.code}: {exc.reason}; body={body[:1000]}"
    except Exception as exc:
        return None, repr(exc)


def endpoint_health_url(host_for_client: str, port: int) -> str:
    return f"http://{host_for_client}:{port}/health"


def endpoint_chat_url(host_for_client: str, port: int) -> str:
    return f"http://{host_for_client}:{port}/v1/chat/completions"


def endpoint_ask_url(host_for_client: str, port: int) -> str:
    return f"http://{host_for_client}:{port}/api/trace-net/ask"


def endpoint_models_url(host_for_client: str, port: int) -> str:
    return f"http://{host_for_client}:{port}/v1/models"


def openwebui_url(openwebui_port: int) -> str:
    return f"http://localhost:{openwebui_port}"


def openai_base_url_for_openwebui(port: int) -> str:
    # Docker Desktop containers should use host.docker.internal to reach a Windows host process.
    return f"http://host.docker.internal:{port}/v1"


def openai_base_url_for_windows(port: int) -> str:
    return f"http://127.0.0.1:{port}/v1"


def docker_available() -> bool:
    try:
        result = _run(["docker", "version"], timeout=20)
        return result.returncode == 0
    except Exception:
        return False


def docker_container_exists(name: str) -> bool:
    try:
        result = _run(["docker", "ps", "-a", "--format", "{{.Names}}"], timeout=20)
        names = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        return name in names
    except Exception:
        return False


def docker_container_running(name: str) -> bool:
    try:
        result = _run(["docker", "inspect", "-f", "{{.State.Running}}", name], timeout=20)
        return result.returncode == 0 and result.stdout.strip().lower() == "true"
    except Exception:
        return False


def start_existing_container(name: str) -> Dict[str, Any]:
    if docker_container_running(name):
        return {"container": name, "action": "already_running", "ok": True}

    if not docker_container_exists(name):
        return {"container": name, "action": "missing", "ok": False}

    result = _run(["docker", "start", name], timeout=60)
    return {
        "container": name,
        "action": "started",
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def ensure_openwebui_container(
    container_name: str,
    port: int,
    create_if_missing: bool = True,
    image: str = "ghcr.io/open-webui/open-webui:main",
) -> Dict[str, Any]:
    if not docker_available():
        return {"container": container_name, "ok": False, "action": "docker_unavailable"}

    if docker_container_exists(container_name):
        return start_existing_container(container_name)

    if not create_if_missing:
        return {"container": container_name, "ok": False, "action": "missing_create_disabled"}

    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--restart", "always",
        "-p", f"{port}:8080",
        "-v", "open-webui:/app/backend/data",
        image,
    ]
    result = _run(cmd, timeout=180)
    return {
        "container": container_name,
        "action": "created",
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def wait_http_ok(url: str, timeout_seconds: int = 60) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    data = None
    while time.time() < deadline:
        data, err = _json_request(url, timeout=5)
        if not err and data is not None:
            return True, "", data
        last_error = err
        time.sleep(1.0)
    return False, last_error, data


def start_trace_endpoint(
    host: str,
    port: int,
    log_dir: Path,
    python_exe: str = sys.executable,
) -> Tuple[Optional[subprocess.Popen], Dict[str, Any]]:
    health, _, data = wait_http_ok(endpoint_health_url("127.0.0.1", port), timeout_seconds=3)
    if health:
        return None, {"action": "already_running", "ok": True, "health": data}

    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "trace_net_endpoint_stdout.log"
    stderr_path = log_dir / "trace_net_endpoint_stderr.log"

    env = os.environ.copy()
    env["PYTHONPATH"] = "." + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [
        python_exe,
        "-B",
        "scripts/serve_trace_net_e2e_local_endpoint_v1.py",
        "--host",
        host,
        "--port",
        str(port),
    ]

    stdout_f = stdout_path.open("a", encoding="utf-8")
    stderr_f = stderr_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        stdout=stdout_f,
        stderr=stderr_f,
        env=env,
        cwd=Path.cwd(),
    )

    ok, err, health_data = wait_http_ok(endpoint_health_url("127.0.0.1", port), timeout_seconds=60)
    return proc, {
        "action": "started",
        "ok": ok,
        "pid": proc.pid,
        "health_error": err,
        "health": health_data,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "cmd": cmd,
    }


def test_trace_chat(port: int, model: str, question: str) -> Dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
    }
    data, err = _json_request(endpoint_chat_url("127.0.0.1", port), payload, timeout=60)
    return {"ok": err == "", "error": err, "response": data}


def test_trace_ask(port: int, question: str) -> Dict[str, Any]:
    payload = {"query": question}
    data, err = _json_request(endpoint_ask_url("127.0.0.1", port), payload, timeout=60)
    return {"ok": err == "", "error": err, "response": data}


def test_models_endpoint(port: int) -> Dict[str, Any]:
    data, err = _json_request(endpoint_models_url("127.0.0.1", port), timeout=20)
    return {"ok": err == "", "error": err, "response": data}


def summarize_chat_response(data: Optional[Dict[str, Any]]) -> str:
    if not data:
        return ""
    try:
        choices = data.get("choices") or []
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")[:900]
    except Exception:
        return json.dumps(data, ensure_ascii=False)[:900]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start TRACE-Net E2E endpoint + Open WebUI and smoke test the connection.")
    parser.add_argument("--trace-host", default="0.0.0.0")
    parser.add_argument("--trace-port", type=int, default=8014)
    parser.add_argument("--openwebui-container", default="open-webui")
    parser.add_argument("--openwebui-port", type=int, default=3000)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--create-openwebui-if-missing", action="store_true", default=True)
    parser.add_argument("--no-create-openwebui-if-missing", dest="create_openwebui_if_missing", action="store_false")
    parser.add_argument("--start-support-containers", action="store_true", help="Start existing trace-net-qdrant and trace-net-postg containers too.")
    parser.add_argument("--start-opensearch", action="store_true", help="Start existing trace-net-opens container too; not required for current artifact endpoint.")
    parser.add_argument("--qdrant-container", default="trace-net-qdrant")
    parser.add_argument("--postgres-container", default="trace-net-postg")
    parser.add_argument("--opensearch-container", default="trace-net-opens")
    parser.add_argument("--output-dir", default="local_data/organization/trace_net/openwebui_e2e_launcher_v1")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--no-hold", action="store_true", help="Exit after starting/testing. Without this, the launcher keeps the endpoint process alive.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir = output_dir / "logs"

    manifest: Dict[str, Any] = {
        "status": "TRACE_NET_OPENWEBUI_E2E_LAUNCHER_STARTED",
        "module": MODULE,
        "version": VERSION,
        "trace_endpoint": {
            "host": args.trace_host,
            "port": args.trace_port,
            "health_url": endpoint_health_url("127.0.0.1", args.trace_port),
            "chat_url": endpoint_chat_url("127.0.0.1", args.trace_port),
            "ask_url": endpoint_ask_url("127.0.0.1", args.trace_port),
        },
        "openwebui": {
            "container": args.openwebui_container,
            "url": openwebui_url(args.openwebui_port),
            "connection_settings": {
                "provider": "OpenAI",
                "base_url_for_docker_openwebui": openai_base_url_for_openwebui(args.trace_port),
                "base_url_for_windows_openwebui": openai_base_url_for_windows(args.trace_port),
                "api_key": "trace-net-local",
                "model": args.model,
            },
        },
        "support_containers": [],
        "smoke_tests": {},
        "safety_contract": {
            "launcher_no_source_truth_mutation": True,
            "launcher_no_postgres_writes": True,
            "launcher_no_qdrant_writes": True,
            "launcher_no_opensearch_writes": True,
            "endpoint_answer_permission_expected": False,
        },
    }

    print("=== TRACE-Net Open WebUI E2E Launcher ===", flush=True)

    support_results: List[Dict[str, Any]] = []
    if args.start_support_containers:
        support_results.append(start_existing_container(args.qdrant_container))
        support_results.append(start_existing_container(args.postgres_container))
    if args.start_opensearch:
        support_results.append(start_existing_container(args.opensearch_container))
    manifest["support_containers"] = support_results

    openwebui_result = ensure_openwebui_container(
        args.openwebui_container,
        args.openwebui_port,
        create_if_missing=args.create_openwebui_if_missing,
    )
    manifest["openwebui"]["container_start_result"] = openwebui_result
    print(f"openwebui_container={openwebui_result}", flush=True)

    proc: Optional[subprocess.Popen] = None
    try:
        proc, endpoint_result = start_trace_endpoint(args.trace_host, args.trace_port, log_dir)
        manifest["trace_endpoint"]["start_result"] = endpoint_result
        print(f"trace_endpoint={endpoint_result}", flush=True)

        if not endpoint_result.get("ok"):
            manifest["status"] = "TRACE_NET_OPENWEBUI_E2E_LAUNCHER_FAILED_ENDPOINT"
            _write_json(output_dir / f"{MODULE}.json", manifest)
            print("status=" + manifest["status"], flush=True)
            return 1

        models_result = test_models_endpoint(args.trace_port)
        ask_result = test_trace_ask(args.trace_port, args.question)
        chat_result = test_trace_chat(args.trace_port, args.model, args.question)
        manifest["smoke_tests"] = {
            "models": models_result,
            "native_ask": ask_result,
            "chat_completions": chat_result,
            "chat_response_preview": summarize_chat_response(chat_result.get("response")),
        }

        all_required_ok = ask_result.get("ok") and chat_result.get("ok")
        manifest["status"] = "TRACE_NET_OPENWEBUI_E2E_LAUNCHER_READY" if all_required_ok else "TRACE_NET_OPENWEBUI_E2E_LAUNCHER_SMOKE_FAILED"
        manifest["quality_status"] = "PASS" if all_required_ok else "FAIL"
        _write_json(output_dir / f"{MODULE}.json", manifest)

        print("\n=== READY INFO ===", flush=True)
        print(f"status={manifest['status']}", flush=True)
        print(f"quality_status={manifest['quality_status']}", flush=True)
        print(f"Open WebUI: {openwebui_url(args.openwebui_port)}", flush=True)
        print("Open WebUI connection settings:", flush=True)
        print(f"  Provider: OpenAI", flush=True)
        print(f"  Base URL: {openai_base_url_for_openwebui(args.trace_port)}", flush=True)
        print(f"  API Key: trace-net-local", flush=True)
        print(f"  Model: {args.model}", flush=True)
        print(f"TRACE health: {endpoint_health_url('127.0.0.1', args.trace_port)}", flush=True)
        print(f"TRACE chat: {endpoint_chat_url('127.0.0.1', args.trace_port)}", flush=True)
        print(f"native_ask_ok={ask_result.get('ok')}", flush=True)
        print(f"chat_completions_ok={chat_result.get('ok')}", flush=True)
        print(f"models_endpoint_ok={models_result.get('ok')}", flush=True)
        if not models_result.get("ok"):
            print("NOTE: /v1/models is missing or failed. If Open WebUI cannot discover the model, add the model manually or apply a /v1/models endpoint patch.", flush=True)
        print("\nAnswer preview:", flush=True)
        print(manifest["smoke_tests"]["chat_response_preview"], flush=True)
        print(f"\nmanifest={output_dir / (MODULE + '.json')}", flush=True)

        if args.open_browser:
            webbrowser.open(openwebui_url(args.openwebui_port))

        if args.no_hold:
            return 0 if all_required_ok else 1

        if proc is None:
            print("\nTRACE endpoint was already running. Launcher can exit safely with Ctrl+C.", flush=True)
        else:
            print("\nHolding terminal open to keep TRACE endpoint alive. Press Ctrl+C to stop endpoint child process.", flush=True)

        while True:
            if proc is not None and proc.poll() is not None:
                print(f"TRACE endpoint exited with code {proc.returncode}", flush=True)
                return int(proc.returncode or 1)
            time.sleep(2.0)

    except KeyboardInterrupt:
        print("\nStopping launcher...", flush=True)
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
        return 0
    finally:
        _write_json(output_dir / f"{MODULE}.json", manifest)


if __name__ == "__main__":
    raise SystemExit(main())
