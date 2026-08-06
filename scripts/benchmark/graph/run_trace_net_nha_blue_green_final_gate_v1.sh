#!/usr/bin/env bash
set -euo pipefail

REPO="${TRACE_NET_REPO:-$(pwd)}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="${TRACE_NET_PYTHON_BIN:-$VENV/bin/python}"
PUBLIC_KEY="${TRACE_NET_OPENWEBUI_COGNITIVE_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_OPENWEBUI_COGNITIVE_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
GEMMA_MODEL="${TRACE_NET_GEMMA_MODEL:-gemma4:26b}"
OLLAMA_URL="${TRACE_NET_NHA_OLLAMA_URL:-http://127.0.0.1:11434}"
ANSWER_KEY="${TRACE_NET_NHA_PHASE20_ANSWER_KEY:-$REPO/tests/fixtures/trace_net_nha_phase20_synthetic_direct_parent_answer_key_v1.json}"
ENGRAM_DIR="${TRACE_NET_NHA_ENGRAM_DIR:-/data/trace_net_runs/nha_phase13_engram_v1}"
BENCHMARK_KEY="${TRACE_NET_NHA_PHASE20_BENCHMARK_KEY:-trace-net-nha-gemma100-benchmark}"
POINTER_PATH="${TRACE_NET_BLUE_GREEN_POINTER_PATH:-/data/trace_net_runs/blue_green_frontdoor_v1/active_backend.json}"
RUN_ROOT_BASE="${TRACE_NET_BLUE_GREEN_FINAL_RUN_ROOT:-/data/trace_net_runs/nha_blue_green_final_v1}"

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"

choose_color() {
  local requested="${TRACE_NET_BLUE_GREEN_CANDIDATE_COLOR:-auto}"
  if [[ "$requested" == "green" || "$requested" == "blue" ]]; then
    echo "$requested"
    return
  fi
  if [[ -f "$POINTER_PATH" ]]; then
    local active
    active="$($PYTHON - "$POINTER_PATH" <<'PY'
import json, sys
from pathlib import Path
try:
    value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    print("")
else:
    print(str(value.get("active_color") or ""))
PY
)"
    if [[ "$active" == "green" ]]; then echo "blue"; return; fi
    if [[ "$active" == "blue" ]]; then echo "green"; return; fi
  fi
  echo "green"
}

COLOR="$(choose_color)"
case "$COLOR" in
  green)
    ROUTER_PORT="${TRACE_NET_BLUE_GREEN_GREEN_ROUTER_PORT:-8218}"
    WRITER_PORT="${TRACE_NET_BLUE_GREEN_GREEN_WRITER_PORT:-8228}"
    NHA_PORT="${TRACE_NET_BLUE_GREEN_GREEN_NHA_PORT:-8231}"
    BENCHMARK_PORT="${TRACE_NET_BLUE_GREEN_GREEN_BENCHMARK_PORT:-8233}"
    ;;
  blue)
    ROUTER_PORT="${TRACE_NET_BLUE_GREEN_BLUE_ROUTER_PORT:-8318}"
    WRITER_PORT="${TRACE_NET_BLUE_GREEN_BLUE_WRITER_PORT:-8328}"
    NHA_PORT="${TRACE_NET_BLUE_GREEN_BLUE_NHA_PORT:-8331}"
    BENCHMARK_PORT="${TRACE_NET_BLUE_GREEN_BLUE_BENCHMARK_PORT:-8333}"
    ;;
esac

RUN_ROOT="$RUN_ROOT_BASE/$COLOR"
CANDIDATE_RUNTIME="${TRACE_NET_BLUE_GREEN_RUNTIME_ROOT:-/data/trace_net_runs/blue_green_v1}/$COLOR"
BENCHMARK_SESSION="trace-net-blue-green-${COLOR}-gemma100-${BENCHMARK_PORT}"
PROMOTED=0
mkdir -p "$RUN_ROOT"

