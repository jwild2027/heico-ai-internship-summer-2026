#!/usr/bin/env bash
set -euo pipefail

REPO="${TRACE_NET_REPO:-/data/trace_net/repos/trace-net-canary}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="$VENV/bin/python"
RUNTIME="${TRACE_NET_RUNTIME_DIR:-/data/trace_net_runs/cognitive_openwebui_v1}"
UNIFIED_URL="${TRACE_NET_UNIFIED_URL:-http://127.0.0.1:8117}"
GUIDED_URL="${TRACE_NET_GUIDED_URL:-http://127.0.0.1:8116}"
UNIFIED_KEY="${TRACE_NET_UNIFIED_KEY:-trace-net-canary-local}"
COGNITIVE_KEY="${TRACE_NET_COGNITIVE_KEY:-trace-net-cognitive-local}"
GEMMA_KEY="${TRACE_NET_GEMMA_COGNITIVE_KEY:-trace-net-gemma-cognitive-local}"
PUBLIC_KEY="${TRACE_NET_OPENWEBUI_COGNITIVE_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_OPENWEBUI_COGNITIVE_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
GEMMA_MODEL="${TRACE_NET_GEMMA_MODEL:-gemma4:26b}"
GEMMA_KEEP_ALIVE="${TRACE_NET_GEMMA_KEEP_ALIVE:-1h}"
SHADOW_PLANNER_ENABLED="${TRACE_NET_H30_SHADOW_PLANNER_ENABLED:-1}"
SHADOW_PLANNER_BASE_URL="${TRACE_NET_H30_SHADOW_PLANNER_BASE_URL:-http://127.0.0.1:11434/v1}"
SHADOW_PLANNER_API_KEY="${TRACE_NET_H30_SHADOW_PLANNER_API_KEY:-ollama}"
SHADOW_PLANNER_MODEL="${TRACE_NET_H30_SHADOW_PLANNER_MODEL:-$GEMMA_MODEL}"
SHADOW_PLANNER_TIMEOUT="${TRACE_NET_H30_SHADOW_PLANNER_TIMEOUT_SECONDS:-300}"
# TRACE_NET_H30_PHASE4_5_1_LAUNCHER_ENV_V1: capture validated-planner rollout settings.
PLANNER_ROLLOUT_MODE="${TRACE_NET_H30_PLANNER_ROLLOUT_MODE:-validate_only}"
PLANNER_EXECUTION_ENABLED="${TRACE_NET_H30_PLANNER_EXECUTION_ENABLED:-0}"
PLANNER_MAX_LATENCY_MS="${TRACE_NET_H30_PLANNER_MAX_LATENCY_MS:-90000}"
PLANNER_BREAKER_FAILURE_THRESHOLD="${TRACE_NET_H30_PLANNER_BREAKER_FAILURE_THRESHOLD:-2}"
PLANNER_BREAKER_SECONDS="${TRACE_NET_H30_PLANNER_BREAKER_SECONDS:-300}"
PLANNER_CANONICAL_BRIDGE_ENABLED="${TRACE_NET_H30_PLANNER_CANONICAL_BRIDGE_ENABLED:-1}"
PLANNER_REQUIRE_ROUTE="${TRACE_NET_H30_PLANNER_REQUIRE_ROUTE:-1}"

case "$PLANNER_ROLLOUT_MODE" in
  validate_only|narrow|broad|mature) ;;
  *)
    echo "invalid_planner_rollout_mode=$PLANNER_ROLLOUT_MODE"
    exit 1
    ;;
esac

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$RUNTIME"

for required in \
  scripts/serve_trace_net_cognitive_router_v1.py \
  scripts/trace_net_h30_shadow_planner_v1.py \
  scripts/serve_trace_net_full_gemma_cognitive_v1.py \
  scripts/serve_trace_net_openwebui_cognitive_bridge_v1.py \
  scripts/trace_net_h30_cold_start_streaming_v1.py \
  scripts/run_trace_net_cognitive_route_smoke_v1.py; do
  if [[ ! -f "$required" ]]; then
    echo "missing_required_file=$required"
    exit 1
  fi
done

