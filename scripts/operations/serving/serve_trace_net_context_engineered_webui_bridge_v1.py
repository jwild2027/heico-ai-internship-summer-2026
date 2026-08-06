from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def _extract_user_question(payload: dict) -> str:
    messages = payload.get("messages") or []
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                return "\n".join(parts).strip()
    return ""


def _extract_part_number(question: str) -> str | None:
    match = PART_RE.search(question or "")
    return match.group(0) if match else None


def _run_context_engineered_trace(args: argparse.Namespace, question: str, part_number: str) -> tuple[str, dict]:
    run_id = str(int(time.time()))
    output_dir = Path(args.output_root) / f"webui_context_engineered_{part_number.replace('-', '_')}_{run_id}"

    cmd = [
        "python",
        "scripts/operations/validation/run_trace_net_raw_to_answer_context_engineered_native_v1.py",
        "--source-package",
        args.source_package,
        "--tesseract-cmd",
        args.tesseract_cmd,
        "--output-dir",
        str(output_dir),
        "--question",
        question,
        "--part-number",
        part_number,
        "--llm-base-url",
        args.ollama_base_url,
        "--llm-model",
        args.ollama_model,
        "--llm-think",
        "false",
        "--llm-num-predict",
        str(args.llm_num_predict),
        "--request-timeout",
        str(args.runner_timeout),
        "--require-source-quality-pass",
        "--require-anchor-communities",
        "--require-llm-success",
        "--quality",
    ]

    proc = subprocess.run(
        cmd,
        cwd=args.repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=args.runner_timeout + 60,
    )

    report_path = output_dir / "trace_net_raw_to_answer_context_engineered_native_v1.json"
    answer_path = output_dir / "trace_net_raw_to_answer_context_engineered_native_v1_answer.md"

    meta = {
        "output_dir": str(output_dir),
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }

    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            meta["summary"] = report.get("summary", {})
            meta["quality_status"] = report.get("quality_status")
        except Exception as exc:
            meta["report_read_error"] = str(exc)

    if answer_path.exists():
        answer = answer_path.read_text(encoding="utf-8", errors="replace").strip()
    else:
        answer = ""

    if proc.returncode != 0:
        answer = (
            "TRACE-Net context-engineered run failed.\n\n"
            f"Output dir: `{output_dir}`\n\n"
            f"STDOUT tail:\n```text\n{proc.stdout[-2000:]}\n```\n\n"
            f"STDERR tail:\n```text\n{proc.stderr[-2000:]}\n```"
        )

    if not answer:
        answer = (
            "TRACE-Net context-engineered run completed, but no answer file was produced.\n\n"
            f"Output dir: `{output_dir}`"
        )

    return answer, meta


class TraceNetHandler(BaseHTTPRequestHandler):
    server_version = "TRACE-Net-WebUI-Bridge/1.0"

    def do_OPTIONS(self):
        _json_response(self, 200, {"ok": True})

    def do_GET(self):
        if self.path in ["/health", "/v1/health"]:
            _json_response(self, 200, {
                "status": "ok",
                "model": self.server.args.model_name,
                "context_engineering": "enabled",
            })
            return

        if self.path in ["/v1/models", "/models"]:
            _json_response(self, 200, {
                "object": "list",
                "data": [
                    {
                        "id": self.server.args.model_name,
                        "object": "model",
                        "owned_by": "trace-net",
                    }
                ],
            })
            return

        _json_response(self, 404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ["/v1/chat/completions", "/chat/completions"]:
            _json_response(self, 404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            payload = json.loads(raw or "{}")
        except Exception as exc:
            _json_response(self, 400, {"error": f"invalid JSON: {exc}"})
            return

        question = _extract_user_question(payload)
        if not question:
            _json_response(self, 400, {"error": "No user question found in messages."})
            return

        part_number = _extract_part_number(question)
        if not part_number:
            content = (
                "TRACE-Net context-engineered WebUI bridge is currently configured for exact part-number questions. "
                "Ask with a part number like `120-29073-001` so the exact OCR/table probe can anchor the context first."
            )
            _json_response(self, 200, {
                "id": f"chatcmpl-tracenet-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self.server.args.model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })
            return

        try:
            answer, meta = _run_context_engineered_trace(self.server.args, question, part_number)
        except subprocess.TimeoutExpired as exc:
            answer = (
                "TRACE-Net context-engineered run timed out.\n\n"
                f"Part number: `{part_number}`\n"
                f"Timeout: `{self.server.args.runner_timeout}` seconds\n\n"
                "Try raising `--runner-timeout` or run the CLI directly first."
            )
            meta = {"error": "timeout", "exception": str(exc)}
        except Exception as exc:
            answer = f"TRACE-Net context-engineered run failed before completion:\n\n```text\n{exc}\n```"
            meta = {"error": "exception", "exception": str(exc)}

        _json_response(self, 200, {
            "id": f"chatcmpl-tracenet-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.server.args.model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": len(answer.split()),
                "total_tokens": len(answer.split()),
            },
            "trace_net": meta,
        })


class TraceNetServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_class, args):
        super().__init__(server_address, handler_class)
        self.args = args


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8021)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--source-package", required=True)
    parser.add_argument("--tesseract-cmd", required=True)
    parser.add_argument("--output-root", default="local_data/organization/trace_net/webui_context_engineered_runs")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-model", default="gemma4:26b")
    parser.add_argument("--llm-num-predict", type=int, default=1200)
    parser.add_argument("--runner-timeout", type=int, default=900)
    parser.add_argument("--model-name", default="trace-net-context-engineered-native-v1")
    args = parser.parse_args()

    Path(args.output_root).mkdir(parents=True, exist_ok=True)

    server = TraceNetServer((args.host, args.port), TraceNetHandler, args)
    print(f"TRACE-Net WebUI bridge running at http://{args.host}:{args.port}")
    print(f"OpenAI-compatible base URL: http://{args.host}:{args.port}/v1")
    print(f"Model: {args.model_name}")
    server.serve_forever()


if __name__ == "__main__":
    main()