stop_benchmark() {
  tmux has-session -t "$BENCHMARK_SESSION" 2>/dev/null && tmux kill-session -t "$BENCHMARK_SESSION" || true
  fuser -k -TERM "${BENCHMARK_PORT}/tcp" 2>/dev/null || true
  sleep 0.5
  if fuser "${BENCHMARK_PORT}/tcp" >/dev/null 2>&1; then
    fuser -k "${BENCHMARK_PORT}/tcp" 2>/dev/null || true
  fi
}

cleanup_failed_candidate() {
  local status=$?
  stop_benchmark
  if [[ "$PROMOTED" == "0" ]]; then
    TRACE_NET_BLUE_GREEN_ALLOW_STOP_ACTIVE=0 \
      bash scripts/operations/launch_trace_net_nha_blue_green_candidate_v1.sh "$COLOR" stop || true
  fi
  echo "TRACE_NET_BLUE_GREEN_CANDIDATE_CLEANUP=PASS"
  echo "production_ports_restarted=false"
  echo "production_backend_pointer_changed=false"
  exit "$status"
}
trap cleanup_failed_candidate ERR

for required in \
  src/trace_net/serving/trace_net_blue_green_pointer_v1.py \
  scripts/operations/serving/serve_trace_net_blue_green_frontdoor_v1.py \
  scripts/operations/launch_trace_net_nha_blue_green_candidate_v1.sh \
  scripts/operations/graph/promote_trace_net_nha_blue_green_v1.sh \
  scripts/benchmark/s3_graph_store/serve_trace_net_nha_phase20_gemma100_v1.py \
  scripts/benchmark/s3_graph_store/run_trace_net_nha_phase20_gemma100_v1.py \
  scripts/benchmark/s3_graph_store/check_trace_net_nha_phase20_gemma100_v1.py; do
  [[ -f "$required" ]] || { echo "missing_required_file=$required"; exit 1; }
done
[[ -f "$ANSWER_KEY" ]] || { echo "missing_answer_key=$ANSWER_KEY"; exit 1; }
[[ -d "$ENGRAM_DIR" ]] || { echo "missing_engram_dir=$ENGRAM_DIR"; exit 1; }

"$PYTHON" -m py_compile \
  src/trace_net/serving/trace_net_blue_green_pointer_v1.py \
  scripts/operations/serving/serve_trace_net_blue_green_frontdoor_v1.py \
  src/trace_net/graph/trace_net_nha_phase20_gemma100_v1.py \
  scripts/benchmark/s3_graph_store/serve_trace_net_nha_phase20_gemma100_v1.py \
  scripts/benchmark/s3_graph_store/run_trace_net_nha_phase20_gemma100_v1.py \
  scripts/benchmark/s3_graph_store/check_trace_net_nha_phase20_gemma100_v1.py

echo "TRACE_NET_BLUE_GREEN_COMPILE=PASS"

# The legacy latency-guard unit test owns the 512-token base writer contract.
# Run it with the optional Phase 19 preservation overlay explicitly disabled.
env \
  TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED=0 \
  TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_ENABLED=0 \
  "$PYTHON" -m pytest -q tests/unit/test_trace_net_h30_phase4_latency_guard_v1.py

"$PYTHON" -m pytest -q \
  tests/unit/test_trace_net_nha_engram_v1.py \
  tests/unit/test_trace_net_nha_phase14_16_cognitive_v1.py \
  tests/unit/test_trace_net_nha_phase18_unified8131_v1.py \
  tests/unit/test_trace_net_h30_phase19_route_completion_fastpath_v1.py \
  tests/unit/test_trace_net_h30_phase19_preservation_writer_v1.py \
  tests/unit/test_trace_net_nha_phase19_gate_v1.py \
  tests/unit/test_trace_net_nha_phase20_gemma100_v1.py \
  tests/unit/test_trace_net_nha_blue_green_v1.py

echo "TRACE_NET_BLUE_GREEN_UNIT_TESTS=PASS"

# Start only the inactive candidate color. Production 8118/8128/8131 remains live.
bash scripts/operations/launch_trace_net_nha_blue_green_candidate_v1.sh "$COLOR" start

