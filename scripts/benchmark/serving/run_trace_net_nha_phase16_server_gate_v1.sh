#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${TRACE_NET_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${TRACE_NET_PYTHON_BIN:-python}"
RELEASE_DIR="${TRACE_NET_NHA_RELEASE_DIR:-$REPO_ROOT/release_data/trace_net/nha_real_release_v1/phase4}"
ENGRAM_DIR="${TRACE_NET_NHA_ENGRAM_DIR:-/data/trace_net_runs/nha_phase13_engram_v1}"
BASE_URL="${TRACE_NET_NHA_BASE_URL:-http://127.0.0.1:8132}"
API_KEY="${TRACE_NET_NHA_API_KEY:-trace-net-openwebui-cognitive}"
MODEL="${TRACE_NET_NHA_MODEL:-trace-net-gemma4-cognitive-rag-nha-engram-v1}"
RUN_ROOT="${TRACE_NET_NHA_PHASE16_GATE_RUN_ROOT:-/data/trace_net_runs/nha_phase16_server_gate_v1}"

mkdir -p "$RUN_ROOT"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/scripts:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON_BIN" -B -m pytest -q \
  tests/unit/test_trace_net_nha_engram_v1.py \
  tests/unit/test_trace_net_nha_phase14_16_cognitive_v1.py

bash scripts/operations/serving/launch_trace_net_nha_phase16_server_v1.sh shadow

"$PYTHON_BIN" -B - <<PY
import json, urllib.request
payload={"messages":[{"role":"user","content":"What larger unit contains 120-20970-001?"}]}
req=urllib.request.Request(
    "${BASE_URL}/v1/nha/decision",
    data=json.dumps(payload).encode(),
    headers={"Content-Type":"application/json","Authorization":"Bearer ${API_KEY}"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    body=json.loads(r.read().decode())
    assert r.status == 200
    assert r.headers.get("X-Trace-Net-NHA-Action") == "shadow_candidate"
    assert r.headers.get("X-Trace-Net-NHA-Engram-Skill") == "nha_direct_parent_lookup"
    assert int(r.headers.get("X-Trace-Net-NHA-Engram-Atoms") or 0) >= 1
    assert r.headers.get("X-Trace-Net-NHA-Gemma-Calls") == "0"
print("TRACE_NET_NHA_PHASE14_SHADOW_CONNECTION=PASS")
PY

bash scripts/operations/serving/launch_trace_net_nha_phase16_server_v1.sh gated

LIVE20_DIR="$RUN_ROOT/gemma20"
rm -rf "$LIVE20_DIR"
"$PYTHON_BIN" -B scripts/benchmark/s3_graph_store/run_trace_net_nha_phase16_gemma20_v1.py \
  --phase4-dir "$RELEASE_DIR" \
  --nha-engram-dir "$ENGRAM_DIR" \
  --base-url "$BASE_URL" \
  --api-key "$API_KEY" \
  --model "$MODEL" \
  --output-dir "$LIVE20_DIR" \
  --expected-count 20 \
  --request-timeout 300 \
  --strict

"$PYTHON_BIN" -B scripts/benchmark/graph/check_trace_net_nha_phase16_gemma20_v1.py \
  --output-dir "$LIVE20_DIR" \
  --expected-count 20 \
  --expected-gemma-overrides 18 \
  --strict

echo "TRACE_NET_NHA_PHASE17_REAL_SITUATION_MODEL_CALL_GATE=PASS"
echo "status=TRACE_NET_NHA_PHASE16_SERVER_GATE_V1"
echo "quality_status=PASS"
echo "engram_dir=$ENGRAM_DIR"
echo "gemma20_dir=$LIVE20_DIR"
echo "public_base_url=$BASE_URL/v1"
echo "public_model=$MODEL"
