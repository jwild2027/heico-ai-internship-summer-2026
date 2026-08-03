#!/usr/bin/env bash
set -euo pipefail

REPO="${TRACE_NET_REPO:-/data/trace_net/repos/heico-ai-internship-summer-2026}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="$VENV/bin/python"
RUNTIME="${TRACE_NET_RUNTIME_DIR:-/data/trace_net_runs/gemma_residency_watchdog_v2}"
BRIDGE_HOST="${TRACE_NET_BRIDGE_HOST:-172.17.0.1}"
COGNITIVE_URL="${TRACE_NET_COGNITIVE_URL:-http://127.0.0.1:8118}"
COGNITIVE_KEY="${TRACE_NET_COGNITIVE_KEY:-trace-net-cognitive-local}"
WRITER_KEY="${TRACE_NET_GEMMA_COGNITIVE_KEY:-trace-net-gemma-cognitive-local}"
PUBLIC_KEY="${TRACE_NET_OPENWEBUI_COGNITIVE_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_OPENWEBUI_COGNITIVE_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
GEMMA_MODEL="${TRACE_NET_GEMMA_MODEL:-gemma4:26b}"
GEMMA_KEEP_ALIVE="${TRACE_NET_GEMMA_KEEP_ALIVE:-1h}"
CHECK_INTERVAL="${TRACE_NET_GEMMA_RESIDENCY_CHECK_INTERVAL_SECONDS:-300}"
RENEW_BEFORE="${TRACE_NET_GEMMA_RENEW_BEFORE_SECONDS:-900}"
PRELOAD_TIMEOUT="${TRACE_NET_GEMMA_PRELOAD_TIMEOUT_SECONDS:-300}"
REQUIRE_RESIDENT="${TRACE_NET_GEMMA_REQUIRE_RESIDENT:-1}"
WATCHDOG_ENABLED="${TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_ENABLED:-1}"
WRITER_TIMEOUT="${TRACE_NET_GEMMA_WRITER_TIMEOUT_SECONDS:-300}"
WRITER_QUEUE_TIMEOUT="${TRACE_NET_GEMMA_WRITER_QUEUE_TIMEOUT_SECONDS:-120}"
PUBLIC_TIMEOUT="${TRACE_NET_PUBLIC_PROXY_TIMEOUT_SECONDS:-360}"
GEMMA_TIMEOUT="${TRACE_NET_PUBLIC_GEMMA_TIMEOUT_SECONDS:-240}"
GEMMA_MAX_TOKENS="${TRACE_NET_PUBLIC_GEMMA_MAX_TOKENS:-512}"
PHASE4_DIR="${TRACE_NET_NHA_PHASE4_DIR:-$REPO/release_data/trace_net/nha_real_release_v1/phase4}"
NHA_ENGRAM_DIR="${TRACE_NET_NHA_ENGRAM_DIR:-/data/trace_net_runs/nha_phase13_engram_v1}"
TELEMETRY_PATH="${TRACE_NET_NHA_TELEMETRY_PATH:-$RUNTIME/8131_residency_telemetry.jsonl}"

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$RUNTIME"

for required in \
  scripts/serve_trace_net_full_gemma_cognitive_v1.py \
  scripts/serve_trace_net_nha_phase16_gemma_proxy_v1.py \
  scripts/serve_trace_net_nha_phase16_gemma_proxy_v1_1.py \
  scripts/trace_net_h30_gemma_residency_watchdog_v2.py; do
  [[ -f "$required" ]] || { echo "missing_required_file=$required"; exit 2; }
done

[[ -d "$PHASE4_DIR" ]] || { echo "missing_phase4_dir=$PHASE4_DIR"; exit 2; }
[[ -d "$NHA_ENGRAM_DIR" ]] || { echo "missing_nha_engram_dir=$NHA_ENGRAM_DIR"; exit 2; }

for command in curl tmux fuser; do
  command -v "$command" >/dev/null || { echo "missing_command=$command"; exit 2; }
done

echo "============================================================"
echo "TRACE-NET GEMMA RESIDENCY STACK V2"
echo "============================================================"
echo "repo=$REPO"
echo "runtime=$RUNTIME"
echo "model=$GEMMA_MODEL"
echo "keep_alive=$GEMMA_KEEP_ALIVE"
echo "watchdog_interval_seconds=$CHECK_INTERVAL"
echo "renew_before_seconds=$RENEW_BEFORE"

echo
echo "=== 1. Verify existing cognitive router ==="
curl --fail-with-body --silent --show-error \
  "$COGNITIVE_URL/health" \
  | tee "$RUNTIME/8118_health_before.json" \
  | "$PYTHON" -m json.tool