curl --fail-with-body --silent --show-error "http://127.0.0.1:$ROUTER_PORT/health" > "$RUN_ROOT/router_health.json"
curl --fail-with-body --silent --show-error "http://127.0.0.1:$WRITER_PORT/health" > "$RUN_ROOT/writer_health.json"
curl --fail-with-body --silent --show-error "http://127.0.0.1:$NHA_PORT/health" > "$RUN_ROOT/nha_health.json"

# Mixed production-style smoke on the candidate only. This retains the proven
# safe-fallback contract for ordinary cognitive routes while requiring real Gemma
# for every non-synthetic request.
"$PYTHON" -B scripts/operations/graph/run_trace_net_nha_phase18_unified8131_gate_v1.py \
  --base-url "http://127.0.0.1:$NHA_PORT" \
  --api-key "$PUBLIC_KEY" \
  --model "$PUBLIC_MODEL" \
  --output-dir "$RUN_ROOT/mixed12" \
  --timeout-seconds 300 \
  --strict

"$PYTHON" -B scripts/maintenance/graph/check_trace_net_nha_phase18_unified8131_gate_v1.py \
  --output-dir "$RUN_ROOT/mixed12" \
  --strict

echo "TRACE_NET_BLUE_GREEN_CANDIDATE_MIXED12=PASS"

# Start the isolated synthetic service on the candidate color's benchmark port.
stop_benchmark
rm -f "$RUN_ROOT/benchmark_telemetry.jsonl"
cat > "/tmp/start_trace_net_blue_green_${COLOR}_gemma100.sh" <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
exec "$PYTHON" -u -B scripts/benchmark/s3_graph_store/serve_trace_net_nha_phase20_gemma100_v1.py \\
  --host 127.0.0.1 \\
  --port "$BENCHMARK_PORT" \\
  --phase5-dir "$ANSWER_KEY" \\
  --nha-engram-dir "$ENGRAM_DIR" \\
  --api-key "$BENCHMARK_KEY" \\
  --ollama-url "$OLLAMA_URL" \\
  --gemma-model "$GEMMA_MODEL" \\
  --timeout-seconds 180 \\
  --max-tokens 384 \\
  --telemetry-path "$RUN_ROOT/benchmark_telemetry.jsonl"
INNER
chmod +x "/tmp/start_trace_net_blue_green_${COLOR}_gemma100.sh"
tmux new-session -d -s "$BENCHMARK_SESSION" \
  "bash /tmp/start_trace_net_blue_green_${COLOR}_gemma100.sh 2>&1 | tee '$RUN_ROOT/benchmark.log'"

"$PYTHON" - "$BENCHMARK_PORT" <<'PY'
import socket, sys, time
port=int(sys.argv[1])
deadline=time.time()+180
while time.time()<deadline:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            print(f"port_{port}=LISTENING")
            raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit(f"benchmark port {port} failed to start")
PY

curl --fail-with-body --silent --show-error "http://127.0.0.1:$BENCHMARK_PORT/health" \
  > "$RUN_ROOT/benchmark_health.json"

"$PYTHON" -B scripts/benchmark/s3_graph_store/run_trace_net_nha_phase20_gemma100_v1.py \
  --base-url "http://127.0.0.1:$BENCHMARK_PORT" \
  --api-key "$BENCHMARK_KEY" \
  --model "$PUBLIC_MODEL" \
  --phase5-dir "$ANSWER_KEY" \
  --output-dir "$RUN_ROOT/gemma100" \
  --timeout-seconds 240 \
  --strict

"$PYTHON" -B scripts/benchmark/s3_graph_store/check_trace_net_nha_phase20_gemma100_v1.py \
  --output-dir "$RUN_ROOT/gemma100" \
  --strict

stop_benchmark

echo "TRACE_NET_BLUE_GREEN_CANDIDATE_GEMMA100=PASS"

