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

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$RUNTIME"

for required in \
  scripts/serve_trace_net_cognitive_router_v1.py \
  scripts/serve_trace_net_full_gemma_cognitive_v1.py \
  scripts/serve_trace_net_openwebui_cognitive_bridge_v1.py \
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
echo "COMPILING H30 COGNITIVE STACK"
echo "============================================================"

"$PYTHON" -m py_compile \
  scripts/serve_trace_net_cognitive_router_v1.py \
  scripts/serve_trace_net_full_gemma_cognitive_v1.py \
  scripts/serve_trace_net_openwebui_cognitive_bridge_v1.py \
  scripts/run_trace_net_cognitive_route_smoke_v1.py

echo "compile_status=PASS"

"$PYTHON" -m pytest -q \
  tests/unit/test_trace_net_cognitive_router_v1.py \
  tests/unit/test_trace_net_full_gemma_cognitive_v1.py

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
curl --fail-with-body --silent --show-error http://127.0.0.1:8118/health | "$PYTHON" -m json.tool
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
  "post_answer_validation": true
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
echo "Connection file:"
echo "  $RUNTIME/openwebui_connection.json"
echo
echo "Existing 8130 stack was not changed."
