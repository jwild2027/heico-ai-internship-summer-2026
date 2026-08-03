#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${TRACE_NET_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${TRACE_NET_PYTHON_BIN:-python}"
RELEASE_DIR="${TRACE_NET_NHA_RELEASE_DIR:-$REPO_ROOT/release_data/trace_net/nha_real_release_v1/phase4}"
BASE_URL="${TRACE_NET_NHA_BASE_URL:-http://127.0.0.1:8132}"
API_KEY="${TRACE_NET_NHA_API_KEY:-trace-net-openwebui-cognitive}"
MODEL="${TRACE_NET_NHA_MODEL:-trace-net-gemma4-cognitive-rag-nha-v1}"
RUN_ROOT="${TRACE_NET_NHA_RELEASE_GATE_RUN_ROOT:-/data/trace_net_runs/nha_phase12_server_release_gate_v1}"

mkdir -p "$RUN_ROOT"
cd "$REPO_ROOT"

"$PYTHON_BIN" -B scripts/maintenance/graph/check_trace_net_nha_phase9_release_v1.py \
  --release-dir "$RELEASE_DIR" \
  --strict

"$PYTHON_BIN" -B -m pytest -q \
  tests/unit/test_trace_net_nha_phase6_query_benchmark_v1.py \
  tests/unit/test_trace_net_nha_phase7_8_runtime_v1.py \
  tests/unit/test_trace_net_nha_phase9_12_release_v1.py

bash scripts/operations/serving/launch_trace_net_nha_phase11_server_v1.sh shadow

"$PYTHON_BIN" -B scripts/benchmark/run_trace_net_nha_phase11_shadow_http_smoke_v1.py \
  --phase4-dir "$RELEASE_DIR" \
  --base-url "$BASE_URL" \
  --api-key "$API_KEY" \
  --strict \
  | tee "$RUN_ROOT/shadow_http_smoke.log"

bash scripts/operations/serving/launch_trace_net_nha_phase11_server_v1.sh gated

LIVE20_DIR="$RUN_ROOT/live20"
rm -rf "$LIVE20_DIR"
"$PYTHON_BIN" -B scripts/benchmark/graph/run_trace_net_nha_phase10_live20_v1.py \
  --phase4-dir "$RELEASE_DIR" \
  --base-url "$BASE_URL" \
  --api-key "$API_KEY" \
  --model "$MODEL" \
  --output-dir "$LIVE20_DIR" \
  --expected-count 20 \
  --request-timeout 240 \
  --latency-hard-limit 180 \
  --strict

"$PYTHON_BIN" -B scripts/benchmark/graph/check_trace_net_nha_phase10_live20_v1.py \
  --output-dir "$LIVE20_DIR" \
  --expected-count 20 \
  --strict

echo "status=TRACE_NET_NHA_PHASE12_SERVER_RELEASE_GATE_V1"
echo "quality_status=PASS"
echo "release_dir=$RELEASE_DIR"
echo "live20_dir=$LIVE20_DIR"
echo "public_base_url=$BASE_URL/v1"
echo "public_model=$MODEL"