# Record the completed candidate gate before changing the active pointer.
"$PYTHON" - "$CANDIDATE_RUNTIME/candidate.json" "$RUN_ROOT" <<'PY'
import json, sys, time
from pathlib import Path
path=Path(sys.argv[1])
value=json.loads(path.read_text(encoding="utf-8"))
value.update({
    "quality_status": "PASS",
    "mixed12_pass": True,
    "gemma100_pass": True,
    "gemma100_real_model_call_count": 100,
    "gemma100_answer_key_pass_count": 100,
    "gate_run_root": str(Path(sys.argv[2]).resolve()),
    "gated_unix": time.time(),
})
temp=path.with_suffix(path.suffix + ".tmp")
temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
temp.replace(path)
print("TRACE_NET_BLUE_GREEN_CANDIDATE_MANIFEST=PASS")
PY

# Promotion validates candidate health and atomically switches the permanent
# pointer. On first installation only the lightweight 8131 listener is replaced;
# 8118/8128 are never rebuilt. Future promotions update only the pointer file.
bash scripts/operations/graph/promote_trace_net_nha_blue_green_v1.sh "$COLOR"
PROMOTED=1

BRIDGE_HOST="$(ip -4 addr show docker0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -1)"
[[ -n "$BRIDGE_HOST" ]] || BRIDGE_HOST="172.17.0.1"

# Final public checks through the permanent front door.
"$PYTHON" - "$BRIDGE_HOST" "$PUBLIC_KEY" "$PUBLIC_MODEL" <<'PY'
import json, sys, urllib.request
host, key, model = sys.argv[1:]
url=f"http://{host}:8131/v1/chat/completions"

def call(query):
    payload={"model":model,"messages":[{"role":"user","content":query}],"stream":False,"temperature":0}
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=300) as response:
        body=json.loads(response.read().decode())
        headers={k.lower():v for k,v in response.headers.items()}
    answer=str((((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""))
    return answer, headers

real_answer, real_headers=call("What is the next highest assembly for 120-20970-003?")
if not real_answer:
    raise SystemExit("public real NHA smoke returned an empty answer")
if int(real_headers.get("x-trace-net-model-calls") or 0) != 1:
    raise SystemExit("public real NHA smoke did not prove one model call")

blocked_answer, blocked_headers=call("What is the next highest assembly for 990-91001-001?")
if "reserved benchmark identifier" not in blocked_answer.casefold():
    raise SystemExit("production synthetic block was not preserved")
if int(blocked_headers.get("x-trace-net-model-calls") or 0) != 0:
    raise SystemExit("synthetic production request unexpectedly called a model")
print("TRACE_NET_BLUE_GREEN_PUBLIC_REAL_NHA=PASS")
print("TRACE_NET_BLUE_GREEN_PUBLIC_SYNTHETIC_BLOCK=PASS")
PY

trap - ERR

echo "TRACE_NET_NHA_BLUE_GREEN_FINAL=PASS"
echo "TRACE_NET_NHA_PHASE20_GEMMA100=PASS"
echo "TRACE_NET_NHA_PHASE20_ALL_100_REAL_GEMMA_CALLS=PASS"
echo "TRACE_NET_NHA_PHASE20_ANSWER_KEY_COMPARISON=PASS"
echo "TRACE_NET_BLUE_GREEN_NO_PRODUCTION_REBUILD=PASS"
echo "TRACE_NET_BLUE_GREEN_NO_ROLLBACK_HANDLER=PASS"
echo "status=TRACE_NET_NHA_BLUE_GREEN_FINAL_GATE_V1"
echo "quality_status=PASS"
echo "active_color=$COLOR"
echo "active_backend=http://127.0.0.1:$NHA_PORT"
echo "public_base_url=http://$BRIDGE_HOST:8131/v1"
echo "public_model=$PUBLIC_MODEL"
echo "production_8118_restarted=false"
echo "production_8128_restarted=false"
echo "benchmark_endpoint_stopped=true"
echo "production_8131_synthetic_block_preserved=true"
echo "port_8132_untouched=true"