for command in tmux curl fuser ip; do
  command -v "$command" >/dev/null || { echo "missing_command=$command"; exit 1; }
done

BRIDGE_HOST="$(ip -4 addr show docker0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -1)"
if [[ -z "$BRIDGE_HOST" ]]; then
  BRIDGE_HOST="172.17.0.1"
fi

echo "============================================================"
echo "VERIFYING EXISTING TRACE-NET UPSTREAMS"
echo "============================================================"

curl --fail-with-body --silent --show-error "$UNIFIED_URL/health" > "$RUNTIME/8117_health.json"
curl --fail-with-body --silent --show-error "$GUIDED_URL/health" > "$RUNTIME/8116_health.json"

"$PYTHON" - <<PY
import json
from pathlib import Path
for name in ("8117_health.json", "8116_health.json"):
    data=json.loads((Path("$RUNTIME")/name).read_text())
    print(name, data.get("quality_status"), data.get("module") or data.get("service"))
    if data.get("quality_status") not in {"PASS", "WARN"}:
        raise SystemExit(f"upstream health failed: {name}")
PY

if ! curl -sS --max-time 15 http://127.0.0.1:11434/api/tags | grep -Fq "$GEMMA_MODEL"; then
  echo "missing_ollama_model=$GEMMA_MODEL"
  exit 1
fi


echo
echo "============================================================"
echo "PRELOADING GEMMA IN OLLAMA"
echo "============================================================"

"$PYTHON" - "$GEMMA_MODEL" "$GEMMA_KEEP_ALIVE" "$RUNTIME/gemma_preload.json" <<'PY'
import json
import sys
import time
import urllib.request
from pathlib import Path

model, keep_alive, output = sys.argv[1:]
payload = {"model": model, "prompt": "", "stream": False, "keep_alive": keep_alive}
request = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
started = time.monotonic()
with urllib.request.urlopen(request, timeout=1200) as response:
    result = json.loads(response.read().decode("utf-8", errors="replace"))
elapsed_ms = round((time.monotonic() - started) * 1000.0, 3)
result["preload_wall_ms"] = elapsed_ms
result["requested_keep_alive"] = keep_alive
Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
if result.get("error"):
    raise SystemExit("Ollama preload returned an error: " + str(result["error"]))
print("gemma_preload_status=PASS")
print(f"gemma_preload_wall_ms={elapsed_ms}")
print(f"gemma_keep_alive={keep_alive}")
PY

curl --fail-with-body --silent --show-error \
  http://127.0.0.1:11434/api/ps \
  > "$RUNTIME/ollama_ps_after_preload.json"

"$PYTHON" - "$GEMMA_MODEL" "$RUNTIME/ollama_ps_after_preload.json" <<'PY'
import json
import sys
from pathlib import Path
model, filename = sys.argv[1:]
data = json.loads(Path(filename).read_text(encoding="utf-8"))
names = {
    str(row.get("name") or row.get("model"))
    for row in data.get("models", [])
    if isinstance(row, dict)
}
print("ollama_loaded_models=" + ",".join(sorted(names)))
if model not in names:
    raise SystemExit(f"preloaded model is not resident according to /api/ps: {model}")
print("gemma_resident_status=PASS")
PY

command -v ollama >/dev/null && ollama ps || true

echo
echo "============================================================"
echo "COMPILING H30 COGNITIVE STACK"
echo "============================================================"

"$PYTHON" -m py_compile \
  scripts/serve_trace_net_cognitive_router_v1.py \
  scripts/trace_net_h30_shadow_planner_v1.py \
  scripts/check_trace_net_h30_shadow_planner_v1.py \
  scripts/run_trace_net_h30_shadow_planner_benchmark_v1.py \
  scripts/serve_trace_net_full_gemma_cognitive_v1.py \
  scripts/serve_trace_net_openwebui_cognitive_bridge_v1.py \
  scripts/trace_net_h30_cold_start_streaming_v1.py \
  scripts/run_trace_net_cognitive_route_smoke_v1.py

echo "compile_status=PASS"

"$PYTHON" -m pytest -q \
  tests/unit/test_trace_net_cognitive_router_v1.py \
  tests/unit/test_trace_net_h30_shadow_planner_v1.py \
  tests/unit/test_trace_net_full_gemma_cognitive_v1.py \
  tests/unit/test_trace_net_h30_cold_start_streaming_v1.py

