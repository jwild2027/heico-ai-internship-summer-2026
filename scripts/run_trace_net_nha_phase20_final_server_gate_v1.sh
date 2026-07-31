#!/usr/bin/env bash
set -euo pipefail

REPO="${TRACE_NET_REPO:-$(pwd)}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="${TRACE_NET_PYTHON_BIN:-$VENV/bin/python}"
RUN_ROOT="${TRACE_NET_NHA_PHASE20_RUN_ROOT:-/data/trace_net_runs/nha_phase20_final_gemma100_v1}"
ANSWER_KEY="${TRACE_NET_NHA_PHASE20_ANSWER_KEY:-$REPO/tests/fixtures/trace_net_nha_phase20_synthetic_direct_parent_answer_key_v1.json}"
ENGRAM_DIR="${TRACE_NET_NHA_ENGRAM_DIR:-/data/trace_net_runs/nha_phase13_engram_v1}"
BENCHMARK_KEY="${TRACE_NET_NHA_PHASE20_BENCHMARK_KEY:-trace-net-nha-gemma100-benchmark}"
GEMMA_MODEL="${TRACE_NET_GEMMA_MODEL:-gemma4:26b}"
OLLAMA_URL="${TRACE_NET_NHA_OLLAMA_URL:-http://127.0.0.1:11434}"
BENCHMARK_PORT="${TRACE_NET_NHA_PHASE20_BENCHMARK_PORT:-8133}"

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$RUN_ROOT"

"$PYTHON" -m py_compile \
  scripts/trace_net_nha_phase20_gemma100_v1.py \
  scripts/serve_trace_net_nha_phase20_gemma100_v1.py \
  scripts/run_trace_net_nha_phase20_gemma100_v1.py \
  scripts/check_trace_net_nha_phase20_gemma100_v1.py

echo "TRACE_NET_NHA_PHASE20_COMPILE=PASS"

"$PYTHON" -m pytest -q \
  tests/unit/test_trace_net_nha_engram_v1.py \
  tests/unit/test_trace_net_nha_phase14_16_cognitive_v1.py \
  tests/unit/test_trace_net_nha_phase18_unified8131_v1.py \
  tests/unit/test_trace_net_h30_phase19_route_completion_fastpath_v1.py \
  tests/unit/test_trace_net_h30_phase19_preservation_writer_v1.py \
  tests/unit/test_trace_net_nha_phase19_gate_v1.py \
  tests/unit/test_trace_net_nha_phase20_gemma100_v1.py

echo "TRACE_NET_NHA_PHASE20_FOCUSED_TESTS=PASS"

stop_benchmark() {
  tmux has-session -t trace-net-nha-gemma100-8133 2>/dev/null && tmux kill-session -t trace-net-nha-gemma100-8133 || true
  fuser -k -TERM "${BENCHMARK_PORT}/tcp" 2>/dev/null || true
  sleep 1
  if fuser "${BENCHMARK_PORT}/tcp" >/dev/null 2>&1; then
    fuser -k "${BENCHMARK_PORT}/tcp" 2>/dev/null || true
  fi
}

rollback_on_failure() {
  status=$?
  stop_benchmark
  bash scripts/launch_trace_net_nha_phase19_stack_v1.sh rollback || true
  exit "$status"
}
trap rollback_on_failure ERR

# Finish and verify the N19 public stack first. The launcher now isolates legacy
# unit tests from the externally enabled preservation-writer environment.
bash scripts/run_trace_net_nha_phase19_server_gate_v1.sh

echo "TRACE_NET_NHA_PHASE19_FINISHED=PASS"

"$PYTHON" -B - "$ANSWER_KEY" <<'PY'
from pathlib import Path
import sys
from scripts.trace_net_nha_phase20_gemma100_v1 import build_gemma100_bank, load_phase5_bundle
path=Path(sys.argv[1]).resolve()
bundle=load_phase5_bundle(path)
if bundle.get("quality_status") != "PASS":
    raise SystemExit("tracked Phase 5 answer key failed: " + ",".join(bundle.get("failures") or []))
bank=build_gemma100_bank(bundle)
if len(bank) != 100:
    raise SystemExit(f"tracked answer key did not generate 100 questions: {len(bank)}")
print(f"tracked_phase5_answer_key={path}")
print(f"tracked_phase5_relationship_count={len(bundle.get('relationships') or [])}")
print("TRACE_NET_NHA_PHASE20_PHASE5_ANSWER_KEY=PASS")
PY

if ! curl -sS --max-time 15 "$OLLAMA_URL/api/tags" | grep -Fq "$GEMMA_MODEL"; then
  echo "missing_ollama_model=$GEMMA_MODEL"
  exit 1
fi

stop_benchmark
rm -f "$RUN_ROOT/server_telemetry.jsonl"

cat > /tmp/start_trace_net_nha_gemma100_8133.sh <<INNER
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
export PYTHONPATH="$REPO/scripts:$REPO"
exec "$PYTHON" -u -B scripts/serve_trace_net_nha_phase20_gemma100_v1.py \
  --host 127.0.0.1 \
  --port "$BENCHMARK_PORT" \
  --phase5-dir "$ANSWER_KEY" \
  --nha-engram-dir "$ENGRAM_DIR" \
  --api-key "$BENCHMARK_KEY" \
  --ollama-url "$OLLAMA_URL" \
  --gemma-model "$GEMMA_MODEL" \
  --timeout-seconds 180 \
  --max-tokens 384 \
  --telemetry-path "$RUN_ROOT/server_telemetry.jsonl"
INNER
chmod +x /tmp/start_trace_net_nha_gemma100_8133.sh

tmux new-session -d -s trace-net-nha-gemma100-8133 \
  "bash /tmp/start_trace_net_nha_gemma100_8133.sh 2>&1 | tee '$RUN_ROOT/8133.log'"

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

curl --fail-with-body --silent --show-error \
  "http://127.0.0.1:$BENCHMARK_PORT/health" \
  > "$RUN_ROOT/8133_health.json"
"$PYTHON" -m json.tool "$RUN_ROOT/8133_health.json"

"$PYTHON" -B scripts/run_trace_net_nha_phase20_gemma100_v1.py \
  --base-url "http://127.0.0.1:$BENCHMARK_PORT" \
  --api-key "$BENCHMARK_KEY" \
  --model trace-net-gemma4-cognitive-rag-v1 \
  --phase5-dir "$ANSWER_KEY" \
  --output-dir "$RUN_ROOT/gemma100" \
  --timeout-seconds 240 \
  --strict

"$PYTHON" -B scripts/check_trace_net_nha_phase20_gemma100_v1.py \
  --output-dir "$RUN_ROOT/gemma100" \
  --strict

stop_benchmark
trap - ERR

echo "TRACE_NET_NHA_PHASE19_FINAL=PASS"
echo "TRACE_NET_NHA_PHASE20_GEMMA100=PASS"
echo "TRACE_NET_NHA_PHASE20_GEMMA100_CHECK=PASS"
echo "TRACE_NET_NHA_PHASE20_ALL_100_REAL_GEMMA_CALLS=PASS"
echo "TRACE_NET_NHA_PHASE20_ANSWER_KEY_COMPARISON=PASS"
echo "status=TRACE_NET_NHA_PHASE20_FINAL_SERVER_GATE_V1"
echo "quality_status=PASS"
echo "public_base_url=http://172.17.0.1:8131/v1"
echo "public_model=trace-net-gemma4-cognitive-rag-v1"
echo "benchmark_endpoint_stopped=true"
echo "production_8131_synthetic_block_preserved=true"
echo "port_8132_untouched=true"
