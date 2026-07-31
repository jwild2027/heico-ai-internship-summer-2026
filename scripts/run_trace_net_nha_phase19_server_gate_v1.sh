#!/usr/bin/env bash
set -euo pipefail

REPO="${TRACE_NET_REPO:-$(pwd)}"
VENV="${TRACE_NET_VENV:-/home/jwild/rag-workspace/.venv}"
PYTHON="${TRACE_NET_PYTHON_BIN:-$VENV/bin/python}"
RUN_ROOT="${TRACE_NET_NHA_PHASE19_GATE_RUN_ROOT:-/data/trace_net_runs/nha_phase19_upstream_latency_writer_v1}"
PUBLIC_KEY="${TRACE_NET_OPENWEBUI_COGNITIVE_KEY:-trace-net-openwebui-cognitive}"
PUBLIC_MODEL="${TRACE_NET_OPENWEBUI_COGNITIVE_MODEL:-trace-net-gemma4-cognitive-rag-v1}"
UPSTREAM_AVG_MAX="${TRACE_NET_NHA_PHASE19_UPSTREAM_AVERAGE_MAX_SECONDS:-80}"
UPSTREAM_MAX="${TRACE_NET_NHA_PHASE19_UPSTREAM_MAXIMUM_MAX_SECONDS:-100}"
NHA_MAX="${TRACE_NET_NHA_PHASE19_NHA_MAXIMUM_MAX_SECONDS:-20}"

cd "$REPO"
source "$VENV/bin/activate"
export PYTHONPATH="$REPO/scripts:$REPO${PYTHONPATH:+:$PYTHONPATH}"
export TRACE_NET_RUNTIME_DIR="${TRACE_NET_RUNTIME_DIR:-/data/trace_net_runs/cognitive_openwebui_phase19_v1}"
mkdir -p "$RUN_ROOT"

"$PYTHON" -m pytest -q \
  tests/unit/test_trace_net_nha_engram_v1.py \
  tests/unit/test_trace_net_nha_phase14_16_cognitive_v1.py \
  tests/unit/test_trace_net_nha_phase18_unified8131_v1.py \
  tests/unit/test_trace_net_h30_phase19_route_completion_fastpath_v1.py \
  tests/unit/test_trace_net_h30_phase19_preservation_writer_v1.py \
  tests/unit/test_trace_net_nha_phase19_gate_v1.py

rollback_on_failure() {
  status=$?
  bash scripts/launch_trace_net_nha_phase19_stack_v1.sh rollback || true
  exit "$status"
}
trap rollback_on_failure ERR

bash scripts/launch_trace_net_nha_phase19_stack_v1.sh promote

BRIDGE_HOST="$(ip -4 addr show docker0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -1)"
[[ -n "$BRIDGE_HOST" ]] || BRIDGE_HOST="172.17.0.1"

curl --fail-with-body --silent --show-error http://127.0.0.1:8118/health \
  > "$RUN_ROOT/8118_health.json"
curl --fail-with-body --silent --show-error http://127.0.0.1:8128/health \
  > "$RUN_ROOT/8128_health.json"

"$PYTHON" - "$RUN_ROOT/8118_health.json" "$RUN_ROOT/8128_health.json" <<'PY'
import json, sys
from pathlib import Path
router=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
writer=json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
rf=router.get("phase19_route_completion_fastpath") or {}
pw=writer.get("phase19_preservation_writer") or {}
print("phase19_route_completion_enabled=", rf.get("enabled"))
print("phase19_preservation_writer_enabled=", pw.get("enabled"))
if router.get("quality_status") != "PASS" or rf.get("enabled") is not True:
    raise SystemExit("N19 route-completion health gate failed")
if writer.get("quality_status") != "PASS" or pw.get("enabled") is not True:
    raise SystemExit("N19 preservation-writer health gate failed")
print("TRACE_NET_NHA_PHASE19_UPSTREAM_HEALTH=PASS")
PY

"$PYTHON" -B scripts/run_trace_net_nha_phase19_unified8131_gate_v1.py \
  --base-url "http://$BRIDGE_HOST:8131" \
  --api-key "$PUBLIC_KEY" \
  --model "$PUBLIC_MODEL" \
  --output-dir "$RUN_ROOT/mixed12" \
  --timeout-seconds 300 \
  --upstream-average-max-seconds "$UPSTREAM_AVG_MAX" \
  --upstream-maximum-max-seconds "$UPSTREAM_MAX" \
  --nha-maximum-max-seconds "$NHA_MAX" \
  --strict

"$PYTHON" -B scripts/check_trace_net_nha_phase19_unified8131_gate_v1.py \
  --output-dir "$RUN_ROOT/mixed12" \
  --strict

curl --fail-with-body --silent --show-error "http://$BRIDGE_HOST:8131/health" \
  > "$RUN_ROOT/final_8131_health.json"
"$PYTHON" -m json.tool "$RUN_ROOT/final_8131_health.json"
trap - ERR

echo "TRACE_NET_NHA_PHASE19_UNIFIED8131=PASS"
echo "TRACE_NET_NHA_PHASE19_ACCEPTANCE_GATE=PASS"
echo "TRACE_NET_NHA_PHASE19_LATENCY_GATE=PASS"
echo "status=TRACE_NET_NHA_PHASE19_SERVER_GATE_V1"
echo "quality_status=PASS"
echo "public_base_url=http://$BRIDGE_HOST:8131/v1"
echo "public_model=$PUBLIC_MODEL"
echo "rollback_command=bash scripts/launch_trace_net_nha_phase19_stack_v1.sh rollback"
echo "port_8132_untouched=true"
