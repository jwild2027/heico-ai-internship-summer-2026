#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-promote}"
REPO="${TRACE_NET_REPO:-$(pwd)}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="${TRACE_NET_PYTHON_BIN:-$VENV/bin/python}"
RUNTIME="${TRACE_NET_NHA_PHASE18_RUNTIME:-/data/trace_net_runs/nha_phase18_unified8131_v1}"
PUBLIC_KEY="${TRACE_NET_OPENWEBUI_COGNITIVE_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_OPENWEBUI_COGNITIVE_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
UPSTREAM_KEY="${TRACE_NET_GEMMA_COGNITIVE_KEY:-trace-net-gemma-cognitive-local}"
UPSTREAM_MODEL="${TRACE_NET_NHA_UPSTREAM_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
UPSTREAM_URL="${TRACE_NET_NHA_UPSTREAM_URL:-http://127.0.0.1:8128}"
OLLAMA_URL="${TRACE_NET_NHA_OLLAMA_URL:-http://127.0.0.1:11434}"
GEMMA_MODEL="${TRACE_NET_GEMMA_MODEL:-gemma4:26b}"
RELEASE_DIR="${TRACE_NET_NHA_RELEASE_DIR:-$REPO/release_data/trace_net/nha_real_release_v1/phase4}"
ENGRAM_DIR="${TRACE_NET_NHA_ENGRAM_DIR:-/data/trace_net_runs/nha_phase13_engram_v1}"
TIMEOUT="${TRACE_NET_H30_PUBLIC_BRIDGE_TIMEOUT_SECONDS:-225}"
GEMMA_TIMEOUT="${TRACE_NET_NHA_GEMMA_TIMEOUT_SECONDS:-180}"
GEMMA_MAX_TOKENS="${TRACE_NET_NHA_GEMMA_MAX_TOKENS:-512}"

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$RUNTIME"

for command in tmux curl fuser ip; do
  command -v "$command" >/dev/null || { echo "missing_command=$command"; exit 1; }
done
for required in \
  scripts/operations/serving/serve_trace_net_nha_phase16_gemma_proxy_v1.py \
  scripts/operations/serving/serve_trace_net_openwebui_cognitive_bridge_v1.py \
  src/trace_net/graph/trace_net_nha_phase14_16_cognitive_v1.py; do
  [[ -f "$required" ]] || { echo "missing_required_file=$required"; exit 1; }
done
[[ -d "$RELEASE_DIR" ]] || { echo "missing_nha_release_dir=$RELEASE_DIR"; exit 1; }
[[ -d "$ENGRAM_DIR" ]] || { echo "missing_nha_engram_dir=$ENGRAM_DIR"; exit 1; }

BRIDGE_HOST="$(ip -4 addr show docker0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -1)"
[[ -n "$BRIDGE_HOST" ]] || BRIDGE_HOST="172.17.0.1"

stop_8131() {
  tmux has-session -t trace-net-openwebui-cognitive-8131 2>/dev/null && tmux kill-session -t trace-net-openwebui-cognitive-8131 || true
  fuser -k -TERM 8131/tcp 2>/dev/null || true
  sleep 1
  fuser 8131/tcp >/dev/null 2>&1 && fuser -k 8131/tcp 2>/dev/null || true
}

wait_8131() {
  "$PYTHON" - "$BRIDGE_HOST" <<'PY'
import socket, sys, time
host=sys.argv[1]
deadline=time.time()+120
while time.time()<deadline:
    try:
        with socket.create_connection((host,8131),timeout=2):
            print("port_8131=LISTENING")
            raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit("port 8131 failed to start")
PY
}

start_legacy() {
  cat > /tmp/start_trace_net_openwebui_cognitive_8131.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
exec "$PYTHON" -u -B scripts/operations/serving/serve_trace_net_openwebui_cognitive_bridge_v1.py \\
  --host "$BRIDGE_HOST" \\
  --port 8131 \\
  --upstream-url "$UPSTREAM_URL" \\
  --upstream-api-key "$UPSTREAM_KEY" \\
  --public-api-key "$PUBLIC_KEY" \\
  --public-model "$PUBLIC_MODEL" \\
  --timeout-seconds "$TIMEOUT"
INNER
  chmod +x /tmp/start_trace_net_openwebui_cognitive_8131.sh
  tmux new-session -d -s trace-net-openwebui-cognitive-8131 \
    "bash /tmp/start_trace_net_openwebui_cognitive_8131.sh 2>&1 | tee '$RUNTIME/8131_legacy.log'"
  wait_8131
  curl --fail-with-body --silent --show-error "http://$BRIDGE_HOST:8131/health" > "$RUNTIME/8131_legacy_health.json"
  "$PYTHON" -m json.tool "$RUNTIME/8131_legacy_health.json"
}