echo "unit_test_status=PASS"

stop_session() {
  local session="$1"
  local port="$2"
  tmux has-session -t "$session" 2>/dev/null && tmux kill-session -t "$session" || true
  fuser -k -TERM "${port}/tcp" 2>/dev/null || true
  sleep 1
  if fuser "${port}/tcp" >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

stop_session trace-net-cognitive-8118 8118
stop_session trace-net-gemma-cognitive-8128 8128
stop_session trace-net-openwebui-cognitive-8131 8131

cat > /tmp/start_trace_net_cognitive_8118.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
export TRACE_NET_H30_SHADOW_PLANNER_ENABLED="$SHADOW_PLANNER_ENABLED"
export TRACE_NET_H30_SHADOW_PLANNER_BASE_URL="$SHADOW_PLANNER_BASE_URL"
export TRACE_NET_H30_SHADOW_PLANNER_API_KEY="$SHADOW_PLANNER_API_KEY"
export TRACE_NET_H30_SHADOW_PLANNER_MODEL="$SHADOW_PLANNER_MODEL"
export TRACE_NET_H30_SHADOW_PLANNER_TIMEOUT_SECONDS="$SHADOW_PLANNER_TIMEOUT"
# TRACE_NET_H30_PHASE4_5_1_LAUNCHER_ENV_V1: propagate settings into the tmux process.
export TRACE_NET_H30_PLANNER_ROLLOUT_MODE="$PLANNER_ROLLOUT_MODE"
export TRACE_NET_H30_PLANNER_EXECUTION_ENABLED="$PLANNER_EXECUTION_ENABLED"
export TRACE_NET_H30_PLANNER_MAX_LATENCY_MS="$PLANNER_MAX_LATENCY_MS"
export TRACE_NET_H30_PLANNER_BREAKER_FAILURE_THRESHOLD="$PLANNER_BREAKER_FAILURE_THRESHOLD"
export TRACE_NET_H30_PLANNER_BREAKER_SECONDS="$PLANNER_BREAKER_SECONDS"
export TRACE_NET_H30_PLANNER_CANONICAL_BRIDGE_ENABLED="$PLANNER_CANONICAL_BRIDGE_ENABLED"
export TRACE_NET_H30_PLANNER_REQUIRE_ROUTE="$PLANNER_REQUIRE_ROUTE"
exec "$PYTHON" -u -B scripts/serve_trace_net_cognitive_router_v1.py \\
  --host 127.0.0.1 \\
  --port 8118 \\
  --unified-base-url "$UNIFIED_URL" \\
  --guided-base-url "$GUIDED_URL" \\
  --unified-api-key "$UNIFIED_KEY" \\
  --api-key "$COGNITIVE_KEY" \\
  --timeout-seconds 1200 \\
  --max-concurrency 2 \\
  --queue-timeout-seconds 1200
INNER

cat > /tmp/start_trace_net_gemma_cognitive_8128.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
export TRACE_NET_GEMMA_KEEP_ALIVE="$GEMMA_KEEP_ALIVE"
exec "$PYTHON" -u -B scripts/serve_trace_net_full_gemma_cognitive_v1.py \\
  --host 127.0.0.1 \\
  --port 8128 \\
  --cognitive-base-url http://127.0.0.1:8118 \\
  --cognitive-api-key "$COGNITIVE_KEY" \\
  --gemma-base-url http://127.0.0.1:11434/v1 \\
  --gemma-api-key ollama \\
  --gemma-model "$GEMMA_MODEL" \\
  --api-key "$GEMMA_KEY" \\
  --timeout-seconds 1200 \\
  --max-concurrency 1 \\
  --queue-timeout-seconds 1200
INNER

cat > /tmp/start_trace_net_openwebui_cognitive_8131.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
exec "$PYTHON" -u -B scripts/serve_trace_net_openwebui_cognitive_bridge_v1.py \\
  --host "$BRIDGE_HOST" \\
  --port 8131 \\
  --upstream-url http://127.0.0.1:8128 \\
  --upstream-api-key "$GEMMA_KEY" \\
  --public-api-key "$PUBLIC_KEY" \\
  --public-model "$PUBLIC_MODEL" \\
  --timeout-seconds 1200
INNER

chmod +x \
  /tmp/start_trace_net_cognitive_8118.sh \
  /tmp/start_trace_net_gemma_cognitive_8128.sh \
  /tmp/start_trace_net_openwebui_cognitive_8131.sh

wait_port() {
  local host="$1"
  local port="$2"
  "$PYTHON" - "$host" "$port" <<'PY'
import socket, sys, time
host=sys.argv[1]
port=int(sys.argv[2])
deadline=time.time()+180
while time.time()<deadline:
    try:
        with socket.create_connection((host,port),timeout=2):
            print(f"port_{port}=LISTENING")
            raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit(f"port {port} failed to start")
PY
}

tmux new-session -d -s trace-net-cognitive-8118 \
  "bash /tmp/start_trace_net_cognitive_8118.sh 2>&1 | tee '$RUNTIME/8118.log'"
wait_port 127.0.0.1 8118

tmux new-session -d -s trace-net-gemma-cognitive-8128 \
  "bash /tmp/start_trace_net_gemma_cognitive_8128.sh 2>&1 | tee '$RUNTIME/8128.log'"
wait_port 127.0.0.1 8128

tmux new-session -d -s trace-net-openwebui-cognitive-8131 \
  "bash /tmp/start_trace_net_openwebui_cognitive_8131.sh 2>&1 | tee '$RUNTIME/8131.log'"
wait_port "$BRIDGE_HOST" 8131

# If docker0 uses a non-default address, verify that exact address too.
# TRACE_NET_H30_PHASE4_5_1_LAUNCHER_ENV_V1: verify the live router received the requested mode.
curl --fail-with-body --silent --show-error \
  http://127.0.0.1:8118/health \
  > "$RUNTIME/8118_health.json"
"$PYTHON" -m json.tool "$RUNTIME/8118_health.json"
"$PYTHON" - "$RUNTIME/8118_health.json" "$PLANNER_ROLLOUT_MODE" "$PLANNER_EXECUTION_ENABLED" <<'PY'
import json
import sys
from pathlib import Path

filename, requested_mode, raw_enabled = sys.argv[1:]
health = json.loads(Path(filename).read_text(encoding="utf-8"))
requested_enabled = raw_enabled.strip().lower() in {"1", "true", "yes", "on"}
expected_execution = requested_enabled and requested_mode != "validate_only"
actual_mode = str(health.get("planner_rollout_mode") or "")
actual_execution = bool(health.get("planner_execution_enabled"))
phase_by_mode = {"validate_only": 2, "narrow": 3, "broad": 4, "mature": 5}
actual_phase = health.get("planner_rollout_phase")
expected_phase = phase_by_mode[requested_mode]

print(f"requested_planner_mode={requested_mode}")
print(f"live_planner_mode={actual_mode}")
print(f"expected_planner_execution={str(expected_execution).lower()}")
print(f"live_planner_execution={str(actual_execution).lower()}")
print(f"expected_planner_phase={expected_phase}")
print(f"live_planner_phase={actual_phase}")

failures = []
if actual_mode != requested_mode:
    failures.append(f"mode:{actual_mode}!={requested_mode}")
if actual_execution is not expected_execution:
    failures.append(f"execution:{actual_execution}!={expected_execution}")
if actual_phase != expected_phase:
    failures.append(f"phase:{actual_phase}!={expected_phase}")
if failures:
    raise SystemExit("planner launcher environment mismatch: " + ", ".join(failures))
print("planner_launcher_env_check=PASS")
PY
curl --fail-with-body --silent --show-error http://127.0.0.1:8128/health | "$PYTHON" -m json.tool
curl --fail-with-body --silent --show-error "http://$BRIDGE_HOST:8131/health" | "$PYTHON" -m json.tool

echo
echo "============================================================"
echo "VERIFYING ALL 19 ROUTES WITHOUT EXPENSIVE RETRIEVAL"
echo "============================================================"

"$PYTHON" scripts/run_trace_net_cognitive_route_smoke_v1.py \
  --base-url http://127.0.0.1:8118 \
  --api-key "$COGNITIVE_KEY" \
  --output "$RUNTIME/all_route_plan_smoke.json"

echo
echo "============================================================"
echo "RUNNING FIVE CRITICAL LIVE ROUTE TESTS"
echo "============================================================"

"$PYTHON" scripts/run_trace_net_cognitive_route_smoke_v1.py \
  --base-url http://127.0.0.1:8118 \
  --api-key "$COGNITIVE_KEY" \
  --timeout-seconds 1200 \
  --live \
  --output "$RUNTIME/critical_live_route_smoke.json"

echo
echo "============================================================"
echo "TESTING OPENWEBUI-COMPATIBLE SSE FROM HOST"
echo "============================================================"

curl --fail-with-body --silent --show-error --no-buffer --max-time 1200 \
  "http://$BRIDGE_HOST:8131/v1/chat/completions" \
  -H "Authorization: Bearer $PUBLIC_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$PUBLIC_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}],\"stream\":true,\"temperature\":0}" \
  > "$RUNTIME/openwebui_stream_test.txt"

grep -Fq 'chat.completion.chunk' "$RUNTIME/openwebui_stream_test.txt"
grep -Fq 'data: [DONE]' "$RUNTIME/openwebui_stream_test.txt"
echo "HOST_STREAM_TEST=PASS"

echo
echo "============================================================"
echo "TESTING FROM INSIDE OPENWEBUI CONTAINER"
echo "============================================================"

docker exec -i \
  -e TRACE_NET_URL="http://$BRIDGE_HOST:8131/v1/chat/completions" \
  -e TRACE_NET_KEY="$PUBLIC_KEY" \
  -e TRACE_NET_MODEL="$PUBLIC_MODEL" \
  open-webui \
  python - <<'PY'
import json, os, urllib.request
payload={
  "model":os.environ["TRACE_NET_MODEL"],
  "messages":[{"role":"user","content":"hello"}],
  "stream":True,
  "temperature":0,
}
request=urllib.request.Request(
  os.environ["TRACE_NET_URL"],
  data=json.dumps(payload).encode(),
  headers={"Authorization":"Bearer "+os.environ["TRACE_NET_KEY"],"Content-Type":"application/json"},
  method="POST",
)
with urllib.request.urlopen(request,timeout=1200) as response:
  content_type=response.headers.get("Content-Type","")
  text=response.read().decode("utf-8",errors="replace")
assert "text/event-stream" in content_type
assert "chat.completion.chunk" in text
assert "data: [DONE]" in text
print("OPENWEBUI_CONTAINER_STREAM_TEST=PASS")
PY

cat > "$RUNTIME/openwebui_connection.json" <<JSON
{
  "base_url": "http://$BRIDGE_HOST:8131/v1",
  "api_key": "$PUBLIC_KEY",
  "model": "$PUBLIC_MODEL",
  "cognitive_router": "http://127.0.0.1:8118",
  "gemma_writer": "http://127.0.0.1:8128",
  "route_count": 19,
  "self_rag": true,
  "crag": true,
  "direct_evidence_only_gemma_writing": true,
  "post_answer_validation": true,
  "gemma_preload": true,
  "gemma_keep_alive": "$GEMMA_KEEP_ALIVE",
  "streaming_mode": "upstream_sse_with_validated_answer_release",
  "raw_unvalidated_tokens_exposed": false
}
JSON

echo
echo "============================================================"
echo "TRACE-NET H30 COGNITIVE OPENWEBUI STACK READY"
echo "============================================================"
echo
echo "Base URL:"
echo "  http://$BRIDGE_HOST:8131/v1"
echo
echo "API key:"
echo "  $PUBLIC_KEY"
echo
echo "Model:"
echo "  $PUBLIC_MODEL"
echo
echo "Gemma keep-alive:"
echo "  $GEMMA_KEEP_ALIVE"
echo
echo "Streaming mode:"
echo "  upstream SSE with validated answer release"
echo
echo "Connection file:"
echo "  $RUNTIME/openwebui_connection.json"
echo
echo "Existing 8130 stack was not changed."
