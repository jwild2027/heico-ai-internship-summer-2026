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
BASE_ENGRAM="${TRACE_NET_NHA_BASE_ENGRAM_CORE:-$REPO_ROOT/local_data/organization/trace_net/engineering_engram_core_v1/trace_net_engineering_engram_core_v1.json}"
BASE_SKILLS="${TRACE_NET_NHA_BASE_SKILL_LIBRARY:-$REPO_ROOT/local_data/organization/trace_net/engram_skill_cards_v1/trace_net_engram_skill_cards_v1.json}"
ENGRAM_DIR="${TRACE_NET_NHA_ENGRAM_DIR:-/data/trace_net_runs/nha_phase13_engram_v1}"
HOST="${TRACE_NET_NHA_HOST:-0.0.0.0}"
PORT="${TRACE_NET_NHA_PORT:-8132}"
UPSTREAM_URL="${TRACE_NET_NHA_UPSTREAM_URL:-http://172.17.0.1:8131}"
OLLAMA_URL="${TRACE_NET_NHA_OLLAMA_URL:-http://127.0.0.1:11434}"
API_KEY="${TRACE_NET_NHA_API_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_NHA_MODEL:-trace-net-gemma4-cognitive-rag-nha-engram-v1}"
UPSTREAM_MODEL="${TRACE_NET_NHA_UPSTREAM_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
GEMMA_MODEL="${TRACE_NET_NHA_GEMMA_MODEL:-gemma4:26b}"
RUN_DIR="${TRACE_NET_NHA_GEMMA_RUN_DIR:-/data/trace_net_runs/nha_phase16_gemma_v1}"
PID_FILE="$RUN_DIR/proxy.pid"
LOG_FILE="$RUN_DIR/proxy_${MODE}.log"
TELEMETRY_FILE="$RUN_DIR/telemetry_${MODE}.jsonl"

mkdir -p "$RUN_DIR" "$ENGRAM_DIR"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/scripts:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON_BIN" -B scripts/build/graph/build_trace_net_nha_engram_v1.py \
  --base-engram-core "$BASE_ENGRAM" \
  --base-skill-library "$BASE_SKILLS" \
  --output-dir "$ENGRAM_DIR" \
  --strict >/dev/null

"$PYTHON_BIN" -B scripts/maintenance/graph/check_trace_net_nha_engram_v1.py \
  --output-dir "$ENGRAM_DIR" \
  --strict >/dev/null

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID"
    for _ in $(seq 1 40); do
      kill -0 "$OLD_PID" 2>/dev/null || break
      sleep 0.2
    done
  fi
  rm -f "$PID_FILE"
fi

# Also stop the prior N11/N12 sidecar if it owns the same port and PID file.
OLD_PHASE11_PID="${TRACE_NET_NHA_RUN_DIR:-/data/trace_net_runs/nha_phase11_server_v1}/proxy.pid"
if [[ -f "$OLD_PHASE11_PID" ]]; then
  OLD_PID="$(cat "$OLD_PHASE11_PID" || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" || true
    sleep 0.5
  fi
fi

nohup "$PYTHON_BIN" -B scripts/operations/serving/serve_trace_net_nha_phase16_gemma_proxy_v1.py \
  --host "$HOST" \
  --port "$PORT" \
  --mode "$MODE" \
  --phase4-dir "$PHASE4_DIR" \
  --nha-engram-dir "$ENGRAM_DIR" \
  --upstream-url "$UPSTREAM_URL" \
  --upstream-api-key "$API_KEY" \
  --public-api-key "$API_KEY" \
  --public-model "$PUBLIC_MODEL" \
  --upstream-model "$UPSTREAM_MODEL" \
  --ollama-url "$OLLAMA_URL" \
  --gemma-model "$GEMMA_MODEL" \
  --telemetry-path "$TELEMETRY_FILE" \
  >"$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

READY=0
for _ in $(seq 1 120); do
  if "$PYTHON_BIN" - <<PY >/dev/null 2>&1
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:${PORT}/health", timeout=3) as r:
    data=json.loads(r.read().decode())
    assert r.status == 200
    assert data.get("quality_status") == "PASS"
    assert data.get("mode") == "${MODE}"
    assert data.get("engram_ready") is True
    assert data.get("gemma_ready") is True
PY
  then
    READY=1
    break
  fi
  sleep 0.5
done

if [[ "$READY" != "1" ]]; then
  echo "NHA Gemma proxy failed health check; inspect $LOG_FILE" >&2
  tail -n 120 "$LOG_FILE" || true
  exit 1
fi

echo "status=TRACE_NET_NHA_PHASE16_SERVER_READY"
echo "quality_status=PASS"
echo "mode=$MODE"
echo "port=$PORT"
echo "pid=$PID"
echo "model=$PUBLIC_MODEL"
echo "answer_model=$GEMMA_MODEL"
echo "engram_dir=$ENGRAM_DIR"
echo "log=$LOG_FILE"
echo "telemetry=$TELEMETRY_FILE"