rollback() {
  echo "TRACE_NET_NHA_PHASE18_8131_ROLLBACK=START"
  stop_8131
  start_legacy
  echo "TRACE_NET_NHA_PHASE18_8131_ROLLBACK=PASS"
}

if [[ "$ACTION" == "rollback" ]]; then
  rollback
  exit 0
fi
[[ "$ACTION" == "promote" ]] || { echo "usage: $0 [promote|rollback]"; exit 2; }

curl --fail-with-body --silent --show-error "$UPSTREAM_URL/health" > "$RUNTIME/8128_health.json"
"$PYTHON" - "$RUNTIME/8128_health.json" <<'PY'
import json, sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
assert value.get("quality_status") == "PASS", value
assert value.get("constrained_gemma_writer_enabled") is True, value
print("upstream_8128_health=PASS")
PY
curl --fail-with-body --silent --show-error "$OLLAMA_URL/api/tags" | grep -Fq "$GEMMA_MODEL"

"$PYTHON" -m py_compile \
  scripts/operations/serving/serve_trace_net_nha_phase16_gemma_proxy_v1.py \
  src/trace_net/graph/trace_net_nha_phase14_16_cognitive_v1.py

PROMOTED=0
on_error() {
  status=$?
  if [[ "$PROMOTED" != "1" ]]; then
    rollback || true
  fi
  exit "$status"
}
trap on_error ERR

stop_8131
cat > /tmp/start_trace_net_openwebui_cognitive_8131.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
exec "$PYTHON" -u -B scripts/operations/serving/serve_trace_net_nha_phase16_gemma_proxy_v1.py \\
  --host "$BRIDGE_HOST" \\
  --port 8131 \\
  --mode gated \\
  --phase4-dir "$RELEASE_DIR" \\
  --nha-engram-dir "$ENGRAM_DIR" \\
  --upstream-url "$UPSTREAM_URL" \\
  --upstream-api-key "$UPSTREAM_KEY" \\
  --public-api-key "$PUBLIC_KEY" \\
  --public-model "$PUBLIC_MODEL" \\
  --upstream-model "$UPSTREAM_MODEL" \\
  --ollama-url "$OLLAMA_URL" \\
  --gemma-model "$GEMMA_MODEL" \\
  --telemetry-path "$RUNTIME/8131_unified_telemetry.jsonl" \\
  --timeout-seconds "$TIMEOUT" \\
  --gemma-timeout-seconds "$GEMMA_TIMEOUT" \\
  --gemma-max-tokens "$GEMMA_MAX_TOKENS"
INNER
chmod +x /tmp/start_trace_net_openwebui_cognitive_8131.sh
tmux new-session -d -s trace-net-openwebui-cognitive-8131 \
  "bash /tmp/start_trace_net_openwebui_cognitive_8131.sh 2>&1 | tee '$RUNTIME/8131_unified.log'"
wait_8131
curl --fail-with-body --silent --show-error "http://$BRIDGE_HOST:8131/health" > "$RUNTIME/8131_unified_health.json"
"$PYTHON" - "$RUNTIME/8131_unified_health.json" "$PUBLIC_MODEL" <<'PY'
import json, sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
expected_model=sys.argv[2]
fail=[]
if value.get("quality_status") != "PASS": fail.append("quality")
if value.get("mode") != "gated": fail.append("mode")
if value.get("model") != expected_model: fail.append("model")
for key in ("upstream_ready", "gemma_ready", "engram_ready"):
    if value.get(key) is not True: fail.append(key)
if int(value.get("real_relationship_count") or 0) < 1: fail.append("relationships")
if fail: raise SystemExit("unified health failed: " + ",".join(fail))
print(json.dumps(value, indent=2))
print("TRACE_NET_NHA_PHASE18_8131_HEALTH=PASS")
PY

cat > "$RUNTIME/openwebui_connection.json" <<JSON
{
  "base_url": "http://$BRIDGE_HOST:8131/v1",
  "api_key": "$PUBLIC_KEY",
  "model": "$PUBLIC_MODEL",
  "upstream_cognitive_writer": "$UPSTREAM_URL",
  "nha_release_dir": "$RELEASE_DIR",
  "nha_engram_dir": "$ENGRAM_DIR",
  "nha_unified_on_8131": true,
  "legacy_8131_rollback_available": true,
  "port_8132_untouched": true
}
JSON
PROMOTED=1
trap - ERR

echo "status=TRACE_NET_NHA_PHASE18_UNIFIED8131_READY"
echo "quality_status=PASS"
echo "public_base_url=http://$BRIDGE_HOST:8131/v1"
echo "public_model=$PUBLIC_MODEL"
echo "upstream_url=$UPSTREAM_URL"
echo "nha_release_dir=$RELEASE_DIR"
echo "nha_engram_dir=$ENGRAM_DIR"
echo "port_8132_untouched=true"