echo
echo "=== 2. Compile focused residency files ==="
"$PYTHON" -m py_compile \
  scripts/trace_net_h30_gemma_residency_watchdog_v2.py \
  scripts/serve_trace_net_nha_phase16_gemma_proxy_v1_1.py \
  scripts/serve_trace_net_full_gemma_cognitive_v1.py \
  tests/unit/test_trace_net_h30_gemma_residency_watchdog_v2.py

echo "compile_status=PASS"

"$PYTHON" -m pytest -q -p no:cacheprovider \
  tests/unit/test_trace_net_h30_gemma_residency_watchdog_v2.py

echo "focused_test_status=PASS"

echo
echo "=== 3. Preload and verify Gemma residency ==="
"$PYTHON" - "$GEMMA_MODEL" "$GEMMA_KEEP_ALIVE" "$PRELOAD_TIMEOUT" "$RUNTIME/preload.json" <<'PY'
from pathlib import Path
import json
import sys
import time
import urllib.request

model, keep_alive, timeout, output = sys.argv[1:]
payload = {
    "model": model,
    "prompt": "",
    "stream": False,
    "keep_alive": keep_alive,
}
request = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
started = time.monotonic()
with urllib.request.urlopen(request, timeout=float(timeout)) as response:
    body = json.loads(response.read().decode("utf-8", errors="replace"))
preload_ms = round((time.monotonic() - started) * 1000.0, 3)
body["preload_ms"] = preload_ms
body["requested_keep_alive"] = keep_alive
Path(output).write_text(json.dumps(body, indent=2), encoding="utf-8")
print("gemma_preload_status=PASS")
print(f"gemma_preload_ms={preload_ms}")
PY

curl --fail-with-body --silent --show-error \
  http://127.0.0.1:11434/api/ps \
  > "$RUNTIME/ollama_ps_after_preload.json"

"$PYTHON" - "$GEMMA_MODEL" "$RUNTIME/ollama_ps_after_preload.json" <<'PY'
from pathlib import Path
import json
import sys
model, path = sys.argv[1:]
data = json.loads(Path(path).read_text(encoding="utf-8"))
rows = [row for row in data.get("models") or [] if isinstance(row, dict)]
names = {str(row.get("name") or row.get("model") or "") for row in rows}
print("ollama_loaded_models=" + ",".join(sorted(names)))
if model not in names:
    raise SystemExit(f"gemma_resident_status=FAIL missing={model}")
row = next(row for row in rows if str(row.get("name") or row.get("model") or "") == model)
print("gemma_resident_status=PASS")
print(f"gemma_resident_expires_at={row.get('expires_at')}")
print(f"gemma_size_vram={row.get('size_vram')}")
PY

