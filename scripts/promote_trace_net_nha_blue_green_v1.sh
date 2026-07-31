#!/usr/bin/env bash
set -euo pipefail

COLOR="${1:-green}"
REPO="${TRACE_NET_REPO:-$(pwd)}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="${TRACE_NET_PYTHON_BIN:-$VENV/bin/python}"
PUBLIC_KEY="${TRACE_NET_OPENWEBUI_COGNITIVE_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_OPENWEBUI_COGNITIVE_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
POINTER_PATH="${TRACE_NET_BLUE_GREEN_POINTER_PATH:-/data/trace_net_runs/blue_green_frontdoor_v1/active_backend.json}"
FRONTDOOR_RUNTIME="${TRACE_NET_BLUE_GREEN_FRONTDOOR_RUNTIME:-/data/trace_net_runs/blue_green_frontdoor_v1}"
PREVIEW_PORT="${TRACE_NET_BLUE_GREEN_PREVIEW_PORT:-8241}"
TIMEOUT="${TRACE_NET_H30_PUBLIC_BRIDGE_TIMEOUT_SECONDS:-300}"

case "$COLOR" in
  green) NHA_PORT="${TRACE_NET_BLUE_GREEN_GREEN_NHA_PORT:-8231}" ;;
  blue) NHA_PORT="${TRACE_NET_BLUE_GREEN_BLUE_NHA_PORT:-8331}" ;;
  *) echo "usage: $0 [green|blue]" >&2; exit 2 ;;
esac

BACKEND_URL="http://127.0.0.1:$NHA_PORT"
CANDIDATE_MANIFEST="${TRACE_NET_BLUE_GREEN_CANDIDATE_MANIFEST:-${TRACE_NET_BLUE_GREEN_RUNTIME_ROOT:-/data/trace_net_runs/blue_green_v1}/$COLOR/candidate.json}"

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$FRONTDOOR_RUNTIME"

for command in tmux curl fuser ip; do
  command -v "$command" >/dev/null || { echo "missing_command=$command"; exit 1; }
done
for required in \
  scripts/trace_net_blue_green_pointer_v1.py \
  scripts/serve_trace_net_blue_green_frontdoor_v1.py; do
  [[ -f "$required" ]] || { echo "missing_required_file=$required"; exit 1; }
done
[[ -f "$CANDIDATE_MANIFEST" ]] || { echo "missing_candidate_manifest=$CANDIDATE_MANIFEST"; exit 1; }

BRIDGE_HOST="$(ip -4 addr show docker0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -1)"
[[ -n "$BRIDGE_HOST" ]] || BRIDGE_HOST="172.17.0.1"

wait_port() {
  local host="$1"
  local port="$2"
  "$PYTHON" - "$host" "$port" <<'PY'
import socket, sys, time
host=sys.argv[1]
port=int(sys.argv[2])
deadline=time.time()+120
while time.time()<deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"port_{port}=LISTENING")
            raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit(f"port {port} failed to start")
PY
}

