#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-shadow}"
if [[ "$MODE" != "shadow" && "$MODE" != "gated" ]]; then
  echo "usage: $0 [shadow|gated]" >&2
  exit 2
fi

REPO_ROOT="${TRACE_NET_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${TRACE_NET_PYTHON_BIN:-python}"
PHASE4_DIR="${TRACE_NET_NHA_RELEASE_DIR:-$REPO_ROOT/release_data/trace_net/nha_real_release_v1/phase4}"
HOST="${TRACE_NET_NHA_HOST:-0.0.0.0}"
PORT="${TRACE_NET_NHA_PORT:-8132}"
UPSTREAM_URL="${TRACE_NET_NHA_UPSTREAM_URL:-http://127.0.0.1:8131}"
API_KEY="${TRACE_NET_NHA_API_KEY:-trace-net-openwebui-cognitive}"
MODEL="${TRACE_NET_NHA_MODEL:-trace-net-gemma4-cognitive-rag-nha-v1}"
RUN_DIR="${TRACE_NET_NHA_RUN_DIR:-/data/trace_net_runs/nha_phase11_server_v1}"
PID_FILE="$RUN_DIR/proxy.pid"
LOG_FILE="$RUN_DIR/proxy_${MODE}.log"
TELEMETRY_FILE="$RUN_DIR/telemetry_${MODE}.jsonl"

mkdir -p "$RUN_DIR"
cd "$REPO_ROOT"

for required in \
  "$PHASE4_DIR/trace_net_nha_hierarchy_relationships_v1.json" \
  "$PHASE4_DIR/trace_net_nha_phase4_answer_key_v1.json" \
  "$PHASE4_DIR/trace_net_nha_phase4_quality_v1.json"; do
  [[ -f "$required" ]] || { echo "missing required release file: $required" >&2; exit 1; }
done

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID"
    for _ in $(seq 1 30); do
      kill -0 "$OLD_PID" 2>/dev/null || break
      sleep 0.2
    done
  fi
  rm -f "$PID_FILE"
fi

nohup "$PYTHON_BIN" -B scripts/serve_trace_net_nha_phase12_release_proxy_v1.py \
  --host "$HOST" \
  --port "$PORT" \
  --mode "$MODE" \
  --phase4-dir "$PHASE4_DIR" \
  --upstream-url "$UPSTREAM_URL" \
  --upstream-api-key "$API_KEY" \
  --public-api-key "$API_KEY" \
  --public-model "$MODEL" \
  --telemetry-path "$TELEMETRY_FILE" \
  >"$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

READY=0
for _ in $(seq 1 60); do
  if "$PYTHON_BIN" - <<PY >/dev/null 2>&1
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:${PORT}/health", timeout=2) as r:
    data=json.loads(r.read().decode())
    assert r.status == 200 and data.get("quality_status") == "PASS" and data.get("mode") == "${MODE}"
PY
  then
    READY=1
    break
  fi
  sleep 0.5
done

if [[ "$READY" != "1" ]]; then
  echo "NHA proxy failed health check; inspect $LOG_FILE" >&2
  tail -n 80 "$LOG_FILE" || true
  exit 1
fi

echo "status=TRACE_NET_NHA_PHASE11_SERVER_READY"
echo "quality_status=PASS"
echo "mode=$MODE"
echo "port=$PORT"
echo "pid=$PID"
echo "phase4_dir=$PHASE4_DIR"
echo "log=$LOG_FILE"
echo "telemetry=$TELEMETRY_FILE"