stop_port() {
  local session="$1"
  local port="$2"
  tmux has-session -t "$session" 2>/dev/null && tmux kill-session -t "$session" || true
  fuser -k -TERM "${port}/tcp" 2>/dev/null || true
  sleep 2
  if fuser "${port}/tcp" >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

echo
echo "=== 4. Restart only writer 8128 and public proxy 8131 ==="
stop_port trace-net-gemma-cognitive-8128 8128
stop_port trace-net-openwebui-cognitive-8131 8131

COMMON_ENV="export TRACE_NET_GEMMA_KEEP_ALIVE='$GEMMA_KEEP_ALIVE'; export TRACE_NET_GEMMA_RESIDENCY_WATCHDOG_ENABLED='$WATCHDOG_ENABLED'; export TRACE_NET_GEMMA_REQUIRE_RESIDENT='$REQUIRE_RESIDENT'; export TRACE_NET_GEMMA_RESIDENCY_CHECK_INTERVAL_SECONDS='$CHECK_INTERVAL'; export TRACE_NET_GEMMA_RENEW_BEFORE_SECONDS='$RENEW_BEFORE'; export TRACE_NET_GEMMA_PRELOAD_TIMEOUT_SECONDS='$PRELOAD_TIMEOUT'"

tmux new-session -d -s trace-net-gemma-cognitive-8128 \
  "cd '$REPO' && source '$VENV/bin/activate' && export PYTHONPATH='$REPO/scripts:$REPO' && $COMMON_ENV; exec '$PYTHON' -u -B scripts/serve_trace_net_full_gemma_cognitive_v1.py --host 127.0.0.1 --port 8128 --cognitive-base-url '$COGNITIVE_URL' --cognitive-api-key '$COGNITIVE_KEY' --gemma-base-url http://127.0.0.1:11434/v1 --gemma-api-key ollama --gemma-model '$GEMMA_MODEL' --api-key '$WRITER_KEY' --timeout-seconds '$WRITER_TIMEOUT' --max-concurrency 1 --queue-timeout-seconds '$WRITER_QUEUE_TIMEOUT' 2>&1 | tee '$RUNTIME/8128.log'"

tmux new-session -d -s trace-net-openwebui-cognitive-8131 \
  "cd '$REPO' && source '$VENV/bin/activate' && export PYTHONPATH='$REPO/scripts:$REPO' && $COMMON_ENV; exec '$PYTHON' -u -B scripts/serve_trace_net_nha_phase16_gemma_proxy_v1_1.py --host '$BRIDGE_HOST' --port 8131 --mode gated --phase4-dir '$PHASE4_DIR' --nha-engram-dir '$NHA_ENGRAM_DIR' --upstream-url http://127.0.0.1:8128 --upstream-api-key '$WRITER_KEY' --public-api-key '$PUBLIC_KEY' --public-model '$PUBLIC_MODEL' --upstream-model '$PUBLIC_MODEL' --ollama-url http://127.0.0.1:11434 --gemma-model '$GEMMA_MODEL' --telemetry-path '$TELEMETRY_PATH' --timeout-seconds '$PUBLIC_TIMEOUT' --gemma-timeout-seconds '$GEMMA_TIMEOUT' --gemma-max-tokens '$GEMMA_MAX_TOKENS' 2>&1 | tee '$RUNTIME/8131.log'"

wait_health() {
  local url="$1"
  local output="$2"
  for _ in $(seq 1 60); do
    if curl --silent --show-error --max-time 10 "$url" > "$output" 2>/dev/null; then
      if "$PYTHON" - "$output" <<'PY' >/dev/null 2>&1
from pathlib import Path
import json
import sys
value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
raise SystemExit(0 if value.get("quality_status") == "PASS" else 1)
PY
      then
        return 0
      fi
    fi
    sleep 2
  done
  return 1
}

wait_health http://127.0.0.1:8128/health "$RUNTIME/8128_health.json"
wait_health "http://$BRIDGE_HOST:8131/health" "$RUNTIME/8131_health.json"

echo
echo "=== 5. Enforce accurate residency health ==="
"$PYTHON" - "$RUNTIME/8128_health.json" "$RUNTIME/8131_health.json" <<'PY'
from pathlib import Path
import json
import sys
for path_text in sys.argv[1:]:
    path=Path(path_text)
    data=json.loads(path.read_text(encoding="utf-8"))
    print()
    print(path.name)
    for key in (
        "quality_status",
        "module",
        "release_proxy",
        "gemma_model_available",
        "gemma_model_resident",
        "cold_start_risk",
        "gemma_residency_watchdog_enabled",
        "gemma_residency_watchdog_running",
        "gemma_keep_alive",
        "validated_progress_streaming",
        "raw_unvalidated_tokens_exposed",
    ):
        if key in data:
            print(f"{key}={data.get(key)}")
    if data.get("quality_status") != "PASS":
        raise SystemExit(f"health quality failed: {path}")
    if data.get("gemma_model_resident") is not True:
        raise SystemExit(f"resident gate failed: {path}")
    if data.get("cold_start_risk") is not False:
        raise SystemExit(f"cold-start risk gate failed: {path}")
print()
print("RESIDENCY_HEALTH_GATE=PASS")
PY

echo
echo "=== 6. Verify safe early progress SSE ==="
curl --fail-with-body --silent --show-error --no-buffer --max-time "$PUBLIC_TIMEOUT" \
  "http://$BRIDGE_HOST:8131/v1/chat/completions" \
  -H "Authorization: Bearer $PUBLIC_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$PUBLIC_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"What bigger assembly is 120-20970-001 installed inside? Use TRACE-Net evidence and cite pages.\"}],\"temperature\":0,\"max_tokens\":128,\"stream\":true}" \
  > "$RUNTIME/progress_stream_test.txt"

grep -Fq '"object": "trace_net.progress"' "$RUNTIME/progress_stream_test.txt"
grep -Fq '"stage": "request_accepted"' "$RUNTIME/progress_stream_test.txt"
grep -Fq '"stage": "answer_validated"' "$RUNTIME/progress_stream_test.txt"
grep -Fq 'chat.completion.chunk' "$RUNTIME/progress_stream_test.txt"
grep -Fq 'data: [DONE]' "$RUNTIME/progress_stream_test.txt"

echo "SAFE_PROGRESS_STREAM_GATE=PASS"

echo
echo "============================================================"
echo "TRACE-NET GEMMA RESIDENCY STACK V2 READY"
echo "============================================================"
echo "Base URL: http://$BRIDGE_HOST:8131/v1"
echo "API key: $PUBLIC_KEY"
echo "Model: $PUBLIC_MODEL"
echo "Runtime: $RUNTIME"
echo "Gemma resident: true"
echo "Cold-start risk: false"
echo "Watchdog interval: ${CHECK_INTERVAL}s"
echo "Validated progress streaming: true"