stop_port_session() {
  local session="$1"
  local port="$2"
  tmux has-session -t "$session" 2>/dev/null && tmux kill-session -t "$session" || true
  fuser -k -TERM "${port}/tcp" 2>/dev/null || true
  sleep 0.5
  if fuser "${port}/tcp" >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

frontdoor_module() {
  curl --silent --show-error --max-time 8 "http://$BRIDGE_HOST:8131/health" 2>/dev/null | \
    "$PYTHON" -c 'import json,sys; print(str(json.load(sys.stdin).get("module") or ""))' 2>/dev/null || true
}

# Validate the candidate and atomically prepare the pointer. No production process
# is stopped during this step.
"$PYTHON" -B scripts/trace_net_blue_green_pointer_v1.py set \
  --pointer-path "$POINTER_PATH" \
  --color "$COLOR" \
  --backend-url "$BACKEND_URL" \
  --model "$PUBLIC_MODEL" \
  --candidate-manifest "$CANDIDATE_MANIFEST" \
  --timeout-seconds 15 \
  > "$FRONTDOOR_RUNTIME/pointer_set_${COLOR}.json"

if [[ "$(frontdoor_module)" == "trace_net_blue_green_frontdoor_v1" ]]; then
  # Normal future promotion: the already-running front door sees the os.replace()
  # pointer update on its next request. No port restart or production rebuild.
  curl --fail-with-body --silent --show-error "http://$BRIDGE_HOST:8131/health" \
    > "$FRONTDOOR_RUNTIME/8131_health_after_pointer_switch.json"
  "$PYTHON" - "$FRONTDOOR_RUNTIME/8131_health_after_pointer_switch.json" "$COLOR" "$BACKEND_URL" <<'PY'
import json, sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
expected_color=sys.argv[2]
expected_backend=sys.argv[3]
fail=[]
if value.get("quality_status") != "PASS": fail.append("quality")
if value.get("module") != "trace_net_blue_green_frontdoor_v1": fail.append("module")
if value.get("active_color") != expected_color: fail.append("color")
if str(value.get("active_backend") or "").rstrip("/") != expected_backend: fail.append("backend")
if fail: raise SystemExit("pointer switch health failed: " + ",".join(fail))
print("TRACE_NET_BLUE_GREEN_ATOMIC_POINTER_SWITCH=PASS")
PY
  echo "TRACE_NET_BLUE_GREEN_PROMOTION=PASS"
  echo "promotion_mode=atomic_pointer_only"
  echo "active_color=$COLOR"
  echo "active_backend=$BACKEND_URL"
  echo "production_rebuild=false"
  echo "rollback_executed=false"
  exit 0
fi

# One-time migration: prove the permanent front-door binary against the candidate
# on a preview port before replacing only the lightweight 8131 listener.
stop_port_session trace-net-blue-green-frontdoor-preview "$PREVIEW_PORT"
cat > /tmp/start_trace_net_blue_green_frontdoor_preview.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
exec "$PYTHON" -u -B scripts/serve_trace_net_blue_green_frontdoor_v1.py \\
  --host 127.0.0.1 \\
  --port "$PREVIEW_PORT" \\
  --pointer-path "$POINTER_PATH" \\
  --backend-api-key "$PUBLIC_KEY" \\
  --public-api-key "$PUBLIC_KEY" \\
  --public-model "$PUBLIC_MODEL" \\
  --timeout-seconds "$TIMEOUT"
INNER
chmod +x /tmp/start_trace_net_blue_green_frontdoor_preview.sh
tmux new-session -d -s trace-net-blue-green-frontdoor-preview \
  "bash /tmp/start_trace_net_blue_green_frontdoor_preview.sh 2>&1 | tee '$FRONTDOOR_RUNTIME/preview.log'"
wait_port 127.0.0.1 "$PREVIEW_PORT"
curl --fail-with-body --silent --show-error "http://127.0.0.1:$PREVIEW_PORT/health" \
  > "$FRONTDOOR_RUNTIME/preview_health.json"
"$PYTHON" - "$FRONTDOOR_RUNTIME/preview_health.json" "$COLOR" <<'PY'
import json, sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
if value.get("quality_status") != "PASS" or value.get("active_color") != sys.argv[2]:
    raise SystemExit("front-door preview health failed")
print("TRACE_NET_BLUE_GREEN_FRONTDOOR_PREVIEW=PASS")
PY

# The candidate has passed all gates and the exact front-door binary has passed
# preview. Replace only the 8131 listener. 8118/8128 and candidate services remain
# running; there is no rebuild and no rollback handler.
tmux has-session -t trace-net-openwebui-cognitive-8131 2>/dev/null && tmux kill-session -t trace-net-openwebui-cognitive-8131 || true
tmux has-session -t trace-net-blue-green-frontdoor-8131 2>/dev/null && tmux kill-session -t trace-net-blue-green-frontdoor-8131 || true
fuser -k -TERM 8131/tcp 2>/dev/null || true
sleep 0.5
fuser 8131/tcp >/dev/null 2>&1 && fuser -k 8131/tcp 2>/dev/null || true

cat > /tmp/start_trace_net_blue_green_frontdoor_8131.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
exec "$PYTHON" -u -B scripts/serve_trace_net_blue_green_frontdoor_v1.py \\
  --host "$BRIDGE_HOST" \\
  --port 8131 \\
  --pointer-path "$POINTER_PATH" \\
  --backend-api-key "$PUBLIC_KEY" \\
  --public-api-key "$PUBLIC_KEY" \\
  --public-model "$PUBLIC_MODEL" \\
  --timeout-seconds "$TIMEOUT"
INNER
chmod +x /tmp/start_trace_net_blue_green_frontdoor_8131.sh
tmux new-session -d -s trace-net-blue-green-frontdoor-8131 \
  "bash /tmp/start_trace_net_blue_green_frontdoor_8131.sh 2>&1 | tee '$FRONTDOOR_RUNTIME/8131.log'"
wait_port "$BRIDGE_HOST" 8131
curl --fail-with-body --silent --show-error "http://$BRIDGE_HOST:8131/health" \
  > "$FRONTDOOR_RUNTIME/8131_health.json"
"$PYTHON" - "$FRONTDOOR_RUNTIME/8131_health.json" "$COLOR" "$BACKEND_URL" <<'PY'
import json, sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
fail=[]
if value.get("quality_status") != "PASS": fail.append("quality")
if value.get("module") != "trace_net_blue_green_frontdoor_v1": fail.append("module")
if value.get("active_color") != sys.argv[2]: fail.append("color")
if str(value.get("active_backend") or "").rstrip("/") != sys.argv[3]: fail.append("backend")
if fail: raise SystemExit("permanent front-door health failed: " + ",".join(fail))
print("TRACE_NET_BLUE_GREEN_FRONTDOOR_8131=PASS")
PY

stop_port_session trace-net-blue-green-frontdoor-preview "$PREVIEW_PORT"

cat > "$FRONTDOOR_RUNTIME/openwebui_connection.json" <<JSON
{
  "base_url": "http://$BRIDGE_HOST:8131/v1",
  "api_key": "$PUBLIC_KEY",
  "model": "$PUBLIC_MODEL",
  "frontdoor": "trace_net_blue_green_frontdoor_v1",
  "pointer_path": "$POINTER_PATH",
  "active_color": "$COLOR",
  "active_backend": "$BACKEND_URL",
  "future_promotions_restart_8131": false,
  "production_rebuild_on_promotion": false
}
JSON

echo "TRACE_NET_BLUE_GREEN_PROMOTION=PASS"
echo "promotion_mode=one_time_frontdoor_install"
echo "active_color=$COLOR"
echo "active_backend=$BACKEND_URL"
echo "public_base_url=http://$BRIDGE_HOST:8131/v1"
echo "production_rebuild=false"
echo "rollback_executed=false"
