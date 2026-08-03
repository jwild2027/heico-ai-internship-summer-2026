#!/usr/bin/env bash
set -euo pipefail

REPO="${TRACE_NET_REPO:-$(pwd)}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="${TRACE_NET_PYTHON_BIN:-$VENV/bin/python}"
RUN_ROOT="${TRACE_NET_NHA_PHASE18_GATE_RUN_ROOT:-/data/trace_net_runs/nha_phase18_unified8131_gate_v1}"
PUBLIC_KEY="${TRACE_NET_OPENWEBUI_COGNITIVE_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_OPENWEBUI_COGNITIVE_MODEL:-trace-net-gemma4-cognitive-rag-v1}"

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$RUN_ROOT"

"$PYTHON" -m pytest -q \
  tests/unit/test_trace_net_nha_engram_v1.py \
  tests/unit/test_trace_net_nha_phase14_16_cognitive_v1.py \
  tests/unit/test_trace_net_nha_phase18_unified8131_v1.py

bash scripts/operations/launch_trace_net_cognitive_openwebui_nha_unified_v1.sh promote

rollback_on_failure() {
  status=$?
  bash scripts/operations/launch_trace_net_cognitive_openwebui_nha_unified_v1.sh rollback || true
  exit "$status"
}
trap rollback_on_failure ERR

BRIDGE_HOST="$(ip -4 addr show docker0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -1)"
[[ -n "$BRIDGE_HOST" ]] || BRIDGE_HOST="172.17.0.1"

"$PYTHON" -B scripts/operations/graph/run_trace_net_nha_phase18_unified8131_gate_v1.py \
  --base-url "http://$BRIDGE_HOST:8131" \
  --api-key "$PUBLIC_KEY" \
  --model "$PUBLIC_MODEL" \
  --output-dir "$RUN_ROOT/mixed12" \
  --timeout-seconds 300 \
  --strict

"$PYTHON" -B scripts/maintenance/graph/check_trace_net_nha_phase18_unified8131_gate_v1.py \
  --output-dir "$RUN_ROOT/mixed12" \
  --strict

curl --fail-with-body --silent --show-error "http://$BRIDGE_HOST:8131/health" \
  > "$RUN_ROOT/final_8131_health.json"
"$PYTHON" -m json.tool "$RUN_ROOT/final_8131_health.json"
trap - ERR

echo "TRACE_NET_NHA_PHASE18_UNIFIED8131_MIXED12=PASS"
echo "TRACE_NET_NHA_PHASE18_UNIFIED8131_CHECK=PASS"
echo "TRACE_NET_NHA_PHASE18_ACTUAL_MODEL_CALL_GATE=PASS"
echo "status=TRACE_NET_NHA_PHASE18_UNIFIED8131_SERVER_GATE_V1"
echo "quality_status=PASS"
echo "public_base_url=http://$BRIDGE_HOST:8131/v1"
echo "public_model=$PUBLIC_MODEL"
echo "legacy_8131_rollback_command=bash scripts/operations/launch_trace_net_cognitive_openwebui_nha_unified_v1.sh rollback"
echo "port_8132_untouched=true"
